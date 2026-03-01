"""FastAPI app entrypoint."""

import asyncio
import logging
import os
import time
import traceback
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import bcrypt
from sqlalchemy import select, text
from starlette.middleware.base import BaseHTTPMiddleware

from api.logging_config import setup_logging
from api.routers import (
    admin, ads, advertisers, advertiser_trends, analytics, auth, brand_channels,
    buzz, campaign_effect, campaigns, competitors, consumer_insights, download,
    events, export, impact, industries, master_index,
    marketing_schedule, meta_signals, mobile_panel, payments, launch_impact,
    products, smartstore, social_channels, social_impact, spend, staging,
    stealth_surf, target_audience, trends,
)
from database import async_session, init_db
from database.models import User

logger = logging.getLogger("adscope.api")

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def _ensure_master_account():
    """Create the initial admin account if it does not exist."""
    admin_email = os.getenv("ADMIN_EMAIL", "admin@adscope.kr")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin1234")

    if admin_password == "admin1234":
        logger.warning(
            "ADMIN_PASSWORD is using default value. "
            "Change it in .env for production!"
        )

    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == admin_email))
        if result.scalar_one_or_none() is None:
            master = User(
                email=admin_email,
                hashed_password=_hash_password(admin_password),
                name="Administrator",
                role="admin",
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            session.add(master)
            await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 DB 초기화 + 마스터 계정 생성."""
    setup_logging()
    logger.info("AdScope API starting up")
    await init_db()
    await _ensure_master_account()
    try:
        yield
    finally:
        logger.info("AdScope API shutting down")
        from database import engine
        await engine.dispose()
        logger.info("Database engine disposed")


app = FastAPI(
    title="AdScope API",
    description="한국 디지털 광고 통합 모니터링 인텔리전스 플랫폼",
    version="0.2.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

_cors_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001,https://adscope.kr,https://www.adscope.kr,https://api.adscope.kr")
CORS_ORIGINS = [o.strip() for o in _cors_origins.split(",") if o.strip()]


# ---------------------------------------------------------------------------
# Rate limiting middleware
# ---------------------------------------------------------------------------
class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter per client IP + route group."""

    _CLEANUP_INTERVAL = 3600  # 1 hour

    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()
        self._lock = asyncio.Lock()

    def _cleanup_stale_keys(self):
        """Remove keys whose timestamp lists are entirely expired (>120s old)."""
        now = time.time()
        if now - self._last_cleanup < self._CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        stale_keys = [
            k for k, ts_list in self.requests.items()
            if not ts_list or (now - ts_list[-1]) > 120
        ]
        for k in stale_keys:
            del self.requests[k]
        if stale_keys:
            logger.debug("Rate limiter cleanup: removed %d stale keys", len(stale_keys))

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Rate limit config: (max_requests, window_seconds, bucket_key)
        if path.startswith("/api/auth/login"):
            limit, window, bucket = 10, 60, "login"
        elif path.startswith("/api/admin"):
            limit, window, bucket = 30, 60, "admin"
        elif path.startswith("/api/"):
            limit, window, bucket = 120, 60, "api"
        else:
            return await call_next(request)

        async with self._lock:
            # Periodic cleanup of stale entries
            self._cleanup_stale_keys()

            key = f"{client_ip}:{bucket}"
            now = time.time()
            self.requests[key] = [t for t in self.requests[key] if now - t < window]

            if len(self.requests[key]) >= limit:
                oldest = self.requests[key][0]
                retry_after = int(window - (now - oldest)) + 1
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )

            self.requests[key].append(now)

        return await call_next(request)


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard security headers into every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            "%s %s -> %d (%.2fs)",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response


app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # HTTPException(401/403 등)은 원래 상태코드로 직접 반환
    if isinstance(exc, HTTPException):
        headers = getattr(exc, "headers", None) or {}
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=headers,
        )
    logger.error(
        "Unhandled exception on %s %s: %s (type=%s)",
        request.method,
        request.url.path,
        str(exc),
        type(exc).__name__,
    )
    logger.debug(traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(ads.router)
app.include_router(advertisers.router)
app.include_router(spend.router)
app.include_router(campaigns.router)
app.include_router(trends.router)
app.include_router(analytics.router)
app.include_router(competitors.router)
app.include_router(industries.router)
app.include_router(products.router)
app.include_router(brand_channels.router)
app.include_router(social_channels.router)
app.include_router(meta_signals.router)
app.include_router(smartstore.router)
app.include_router(social_impact.router)
app.include_router(payments.router)
app.include_router(advertiser_trends.router)
app.include_router(export.router)
app.include_router(events.router)
app.include_router(staging.router)
app.include_router(launch_impact.router)
app.include_router(impact.router)
app.include_router(marketing_schedule.router)
app.include_router(mobile_panel.router)
app.include_router(stealth_surf.router)
app.include_router(download.router)
app.include_router(buzz.router)
app.include_router(consumer_insights.router)
app.include_router(target_audience.router)
app.include_router(campaign_effect.router)
app.include_router(master_index.router)


# ---------------------------------------------------------------------------
# SECURITY WARNING [C4]: StaticFiles mounts below serve images WITHOUT
# authentication.  Any user (or bot) who knows an image filename can access
# it directly.  This is acceptable during development, but MUST be replaced
# with an authenticated image-serving endpoint (e.g. a FastAPI route that
# validates a JWT token or session cookie) before production deployment.
#
# TODO: Replace these StaticFiles mounts with an API route that checks
#       `get_current_user` (see api/deps.py) and streams the file via
#       `FileResponse` or `StreamingResponse`.  The download.py router
#       already contains `_resolve_image_path()` which can be reused.
# ---------------------------------------------------------------------------

# 로컬 이미지 스토리지 서빙
_image_dir = Path(os.getenv("IMAGE_STORE_DIR", "stored_images"))
if _image_dir.exists():
    app.mount("/images", StaticFiles(directory=str(_image_dir)), name="images")

# screenshots 디렉토리 서빙 (backfill 이미지 등)
_screenshots_dir = Path("screenshots")
if _screenshots_dir.exists():
    app.mount("/screenshots", StaticFiles(directory=str(_screenshots_dir)), name="screenshots")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect to API docs."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    """Production-grade health check with monitoring."""
    import platform
    import shutil
    from database import engine

    health_status = {"status": "ok", "service": "adscope-api", "version": "0.2.0"}

    # DB connectivity check
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        health_status["database"] = "connected"
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["database"] = f"error: {str(e)}"

    # DB file size
    db_path = os.path.join(os.getcwd(), "adscope.db")
    if os.path.exists(db_path):
        size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
        health_status["db_size_mb"] = size_mb
        if size_mb > 500:
            health_status["db_size_warning"] = True

    # Disk space
    try:
        total, used, free = shutil.disk_usage(os.getcwd())
        health_status["disk_free_gb"] = round(free / (1024**3), 1)
        if free / (1024**3) < 5:
            health_status["disk_warning"] = True
    except Exception:
        pass

    # Last crawl freshness
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT MAX(captured_at) FROM ad_snapshots"))
            last = result.scalar()
            if last:
                from datetime import timezone as tz
                hours_ago = (datetime.now(tz.utc).replace(tzinfo=None) - last).total_seconds() / 3600
                health_status["last_crawl_hours_ago"] = round(hours_ago, 1)
                if hours_ago > 26:
                    health_status["crawl_stale"] = True
    except Exception:
        pass

    # Active users count
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM users WHERE is_active = 1"))
            health_status["active_users"] = result.scalar() or 0
    except Exception:
        pass

    # Backup status
    backup_dir = os.path.join(os.getcwd(), "backups")
    if os.path.exists(backup_dir):
        backups = sorted(Path(backup_dir).glob("adscope_*.db"), reverse=True)
        if backups:
            health_status["last_backup"] = backups[0].name
            health_status["backup_count"] = len(backups)

    health_status["python"] = platform.python_version()
    return health_status


# ---------------------------------------------------------------------------
# TEMPORARY: Data upload endpoint for Railway migration
# Remove after initial data is transferred
# ---------------------------------------------------------------------------
@app.post("/api/_upload_data", include_in_schema=False)
async def upload_data(file: UploadFile = File(...), secret: str = ""):
    """Upload gzipped DB or tar.gz images to /data volume."""
    import gzip
    import shutil

    if secret != "adscope-migrate-2026":
        raise HTTPException(status_code=403, detail="Forbidden")

    filename = file.filename or "unknown"
    data_dir = Path("/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    if filename.endswith(".db.gz"):
        # Gzipped SQLite DB — must close engine, remove WAL/SHM, then replace
        from database import engine, DATABASE_URL
        # Resolve actual DB path from DATABASE_URL (e.g. sqlite+aiosqlite:///adscope.db)
        db_path_str = DATABASE_URL.split("///")[-1]
        if not os.path.isabs(db_path_str):
            db_path_str = os.path.join("/app", db_path_str)
        target = Path(db_path_str)
        wal = Path(f"{db_path_str}-wal")
        shm = Path(f"{db_path_str}-shm")

        # Dispose all connections so SQLite releases the file
        await engine.dispose()

        # Remove WAL/SHM journal files from the old (empty) DB
        for f_path in [wal, shm]:
            if f_path.exists():
                f_path.unlink()

        with open("/tmp/upload.db.gz", "wb") as f:
            shutil.copyfileobj(file.file, f)
        with gzip.open("/tmp/upload.db.gz", "rb") as gz:
            with open(target, "wb") as out:
                shutil.copyfileobj(gz, out)
        os.remove("/tmp/upload.db.gz")

        # Re-initialize engine so API keeps working after upload
        from database import init_db
        await init_db()

        size_mb = round(target.stat().st_size / (1024 * 1024), 2)
        return {"status": "ok", "file": str(target), "size_mb": size_mb}

    elif filename.endswith(".tar.gz"):
        # Images archive
        import tarfile
        tmp_path = "/tmp/upload.tar.gz"
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        with tarfile.open(tmp_path, "r:gz") as tar:
            tar.extractall(path=str(data_dir))
        os.remove(tmp_path)
        return {"status": "ok", "extracted_to": str(data_dir)}

    else:
        raise HTTPException(status_code=400, detail="Only .db.gz or .tar.gz")
