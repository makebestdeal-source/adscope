"""광고주 업종(industry_id) → 기본 제품 카테고리 자동 매핑."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from database import async_session
from database.models import AdDetail, Advertiser, ProductCategory

# industry_id → default product_category_id 매핑
# 각 업종의 첫 번째 소분류를 기본값으로 사용
INDUSTRY_TO_PRODUCT_CATEGORY = {
    10: "공기청정기",  # 가전/전자
    5: "커피",  # 식품/음료
    6: "스킨케어",  # 뷰티/화장품
    3: "승용차",  # 자동차
    16: "캠핑",  # 스포츠/아웃도어
    8: "종합몰",  # 유통/쇼핑
    9: "영양제",  # 건강/의료
}

async def map_product_categories():
    async with async_session() as session:
        # 모든 AdDetail 조회
        result = await session.execute(select(AdDetail))
        details = result.scalars().all()

        # ProductCategory 이름 → id 매핑
        cat_result = await session.execute(select(ProductCategory))
        categories = cat_result.scalars().all()
        cat_map = {cat.name: cat.id for cat in categories}

        updated = 0
        for detail in details:
            if detail.product_category_id is not None:
                continue  # 이미 설정됨

            # 광고주의 industry_id 조회
            if not detail.advertiser_id:
                continue

            adv_result = await session.execute(
                select(Advertiser).where(Advertiser.id == detail.advertiser_id)
            )
            advertiser = adv_result.scalar_one_or_none()
            if not advertiser or not advertiser.industry_id:
                continue

            # industry → product_category 매핑
            cat_name = INDUSTRY_TO_PRODUCT_CATEGORY.get(advertiser.industry_id)
            if cat_name and cat_name in cat_map:
                detail.product_category_id = cat_map[cat_name]
                detail.product_category = cat_name
                updated += 1

        await session.commit()
        print(f"Updated {updated} ad_details with product_category")

if __name__ == "__main__":
    asyncio.run(map_product_categories())
