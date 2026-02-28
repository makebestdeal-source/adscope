"""광고주 자동 등록 + 퍼지 매칭 테스트."""

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

from database import async_session, init_db
from database.models import AdDetail, Advertiser
from processor.advertiser_matcher import AdvertiserMatcher


async def test_advertiser_matching():
    """크롤링된 광고주명을 DB에 등록하고 퍼지 매칭 테스트."""
    await init_db()

    # 1) 기존 광고 상세에서 광고주명 추출
    print("=== [1/3] 크롤링된 광고주명 수집 ===")
    async with async_session() as session:
        result = await session.execute(
            select(AdDetail.advertiser_name_raw)
            .where(AdDetail.advertiser_name_raw.isnot(None))
            .distinct()
        )
        raw_names = [r[0] for r in result.all()]
        print(f"  고유 광고주명: {len(raw_names)}개")
        for name in sorted(raw_names):
            print(f"    - {name}")

    # 2) 광고주 DB 자동 등록
    print(f"\n=== [2/3] 광고주 DB 등록 ===")
    async with async_session() as session:
        registered = 0
        for name in raw_names:
            if not name or len(name) < 2:
                continue
            # 이미 존재하는지 확인
            exists = await session.execute(
                select(Advertiser).where(Advertiser.name == name)
            )
            if exists.scalar_one_or_none():
                continue
            adv = Advertiser(
                name=name,
                aliases=[],
                industry_id=None,
            )
            session.add(adv)
            registered += 1
        await session.commit()
        print(f"  신규 등록: {registered}명")

    # 3) 퍼지 매칭 테스트
    print(f"\n=== [3/3] 퍼지 매칭 테스트 ===")
    matcher = AdvertiserMatcher()

    async with async_session() as session:
        adv_result = await session.execute(select(Advertiser))
        existing = [
            {"id": a.id, "name": a.name, "aliases": a.aliases}
            for a in adv_result.scalars()
        ]
        matcher.load_advertisers(existing)
        print(f"  등록된 광고주: {len(existing)}명")

        # 유사한 이름으로 매칭 테스트
        test_names = [
            "동화저축은행",      # 정확 매칭
            "동화 저축은행",     # 띄어쓰기 차이
            "동화저축",          # 축약
            "SBI저축은행",       # 정확
            "sbi저축은행",       # 대소문자
            "네이버 파이낸셜",   # 정확
            "네이버파이낸셜",    # 띄어쓰기 제거
            "삼성화재",          # 부분 매칭
            "알 수 없는 광고주", # 매칭 불가
        ]

        print(f"\n  테스트 매칭 결과:")
        for name in test_names:
            adv_id, score = matcher.match(name)
            if adv_id:
                matched_name = next(a["name"] for a in existing if a["id"] == adv_id)
                print(f"    '{name}' → '{matched_name}' (ID={adv_id}, 유사도 {score:.0f}%)")
            else:
                print(f"    '{name}' → 매칭 실패")

    print("\n=== 광고주 매칭 테스트 완료 ===")


if __name__ == "__main__":
    asyncio.run(test_advertiser_matching())
