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
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(_root) / ".env")

# -- Default 6 channels --
_DEFAULT_CHANNELS = "naver_search,naver_da,kakao_da,google_gdn,youtube_ads,facebook,instagram,naver_shopping"
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


def _handle_signal(sig, _frame):
    """Graceful shutdown on SIGINT / SIGTERM."""
    sig_name = signal.Signals(sig).name
    logger.info("Received {}, shutting down...", sig_name)
    if _scheduler is not None:
        try:
            _scheduler.stop()
        except Exception:
            pass
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

    # -- Wait for shutdown --
    _shutdown_event = asyncio.Event()
    logger.info("Scheduler running. Ctrl+C to stop.")
    await _shutdown_event.wait()

    logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
