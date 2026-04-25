"""병렬 수집 + DB 저장 -- 10분 제한, 볼륨 최대화."""
import asyncio
import io
import json
import os
import random
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# ── 볼륨 최대화 설정 (매체 사이즈 비례) ──
# 시장규모: 구글전체 3.0조(검색2.0+GDN1.0) | 네이버SA 1.9조 | 유튜브 1.9조
#           카카오 1.5조 | 네이버쇼핑 1.1조 | 메타 1조 | 틱톡 0.3조
# 구글 검색광고 > 네이버 SA (글로벌 매체 비중 반영)
os.environ["CRAWLER_DWELL_MIN_MS"] = "1500"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2500"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MIN"] = "2"
os.environ["CRAWLER_DWELL_SCROLL_COUNT_MAX"] = "4"
os.environ["CRAWLER_INTER_PAGE_MIN_MS"] = "800"
os.environ["CRAWLER_INTER_PAGE_MAX_MS"] = "1500"
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"
# 유튜브 (시장 1.9조 -- 2배 확대)
os.environ["YOUTUBE_AD_WAIT_MS"] = "18000"
os.environ["YOUTUBE_PLAYER_SAMPLES"] = "20"     # 10→20 (2배)
os.environ["YOUTUBE_SURF_SAMPLES"] = "30"       # 15→30 (2배)
os.environ["YT_ADS_MAX_ADVERTISERS"] = "200"    # 100→200 (2배)
os.environ["YT_ADS_MAX_ADS"] = "600"            # 300→600 (2배)
# 구글검색 (시장 2.0조 -- 2배 확대)
os.environ["GS_ADS_MAX_ADVERTISERS"] = "100"    # 50→100 (2배)
os.environ["GS_ADS_MAX_ADS"] = "400"            # 200→400 (2배)
# 네이버쇼핑 (시장 1.1조 -- 2배 확대)
os.environ["NAVER_SHOP_MAX_ADS"] = "100"        # 50→100 (2배)
# GDN (시장 0.4조) — 2배 확대
os.environ["GDN_MAX_ADVERTISERS"] = "100"       # 50→100 (2배)
os.environ["GDN_MAX_ADS"] = "400"               # 200→400 (2배)
# 메타 (시장 1조 -- 2배 확대)
os.environ["META_TRUST_CHECK"] = "false"
os.environ["META_FEED_SCROLL_COUNT"] = "30"     # 15→30 (2배)
os.environ["META_MAX_PAGES"] = "10"             # 5→10 (2배)
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "30"  # 15→30 (2배)
os.environ["INSTAGRAM_REELS_SWIPES"] = "40"    # 20→40 (2배)
os.environ["FB_CONTACT_MAX_PAGES"] = "12"      # 6→12 (2배)
os.environ["FB_CONTACT_SCROLL_ROUNDS"] = "20"  # 10→20 (2배)
# 카카오 (시장 1.5조 -- 전체 12개 미디어 수집)
os.environ["KAKAO_MAX_MEDIA"] = "16"            # 8→16 (전체 지면 커버)
os.environ["MEDIA_COLLECTION_PROFILE"] = "full" # balanced→full (core+secondary+extended)
os.environ["KAKAO_LANDING_RESOLVE_LIMIT"] = "0"
# 네이버 DA
os.environ["NAVER_DA_CATEGORY_TABS"] = "6"      # 6 유지 (최대 탭 수)

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from crawler.stealth_patch import enable_stealth
enable_stealth()  # playwright-stealth 전체 크롤러 적용

from database import init_db
from database.models import AdSnapshot, AdDetail, Keyword, Persona, Advertiser, Industry
from sqlalchemy import select
from processor.advertiser_name_cleaner import clean_name_for_pipeline
from processor.korean_filter import is_korean_ad, clean_advertiser_name
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEFAULT_MOBILE, PC_DEVICE, get_device_for_persona
from processor.creative_hasher import compute_creative_hash, compute_text_hash
from processor.extra_data_normalizer import normalize_extra_data
from processor.landing_cache import get_cached_brand, cache_landing_result
from processor.data_washer import save_to_staging, wash_and_promote
from processor.channel_utils import (
    CONTACT_CHANNELS,
    CATALOG_CHANNELS,
    is_contact as _is_contact,
)

# ── 접촉 채널별 동시 페르소나 수 (연령/성별 다양성 확보) ──
# 각 페르소나는 독립 브라우저 세션 → 같은 지면에서 다른 광고 노출
# NOTE: OOM 방지를 위해 페르소나 수 축소 (2026-03-26)
CHANNEL_PERSONA_COUNT = {
    "naver_search": 2,   # 검색: 2명 (3→2)
    "naver_da": 2,       # DA 서핑: 2명 (3→2)
    "kakao_da": 1,       # 카카오 DA: 1명 (2→1)
    "youtube_surf": 2,   # 유튜브 서핑: 2명 (3→2)
    "google_gdn": 1,     # GDN 서핑: 1명 (2→1)
    "meta_feed": 1,      # 메타 피드: 1명 (2→1)
}

# 동시 브라우저 최대 수 (메모리 보호: ~300MB × 2 = ~600MB)
MAX_BROWSERS = 2
_browser_sem: asyncio.Semaphore | None = None


def _load_adic_top_advertisers() -> list[str]:
    """ADIC 100대 광고주 이름을 DB에서 로드 (YouTube/Google 검색 키워드로 활용)."""
    try:
        import sqlite3
        conn = sqlite3.connect(str(Path(_root) / "adscope.db"))
        rows = conn.execute("""
            SELECT DISTINCT advertiser_name FROM adic_ad_expenses
            WHERE medium = 'total' AND amount > 1000000
            ORDER BY amount DESC
            LIMIT 100
        """).fetchall()
        conn.close()
        if rows:
            return [r[0] for r in rows]
    except Exception:
        pass
    return []


def _load_youtube_ads_keywords() -> list[str]:
    """Load YouTube Ads keywords from seed JSON + ADIC top advertisers."""
    yt_path = Path(_root) / "database" / "seed_data" / "youtube_ads_keywords.json"
    base_keywords = []
    if yt_path.exists():
        with open(yt_path, encoding="utf-8") as f:
            data = json.load(f)
        base_keywords = data.get("keywords", [])
    if not base_keywords:
        base_keywords = ["samsung", "hyundai", "coupang", "baemin", "LG", "SK",
                "kakao", "naver", "shinhan", "hana", "lotte", "CJ"]

    # ADIC 100대 광고주 추가 (YouTube Transparency Center에서 직접 검색)
    adic_names = _load_adic_top_advertisers()
    if adic_names:
        combined = list(dict.fromkeys(base_keywords + adic_names))
        logger.info(f"[fast_crawl] YouTube keywords: {len(base_keywords)} base + {len(adic_names)} ADIC = {len(combined)} total")
        return combined
    return base_keywords


def _load_meta_ad_keywords() -> list[str]:
    """Load Meta Ad Library keywords from seed JSON, fallback to hardcoded list.

    빈 문자열("")을 앞에 포함 → 브라우즈 모드(KR 전체 활성 광고)를 먼저 수행.
    """
    meta_path = Path(_root) / "database" / "seed_data" / "meta_ad_keywords.json"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
        keywords = data.get("keywords", [])
        if keywords:
            return keywords
    # fallback
    return ["Samsung", "Hyundai", "LG", "SK", "Kia", "Lotte",
            "CJ", "Kakao", "Naver", "Coupang", "Amore Pacific",
            "Shinhan", "KB", "Hana", "NH", "Woori"]


def _generate_transparency_prefixes() -> list[str]:
    """한글 초성+중성 음절(가~힣) + 알파벳(a~z) + 숫자(0~9) 전체 생성.

    Google Ads Transparency Center에서 대한민국(region=KR) 광고주를
    빠짐없이 검색하기 위한 프리픽스 목록.
    - 한글: 19초성 × 21중성 = 399개 음절 (가, 개, 갸, ..., 히)
    - 알파벳: a~z (26개)
    - 숫자: 0~9 (10개)
    총 435개
    """
    prefixes = []
    # 한글 초성+중성 조합 (받침 없는 음절 = 가, 개, 갸, 걔, 거, 게, ...)
    # 유니코드 한글 음절 블록: 0xAC00 + (초성*21 + 중성) * 28
    for cho in range(19):      # ㄱ~ㅎ (19개 초성)
        for jung in range(21):  # ㅏ~ㅣ (21개 중성)
            code = 0xAC00 + (cho * 21 + jung) * 28
            prefixes.append(chr(code))
    # 알파벳 a-z
    prefixes.extend([chr(c) for c in range(ord('a'), ord('z') + 1)])
    # 숫자 0-9
    prefixes.extend([str(i) for i in range(10)])
    return prefixes


def _load_google_search_ads_keywords() -> list[str]:
    """Load Google Search Ads keywords from seed JSON + ADIC top advertisers."""
    gs_path = Path(_root) / "database" / "seed_data" / "google_search_ads_keywords.json"
    base_keywords = []
    if gs_path.exists():
        with open(gs_path, encoding="utf-8") as f:
            data = json.load(f)
        base_keywords = data.get("keywords", [])
    if not base_keywords:
        base_keywords = ["삼성", "현대", "LG", "SK", "카카오", "네이버", "쿠팡",
                "롯데", "CJ", "아모레퍼시픽", "신세계",
                "보험", "대출", "신용카드", "투자", "은행",
                "여행", "항공권", "호텔예약",
                "자동차", "전기차", "중고차",
                "부동산", "아파트", "인테리어",
                "교육", "영어", "코딩",
                "다이어트", "성형", "피부과", "탈모",
                "병원", "변호사", "치과",
                "이사", "가전", "노트북", "정수기"]

    # ADIC 100대 광고주 추가
    adic_names = _load_adic_top_advertisers()
    if adic_names:
        combined = list(dict.fromkeys(base_keywords + adic_names))
        return combined
    return base_keywords


# ── 인구통계 페르소나 (제어그룹 제외) ──
DEMO_PERSONAS = [code for code, p in PERSONAS.items() if p.targeting_category == "demographic"]

# ── 채널별 크롤 태스크 (시장 규모 비례 볼륨) ──
# 페르소나는 라운드 로빈으로 자동 할당
#
# 시장규모 순: 구글전체(3.0조) > 네이버SA(1.9조) > 유튜브(1.9조) > 카카오(1.5조)
#              > 네이버쇼핑(1.1조) > 메타(1조) > 틱톡(0.3조)
CHANNEL_TASKS_BASE = [
    # ── 접촉 측정 (실제 브라우징) ──

    # [1] 네이버 검색 — 시장 1.9조
    # 제품/카테고리 키워드 80% + 주요 브랜드 20%
    # 업종 균등 배분: 생활용품/패션/가전/식품/뷰티 등 일반 소비재 중심
    ("naver_search", [
        # ── 제품/카테고리 키워드 (80%) ──
        # 생활용품 (일상 소비재)
        "물티슈", "장갑", "세제", "섬유유연제", "샴푸", "치약",
        "생수", "휴지", "기저귀", "분유", "마스크", "손세정제",
        "수건", "빨래건조대", "우산", "칫솔", "면도기", "바디워시",
        # 패션/의류
        "여름옷", "반팔티", "원피스", "청바지", "운동화", "샌들",
        "등산복", "레깅스", "요가복", "골프웨어", "수영복", "패딩",
        "가방", "지갑", "시계", "선글라스", "모자", "넥타이",
        "남성정장", "여성구두", "스니커즈", "백팩", "캐리어",
        # 뷰티/화장품
        "선크림", "파운데이션", "립스틱", "마스크팩", "로션", "토너",
        "클렌징폼", "아이크림", "세럼", "향수", "네일", "제모기",
        "헤어드라이기", "고데기", "염색약", "두피케어",
        # 가전/디지털
        "노트북", "냉장고", "에어컨", "공기청정기", "정수기",
        "세탁기", "건조기", "식기세척기", "로봇청소기", "무선청소기",
        "이어폰", "블루투스스피커", "모니터", "태블릿", "스마트폰",
        "선풍기", "제습기", "가습기", "전기밥솥", "안마의자",
        "전자레인지", "오븐", "믹서기", "에어프라이어", "커피머신",
        # 가구/인테리어
        "소파", "침대", "매트리스", "책상", "옷장", "선반",
        "커튼", "조명", "러그", "수납장", "식탁", "의자",
        # 식품/음료
        "라면", "간식", "커피", "우유", "냉동식품", "즉석밥",
        "건강음료", "다이어트식품", "닭가슴살", "프로틴", "견과류",
        "김치", "반찬", "과자", "아이스크림", "생선", "정육",
        # 건강/영양
        "비타민", "영양제", "유산균", "콜라겐", "단백질",
        "홍삼", "오메가3", "루테인", "프로바이오틱스", "철분제",
        # 반려동물
        "강아지사료", "고양이사료", "강아지간식", "고양이장난감",
        "동물병원", "펫보험", "반려동물용품",
        # 육아/유아
        "유모차", "아기침대", "카시트", "유아용품", "아기옷",
        "젖병", "이유식", "아기물티슈", "장난감",
        # 스포츠/레저
        "골프채", "골프공", "골프레슨", "캠핑장비", "텐트",
        "등산화", "낚시용품", "자전거", "헬스장", "필라테스",
        "요가매트", "덤벨", "런닝머신", "수영", "축구화",
        # 자동차/용품
        "자동차", "SUV", "전기차", "중고차", "경차",
        "블랙박스", "차량용방향제", "타이어", "네비게이션", "장기렌트",
        # 금융/보험 (편중 방지 — 핵심만)
        "보험비교", "자동차보험", "실비보험", "대출", "신용카드",
        # 부동산
        "아파트", "인테리어", "이사업체", "분양", "원룸",
        # 여행/숙박
        "여행", "호텔", "항공권", "렌터카", "펜션", "리조트",
        # 교육
        "영어학원", "토익", "자격증", "과외", "온라인강의",
        # 의료/법률
        "치과", "임플란트", "피부과", "성형외과", "변호사",
        # 렌탈/구독
        "정수기렌탈", "공기청정기렌탈", "가전렌탈",
        # 외식/배달
        "배달음식", "맛집", "치킨배달", "피자배달",
        # 결혼
        "웨딩홀", "결혼정보", "상조",
        # 게임
        "모바일게임", "게임다운로드",
        # ── 주요 브랜드 (20%) ──
        "쿠팡", "무신사", "올리브영", "오늘의집", "컬리",
        "배달의민족", "삼성전자", "LG전자", "다이슨", "코웨이",
        "현대자동차", "기아", "쏘카", "야놀자", "여기어때",
        "직방", "당근마켓", "번개장터", "토스", "카카오뱅크",
    ]),

    # [2] 카카오 DA — 시장 1.5조 (keyword_dependent=False — 키워드 무관, media_urls 전체 순회)
    # crawl_keyword()가 keyword 무시하고 media_urls[:KAKAO_MAX_MEDIA] 전체 방문
    # → 키워드 1개로 충분 (반복 루핑은 접촉 채널이므로 round_num으로 자동 처리)
    ("kakao_da", ["all"]),

    # [3] 네이버 DA — 서핑 모드: 1세션에서 18개 지면 + 기사 서브페이지 순회
    ("naver_da", ["surf"]),

    # [4] GDN — 언론사 서핑 + Transparency Center IMAGE (프리픽스 검색)
    ("google_gdn", ["surf"] + _generate_transparency_prefixes()),

    # [5] 유튜브 서핑 — 시장 1.9조 (영상 직접 로드)
    ("youtube_surf", ["surf"]),

    # ── 카탈로그 (페르소나 무관, 공개 데이터) ──

    # [6] 유튜브 투명성센터 — 전체 KR 광고주 프리픽스 검색 (64개)
    ("youtube_ads", _generate_transparency_prefixes()),

    # [7] 구글 검색광고 투명성센터 — 전체 KR 광고주 프리픽스 검색 (64개)
    ("google_search_ads", _generate_transparency_prefixes()),

    # [8] 메타 (FB+IG 통합) — 시장 1조
    # 브라우즈 모드(""): KR 전체 활성 광고를 스크롤로 수집 (매 방문마다 다른 광고 노출)
    # 프리픽스 검색: 한글 초성+중성 + 알파벳 + 숫자로 국내 모든 광고주 검색
    ("meta", (
        [""] * 10  # KR 전체 브라우즈 10회
        + _generate_transparency_prefixes()  # 435개 프리픽스 검색
    )),

    # [8.5] 메타 피드 서핑 — 로그인 후 실제 FB/IG 피드에서 Sponsored 광고 수집
    ("meta_feed", ["both"]),

    # [9] 틱톡 — 시장 0.3조 (카테고리별 Top Ads 수집, 2배 확대)
    ("tiktok_ads", ["", "게임", "뷰티", "패션", "음식", "반려동물", "교육", "여행"]),

    # [10] 네이버 쇼핑 — 시장 1.1조 (키워드 2배 확대)
    ("naver_shopping", [
        # 뷰티/화장품 (쇼핑검색 최대 카테고리)
        "화장품", "선크림", "세럼", "클렌징", "마스크팩", "립스틱",
        "파운데이션", "아이섀도", "로션", "토너", "앰플", "미스트",
        # 가전/디지털
        "노트북", "에어컨", "공기청정기", "냉장고", "세탁기", "TV",
        "이어폰", "정수기", "안마의자", "로봇청소기",
        "스마트폰", "태블릿", "스마트워치", "무선청소기", "식기세척기",
        # 건강/식품
        "비타민", "프로틴", "영양제", "유산균", "다이어트식품",
        "홍삼", "오메가3", "루테인", "콜라겐", "단백질바",
        # 유아/생활
        "유모차", "기저귀", "분유", "아기침대", "카시트",
        # 패션/스포츠
        "운동화", "캠핑", "골프", "등산", "레깅스", "요가복",
        "골프채", "골프백", "텐트", "등산화",
        # 브랜드 가전
        "다이슨", "삼성가전", "LG가전", "필립스", "코웨이", "쿠쿠",
        # 게임/게이밍 기기
        "게이밍키보드", "게이밍마우스", "게이밍헤드셋", "게이밍모니터",
        "닌텐도스위치", "PS5", "Xbox",
        # 가구/인테리어
        "소파", "침대", "매트리스", "책상", "옷장",
        "수납장", "선반", "조명", "커튼",
        # 자동차 용품
        "블랙박스", "타이어", "카시트", "차량용품",
        "차량방향제", "썬팅", "휠커버",
        # 반려동물
        "강아지간식", "고양이용품", "반려동물장례",
        "고양이사료", "강아지사료", "강아지옷", "고양이장난감",
        # 식품
        "단백질", "콜라겐", "루테인",
        "즉석식품", "냉동식품", "건강음료", "과자", "커피",
    ]),

]


def build_persona_tasks():
    """페르소나별 채널 태스크 생성 — 접촉 채널은 다수 페르소나 동시 투입.

    CHANNEL_PERSONA_COUNT에 따라 접촉 채널마다 2~3개 페르소나를 배정.
    12개 인구통계 페르소나를 셔플하여 연령/성별 다양성 최대화.
    카탈로그 채널은 페르소나 무관 1회 수집.
    """
    tasks = []  # (channel, persona_code, device_type, keywords)

    # 접촉 채널 목록 추출
    contact_tasks = [(ch, kw) for ch, kw in CHANNEL_TASKS_BASE if ch in CONTACT_CHANNELS]
    catalog_tasks = [(ch, kw) for ch, kw in CHANNEL_TASKS_BASE if ch not in CONTACT_CHANNELS]

    # ── 카탈로그 채널 먼저: headless, 빠름 → 시간 내 최대 수집 보장 ──
    for channel, keywords in catalog_tasks:
        tasks.append((channel, None, "pc", keywords))

    # ── 접촉 채널: 채널별 N개 페르소나 동시 배정 ──
    shuffled_personas = list(DEMO_PERSONAS)
    random.shuffle(shuffled_personas)
    persona_idx = 0

    # DA/피드 채널은 모바일웹 강제 (PC보다 광고 노출이 훨씬 많음)
    FORCE_MOBILE_CHANNELS = {"naver_da", "kakao_da", "meta_feed"}

    for channel, keywords in contact_tasks:
        n_personas = CHANNEL_PERSONA_COUNT.get(channel, 1)
        for _ in range(n_personas):
            if persona_idx >= len(shuffled_personas):
                persona_idx = 0
                random.shuffle(shuffled_personas)  # 한 바퀴 돌면 재셔플
            code = shuffled_personas[persona_idx]
            persona = PERSONAS[code]
            if channel in FORCE_MOBILE_CHANNELS:
                device = "mobile"
            else:
                device = "mobile" if "mobile" in persona.primary_device else "pc"
            tasks.append((channel, code, device, keywords))
            persona_idx += 1

    return tasks

TOTAL_TIMEOUT = 7200  # 120분 (2시간 — 어제 대비 2배 볼륨)


async def save_to_db(channel_name, result, keyword_text, persona_code, device_type):
    """수집 결과를 DB에 저장."""
    from database import async_session
    async with async_session() as session:
        ind_result = await session.execute(
            select(Industry).where(Industry.name == "기타")
        )
        industry = ind_result.scalar_one_or_none()
        if not industry:
            industry = Industry(name="기타")
            session.add(industry)
            await session.flush()

        kw_result = await session.execute(
            select(Keyword).where(Keyword.keyword == keyword_text)
        )
        kw = kw_result.scalar_one_or_none()
        if not kw:
            kw = Keyword(keyword=keyword_text, industry_id=industry.id, is_active=True)
            session.add(kw)
            await session.flush()

        # 카탈로그 채널도 persona_id 필요 (NOT NULL) — 없으면 M30 기본값
        _code = persona_code or "M30"
        persona_row = None
        p_result = await session.execute(
            select(Persona).where(Persona.code == _code)
        )
        persona_row = p_result.scalar_one_or_none()
        if not persona_row:
            _p = PERSONAS.get(_code)
            _age = str(_p.age_group).replace("대", "") if _p and _p.age_group else "30"
            _gender = "F" if (_p and _p.gender and "여" in _p.gender) else ("M" if _code[0:1] != "F" else "F")
            persona_row = Persona(code=_code, age_group=_age, gender=_gender, login_type="none")
            session.add(persona_row)
            await session.flush()

        snap = AdSnapshot(
            keyword_id=kw.id,
            persona_id=persona_row.id if persona_row else None,
            device=device_type,
            channel=channel_name,
            captured_at=result.get("captured_at"),
            ad_count=len(result.get("ads", [])),
            screenshot_path=result.get("screenshot_path"),
            page_url=result.get("page_url", ""),
        )
        session.add(snap)
        await session.flush()

        korean_filtered = 0
        for ad in result.get("ads", []):
            # Korean filter: only store Korean-market ads
            if not is_korean_ad(ad.get("ad_text"), ad.get("advertiser_name"),
                                ad.get("brand"), ad.get("ad_description")):
                korean_filtered += 1
                continue

            adv_name = clean_advertiser_name(ad.get("advertiser_name"))
            # 추가 정리: URL, 도메인, 광고카피 제거
            adv_name = clean_name_for_pipeline(adv_name) if adv_name else adv_name
            advertiser_id = None
            if adv_name:
                adv_result = await session.execute(
                    select(Advertiser).where(Advertiser.name == adv_name)
                )
                adv = adv_result.scalar_one_or_none()
                if not adv:
                    adv = Advertiser(name=adv_name)
                    session.add(adv)
                    await session.flush()
                advertiser_id = adv.id

            # extra_data 정규화
            raw_extra = ad.get("extra_data") or {}
            normalized_extra = normalize_extra_data(raw_extra, channel_name)

            # creative hash 계산
            c_hash = compute_creative_hash(ad.get("creative_image_path"))
            if not c_hash:
                c_hash = compute_text_hash(adv_name, ad.get("ad_text"), ad.get("url"))

            # landing URL 캐시 활용 (광고주명 보강)
            ad_url = ad.get("url")
            if ad_url and not adv_name:
                cached = await get_cached_brand(session, ad_url)
                if cached and cached.get("brand_name"):
                    adv_name = cached["brand_name"]
                    advertiser_id = cached.get("advertiser_id")
            elif ad_url and adv_name:
                # 해석 결과를 캐시에 저장
                await cache_landing_result(session, ad_url, brand_name=adv_name, advertiser_id=advertiser_id)

            detail = AdDetail(
                snapshot_id=snap.id,
                persona_id=persona_row.id,
                advertiser_id=advertiser_id,
                advertiser_name_raw=adv_name,
                ad_text=ad.get("ad_text"),
                ad_description=ad.get("ad_description"),
                position=ad.get("position"),
                url=ad.get("url"),
                display_url=ad.get("display_url"),
                ad_type=ad.get("ad_type"),
                verification_status=ad.get("verification_status"),
                verification_source=ad.get("verification_source"),
                creative_image_path=ad.get("creative_image_path"),
                creative_hash=c_hash,
                extra_data=normalized_extra,
                is_contact=_is_contact(channel_name, ad),
            )
            session.add(detail)

        # Update ad_count to reflect filtered count
        if korean_filtered:
            snap.ad_count = snap.ad_count - korean_filtered
            await session.commit()
        else:
            await session.commit()
        return snap.id


def _detect_adb_device() -> str | None:
    """ADB 연결된 Android 디바이스 serial 반환. 없으면 None."""
    try:
        from crawler.mobile.adb_client import ADBClient
        devices = ADBClient.list_devices()
        if devices:
            serial = devices[0].get("serial")
            logger.info(f"[mobile] ADB 디바이스 감지: {serial}")
            return serial
    except Exception:
        pass
    return None


async def crawl_mobile_apps(device_serial: str, deadline: float) -> list[dict]:
    """ADB 디바이스로 Instagram + Naver 앱 광고 수집.

    mitmproxy가 없으면 조용히 스킵.
    deadline까지 남은 시간 내에서 수집.
    """
    try:
        import importlib
        mitmproxy_module = importlib.util.find_spec("mitmproxy")
        if not mitmproxy_module:
            logger.info("[mobile] mitmproxy 미설치 — 앱 수집 스킵 (pip install mitmproxy)")
            return []
    except Exception:
        return []

    remaining = deadline - time.time()
    if remaining < 60:
        return []

    mobile_results = []
    per_app_sec = min(90, int(remaining / 2))

    try:
        from crawler.mobile.instagram_app import InstagramAppCrawler
        ig_crawler = InstagramAppCrawler(device_serial=device_serial)
        ig_result = await ig_crawler.crawl(duration_sec=per_app_sec)
        if ig_result.get("ads"):
            mobile_results.append(ig_result)
            logger.info(f"[mobile_instagram] {len(ig_result['ads'])}건 수집")
    except Exception as exc:
        logger.warning(f"[mobile_instagram] 수집 실패: {exc}")

    if time.time() < deadline - 60:
        try:
            from crawler.mobile.naver_app import NaverAppCrawler
            naver_crawler = NaverAppCrawler(device_serial=device_serial)
            naver_result = await naver_crawler.crawl(duration_sec=per_app_sec)
            if naver_result.get("ads"):
                mobile_results.append(naver_result)
                logger.info(f"[mobile_naver] {len(naver_result['ads'])}건 수집")
        except Exception as exc:
            logger.warning(f"[mobile_naver] 수집 실패: {exc}")

    return mobile_results


def _get_crawler_cls(channel_name):
    from crawler.naver_da import NaverDACrawler
    from crawler.naver_search import NaverSearchCrawler
    from crawler.google_gdn import GoogleGDNCrawler
    from crawler.kakao_da import KakaoDACrawler
    from crawler.youtube_ads import YouTubeAdsCrawler
    from crawler.youtube_surf import YouTubeSurfCrawler
    from crawler.meta_library import MetaLibraryCrawler
    from crawler.meta_feed_surf import MetaFeedSurfCrawler
    from crawler.tiktok_ads import TikTokAdsCrawler
    from crawler.naver_shopping import NaverShoppingCrawler
    from crawler.google_search_ads import GoogleSearchAdsCrawler

    return {
        "naver_search": NaverSearchCrawler,
        "naver_da": NaverDACrawler,
        "google_gdn": GoogleGDNCrawler,
        "google_search_ads": GoogleSearchAdsCrawler,
        "kakao_da": KakaoDACrawler,
        "youtube_ads": YouTubeAdsCrawler,
        "youtube_surf": YouTubeSurfCrawler,
        "meta": MetaLibraryCrawler,
        "meta_feed": MetaFeedSurfCrawler,
        "tiktok_ads": TikTokAdsCrawler,
        "naver_shopping": NaverShoppingCrawler,
    }[channel_name]


CHANNEL_TIMEOUT = {
    "google_gdn": 480,           # 240→480 (2배)
    "google_search_ads": 480,    # 240→480 (2배)
    "youtube_ads": 720,          # 360→720 (2배)
    "youtube_surf": 720,         # 360→720 (2배)
    "meta": 720,                 # 360→720 (2배)
    "naver_da": 900,             # 18개 지면 + 기사 서브페이지 서핑
    "kakao_da": 600,             # 16개 미디어 순회 (각 ~11초 × 16 = ~176초 + 여유)
    "meta_feed": 480,            # FB + IG 피드 서핑 (25스크롤 × 2플랫폼)
}


async def crawl_channel(channel_name, persona_code, device_type, keywords, deadline):
    """단일 채널+페르소나: 키워드 순회하며 deadline까지 최대한 수집. staging 경유.

    브라우저 세마포어로 동시 브라우저 인스턴스 수를 MAX_BROWSERS로 제한.
    """
    global _browser_sem
    if _browser_sem is None:
        _browser_sem = asyncio.Semaphore(MAX_BROWSERS)

    cls = _get_crawler_cls(channel_name)
    # 카탈로그 채널은 페르소나 없음 — 크롤링 시 기본 프로필 사용
    persona = PERSONAS.get(persona_code, PERSONAS["M30"]) if persona_code else PERSONAS["M30"]
    device = get_device_for_persona(persona)
    per_kw_timeout = CHANNEL_TIMEOUT.get(channel_name, 120)

    total_ads = 0
    promoted_count = 0
    errors = []

    # 접촉/DA 채널: deadline까지 지면을 반복 순회 (광고 로테이션으로 매번 다른 광고)
    # 카탈로그 채널: 1회 순회 (같은 쿼리 = 같은 결과)
    is_contact = channel_name in CONTACT_CHANNELS
    shuffled_kw = list(keywords)
    random.shuffle(shuffled_kw)

    round_num = 0
    while True:
        round_num += 1
        if round_num > 1 and not is_contact:
            break  # 카탈로그 채널은 1회만
        if time.time() >= deadline:
            break
        if round_num > 1:
            random.shuffle(shuffled_kw)
            print(f"  [R] {channel_name} round {round_num} ({persona_code})", flush=True)

        for kw in shuffled_kw:
            if time.time() >= deadline:
                break
            remaining = deadline - time.time()
            if remaining < 10:
                break

            t0 = time.time()
            try:
                # 세마포어: 동시 브라우저 수 MAX_BROWSERS 이하로 제한
                async with _browser_sem:
                    async with cls() as crawler:
                        result = await asyncio.wait_for(
                            crawler.crawl_keyword(kw, persona, device),
                            timeout=min(remaining, per_kw_timeout),
                        )
                ads = result.get("ads", [])
                total_ads += len(ads)

                if ads:
                    # Staging -> Wash -> Auto-promote
                    from database import async_session
                    async with async_session() as session:
                        batch_id, staged = await save_to_staging(
                            session, channel_name, result, kw, persona_code, device_type,
                        )
                    async with async_session() as session:
                        wp_result = await wash_and_promote(session, batch_id)
                    w = wp_result["wash"]
                    p = wp_result["promote"]
                    promoted_count += p.get("promoted", 0)
                    dedup_count = p.get("deduped", 0)
                    elapsed = time.time() - t0
                    dedup_str = f"/{dedup_count}dup" if dedup_count else ""
                    print(
                        f"  [+] {channel_name}/{kw} ({persona_code}): "
                        f"{len(ads)} ads -> {w['approved']}ok/{w['rejected']}rej "
                        f"-> {p.get('promoted',0)} new{dedup_str} ({elapsed:.0f}s)",
                        flush=True,
                    )
                else:
                    elapsed = time.time() - t0
                    print(f"  [+] {channel_name}/{kw} ({persona_code}): 0 ads ({elapsed:.0f}s)", flush=True)

            except asyncio.TimeoutError:
                print(f"  [T] {channel_name}/{kw} ({persona_code}): timeout ({time.time()-t0:.0f}s)", flush=True)
            except Exception as e:
                err_msg = str(e)[:120]
                errors.append(err_msg)
                print(f"  [!] {channel_name}/{kw} ({persona_code}): {err_msg}", flush=True)

    return {
        "channel": channel_name,
        "persona": persona_code,
        "total_ads": total_ads,
        "promoted": promoted_count,
        "errors": errors,
    }


async def main():
    await init_db()

    persona_tasks = build_persona_tasks()
    contact_count = sum(1 for ch, p, d, kw in persona_tasks if p is not None)
    catalog_count = len(persona_tasks) - contact_count
    unique_personas = len(set(p for _, p, _, _ in persona_tasks if p))

    # ADB 디바이스 감지 (모바일 앱 수집 가능 여부)
    adb_serial = _detect_adb_device()

    print("=" * 60)
    print(f"  AdScope Parallel Crawl -- {len(persona_tasks)} tasks")
    print(f"  Contact: {contact_count} (x{unique_personas} personas) | Catalog: {catalog_count}")
    print(f"  Max browsers: {MAX_BROWSERS} | Timeout: {TOTAL_TIMEOUT}s")
    if adb_serial:
        print(f"  Mobile ADB: {adb_serial} (Instagram + Naver app crawl)")
    print("=" * 60)

    deadline = time.time() + TOTAL_TIMEOUT
    t_start = time.time()

    # ── 웨이브 실행: 카탈로그(headless) 먼저, 접촉(headful) 나중에 ──
    # 전부 동시에 띄우면 메모리 폭발 + 브라우저 크래시 발생
    catalog_tasks = [(ch, p, d, kw) for ch, p, d, kw in persona_tasks if ch not in CONTACT_CHANNELS]
    contact_tasks = [(ch, p, d, kw) for ch, p, d, kw in persona_tasks if ch in CONTACT_CHANNELS]

    results = []

    # Wave 1: 카탈로그 (headless, 가벼움 — 3개씩 배치, OOM 방지)
    if catalog_tasks:
        MAX_CATALOG_BATCH = 3
        print(f"\n  == Wave 1: Catalog ({len(catalog_tasks)} tasks, {MAX_CATALOG_BATCH}/batch) ==", flush=True)
        for ci in range(0, len(catalog_tasks), MAX_CATALOG_BATCH):
            if time.time() >= deadline:
                print("  [!] Deadline reached during Wave 1", flush=True)
                break
            cat_batch = catalog_tasks[ci:ci + MAX_CATALOG_BATCH]
            wave1 = []
            for channel, persona_code, device, keywords in cat_batch:
                print(f"  Starting {channel} [{persona_code}/{device}] ({len(keywords)} kw)...", flush=True)
                wave1.append(crawl_channel(channel, persona_code, device, keywords, deadline))
            wave1_results = await asyncio.gather(*wave1, return_exceptions=True)
            results.extend(wave1_results)
            # 배치 간 메모리 정리
            if ci + MAX_CATALOG_BATCH < len(catalog_tasks):
                import gc; gc.collect()
                await asyncio.sleep(2)

    if time.time() >= deadline:
        print("  [!] Deadline reached after Wave 1", flush=True)
    else:
        # Wave 2: 접촉 (headful, 무거움 — 3개씩 배치 실행, OOM 방지)
        MAX_CONTACT_BATCH = 3
        print(f"\n  == Wave 2: Contact ({len(contact_tasks)} tasks, {MAX_CONTACT_BATCH}/batch) ==", flush=True)
        for i in range(0, len(contact_tasks), MAX_CONTACT_BATCH):
            if time.time() >= deadline:
                print("  [!] Deadline reached, skipping remaining contact batches", flush=True)
                break
            batch = contact_tasks[i:i + MAX_CONTACT_BATCH]
            wave2 = []
            for channel, persona_code, device, keywords in batch:
                print(f"  Starting {channel} [{persona_code}/{device}] ({len(keywords)} kw)...", flush=True)
                wave2.append(crawl_channel(channel, persona_code, device, keywords, deadline))
            batch_results = await asyncio.gather(*wave2, return_exceptions=True)
            results.extend(batch_results)
            # 배치 간 5초 쿨다운 + GC (메모리 정리 시간)
            if i + MAX_CONTACT_BATCH < len(contact_tasks):
                import gc; gc.collect()
                await asyncio.sleep(5)

    # Wave 3: 모바일 앱 수집 (ADB 연결 시)
    if adb_serial and time.time() < deadline:
        print(f"\n  == Wave 3: Mobile App ({adb_serial}) ==", flush=True)
        mobile_results = await crawl_mobile_apps(adb_serial, deadline)
        for mob_result in mobile_results:
            channel = mob_result.get("channel", "mobile")
            ads = mob_result.get("ads", [])
            if ads:
                try:
                    from database import async_session
                    async with async_session() as session:
                        batch_id, staged = await save_to_staging(
                            session, channel, mob_result, "surf", "mobile", "android"
                        )
                    async with async_session() as session:
                        wp = await wash_and_promote(session, batch_id)
                    p = wp["promote"]
                    promoted_n = p.get("promoted", 0)
                    dedup_n = p.get("deduped", 0)
                    dedup_str = f"/{dedup_n}dup" if dedup_n else ""
                    print(f"  [+] {channel}: {len(ads)} ads -> {promoted_n} new{dedup_str}", flush=True)
                    results.append({"channel": channel, "persona": "mobile", "total_ads": len(ads), "promoted": promoted_n, "errors": []})
                except Exception as e:
                    print(f"  [!] {channel} DB 저장 실패: {str(e)[:120]}", flush=True)
        if not mobile_results:
            print("  (no mobile ads collected or mitmproxy not available)", flush=True)

    # 결과 요약
    elapsed_total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  RESULTS (total {elapsed_total:.0f}s)")
    print(f"{'=' * 60}")

    grand_total = 0
    grand_promoted = 0
    # 채널별 합산
    channel_summary = {}
    for r in results:
        if isinstance(r, Exception):
            print(f"  [X] Exception: {str(r)[:100]}")
            continue
        ch = r["channel"]
        persona = r.get("persona", "?")
        ads = r["total_ads"]
        promoted = r.get("promoted", 0)
        errs = len(r["errors"])
        grand_total += ads
        grand_promoted += promoted

        if ch not in channel_summary:
            channel_summary[ch] = {"ads": 0, "promoted": 0, "personas": [], "errors": 0}
        channel_summary[ch]["ads"] += ads
        channel_summary[ch]["promoted"] += promoted
        channel_summary[ch]["errors"] += errs
        if persona:
            channel_summary[ch]["personas"].append(persona)

        status = "OK" if promoted > 0 else ("ERR" if errs > 0 else "EMPTY")
        print(f"  {ch:20s} | {(persona or '-'):4s} | {ads:4d} ads | {promoted:4d} promoted | {errs} errors | {status}")

    # 채널별 합산 요약
    print(f"\n  {'─' * 58}")
    print(f"  {'CHANNEL':20s} | {'PERSONAS':12s} | {'ADS':>5s} | {'PROMOTED':>8s}")
    print(f"  {'─' * 58}")
    for ch, s in sorted(channel_summary.items()):
        p_str = ",".join(s["personas"]) if s["personas"] else "-"
        print(f"  {ch:20s} | {p_str:12s} | {s['ads']:5d} | {s['promoted']:8d}")
    print(f"  {'─' * 58}")

    print(f"\n  TOTAL: {grand_total} collected -> {grand_promoted} promoted to live DB")

    # Campaign & spend rebuild
    if grand_promoted > 0:
        print("\n  Rebuilding campaigns & spend estimates...", flush=True)
        try:
            from processor.campaign_builder import rebuild_campaigns_and_spend
            stats = await rebuild_campaigns_and_spend(active_days=30)
            print(f"  Campaigns: {stats['campaigns_total']} | Spend: {stats['spend_estimates_total']} | New advertisers: {stats['created_advertisers']}")
        except Exception as e:
            print(f"  [!] Campaign rebuild failed: {str(e)[:100]}")

    print(f"  Refresh http://localhost:3001 to see results")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
