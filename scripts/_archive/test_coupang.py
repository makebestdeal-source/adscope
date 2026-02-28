"""쿠팡 광고 크롤러 테스트."""

import asyncio
import io
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from crawler.coupang_ads import CoupangAdsCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import PC_DEVICE


async def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else "화장품"
    print(f"=== Coupang Ads Crawler Test: '{keyword}' ===")

    async with CoupangAdsCrawler() as crawler:
        result = await crawler.crawl_keyword(keyword, PERSONAS["M30"], PC_DEVICE)

    ads = result.get("ads", [])
    print(f"\nTotal: {len(ads)} ads | Duration: {result.get('crawl_duration_ms', 0)}ms")

    for i, ad in enumerate(ads[:10]):
        extra = ad.get("extra_data", {})
        print(f"\n[{i+1}] {ad.get('advertiser_name') or '?'}")
        print(f"    {(ad.get('ad_text') or '')[:60]}")
        print(f"    price={extra.get('price','?')}")

    if len(ads) > 10:
        print(f"\n... +{len(ads) - 10} more")

    return len(ads)


if __name__ == "__main__":
    count = asyncio.run(main())
    sys.exit(0 if count > 0 else 1)
