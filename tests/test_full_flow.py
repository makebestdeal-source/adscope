"""추가 키워드 크롤링 + 광고주 매칭 + 광고비 추정 통합 테스트."""

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
from database import async_session, init_db
from database.models import AdDetail, AdSnapshot, Advertiser, Keyword
from processor.advertiser_matcher import AdvertiserMatcher
from processor.pipeline import save_crawl_results
from processor.spend_estimator import SpendEstimatorV1


async def test_full_flow():
    """추가 업종 크롤링 → DB 적재 → 광고주 매칭 → 광고비 추정."""
    await init_db()

    # 1) 추가 키워드 크롤링 (의료/뷰티 + 교육 업종)
    print("=== [1/4] 추가 키워드 크롤링 ===")
    keywords = ["성형외과", "영어학원"]

    async with NaverSearchCrawler() as crawler:
        results = await crawler.crawl_keywords(
            keywords=keywords,
            persona_code="P1",
            device_type="pc",
        )

    total_ads = sum(len(r.get("ads", [])) for r in results)
    print(f"  크롤링 완료: 키워드 {len(results)}개, 광고 {total_ads}건\n")

    # 2) DB 적재
    print("=== [2/4] DB 적재 ===")
    async with async_session() as session:
        saved = await save_crawl_results(session, results)
        print(f"  DB 적재 완료: 스냅샷 {saved}개\n")

    # 3) 광고주 자동 매칭
    print("=== [3/4] 광고주 자동 매칭 ===")
    matcher = AdvertiserMatcher()

    async with async_session() as session:
        # 기존 광고주 로드 (없으면 빈 상태로 시작)
        adv_result = await session.execute(select(Advertiser))
        existing = [
            {"id": a.id, "name": a.name, "aliases": a.aliases}
            for a in adv_result.scalars()
        ]
        matcher.load_advertisers(existing)
        print(f"  기존 광고주 {len(existing)}명 로드")

        # 크롤링된 광고주명으로 매칭 테스트
        details = await session.execute(select(AdDetail).limit(20))
        matched = 0
        new_names = set()

        for d in details.scalars():
            raw_name = d.advertiser_name_raw
            if not raw_name:
                continue
            adv_id, score = matcher.match(raw_name)
            if adv_id:
                matched += 1
                print(f"  [매칭] {raw_name} → ID {adv_id} (유사도 {score:.0f}%)")
            else:
                new_names.add(raw_name)

        print(f"\n  매칭 결과: {matched}건 매칭, {len(new_names)}건 신규 광고주")
        if new_names:
            print(f"  신규 광고주 목록:")
            for name in sorted(new_names)[:15]:
                print(f"    - {name}")

    # 4) 광고비 추정
    print("\n=== [4/4] 광고비 추정 ===")
    estimator = SpendEstimatorV1()

    async with async_session() as session:
        # 키워드별 CPC 가져오기
        kw_result = await session.execute(select(Keyword).where(Keyword.keyword.in_(keywords)))
        kw_map = {k.keyword: k for k in kw_result.scalars()}

        # 최근 스냅샷의 광고 상세
        for kw_name, kw_obj in kw_map.items():
            snap = await session.execute(
                select(AdSnapshot)
                .where(AdSnapshot.keyword_id == kw_obj.id)
                .order_by(AdSnapshot.captured_at.desc())
                .limit(1)
            )
            snapshot = snap.scalar_one_or_none()
            if not snapshot:
                continue

            ads = await session.execute(
                select(AdDetail).where(AdDetail.snapshot_id == snapshot.id).limit(5)
            )
            print(f"\n  [{kw_name}] CPC={kw_obj.naver_cpc:,}원, 월검색량={kw_obj.monthly_search_vol:,}")
            for ad in ads.scalars():
                est = estimator.estimate_naver_search(
                    keyword=kw_name,
                    cpc=kw_obj.naver_cpc,
                    monthly_search_vol=kw_obj.monthly_search_vol,
                    position=ad.position,
                    advertiser_name=ad.advertiser_name_raw,
                )
                print(
                    f"    #{ad.position} {ad.advertiser_name_raw or 'N/A':<20} "
                    f"→ 일 추정 {est.est_daily_spend:>10,}원 "
                    f"(신뢰도 {est.confidence:.0%})"
                )

    # 5) 전체 DB 통계
    print("\n=== 전체 DB 현황 ===")
    async with async_session() as session:
        snap_count = (await session.execute(select(func.count(AdSnapshot.id)))).scalar()
        ad_count = (await session.execute(select(func.count(AdDetail.id)))).scalar()
        print(f"  총 스냅샷: {snap_count}개")
        print(f"  총 광고 상세: {ad_count}건")

    print("\n=== 전체 플로우 테스트 완료 ===")


if __name__ == "__main__":
    asyncio.run(test_full_flow())
