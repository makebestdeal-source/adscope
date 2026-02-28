"""JWT authentication dependencies for FastAPI."""

import os
import secrets
import warnings
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import User, UserSession

load_dotenv()

_DEFAULT_SECRET = "adscope-default-secret-key-change-in-production"
_env_secret = os.getenv("JWT_SECRET_KEY", "")


def _persist_jwt_secret() -> str:
    """Generate a JWT secret and persist it to .env so it survives restarts."""
    new_key = secrets.token_urlsafe(32)
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
            # Replace existing placeholder or append
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith("JWT_SECRET_KEY="):
                    lines[i] = "JWT_SECRET_KEY=" + new_key + "\n"
                    found = True
                    break
            if not found:
                lines.append("\nJWT_SECRET_KEY=" + new_key + "\n")
            with open(env_path, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
        else:
            with open(env_path, "w", encoding="utf-8") as fh:
                fh.write("JWT_SECRET_KEY=" + new_key + "\n")
        os.environ["JWT_SECRET_KEY"] = new_key
    except OSError:
        warnings.warn("Could not persist JWT_SECRET_KEY to .env")
    return new_key


if not _env_secret or _env_secret == _DEFAULT_SECRET:
    if os.getenv("ENVIRONMENT", "").lower() == "production":
        raise RuntimeError("JWT_SECRET_KEY must be set in production!")
    JWT_SECRET_KEY = _persist_jwt_secret()
    warnings.warn(
        "JWT_SECRET_KEY was not set - generated and saved to .env"
    )
else:
    JWT_SECRET_KEY = _env_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: int, email: str, role: str, plan: str = "lite",
    session_id: str | None = None, paid: bool = False,
) -> str:
    """Create a JWT access token with optional session binding."""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "plan": plan,
        "paid": paid,
        "exp": expire,
    }
    if session_id:
        payload["sid"] = session_id
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from a JWT Bearer token.

    Non-admin users: session (sid) must be active, device fingerprint must match.
    Admin users: bypass all session checks.
    """
    # Support _token query param for file downloads (browser can't send headers)
    token: str | None = None
    if credentials:
        token = credentials.credentials
    else:
        token = request.query_params.get("_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Admin bypasses session validation
    if user.role == "admin":
        return user

    # Plan expiry check (non-admin only)
    # plan_expires_at may be naive (SQLite) or aware — normalize both to naive UTC
    if user.plan_expires_at:
        expires = user.plan_expires_at.replace(tzinfo=None) if user.plan_expires_at.tzinfo else user.plan_expires_at
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        if expires < now_utc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Plan expired. Please renew your subscription.",
                headers={"X-Plan-Expired": "true"},
            )

    # Non-admin: validate active session
    session_id = payload.get("sid")
    if session_id:
        sess_result = await db.execute(
            select(UserSession).where(
                UserSession.session_token == session_id,
                UserSession.user_id == user.id,
                UserSession.is_active == True,
            )
        )
        session = sess_result.scalar_one_or_none()
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired - logged in from another device",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check device fingerprint match
        client_fp = request.headers.get("X-Device-Fingerprint", "")
        if (
            session.device_fingerprint
            and client_fp
            and session.device_fingerprint != client_fp
        ):
            session.is_active = False
            session.revoked_at = datetime.now(timezone.utc)
            session.revoke_reason = "fingerprint_mismatch"
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Device mismatch - please log in again",
            )

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require the current user to have admin role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


async def require_paid(user: User = Depends(get_current_user)) -> User:
    """Block free-trial users from downloading. Only paid users and admin pass."""
    if user.role == "admin":
        return user
    # payment_confirmed=True인 유저만 다운로드 허용 (어드민 제외 전원 차단)
    paid = getattr(user, "payment_confirmed", None)
    if not paid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="다운로드는 유료 회원 전용 기능입니다. 플랜을 업그레이드해주세요.",
            headers={"X-Upgrade-Required": "true"},
        )
    return user


def require_plan(min_plan: str):
    """Return a dependency that enforces a minimum plan level.

    Plan hierarchy: admin > full > lite
    Admin users always pass.

    Usage::

        @router.get("/gallery", dependencies=[Depends(require_plan("full"))])
    """
    _plan_levels = {"lite": 0, "full": 1, "admin": 2}
    required_level = _plan_levels.get(min_plan, 0)

    async def _check_plan(user: User = Depends(get_current_user)) -> User:
        # Admin bypasses all plan checks
        if user.role == "admin":
            return user
        user_level = _plan_levels.get(user.plan or "lite", 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This feature requires the '{min_plan}' plan. "
                       f"Current plan: '{user.plan or 'lite'}'",
                headers={"X-Required-Plan": min_plan},
            )
        return user

    return _check_plan
