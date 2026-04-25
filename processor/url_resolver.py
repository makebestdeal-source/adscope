"""광고주명으로 공식 사이트를 검색하여 URL을 자동 매칭하는 유틸리티.

라이브러리 크롤러(Meta, YouTube, TikTok 등)에서 광고주 URL이
누락되었을 때, 네이버 검색으로 공식사이트를 찾아 폴백 URL로 사용.
"""

import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, quote

import httpx
from loguru import logger

# ── 광고 인프라/플랫폼 도메인 (공식 사이트로 인정 안 함) ──
EXCLUDE_DOMAINS = {
    # 검색엔진/포탈
    "naver.com", "google.com", "google.co.kr", "daum.net", "bing.com",
    "search.naver.com", "m.search.naver.com",
    # 소셜/영상
    "youtube.com", "youtu.be", "instagram.com", "facebook.com", "fb.com",
    "tiktok.com", "twitter.com", "x.com", "threads.net",
    # 광고 인프라
    "adstransparency.google.com", "ader.naver.com", "tr.ad.daum.net",
    "ads.tiktok.com", "googleads.g.doubleclick.net",
    # 플랫폼/마켓
    "smartstore.naver.com", "brand.naver.com", "blog.naver.com",
    "cafe.naver.com", "post.naver.com", "tv.naver.com",
    "shopping.naver.com", "search.shopping.naver.com",
    "m.shopping.naver.com", "msearch.shopping.naver.com",
    "coupang.com", "gmarket.co.kr", "11st.co.kr", "auction.co.kr",
    # 카카오 서비스
    "pf.kakao.com", "kakao.com", "kakaocorp.com",
    "page.kakao.com", "story.kakao.com", "talk.kakao.com",
    # 위키/뉴스/커뮤니티
    "wikipedia.org", "namu.wiki", "namuwiki.kr",
    "news.naver.com", "entertain.naver.com", "sports.naver.com",
    "dict.naver.com", "terms.naver.com", "kin.naver.com",
    # 앱 마켓
    "play.google.com", "apps.apple.com",
    # 기타 인프라
    "navercorp.com",
    # 채용/취업 사이트
    "saramin.co.kr", "jobkorea.co.kr", "wanted.co.kr",
    # 리뷰/비교 사이트
    "cnet.com", "pcmag.com",
    # TVCF 관련 (로그인/리다이렉트)
    "crefe.me", "tvcf.co.kr", "router.tvcf.co.kr",
    # 뉴스/미디어 포탈
    "heraldcorp.com", "biz.heraldcorp.com", "hani.co.kr", "chosun.com",
    "donga.com", "joins.com", "joongang.co.kr", "mk.co.kr", "hankyung.com",
}

EXCLUDE_PATTERNS = [
    "naver.com", "daum.net", "google.", "doubleclick",
    "wikipedia.", "namu.wiki", "tistory.com", "brunch.co.kr",
]

FOREIGN_TLDS = {".jp", ".cn", ".tw", ".vn", ".th", ".ru", ".de", ".fr", ".it", ".es"}

MIN_SEARCH_LEN = 2
MAX_SEARCH_LEN = 40

# ── 캐시 ──
_CACHE_FILE = Path(__file__).parent / ".url_cache.json"
_mem_cache: dict[str, str | None] = {}
_cache_loaded = False


def _load_cache():
    global _mem_cache, _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    if _CACHE_FILE.exists():
        try:
            data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            _mem_cache.update(data)
            logger.debug(f"URL cache loaded: {len(_mem_cache)} entries")
        except Exception:
            pass


def _save_cache():
    try:
        _CACHE_FILE.write_text(
            json.dumps(_mem_cache, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    except Exception:
        pass


def _is_excluded_domain(domain: str) -> bool:
    if not domain:
        return True
    domain = domain.lower().lstrip("www.")
    if domain in EXCLUDE_DOMAINS:
        return True
    for pat in EXCLUDE_PATTERNS:
        if pat in domain:
            return True
    for tld in FOREIGN_TLDS:
        if domain.endswith(tld):
            return True
    return False


def _extract_clean_domain(url: str) -> str | None:
    try:
        if "://" not in url:
            url = f"https://{url}"
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain if domain and "." in domain else None
    except Exception:
        return None


async def search_naver(client: httpx.AsyncClient, query: str) -> str | None:
    """네이버 검색으로 광고주 공식사이트 URL 추출."""
    search_url = f"https://search.naver.com/search.naver?query={quote(query + ' 공식사이트')}"

    try:
        from bs4 import BeautifulSoup

        resp = await client.get(
            search_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        site_candidates = []

        # Strategy 1: 사이트 섹션 링크
        for a in soup.select("a.link_tit, a.api_txt_lines, a.link_name"):
            href = a.get("href", "")
            if href and "://" in href:
                domain = _extract_clean_domain(href)
                if domain and not _is_excluded_domain(domain):
                    site_candidates.append(href)

        # Strategy 2: 일반 검색 결과 (메인 페이지만)
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href or "://" not in href:
                continue
            domain = _extract_clean_domain(href)
            if not domain or _is_excluded_domain(domain):
                continue
            parsed = urlparse(href)
            path = parsed.path.rstrip("/")
            if not path or path == "/" or len(path.split("/")) <= 2:
                site_candidates.append(href)

        # Strategy 3: "공식 사이트" / "바로가기" 텍스트 링크
        for a in soup.find_all(
            "a", string=re.compile(r"(공식|사이트|홈페이지|바로가기|공식 사이트)")
        ):
            href = a.get("href", "")
            if href and "://" in href:
                domain = _extract_clean_domain(href)
                if domain and not _is_excluded_domain(domain):
                    return f"https://{domain}"

        if site_candidates:
            domain_counts: dict[str, int] = {}
            for url in site_candidates:
                d = _extract_clean_domain(url)
                if d and not _is_excluded_domain(d):
                    domain_counts[d] = domain_counts.get(d, 0) + 1

            if domain_counts:
                best = max(domain_counts, key=lambda d: domain_counts[d])
                return f"https://{best}"

        return None

    except (httpx.TimeoutException, httpx.ConnectError, Exception) as e:
        logger.debug(f"Search error for '{query}': {str(e)[:80]}")
        return None


async def resolve_advertiser_url(
    advertiser_name: str | None,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """광고주명으로 공식 사이트 URL 검색 (캐시 우선)."""
    if not advertiser_name or not advertiser_name.strip():
        return None

    name = advertiser_name.strip()
    if len(name) < MIN_SEARCH_LEN or len(name) > MAX_SEARCH_LEN:
        return None

    _load_cache()

    # 캐시 확인
    if name in _mem_cache:
        return _mem_cache[name]

    # 네이버 검색
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)

    try:
        result = await search_naver(client, name)
        _mem_cache[name] = result
        _save_cache()

        if result:
            logger.info(f"URL resolved: {name} -> {result}")
        return result
    finally:
        if own_client:
            await client.aclose()


async def resolve_urls_batch(
    advertiser_names: list[str],
    client: httpx.AsyncClient | None = None,
) -> dict[str, str | None]:
    """여러 광고주명 배치 검색 (5개 동시, 1.5초 간격)."""
    _load_cache()

    results: dict[str, str | None] = {}
    to_search: list[str] = []

    # 캐시에서 먼저 확인
    for name in set(advertiser_names):
        name = name.strip()
        if not name or len(name) < MIN_SEARCH_LEN or len(name) > MAX_SEARCH_LEN:
            continue
        if name in _mem_cache:
            results[name] = _mem_cache[name]
        else:
            to_search.append(name)

    if not to_search:
        return results

    logger.info(f"URL resolve: {len(to_search)} advertisers to search (cache hit: {len(results)})")

    BATCH_SIZE = 5
    DELAY = 1.5

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)

    try:
        for i in range(0, len(to_search), BATCH_SIZE):
            batch = to_search[i : i + BATCH_SIZE]
            search_tasks = [search_naver(client, name) for name in batch]
            search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            for name, result in zip(batch, search_results):
                if isinstance(result, Exception):
                    result = None
                _mem_cache[name] = result
                results[name] = result
                if result:
                    logger.info(f"  [+] {name} -> {result}")

            if i + BATCH_SIZE < len(to_search):
                await asyncio.sleep(DELAY)

        _save_cache()
    finally:
        if own_client:
            await client.aclose()

    found = sum(1 for v in results.values() if v)
    logger.info(f"URL resolve done: {found}/{len(results)} found")
    return results
