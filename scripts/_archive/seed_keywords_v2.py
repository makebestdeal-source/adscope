"""
Keyword Scope v2: Insert industry-mapped commercial + shopping keywords.

DB Industry mapping (from actual DB):
  1  기타
  2  IT/통신
  3  자동차
  4  금융/보험
  5  식품/음료
  6  뷰티/화장품
  7  패션/의류
  8  유통/이커머스
  9  제약/헬스케어
  10 가전/전자
  11 건설/부동산
  12 게임
  13 엔터테인먼트
  14 여행/항공
  15 교육
  16 스포츠/아웃도어
  17 가구/인테리어
  18 주류
  19 공공기관
  20 반려동물
  21 생활용품        (new)
"""

import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from database import async_session, init_db
from database.models import Keyword, Industry


# ───────────────────────────────────────────────────
# Industry to add (if missing)
# ───────────────────────────────────────────────────
NEW_INDUSTRIES = [
    {"name": "생활용품", "avg_cpc_min": 400, "avg_cpc_max": 1500},
]

# ───────────────────────────────────────────────────
# Keyword scope per industry
#   - Core commercial keywords (5~8 per industry)
#   - Shopping long-tail keywords (3~5 per industry)
# ───────────────────────────────────────────────────
KEYWORD_SCOPE = {
    # ── 뷰티/화장품 (ID 6) ──
    "뷰티/화장품": {
        "core": [
            "화장품", "스킨케어", "메이크업", "기초화장품", "선크림",
            "클렌징", "마스크팩", "립스틱",
        ],
        "shopping": [
            "화장품 추천", "스킨케어 인기", "선크림 가성비",
            "기초화장품 세트", "메이크업 브랜드 추천",
        ],
    },
    # ── 패션/의류 (ID 7) ──
    "패션/의류": {
        "core": [
            "패션", "의류", "신발", "가방", "아우터",
            "원피스", "청바지", "스니커즈",
        ],
        "shopping": [
            "패션 추천", "의류 인기", "신발 가성비",
            "아우터 추천", "가방 브랜드 추천",
        ],
    },
    # ── 식품/음료 (ID 5) ──
    "식품/음료": {
        "core": [
            "건강식품", "다이어트식품", "간편식", "커피", "음료",
            "단백질보충제", "견과류", "차",
        ],
        "shopping": [
            "건강식품 추천", "간편식 인기", "커피 가성비",
            "다이어트식품 추천", "음료 인기순",
        ],
    },
    # ── 금융/보험 (ID 4) ──
    "금융/보험": {
        "core": [
            "대출", "보험", "카드", "적금", "투자",
            "신용대출", "실손보험", "주담대",
        ],
        "shopping": [
            "카드 추천", "적금 추천", "보험 가성비",
            "대출 금리비교", "투자 인기",
        ],
    },
    # ── IT/통신 (ID 2) ──
    "IT/통신": {
        "core": [
            "스마트폰", "노트북", "태블릿", "이어폰", "모니터",
            "키보드", "마우스", "웹캠",
        ],
        "shopping": [
            "스마트폰 추천", "노트북 가성비", "이어폰 인기",
            "태블릿 추천", "모니터 가성비",
        ],
    },
    # ── 자동차 (ID 3) ──
    "자동차": {
        "core": [
            "자동차", "SUV", "전기차", "중고차", "수입차",
            "하이브리드", "경차", "자동차보험",
        ],
        "shopping": [
            "자동차 추천", "전기차 가성비", "중고차 인기",
            "SUV 추천", "수입차 가성비",
        ],
    },
    # ── 여행/항공 (ID 14) ──
    "여행/항공": {
        "core": [
            "항공권", "호텔", "여행", "해외여행", "국내여행",
            "렌터카", "패키지여행", "리조트",
        ],
        "shopping": [
            "항공권 가성비", "호텔 추천", "여행 인기",
            "국내여행 추천", "해외여행 가성비",
        ],
    },
    # ── 교육 (ID 15) ──
    "교육": {
        "core": [
            "영어", "학원", "자격증", "인강", "코딩",
            "토익", "수능", "과외",
        ],
        "shopping": [
            "인강 추천", "학원 인기", "자격증 가성비",
            "영어 추천", "코딩 인강 추천",
        ],
    },
    # ── 게임 (ID 12) ──
    "게임": {
        "core": [
            "모바일게임", "PC게임", "RPG", "신작게임",
            "게이밍마우스", "게이밍키보드", "게임패드",
        ],
        "shopping": [
            "모바일게임 추천", "PC게임 인기", "신작게임 추천",
            "게이밍마우스 가성비",
        ],
    },
    # ── 제약/헬스케어 (ID 9) ── (건강/의료)
    "제약/헬스케어": {
        "core": [
            "병원", "약국", "건강검진", "치과", "피부과",
            "비타민", "유산균", "영양제",
        ],
        "shopping": [
            "비타민 추천", "유산균 인기", "영양제 가성비",
            "건강검진 추천", "치과 추천",
        ],
    },
    # ── 유통/이커머스 (ID 8) ──
    "유통/이커머스": {
        "core": [
            "할인", "세일", "쿠폰", "최저가", "직구",
            "특가", "타임세일", "무료배송",
        ],
        "shopping": [
            "쿠폰 추천", "최저가 인기", "직구 가성비",
            "할인 추천", "세일 인기순",
        ],
    },
    # ── 생활용품 (ID 21, new) ──
    "생활용품": {
        "core": [
            "생활용품", "세제", "청소", "주방", "욕실",
            "수건", "정리함", "휴지",
        ],
        "shopping": [
            "생활용품 추천", "세제 가성비", "청소 인기",
            "주방용품 추천", "욕실용품 가성비",
        ],
    },
    # ── 건설/부동산 (ID 11) ──
    "건설/부동산": {
        "core": [
            "아파트", "분양", "오피스텔", "전세", "월세",
            "재건축", "신축아파트", "상가",
        ],
        "shopping": [
            "아파트 분양 추천", "오피스텔 인기", "전세 추천",
            "분양 가성비",
        ],
    },
    # ── 엔터테인먼트 (ID 13) ──
    "엔터테인먼트": {
        "core": [
            "영화", "드라마", "공연", "음악", "콘서트",
            "OTT", "뮤지컬", "웹툰",
        ],
        "shopping": [
            "OTT 추천", "공연 인기", "콘서트 추천",
            "영화 추천", "웹툰 인기",
        ],
    },
    # ── 가전/전자 (ID 10) ── (추가 보강)
    "가전/전자": {
        "core": [
            "에어컨", "냉장고", "세탁기", "건조기", "공기청정기",
            "로봇청소기", "TV", "식기세척기",
        ],
        "shopping": [
            "에어컨 추천", "냉장고 가성비", "세탁기 인기",
            "공기청정기 추천", "로봇청소기 가성비",
        ],
    },
    # ── 스포츠/아웃도어 (ID 16) ──
    "스포츠/아웃도어": {
        "core": [
            "러닝화", "등산화", "골프", "헬스", "캠핑",
            "자전거", "필라테스", "요가",
        ],
        "shopping": [
            "러닝화 추천", "캠핑용품 가성비", "골프 인기",
            "등산화 추천",
        ],
    },
    # ── 가구/인테리어 (ID 17) ──
    "가구/인테리어": {
        "core": [
            "소파", "침대", "매트리스", "책상", "의자",
            "인테리어", "조명", "커튼",
        ],
        "shopping": [
            "소파 추천", "매트리스 가성비", "책상 인기",
            "침대 추천", "의자 가성비",
        ],
    },
    # ── 반려동물 (ID 20) ──
    "반려동물": {
        "core": [
            "강아지사료", "고양이사료", "동물병원", "펫보험",
            "강아지간식", "고양이장난감", "펫시터",
        ],
        "shopping": [
            "강아지사료 추천", "고양이사료 인기", "펫용품 가성비",
            "강아지간식 추천",
        ],
    },
    # ── 주류 (ID 18) ──
    "주류": {
        "core": [
            "와인", "위스키", "맥주", "소주", "전통주",
        ],
        "shopping": [
            "와인 추천", "위스키 인기", "맥주 가성비",
        ],
    },
}


async def main():
    # Tables already exist; skip init_db to avoid mapper config issue
    # await init_db()

    async with async_session() as session:
        # ── Step 1: Ensure new industries exist ──
        for ind_data in NEW_INDUSTRIES:
            result = await session.execute(
                select(Industry).where(Industry.name == ind_data["name"])
            )
            existing = result.scalar_one_or_none()
            if not existing:
                new_ind = Industry(
                    name=ind_data["name"],
                    avg_cpc_min=ind_data.get("avg_cpc_min"),
                    avg_cpc_max=ind_data.get("avg_cpc_max"),
                )
                session.add(new_ind)
                print(f"[Industry] Added: {ind_data['name']}")
            else:
                print(f"[Industry] Already exists: {ind_data['name']} (id={existing.id})")
        await session.commit()

        # ── Step 2: Build industry name -> id map ──
        result = await session.execute(select(Industry))
        industries = {ind.name: ind.id for ind in result.scalars().all()}
        print(f"\nIndustry map ({len(industries)} total):")
        for name, iid in sorted(industries.items(), key=lambda x: x[1]):
            print(f"  {iid:3d}  {name}")

        # ── Step 3: Get existing keywords (keyword + industry_id pair) ──
        result = await session.execute(select(Keyword.keyword, Keyword.industry_id))
        existing_pairs = {(row[0], row[1]) for row in result.all()}
        # Also track keyword text only (for looser dedup)
        existing_texts = {row[0] for row in existing_pairs}
        print(f"\nExisting keywords: {len(existing_pairs)} pairs, {len(existing_texts)} unique texts")

        # ── Step 4: Insert keywords ──
        added = 0
        skipped = 0
        for industry_name, kw_groups in KEYWORD_SCOPE.items():
            ind_id = industries.get(industry_name)
            if ind_id is None:
                print(f"\n[WARN] Industry '{industry_name}' not found in DB, skipping")
                continue

            all_kws = kw_groups["core"] + kw_groups["shopping"]
            for kw_text in all_kws:
                kw_text = kw_text.strip()
                if (kw_text, ind_id) in existing_pairs:
                    skipped += 1
                    continue
                # Also skip if same text exists in same industry
                # (already covered above, but be safe)
                session.add(Keyword(
                    industry_id=ind_id,
                    keyword=kw_text,
                    is_active=True,
                ))
                existing_pairs.add((kw_text, ind_id))
                added += 1

        if added > 0:
            await session.commit()

        # ── Step 5: Summary ──
        result = await session.execute(select(Keyword))
        total = len(result.all())

        print(f"\n{'='*50}")
        print(f"Added:   {added} new keywords")
        print(f"Skipped: {skipped} (already exist)")
        print(f"Total:   {total} keywords in DB")
        print(f"{'='*50}")

        # Per-industry breakdown
        result = await session.execute(
            select(Industry.name, Industry.id)
        )
        ind_list = result.all()
        print(f"\nPer-industry keyword counts:")
        for ind_name, ind_id in sorted(ind_list, key=lambda x: x[1]):
            r = await session.execute(
                select(Keyword).where(Keyword.industry_id == ind_id)
            )
            kw_count = len(r.all())
            if kw_count > 0:
                print(f"  {ind_id:3d}  {ind_name:<20s}  {kw_count} keywords")


if __name__ == "__main__":
    asyncio.run(main())
