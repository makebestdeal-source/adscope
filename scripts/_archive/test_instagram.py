"""Instagram crawler quick test."""
import asyncio
import io
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# Instagram credentials
os.environ["INSTAGRAM_USERNAME"] = "makebestdeal@gmail.com"
os.environ["INSTAGRAM_PASSWORD"] = "pjm990101@"
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "4"
os.environ["INSTAGRAM_REELS_SWIPES"] = "5"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from crawler.instagram_mobile import InstagramMobileCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEFAULT_MOBILE


async def main():
    crawler = InstagramMobileCrawler()
    persona = list(PERSONAS.values())[0]
    device = DEFAULT_MOBILE

    logger.info("Starting Instagram test crawl...")
    await crawler.start()
    try:
        result = await crawler.crawl_keyword("explore", persona, device)
    finally:
        await crawler.stop()

    ads = result.get("ads", [])
    method = result.get("contact_method", "none")
    elapsed = result.get("crawl_duration_ms", 0)

    print(f"\n{'='*50}")
    print(f"Contact method: {method}")
    print(f"Ads collected: {len(ads)}")
    print(f"Duration: {elapsed/1000:.1f}s")

    for i, ad in enumerate(ads[:10], 1):
        name = ad.get("advertiser_name", "?")
        atype = ad.get("ad_type", "?")
        placement = ad.get("ad_placement", "?")
        print(f"  {i}. [{atype}] {name} ({placement})")

    if len(ads) > 10:
        print(f"  ... +{len(ads)-10} more")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
