"""브랜드명 기반으로 ad_details.product_category / product_category_id 백필.

알려진 브랜드 → 소분류명 매핑을 이용해 기존 광고 데이터를 보강한다.
이미 product_category_id가 있는 레코드는 건드리지 않는다 (멱등성 보장).

Usage:
    python scripts/backfill_brand_categories.py
    python scripts/backfill_brand_categories.py --dry-run   # 실제 저장 안 함
"""
import asyncio
import io
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from database import async_session, init_db
from database.models import AdDetail, Advertiser, ProductCategory
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

# 브랜드명(소문자) → 소분류명 매핑
# 소분류명은 product_categories.name 과 정확히 일치해야 함
BRAND_SUBCATEGORY: dict[str, str] = {
    # ── 게임 ──
    "엔씨소프트": "PC게임", "nc소프트": "PC게임", "ncsoft": "PC게임",
    "넥슨": "PC게임", "nexon": "PC게임",
    "넷마블": "모바일게임", "netmarble": "모바일게임",
    "카카오게임즈": "모바일게임",
    "크래프톤": "PC게임", "krafton": "PC게임",
    "스마일게이트": "PC게임", "smilegate": "PC게임",
    "컴투스": "모바일게임", "com2us": "모바일게임",
    "펄어비스": "PC게임", "pearl abyss": "PC게임",
    "라이엇게임즈": "PC게임", "riot games": "PC게임",
    "블리자드": "PC게임", "blizzard": "PC게임",
    "슈퍼셀": "모바일게임", "supercell": "모바일게임",
    "플레이스테이션": "콘솔게임", "playstation": "콘솔게임", "ps5": "콘솔게임",
    "xbox": "콘솔게임", "닌텐도": "콘솔게임", "nintendo": "콘솔게임",
    "스팀": "게임플랫폼", "steam": "게임플랫폼",
    "t1": "e스포츠", "젠지": "e스포츠", "gen.g": "e스포츠",

    # ── 모바일/IT ──
    "삼성전자": "스마트폰", "samsung": "스마트폰",
    "애플": "스마트폰", "apple": "스마트폰", "아이폰": "스마트폰", "iphone": "스마트폰",
    "샤오미": "스마트폰", "xiaomi": "스마트폰",
    "lg그램": "노트북", "lg gram": "노트북",
    "맥북": "노트북", "macbook": "노트북",
    "갤럭시탭": "태블릿", "galaxy tab": "태블릿", "아이패드": "태블릿", "ipad": "태블릿",
    "에어팟": "이어폰/헤드폰", "airpods": "이어폰/헤드폰",
    "갤럭시버즈": "이어폰/헤드폰", "galaxy buds": "이어폰/헤드폰",
    "갤럭시워치": "스마트워치", "apple watch": "스마트워치",
    "로지텍": "주변기기", "logitech": "주변기기",
    "hp": "노트북", "dell": "노트북", "lenovo": "노트북", "레노버": "노트북",

    # ── 소프트웨어/SaaS ──
    "한컴": "업무툴", "microsoft": "업무툴", "ms365": "업무툴",
    "어도비": "디자인툴", "adobe": "디자인툴",
    "미리캔버스": "디자인툴", "캔바": "디자인툴", "canva": "디자인툴",
    "안랩": "보안솔루션", "이스트소프트": "보안솔루션",
    "더존비즈온": "ERP", "sap": "ERP",
    "salesforce": "CRM", "hubspot": "CRM",
    "슬랙": "협업툴", "slack": "협업툴", "팀즈": "협업툴", "jira": "협업툴",
    "뤼튼": "AI서비스", "wrtn": "AI서비스",
    "네이버클라우드": "클라우드", "kt클라우드": "클라우드", "aws": "클라우드",

    # ── 가전/전자 ──
    "코웨이": "공기청정기", "위닉스": "공기청정기",
    "쿠쿠": "조리기구", "쿠첸": "조리기구",
    "다이슨": "헤어드라이어", "dyson": "헤어드라이어",
    "에코백스": "로봇청소기", "ecovacs": "로봇청소기",
    "소니": "오디오", "sony": "오디오",
    "jbl": "오디오", "하만": "오디오",

    # ── 금융서비스 ──
    "kb국민카드": "카드", "삼성카드": "카드", "현대카드": "카드",
    "신한카드": "카드", "롯데카드": "카드", "bc카드": "카드",
    "삼성생명": "보험", "한화생명": "보험", "교보생명": "보험",
    "db손해보험": "보험", "현대해상": "보험", "kb손해보험": "보험",
    "kb증권": "투자", "키움증권": "투자", "미래에셋증권": "투자",
    "삼성증권": "투자", "한국투자증권": "투자", "nh투자증권": "투자",
    "카카오뱅크": "핀테크", "케이뱅크": "저축", "토스": "핀테크",
    "카카오페이": "핀테크", "네이버페이": "핀테크",
    "카카오페이손해보험": "보험",
    "현대캐피탈": "대출", "현대카드": "카드",
    "kb캐피탈": "대출", "신한캐피탈": "대출",
    "업비트": "암호화폐", "빗썸": "암호화폐", "코인원": "암호화폐",
    "sbi저축은행": "대출", "웰컴저축은행": "대출",
    "kb국민은행": "저축", "신한은행": "저축", "하나은행": "저축",
    "우리은행": "저축", "농협은행": "저축",

    # ── 뷰티/화장품 ──
    "아모레퍼시픽": "스킨케어", "아모레": "스킨케어",
    "설화수": "스킨케어", "라네즈": "스킨케어", "이니스프리": "스킨케어",
    "헤라": "메이크업", "에뛰드": "메이크업", "에뛰드하우스": "메이크업",
    "3ce": "메이크업", "롬앤": "메이크업", "클리오": "메이크업",
    "lg생활건강": "스킨케어", "숨37": "스킨케어", "오휘": "스킨케어",
    "닥터자르트": "더마/의약외품", "코스알엑스": "더마/의약외품",
    "비플레인": "더마/의약외품",
    "려": "헤어케어", "케라시스": "헤어케어", "아모스": "헤어케어",
    "바세린": "바디케어", "뉴트로지나": "바디케어",
    "조말론": "향수", "샤넬": "향수",

    # ── 패션 ──
    "무신사": "의류", "지그재그": "의류", "에이블리": "의류",
    "w컨셉": "의류", "29cm": "의류",
    "나이키": "신발", "nike": "신발",
    "아디다스": "신발", "adidas": "신발",
    "뉴발란스": "신발", "new balance": "신발",
    "쌤소나이트": "가방", "samsonite": "가방", "mcm": "가방",
    "제이에스티나": "주얼리",
    "타이맥스": "시계", "스와치": "시계", "카시오": "시계", "casio": "시계",

    # ── 스포츠/아웃도어 ──
    "노스페이스": "아웃도어의류", "the north face": "아웃도어의류",
    "k2": "아웃도어의류", "코오롱스포츠": "아웃도어의류",
    "데상트": "스포츠웨어", "descente": "스포츠웨어",
    "캘러웨이": "골프", "타이틀리스트": "골프", "callaway": "골프",
    "바디프랜드": "헬스/피트니스",
    "메리다": "자전거", "자이언트": "자전거",
    "블랙야크": "등산/캠핑", "코베아": "등산/캠핑",

    # ── 식품/음료 ──
    "cj제일제당": "간편식", "풀무원": "간편식", "오뚜기": "간편식",
    "농심": "간식/베이커리", "오리온": "간식/베이커리",
    "롯데제과": "간식/베이커리", "해태제과": "간식/베이커리",
    "파리바게뜨": "간식/베이커리", "뚜레쥬르": "간식/베이커리",
    "코카콜라": "음료", "롯데칠성": "음료", "동원f&b": "음료",
    "매일유업": "유제품", "남양유업": "유제품", "서울우유": "유제품",
    "스타벅스": "커피", "투썸플레이스": "커피",
    "메가커피": "커피", "이디야": "커피", "할리스": "커피",
    "하이트진로": "주류", "오비맥주": "주류", "카스": "주류",
    "종근당건강": "건강식품", "cj웰케어": "건강식품",
    "마켓컬리": "신선식품", "컬리": "신선식품",

    # ── 건강/의료 ──
    "유한양행": "약국", "동아제약": "약국", "종근당": "약국",
    "한미약품": "약국", "gc녹십자": "약국",
    "365mc": "다이어트", "닥터다이어트": "다이어트",
    "오라클피부과": "피부과/성형",
    "강남유디치과": "병원",
    "인바디": "의료기기",
    "닥터나우": "헬스앱",  # 앱서비스로 분류
    "눔": "헬스앱",

    # ── 교육 ──
    "메가스터디": "입시/수능", "이투스": "입시/수능", "대성마이맥": "입시/수능",
    "에듀윌": "자격증",
    "해커스": "어학", "야나두": "어학", "스픽": "어학", "speakit": "어학",
    "클래스101": "온라인강의", "패스트캠퍼스": "온라인강의", "콜로소": "온라인강의",
    "코드스테이츠": "코딩교육", "스파르타코딩": "코딩교육", "위코드": "코딩교육",
    "웅진씽크빅": "유아/초등교육", "아이스크림홈런": "유아/초등교육",

    # ── 여행/레저 ──
    "대한항공": "항공권", "kal": "항공권",
    "아시아나항공": "항공권", "아시아나": "항공권",
    "제주항공": "항공권", "진에어": "항공권",
    "에어부산": "항공권", "티웨이항공": "항공권",
    "하나투어": "패키지여행", "모두투어": "패키지여행",
    "야놀자": "호텔", "여기어때": "호텔",
    "에어비앤비": "레저/체험", "airbnb": "레저/체험",
    "롯데렌터카": "렌터카", "쏘카": "렌터카", "그린카": "렌터카",

    # ── 자동차 ──
    "현대자동차": "SUV", "현대": "SUV",
    "기아": "SUV", "제네시스": "승용차",
    "벤츠": "수입차", "mercedes": "수입차",
    "bmw": "수입차", "아우디": "수입차", "audi": "수입차",
    "볼보": "수입차", "volvo": "수입차",
    "테슬라": "전기차", "tesla": "전기차",
    "엔카": "중고차", "kb차차차": "중고차", "헤이딜러": "중고차", "첫차": "중고차",
    "불스원": "부품/용품", "3m": "부품/용품",

    # ── 엔터테인먼트 ──
    "넷플릭스": "OTT", "netflix": "OTT",
    "티빙": "OTT", "웨이브": "OTT", "왓챠": "OTT",
    "멜론": "음악", "지니뮤직": "음악",
    "cgv": "영화", "롯데시네마": "영화", "메가박스": "영화",
    "네이버웹툰": "웹툰", "카카오웹툰": "웹툰", "리디북스": "웹툰",
    "hybe": "방송/미디어", "sm엔터": "방송/미디어", "yg엔터": "방송/미디어",
    "아프리카tv": "스트리밍", "트위치": "스트리밍",

    # ── 유통/쇼핑 ──
    "쿠팡": "종합몰", "g마켓": "종합몰", "11번가": "종합몰",
    "ssg닷컴": "종합몰", "ssg": "종합몰",
    "이마트": "오프라인매장", "롯데마트": "오프라인매장", "홈플러스": "오프라인매장",
    "당근마켓": "중고거래", "중고나라": "중고거래", "번개장터": "중고거래",
    "cj온스타일": "홈쇼핑", "gs샵": "홈쇼핑", "현대홈쇼핑": "홈쇼핑",
    "오늘의집": "인테리어",

    # ── 통신/인터넷 ──
    "sk텔레콤": "이동통신", "skt": "이동통신",
    "kt": "이동통신", "lg유플러스": "이동통신", "uplus": "이동통신",
    "헬로모바일": "알뜰폰", "skb": "인터넷",

    # ── 부동산 ──
    "현대건설": "아파트분양", "gs건설": "아파트분양",
    "삼성물산": "아파트분양", "dl이앤씨": "아파트분양",
    "직방": "프롭테크", "다방": "전월세", "호갱노노": "프롭테크",
    "한샘": "인테리어",

    # ── 반려동물 ──
    "하림펫푸드": "반려동물식품", "로얄캐닌": "반려동물식품",
    "펫프렌즈": "반려동물용품", "어반펫": "반려동물용품", "핏펫": "펫보험",

    # ── 앱서비스 ──
    "배달의민족": "배달앱", "배민": "배달앱",
    "쿠팡이츠": "배달앱", "요기요": "배달앱",
    "카카오t": "유틸리티앱", "카카오택시": "유틸리티앱",
    "아만다": "데이팅앱", "정오의데이트": "데이팅앱",

    # ── 공공/기관 ──
    "한국관광공사": "지자체", "lh": "공공서비스",
    "한국전력": "공공서비스", "코레일": "공공서비스",
    "국민건강보험": "정부기관", "건강보험심사평가원": "정부기관",
}


async def _load_category_map(session: AsyncSession) -> dict[str, int]:
    """소분류명 → id 매핑 로드."""
    result = await session.execute(
        select(ProductCategory.name, ProductCategory.id).where(
            ProductCategory.parent_id.isnot(None)
        )
    )
    return {name: id_ for name, id_ in result.all()}


async def backfill(dry_run: bool = False) -> None:
    await init_db()

    async with async_session() as session:
        cat_map = await _load_category_map(session)
        print(f"카테고리 맵 로드: {len(cat_map)}개 소분류")

        # 광고주 목록 조회
        adv_result = await session.execute(
            select(Advertiser.id, Advertiser.name, Advertiser.brand_name)
        )
        advertisers = adv_result.all()
        print(f"광고주 {len(advertisers)}명 대상 매핑 시도")

        updated_advertisers = 0
        updated_ads = 0

        for adv_id, adv_name, brand_name in advertisers:
            # 브랜드명으로 소분류 찾기 (소문자 비교)
            name_candidates = [
                (adv_name or "").lower().strip(),
                (brand_name or "").lower().strip(),
            ]
            subcategory = None
            for candidate in name_candidates:
                if not candidate:
                    continue
                # 정확한 매핑만 사용 (부분 매칭 제외 — 오분류 방지)
                subcategory = BRAND_SUBCATEGORY.get(candidate)
                if subcategory:
                    break

            if not subcategory:
                continue

            cat_id = cat_map.get(subcategory)
            if not cat_id:
                print(f"  [WARN] 소분류 '{subcategory}' DB에 없음 — 광고주: {adv_name}")
                continue

            # 해당 광고주의 product_category_id 없는 ad_details 업데이트
            if not dry_run:
                result = await session.execute(
                    update(AdDetail)
                    .where(
                        AdDetail.advertiser_id == adv_id,
                        AdDetail.product_category_id.is_(None),
                    )
                    .values(
                        product_category=subcategory,
                        product_category_id=cat_id,
                    )
                )
                count = result.rowcount
            else:
                # dry-run: 카운트만
                from sqlalchemy import func, select as sa_select
                count_r = await session.execute(
                    sa_select(func.count(AdDetail.id)).where(
                        AdDetail.advertiser_id == adv_id,
                        AdDetail.product_category_id.is_(None),
                    )
                )
                count = count_r.scalar() or 0

            if count > 0:
                updated_advertisers += 1
                updated_ads += count
                print(f"  {'[DRY] ' if dry_run else ''}광고주: {adv_name} → {subcategory} ({count}건)")

        if not dry_run:
            await session.commit()

        print(f"\n완료: 광고주 {updated_advertisers}명, 광고 {updated_ads}건 {'(dry-run)' if dry_run else '업데이트'}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    asyncio.run(backfill(dry_run=dry))
