"""TikTok Creative Center 크롤러 테스트."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler.tiktok_ads import TikTokAdsCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import PC_DEVICE


def sp(*args):
    try:
        print(*args)
    except UnicodeEncodeError:
        print(" ".join(str(a) for a in args).encode("ascii", "replace").decode())


async def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    sp(f"=== TikTok Ads Crawler Test ===")

    async with TikTokAdsCrawler() as crawler:
        result = await crawler.crawl_keyword(keyword, PERSONAS["M30"], PC_DEVICE)

    ads = result.get("ads", [])
    sp(f"\nTotal: {len(ads)} ads | Duration: {result.get('crawl_duration_ms', 0)}ms")

    for i, ad in enumerate(ads[:15]):
        extra = ad.get("extra_data", {})
        sp(f"\n[{i+1}] {ad.get('advertiser_name') or '?'}")
        sp(f"    {(ad.get('ad_text') or '')[:60]}")
        sp(f"    industry={extra.get('industry','?')} ctr={extra.get('ctr','?')} likes={extra.get('like_count','?')}")
        sp(f"    cover={'Y' if ad.get('creative_image_path') else 'N'} video={'Y' if extra.get('video_url') else 'N'}")

    if len(ads) > 15:
        sp(f"\n... +{len(ads) - 15} more")

    return len(ads)


if __name__ == "__main__":
    count = asyncio.run(main())
    sys.exit(0 if count > 0 else 1)
