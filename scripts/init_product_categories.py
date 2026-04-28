"""Initialize/update ProductCategory with comprehensive categories matching AI enricher."""
import asyncio
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from database import async_session, init_db
from database.models import ProductCategory
from sqlalchemy import select

# AI enricher 프롬프트와 정확히 일치하는 대분류 → 소분류 맵
# (ai_enricher.py SYSTEM_PROMPT의 카테고리명과 동일하게 유지)
PRODUCT_CATEGORIES: dict[str, list[str]] = {
    "가전/전자": [
        "TV", "냉장고", "세탁기", "에어컨", "헤어드라이어",
        "공기청정기", "로봇청소기", "조리기구", "오디오",
    ],
    "모바일/IT": [
        "스마트폰", "태블릿", "노트북", "데스크톱",
        "이어폰/헤드폰", "스마트워치", "주변기기",
    ],
    "소프트웨어/SaaS": [
        "업무툴", "클라우드", "보안솔루션", "ERP", "CRM",
        "디자인툴", "협업툴", "AI서비스",
    ],
    "게임": [
        "모바일게임", "PC게임", "콘솔게임", "게임플랫폼", "e스포츠",
    ],
    "뷰티/화장품": [
        "스킨케어", "메이크업", "향수", "헤어케어", "남성화장품",
        "바디케어", "더마/의약외품",
    ],
    "패션": [
        "의류", "신발", "가방", "액세서리", "스포츠웨어",
        "시계", "주얼리",
    ],
    "식품/음료": [
        "간편식", "건강식품", "음료", "커피", "주류",
        "유제품", "간식/베이커리", "신선식품",
    ],
    "금융서비스": [
        "카드", "보험", "투자", "대출", "저축",
        "핀테크", "암호화폐",
    ],
    "자동차": [
        "승용차", "SUV", "전기차", "중고차", "수입차",
        "렌터카", "부품/용품",
    ],
    "여행/레저": [
        "항공권", "호텔", "패키지여행", "렌터카", "레저/체험",
        "캠핑", "크루즈",
    ],
    "교육": [
        "어학", "자격증", "온라인강의", "학원", "코딩교육",
        "유아/초등교육", "입시/수능",
    ],
    "생활서비스": [
        "배달", "이사", "청소", "인테리어", "수리",
        "세탁", "정비",
    ],
    "앱서비스": [
        "배달앱", "커머스앱", "금융앱", "유틸리티앱", "SNS",
        "헬스앱", "데이팅앱",
    ],
    "엔터테인먼트": [
        "영화", "OTT", "음악", "공연", "웹툰",
        "방송/미디어", "스트리밍",
    ],
    "건강/의료": [
        "병원", "약국", "건강검진", "다이어트", "영양제",
        "의료기기", "피부과/성형",
    ],
    "부동산": [
        "아파트분양", "오피스텔", "전월세", "상가", "토지",
        "프롭테크", "부동산중개",
    ],
    "유통/쇼핑": [
        "종합몰", "전문몰", "중고거래", "직구", "오프라인매장",
        "홈쇼핑", "멤버십",
    ],
    "통신/인터넷": [
        "이동통신", "인터넷", "IPTV", "IoT", "알뜰폰",
        "B2B통신",
    ],
    "스포츠/아웃도어": [
        "운동용품", "아웃도어의류", "헬스/피트니스", "골프",
        "자전거", "등산/캠핑",
    ],
    "반려동물": [
        "반려동물식품", "반려동물용품", "동물병원", "펫보험",
    ],
    "공공/기관": [
        "정부기관", "공공서비스", "NGO/비영리", "지자체",
    ],
    "기타": [],
}


async def init_product_categories():
    """Get-or-create for all categories (idempotent)."""
    await init_db()

    created_parents = 0
    created_children = 0
    skipped = 0

    async with async_session() as session:
        for parent_name, children in PRODUCT_CATEGORIES.items():
            # 대분류 get-or-create
            result = await session.execute(
                select(ProductCategory).where(
                    ProductCategory.name == parent_name,
                    ProductCategory.parent_id.is_(None),
                )
            )
            parent = result.scalar_one_or_none()
            if parent is None:
                parent = ProductCategory(name=parent_name)
                session.add(parent)
                await session.flush()
                created_parents += 1
                print(f"  [NEW] 대분류: {parent_name} (id={parent.id})")
            else:
                skipped += 1

            for child_name in children:
                # 소분류 get-or-create
                child_result = await session.execute(
                    select(ProductCategory).where(
                        ProductCategory.name == child_name,
                        ProductCategory.parent_id == parent.id,
                    )
                )
                child = child_result.scalar_one_or_none()
                if child is None:
                    session.add(ProductCategory(name=child_name, parent_id=parent.id))
                    created_children += 1
                else:
                    skipped += 1

        await session.commit()

    print(f"\n완료: 대분류 +{created_parents}개, 소분류 +{created_children}개, 기존 {skipped}개 유지")


if __name__ == "__main__":
    asyncio.run(init_product_categories())
