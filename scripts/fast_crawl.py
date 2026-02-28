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
# 유튜브 (시장 1.9조 -- 최대 볼륨)
os.environ["YOUTUBE_AD_WAIT_MS"] = "18000"
os.environ["YOUTUBE_PLAYER_SAMPLES"] = "10"
os.environ["YOUTUBE_SURF_SAMPLES"] = "15"       # 10→15 (시장비중 반영)
os.environ["YT_ADS_MAX_ADVERTISERS"] = "100"
os.environ["YT_ADS_MAX_ADS"] = "300"
# 구글검색 (시장 2.0조 -- 네이버SA 대비 동등 이상 수집, 글로벌 매체 비중 반영)
os.environ["GS_ADS_MAX_ADVERTISERS"] = "50"
os.environ["GS_ADS_MAX_ADS"] = "200"
# 네이버쇼핑 (시장 1.1조 -- 파워링크 수 극대화)
os.environ["NAVER_SHOP_MAX_ADS"] = "50"
# GDN (시장 0.4조) — Transparency Center IMAGE format
os.environ["GDN_MAX_ADVERTISERS"] = "50"
os.environ["GDN_MAX_ADS"] = "200"
# 메타 (시장 1조)
os.environ["META_TRUST_CHECK"] = "false"
os.environ["META_FEED_SCROLL_COUNT"] = "15"
os.environ["META_MAX_PAGES"] = "5"
os.environ["INSTAGRAM_EXPLORE_CLICKS"] = "15"
os.environ["INSTAGRAM_REELS_SWIPES"] = "20"
os.environ["FB_CONTACT_MAX_PAGES"] = "6"
os.environ["FB_CONTACT_SCROLL_ROUNDS"] = "10"
# 카카오 (시장 1.5조)
os.environ["KAKAO_MAX_MEDIA"] = "8"             # 6→8 (시장비중 반영)
os.environ["KAKAO_LANDING_RESOLVE_LIMIT"] = "0"
# 네이버 DA
os.environ["NAVER_DA_CATEGORY_TABS"] = "6"      # 4→6 (시장비중 반영)

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

    # [1] 네이버 검색 — 시장 1.9조 (최대 키워드 배정, 55개)
    ("naver_search", [
        # 금융/보험 (CPC 최고가 업종)
        "보험", "보험비교", "자동차보험", "실비보험",
        "대출", "신용대출", "주택담보대출",
        "신용카드", "적금", "주식", "투자",
        # 여행/숙박
        "여행", "호텔", "항공권", "렌터카", "패키지여행",
        # 자동차
        "자동차", "SUV", "전기차", "중고차", "수입차",
        # 부동산/인테리어
        "아파트", "인테리어", "이사", "부동산", "분양", "원룸",
        # 교육
        "영어학원", "코딩교육", "자격증", "공무원학원", "수능", "유아교육",
        # 건강/뷰티
        "다이어트", "헬스", "피부관리", "탈모", "성형외과",
        "화장품", "피부과", "치과",
        # 쇼핑/생활/가전
        "가전", "노트북", "냉장고", "정수기", "에어컨", "공기청정기",
        # 법률/의료
        "변호사", "병원", "법률상담",
        # 반려동물
        "반려동물", "강아지사료",
        # 웨딩/생활
        "결혼", "웨딩",
        # 취업/창업
        "취업", "창업", "프랜차이즈",
        # 소비자 브랜드 (직접 검색으로 광고 노출)
        "다이슨", "코웨이", "쿠쿠", "SK매직", "에이스침대", "시몬스",
        "올리브영", "무신사", "컬리", "오늘의집", "배달의민족", "요기요",
        "안다르", "젝시믹스", "메가커피", "컴포즈커피", "스타벅스",
        "삼성전자", "LG전자", "현대자동차", "기아자동차",
        # 게임사 (업종 과소대표 보정)
        "넥슨", "크래프톤", "엔씨소프트", "넷마블", "스마일게이트",
        "카카오게임즈", "펄어비스", "위메이드", "컴투스", "데브시스터즈",
        "모바일게임", "온라인게임", "PC게임", "게임 사전예약", "게임 다운로드",
        "게임 순위", "신작게임", "RPG게임", "게임 이벤트",
        # 외식/프랜차이즈 (업종 보강)
        "치킨 프랜차이즈", "카페 창업", "배달음식", "맛집", "뷔페",
        "삼겹살", "족발", "피자", "햄버거", "분식",
        # 결혼/웨딩 (업종 보강)
        "웨딩홀", "웨딩박람회", "결혼정보회사", "스드메", "허니문",
        # 반려동물 (업종 보강)
        "반려견용품", "고양이사료", "동물병원", "펫보험",
        # 법률/세무 (업종 보강)
        "형사변호사", "이혼변호사", "세무사", "법무법인",
        # 렌탈/구독 (업종 보강)
        "렌탈", "정수기렌탈", "공기청정기렌탈", "가전렌탈",
        # IT/플랫폼 (업종 보강)
        "챗GPT", "AI", "앱개발", "웹개발", "클라우드",
        # 부동산 세분화
        "오피스텔", "빌라", "전원주택", "상가임대", "토지매매",
        # 건강/의료 세분화
        "임플란트", "교정", "라식라섹", "척추", "관절",
        "한의원", "한방치료", "통증치료",
    ]),

    # [2] 카카오 DA — 시장 1.5조 (페이지 확대: 6→12)
    ("kakao_da", [
        "main", "news", "entertainment", "shopping", "finance", "sports",
        "webtoon", "beauty", "travel", "auto", "game", "food",
    ]),

    # [3] 네이버 DA — 네이버 전체의 일부 (페이지 확대: 3→6)
    ("naver_da", ["main", "news", "entertainment", "sports", "finance", "shopping"]),

    # [4] GDN — Transparency Center IMAGE format (구글검색과 동일 키워드)
    ("google_gdn", _load_google_search_ads_keywords()),

    # [5] 유튜브 서핑 — 시장 1.9조 (영상 직접 로드)
    ("youtube_surf", ["surf"]),

    # ── 카탈로그 (페르소나 무관, 공개 데이터) ──

    # [6] 유튜브 투명성센터 — 시장 1.9조 (247 키워드)
    ("youtube_ads", _load_youtube_ads_keywords()),

    # [7] 구글 검색광고 투명성센터 — 시장 2.0조 (네이버SA 이상 수집, 200+ 키워드)
    ("google_search_ads", _load_google_search_ads_keywords()),

    # [8] 메타 (FB+IG) — 시장 1조 (478 키워드)
    ("facebook", _load_meta_ad_keywords()),
    ("instagram", _load_meta_ad_keywords()),

    # [9] 틱톡 — 시장 0.3조
    ("tiktok_ads", [""]),

    # [10] 네이버 쇼핑 — 시장 1.1조 (고경쟁 상품군 키워드 최대화)
    ("naver_shopping", [
        # 뷰티/화장품 (쇼핑검색 최대 카테고리)
        "화장품", "선크림", "세럼", "클렌징", "마스크팩", "립스틱",
        # 가전/디지털
        "노트북", "에어컨", "공기청정기", "냉장고", "세탁기", "TV",
        "이어폰", "정수기", "안마의자", "로봇청소기",
        # 건강/식품
        "비타민", "프로틴", "영양제", "유산균", "다이어트식품",
        # 유아/생활
        "유모차", "기저귀", "분유",
        # 패션/스포츠
        "운동화", "캠핑", "골프", "등산",
        # 브랜드 가전
        "다이슨", "삼성가전", "LG가전", "필립스",
        # 게임/게이밍 기기
        "게이밍키보드", "게이밍마우스", "게이밍헤드셋", "게이밍모니터",
        # 가구/인테리어
        "소파", "침대", "매트리스", "책상", "옷장",
        # 자동차 용품
        "블랙박스", "타이어", "카시트", "차량용품",
        # 반려동물
        "강아지간식", "고양이용품", "반려동물장례",
        # 식품/건강
        "단백질", "콜라겐", "홍삼", "오메가3", "루테인",
    ]),

]


def build_persona_tasks():
    """페르소나별 채널 태스크 생성. 접촉 채널은 전체 12 페르소나 순환, 카탈로그는 1회.

    접촉 채널마다 2~3개 페르소나를 배정하여 모든 연령대(10~60대)가 커버되도록 한다.
    실행마다 persona_idx가 달라지므로 여러 번 실행 시 모든 페르소나가 골고루 사용됨.
    """
    tasks = []  # (channel, persona_code, device_type, keywords)

    # 접촉 채널 목록 추출
    contact_tasks = [(ch, kw) for ch, kw in CHANNEL_TASKS_BASE if ch in CONTACT_CHANNELS]
    catalog_tasks = [(ch, kw) for ch, kw in CHANNEL_TASKS_BASE if ch not in CONTACT_CHANNELS]

    # 각 접촉 채널에 2~3개 페르소나 배정 (전체 12 페르소나를 고르게 분배)
    # 실행마다 시작점을 랜덤으로 변경하여 편향 방지
    shuffled_personas = list(DEMO_PERSONAS)
    random.shuffle(shuffled_personas)

    personas_per_channel = max(2, len(shuffled_personas) // max(len(contact_tasks), 1))
    persona_idx = 0

    for channel, keywords in contact_tasks:
        assigned = 0
        while assigned < personas_per_channel and persona_idx < len(shuffled_personas):
            code = shuffled_personas[persona_idx]
            persona = PERSONAS[code]
            device = "mobile" if "mobile" in persona.primary_device else "pc"
            tasks.append((channel, code, device, keywords))
            persona_idx += 1
            assigned += 1

    # 남은 페르소나가 있으면 접촉 채널에 추가 배정
    remaining_idx = 0
    while persona_idx < len(shuffled_personas):
        channel, keywords = contact_tasks[remaining_idx % len(contact_tasks)]
        code = shuffled_personas[persona_idx]
        persona = PERSONAS[code]
        device = "mobile" if "mobile" in persona.primary_device else "pc"
        tasks.append((channel, code, device, keywords))
        persona_idx += 1
        remaining_idx += 1

    # 카탈로그 채널: 페르소나 없음 (검색/카탈로그는 연령·성별 무관)
    for channel, keywords in catalog_tasks:
        tasks.append((channel, None, "pc", keywords))

    return tasks

TOTAL_TIMEOUT = 900  # 15분


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


def _get_crawler_cls(channel_name):
    from crawler.naver_da import NaverDACrawler
    from crawler.naver_search import NaverSearchCrawler
    from crawler.google_gdn import GoogleGDNCrawler
    from crawler.kakao_da import KakaoDACrawler
    from crawler.youtube_ads import YouTubeAdsCrawler
    from crawler.youtube_surf import YouTubeSurfCrawler
    from crawler.instagram_catalog import InstagramCatalogCrawler
    from crawler.meta_library import MetaLibraryCrawler
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
        "facebook": MetaLibraryCrawler,
        "instagram": InstagramCatalogCrawler,
        "tiktok_ads": TikTokAdsCrawler,
        "naver_shopping": NaverShoppingCrawler,
    }[channel_name]


CHANNEL_TIMEOUT = {
    "google_gdn": 240,
    "google_search_ads": 240,    # 200+ kw, 글로벌 매체 비중 반영
    "youtube_ads": 360,
    "youtube_surf": 360,
    "instagram": 360,
    "facebook": 360,
    "naver_da": 180,
}


async def crawl_channel(channel_name, persona_code, device_type, keywords, deadline):
    """단일 채널: 키워드 순회하며 deadline까지 최대한 수집. staging 경유."""
    cls = _get_crawler_cls(channel_name)
    # 카탈로그 채널은 페르소나 없음 — 크롤링 시 기본 프로필 사용
    persona = PERSONAS.get(persona_code, PERSONAS["M30"]) if persona_code else PERSONAS["M30"]
    device = get_device_for_persona(persona)
    per_kw_timeout = CHANNEL_TIMEOUT.get(channel_name, 120)

    total_ads = 0
    promoted_count = 0
    errors = []

    # 매 실행마다 다른 키워드부터 시작하도록 셔플
    shuffled_kw = list(keywords)
    random.shuffle(shuffled_kw)

    for kw in shuffled_kw:
        if time.time() >= deadline:
            break
        remaining = deadline - time.time()
        if remaining < 10:
            break

        t0 = time.time()
        try:
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

    print("=" * 60)
    print("  AdScope Parallel Crawl (10 min limit)")
    print("=" * 60)

    deadline = time.time() + TOTAL_TIMEOUT
    t_start = time.time()

    # 페르소나별 태스크 생성 + 병렬 실행
    persona_tasks = build_persona_tasks()
    tasks = []
    for channel, persona_code, device, keywords in persona_tasks:
        print(f"  Starting {channel} [{persona_code}/{device}] ({len(keywords)} kw)...", flush=True)
        tasks.append(crawl_channel(channel, persona_code, device, keywords, deadline))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 결과 요약
    elapsed_total = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"  RESULTS (total {elapsed_total:.0f}s)")
    print(f"{'=' * 60}")

    grand_total = 0
    grand_promoted = 0
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
        status = "OK" if promoted > 0 else ("ERR" if errs > 0 else "EMPTY")
        print(f"  {ch:20s} | {(persona or '-'):4s} | {ads:4d} ads | {promoted:4d} promoted | {errs} errors | {status}")

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
