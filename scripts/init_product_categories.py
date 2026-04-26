"""Initialize ProductCategory with 20+ standard product categories."""
import asyncio
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)

from database import async_session
from database.models import ProductCategory, Industry

# 대분류 → 중분류 맵
PRODUCT_CATEGORIES = {
    "모바일/IT": [
        "스마트폰",
        "태블릿",
        "노트북",
        "데스크톱",
        "스마트워치",
    ],
    "가전/전자": [
        "냉장고",
        "세탁기",
        "에어컨",
        "공기청정기",
        "청소기",
        "조리기구",
    ],
    "식품/음료": [
        "커피",
        "간식",
        "음료",
        "영양제",
        "건강음료",
        "유제품",
    ],
    "패션": [
        "의류",
        "신발",
        "가방",
        "액세서리",
        "시계",
    ],
    "뷰티/화장품": [
        "스킨케어",
        "메이크업",
        "헤어케어",
        "향수",
        "남성미용",
    ],
    "금융서비스": [
        "카드",
        "보험",
        "투자",
        "대출",
        "송금",
    ],
    "자동차": [
        "승용차",
        "SUV",
        "전기차",
        "부품",
        "렌터카",
    ],
    "여행/레저": [
        "항공권",
        "호텔",
        "투어",
        "액티비티",
        "캠핑",
    ],
    "교육": [
        "온라인강좌",
        "학원",
        "교재",
        "어학",
        "자격증",
    ],
    "생활서비스": [
        "배달",
        "숙박",
        "이사",
        "청소",
        "정비",
    ],
}


async def init_product_categories():
    """Initialize product categories."""
    async with async_session() as session:
        for category_name, subcategories in PRODUCT_CATEGORIES.items():
            # 대분류 생성
            parent = ProductCategory(name=category_name)
            session.add(parent)
            await session.flush()  # ID 할당 받기

            # 중분류 생성
            for sub_name in subcategories:
                child = ProductCategory(
                    name=sub_name,
                    parent_id=parent.id,
                )
                session.add(child)

        await session.commit()
        print(f"Created {len(PRODUCT_CATEGORIES)} parent categories")
        print(f"Created {sum(len(v) for v in PRODUCT_CATEGORIES.values())} subcategories")


if __name__ == "__main__":
    asyncio.run(init_product_categories())
