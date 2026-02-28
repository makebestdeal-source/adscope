"""Admin panel API -- JWT authentication + system management."""

import csv
import io
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import require_admin
from database import get_db
from database.models import (
    AdDetail, AdSnapshot, Advertiser, Keyword, Persona, Industry, User,
    BrandChannelContent, ChannelStats, SmartStoreSnapshot, TrafficSignal,
    ActivityScore, MetaSignalComposite, PaymentRecord,
)
from database.schemas import CSVImportResult

router = APIRouter(prefix="/api/admin", tags=["admin"])

logger = logging.getLogger("adscope.admin")

# ---------------------------------------------------------------------------
# Subprocess tracking -- prevent duplicate runs, log stderr to logs/
# ---------------------------------------------------------------------------
_running_processes: dict[str, subprocess.Popen] = {}
_LOGS_DIR = os.path.join(os.getcwd(), "logs")


def _ensure_logs_dir():
    os.makedirs(_LOGS_DIR, exist_ok=True)


def _is_process_alive(name: str) -> bool:
    """Check if a tracked process is still running."""
    proc = _running_processes.get(name)
    if proc is None:
        return False
    if proc.poll() is not None:
        # Process has finished -- clean up
        del _running_processes[name]
        return False
    return True


def _start_tracked_process(name: str, args: list[str], **kwargs) -> subprocess.Popen:
    """Start a subprocess and track it by name.

    Raises HTTPException(409) if a process with the same name is already running.
    stderr is redirected to logs/<name>.stderr.log instead of DEVNULL.
    The stderr file handle is properly closed after being inherited by the child
    process to prevent file descriptor leaks in the parent.
    """
    if _is_process_alive(name):
        raise HTTPException(
            status_code=409,
            detail=f"'{name}' is already running (PID {_running_processes[name].pid})",
        )
    _ensure_logs_dir()
    stderr_path = os.path.join(_LOGS_DIR, f"{name}.stderr.log")
    stderr_file = open(stderr_path, "a", encoding="utf-8", errors="replace")
    try:
        stderr_file.write(f"\n--- Started at {datetime.now().isoformat()} ---\n")
        stderr_file.flush()
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=stderr_file,
            **kwargs,
        )
    except Exception:
        stderr_file.close()
        raise
    finally:
        # Close our copy of the file handle -- the child process has inherited it.
        # This prevents file descriptor leaks in the parent (API) process.
        stderr_file.close()
    _running_processes[name] = proc
    logger.info("Started %s (PID %d), stderr -> %s", name, proc.pid, stderr_path)
    return proc


@router.get("/crawl/processes")
async def crawl_process_status(
    _admin: User = Depends(require_admin),
):
    """Show status of all tracked background processes."""
    result = {}
    finished = []
    for name, proc in list(_running_processes.items()):
        rc = proc.poll()
        if rc is not None:
            result[name] = {"pid": proc.pid, "status": "finished", "returncode": rc}
            finished.append(name)
        else:
            result[name] = {"pid": proc.pid, "status": "running"}
    # Clean up finished processes
    for name in finished:
        del _running_processes[name]
    return {
        "processes": result,
        "active_count": sum(1 for v in result.values() if v["status"] == "running"),
    }


@router.get("/stats")
async def admin_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """System-wide statistics for admin dashboard."""
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)

    total_snapshots = (await db.execute(select(func.count(AdSnapshot.id)))).scalar() or 0
    total_ads = (await db.execute(select(func.count(AdDetail.id)))).scalar() or 0
    total_advertisers = (await db.execute(select(func.count(Advertiser.id)))).scalar() or 0
    total_keywords = (await db.execute(select(func.count(Keyword.id)))).scalar() or 0
    total_personas = (await db.execute(select(func.count(Persona.id)))).scalar() or 0

    # Channel distribution
    channel_dist = await db.execute(
        select(AdSnapshot.channel, func.count(AdSnapshot.id))
        .group_by(AdSnapshot.channel)
    )

    # Latest crawl time
    latest = await db.execute(select(func.max(AdSnapshot.captured_at)))
    latest_dt = latest.scalar()
    latest_crawl = None
    if latest_dt:
        latest_kst = latest_dt + timedelta(hours=9)
        latest_crawl = latest_kst.isoformat()

    # DB file size
    db_size_mb = 0
    try:
        db_path = os.path.join(os.getcwd(), "adscope.db")
        if os.path.exists(db_path):
            db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)
    except Exception:
        pass

    return {
        "total_snapshots": total_snapshots,
        "total_ads": total_ads,
        "total_advertisers": total_advertisers,
        "total_keywords": total_keywords,
        "total_personas": total_personas,
        "by_channel": {row[0]: row[1] for row in channel_dist.all()},
        "latest_crawl": latest_crawl,
        "db_size_mb": db_size_mb,
        "server_time": now_kst.isoformat(),
    }


@router.get("/crawl-status")
async def crawl_status(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """채널별 수집 현황: 마지막 수집 시간, 오늘 수집 건수, 상태."""
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    today_start_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_utc = today_start_kst.replace(tzinfo=None) - timedelta(hours=9)

    # 채널별 마지막 수집 시간
    last_crawl_q = await db.execute(
        select(
            AdSnapshot.channel,
            func.max(AdSnapshot.captured_at).label("last_crawl"),
            func.count(AdSnapshot.id).label("total_snapshots"),
        )
        .group_by(AdSnapshot.channel)
    )

    # 채널별 오늘 수집 건수 (광고 개수)
    today_q = await db.execute(
        select(
            AdSnapshot.channel,
            func.count(AdDetail.id).label("today_ads"),
        )
        .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at >= today_start_utc)
        .group_by(AdSnapshot.channel)
    )
    today_map = {row[0]: row[1] for row in today_q.all()}

    channels = []
    for row in last_crawl_q.all():
        ch = row.channel
        last_dt = row.last_crawl
        last_kst = None
        minutes_ago = None
        status = "idle"

        if last_dt:
            last_kst_dt = last_dt + timedelta(hours=9)
            last_kst = last_kst_dt.isoformat()
            diff = now_kst.replace(tzinfo=None) - last_kst_dt
            minutes_ago = int(diff.total_seconds() / 60)
            if minutes_ago < 60:
                status = "recent"
            elif minutes_ago < 1440:  # 24h
                status = "today"
            else:
                status = "stale"

        channels.append({
            "channel": ch,
            "last_crawl_kst": last_kst,
            "minutes_ago": minutes_ago,
            "status": status,
            "total_snapshots": row.total_snapshots,
            "today_ads": today_map.get(ch, 0),
        })

    # 전체 통계
    total_advertisers = (await db.execute(select(func.count(Advertiser.id)))).scalar() or 0
    total_ads = (await db.execute(select(func.count(AdDetail.id)))).scalar() or 0
    total_snapshots = (await db.execute(select(func.count(AdSnapshot.id)))).scalar() or 0

    # 오늘 전체 수집 건수
    today_total = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at >= today_start_utc)
    )

    return {
        "channels": sorted(channels, key=lambda x: x["today_ads"], reverse=True),
        "summary": {
            "total_advertisers": total_advertisers,
            "total_ads": total_ads,
            "total_snapshots": total_snapshots,
            "today_total_ads": today_total.scalar() or 0,
        },
        "server_time_kst": now_kst.isoformat(),
    }


@router.post("/ai-enrich")
async def run_ai_enrich(
    limit: int = 100,
    channel: str | None = None,
    _admin: User = Depends(require_admin),
):
    """Trigger AI enrichment batch (DeepSeek Vision)."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise HTTPException(status_code=400, detail="DEEPSEEK_API_KEY not set in .env")
    try:
        from processor.ai_enricher import enrich_ads
        stats = await enrich_ads(limit=limit, channel_filter=channel)
        return {"status": "done", **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crawl/start")
async def start_crawl(
    _admin: User = Depends(require_admin),
):
    """Trigger a crawl run (fast_crawl.py) in the background."""
    script_path = os.path.join(os.getcwd(), "scripts", "fast_crawl.py")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="fast_crawl.py not found")

    try:
        proc = _start_tracked_process(
            "fast_crawl",
            [sys.executable, "-u", script_path],
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return {"status": "started", "pid": proc.pid, "message": "Crawl started in background"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels")
async def list_channels(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all channels with their ad counts."""
    result = await db.execute(
        select(
            AdSnapshot.channel,
            func.count(AdSnapshot.id).label("snapshots"),
            func.sum(AdSnapshot.ad_count).label("ads"),
            func.max(AdSnapshot.captured_at).label("last_crawl"),
        )
        .group_by(AdSnapshot.channel)
        .order_by(func.count(AdSnapshot.id).desc())
    )
    channels = []
    for row in result.all():
        last_crawl = None
        if row.last_crawl:
            last_crawl = (row.last_crawl + timedelta(hours=9)).isoformat()
        channels.append({
            "channel": row.channel,
            "snapshots": row.snapshots,
            "ads": row.ads or 0,
            "last_crawl": last_crawl,
        })
    return channels


@router.post("/import-advertisers", response_model=CSVImportResult)
async def import_advertisers_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Import or update advertisers from a CSV file.

    Expected columns: name, industry, annual_revenue, employee_count,
    founded_year, headquarters, is_public, market_cap, business_category,
    website, description
    """
    content = await file.read()
    try:
        text_content = content.decode("utf-8-sig")  # Handle Excel BOM
    except UnicodeDecodeError:
        text_content = content.decode("cp949", errors="replace")

    reader = csv.DictReader(io.StringIO(text_content))

    # Build industry name -> id map
    ind_result = await db.execute(select(Industry))
    industry_map: dict[str, int] = {}
    for ind in ind_result.scalars().all():
        industry_map[ind.name.lower()] = ind.id

    # Build existing advertiser name -> object map
    adv_result = await db.execute(select(Advertiser))
    existing_map: dict[str, Advertiser] = {}
    for adv in adv_result.scalars().all():
        existing_map[adv.name.lower()] = adv

    created = 0
    updated = 0
    skipped = 0
    errors: list[str] = []
    total_rows = 0

    for row_num, row in enumerate(reader, start=2):
        total_rows += 1
        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1
            errors.append(f"Row {row_num}: empty name, skipped")
            continue

        try:
            # Resolve industry
            industry_name = (row.get("industry") or "").strip()
            industry_id = industry_map.get(industry_name.lower()) if industry_name else None

            # Parse numeric fields safely
            annual_revenue = _parse_float(row.get("annual_revenue"))
            employee_count = _parse_int(row.get("employee_count"))
            founded_year = _parse_int(row.get("founded_year"))
            market_cap = _parse_float(row.get("market_cap"))
            is_public = _parse_bool(row.get("is_public"))
            headquarters = (row.get("headquarters") or "").strip() or None
            business_category = (row.get("business_category") or "").strip() or None
            website = (row.get("website") or "").strip() or None
            description = (row.get("description") or "").strip() or None

            if name.lower() in existing_map:
                # Update existing advertiser
                adv = existing_map[name.lower()]
                if industry_id is not None:
                    adv.industry_id = industry_id
                if annual_revenue is not None:
                    adv.annual_revenue = annual_revenue
                if employee_count is not None:
                    adv.employee_count = employee_count
                if founded_year is not None:
                    adv.founded_year = founded_year
                if market_cap is not None:
                    adv.market_cap = market_cap
                if is_public is not None:
                    adv.is_public = is_public
                if headquarters:
                    adv.headquarters = headquarters
                if business_category:
                    adv.business_category = business_category
                if website:
                    adv.website = website
                if description:
                    adv.description = description
                adv.data_source = "csv"
                adv.profile_updated_at = datetime.utcnow()
                updated += 1
            else:
                # Create new advertiser
                adv = Advertiser(
                    name=name,
                    brand_name=name,
                    industry_id=industry_id,
                    annual_revenue=annual_revenue,
                    employee_count=employee_count,
                    founded_year=founded_year,
                    market_cap=market_cap,
                    is_public=is_public or False,
                    headquarters=headquarters,
                    business_category=business_category,
                    website=website,
                    description=description,
                    data_source="csv",
                    profile_updated_at=datetime.utcnow(),
                )
                db.add(adv)
                existing_map[name.lower()] = adv
                created += 1

        except Exception as e:
            skipped += 1
            errors.append(f"Row {row_num} ({name}): {str(e)}")

    await db.commit()

    return CSVImportResult(
        total_rows=total_rows,
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors[:50],  # Limit error messages
    )


@router.post("/collect/social")
async def start_social_collection(
    _admin: User = Depends(require_admin),
):
    """Trigger brand monitor + social stats collection."""
    try:
        cmd = (
            "import asyncio, sys, os\n"
            "sys.path.insert(0, os.getcwd())\n"
            "from dotenv import load_dotenv\n"
            "load_dotenv()\n"
            "from database import init_db\n"
            "async def run():\n"
            "    await init_db()\n"
            "    from scheduler.scheduler import AdScopeScheduler\n"
            "    s = AdScopeScheduler()\n"
            "    await s._run_brand_monitor()\n"
            "    await s._run_social_stats()\n"
            "asyncio.run(run())\n"
        )
        proc = _start_tracked_process(
            "social_collection",
            [sys.executable, "-c", cmd],
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return {"status": "started", "pid": proc.pid, "message": "소셜 수집 시작 (브랜드 모니터 + 소셜 통계)"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/smartstore")
async def start_smartstore_signal(
    _admin: User = Depends(require_admin),
):
    """Trigger SmartStore meta-signal collection."""
    try:
        cmd = (
            "import asyncio, sys, os\n"
            "sys.path.insert(0, os.getcwd())\n"
            "from dotenv import load_dotenv\n"
            "load_dotenv()\n"
            "from database import init_db\n"
            "async def run():\n"
            "    await init_db()\n"
            "    from processor.smartstore_collector import collect_smartstore_signals\n"
            "    result = await collect_smartstore_signals()\n"
            "    print(result)\n"
            "asyncio.run(run())\n"
        )
        proc = _start_tracked_process(
            "smartstore_signal",
            [sys.executable, "-c", cmd],
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return {"status": "started", "pid": proc.pid, "message": "스마트스토어 신호 수집 시작"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/traffic")
async def start_traffic_signal(
    _admin: User = Depends(require_admin),
):
    """Trigger traffic signal estimation."""
    try:
        cmd = (
            "import asyncio, sys, os\n"
            "sys.path.insert(0, os.getcwd())\n"
            "from dotenv import load_dotenv\n"
            "load_dotenv()\n"
            "from database import init_db\n"
            "async def run():\n"
            "    await init_db()\n"
            "    from processor.traffic_estimator import estimate_traffic_signals\n"
            "    result = await estimate_traffic_signals()\n"
            "    print(result)\n"
            "asyncio.run(run())\n"
        )
        proc = _start_tracked_process(
            "traffic_signal",
            [sys.executable, "-c", cmd],
            cwd=os.getcwd(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return {"status": "started", "pid": proc.pid, "message": "트래픽 신호 수집 시작"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/activity")
async def start_activity_score(
    _admin: User = Depends(require_admin),
):
    """Trigger activity score calculation."""
    try:
        from processor.activity_scorer import calculate_activity_scores
        result = await calculate_activity_scores()
        return {"status": "done", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/meta-aggregate")
async def start_meta_aggregate(
    _admin: User = Depends(require_admin),
):
    """Trigger meta-signal aggregation."""
    try:
        from processor.meta_signal_aggregator import aggregate_meta_signals
        result = await aggregate_meta_signals()
        return {"status": "done", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/campaign-rebuild")
async def start_campaign_rebuild(
    _admin: User = Depends(require_admin),
):
    """Trigger campaign & spend rebuild."""
    try:
        from processor.campaign_builder import rebuild_campaigns_and_spend
        result = await rebuild_campaigns_and_spend(active_days=7)
        return {"status": "done", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/journey-ingest")
async def start_journey_ingest(
    _admin: User = Depends(require_admin),
):
    """Trigger journey event ingestion."""
    try:
        from processor.journey_ingestor import ingest_journey_events
        result = await ingest_journey_events()
        return {"status": "done", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/campaign-enrich")
async def start_campaign_enrich(
    _admin: User = Depends(require_admin),
):
    """Trigger campaign metadata AI enrichment."""
    try:
        from processor.campaign_enricher import enrich_campaign_metadata
        result = await enrich_campaign_metadata(limit=100)
        return {"status": "done", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collect/lift-calculate")
async def start_lift_calculate(
    _admin: User = Depends(require_admin),
):
    """Trigger campaign lift calculation."""
    try:
        from processor.lift_calculator import calculate_campaign_lifts
        result = await calculate_campaign_lifts()
        return {"status": "done", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule-overview")
async def schedule_overview(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Return full schedule overview with categories and last run times."""

    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)

    async def _last_ts(model, col):
        r = await db.execute(select(func.max(col)))
        v = r.scalar()
        if v:
            return (v + timedelta(hours=9)).isoformat()
        return None

    last_crawl = await _last_ts(AdSnapshot, AdSnapshot.captured_at)
    last_brand = await _last_ts(BrandChannelContent, BrandChannelContent.discovered_at)
    last_social = await _last_ts(ChannelStats, ChannelStats.collected_at)
    last_smartstore = await _last_ts(SmartStoreSnapshot, SmartStoreSnapshot.captured_at)
    last_traffic = await _last_ts(TrafficSignal, TrafficSignal.date)
    last_activity = await _last_ts(ActivityScore, ActivityScore.date)
    last_meta = await _last_ts(MetaSignalComposite, MetaSignalComposite.date)

    # Count rows
    brand_count = (await db.execute(select(func.count(BrandChannelContent.id)))).scalar() or 0
    channel_stats_count = (await db.execute(select(func.count(ChannelStats.id)))).scalar() or 0
    smartstore_count = (await db.execute(select(func.count(SmartStoreSnapshot.id)))).scalar() or 0
    traffic_count = (await db.execute(select(func.count(TrafficSignal.id)))).scalar() or 0
    activity_count = (await db.execute(select(func.count(ActivityScore.id)))).scalar() or 0
    meta_count = (await db.execute(select(func.count(MetaSignalComposite.id)))).scalar() or 0

    schedule = {
        "categories": [
            {
                "id": "ad_collection",
                "name": "광고 수집",
                "description": "접촉 + 카탈로그 광고 데이터 수집",
                "items": [
                    {
                        "id": "fast_crawl",
                        "name": "병렬 크롤링 (fast_crawl)",
                        "schedule": "수동 또는 스케줄러",
                        "schedule_time": "평일 08:00~22:00 (페르소나별)",
                        "last_run": last_crawl,
                        "trigger_endpoint": "/api/admin/crawl/start",
                        "description": "7채널 병렬 수집 (네이버/카카오/구글/유튜브/메타/인스타)",
                    },
                    {
                        "id": "ai_enrich",
                        "name": "AI 보강",
                        "schedule": "매일 03:00",
                        "schedule_time": "03:00 KST",
                        "last_run": None,
                        "trigger_endpoint": "/api/admin/ai-enrich",
                        "description": "DeepSeek 텍스트 + Vision 광고 분류/보강",
                    },
                    {
                        "id": "campaign_rebuild",
                        "name": "캠페인/광고비 리빌드",
                        "schedule": "수집 완료 후 자동",
                        "schedule_time": "수집 직후",
                        "last_run": None,
                        "trigger_endpoint": "/api/admin/collect/campaign-rebuild",
                        "description": "SpendEstimatorV2 기반 광고비 역추정",
                    },
                ],
            },
            {
                "id": "social_collection",
                "name": "소셜 수집",
                "description": "브랜드 채널 콘텐츠 + 소셜 통계",
                "items": [
                    {
                        "id": "brand_monitor",
                        "name": "브랜드 채널 모니터링",
                        "schedule": "매일 02:00",
                        "schedule_time": "02:00 KST",
                        "last_run": last_brand,
                        "data_count": brand_count,
                        "trigger_endpoint": "/api/admin/collect/social",
                        "description": "YouTube/Instagram 채널 콘텐츠 수집 (영상, 게시물)",
                    },
                    {
                        "id": "social_stats",
                        "name": "소셜 통계 (인게이지먼트)",
                        "schedule": "매일 02:30",
                        "schedule_time": "02:30 KST",
                        "last_run": last_social,
                        "data_count": channel_stats_count,
                        "trigger_endpoint": "/api/admin/collect/social",
                        "description": "구독자/팔로워 수, 인게이지먼트율 계산",
                    },
                ],
            },
            {
                "id": "meta_signals",
                "name": "메타시그널",
                "description": "스마트스토어/트래픽/활동 지수 -> 광고비 보정",
                "items": [
                    {
                        "id": "smartstore",
                        "name": "스마트스토어 신호",
                        "schedule": "매일 04:00",
                        "schedule_time": "04:00 KST",
                        "last_run": last_smartstore,
                        "data_count": smartstore_count,
                        "trigger_endpoint": "/api/admin/collect/smartstore",
                        "description": "네이버 스마트스토어 리뷰/매출 메타데이터",
                    },
                    {
                        "id": "traffic",
                        "name": "트래픽 신호",
                        "schedule": "매일 04:30",
                        "schedule_time": "04:30 KST",
                        "last_run": last_traffic,
                        "data_count": traffic_count,
                        "trigger_endpoint": "/api/admin/collect/traffic",
                        "description": "네이버 DataLab + Google Trends 검색 지수",
                    },
                    {
                        "id": "activity",
                        "name": "활동 점수",
                        "schedule": "매일 05:00",
                        "schedule_time": "05:00 KST",
                        "last_run": last_activity,
                        "data_count": activity_count,
                        "trigger_endpoint": "/api/admin/collect/activity",
                        "description": "크리에이티브/캠페인/채널 활동 복합 점수",
                    },
                    {
                        "id": "meta_aggregate",
                        "name": "메타시그널 통합",
                        "schedule": "매일 05:30",
                        "schedule_time": "05:30 KST",
                        "last_run": last_meta,
                        "data_count": meta_count,
                        "trigger_endpoint": "/api/admin/collect/meta-aggregate",
                        "description": "3개 신호 통합 -> spend_multiplier(0.7~1.5) 산출",
                    },
                ],
            },
        ],
        "timeline": [
            {"time": "02:00", "label": "브랜드 채널 모니터링", "category": "social"},
            {"time": "02:30", "label": "소셜 통계 (인게이지먼트)", "category": "social"},
            {"time": "03:00", "label": "AI 보강", "category": "ad"},
            {"time": "04:00", "label": "스마트스토어 신호", "category": "meta"},
            {"time": "04:30", "label": "트래픽 신호", "category": "meta"},
            {"time": "05:00", "label": "활동 점수", "category": "meta"},
            {"time": "05:30", "label": "메타시그널 통합", "category": "meta"},
            {"time": "08:00-22:00", "label": "광고 접촉 수집 (페르소나 스케줄)", "category": "ad"},
        ],
        "server_time_kst": now_kst.isoformat(),
    }
    return schedule


@router.get("/benchmarks")
async def list_benchmarks(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all spend benchmarks with calibration factors."""
    from processor.spend_calibrator import list_benchmarks as _list
    return await _list(db)


@router.post("/benchmarks")
async def create_benchmark(
    data: dict,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Create a new spend benchmark entry.

    Body: {advertiser_id, channel?, actual_monthly_spend, period_start, period_end,
           advertiser_size, source?, notes?}
    """
    from database.models import SpendBenchmark
    from processor.spend_calibrator import classify_advertiser_size

    adv_id = data.get("advertiser_id")
    if not adv_id:
        raise HTTPException(400, "advertiser_id required")
    actual = data.get("actual_monthly_spend")
    if not actual or actual <= 0:
        raise HTTPException(400, "actual_monthly_spend must be positive")

    period_start = datetime.fromisoformat(data["period_start"]) if data.get("period_start") else datetime.now() - timedelta(days=30)
    period_end = datetime.fromisoformat(data["period_end"]) if data.get("period_end") else datetime.now()

    # Auto-determine industry from advertiser
    adv = await db.execute(select(Advertiser).where(Advertiser.id == adv_id))
    adv_obj = adv.scalar_one_or_none()
    if not adv_obj:
        raise HTTPException(404, f"Advertiser {adv_id} not found")

    bm = SpendBenchmark(
        advertiser_id=adv_id,
        channel=data.get("channel"),
        period_start=period_start,
        period_end=period_end,
        actual_monthly_spend=actual,
        advertiser_size=data.get("advertiser_size") or classify_advertiser_size(actual),
        source=data.get("source", "direct_input"),
        industry_id=adv_obj.industry_id,
        notes=data.get("notes"),
    )
    db.add(bm)
    await db.commit()
    await db.refresh(bm)

    return {"id": bm.id, "advertiser_name": adv_obj.name, "calibration_factor": bm.calibration_factor}


@router.post("/benchmarks/recalculate")
async def recalculate_benchmarks(
    _admin: User = Depends(require_admin),
):
    """Recalculate all benchmark calibration factors."""
    from processor.spend_calibrator import compute_calibration_factors
    result = await compute_calibration_factors()
    return result


# -- 결제/회원 관리 --

@router.get("/payments")
async def list_payments(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all payment records."""
    stmt = select(PaymentRecord, User.email, User.company_name).join(
        User, PaymentRecord.user_id == User.id
    ).order_by(PaymentRecord.created_at.desc()).limit(200)
    if status:
        stmt = stmt.where(PaymentRecord.status == status)
    result = await db.execute(stmt)
    return [
        {
            "id": r.id, "user_id": r.user_id, "email": email,
            "company_name": company, "merchant_uid": r.merchant_uid,
            "plan": r.plan, "plan_period": r.plan_period,
            "amount": r.amount, "pay_method": r.pay_method,
            "status": r.status,
            "paid_at": r.paid_at.isoformat() if r.paid_at else None,
            "verified_at": r.verified_at.isoformat() if r.verified_at else None,
            "activated_by": r.activated_by,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r, email, company in result.all()
    ]


@router.post("/payments/{payment_id}/activate")
async def activate_payment(
    payment_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin: activate a paid subscription."""
    result = await db.execute(
        select(PaymentRecord).where(PaymentRecord.id == payment_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Payment not found")
    if record.status not in ("paid", "pending"):
        raise HTTPException(400, f"Cannot activate payment with status '{record.status}'")

    # Update payment record
    record.status = "activated"
    record.verified_at = datetime.now(timezone.utc)
    record.activated_by = admin.email

    # Update user plan
    user_result = await db.execute(select(User).where(User.id == record.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        now = datetime.now(timezone.utc)
        if record.plan_period == "yearly":
            expires = now + timedelta(days=365)
        else:
            expires = now + timedelta(days=30)
        user.plan = record.plan
        user.plan_period = record.plan_period
        user.plan_started_at = now
        user.plan_expires_at = expires
        user.payment_confirmed = True

    await db.commit()
    return {"status": "activated", "payment_id": payment_id, "user_email": user.email if user else None}


@router.post("/payments/{payment_id}/reject")
async def reject_payment(
    payment_id: int,
    reason: str = "rejected by admin",
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin: reject a payment."""
    result = await db.execute(
        select(PaymentRecord).where(PaymentRecord.id == payment_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Payment not found")
    record.status = "refunded"
    record.notes = reason
    await db.commit()
    return {"status": "rejected", "payment_id": payment_id}


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all users with plan info."""
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).limit(500)
    )
    users = result.scalars().all()
    return [
        {
            "id": u.id, "email": u.email, "name": u.name,
            "company_name": u.company_name, "role": u.role,
            "plan": u.plan, "plan_period": u.plan_period,
            "is_active": u.is_active,
            "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
            "trial_started_at": u.trial_started_at.isoformat() if u.trial_started_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users/{user_id}/extend")
async def extend_user_plan(
    user_id: int,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin: extend a user's plan expiry."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    base = user.plan_expires_at or datetime.now(timezone.utc)
    user.plan_expires_at = base + timedelta(days=days)
    await db.commit()
    return {"status": "extended", "new_expires_at": user.plan_expires_at.isoformat()}


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin: deactivate a user account."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")
    if user.role == "admin":
        raise HTTPException(400, "Cannot deactivate admin")
    user.is_active = False
    await db.commit()
    return {"status": "deactivated", "user_id": user_id}


def _parse_float(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    try:
        return float(value.strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def _parse_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    try:
        return int(float(value.strip().replace(",", "")))
    except (ValueError, TypeError):
        return None


def _parse_bool(value: str | None) -> bool | None:
    if not value or not value.strip():
        return None
    v = value.strip().lower()
    if v in ("true", "1", "yes", "y"):
        return True
    if v in ("false", "0", "no", "n"):
        return False
    return None
