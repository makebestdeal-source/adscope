"""Facebook crawlers quick test (contact + library)."""
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

os.environ["FB_CONTACT_MAX_PAGES"] = "4"
os.environ["FB_CONTACT_SCROLL_ROUNDS"] = "6"
os.environ["META_FEED_SCROLL_COUNT"] = "6"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from crawler.facebook_contact import FacebookContactCrawler
from crawler.meta_library import MetaLibraryCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEFAULT_MOBILE, PC_DEVICE


async def test_contact():
    print("\n[1] Testing FacebookContactCrawler (public pages)...")
    crawler = FacebookContactCrawler()
    persona = list(PERSONAS.values())[0]
    await crawler.start()
    try:
        result = await crawler.crawl_keyword("browse", persona, PC_DEVICE)
        ads = result.get("ads", [])
        method = result.get("contact_method", "none")
        elapsed = result.get("crawl_duration_ms", 0)
        print(f"  Contact method: {method}")
        print(f"  Ads: {len(ads)}, Duration: {elapsed/1000:.1f}s")
        for i, ad in enumerate(ads[:5], 1):
            print(f"    {i}. {ad.get('advertiser_name','?')} [{ad.get('ad_type','?')}]")
        if len(ads) > 5:
            print(f"    ... +{len(ads)-5} more")
        return len(ads)
    finally:
        await crawler.stop()


async def test_library():
    print("\n[2] Testing MetaLibraryCrawler (Ad Library)...")
    crawler = MetaLibraryCrawler()
    persona = list(PERSONAS.values())[0]
    await crawler.start()
    try:
        result = await crawler.crawl_keyword("all", persona, PC_DEVICE)
        ads = result.get("ads", [])
        elapsed = result.get("crawl_duration_ms", 0)
        print(f"  Ads: {len(ads)}, Duration: {elapsed/1000:.1f}s")
        for i, ad in enumerate(ads[:5], 1):
            print(f"    {i}. {ad.get('advertiser_name','?')} [{ad.get('ad_type','?')}]")
        if len(ads) > 5:
            print(f"    ... +{len(ads)-5} more")
        return len(ads)
    finally:
        await crawler.stop()


async def main():
    c1 = await test_contact()
    c2 = await test_library()
    print(f"\n{'='*50}")
    print(f"Facebook Contact: {c1} ads")
    print(f"Facebook Library: {c2} ads")
    print(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
