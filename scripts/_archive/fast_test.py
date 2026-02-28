"""초고속 채널별 테스트 — dwell/scroll 최소화, 직접 결과 확인."""
import asyncio
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# 최소 대기시간으로 오버라이드
os.environ["CRAWLER_DWELL_MIN_MS"] = "2000"
os.environ["CRAWLER_DWELL_MAX_MS"] = "3000"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MIN"] = "1"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MAX"] = "2"
os.environ["CRAWLER_INTER_PAGE_MIN_MS"] = "1000"
os.environ["CRAWLER_INTER_PAGE_MAX_MS"] = "2000"
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"
os.environ["YOUTUBE_AD_WAIT_MS"] = "10000"
os.environ["GDN_MAX_PUBLISHERS"] = "2"
os.environ["GDN_ARTICLES_PER_PUBLISHER"] = "2"
os.environ["GDN_TRUST_CHECK"] = "false"
os.environ["META_TRUST_CHECK"] = "false"
os.environ["META_FEED_SCROLL_COUNT"] = "2"
os.environ["KAKAO_MAX_MEDIA"] = "2"
os.environ["KAKAO_LANDING_RESOLVE_LIMIT"] = "0"
os.environ["NAVER_DA_CATEGORY_TABS"] = "0"
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "2"
os.environ["INSTAGRAM_REELS_SWIPES"] = "2"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

from database import init_db
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEFAULT_MOBILE, PC_DEVICE


async def test_one(channel_name, device_type, keyword):
    # Late import to pick up env overrides
    from crawler.naver_search import NaverSearchCrawler
    from crawler.naver_da import NaverDACrawler
    from crawler.google_gdn import GoogleGDNCrawler
    from crawler.kakao_da import KakaoDACrawler
    from crawler.youtube_ads import YouTubeAdsCrawler
    from crawler.instagram_mobile import InstagramMobileCrawler
    from crawler.meta_library import MetaLibraryCrawler

    CRAWLERS = {
        "naver_search": NaverSearchCrawler,
        "naver_da": NaverDACrawler,
        "google_gdn": GoogleGDNCrawler,
        "kakao_da": KakaoDACrawler,
        "youtube_ads": YouTubeAdsCrawler,
        "facebook": MetaLibraryCrawler,
        "instagram": InstagramMobileCrawler,
    }

    cls = CRAWLERS[channel_name]
    persona = PERSONAS.get("M30", list(PERSONAS.values())[0])
    device = DEFAULT_MOBILE if device_type == "mobile" else PC_DEVICE

    t0 = time.time()
    try:
        async with cls() as crawler:
            result = await asyncio.wait_for(
                crawler.crawl_keyword(keyword, persona, device),
                timeout=90,
            )
        elapsed = time.time() - t0
        ads = result.get("ads", [])
        return channel_name, "OK", len(ads), f"{elapsed:.0f}s", ads[:5]
    except asyncio.TimeoutError:
        return channel_name, "TIMEOUT", 0, f"{time.time()-t0:.0f}s", []
    except Exception as e:
        return channel_name, "ERROR", 0, f"{time.time()-t0:.0f}s", [{"error": str(e)[:150]}]


async def main():
    await init_db()

    tests = [
        ("naver_search", "pc", "travel"),
        ("naver_da", "pc", "travel"),
        ("google_gdn", "pc", "travel"),
        ("kakao_da", "pc", "travel"),
        ("youtube_ads", "pc", "travel"),
        ("facebook", "pc", "travel"),
        ("instagram", "mobile", "beauty"),
    ]

    print("=" * 60)
    print("  AdScope Fast Test (90s limit per channel)")
    print("=" * 60)

    for channel, device, kw in tests:
        print(f"\n[{channel}] testing...", flush=True)
        name, status, count, elapsed, ads = await test_one(channel, device, kw)
        icon = {"OK": "O", "TIMEOUT": "X", "ERROR": "X"}.get(status, "?")
        print(f"  {icon} {name:20s} | {status:8s} | {count:3d} ads | {elapsed}")
        for ad in ads:
            if "error" in ad:
                print(f"    ERR: {ad['error']}")
            else:
                adv = ad.get("advertiser_name", "?")
                txt = (ad.get("ad_text") or "")[:35]
                src = ad.get("extra_data", {}).get("source", ad.get("ad_type", ""))
                print(f"    {adv} | {txt} | [{src}]")

    print("\n" + "=" * 60)
    print("  DONE")


if __name__ == "__main__":
    asyncio.run(main())
