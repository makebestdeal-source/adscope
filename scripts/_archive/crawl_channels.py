"""Run one-off crawl for selected channels and persist results."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

from loguru import logger
from sqlalchemy import select

_project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(Path(_project_root) / ".env")

from crawler.google_gdn import GoogleGDNCrawler
from crawler.kakao_da import KakaoDACrawler
from crawler.meta_library import MetaLibraryCrawler
from crawler.naver_da import NaverDACrawler
from crawler.naver_search import NaverSearchCrawler
from crawler.youtube_ads import YouTubeAdsCrawler
from crawler.instagram_mobile import InstagramMobileCrawler
from database import async_session, init_db
from database.models import Keyword
from processor.campaign_builder import rebuild_campaigns_and_spend
from processor.pipeline import save_crawl_results

CRAWLER_MAP = {
    "naver_search": NaverSearchCrawler,
    "naver_da": NaverDACrawler,
    "youtube_ads": YouTubeAdsCrawler,
    "facebook": MetaLibraryCrawler,
    "instagram": InstagramMobileCrawler,
    "google_gdn": GoogleGDNCrawler,
    "kakao_da": KakaoDACrawler,
}


def _parse_args():
    parser = argparse.ArgumentParser(description="One-off multi-channel crawl")
    parser.add_argument(
        "--channels",
        default=os.getenv("CRAWL_CHANNELS", "naver_search"),
        help="Comma separated channels: naver_search,naver_da,youtube_ads,facebook,instagram,google_gdn,kakao_da",
    )
    parser.add_argument("--persona", default="M30", help="Persona code (default: M30)")
    parser.add_argument(
        "--device",
        default="both",
        choices=["pc", "mobile", "both"],
        help="Device type: pc, mobile, or both (default: both)",
    )
    parser.add_argument("--limit", type=int, default=5, help="Keyword count when --keywords is omitted")
    parser.add_argument(
        "--keywords",
        default="",
        help="Comma separated explicit keywords; when omitted, load active keywords from DB",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild campaigns/spend after saving snapshots",
    )
    parser.add_argument(
        "--analyze-landings",
        action="store_true",
        help="Analyze landing pages after saving snapshots",
    )
    return parser.parse_args()


def _resolve_channels(raw: str) -> list[str]:
    channels: list[str] = []
    for chunk in raw.split(","):
        name = chunk.strip()
        if not name:
            continue
        if name not in CRAWLER_MAP:
            logger.warning("Unsupported channel ignored: {}", name)
            continue
        if name not in channels:
            channels.append(name)
    return channels or ["naver_search"]


async def _load_keywords(limit: int) -> list[str]:
    async with async_session() as session:
        rows = await session.execute(
            select(Keyword.keyword).where(Keyword.is_active.is_(True)).order_by(Keyword.id).limit(limit)
        )
        return [row[0] for row in rows.all()]


async def main():
    args = _parse_args()
    await init_db()

    channels = _resolve_channels(args.channels)
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []
    if not keywords:
        keywords = await _load_keywords(max(1, args.limit))
    if not keywords:
        raise RuntimeError("No keywords available to crawl")

    device_types = ["pc", "mobile"] if args.device == "both" else [args.device]

    logger.info("Channels: {}", ", ".join(channels))
    logger.info("Keywords: {}", ", ".join(keywords))
    logger.info("Persona/device: {}/{}", args.persona, "+".join(device_types))

    all_results: list[dict] = []
    for channel in channels:
        crawler_cls = CRAWLER_MAP[channel]
        channel_keywords = keywords
        if not getattr(crawler_cls, "keyword_dependent", True):
            channel_keywords = keywords[:1]
        for dev in device_types:
            logger.info("[run] channel start: {} ({})", channel, dev)
            async with crawler_cls() as crawler:
                results = await crawler.crawl_keywords(
                    keywords=channel_keywords,
                    persona_code=args.persona,
                    device_type=dev,
                )
                all_results.extend(results)
            logger.info("[run] channel done: {} ({}) — {} records", channel, dev, len(results))

    async with async_session() as session:
        saved = await save_crawl_results(session, all_results)

    errors = sum(1 for r in all_results if r.get("error"))
    total_ads = sum(len(r.get("ads", [])) for r in all_results if not r.get("error"))
    logger.info(
        "[run] save complete - snapshots={}, total_ads={}, errors={}",
        saved,
        total_ads,
        errors,
    )

    if args.rebuild and saved > 0:
        stats = await rebuild_campaigns_and_spend(active_days=7)
        logger.info(
            "[run] rebuild complete - campaigns={}, spend_estimates={}",
            stats["campaigns_total"],
            stats["spend_estimates_total"],
        )

    if args.analyze_landings and saved > 0:
        from processor.landing_analyzer import batch_analyze_landings

        landing_stats = await batch_analyze_landings(days=1, limit=200)
        logger.info(
            "[run] landing analysis complete - analyzed={}, backfilled={}, errors={}",
            landing_stats["analyzed"],
            landing_stats["backfilled"],
            landing_stats["errors"],
        )


if __name__ == "__main__":
    asyncio.run(main())
