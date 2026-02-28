"""Advertiser profile (background data) seeding script.

Populates existing advertisers with corporate profile data:
annual_revenue, employee_count, founded_year, headquarters, etc.

Usage:
  python scripts/seed_advertiser_profiles.py [--dry-run]
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger
from sqlalchemy import func, select

# Add project root to PATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import async_session, init_db
from database.models import Advertiser


# Major Korean advertiser profiles with background data
# Revenue / market_cap in KRW (won)
PROFILES: list[dict] = [
    # IT/Tech
    {
        "name": "삼성전자",
        "annual_revenue": 258_935_500_000_000,
        "employee_count": 267800,
        "founded_year": 1969,
        "headquarters": "경기도 수원시",
        "is_public": True,
        "market_cap": 390_000_000_000_000,
        "business_category": "C261",
        "description": "반도체, 스마트폰, 가전 등 글로벌 IT 기업",
    },
    {
        "name": "LG전자",
        "annual_revenue": 84_227_500_000_000,
        "employee_count": 39000,
        "founded_year": 1958,
        "headquarters": "서울 영등포구",
        "is_public": True,
        "market_cap": 18_000_000_000_000,
        "business_category": "C261",
        "description": "가전, TV, 생활가전 글로벌 기업",
    },
    {
        "name": "SK텔레콤",
        "annual_revenue": 17_742_000_000_000,
        "employee_count": 5500,
        "founded_year": 1984,
        "headquarters": "서울 중구",
        "is_public": True,
        "market_cap": 12_000_000_000_000,
        "business_category": "J612",
        "description": "국내 최대 이동통신사, AI/반도체 사업 확대",
    },
    {
        "name": "KT",
        "annual_revenue": 26_381_000_000_000,
        "employee_count": 23000,
        "founded_year": 1981,
        "headquarters": "서울 종로구",
        "is_public": True,
        "market_cap": 9_000_000_000_000,
        "business_category": "J612",
        "description": "유무선 통신, IPTV, 클라우드 사업자",
    },
    {
        "name": "LG유플러스",
        "annual_revenue": 14_037_000_000_000,
        "employee_count": 10500,
        "founded_year": 1996,
        "headquarters": "서울 용산구",
        "is_public": True,
        "market_cap": 5_000_000_000_000,
        "business_category": "J612",
        "description": "이동통신 3사, 5G 및 콘텐츠 사업",
    },
    {
        "name": "카카오",
        "annual_revenue": 7_107_000_000_000,
        "employee_count": 4500,
        "founded_year": 2010,
        "headquarters": "경기도 성남시",
        "is_public": True,
        "market_cap": 22_000_000_000_000,
        "business_category": "J582",
        "description": "카카오톡 기반 플랫폼, 핀테크, 모빌리티, 엔터테인먼트",
    },
    {
        "name": "네이버",
        "annual_revenue": 9_605_000_000_000,
        "employee_count": 4200,
        "founded_year": 1999,
        "headquarters": "경기도 성남시",
        "is_public": True,
        "market_cap": 47_000_000_000_000,
        "business_category": "J631",
        "description": "국내 최대 검색/포털, AI, 커머스, 클라우드",
    },
    {
        "name": "쿠팡",
        "annual_revenue": 31_847_000_000_000,
        "employee_count": 70000,
        "founded_year": 2010,
        "headquarters": "서울 송파구",
        "is_public": True,
        "market_cap": 45_000_000_000_000,
        "business_category": "G479",
        "description": "로켓배송 기반 이커머스, OTT 서비스(쿠팡플레이)",
    },
    {
        "name": "배달의민족",
        "annual_revenue": 3_200_000_000_000,
        "employee_count": 5000,
        "founded_year": 2010,
        "headquarters": "서울 송파구",
        "is_public": False,
        "description": "국내 1위 배달 플랫폼 (우아한형제들)",
    },
    # Automotive
    {
        "name": "현대자동차",
        "annual_revenue": 162_664_000_000_000,
        "employee_count": 75000,
        "founded_year": 1967,
        "headquarters": "서울 서초구",
        "is_public": True,
        "market_cap": 55_000_000_000_000,
        "business_category": "C303",
        "description": "국내 최대 자동차 제조사, 전기차/수소차 선도",
    },
    {
        "name": "기아",
        "annual_revenue": 98_799_000_000_000,
        "employee_count": 52000,
        "founded_year": 1944,
        "headquarters": "서울 서초구",
        "is_public": True,
        "market_cap": 38_000_000_000_000,
        "business_category": "C303",
        "description": "현대차그룹 계열 글로벌 자동차 제조사",
    },
    {
        "name": "제네시스",
        "annual_revenue": 12_000_000_000_000,
        "employee_count": 3000,
        "founded_year": 2015,
        "headquarters": "서울 서초구",
        "is_public": False,
        "business_category": "C303",
        "description": "현대차그룹 프리미엄 자동차 브랜드",
    },
    # Finance
    {
        "name": "삼성카드",
        "annual_revenue": 5_400_000_000_000,
        "employee_count": 4500,
        "founded_year": 1988,
        "headquarters": "서울 중구",
        "is_public": True,
        "market_cap": 4_500_000_000_000,
        "business_category": "K649",
        "description": "삼성그룹 계열 신용카드사",
    },
    {
        "name": "KB국민카드",
        "annual_revenue": 5_100_000_000_000,
        "employee_count": 3800,
        "founded_year": 1980,
        "headquarters": "서울 종로구",
        "is_public": False,
        "business_category": "K649",
        "description": "KB금융그룹 신용카드사",
    },
    {
        "name": "신한카드",
        "annual_revenue": 6_200_000_000_000,
        "employee_count": 4100,
        "founded_year": 1986,
        "headquarters": "서울 중구",
        "is_public": False,
        "business_category": "K649",
        "description": "신한금융그룹 카드사, 업계 점유율 1위",
    },
    {
        "name": "현대카드",
        "annual_revenue": 4_800_000_000_000,
        "employee_count": 3200,
        "founded_year": 1995,
        "headquarters": "서울 영등포구",
        "is_public": False,
        "business_category": "K649",
        "description": "현대차그룹 카드사, 디자인/마케팅 혁신",
    },
    {
        "name": "토스",
        "annual_revenue": 1_700_000_000_000,
        "employee_count": 3000,
        "founded_year": 2013,
        "headquarters": "서울 강남구",
        "is_public": False,
        "business_category": "K642",
        "description": "비바리퍼블리카, 모바일 핀테크 슈퍼앱",
    },
    {
        "name": "카카오뱅크",
        "annual_revenue": 1_500_000_000_000,
        "employee_count": 2000,
        "founded_year": 2016,
        "headquarters": "경기도 성남시",
        "is_public": True,
        "market_cap": 8_000_000_000_000,
        "business_category": "K641",
        "description": "국내 1위 인터넷전문은행",
    },
    # Shopping / Commerce
    {
        "name": "SSG닷컴",
        "annual_revenue": 2_100_000_000_000,
        "employee_count": 2500,
        "founded_year": 2014,
        "headquarters": "서울 강남구",
        "is_public": False,
        "business_category": "G479",
        "description": "신세계그룹 온라인 커머스 플랫폼",
    },
    {
        "name": "무신사",
        "annual_revenue": 7_000_000_000_000,
        "employee_count": 2500,
        "founded_year": 2001,
        "headquarters": "서울 성동구",
        "is_public": False,
        "business_category": "G479",
        "description": "국내 최대 패션 이커머스 플랫폼",
    },
    {
        "name": "올리브영",
        "annual_revenue": 4_200_000_000_000,
        "employee_count": 8000,
        "founded_year": 1999,
        "headquarters": "서울 중구",
        "is_public": False,
        "business_category": "G471",
        "description": "CJ그룹 H&B(헬스앤뷰티) 매장/온라인 플랫폼",
    },
    # Food & Beverage
    {
        "name": "CJ제일제당",
        "annual_revenue": 29_780_000_000_000,
        "employee_count": 26000,
        "founded_year": 1953,
        "headquarters": "서울 중구",
        "is_public": True,
        "market_cap": 7_500_000_000_000,
        "business_category": "C107",
        "description": "식품, 바이오 글로벌 기업 (비비고 등)",
    },
    {
        "name": "농심",
        "annual_revenue": 3_480_000_000_000,
        "employee_count": 5200,
        "founded_year": 1965,
        "headquarters": "서울 동작구",
        "is_public": True,
        "market_cap": 2_500_000_000_000,
        "business_category": "C107",
        "description": "라면/스낵 제조 (신라면, 새우깡 등)",
    },
    {
        "name": "오뚜기",
        "annual_revenue": 3_200_000_000_000,
        "employee_count": 4800,
        "founded_year": 1969,
        "headquarters": "서울 강남구",
        "is_public": True,
        "market_cap": 2_800_000_000_000,
        "business_category": "C107",
        "description": "라면, 카레, 케첩 등 종합식품 기업",
    },
    # Beauty / Fashion
    {
        "name": "아모레퍼시픽",
        "annual_revenue": 4_500_000_000_000,
        "employee_count": 11000,
        "founded_year": 1945,
        "headquarters": "서울 용산구",
        "is_public": True,
        "market_cap": 6_000_000_000_000,
        "business_category": "C204",
        "description": "설화수, 라네즈 등 글로벌 뷰티 기업",
    },
    {
        "name": "LG생활건강",
        "annual_revenue": 6_800_000_000_000,
        "employee_count": 10000,
        "founded_year": 2001,
        "headquarters": "서울 종로구",
        "is_public": True,
        "market_cap": 9_000_000_000_000,
        "business_category": "C204",
        "description": "후, 숨, 오휘 등 럭셔리 뷰티 + 생활용품",
    },
    # Travel
    {
        "name": "야놀자",
        "annual_revenue": 800_000_000_000,
        "employee_count": 3000,
        "founded_year": 2005,
        "headquarters": "서울 강남구",
        "is_public": False,
        "business_category": "N791",
        "description": "국내 최대 숙박/레저 플랫폼",
    },
    {
        "name": "하나투어",
        "annual_revenue": 1_200_000_000_000,
        "employee_count": 2500,
        "founded_year": 1993,
        "headquarters": "서울 종로구",
        "is_public": True,
        "market_cap": 1_500_000_000_000,
        "business_category": "N791",
        "description": "국내 최대 여행사",
    },
    # Entertainment
    {
        "name": "넷플릭스코리아",
        "annual_revenue": 900_000_000_000,
        "employee_count": 500,
        "founded_year": 2016,
        "headquarters": "서울 강남구",
        "is_public": False,
        "business_category": "J591",
        "description": "글로벌 OTT 서비스 한국법인",
    },
    {
        "name": "티빙",
        "annual_revenue": 400_000_000_000,
        "employee_count": 800,
        "founded_year": 2020,
        "headquarters": "서울 마포구",
        "is_public": False,
        "business_category": "J591",
        "description": "CJ ENM OTT 플랫폼",
    },
    # Insurance
    {
        "name": "삼성생명",
        "annual_revenue": 27_000_000_000_000,
        "employee_count": 6500,
        "founded_year": 1957,
        "headquarters": "서울 서초구",
        "is_public": True,
        "market_cap": 15_000_000_000_000,
        "business_category": "K651",
        "description": "국내 최대 생명보험사",
    },
    {
        "name": "한화생명",
        "annual_revenue": 18_500_000_000_000,
        "employee_count": 5000,
        "founded_year": 1946,
        "headquarters": "서울 영등포구",
        "is_public": True,
        "market_cap": 4_000_000_000_000,
        "business_category": "K651",
        "description": "한화그룹 생명보험사",
    },
]


async def seed_profiles(dry_run: bool = False):
    """Update existing advertisers with corporate profile data."""
    await init_db()

    async with async_session() as session:
        # Build name -> advertiser map (case-insensitive)
        result = await session.execute(select(Advertiser))
        adv_map: dict[str, Advertiser] = {}
        for adv in result.scalars().all():
            adv_map[adv.name.lower()] = adv

        updated = 0
        skipped = 0

        for profile in PROFILES:
            name = profile["name"]
            key = name.lower()

            if key not in adv_map:
                skipped += 1
                if dry_run:
                    logger.info(f"[DRY-RUN] SKIP: '{name}' not found in DB")
                continue

            adv = adv_map[key]
            changed = False

            for field in (
                "annual_revenue",
                "employee_count",
                "founded_year",
                "headquarters",
                "is_public",
                "market_cap",
                "business_category",
                "description",
            ):
                value = profile.get(field)
                if value is not None:
                    current = getattr(adv, field, None)
                    if current != value:
                        if not dry_run:
                            setattr(adv, field, value)
                        changed = True

            if changed:
                if not dry_run:
                    adv.data_source = "seed"
                    adv.profile_updated_at = datetime.utcnow()
                updated += 1
                if dry_run:
                    logger.info(f"[DRY-RUN] UPDATE: {name}")
            else:
                skipped += 1

        if not dry_run:
            await session.commit()

        logger.info(
            f"Profile seeding complete: {updated} updated, {skipped} skipped"
            + (" (DRY-RUN)" if dry_run else "")
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed advertiser profile background data"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to DB",
    )
    args = parser.parse_args()

    asyncio.run(seed_profiles(dry_run=args.dry_run))
