"""Seed product_categories table with hierarchical category data.

Usage:
    python -m scripts.seed_product_categories
"""

import asyncio
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from database import async_session, init_db
from database.models import ProductCategory, Industry
from sqlalchemy import select


# 대분류 -> 소분류 매핑
CATEGORY_TREE: dict[str, list[str]] = {
    "가전/전자": ["TV", "냉장고", "세탁기", "에어컨", "헤어드라이어", "공기청정기", "로봇청소기"],
    "모바일/IT": ["스마트폰", "태블릿", "노트북", "이어폰/헤드폰", "스마트워치"],
    "뷰티/화장품": ["스킨케어", "메이크업", "향수", "헤어케어", "남성화장품"],
    "패션": ["의류", "신발", "가방", "액세서리", "스포츠웨어"],
    "식품/음료": ["간편식", "건강식품", "음료", "커피", "주류"],
    "금융서비스": ["대출", "보험", "카드", "투자", "저축"],
    "자동차": ["승용차", "SUV", "전기차", "중고차", "수입차"],
    "여행/레저": ["항공권", "호텔", "패키지여행", "렌터카", "레저/체험"],
    "교육": ["어학", "자격증", "온라인강의", "학원", "코딩교육"],
    "생활서비스": ["배달", "이사", "청소", "인테리어", "수리"],
    "엔터테인먼트": ["영화", "OTT", "음악", "게임", "공연"],
    "건강/의료": ["병원", "약국", "건강검진", "다이어트", "영양제"],
    "부동산": ["아파트분양", "오피스텔", "전월세", "상가", "토지"],
    "유통/쇼핑": ["종합몰", "전문몰", "중고거래", "직구", "오프라인매장"],
}

# 대분류 -> 업종(Industry) 매핑 (있을 경우)
CATEGORY_TO_INDUSTRY: dict[str, str] = {
    "가전/전자": "가전/전자",
    "모바일/IT": "IT/테크",
    "뷰티/화장품": "뷰티/화장품",
    "패션": "패션/의류",
    "식품/음료": "식품/음료",
    "금융서비스": "금융/보험",
    "자동차": "자동차",
    "여행/레저": "여행/항공",
    "교육": "교육",
    "생활서비스": "생활용품",
    "엔터테인먼트": "엔터테인먼트",
    "건강/의료": "건강/의료",
    "부동산": "부동산",
    "유통/쇼핑": "유통/이커머스",
}


async def seed():
    await init_db()

    async with async_session() as session:
        # 기존 카테고리 확인
        existing = await session.execute(select(ProductCategory))
        if existing.scalars().first():
            print("[seed_product_categories] already seeded, skipping")
            return

        # Industry 매핑 로드
        ind_rows = await session.execute(select(Industry))
        industry_map = {ind.name: ind.id for ind in ind_rows.scalars().all()}

        created = 0
        for parent_name, children in CATEGORY_TREE.items():
            ind_name = CATEGORY_TO_INDUSTRY.get(parent_name)
            ind_id = industry_map.get(ind_name) if ind_name else None

            parent = ProductCategory(
                name=parent_name,
                parent_id=None,
                industry_id=ind_id,
            )
            session.add(parent)
            await session.flush()
            created += 1

            for child_name in children:
                child = ProductCategory(
                    name=child_name,
                    parent_id=parent.id,
                    industry_id=ind_id,
                )
                session.add(child)
                created += 1

        await session.commit()
        print(f"[seed_product_categories] created {created} categories")


if __name__ == "__main__":
    asyncio.run(seed())
