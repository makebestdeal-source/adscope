"""Integration test for new Instagram crawler priorities 3a and 3b.

Tests:
- Priority 3a: Threads.net GraphQL capture
- Priority 3b: Instagram profile coauthor extraction
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"
os.environ["CRAWLER_DWELL_MIN_MS"] = "1000"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2000"
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "2"
os.environ["INSTAGRAM_REELS_SWIPES"] = "2"
os.environ["INSTAGRAM_PUBLIC_PROFILE_VISITS"] = "2"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from crawler.instagram_mobile import InstagramMobileCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEFAULT_MOBILE


async def test_threads_only():
    """Test Threads.net browsing directly."""
    print("=" * 60)
    print("  Test: Threads.net GraphQL capture (Priority 3a)")
    print("=" * 60)

    async with InstagramMobileCrawler() as crawler:
        persona = PERSONAS.get("M30", list(PERSONAS.values())[0])
        device = DEFAULT_MOBILE

        context = await crawler._create_context(persona, device)
        try:
            t0 = time.time()
            ads = await crawler._browse_threads(context)
            elapsed = time.time() - t0

            print(f"\n  Threads result: {len(ads)} ads in {elapsed:.1f}s")
            for ad in ads[:10]:
                print(f"    - {ad.get('advertiser_name')}: "
                      f"{ad.get('ad_text', '')[:60]}")
                print(f"      type={ad.get('ad_type')} "
                      f"placement={ad.get('ad_placement')}")
                extra = ad.get("extra_data", {})
                print(f"      method={extra.get('detection_method')} "
                      f"is_contact={extra.get('is_contact')}")
        finally:
            await context.close()

    return ads


async def test_coauthor_only():
    """Test Instagram profile coauthor extraction directly."""
    print("\n" + "=" * 60)
    print("  Test: Profile coauthor extraction (Priority 3b)")
    print("=" * 60)

    async with InstagramMobileCrawler() as crawler:
        persona = PERSONAS.get("M30", list(PERSONAS.values())[0])
        device = DEFAULT_MOBILE

        context = await crawler._create_context(persona, device)
        try:
            t0 = time.time()
            ads = await crawler._extract_profile_coauthors(context)
            elapsed = time.time() - t0

            print(f"\n  Coauthor result: {len(ads)} ads in {elapsed:.1f}s")
            for ad in ads[:15]:
                print(f"    - {ad.get('advertiser_name')}: "
                      f"{ad.get('ad_text', '')[:60]}")
                extra = ad.get("extra_data", {})
                coauthors = extra.get("coauthor_usernames", [])
                print(f"      coauthors={coauthors} "
                      f"method={extra.get('detection_method')}")
        finally:
            await context.close()

    return ads


async def test_full_crawl():
    """Test full crawl_keyword with new priorities."""
    print("\n" + "=" * 60)
    print("  Test: Full crawl_keyword (all priorities)")
    print("=" * 60)

    async with InstagramMobileCrawler() as crawler:
        persona = PERSONAS.get("M30", list(PERSONAS.values())[0])
        device = DEFAULT_MOBILE

        t0 = time.time()
        result = await crawler.crawl_keyword("explore", persona, device)
        elapsed = time.time() - t0

        ads = result.get("ads", [])
        method = result.get("contact_method", "unknown")

        print(f"\n  Full crawl result:")
        print(f"    Ads: {len(ads)}")
        print(f"    Contact method: {method}")
        print(f"    Duration: {elapsed:.1f}s")
        print(f"    Page URL: {result.get('page_url', '')[:80]}")

        for ad in ads[:10]:
            is_contact = (ad.get("extra_data") or {}).get("is_contact")
            print(f"    [{ad.get('position')}] {ad.get('advertiser_name')}: "
                  f"{ad.get('ad_text', '')[:50]}... "
                  f"(contact={is_contact})")

    return result


async def main():
    print("=" * 60)
    print("  Instagram New Priorities Integration Test")
    print("=" * 60)

    # Test each new approach individually
    threads_ads = await asyncio.wait_for(test_threads_only(), timeout=120)
    coauthor_ads = await asyncio.wait_for(test_coauthor_only(), timeout=120)

    # Test full crawl flow
    full_result = await asyncio.wait_for(test_full_crawl(), timeout=300)

    # Summary
    print("\n" + "=" * 60)
    print("  INTEGRATION TEST SUMMARY")
    print("=" * 60)
    print(f"  Threads.net ads: {len(threads_ads)}")
    print(f"  Profile coauthor ads: {len(coauthor_ads)}")
    full_ads = full_result.get("ads", [])
    full_method = full_result.get("contact_method", "unknown")
    print(f"  Full crawl ads: {len(full_ads)} (method: {full_method})")

    # Check if we got contact ads
    contact_ads = [
        a for a in full_ads
        if (a.get("extra_data") or {}).get("is_contact") is True
    ]
    print(f"  Contact ads (is_contact=True): {len(contact_ads)}")


if __name__ == "__main__":
    asyncio.run(main())
