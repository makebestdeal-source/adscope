"""빠른 업종 분류 - 광고주명 키워드 기반."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import async_session
from database.models import Advertiser, Industry

# 키워드 → industry_id 매핑
KEYWORD_RULES = {
    # 가전/전자 (10)
    "가전": 10, "전자": 10, "LG": 10, "삼성": 10,
    "냉장고": 10, "세탁기": 10, "에어컨": 10, "청소기": 10,
    "조명": 10, "다이슨": 10, "TV": 10, "노트북": 10,
    # 모바일/IT → IT/통신 (2)
    "앱": 2, "플랫폼": 2, "소프트웨어": 2, "SaaS": 2, "솔루션": 2,
    "IT": 2, "클라우드": 2, "ERP": 2, "CRM": 2,
    # 통신 → IT/통신 (2)
    "통신": 2, "인터넷": 2, "IPTV": 2, "알뜰폰": 2,
    # 스포츠/아웃도어 (16)
    "스포츠": 16, "피트니스": 16, "헬스": 16,
    # 식품/음료 (5)
    "커피": 5, "음료": 5, "음식": 5, "식품": 5, "베이커리": 5,
    "배달": 5, "푸드": 5, "치킨": 5, "피자": 5,
    # 주류 (18)
    "주류": 18, "맥주": 18, "와인": 18, "소주": 18,
    # 뷰티/화장품 (6)
    "뷰티": 6, "화장품": 6, "스킨케어": 6, "헤어": 6, "향수": 6,
    "에스더": 6,
    # 패션/의류 (7)
    "패션": 7, "의류": 7, "신발": 7, "가방": 7,
    # 유통/이커머스 (8)
    "몰": 8, "마켓": 8, "쇼핑": 8, "이커머스": 8, "오픈마켓": 8,
    # 제약/헬스케어 (9)
    "건강": 9, "의약": 9, "영양제": 9, "병원": 9, "의료": 9, "제약": 9,
    # 자동차 (3)
    "렌터카": 3, "자동차": 3, "자동차": 3, "중고차": 3,
    # 건설/부동산 (11)
    "부동산": 11, "분양": 11, "아파트": 11, "건설": 11, "인테리어": 11,
    # 게임 (12)
    "게임": 12,
    # 엔터테인먼트 (13)
    "엔터": 13, "OTT": 13, "영화": 13, "음악": 13, "웹툰": 13,
    # 여행/항공 (14)
    "여행": 14, "항공": 14, "호텔": 14, "숙박": 14,
    # 교육 (15)
    "교육": 15, "학원": 15, "어학": 15, "에듀": 15,
    # 가구/인테리어 (17)
    "가구": 17, "홈": 17,
    # 반려동물 (20)
    "펫": 20, "반려": 20,
    # 생활용품 (21)
    "생활": 21, "세제": 21,
    # 금융/보험 (4)
    "금융": 4, "보험": 4, "은행": 4, "증권": 4, "카드": 4, "대출": 4, "투자": 4,
    # 핀테크 → 금융/보험 (4)
    "핀테크": 4, "페이": 4,
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
