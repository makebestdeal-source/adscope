"""각 채널 빠르게 1회씩 테스트 — 결과 요약 출력."""
import asyncio
import sys
import os
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# 환경변수 오버라이드 — 빠른 테스트용
os.environ["YOUTUBE_AD_WAIT_MS"] = "10000"
os.environ["GDN_MAX_PUBLISHERS"] = "2"
os.environ["GDN_ARTICLES_PER_PUBLISHER"] = "2"
os.environ["GDN_TRUST_CHECK"] = "false"
os.environ["META_TRUST_CHECK"] = "false"
os.environ["META_FEED_SCROLL_COUNT"] = "2"
os.environ["KAKAO_MAX_MEDIA"] = "2"
os.environ["KAKAO_LANDING_RESOLVE_LIMIT"] = "2"
os.environ["NAVER_DA_CATEGORY_TABS"] = "2"
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "3"
os.environ["INSTAGRAM_REELS_SWIPES"] = "3"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<5} | {message}")

from database import init_db
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEFAULT_MOBILE, PC_DEVICE


TESTS = [
    ("naver_search", "pc", "travel"),
    ("naver_da", "mobile", "travel"),
    ("google_gdn", "pc", "travel"),
    ("kakao_da", "mobile", "travel"),
    ("youtube_ads", "pc", "travel"),
    ("facebook", "pc", "travel"),
    ("instagram", "mobile", "beauty"),
]


async def test_channel(channel_name: str, device_type: str, keyword: str):
    """단일 채널 테스트 — 결과 요약 반환."""
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
                timeout=120,  # 2분 타임아웃
            )
        elapsed = time.time() - t0
        ads = result.get("ads", [])
        ad_count = len(ads)

        # 광고 요약
        summary_lines = []
        for ad in ads[:5]:
            name = ad.get("advertiser_name", "?")
            text = (ad.get("ad_text") or "")[:40]
            src = ad.get("extra_data", {}).get("detection_method") or ad.get("extra_data", {}).get("source") or ad.get("ad_type", "")
            summary_lines.append(f"    {name} | {text} | [{src}]")

        return {
            "channel": channel_name,
            "device": device_type,
            "status": "OK" if ad_count > 0 else "EMPTY",
            "ads": ad_count,
            "elapsed": f"{elapsed:.1f}s",
            "details": summary_lines,
            "error": None,
        }
    except asyncio.TimeoutError:
        return {
            "channel": channel_name,
            "device": device_type,
            "status": "TIMEOUT",
            "ads": 0,
            "elapsed": f"{time.time()-t0:.1f}s",
            "details": [],
            "error": "2분 타임아웃",
        }
    except Exception as e:
        return {
            "channel": channel_name,
            "device": device_type,
            "status": "ERROR",
            "ads": 0,
            "elapsed": f"{time.time()-t0:.1f}s",
            "details": [],
            "error": str(e)[:200],
        }


async def main():
    await init_db()

    print("\n" + "=" * 70)
    print("  AdScope 채널별 빠른 테스트 (각 채널 2분 제한)")
    print("=" * 70)

    results = []
    for channel, device, keyword in TESTS:
        print(f"\n>>> [{channel}] ({device}) 테스트 시작...")
        result = await test_channel(channel, device, keyword)
        results.append(result)

        status_icon = {"OK": "✓", "EMPTY": "△", "TIMEOUT": "✗", "ERROR": "✗"}.get(result["status"], "?")
        print(f"  {status_icon} {result['channel']:20s} | {result['status']:8s} | 광고 {result['ads']:3d}건 | {result['elapsed']}")
        if result["error"]:
            print(f"    ERROR: {result['error']}")
        for line in result["details"]:
            print(line)

    # 최종 요약
    print("\n" + "=" * 70)
    print("  최종 결과 요약")
    print("=" * 70)
    for r in results:
        status_icon = {"OK": "✓", "EMPTY": "△", "TIMEOUT": "✗", "ERROR": "✗"}.get(r["status"], "?")
        print(f"  {status_icon} {r['channel']:20s} | {r['status']:8s} | 광고 {r['ads']:3d}건 | {r['elapsed']}")

    ok = sum(1 for r in results if r["status"] == "OK")
    total = len(results)
    print(f"\n  성공: {ok}/{total}")


if __name__ == "__main__":
    asyncio.run(main())
