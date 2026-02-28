"""네이버 검색광고 크롤러 실제 테스트."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_TESTS") != "1",
    reason="Set RUN_E2E_TESTS=1 to run live integration tests.",
)

from crawler.naver_search import NaverSearchCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import PC_DEVICE, MOBILE_GALAXY


async def test_single_keyword():
    """단일 키워드 PC + 모바일 테스트."""
    keyword = "대출"

    async with NaverSearchCrawler() as crawler:
        # PC 테스트
        print(f"\n{'='*60}")
        print(f"[PC] '{keyword}' 검색 중...")
        print(f"{'='*60}")

        result_pc = await crawler.crawl_keyword(keyword, PERSONAS["P4"], PC_DEVICE)
        print(f"  페이지 URL: {result_pc.get('page_url', 'N/A')}")
        print(f"  수집 시간: {result_pc.get('crawl_duration_ms', 0)}ms")
        print(f"  광고 수: {len(result_pc.get('ads', []))}건")

        for i, ad in enumerate(result_pc.get("ads", []), 1):
            print(f"\n  [{i}] {ad.get('ad_type', '?')} — 순위 {ad.get('position', '?')}")
            print(f"      광고주: {ad.get('advertiser_name', 'N/A')}")
            print(f"      제목: {ad.get('ad_text', 'N/A')[:60]}")
            print(f"      URL: {ad.get('url', 'N/A')[:80]}")

        # 모바일 테스트
        print(f"\n{'='*60}")
        print(f"[Mobile] '{keyword}' 검색 중...")
        print(f"{'='*60}")

        result_mobile = await crawler.crawl_keyword(keyword, PERSONAS["P4"], MOBILE_GALAXY)
        print(f"  페이지 URL: {result_mobile.get('page_url', 'N/A')}")
        print(f"  수집 시간: {result_mobile.get('crawl_duration_ms', 0)}ms")
        print(f"  광고 수: {len(result_mobile.get('ads', []))}건")

        for i, ad in enumerate(result_mobile.get("ads", []), 1):
            print(f"\n  [{i}] {ad.get('ad_type', '?')} — 순위 {ad.get('position', '?')}")
            print(f"      광고주: {ad.get('advertiser_name', 'N/A')}")
            print(f"      제목: {ad.get('ad_text', 'N/A')[:60]}")

    # 결과 저장
    results = {"pc": result_pc, "mobile": result_mobile}
    # datetime 직렬화
    for key in results:
        if "captured_at" in results[key]:
            results[key]["captured_at"] = str(results[key]["captured_at"])

    output_path = Path("tests/test_crawlers/crawl_result_sample.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n결과 저장: {output_path}")

    return results


if __name__ == "__main__":
    asyncio.run(test_single_keyword())
