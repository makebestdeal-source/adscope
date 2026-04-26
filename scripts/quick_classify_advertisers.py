"""빠른 업종 분류 - 광고주명 키워드 기반."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import async_session
from database.models import Advertiser, Industry

# 키워드 → industry_id 매핑
KEYWORD_RULES = {
    "가전": 10,  # 가전/전자
    "전자": 10,
    "LG": 10,
    "삼성": 10,
    "냉장고": 10,
    "세탁기": 10,
    "에어컨": 10,
    "청소기": 10,
    "조명": 10,
    "스포츠": 16,  # 스포츠/아웃도어
    "스포츠용": 16,
    "커피": 5,  # 식품/음료
    "음료": 5,
    "음식": 5,
    "식품": 5,
    "건강": 9,  # 제약/헬스케어
    "의약": 9,
    "영양제": 9,
    "다이슨": 10,  # 가전
    "에스더": 6,  # 뷰티/화장품 (몰 이름에서)
    "몰": 8,  # 유통/이커머스
    "마켓": 8,
    "쇼핑": 8,
    "렌터카": 3,  # 자동차
    "자동차": 3,
}

async def classify():
    async with async_session() as session:
        # 모든 광고주 조회
        from sqlalchemy import select
        result = await session.execute(select(Advertiser))
        advertisers = result.scalars().all()

        updated = 0
        for adv in advertisers:
            if adv.industry_id is not None:
                continue  # 이미 분류됨

            # 광고주명에서 키워드 찾기
            name_lower = (adv.name or "").lower()
            matched_industry = None

            for keyword, industry_id in KEYWORD_RULES.items():
                if keyword.lower() in name_lower:
                    matched_industry = industry_id
                    break

            # 기본값: 기타 (1)
            if matched_industry is None:
                matched_industry = 1

            adv.industry_id = matched_industry
            updated += 1

        await session.commit()
        print(f"Updated {updated} advertisers")

if __name__ == "__main__":
    asyncio.run(classify())
