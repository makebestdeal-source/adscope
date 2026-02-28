"""추가 업종 크롤링 스크립트 — 미수집 키워드들을 한번에 크롤링+적재."""

import asyncio
import os
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://adscope:adscope@localhost:5433/adscope"

from sqlalchemy import func, select
from loguru import logger

from crawler.naver_search import NaverSearchCrawler
from database import async_session, init_db
from database.models import AdDetail, AdSnapshot, Advertiser, Industry, Keyword
from processor.pipeline import save_crawl_results
from processor.advertiser_matcher import AdvertiserMatcher
from processor.korean_filter import clean_advertiser_name


# 크롤링 대상 업종 ID 목록 (전체 10개 중 원하는 것만 선택)
# 1=금융, 2=의료/뷰티, 3=교육, 4=부동산, 5=법률
# 6=쇼핑/커머스, 7=IT/테크, 8=여행, 9=음식/외식, 10=자동차
TARGET_INDUSTRIES = [3, 4, 5, 7, 8, 9, 10]  # 금융(1)/의료(2) 제외 (이미 수집됨)


async def get_uncrawled_keywords(session, industry_ids: list[int]) -> list[tuple[str, str]]:
    """아직 크롤링되지 않은 키워드 목록 반환. Returns: [(keyword, industry_name), ...]"""
    # 이미 크롤링된 키워드 ID 조회
    crawled_kw_ids = await session.execute(
        select(AdSnapshot.keyword_id).distinct()
    )
    crawled_ids = {row[0] for row in crawled_kw_ids}

    # 대상 업종의 키워드 중 미수집 건 조회
    result = await session.execute(
        select(Keyword, Industry.name)
        .join(Industry, Keyword.industry_id == Industry.id)
        .where(Keyword.industry_id.in_(industry_ids))
        .where(Keyword.is_active == True)
        .order_by(Keyword.industry_id, Keyword.id)
    )

    uncrawled = []
    for kw, ind_name in result:
        if kw.id not in crawled_ids:
            uncrawled.append((kw.keyword, ind_name))

    return uncrawled


async def run_crawling():
    await init_db()

    async with async_session() as session:
        uncrawled = await get_uncrawled_keywords(session, TARGET_INDUSTRIES)

    if not uncrawled:
        print("모든 대상 키워드가 이미 수집되었습니다.")
        return

    # 업종별 그룹핑
    by_industry: dict[str, list[str]] = {}
    for kw, ind_name in uncrawled:
        by_industry.setdefault(ind_name, []).append(kw)

    print("=" * 60)
    print(f"  미수집 키워드: 총 {len(uncrawled)}개")
    for ind, kws in by_industry.items():
        print(f"    {ind}: {', '.join(kws)}")
    print("=" * 60)

    # 크롤링 실행
    all_results = []
    keywords = [kw for kw, _ in uncrawled]

    print(f"\n[1/3] 크롤링 시작 (PC, P4 페르소나)...")
    async with NaverSearchCrawler() as crawler:
        results = await crawler.crawl_keywords(
            keywords=keywords,
            persona_code="P4",
            device_type="pc",
        )
    all_results.extend(results)

    success = [r for r in results if not r.get("error")]
    total_ads = sum(len(r.get("ads", [])) for r in success)
    print(f"  PC 크롤링 완료: {len(success)}/{len(keywords)} 키워드, 광고 {total_ads}건")

    # DB 적재
    print(f"\n[2/3] DB 적재 중...")
    async with async_session() as session:
        saved = await save_crawl_results(session, all_results)
        print(f"  스냅샷 {saved}개 적재 완료")

    # 광고주 매칭
    print(f"\n[3/3] 광고주 매칭...")
    async with async_session() as session:
        # 기존 광고주 로드
        adv_result = await session.execute(select(Advertiser))
        existing = [
            {"id": a.id, "name": a.name, "aliases": a.aliases or []}
            for a in adv_result.scalars()
        ]

        # 새 광고주 자동 등록 (미매칭 광고주명)
        unmatched_names = await session.execute(
            select(AdDetail.advertiser_name_raw)
            .where(AdDetail.advertiser_id.is_(None))
            .where(AdDetail.advertiser_name_raw.isnot(None))
            .distinct()
        )
        new_count = 0
        for (raw_name,) in unmatched_names:
            name = raw_name.strip()
            if not name:
                continue
            # 외국어/가비지 이름 필터링
            name = clean_advertiser_name(name)
            if not name:
                continue
            # 이미 등록된 이름인지 확인
            exists = await session.execute(
                select(Advertiser).where(Advertiser.name == name)
            )
            if exists.scalar_one_or_none():
                continue
            session.add(Advertiser(name=name))
            new_count += 1

        if new_count > 0:
            await session.commit()
            print(f"  새 광고주 {new_count}명 자동 등록")

    # 최종 통계
    print(f"\n{'=' * 60}")
    print("  크롤링 완료 요약")
    print(f"{'=' * 60}")
    async with async_session() as session:
        snap_count = (await session.execute(select(func.count(AdSnapshot.id)))).scalar()
        ad_count = (await session.execute(select(func.count(AdDetail.id)))).scalar()
        adv_count = (await session.execute(select(func.count(Advertiser.id)))).scalar()

        print(f"  총 스냅샷: {snap_count}개")
        print(f"  총 광고 상세: {ad_count}개")
        print(f"  총 광고주: {adv_count}명")

        # 업종별 스냅샷 수
        result = await session.execute(
            select(Industry.name, func.count(AdSnapshot.id))
            .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
            .join(Industry, Keyword.industry_id == Industry.id)
            .group_by(Industry.name)
            .order_by(func.count(AdSnapshot.id).desc())
        )
        print(f"\n  업종별 스냅샷:")
        for ind_name, count in result:
            print(f"    {ind_name}: {count}개")


if __name__ == "__main__":
    asyncio.run(run_crawling())
