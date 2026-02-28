"""Quick integration test of the updated youtube_surf.py.

Tests that the crawler can start, create context, and detect ads
using the new persistent profile + stealth + CDP approach.
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, "c:\\Users\\user\\Desktop\\adscopre")

from crawler.youtube_surf import YouTubeSurfCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import PC_DEVICE


def safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode())


async def main():
    safe_print("=" * 60)
    safe_print("  YouTube Surf Crawler Integration Test")
    safe_print("  (persistent profile + stealth v2 + CDP)")
    safe_print("=" * 60)

    crawler = YouTubeSurfCrawler()
    safe_print(f"\n  Crawler channel: {crawler.channel}")
    safe_print(f"  Video samples: {crawler.video_samples}")
    safe_print(f"  Ad wait ms: {crawler.ad_wait_ms}")
    safe_print(f"  Stealth available: {crawler._stealth is not None}")
    safe_print(f"  Profile dir: {crawler._PROFILE_DIR}")

    # Use only 2 video samples for quick test
    crawler.video_samples = 2
    crawler.ad_wait_ms = 10000

    persona = PERSONAS["M30"]
    device = PC_DEVICE

    start = time.time()

    async with crawler:
        safe_print(f"\n  Browser started OK")
        safe_print(f"  Persistent context: {crawler._persistent_ctx is not None}")

        result = await crawler.crawl_keyword(
            keyword=None,
            persona=persona,
            device=device,
        )

        elapsed = time.time() - start

    safe_print(f"\n  Crawl completed in {elapsed:.1f}s")
    safe_print(f"  Keyword: {result.get('keyword')}")
    safe_print(f"  Ads found: {len(result.get('ads', []))}")
    safe_print(f"  Duration: {result.get('crawl_duration_ms')}ms")
    safe_print(f"  Page URL: {result.get('page_url')}")

    if result.get("ads"):
        safe_print(f"\n  Ad details:")
        for ad in result["ads"]:
            safe_print(f"    [{ad.get('ad_type')}] {ad.get('advertiser_name') or '(unknown)'}")
            safe_print(f"      source: {ad.get('extra_data', {}).get('source')}")
            safe_print(f"      url: {(ad.get('url') or '')[:80]}")
    else:
        safe_print("\n  No ads captured (this may be normal for headless)")

    # Print any extra metrics
    safe_print(f"\n  Screenshot: {result.get('screenshot_path')}")
    safe_print(f"\n  VERDICT: {'SUCCESS - Ads detected!' if result.get('ads') else 'No ads captured'}")


if __name__ == "__main__":
    asyncio.run(main())
