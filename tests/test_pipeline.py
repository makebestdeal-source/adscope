"""크롤러 -> DB 적재 파이프라인 통합 테스트."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E_TESTS") != "1",
    reason="Set RUN_E2E_TESTS=1 to run live integration tests.",
)

from sqlalchemy import func, select

from crawler.naver_search import NaverSearchCrawler
from crawler.personas.device_config import PC_DEVICE
from crawler.personas.profiles import PERSONAS
from database import async_session, init_db
from database.models import AdDetail, AdSnapshot
from processor.pipeline import save_crawl_results


async def test_pipeline():
    """크롤링 -> 정규화 -> DB 적재 전체 파이프라인 테스트."""
    await init_db()

    # 1) 크롤링
    print("=== [1/3] 크롤링 실행 ===")
    keywords = ["대출", "보험"]

    async with NaverSearchCrawler() as crawler:
        results = await crawler.crawl_keywords(
            keywords=keywords,
            persona_code="P4",
            device_type="pc",
        )

    total_ads = sum(len(r.get("ads", [])) for r in results)
    print(f"  크롤링 완료: 키워드 {len(results)}개, 광고 {total_ads}건\n")

    # 2) DB 적재
    print("=== [2/3] DB 적재 ===")
    async with async_session() as session:
        saved = await save_crawl_results(session, results)
        print(f"  DB 적재 완료: 스냅샷 {saved}개\n")

    # 3) 검증
    print("=== [3/3] DB 검증 ===")
    async with async_session() as session:
        # 스냅샷 수
        snap_count = await session.execute(select(func.count(AdSnapshot.id)))
        print(f"  총 스냅샷: {snap_count.scalar()}개")

        # 광고 수
        ad_count = await session.execute(select(func.count(AdDetail.id)))
        print(f"  총 광고 상세: {ad_count.scalar()}개")

        # 최근 스냅샷
        recent = await session.execute(
            select(AdSnapshot).order_by(AdSnapshot.captured_at.desc()).limit(3)
        )
        for snap in recent.scalars():
            print(f"\n  스냅샷 #{snap.id}")
            print(f"    채널: {snap.channel}")
            print(f"    디바이스: {snap.device}")
            print(f"    광고 수: {snap.ad_count}")
            print(f"    수집 시간: {snap.crawl_duration_ms}ms")
            print(f"    캡처: {snap.captured_at}")

        # 광고 상세 샘플
        details = await session.execute(
            select(AdDetail).limit(5)
        )
        print(f"\n  --- 광고 상세 샘플 ---")
        for d in details.scalars():
            print(f"  [{d.position}] {d.ad_type} | {d.advertiser_name_raw} | {(d.ad_text or '')[:50]}")

    print("\n=== 파이프라인 테스트 완료 ===")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
