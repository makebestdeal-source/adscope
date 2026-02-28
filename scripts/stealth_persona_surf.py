"""멀티 페르소나 기사면/소셜 광고 수집기.

headful Chrome + playwright-stealth로 실제 사용자처럼 서핑하며 광고 수집.
네이버뉴스/다음뉴스 -> 원본 기사 -> GDN/네이버DA/카카오DA 캡처.
12개 페르소나(10~60대 남녀)로 타겟팅 광고 차이 측정.

Usage:
  python scripts/stealth_persona_surf.py                  # 기본 6 페르소나 (20~40대)
  python scripts/stealth_persona_surf.py --all             # 전체 12 페르소나 (10~60대)
  python scripts/stealth_persona_surf.py F30 M40 F40      # 특정 페르소나만
  python scripts/stealth_persona_surf.py M10 F10 --social  # 10대 + 소셜 포함
"""
import asyncio
import io
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import DEVICES, get_device_for_persona

# ── 광고 네트워크 패턴 ──
AD_NETWORKS = {
    "youtube": ["youtube.com/api/stats/ads", "youtube.com/pagead/",
                "youtube.com/ptracking", "youtubei/v1/player",
                "youtube.com/get_midroll_info"],
    "gdn": ["doubleclick.net", "googlesyndication.com", "googleads",
             "adservice.google", "googleadservices", "pagead",
             "securepubads", "adsense", "tpc.googlesyndication"],
    "naver": ["siape.veta.naver.com", "adcr.naver.com", "adsun.naver.com",
              "displayad.naver.com", "nstat.naver.com"],
    "naver_shopping": ["ad.search.naver.com", "adcr.naver.com/adcr?"],
    "kakao": ["adfit.kakao.com", "display.ad.daum.net", "t1.daumcdn.net/adfit",
              "ad.daum.net"],
    "meta": ["facebook.com/tr", "connect.facebook.net", "graph.facebook.com",
             "ads.instagram.com"],
}

ALL_PATTERNS = []
for pats in AD_NETWORKS.values():
    ALL_PATTERNS.extend(pats)

# ── 네이버/다음 뉴스 카테고리 ──
NEWS_CATEGORIES = [
    ("naver-politics", "https://news.naver.com/section/100"),
    ("naver-economy", "https://news.naver.com/section/101"),
    ("naver-society", "https://news.naver.com/section/102"),
    ("naver-sports", "https://sports.news.naver.com/"),
    ("daum-politics", "https://news.daum.net/politics"),
    ("daum-economy", "https://news.daum.net/economic"),
    ("daum-society", "https://news.daum.net/society"),
    ("daum-sports", "https://sports.daum.net/"),
]

# ── 언론사 카테고리별 URL (GDN 수집 핵심) — 30개사 ──
PUBLISHER_CATEGORIES = {
    # ── Tier 1: 종합 일간지 (대형 광고주 집중) ──
    "chosun": [
        ("chosun-politics", "https://www.chosun.com/politics/"),
        ("chosun-economy", "https://www.chosun.com/economy/"),
        ("chosun-society", "https://www.chosun.com/national/"),
        ("chosun-sports", "https://www.chosun.com/sports/"),
    ],
    "joongang": [
        ("joongang-politics", "https://www.joongang.co.kr/politics"),
        ("joongang-economy", "https://www.joongang.co.kr/money"),
        ("joongang-society", "https://www.joongang.co.kr/society"),
        ("joongang-sports", "https://www.joongang.co.kr/sports"),
    ],
    "donga": [
        ("donga-politics", "https://www.donga.com/news/Politics"),
        ("donga-economy", "https://www.donga.com/news/Economy"),
        ("donga-society", "https://www.donga.com/news/Society"),
        ("donga-sports", "https://www.donga.com/news/Sports"),
    ],
    "hani": [
        ("hani-politics", "https://www.hani.co.kr/arti/politics"),
        ("hani-economy", "https://www.hani.co.kr/arti/economy"),
        ("hani-society", "https://www.hani.co.kr/arti/society"),
        ("hani-sports", "https://www.hani.co.kr/arti/sports"),
    ],
    "khan": [
        ("khan-politics", "https://www.khan.co.kr/politics"),
        ("khan-economy", "https://www.khan.co.kr/economy"),
        ("khan-society", "https://www.khan.co.kr/national"),
        ("khan-sports", "https://www.khan.co.kr/sports"),
    ],
    "hankookilbo": [
        ("hankook-politics", "https://www.hankookilbo.com/News/Politics"),
        ("hankook-economy", "https://www.hankookilbo.com/News/Economy"),
        ("hankook-society", "https://www.hankookilbo.com/News/Society"),
        ("hankook-sports", "https://www.hankookilbo.com/News/Sports"),
    ],
    # ── Tier 2: 방송사 (TV 광고주 디지털 확장) ──
    "sbs": [
        ("sbs-politics", "https://news.sbs.co.kr/news/newsSection.do?plink=TOPNAV&sectionId=01"),
        ("sbs-economy", "https://news.sbs.co.kr/news/newsSection.do?plink=TOPNAV&sectionId=02"),
        ("sbs-society", "https://news.sbs.co.kr/news/newsSection.do?plink=TOPNAV&sectionId=03"),
        ("sbs-sports", "https://sports.sbs.co.kr/"),
    ],
    "kbs": [
        ("kbs-politics", "https://news.kbs.co.kr/news/pc/category/category.do?ref=pMnavi#111"),
        ("kbs-economy", "https://news.kbs.co.kr/news/pc/category/category.do?ref=pMnavi#112"),
        ("kbs-society", "https://news.kbs.co.kr/news/pc/category/category.do?ref=pMnavi#113"),
        ("kbs-sports", "https://news.kbs.co.kr/news/pc/category/category.do?ref=pMnavi#115"),
    ],
    "mbc": [
        ("mbc-politics", "https://imnews.imbc.com/news/2026/politic/"),
        ("mbc-economy", "https://imnews.imbc.com/news/2026/econo/"),
        ("mbc-society", "https://imnews.imbc.com/news/2026/society/"),
        ("mbc-sports", "https://imnews.imbc.com/news/2026/sports/"),
    ],
    "jtbc": [
        ("jtbc-politics", "https://news.jtbc.co.kr/section/list.aspx?scode=10"),
        ("jtbc-economy", "https://news.jtbc.co.kr/section/list.aspx?scode=20"),
        ("jtbc-society", "https://news.jtbc.co.kr/section/list.aspx?scode=30"),
        ("jtbc-sports", "https://news.jtbc.co.kr/section/list.aspx?scode=60"),
    ],
    "ytn": [
        ("ytn-politics", "https://www.ytn.co.kr/news/list.php?mcd=0101"),
        ("ytn-economy", "https://www.ytn.co.kr/news/list.php?mcd=0102"),
        ("ytn-society", "https://www.ytn.co.kr/news/list.php?mcd=0103"),
        ("ytn-sports", "https://www.ytn.co.kr/news/list.php?mcd=0107"),
    ],
    # ── Tier 3: 경제지 (금융/부동산 광고주 밀집) ──
    "mk": [
        ("mk-economy", "https://www.mk.co.kr/news/economy/"),
        ("mk-stock", "https://www.mk.co.kr/news/stock/"),
        ("mk-realestate", "https://www.mk.co.kr/news/realestate/"),
        ("mk-society", "https://www.mk.co.kr/news/society/"),
    ],
    "hankyung": [
        ("hk-economy", "https://www.hankyung.com/economy"),
        ("hk-finance", "https://www.hankyung.com/finance"),
        ("hk-realestate", "https://www.hankyung.com/realestate"),
        ("hk-society", "https://www.hankyung.com/society"),
    ],
    "edaily": [
        ("edaily-economy", "https://www.edaily.co.kr/news/economy"),
        ("edaily-stock", "https://www.edaily.co.kr/news/stock"),
        ("edaily-realestate", "https://www.edaily.co.kr/news/realestate"),
    ],
    "mt": [
        ("mt-economy", "https://news.mt.co.kr/mtview.php?type=1"),
        ("mt-stock", "https://news.mt.co.kr/mtview.php?type=2"),
        ("mt-realestate", "https://news.mt.co.kr/mtview.php?type=7"),
    ],
    "sedaily": [
        ("sedaily-economy", "https://www.sedaily.com/NewsList/GC01"),
        ("sedaily-stock", "https://www.sedaily.com/NewsList/GC02"),
        ("sedaily-realestate", "https://www.sedaily.com/NewsList/GC07"),
    ],
    "fnnews": [
        ("fnnews-economy", "https://www.fnnews.com/section/001"),
        ("fnnews-stock", "https://www.fnnews.com/section/002"),
        ("fnnews-realestate", "https://www.fnnews.com/section/007"),
    ],
    "heraldcorp": [
        ("herald-economy", "https://biz.heraldcorp.com/economy"),
        ("herald-finance", "https://biz.heraldcorp.com/finance"),
        ("herald-realestate", "https://biz.heraldcorp.com/realestate"),
    ],
    "asiae": [
        ("asiae-economy", "https://www.asiae.co.kr/list/economy"),
        ("asiae-stock", "https://www.asiae.co.kr/list/stock"),
    ],
    # ── Tier 4: IT/기술 매체 (IT/게임 광고주) ──
    "etnews": [
        ("etnews-industry", "https://www.etnews.com/news/industry"),
        ("etnews-telecom", "https://www.etnews.com/news/telecom"),
    ],
    "dt": [
        ("dt-industry", "https://www.dt.co.kr/category/industry/"),
        ("dt-telecom", "https://www.dt.co.kr/category/telecom/"),
    ],
    "inews24": [
        ("inews-it", "https://www.inews24.com/list/it"),
        ("inews-economy", "https://www.inews24.com/list/economy"),
    ],
    # ── Tier 5: 통신/종합 ──
    "newsis": [
        ("newsis-politics", "https://www.newsis.com/politics/"),
        ("newsis-economy", "https://www.newsis.com/economy/"),
        ("newsis-society", "https://www.newsis.com/society/"),
    ],
    "nocutnews": [
        ("nocut-politics", "https://www.nocutnews.co.kr/news/list?c1=200"),
        ("nocut-economy", "https://www.nocutnews.co.kr/news/list?c1=300"),
        ("nocut-society", "https://www.nocutnews.co.kr/news/list?c1=400"),
    ],
    "newspim": [
        ("newspim-economy", "https://www.newspim.com/news/list/economy"),
        ("newspim-stock", "https://www.newspim.com/news/list/stock"),
    ],
    "dailian": [
        ("dailian-politics", "https://www.dailian.co.kr/news/list/politics"),
        ("dailian-economy", "https://www.dailian.co.kr/news/list/economy"),
    ],
    # ── Tier 6: 스포츠/엔터 (스포츠/게임/뷰티 광고주) ──
    "sportschosun": [
        ("sc-sports", "https://sports.chosun.com/"),
        ("sc-entertain", "https://sports.chosun.com/entertainment/"),
    ],
    "osen": [
        ("osen-sports", "https://www.osen.co.kr/list/sports"),
        ("osen-entertain", "https://www.osen.co.kr/list/enter"),
    ],
    "mydaily": [
        ("mydaily-entertain", "https://www.mydaily.co.kr/new_yk/ent/"),
        ("mydaily-sports", "https://www.mydaily.co.kr/new_yk/spt/"),
    ],
}

# ── 대형 커뮤니티 사이트 (GDN/AdFit 광고 밀집) ──
COMMUNITY_SITES = [
    ("dcinside-hot", "https://gall.dcinside.com/board/lists/?id=dcbest"),
    ("dcinside-hit", "https://gall.dcinside.com/board/lists/?id=hit"),
    ("clien-popular", "https://www.clien.net/service/board/park"),
    ("clien-news", "https://www.clien.net/service/board/news"),
    ("fmkorea-hot", "https://www.fmkorea.com/index.php?mid=best"),
    ("ppomppu-hot", "https://www.ppomppu.co.kr/zboard/zboard.php?id=freeboard"),
    ("ppomppu-deal", "https://www.ppomppu.co.kr/zboard/zboard.php?id=ppomppu"),
    ("ruliweb-hot", "https://bbs.ruliweb.com/best"),
    ("bobaedream-free", "https://www.bobaedream.co.kr/list?code=freeb"),
    ("bobaedream-car", "https://www.bobaedream.co.kr/list?code=strange"),
    ("theqoo-hot", "https://theqoo.net/hot"),
    ("instiz-hot", "https://www.instiz.net/pt"),
    ("mlbpark-hot", "https://mlbpark.donga.com/mp/b.php?b=bullpen"),
    ("todayhumor-best", "https://www.todayhumor.co.kr/board/list.php?table=bestofbest"),
]

# ── 주요 포털/트래픽 매체 (메인 페이지 DA 수집) ──
PORTAL_SITES = [
    ("nate-main", "https://www.nate.com/"),
    ("nate-news", "https://news.nate.com/"),
    ("nate-pann", "https://pann.nate.com/talk/today"),
    ("zum-main", "https://zum.com/"),
    ("zum-news", "https://news.zum.com/"),
    ("naver-mobile-main", "https://m.naver.com/"),
    ("daum-main", "https://www.daum.net/"),
]

# 퍼블리셔별 1개 카테고리씩만 수집 (전체 하면 너무 오래 걸림)
# 라운드로빈으로 매 실행마다 다른 카테고리 선택
def get_publisher_urls():
    """현재 시간 기반 라운드로빈으로 카테고리 선택."""
    hour = datetime.now().hour
    result = []
    for pub_name, cats in PUBLISHER_CATEGORIES.items():
        idx = hour % len(cats)
        cat_name, cat_url = cats[idx]
        result.append((cat_name, cat_url, pub_name))
    return result


# ── 페르소나별 워밍업 사이트 (쿠키 축적 → 타겟팅 광고 유도) ──
WARMUP_URLS = {
    # 10대: 게임/학원/아이돌
    "M10": ["https://www.op.gg/", "https://www.inven.co.kr/"],
    "F10": ["https://www.oliveyoung.co.kr/", "https://www.weverse.io/"],
    # 20대: 패션/테크/뷰티/식품
    "M20": ["https://www.musinsa.com/", "https://www.todayhumor.co.kr/"],
    "F20": ["https://www.oliveyoung.co.kr/", "https://www.kurly.com/"],
    # 30대: 부동산/금융/육아/인테리어
    "M30": ["https://land.naver.com/", "https://finance.naver.com/"],
    "F30": ["https://ohou.se/", "https://www.cjthemarket.com/"],
    # 40대: 금융/골프/교육/건강
    "M40": ["https://finance.naver.com/", "https://www.kbstar.com/"],
    "F40": ["https://www.ssg.com/", "https://www.gmarket.co.kr/"],
    # 50대: 건강/뉴스/홈쇼핑
    "M50": ["https://finance.naver.com/", "https://news.naver.com/"],
    "F50": ["https://www.hmall.com/", "https://www.ssg.com/"],
    # 60대: 건강/뉴스/여행
    "M60": ["https://news.naver.com/", "https://www.hanatourthai.com/"],
    "F60": ["https://www.hmall.com/", "https://www.cjthemarket.com/"],
}

# 전체 인구통계 페르소나 12개 (10~60대 남녀)
ALL_PERSONAS = ["M10", "F10", "M20", "F20", "M30", "F30", "M40", "F40", "M50", "F50", "M60", "F60"]
# 기본 타겟: 광고 집행이 활발한 20~40대
TARGET_PERSONAS = ["M20", "F20", "M30", "F30", "M40", "F40"]

ARTICLES_PER_CATEGORY = 2

# ── 페르소나별 유튜브 시드 영상 (광고가 잘 붙는 인기 영상) ──
# ── 한글 제목, 8분 이상 영상 위주 (프리롤/미드롤 광고 노출 극대화) ──
YOUTUBE_VIDEOS = {
    "M10": [  # 게임, 스포츠, 웹예능
        "https://www.youtube.com/watch?v=_qN3x6rFzJY",  # 침착맨 삼국지 1시간
        "https://www.youtube.com/watch?v=AO-JYjRPiHc",  # 피식대학 한사랑산악회
        "https://www.youtube.com/watch?v=kTfS5HAyR4s",  # 풍월량 게임 플레이
    ],
    "F10": [  # K-POP, 뷰티, 브이로그
        "https://www.youtube.com/watch?v=3FWVKu1Yhjk",  # 회사원A 브이로그
        "https://www.youtube.com/watch?v=aqBJF4MhjOk",  # 이사배 메이크업 튜토리얼
        "https://www.youtube.com/watch?v=jUH6gSz2MKU",  # 뮤비뱅크 K-POP 무대모음
    ],
    "M20": [  # IT, 경제, 자동차
        "https://www.youtube.com/watch?v=cjUawNHQJHM",  # 잇섭 IT 리뷰 (10분+)
        "https://www.youtube.com/watch?v=Lkb9IiB0e5A",  # 슈카월드 경제이야기
        "https://www.youtube.com/watch?v=OGvjsQJEoP0",  # 모트라인 자동차 리뷰
    ],
    "F20": [  # 뷰티, 먹방, 브이로그
        "https://www.youtube.com/watch?v=kPa7bsKwL-c",  # 쯔양 먹방 (10분+)
        "https://www.youtube.com/watch?v=aqBJF4MhjOk",  # 이사배 뷰티
        "https://www.youtube.com/watch?v=0pSlu2okpqM",  # 햄지 ASMR 먹방
    ],
    "M30": [  # 경제, 시사, 예능
        "https://www.youtube.com/watch?v=Lkb9IiB0e5A",  # 슈카월드 경제
        "https://www.youtube.com/watch?v=cjUawNHQJHM",  # 잇섭 IT
        "https://www.youtube.com/watch?v=AO-JYjRPiHc",  # 피식대학
    ],
    "F30": [  # 육아, 요리, 인테리어
        "https://www.youtube.com/watch?v=XhcX20SKRGA",  # 백종원 레시피 (15분+)
        "https://www.youtube.com/watch?v=3FWVKu1Yhjk",  # 일상 브이로그
        "https://www.youtube.com/watch?v=kPa7bsKwL-c",  # 쯔양 먹방
    ],
    "M40": [  # 뉴스, 시사, 골프, 경제
        "https://www.youtube.com/watch?v=8DPk7hfb7Y8",  # 한문철 블랙박스 (10분+)
        "https://www.youtube.com/watch?v=Lkb9IiB0e5A",  # 슈카월드
        "https://www.youtube.com/watch?v=OGvjsQJEoP0",  # 자동차 리뷰
    ],
    "F40": [  # 건강, 요리, 교육
        "https://www.youtube.com/watch?v=XhcX20SKRGA",  # 백종원 요리
        "https://www.youtube.com/watch?v=8DPk7hfb7Y8",  # 한문철
        "https://www.youtube.com/watch?v=3FWVKu1Yhjk",  # 일상 브이로그
    ],
    "M50": [  # 뉴스, 건강, 역사
        "https://www.youtube.com/watch?v=8DPk7hfb7Y8",  # 한문철
        "https://www.youtube.com/watch?v=Lkb9IiB0e5A",  # 슈카월드
        "https://www.youtube.com/watch?v=XhcX20SKRGA",  # 백종원
    ],
    "F50": [  # 건강, 트로트, 요리
        "https://www.youtube.com/watch?v=XhcX20SKRGA",  # 백종원 요리
        "https://www.youtube.com/watch?v=8DPk7hfb7Y8",  # 한문철
        "https://www.youtube.com/watch?v=kPa7bsKwL-c",  # 쯔양
    ],
    "M60": [  # 뉴스, 역사, 건강
        "https://www.youtube.com/watch?v=8DPk7hfb7Y8",  # 한문철
        "https://www.youtube.com/watch?v=Lkb9IiB0e5A",  # 슈카월드
        "https://www.youtube.com/watch?v=XhcX20SKRGA",  # 백종원
    ],
    "F60": [  # 건강, 요리, 생활정보
        "https://www.youtube.com/watch?v=XhcX20SKRGA",  # 백종원
        "https://www.youtube.com/watch?v=8DPk7hfb7Y8",  # 한문철
        "https://www.youtube.com/watch?v=0pSlu2okpqM",  # 햄지
    ],
}

# ── 네이버 쇼핑 검색 키워드 (스텔스) ──
NAVER_SHOPPING_KEYWORDS = [
    "삼성 갤럭시", "아이폰", "나이키 운동화", "다이슨 에어랩",
    "맥북 프로", "에어팟", "올리브영", "무신사 추천",
]

# ── 카카오 네트워크 파트너 앱 웹사이트 (AdFit/카카오모먼트 광고 수집) ──
PARTNER_APP_SITES = [
    # 오늘의집: 인테리어/라이프스타일 — Kakao AdFit + GDN 게재
    ("ohou-home", "https://ohou.se/"),
    ("ohou-store", "https://ohou.se/store"),
    ("ohou-projects", "https://ohou.se/projects"),
    # ZigZag: 패션 커머스 — Kakao AdFit 게재
    ("zigzag-home", "https://zigzag.kr/"),
    ("zigzag-ranking", "https://zigzag.kr/ranking"),
    # 티스토리: 카카오 직영 블로그 — AdFit 광고 집중
    ("tistory-home", "https://www.tistory.com/"),
    # 브런치: 카카오 콘텐츠 — AdFit 게재
    ("brunch-home", "https://brunch.co.kr/"),
    # 다음 웹툰: 카카오 직영 — 카카오모먼트 광고
    ("kakao-webtoon", "https://webtoon.kakao.com/"),
    # 카카오페이지: 카카오 직영 웹소설/웹툰 — AdFit 광고 밀도 최고
    ("kakaopage", "https://page.kakao.com/"),
]

# 카카오 광고 네트워크 URL 패턴 (파트너 앱 전용 확장)
KAKAO_AD_PATTERNS = [
    "adfit.kakao.com", "display.ad.daum.net", "t1.daumcdn.net/adfit",
    "ad.daum.net", "kakaoad.com", "kgsdk.kakao.com",
    "keywordad.kakao.com",
]


def classify_ad(url):
    """광고 URL을 네트워크별로 분류.

    youtube 패턴을 gdn보다 먼저 체크하여 YouTube 인스트림 광고를
    GDN 디스플레이와 구분한다.
    """
    for network, patterns in AD_NETWORKS.items():
        for pat in patterns:
            if pat in url:
                return network
    return "other"


async def warmup_persona(ctx, persona_code):
    """페르소나 쿠키 워밍업 (관심사 사이트 방문)."""
    urls = WARMUP_URLS.get(persona_code, [])
    if not urls:
        return

    page = await ctx.new_page()
    for url in urls[:2]:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            for _ in range(4):
                await page.evaluate("window.scrollBy(0, 400)")
                await asyncio.sleep(random.uniform(0.6, 1.2))
            await asyncio.sleep(random.uniform(1.5, 3))
        except Exception:
            pass
    await page.close()


async def surf_category(ctx, cat_name, cat_url, channel_name):
    """카테고리에서 기사 클릭 -> 광고 캡처."""
    page = await ctx.new_page()
    ads_collected = []

    try:
        await page.goto(cat_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 4))

        # 기사 링크 추출
        article_links = await page.evaluate("""
            (() => {
                const as = document.querySelectorAll('a[href]');
                const arts = [];
                for (const a of as) {
                    const h = a.href;
                    if (!h || h.includes('#') || h.includes('javascript:')) continue;
                    if (h.includes('/article/') || h.includes('/news/read') ||
                        h.includes('n.news.naver.com') || h.includes('v.daum.net/v/') ||
                        h.includes('/newsView/') || h.match(/\\/\\d{8,}/)) {
                        arts.push(h);
                    }
                }
                return [...new Set(arts)].slice(0, 10);
            })()
        """)
        await page.close()

        if not article_links:
            return ads_collected

        for art_url in article_links[:ARTICLES_PER_CATEGORY]:
            art_page = await ctx.new_page()

            async def on_resp(response, _ads=ads_collected):
                u = response.url
                if response.status == 200:
                    for pat in ALL_PATTERNS:
                        if pat in u:
                            network = classify_ad(u)
                            _ads.append({
                                "url": u[:150],
                                "network": network,
                                "channel": channel_name,
                                "source_category": cat_name,
                            })
                            break

            art_page.on("response", on_resp)

            try:
                await art_page.goto(art_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(2, 3))
                scroll_count = random.randint(6, 12)
                for i in range(scroll_count):
                    await art_page.evaluate(f"window.scrollBy(0, {random.randint(250, 450)})")
                    await asyncio.sleep(random.uniform(0.8, 1.5))
                await asyncio.sleep(random.uniform(2, 4))
            except Exception:
                pass
            finally:
                await art_page.close()

    except Exception:
        try:
            await page.close()
        except Exception:
            pass

    return ads_collected


async def surf_publisher(ctx, cat_name, cat_url, pub_name):
    """언론사 카테고리 기사면 서핑 (GDN 캡처)."""
    page = await ctx.new_page()
    ads_collected = []

    try:
        await page.goto(cat_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 4))

        # 기사 링크
        links = await page.evaluate("""
            (() => {
                const as = document.querySelectorAll('a[href]');
                const domain = window.location.hostname;
                const arts = [];
                for (const a of as) {
                    const h = a.href;
                    if (h && h.includes(domain) && h.length > 50 && !h.includes('#')) {
                        arts.push(h);
                    }
                }
                return [...new Set(arts)].slice(0, 8);
            })()
        """)
        await page.close()

        for art_url in (links or [])[:ARTICLES_PER_CATEGORY]:
            art_page = await ctx.new_page()

            async def on_resp(response, _ads=ads_collected):
                u = response.url
                if response.status == 200:
                    for pat in ALL_PATTERNS:
                        if pat in u:
                            _ads.append({
                                "url": u[:150],
                                "network": classify_ad(u),
                                "channel": f"gdn_{pub_name}",
                                "source_category": cat_name,
                            })
                            break

            art_page.on("response", on_resp)

            try:
                await art_page.goto(art_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(2, 4))
                for _ in range(10):
                    await art_page.evaluate(f"window.scrollBy(0, {random.randint(250, 450)})")
                    await asyncio.sleep(random.uniform(0.8, 1.5))
                await asyncio.sleep(random.uniform(2, 4))
            except Exception:
                pass
            finally:
                await art_page.close()

    except Exception:
        try:
            await page.close()
        except Exception:
            pass

    return ads_collected


async def surf_instagram(ctx):
    """IG 쿠키 로그인 후 피드 서핑 -> sponsored 광고 캡처."""
    ads_collected = []
    cookie_path = Path(_root) / "ig_cookies.json"
    if not cookie_path.exists():
        logger.warning("[IG] ig_cookies.json not found, skipping")
        return ads_collected

    try:
        with open(cookie_path, encoding="utf-8") as f:
            cookies = json.load(f)
        await ctx.add_cookies(cookies)
    except Exception as e:
        logger.warning(f"[IG] Cookie load failed: {str(e)[:60]}")
        return ads_collected

    page = await ctx.new_page()

    async def on_ig_resp(response, _ads=ads_collected):
        u = response.url
        if response.status == 200 and ("graphql" in u or "api/v1" in u):
            try:
                body = await response.text()
                if '"is_ad":true' in body or '"is_paid_partnership"' in body:
                    _ads.append({
                        "url": u[:150],
                        "network": "meta",
                        "channel": "instagram_feed",
                        "source_category": "ig_feed",
                    })
            except Exception:
                pass
        # 일반 meta 패턴도 잡기
        for pat in AD_NETWORKS["meta"]:
            if pat in u and response.status == 200:
                _ads.append({
                    "url": u[:150],
                    "network": "meta",
                    "channel": "instagram_feed",
                    "source_category": "ig_ad_network",
                })
                break

    page.on("response", on_ig_resp)

    try:
        logger.info("[IG] Loading feed (slow approach)...")
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
        # 소셜은 천천히 접속 (차단 방지)
        await asyncio.sleep(random.uniform(4, 6))
        for _ in range(15):
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(random.uniform(1.5, 3.0))
        await asyncio.sleep(random.uniform(3, 5))
        logger.info(f"[IG] Captured {len(ads_collected)} ad responses")
    except Exception as e:
        logger.warning(f"[IG] Error: {str(e)[:60]}")
    finally:
        await page.close()

    return ads_collected


async def surf_facebook(ctx):
    """FB 로그인 후 피드 서핑 -> 광고 캡처."""
    ads_collected = []
    page = await ctx.new_page()

    async def on_fb_resp(response, _ads=ads_collected):
        u = response.url
        if response.status == 200:
            for pat in ALL_PATTERNS:
                if pat in u:
                    _ads.append({
                        "url": u[:150],
                        "network": classify_ad(u),
                        "channel": "facebook_feed",
                        "source_category": "fb_feed",
                    })
                    break

    page.on("response", on_fb_resp)

    try:
        logger.info("[FB] Logging in (slow approach)...")
        await page.goto("https://www.facebook.com/login", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(3, 5))
        await page.fill('input[name="email"]', "01083706470")
        await asyncio.sleep(random.uniform(0.5, 1))
        await page.fill('input[name="pass"]', "pjm990101@")
        await asyncio.sleep(random.uniform(0.5, 1))
        await page.click('button[name="login"]')
        # 로그인 후 충분히 대기
        await asyncio.sleep(random.uniform(6, 10))

        # 피드 스크롤
        for _ in range(12):
            await page.evaluate("window.scrollBy(0, 500)")
            await asyncio.sleep(random.uniform(1.5, 3.0))
        await asyncio.sleep(random.uniform(3, 5))
        logger.info(f"[FB] Captured {len(ads_collected)} ad responses")
    except Exception as e:
        logger.warning(f"[FB] Error: {str(e)[:60]}")
    finally:
        await page.close()

    return ads_collected


async def surf_youtube(ctx, persona_code):
    """유튜브 급상승/인기 영상 방문 -> 프리롤/미드롤 인스트림 광고 캡처.

    1. 한국 급상승 페이지(/feed/trending)에서 영상 수집
    2. 홈페이지 추천 영상 보충
    3. 시드 영상은 fallback으로만 사용
    """
    ads_collected = []

    # 쿠키 설정 (한국 로케일)
    await ctx.add_cookies([
        {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
         "domain": ".youtube.com", "path": "/"},
        {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
         "domain": ".youtube.com", "path": "/"},
    ])

    videos = []

    # 1단계: 한국 급상승(인기) 영상 수집
    page = await ctx.new_page()
    try:
        await page.goto("https://www.youtube.com/feed/trending?gl=KR&hl=ko",
                        wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(3, 5))

        # 급상승 페이지에서 영상 링크 추출 (8분+ 우선)
        trending = await page.evaluate("""
            (() => {
                const items = document.querySelectorAll('ytd-video-renderer, ytd-expanded-shelf-contents-renderer ytd-video-renderer');
                const urls = [];
                const fallback = [];
                for (const item of items) {
                    const link = item.querySelector('a[href*="/watch?v="]');
                    if (!link) continue;
                    const h = link.href;
                    if (!h || urls.includes(h) || fallback.includes(h)) continue;
                    const badge = item.querySelector('span.ytd-thumbnail-overlay-time-status-renderer, #overlays span');
                    const durText = badge ? badge.textContent.trim() : '';
                    const parts = durText.split(':').map(Number);
                    let secs = 0;
                    if (parts.length === 3) secs = parts[0]*3600 + parts[1]*60 + parts[2];
                    else if (parts.length === 2) secs = parts[0]*60 + parts[1];
                    if (secs >= 480) { urls.push(h); }
                    else if (secs >= 120) { fallback.push(h); }
                    if (urls.length >= 20) break;
                }
                while (urls.length < 20 && fallback.length > 0) {
                    urls.push(fallback.shift());
                }
                return urls;
            })()
        """)
        for r in (trending or []):
            if r not in videos:
                videos.append(r)
        logger.info(f"[YT] Trending: {len(trending or [])} videos found")
    except Exception as e:
        logger.debug(f"[YT] Trending page failed: {str(e)[:60]}")
    finally:
        await page.close()

    # 2단계: 홈페이지 추천 영상으로 보충
    page = await ctx.new_page()
    try:
        await page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(random.uniform(3, 5))

        recommended = await page.evaluate("""
            (() => {
                const items = document.querySelectorAll('ytd-rich-item-renderer, ytd-video-renderer');
                const urls = [];
                const fallback = [];
                for (const item of items) {
                    const link = item.querySelector('a[href*="/watch?v="]');
                    if (!link) continue;
                    const h = link.href;
                    if (!h || urls.includes(h) || fallback.includes(h)) continue;
                    const badge = item.querySelector('span.ytd-thumbnail-overlay-time-status-renderer, #overlays span');
                    const durText = badge ? badge.textContent.trim() : '';
                    const parts = durText.split(':').map(Number);
                    let secs = 0;
                    if (parts.length === 3) secs = parts[0]*3600 + parts[1]*60 + parts[2];
                    else if (parts.length === 2) secs = parts[0]*60 + parts[1];
                    if (secs >= 480) { urls.push(h); }
                    else if (secs >= 120) { fallback.push(h); }
                    if (urls.length >= 15) break;
                }
                while (urls.length < 15 && fallback.length > 0) {
                    urls.push(fallback.shift());
                }
                return urls;
            })()
        """)
        for r in (recommended or []):
            if r not in videos:
                videos.append(r)
        logger.info(f"[YT] Home recommended: {len(recommended or [])} videos")
    except Exception as e:
        logger.debug(f"[YT] Home page failed: {str(e)[:60]}")
    finally:
        await page.close()

    # 3단계: 시드 영상으로 최소 보장 (급상승/홈이 실패한 경우)
    seed = YOUTUBE_VIDEOS.get(persona_code, YOUTUBE_VIDEOS.get("M30", []))
    for s in seed:
        if s not in videos:
            videos.append(s)

    random.shuffle(videos)

    # 영상별 광고 캡처 (최대 15개 영상)
    for i, video_url in enumerate(videos[:15]):
        vpage = await ctx.new_page()

        async def on_yt_resp(response, _ads=ads_collected, _url=video_url):
            u = response.url
            if response.status != 200:
                return
            # YouTube 전용 광고 패턴 (인스트림)
            for pat in AD_NETWORKS.get("youtube", []):
                if pat in u:
                    _ads.append({
                        "url": u[:150],
                        "network": "youtube",
                        "channel": "youtube_instream",
                        "source_category": f"yt_video_{i}",
                    })
                    return
            # GDN 패턴도 YouTube 페이지에서 나오면 youtube로 분류
            if "youtube.com" in _url:
                for pat in ["doubleclick.net/pagead", "googleads.g.doubleclick"]:
                    if pat in u:
                        _ads.append({
                            "url": u[:150],
                            "network": "youtube",
                            "channel": "youtube_instream",
                            "source_category": f"yt_video_{i}",
                        })
                        return

        vpage.on("response", on_yt_resp)

        try:
            await vpage.goto(video_url, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(random.uniform(2, 3))

            # 뮤트 + 재생
            await vpage.evaluate("""() => {
                const v = document.querySelector('video');
                if (v) { v.muted = true; v.play().catch(() => {}); }
                const btn = document.querySelector('.ytp-large-play-button, .ytp-play-button');
                if (btn) btn.click();
            }""")

            # 광고 대기 (30~40초 — 프리롤+미드롤 캡처)
            for _ in range(8):
                await asyncio.sleep(random.uniform(4, 5))

            logger.debug(f"[YT] Video {i+1}/{len(videos[:15])}: {video_url[:60]} -> {len(ads_collected)} total")
        except Exception as e:
            logger.debug(f"[YT] Video failed: {str(e)[:60]}")
        finally:
            await vpage.close()

    logger.info(f"[YT] Captured {len(ads_collected)} YouTube ad signals")
    return ads_collected


async def surf_naver_shopping(ctx, persona_code):
    """네이버 쇼핑 검색 → ad.search.naver.com 광고 캡처."""
    ads_collected = []
    keywords = list(NAVER_SHOPPING_KEYWORDS)
    random.shuffle(keywords)

    for kw in keywords[:4]:
        page = await ctx.new_page()

        async def on_shop_resp(response, _ads=ads_collected, _kw=kw):
            u = response.url
            if response.status != 200:
                return
            for pat in AD_NETWORKS.get("naver_shopping", []):
                if pat in u:
                    _ads.append({
                        "url": u[:150],
                        "network": "naver_shopping",
                        "channel": "naver_shopping_search",
                        "source_category": f"shopping_{_kw}",
                    })
                    return

        page.on("response", on_shop_resp)

        try:
            from urllib.parse import quote
            url = f"https://m.search.naver.com/search.naver?where=shopping&query={quote(kw)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(random.uniform(2, 3))
            for _ in range(4):
                await page.evaluate(f"window.scrollBy(0, {random.randint(300, 500)})")
                await asyncio.sleep(random.uniform(0.8, 1.5))
            await asyncio.sleep(random.uniform(1, 2))
        except Exception:
            pass
        finally:
            await page.close()

    logger.info(f"[SHOP] Captured {len(ads_collected)} shopping ad signals")
    return ads_collected


async def surf_partner_apps(ctx, persona_code):
    """카카오 네트워크 파트너 앱 웹사이트 서핑 -> AdFit/카카오모먼트 광고 캡처."""
    ads_collected = []

    for site_name, site_url in PARTNER_APP_SITES:
        page = await ctx.new_page()

        async def on_partner_resp(response, _ads=ads_collected, _site=site_name):
            u = response.url
            if response.status != 200:
                return
            # 카카오 광고 네트워크 패턴 우선 체크
            for pat in KAKAO_AD_PATTERNS:
                if pat in u:
                    _ads.append({
                        "url": u[:150],
                        "network": "kakao",
                        "channel": f"kakao_partner_{_site}",
                        "source_category": f"partner_{_site}",
                    })
                    return
            # GDN 패턴도 체크 (파트너 앱에서 GDN 광고도 나옴)
            for pat in AD_NETWORKS.get("gdn", []):
                if pat in u:
                    _ads.append({
                        "url": u[:150],
                        "network": "gdn",
                        "channel": f"gdn_partner_{_site}",
                        "source_category": f"partner_{_site}",
                    })
                    return

        page.on("response", on_partner_resp)

        try:
            await page.goto(site_url, wait_until="domcontentloaded", timeout=15000)
            await asyncio.sleep(random.uniform(2, 4))
            for _ in range(8):
                await page.evaluate(f"window.scrollBy(0, {random.randint(250, 450)})")
                await asyncio.sleep(random.uniform(0.8, 1.5))
            await asyncio.sleep(random.uniform(1, 2))
        except Exception:
            pass
        finally:
            await page.close()

    logger.info(f"[PARTNER] Captured {len(ads_collected)} partner app ad signals")
    return ads_collected


async def surf_community(ctx, site_name, site_url):
    """커뮤니티 사이트 서핑 -> GDN/AdFit 광고 캡처."""
    ads_collected = []
    page = await ctx.new_page()

    async def on_resp(response, _ads=ads_collected, _site=site_name):
        u = response.url
        if response.status != 200:
            return
        for pat in ALL_PATTERNS:
            if pat in u:
                _ads.append({
                    "url": u[:150],
                    "network": classify_ad(u),
                    "channel": f"community_{_site}",
                    "source_category": f"community_{_site}",
                })
                break

    page.on("response", on_resp)

    try:
        await page.goto(site_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 4))
        # 게시글 목록 스크롤
        for _ in range(10):
            await page.evaluate(f"window.scrollBy(0, {random.randint(250, 450)})")
            await asyncio.sleep(random.uniform(0.8, 1.5))
        await asyncio.sleep(random.uniform(1, 2))

        # 게시글 1개 클릭하여 기사면 광고 수집
        article_links = await page.evaluate("""
            (() => {
                const as = document.querySelectorAll('a[href]');
                const arts = [];
                for (const a of as) {
                    const h = a.href;
                    if (!h || h.includes('#') || h.includes('javascript:')) continue;
                    if (h.length > 40) arts.push(h);
                    if (arts.length >= 5) break;
                }
                return arts;
            })()
        """)
        await page.close()

        if article_links:
            for art_url in article_links[:1]:
                art_page = await ctx.new_page()

                async def on_art_resp(response, _ads2=ads_collected, _s=site_name):
                    u2 = response.url
                    if response.status == 200:
                        for pat in ALL_PATTERNS:
                            if pat in u2:
                                _ads2.append({
                                    "url": u2[:150],
                                    "network": classify_ad(u2),
                                    "channel": f"community_{_s}",
                                    "source_category": f"community_{_s}_article",
                                })
                                break

                art_page.on("response", on_art_resp)
                try:
                    await art_page.goto(art_url, wait_until="domcontentloaded", timeout=15000)
                    await asyncio.sleep(random.uniform(2, 3))
                    for _ in range(6):
                        await art_page.evaluate(f"window.scrollBy(0, {random.randint(250, 450)})")
                        await asyncio.sleep(random.uniform(0.8, 1.5))
                except Exception:
                    pass
                finally:
                    await art_page.close()

    except Exception:
        try:
            await page.close()
        except Exception:
            pass

    return ads_collected


async def surf_portal(ctx, site_name, site_url):
    """포털/트래픽 매체 메인 + 기사면 DA 광고 수집."""
    ads_collected = []
    page = await ctx.new_page()

    async def on_resp(response, _ads=ads_collected, _site=site_name):
        u = response.url
        if response.status != 200:
            return
        for pat in ALL_PATTERNS:
            if pat in u:
                _ads.append({
                    "url": u[:150],
                    "network": classify_ad(u),
                    "channel": f"portal_{_site}",
                    "source_category": f"portal_{_site}",
                })
                break

    page.on("response", on_resp)

    try:
        await page.goto(site_url, wait_until="domcontentloaded", timeout=15000)
        await asyncio.sleep(random.uniform(2, 4))
        for _ in range(12):
            await page.evaluate(f"window.scrollBy(0, {random.randint(250, 450)})")
            await asyncio.sleep(random.uniform(0.8, 1.5))
        await asyncio.sleep(random.uniform(1, 2))

        # 기사/콘텐츠 링크 추출 → 기사면 진입
        article_links = await page.evaluate("""
            (() => {
                const as = document.querySelectorAll('a[href]');
                const arts = [];
                for (const a of as) {
                    const h = a.href;
                    if (!h || h.includes('#') || h.includes('javascript:')) continue;
                    if (h.length > 40) arts.push(h);
                    if (arts.length >= 5) break;
                }
                return arts;
            })()
        """)
        await page.close()

        # 기사면 최대 3개 진입하여 광고 수집
        for art_url in (article_links or [])[:3]:
            art_page = await ctx.new_page()

            async def on_art_resp(response, _ads2=ads_collected, _s=site_name):
                u2 = response.url
                if response.status == 200:
                    for pat in ALL_PATTERNS:
                        if pat in u2:
                            _ads2.append({
                                "url": u2[:150],
                                "network": classify_ad(u2),
                                "channel": f"portal_{_s}",
                                "source_category": f"portal_{_s}_article",
                            })
                            break

            art_page.on("response", on_art_resp)
            try:
                await art_page.goto(art_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(random.uniform(2, 3))
                for _ in range(8):
                    await art_page.evaluate(f"window.scrollBy(0, {random.randint(250, 450)})")
                    await asyncio.sleep(random.uniform(0.8, 1.5))
            except Exception:
                pass
            finally:
                await art_page.close()

    except Exception:
        try:
            await page.close()
        except Exception:
            pass

    return ads_collected


async def save_ads_to_db(ads, persona_code):
    """수집된 광고를 serpapi_ads 테이블에 저장."""
    if not ads:
        return 0

    from database import async_session
    from sqlalchemy import text

    saved = 0
    async with async_session() as session:
        try:
            for ad in ads:
                url = ad.get("url", "")
                if not url:
                    continue
                await session.execute(
                    text("""
                        INSERT INTO serpapi_ads
                        (advertiser_name, format, target_domain, extra_data)
                        VALUES (:name, :fmt, :domain, :extra)
                    """),
                    {
                        "name": f"stealth_{ad['network']}_{ad.get('source_category', '')}",
                        "fmt": "display",
                        "domain": url[:200],
                        "extra": json.dumps({
                            "network": ad["network"],
                            "channel": ad.get("channel", ""),
                            "persona": persona_code,
                            "source": ad.get("source_category", ""),
                        }, ensure_ascii=False),
                    },
                )
                saved += 1
            await session.commit()
        except Exception as e:
            logger.error(f"[stealth_surf] DB save failed: {e}")
            await session.rollback()
    return saved


async def run_persona(persona_code, include_social=False):
    """한 페르소나로 전체 서핑."""
    persona = PERSONAS[persona_code]
    device = get_device_for_persona(persona)
    t0 = time.time()

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
        )
        try:
            ctx = await browser.new_context(
                viewport={"width": device.viewport_width, "height": device.viewport_height},
                user_agent=device.user_agent,
                is_mobile=device.is_mobile,
                has_touch=device.has_touch,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
            )

            stealth = Stealth(navigator_languages_override=("ko-KR", "ko"), navigator_platform_override="Win32")
            for s in list(stealth.enabled_scripts):
                await ctx.add_init_script(s)

            all_ads = []

            # 1. 쿠키 워밍업
            logger.info(f"[{persona_code}] Warming up cookies...")
            await warmup_persona(ctx, persona_code)

            # 2. 네이버/다음 뉴스 기사
            for cat_name, cat_url in NEWS_CATEGORIES:
                ads = await surf_category(ctx, cat_name, cat_url, "news_surf")
                all_ads.extend(ads)
                logger.info(f"[{persona_code}] {cat_name}: {len(ads)} ads")

            # 3. 언론사 카테고리별 기사면 (GDN)
            pub_urls = get_publisher_urls()
            for cat_name, cat_url, pub_name in pub_urls:
                ads = await surf_publisher(ctx, cat_name, cat_url, pub_name)
                all_ads.extend(ads)
                logger.info(f"[{persona_code}] {cat_name}: {len(ads)} ads")

            # 4. 유튜브 인스트림 광고
            yt_ads = await surf_youtube(ctx, persona_code)
            all_ads.extend(yt_ads)
            logger.info(f"[{persona_code}] YouTube: {len(yt_ads)} ads")

            # 5. 네이버 쇼핑 검색 광고
            shop_ads = await surf_naver_shopping(ctx, persona_code)
            all_ads.extend(shop_ads)
            logger.info(f"[{persona_code}] Shopping: {len(shop_ads)} ads")

            # 6. 카카오 파트너 앱 (오늘의집/ZigZag/티스토리/브런치/웹툰)
            partner_ads = await surf_partner_apps(ctx, persona_code)
            all_ads.extend(partner_ads)
            logger.info(f"[{persona_code}] Partner apps: {len(partner_ads)} ads")

            # 7. 대형 커뮤니티 (GDN/AdFit 밀집)
            for site_name, site_url in COMMUNITY_SITES:
                try:
                    comm_ads = await surf_community(ctx, site_name, site_url)
                    all_ads.extend(comm_ads)
                    if comm_ads:
                        logger.info(f"[{persona_code}] {site_name}: {len(comm_ads)} ads")
                except Exception:
                    pass

            # 8. 포털/트래픽 매체 (네이트/ZUM 등 메인DA)
            for site_name, site_url in PORTAL_SITES:
                try:
                    portal_ads = await surf_portal(ctx, site_name, site_url)
                    all_ads.extend(portal_ads)
                    if portal_ads:
                        logger.info(f"[{persona_code}] {site_name}: {len(portal_ads)} ads")
                except Exception:
                    pass

            # 9. 소셜 (옵션)
            if include_social:
                ig_ads = await surf_instagram(ctx)
                all_ads.extend(ig_ads)
                fb_ads = await surf_facebook(ctx)
                all_ads.extend(fb_ads)

        finally:
            await browser.close()
    finally:
        await pw.stop()

    # 네트워크별 집계
    by_network = {}
    for ad in all_ads:
        net = ad["network"]
        by_network[net] = by_network.get(net, 0) + 1

    elapsed = round(time.time() - t0, 1)

    # DB 저장
    saved = await save_ads_to_db(all_ads, persona_code)

    logger.info(
        f"[{persona_code}] Done: {len(all_ads)} ads ({elapsed}s) | "
        f"YT:{by_network.get('youtube',0)} GDN:{by_network.get('gdn',0)} "
        f"Naver:{by_network.get('naver',0)} Shop:{by_network.get('naver_shopping',0)} "
        f"Kakao:{by_network.get('kakao',0)} Meta:{by_network.get('meta',0)} | "
        f"Saved: {saved}"
    )

    return {
        "persona": persona_code,
        "total": len(all_ads),
        "by_network": by_network,
        "elapsed": elapsed,
        "saved": saved,
    }


async def main():
    # CLI 인자 파싱
    args = sys.argv[1:]
    include_social = "--social" in args
    use_all = "--all" in args
    persona_args = [a for a in args if a in ALL_PERSONAS]

    if persona_args:
        run_personas = persona_args
    elif use_all:
        run_personas = ALL_PERSONAS
    else:
        run_personas = TARGET_PERSONAS

    logger.info("=" * 60)
    logger.info("Multi-Persona Stealth Ad Collection")
    logger.info(f"Personas: {run_personas}")
    logger.info(f"Social: {'ON' if include_social else 'OFF'}")
    logger.info(f"Publishers: {len(PUBLISHER_CATEGORIES)} ({sum(len(v) for v in PUBLISHER_CATEGORIES.values())} categories)")
    logger.info("=" * 60)

    results = []
    for code in run_personas:
        logger.info(f"\n--- Persona: {code} ({PERSONAS[code].description}) ---")
        r = await run_persona(code, include_social=include_social)
        results.append(r)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"{'Persona':<8} {'Total':>6} {'YT':>4} {'GDN':>5} {'Naver':>6} {'Shop':>5} {'Kakao':>6} {'Meta':>5} {'Time':>6}")
    logger.info("-" * 50)

    grand_total = 0
    for r in results:
        bn = r["by_network"]
        logger.info(
            f"{r['persona']:<8} {r['total']:>6} {bn.get('youtube',0):>4} {bn.get('gdn',0):>5} "
            f"{bn.get('naver',0):>6} {bn.get('naver_shopping',0):>5} "
            f"{bn.get('kakao',0):>6} {bn.get('meta',0):>5} "
            f"{r['elapsed']:>5.0f}s"
        )
        grand_total += r["total"]

    logger.info(f"\nGrand total: {grand_total} ad responses from {len(results)} personas")
    logger.info(f"Total saved to DB: {sum(r['saved'] for r in results)}")


if __name__ == "__main__":
    asyncio.run(main())
