"""Small-sample live crawler validation with field completeness checks."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from loguru import logger

from crawler.google_gdn import GoogleGDNCrawler
from crawler.google_search_ads import GoogleSearchAdsCrawler
from crawler.kakao_da import KakaoDACrawler
from crawler.meta_library import MetaLibraryCrawler
from crawler.naver_da import NaverDACrawler
from crawler.naver_search import NaverSearchCrawler
from crawler.naver_shopping import NaverShoppingCrawler
from crawler.personas.device_config import DEVICES
from crawler.personas.profiles import PERSONAS
from crawler.tiktok_ads import TikTokAdsCrawler
from crawler.youtube_ads import YouTubeAdsCrawler

load_dotenv(ROOT / ".env")

# Keep live validation fast and comparable.
os.environ.setdefault("CRAWLER_WARMUP_SITE_COUNT", "0")
os.environ.setdefault("CRAWLER_DWELL_MIN_MS", "800")
os.environ.setdefault("CRAWLER_DWELL_MAX_MS", "1400")
os.environ.setdefault("CRAWLER_DWELL_SCROLL_COUNT_MIN", "1")
os.environ.setdefault("CRAWLER_DWELL_SCROLL_COUNT_MAX", "2")
os.environ.setdefault("CRAWLER_INTER_PAGE_MIN_MS", "300")
os.environ.setdefault("CRAWLER_INTER_PAGE_MAX_MS", "600")
os.environ.setdefault("KAKAO_MAX_MEDIA", "6")
os.environ.setdefault("KAKAO_LANDING_RESOLVE_LIMIT", "2")
os.environ.setdefault("NAVER_DA_CATEGORY_TABS", "2")
os.environ.setdefault("META_MAX_PAGES", "2")
os.environ.setdefault("META_AD_LIMIT", "25")
os.environ.setdefault("GDN_MAX_ADVERTISERS", "8")
os.environ.setdefault("GDN_MAX_ADS", "25")
os.environ.setdefault("GS_ADS_MAX_ADVERTISERS", "6")
os.environ.setdefault("GS_ADS_MAX_ADS", "25")
os.environ.setdefault("YT_ADS_MAX_ADVERTISERS", "6")
os.environ.setdefault("YT_ADS_MAX_ADS", "25")
os.environ.setdefault("NAVER_SHOP_MAX_ADS", "20")

OUT_DIR = ROOT / "cache" / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_FIELDS = (
    "advertiser_name",
    "ad_text",
    "url",
    "display_url",
    "ad_placement",
)


@dataclass(frozen=True)
class ValidationCase:
    channel: str
    crawler_cls: type
    keyword: str
    persona_code: str
    device_key: str


DEFAULT_CASES: list[ValidationCase] = [
    ValidationCase("naver_search", NaverSearchCrawler, "대출", "M30", "mobile"),
    ValidationCase("naver_da", NaverDACrawler, "main", "CTRL_CLEAN", "pc"),
    ValidationCase("naver_shopping", NaverShoppingCrawler, "에어팟", "CTRL_CLEAN", "pc"),
    ValidationCase("kakao_da", KakaoDACrawler, "qa", "CTRL_CLEAN", "mobile"),
    ValidationCase("google_gdn", GoogleGDNCrawler, "보험", "CTRL_CLEAN", "pc"),
    ValidationCase("google_search_ads", GoogleSearchAdsCrawler, "보험", "CTRL_CLEAN", "pc"),
    ValidationCase("youtube_ads", YouTubeAdsCrawler, "보험", "CTRL_CLEAN", "pc"),
    ValidationCase("tiktok_ads", TikTokAdsCrawler, "lip", "CTRL_CLEAN", "pc"),
    ValidationCase("meta", MetaLibraryCrawler, "대출", "CTRL_CLEAN", "pc"),
]


def _pct(missing: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(missing * 100.0 / total, 2)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _field_completeness(ads: list[dict]) -> dict[str, dict[str, float | int]]:
    total = len(ads)
    stats: dict[str, dict[str, float | int]] = {}
    for field in REQUIRED_FIELDS:
        missing = sum(1 for ad in ads if _is_missing(ad.get(field)))
        stats[field] = {
            "missing": missing,
            "present": total - missing,
            "missing_pct": _pct(missing, total),
        }
    return stats


def _sample_rows(ads: list[dict], sample_size: int) -> list[dict]:
    rows: list[dict] = []
    for ad in ads[:sample_size]:
        rows.append(
            {
                "advertiser_name": ad.get("advertiser_name"),
                "ad_text": ad.get("ad_text"),
                "url": ad.get("url"),
                "display_url": ad.get("display_url"),
                "ad_placement": ad.get("ad_placement"),
                "ad_type": ad.get("ad_type"),
            }
        )
    return rows


async def _run_case(case: ValidationCase, sample_size: int) -> dict:
    persona = PERSONAS[case.persona_code]
    device = DEVICES[case.device_key]
    captured_at = datetime.now(timezone.utc).isoformat(sep=" ")

    async with case.crawler_cls() as crawler:
        try:
            result = await crawler.crawl_keyword(case.keyword, persona, device)
            ads = result.get("ads") or []
            return {
                "channel": case.channel,
                "status": "ok",
                "keyword": case.keyword,
                "device": case.device_key,
                "captured_at": captured_at,
                "total_ads": len(ads),
                "missing": _field_completeness(ads),
                "sample": _sample_rows(ads, sample_size),
            }
        except Exception as exc:
            logger.exception("[validation] {} failed", case.channel)
            return {
                "channel": case.channel,
                "status": "error",
                "keyword": case.keyword,
                "device": case.device_key,
                "captured_at": captured_at,
                "error": str(exc)[:300],
                "total_ads": 0,
                "missing": _field_completeness([]),
                "sample": [],
            }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run small live crawler validation")
    parser.add_argument(
        "--channels",
        default="all",
        help="Comma-separated channels to validate, or 'all'",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=3,
        help="Number of sample ads to include per channel",
    )
    return parser.parse_args()


async def _main():
    args = _parse_args()
    requested = None
    if args.channels != "all":
        requested = {part.strip() for part in args.channels.split(",") if part.strip()}

    cases = [case for case in DEFAULT_CASES if requested is None or case.channel in requested]
    if not cases:
        raise SystemExit("No matching channels selected")

    logger.remove()
    logger.add(sys.stderr, level="INFO")

    results = []
    for case in cases:
        logger.info(
            "[validation] running {} keyword='{}' device={}",
            case.channel,
            case.keyword,
            case.device_key,
        )
        results.append(await _run_case(case, max(1, args.sample_size)))

    out_path = OUT_DIR / "live_crawler_validation_latest.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
