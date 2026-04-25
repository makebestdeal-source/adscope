"""AdScope Scheduler Runner -- 6-channel production scheduler.

Usage:
    python scripts/run_scheduler.py

Environment variables:
    CRAWL_CHANNELS  -- comma-separated channel list
                       (default: naver_search,naver_da,kakao_da,google_gdn,youtube_ads,facebook)

Ctrl+C or SIGTERM for graceful shutdown.
"""

import asyncio
import io
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(_root) / ".env")

# -- Default 6 channels --
_DEFAULT_CHANNELS = "naver_search,naver_da,kakao_da,google_gdn,youtube_ads,meta,naver_shopping"
os.environ.setdefault("CRAWL_CHANNELS", _DEFAULT_CHANNELS)

from loguru import logger  # noqa: E402
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

_logs_dir = Path(_root) / "logs"
_logs_dir.mkdir(exist_ok=True)
logger.add(
    str(_logs_dir / "scheduler_{time:YYYY-MM-DD}.log"),
    rotation="1 day",
    retention="7 days",
    level="DEBUG",
    encoding="utf-8",
)

from crawler.stealth_patch import enable_stealth  # noqa: E402
enable_stealth()  # playwright-stealth 전체 크롤러 적용

from database import init_db, async_session  # noqa: E402
from database.models import Keyword, Industry  # noqa: E402
from scheduler.scheduler import AdScopeScheduler  # noqa: E402
from sqlalchemy import select  # noqa: E402


_scheduler: AdScopeScheduler | None = None
_shutdown_event: asyncio.Event | None = None


def _kill_orphan_nodes():
    """현재 Python 프로세스 하위가 아닌 좀비 node.exe 프로세스 정리 (Windows)."""
    try:
        import psutil
        my_pid = os.getpid()
        my_children = {p.pid for p in psutil.Process(my_pid).children(recursive=True)}
        killed = 0
        for proc in psutil.process_iter(["pid", "name", "ppid"]):
            try:
                if proc.info["name"] and "node" in proc.info["name"].lower():
                    if proc.info["pid"] not in my_children:
                        # 부모가 살아있는 node는 건드리지 않음 (VSCode 등)
                        try:
                            parent = psutil.Process(proc.info["ppid"])
                            if parent.is_running() and parent.name() not in ("python.exe", "python"):
                                continue
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass  # 부모 없음 = orphan
                        proc.kill()
                        killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if killed:
            logger.info("[node_cleanup] orphan node 프로세스 {} 개 정리", killed)
    except ImportError:
        # psutil 없으면 taskkill fallback (과격하지만 최후 수단)
        subprocess.run(["taskkill", "/F", "/IM", "node.exe"],
                       capture_output=True, check=False)
        logger.info("[node_cleanup] taskkill /F /IM node.exe 실행")
    except Exception as e:
        logger.debug("[node_cleanup] error: {}", e)


def _handle_signal(sig, _frame):
    """Graceful shutdown on SIGINT / SIGTERM."""
    sig_name = signal.Signals(sig).name
    logger.info("Received {}, shutting down...", sig_name)
    if _scheduler is not None:
        try:
            _scheduler.stop()
        except Exception:
            pass
    _kill_orphan_nodes()
    if _shutdown_event is not None:
        _shutdown_event.set()


async def _sync_seed_data():
    """Sync industries + keywords from seed JSON into DB (additive only)."""
    seed_dir = Path(_root) / "database" / "seed_data"

    industries_path = seed_dir / "industries.json"
    keywords_path = seed_dir / "keywords.json"

    if not keywords_path.exists():
        logger.warning("Keyword seed not found: {}", keywords_path)
        return

    async with async_session() as session:
        # -- Industries --
        if industries_path.exists():
            with open(industries_path, encoding="utf-8") as f:
                industries_data = json.load(f)
            for item in industries_data:
                result = await session.execute(
                    select(Industry).where(Industry.id == item["id"])
                )
                if not result.scalar_one_or_none():
                    session.add(Industry(
                        id=item["id"],
                        name=item["name"],
                        avg_cpc_min=item.get("avg_cpc_min"),
                        avg_cpc_max=item.get("avg_cpc_max"),
                    ))
            await session.flush()

        # -- Keywords --
        with open(keywords_path, encoding="utf-8") as f:
            seed_data = json.load(f)

        existing = await session.execute(select(Keyword.keyword))
        existing_set = {row[0] for row in existing.all()}

        added = 0
        for item in seed_data:
            kw = item["keyword"].strip()
            if kw not in existing_set:
                session.add(Keyword(
                    industry_id=item["industry_id"],
                    keyword=kw,
                    naver_cpc=item.get("naver_cpc"),
                    monthly_search_vol=item.get("monthly_search_vol"),
                ))
                added += 1

        if added > 0:
            await session.commit()
            logger.info("Synced {} new keywords into DB", added)
        else:
            logger.info("All keywords already in DB ({})", len(existing_set))


async def main():
    global _scheduler, _shutdown_event

    # -- Signal handlers --
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # -- DB init --
    await init_db()
    logger.info("DB initialized")

    # -- Sync seed data --
    await _sync_seed_data()

    # -- Scheduler --
    _scheduler = AdScopeScheduler()
    _scheduler.load_keywords()
    _scheduler.setup_schedules()

    channels = os.environ.get("CRAWL_CHANNELS", _DEFAULT_CHANNELS)
    logger.info("Starting scheduler | channels: {}", channels)
    logger.info("Keywords loaded: {}", len(_scheduler._keywords))

    _scheduler.start()

    # -- 시작 시 한 번 orphan node 정리 --
    _kill_orphan_nodes()

    # -- 30분마다 orphan node 정리 태스크 --
    async def _periodic_node_cleanup():
        while not (_shutdown_event and _shutdown_event.is_set()):
            await asyncio.sleep(30 * 60)
            _kill_orphan_nodes()

    asyncio.ensure_future(_periodic_node_cleanup())

    # -- Wait for shutdown --
    _shutdown_event = asyncio.Event()
    logger.info("Scheduler running. Ctrl+C to stop.")
    await _shutdown_event.wait()

    # -- 종료 시 최종 정리 --
    _kill_orphan_nodes()
    logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
