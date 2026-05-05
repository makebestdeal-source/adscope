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
# 유튜브 (시장 1.9조 -- 5배 확대)
os.environ["YOUTUBE_AD_WAIT_MS"] = "18000"
os.environ["YOUTUBE_PLAYER_SAMPLES"] = "50"     # 10→50 (5배)
os.environ["YOUTUBE_SURF_SAMPLES"] = "75"       # 15→75 (5배)
os.environ["YT_ADS_MAX_ADVERTISERS"] = "500"    # 100→500 (5배)
os.environ["YT_ADS_MAX_ADS"] = "1500"           # 300→1500 (5배)
# 구글검색 (시장 2.0조 -- 5배 확대)
os.environ["GS_ADS_MAX_ADVERTISERS"] = "250"    # 50→250 (5배)
os.environ["GS_ADS_MAX_ADS"] = "1000"           # 200→1000 (5배)
# 네이버쇼핑 (시장 1.1조 -- 5배 확대)
os.environ["NAVER_SHOP_MAX_ADS"] = "250"        # 50→250 (5배)
# 메타 라이브러리 (시장 1조 -- 5배 확대)
os.environ["META_TRUST_CHECK"] = "false"
os.environ["META_MAX_PAGES"] = "25"             # 5→25 (5배)
# 카카오 (시장 1.5조 -- 5배 확대)
os.environ["KAKAO_MAX_MEDIA"] = "40"            # 8→40 (5배, 실제 미디어 수까지만 수집)
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
from scripts.fix_industry_classifications import is_garbage as _is_garbage_advertiser
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
    "naver_search": 2,   # 검색: 2명
    # "naver_da": 2,   # → run_da_crawl.py로 분리
    # "kakao_da": 1,   # → run_da_crawl.py로 분리
    # youtube_surf / google_gdn / meta_feed 제거 — 수집 0건 확인
}

# 동시 브라우저 최대 수 (32GB 기준: ~400MB × 4 = ~1.6GB)
MAX_BROWSERS = 4
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


def _load_keywords_by_volume() -> dict[str, int]:
    """DB에서 monthly_search_vol 기준 키워드 볼륨 맵 반환."""
    import sqlite3
    db_path = Path(_root) / "adscope.db"
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT keyword, monthly_search_vol FROM keywords WHERE monthly_search_vol IS NOT NULL")
        result = {row[0]: row[1] for row in cur.fetchall()}
        conn.close()
        return result
    except Exception:
        return {}


def _sort_keywords_by_volume(keywords: list[str], volume_map: dict[str, int]) -> list[str]:
    """볼륨 데이터 있는 키워드 우선, 없으면 원래 순서 유지."""
    with_vol = sorted([(kw, volume_map.get(kw, 0)) for kw in keywords if kw in volume_map],
                       key=lambda x: -x[1])
    without_vol = [kw for kw in keywords if kw not in volume_map]
    return [kw for kw, _ in with_vol] + without_vol


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
        return _sort_keywords_by_volume(combined, _kw_volumes)
    return _sort_keywords_by_volume(base_keywords, _kw_volumes)


# ── 인구통계 페르소나 (제어그룹 제외) ──
DEMO_PERSONAS = [code for code, p in PERSONAS.items() if p.targeting_category == "demographic"]

# ── 키워드 볼륨 맵 로드 (naver_search/google_search_ads 정렬에 사용) ──
_kw_volumes = _load_keywords_by_volume()

# ── 네이버 검색 키워드 목록 (볼륨 정렬 전 원본) ──
_NAVER_SEARCH_KW = [
    # ── 금융/보험 (CPC 최고, 상업성 1위) ──
    "보험비교", "자동차보험", "실비보험", "대출", "신용카드",
    "생명보험", "암보험", "치아보험", "어린이보험", "운전자보험",
    "화재보험", "여행자보험", "반려동물보험", "질병보험",
    "개인연금", "IRP", "ETF", "주식투자", "펀드",
    "비상금대출", "카드론", "주택담보대출", "전세대출",
    "청년대출", "정부지원대출", "저금리대출",
    "체크카드", "할인카드", "포인트카드", "마일리지카드",
    "간편송금", "계좌개설", "파킹통장", "CMA통장",
    # ── 의료/건강 (CPC 2위) ──
    "치과", "임플란트", "피부과", "성형외과", "변호사",
    "라식", "라섹", "스마일라식", "안과",
    "정형외과", "재활치료", "물리치료", "도수치료",
    "한의원", "침치료", "추나요법", "한방다이어트",
    "비만클리닉", "체형교정", "모발이식", "제모",
    "피부레이저", "보톡스", "필러", "윤곽주사",
    "코성형", "눈성형", "가슴성형", "지방흡입",
    "내과", "가정의학과", "검진센터", "건강검진",
    "정신건강의학과", "심리상담", "산후조리원",
    "요양병원", "요양원", "실버케어",
    # ── 부동산/이사 (CPC 3위) ──
    "아파트", "인테리어", "이사업체", "분양", "원룸",
    "빌라", "오피스텔", "상가분양", "재건축", "재개발",
    "부동산앱", "전세", "월세", "역세권", "신축아파트",
    "청약", "LH청약", "공공분양", "아파트시세",
    "이삿짐센터", "포장이사", "반포장이사", "용달이사",
    "인테리어견적", "셀프인테리어", "실내인테리어", "사무실인테리어",
    "홈스타일링", "홈리모델링", "창문교체", "방음창",
    # ── 법률/세금/회계 (CPC 높음) ──
    "변호사상담", "법률상담", "이혼변호사", "형사변호사",
    "세무사", "회계사", "세금신고", "부가세신고",
    "노무사", "노동법률", "근로계약", "실업급여",
    "특허사무소", "상표등록", "법인설립",
    # ── 자동차 (CPC 높음) ──
    "자동차", "SUV", "전기차", "중고차", "경차",
    "블랙박스", "차량용방향제", "타이어", "네비게이션", "장기렌트",
    "하이브리드차", "수입차", "자동차보험가입", "자동차검사",
    "엔진오일", "차량용공기청정기", "하이패스", "차량용충전기",
    "세차용품", "광택", "카시트방석", "자동차매트",
    "단기렌트카", "카쉐어링", "전기차충전", "전기차보조금",
    # ── 가전/디지털 (검색량+CPC 모두 높음) ──
    "노트북", "냉장고", "에어컨", "공기청정기", "정수기",
    "세탁기", "건조기", "식기세척기", "로봇청소기", "무선청소기",
    "이어폰", "블루투스스피커", "모니터", "태블릿", "스마트폰",
    "선풍기", "제습기", "가습기", "전기밥솥", "안마의자",
    "전자레인지", "오븐", "믹서기", "에어프라이어", "커피머신",
    "스마트TV", "OLED TV", "프로젝터", "사운드바", "게이밍모니터",
    "기계식키보드", "게이밍마우스", "웹캠", "외장하드", "SSD",
    "공유기", "스마트플러그", "홈캠", "도어락", "스마트홈",
    "아이패드", "갤럭시탭", "전자책", "닌텐도", "플레이스테이션",
    "충전기", "보조배터리", "무선충전", "케이블", "어댑터",
    "케이스", "보호필름", "이어버드", "무선이어폰", "헤드폰",
    "전동칫솔", "전기면도기", "헤어클리퍼", "비데", "욕조",
    # ── 여행/숙박 ──
    "여행", "호텔", "항공권", "렌터카", "펜션", "리조트",
    "해외여행", "국내여행", "제주도여행", "강원도여행",
    "유럽여행", "일본여행", "동남아여행", "미국여행",
    "캠핑장", "글램핑", "풀빌라", "독채펜션", "호캉스",
    "여행패키지", "자유여행", "배낭여행", "크루즈여행",
    "비즈니스호텔", "부티크호텔", "에어비앤비",
    "공항픽업", "여행자보험", "여행가방", "여권파우치",
    "여행용화장품", "여행용어댑터", "캐리어대여",
    # ── 교육 ──
    "영어학원", "토익", "자격증", "과외", "온라인강의",
    "수학학원", "코딩학원", "미술학원", "피아노학원", "태권도",
    "토플", "오픽", "SAT", "한국어능력시험", "한자자격증",
    "운전면허", "요리학원", "바리스타자격증", "제빵자격증",
    "공무원시험", "경찰시험", "소방사시험", "간호사시험",
    "편입시험", "수능준비", "논술", "입시컨설팅",
    "독서논술", "어린이영어", "유아교육", "방문학습지",
    "인강", "유튜브강의", "클래스101", "탈잉",
    "외국어학원", "중국어", "일본어", "스페인어",
    "IT자격증", "정보처리기사", "네트워크관리사",
    # ── 건강/영양 ──
    "비타민", "영양제", "유산균", "콜라겐", "단백질",
    "홍삼", "오메가3", "루테인", "프로바이오틱스", "철분제",
    "마그네슘", "아연", "칼슘", "비타민D", "비타민C",
    "멀티비타민", "면역영양제", "간건강", "장건강", "눈건강",
    "관절영양제", "글루코사민", "코엔자임Q10", "NAD+",
    "다이어트약", "체중감량", "지방분해", "디톡스",
    # ── 뷰티/화장품 ──
    "선크림", "파운데이션", "립스틱", "마스크팩", "로션", "토너",
    "클렌징폼", "아이크림", "세럼", "향수", "네일", "제모기",
    "헤어드라이기", "고데기", "염색약", "두피케어",
    "쿠션파운데이션", "컨실러", "하이라이터", "쉐딩", "블러셔",
    "아이섀도", "아이라이너", "마스카라", "속눈썹", "눈썹",
    "립글로스", "립틴트", "립밤", "클렌징오일", "클렌징밀크",
    "미스트", "앰플", "에센스", "스킨케어세트", "남성화장품",
    "BB크림", "CC크림", "자외선차단제", "선스틱", "선쿠션",
    "헤어에센스", "헤어팩", "두피앰플", "샴푸바", "트리트먼트",
    "탈모샴푸", "탈모영양제", "헤어롤", "고데기빗", "아이롤러",
    "미용기기", "피부관리기", "LED마스크", "초음파클렌저",
    # ── 스포츠/레저 ──
    "골프채", "골프공", "골프레슨", "캠핑장비", "텐트",
    "등산화", "낚시용품", "자전거", "헬스장", "필라테스",
    "요가매트", "덤벨", "런닝머신", "수영", "축구화",
    "골프스코어", "골프백", "골프화", "골프장예약",
    "스포츠용품", "배드민턴", "탁구", "볼링", "클라이밍",
    "서핑보드", "패들보드", "스노우보드", "스키용품",
    "캠핑의자", "캠핑테이블", "랜턴", "버너", "코펠",
    "등산가방", "트레킹폴", "등산양말", "등산스틱",
    "헬스용품", "단백질쉐이커", "폼롤러", "밴드운동",
    "인라인스케이트", "킥보드", "전동킥보드",
    # ── 패션/의류 ──
    "여름옷", "반팔티", "원피스", "청바지", "운동화", "샌들",
    "등산복", "레깅스", "요가복", "골프웨어", "수영복", "패딩",
    "가방", "지갑", "시계", "선글라스", "모자", "넥타이",
    "남성정장", "여성구두", "스니커즈", "백팩", "캐리어",
    "봄자켓", "트렌치코트", "후드티", "맨투맨", "슬랙스",
    "치마", "니트", "가디건", "숏패딩", "롱패딩",
    "란제리", "속옷", "양말", "벨트", "스카프",
    "모자", "비니", "장화", "플랫슈즈", "하이힐",
    "명품가방", "크로스백", "숄더백", "클러치", "토트백",
    "남성가방", "여성지갑", "남성지갑", "카드지갑",
    # ── 가구/인테리어 ──
    "소파", "침대", "매트리스", "책상", "옷장", "선반",
    "커튼", "조명", "러그", "수납장", "식탁", "의자",
    "인테리어시공", "벽지", "바닥재", "타일", "페인트",
    "붙박이장", "드레스룸", "주방리모델링", "욕실리모델링",
    "블라인드", "롤스크린", "카펫", "쿠션", "스탠드조명",
    "모듈소파", "1인소파", "침대프레임", "라텍스매트리스",
    "책장", "행거", "신발장", "거울", "액자", "시계벽걸이",
    # ── 식품/음료 ──
    "라면", "간식", "커피", "우유", "냉동식품", "즉석밥",
    "건강음료", "다이어트식품", "닭가슴살", "프로틴", "견과류",
    "김치", "반찬", "과자", "아이스크림", "생선", "정육",
    "원두커피", "캡슐커피", "믹스커피", "녹차", "홍차", "허브티",
    "에너지드링크", "탄산음료", "주스", "식혜", "두유", "두유단백질",
    "쌀", "잡곡", "밀가루", "설탕", "소금", "식용유",
    "간장", "된장", "고추장", "참기름", "들기름",
    "과일", "채소", "딸기", "수박", "망고", "블루베리",
    "밀키트", "냉장반찬", "국내산한우", "삼겹살", "닭고기",
    "새우", "오징어", "참치캔", "햄", "소시지", "치즈",
    "요거트", "버터", "크림치즈", "아이스크림케이크",
    "초콜릿", "젤리", "사탕", "빵", "케이크", "마카롱",
    # ── 반려동물 ──
    "강아지사료", "고양이사료", "강아지간식", "고양이장난감",
    "동물병원", "펫보험", "반려동물용품",
    "강아지옷", "고양이화장실", "강아지유모차", "펫카시트",
    "강아지영양제", "고양이영양제", "반려동물미용", "펫호텔",
    "강아지패드", "고양이모래", "스크래쳐", "캣타워",
    "강아지목줄", "강아지하네스", "펫케어", "반려동물보험",
    # ── 육아/유아 ──
    "유모차", "아기침대", "카시트", "유아용품", "아기옷",
    "젖병", "이유식", "아기물티슈", "장난감",
    "유아식", "어린이영양제", "아기로션", "아기샴푸",
    "레고", "보드게임", "유아교구", "어린이책",
    "임신테스트기", "임산부영양제", "수유브라", "수유패드",
    "아기모니터", "아기카메라", "유아안전용품",
    # ── IT/소프트웨어/앱 ──
    "웹호스팅", "도메인", "클라우드서버", "VPN",
    "ERP", "CRM", "회계프로그램", "POS",
    "앱개발", "홈페이지제작", "쇼핑몰솔루션",
    "디자인툴", "영상편집", "사진편집", "PPT",
    "보안프로그램", "백신", "랜섬웨어방지",
    "원격근무", "화상회의", "협업툴", "프로젝트관리",
    "전자서명", "전자계약", "세금계산서",
    # ── 외식/배달/카페 ──
    "배달음식", "맛집", "치킨배달", "피자배달",
    "배달앱", "쿠팡이츠", "요기요",
    "카페창업", "프랜차이즈창업", "식당창업",
    "아메리카노", "라떼", "버블티", "스무디",
    "치킨", "피자", "중국집", "분식", "일식",
    "한식뷔페", "고기집", "삼겹살", "소고기",
    "브런치", "베이커리카페", "디저트카페",
    # ── 결혼/이벤트 ──
    "웨딩홀", "결혼정보", "상조",
    "스드메", "웨딩드레스", "웨딩촬영", "신혼여행",
    "청첩장", "돌잔치", "환갑잔치", "칠순",
    "꽃배달", "화환", "케이터링", "이벤트플래너",
    "돌봄서비스", "베이비시터", "아이돌봄",
    # ── 게임 ──
    "모바일게임", "게임다운로드",
    "RPG게임", "전략게임", "퍼즐게임",
    "PC게임", "콘솔게임", "게임아이템", "게임머니",
    "리그오브레전드", "배틀그라운드", "메이플스토리",
    # ── 엔터/미디어/문화 ──
    "OTT", "넷플릭스", "왓챠", "웨이브", "티빙",
    "공연예매", "뮤지컬", "연극", "콘서트", "팬미팅",
    "영화관", "CGV", "롯데시네마", "메가박스",
    "전시회", "박물관", "미술관", "테마파크",
    "아이돌", "K팝", "음악앱", "멜론", "지니뮤직",
    # ── 사무/B2B ──
    "사무용품", "프린터", "복합기", "잉크", "토너",
    "사무가구", "사무실의자", "스탠딩데스크",
    "명함", "현수막", "배너", "봉투인쇄", "인쇄소",
    "택배", "물류", "창고보관", "배송대행",
    "청소업체", "건물관리", "시설관리",
    "식자재", "구내식당", "케이터링서비스",
    # ── 주류/담배 ──
    "맥주", "소주", "와인", "위스키", "막걸리",
    "수제맥주", "와인구독", "양주", "전통주",
    # ── 중고/렌탈 ──
    "중고거래", "당근마켓", "번개장터", "중고폰",
    "가전렌탈", "정수기렌탈", "공기청정기렌탈", "안마의자렌탈",
    "차량렌트", "단기렌트", "장기렌트",
    # ── 브랜드 ──
    "쿠팡", "무신사", "올리브영", "오늘의집", "컬리",
    "배달의민족", "삼성전자", "LG전자", "다이슨", "코웨이",
    "현대자동차", "기아", "쏘카", "야놀자", "여기어때",
    "직방", "당근마켓", "번개장터", "토스", "카카오뱅크",
    "카카오", "네이버", "라인", "쿠팡이츠", "마켓컬리",
    "SSG닷컴", "롯데온", "11번가", "G마켓", "옥션",
    "아이허브", "이마트", "홈플러스", "코스트코",
    "스타벅스", "할리스", "이디야", "투썸플레이스",
    "교촌치킨", "BHC", "굽네치킨", "BBQ",
    "맥도날드", "버거킹", "롯데리아", "KFC",
    "CJ제일제당", "오뚜기", "농심", "삼양식품",
    "아모레퍼시픽", "LG생활건강", "한국콜마",
    "삼성화재", "현대해상", "DB손해보험", "KB손해보험",
    "신한은행", "국민은행", "우리은행", "하나은행",
    "현대카드", "삼성카드", "신한카드", "KB국민카드",
    "에이블씨엔씨", "클리오", "토니모리", "이니스프리",
]

# ── 채널별 크롤 태스크 (시장 규모 비례 볼륨) ──
# 페르소나는 라운드 로빈으로 자동 할당
#
# 시장규모 순: 구글전체(3.0조) > 네이버SA(1.9조) > 유튜브(1.9조) > 카카오(1.5조)
#              > 네이버쇼핑(1.1조) > 메타(1조) > 틱톡(0.3조)
CHANNEL_TASKS_BASE = [
    # ── 접촉 측정 (실제 브라우징) ──

    # [1] 네이버 검색 — 시장 1.9조
    # 1000개+ 키워드: 제품/카테고리 85% + 브랜드 15%
    # 업종 균등 배분: 생활/패션/가전/식품/뷰티/건강/반려/육아/스포츠/자동차/금융/부동산/여행/교육/의료/IT/외식/결혼/게임 등
    ("naver_search", _sort_keywords_by_volume(_NAVER_SEARCH_KW, _kw_volumes)),

    # ── 카탈로그 (페르소나 무관, 공개 데이터) ──

    # [6] 구글 투명성센터 — YouTube(VIDEO) + 검색광고(TEXT) 한 번에 수집
    # youtube_ads 크롤러가 VIDEO → youtube_ads, TEXT → google_search_ads 로 동시 저장
    ("youtube_ads", _generate_transparency_prefixes()),

    # [6b] Google GDN (Display Network) — 투명성센터 IMAGE 포맷
    # 삼성/현대/LG/SK/카카오/네이버/쿠팡 등 디스플레이 광고주 수집
    ("google_gdn", [
        "삼성", "현대", "LG", "SK", "카카오", "네이버", "쿠팡",
        "롯데", "CJ", "아모레퍼시픽", "신세계", "GS",
        "KB", "신한", "하나", "NH", "우리",
        "보험", "대출", "신용카드", "투자",
        "여행", "항공", "숙박",
        "자동차", "전기차",
        "부동산", "아파트",
        "교육", "영어",
        "다이어트", "피부과",
        "이마트", "홈플러스", "올리브영",
        "배민", "쿠팡이츠", "야놀자",
    ]),

    # [8] 메타 Ad Library (FB+IG 통합) — 시장 1조
    # 브라우즈 모드(""): KR 전체 활성 광고를 스크롤로 수집 (매 방문마다 다른 광고 노출)
    # 브랜드명 검색: meta_ad_keywords.json의 1025개 실제 한국 브랜드명으로 검색
    # (프리픽스 435개는 Meta Ad Library에서 0건 반환 → 브랜드명 검색으로 교체)
    ("meta", (
        [""] * 30  # KR 전체 브라우즈 30회
        + _load_meta_ad_keywords()  # 1025개 브랜드명 검색 (실제 광고주명 기반)
    )),

    # [9] 틱톡 — 시장 0.3조 (업종 확대: 8→14개)
    ("tiktok_ads", ["", "게임", "뷰티", "패션", "음식", "반려동물", "교육", "여행",
                    "금융", "기술", "건강", "자동차", "엔터테인먼트", "쇼핑"]),

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
        # 식품/음료
        "즉석식품", "냉동식품", "건강음료", "과자", "커피",
        "프리미엄커피", "캡슐커피", "원두커피", "에너지드링크",
        # 주방/생활
        "주방용품", "조리도구", "냄비", "프라이팬", "밀폐용기",
        "청소기", "드럼세탁기", "건조기", "식기세척기",
        # 의류/패션
        "여성티셔츠", "남성자켓", "청바지", "원피스", "니트",
        "패딩", "롱패딩", "가디건", "후드티", "맨투맨",
        # 뷰티 추가
        "향수", "선글라스", "헤어드라이어", "고데기", "샴푸",
        "컨디셔너", "바디워시", "핸드크림", "립밤", "쿠션",
        # 건강기기
        "혈압계", "체중계", "안마기", "마사지건", "족욕기",
        # 여행/레저
        "캐리어", "여행가방", "여권지갑", "여행파우치",
        # 사무용품
        "프린터", "복합기", "스캐너", "모니터암", "키보드",
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

TOTAL_TIMEOUT = 28800  # 480분 (8시간)


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
        quality_filtered = 0
        for ad in result.get("ads", []):
            # Korean filter: only store Korean-market ads
            if not is_korean_ad(ad.get("ad_text"), ad.get("advertiser_name"),
                                ad.get("brand"), ad.get("ad_description")):
                korean_filtered += 1
                continue

            # 품질 게이트: URL 없거나 소재(텍스트+이미지) 전부 없으면 저장 안 함
            has_url = bool(ad.get("url") or ad.get("display_url"))
            has_content = bool(ad.get("ad_text") or ad.get("creative_image_path"))
            if not has_url or not has_content:
                quality_filtered += 1
                continue

            adv_name = clean_advertiser_name(ad.get("advertiser_name"))
            # 추가 정리: URL, 도메인, 광고카피 제거
            adv_name = clean_name_for_pipeline(adv_name) if adv_name else adv_name
            # 쓰레기 광고주명 필터 (라이브러리 ID:, 이모지 카피, 랜덤코드 등)
            if adv_name and _is_garbage_advertiser(adv_name):
                adv_name = None
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
    "youtube_ads": 1800,         # VIDEO+TEXT 동시 수집 (google_search_ads 포함)
    "google_gdn": 600,           # 투명성센터 IMAGE 포맷 (키워드당 광고주 10개 × 15s)
    "meta": 1800,                # 360→1800 (5배)
    "naver_da": 900,             # 18개 지면 서핑 (탭 수 고정)
    "kakao_da": 3000,            # 600→3000 (5배, 미디어 순회)
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

    # 모든 채널 deadline까지 반복 수집 (카탈로그도 루프 — 키워드 다양성으로 새 광고 계속 발굴)
    # 1라운드: 볼륨 정렬 순서 유지 (상업성 높은 키워드 우선), 2라운드~: 셔플로 다양성 확보
    sorted_kw = list(keywords)

    round_num = 0
    while True:
        round_num += 1
        if round_num == 1:
            shuffled_kw = sorted_kw  # 1라운드는 볼륨 정렬 순서 그대로
        else:
            shuffled_kw = list(sorted_kw)
            random.shuffle(shuffled_kw)
            print(f"  [R] {channel_name} round {round_num} ({persona_code})", flush=True)
        if time.time() >= deadline:
            break

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

                # extra_results 처리 (예: youtube_ads가 함께 수집한 google_search_ads)
                for extra in result.get("extra_results", []):
                    extra_ads = extra.get("ads", [])
                    extra_channel = extra.get("channel", "")
                    if extra_ads and extra_channel:
                        from database import async_session
                        async with async_session() as session:
                            extra_batch_id, _ = await save_to_staging(
                                session, extra_channel, extra, kw, persona_code, device_type,
                            )
                        async with async_session() as session:
                            await wash_and_promote(session, extra_batch_id)
                        total_ads += len(extra_ads)
                        print(f"  [+] {extra_channel}/{kw}: {len(extra_ads)} text ads", flush=True)

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

    results = []

    # 전체 태스크 병렬 실행 (카탈로그+접촉 동시, 세마포어로 동시 브라우저 수 제한)
    print(f"\n  == Parallel: All {len(persona_tasks)} tasks (semaphore={MAX_BROWSERS}) ==", flush=True)
    all_coros = []
    for channel, persona_code, device, keywords in persona_tasks:
        print(f"  Starting {channel} [{persona_code}/{device}] ({len(keywords)} kw)...", flush=True)
        all_coros.append(crawl_channel(channel, persona_code, device, keywords, deadline))
    results = list(await asyncio.gather(*all_coros, return_exceptions=True))

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
