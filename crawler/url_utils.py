"""URL 유틸리티 — 도메인 추출 및 광고 리다이렉트 URL 해석.

각 크롤러에서 중복 구현되던 URL 파싱/해석 로직을 단일 모듈로 통합.
"""
from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

try:
    import requests as _requests
    _HTTP_SESSION = _requests.Session()
    _HTTP_SESSION.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    _HTTP_SESSION.max_redirects = 10
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


# 리다이렉트 URL 해석 시 실제 목적지를 담고 있는 파라미터 키 (우선순위 순)
_REDIRECT_PARAM_KEYS = ("r", "u", "url", "adurl", "eu", "ru", "target", "lp", "landing", "next", "redirect")

# 광고 트래킹/리다이렉트 도메인 (HTTP 추적이 필요한 호스트)
_TRACKING_HOSTS = (
    "adcr.naver.com", "siape.veta.naver.com", "ad.search.naver.com",
    "l.facebook.com", "lm.facebook.com", "l.instagram.com",
    "ad.daum.net", "track.kakao.com", "tr.ad.daum.net",
    "doubleclick.net", "googleadservices.com", "ad.doubleclick.net",
    "tivan.naver.com", "ader.naver.com",
)

# 네이버 리다이렉트 호스트
_NAVER_REDIRECT_HOSTS = ("adcr.naver.com", "siape.veta.naver.com", "ad.search.naver.com")

# Meta(Facebook/Instagram) 리다이렉트 호스트
_META_REDIRECT_HOSTS = (
    "l.facebook.com", "lm.facebook.com",
    "l.instagram.com",
)


def extract_domain(url: str | None) -> str | None:
    """URL에서 netloc(호스트) 추출. 실패 시 None."""
    if not url:
        return None
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None


def _decode_param(value: str) -> str:
    """이중 인코딩된 URL 파라미터를 안전하게 디코딩."""
    candidate = unquote(value).strip()
    if "%" in candidate:
        candidate = unquote(candidate).strip()
    return candidate


def resolve_redirect_url(url: str | None) -> str | None:
    """광고 트래킹/리다이렉트 URL에서 실제 목적지 URL을 추출.

    지원 패턴:
    - 네이버: adcr.naver.com, siape.veta.naver.com, ad.search.naver.com
    - Meta: l.facebook.com/l.php?u=, l.instagram.com, instagram.com/away
    - 카카오/범용: ?url=, ?adurl=, ?ru=, ?eu= 등

    파라미터가 없거나 해석 불가 시 원본 URL 반환.
    """
    if not url:
        return None
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()

        # 리다이렉트 호스트인지 확인
        is_redirect_host = (
            any(h in host for h in _NAVER_REDIRECT_HOSTS)
            or any(h in host for h in _META_REDIRECT_HOSTS)
        )

        if not is_redirect_host:
            # 범용 쿼리 파라미터 시도
            query = parse_qs(parsed.query)
            for key in _REDIRECT_PARAM_KEYS:
                vals = query.get(key)
                if not vals:
                    continue
                candidate = _decode_param(vals[0])
                if candidate.startswith(("http://", "https://")):
                    return candidate
            return url

        query = parse_qs(parsed.query)
        for key in _REDIRECT_PARAM_KEYS:
            vals = query.get(key)
            if not vals:
                continue
            candidate = _decode_param(vals[0])
            if candidate.startswith(("http://", "https://")):
                return candidate

        return url
    except Exception:
        return url


# ── 프로세스 단위 리다이렉트 캐시 ──
_REDIRECT_CACHE: dict[str, str] = {}


def is_tracking_url(url: str | None) -> bool:
    """URL이 광고 트래킹/리다이렉트 도메인인지 확인."""
    if not url:
        return False
    try:
        host = urlparse(url).netloc.lower()
        return any(h in host for h in _TRACKING_HOSTS)
    except Exception:
        return False


def resolve_via_http(url: str | None, timeout: int = 5) -> str | None:
    """실제 HTTP HEAD 요청으로 리다이렉트 체인을 추적하여 최종 URL 반환.

    - 캐시 포함 (프로세스 단위) — 동일 URL 반복 호출 시 HTTP 요청 없음
    - requests 미설치 시 정적 파라미터 파싱(resolve_redirect_url)으로 fallback
    - 실패 시 원본 URL 반환 (None 반환 없음)

    사용처: 트래킹 URL(tivan.naver.com, l.facebook.com 등)을 실제 광고주 도메인으로 해석.
    """
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return url

    # 캐시 히트
    if url in _REDIRECT_CACHE:
        return _REDIRECT_CACHE[url]

    if _HAS_REQUESTS:
        try:
            r = _HTTP_SESSION.head(url, allow_redirects=True, timeout=timeout)
            final = r.url
            # GET fallback: HEAD가 405 반환하는 서버 대응
            if r.status_code in (405, 501) or final == url:
                r2 = _HTTP_SESSION.get(url, allow_redirects=True, timeout=timeout, stream=True)
                r2.close()
                final = r2.url
            _REDIRECT_CACHE[url] = final
            return final
        except Exception:
            pass

    # fallback: 정적 파라미터 파싱
    static = resolve_redirect_url(url)
    result = static if static else url
    _REDIRECT_CACHE[url] = result
    return result
