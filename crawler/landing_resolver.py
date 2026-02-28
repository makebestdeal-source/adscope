"""광고 랜딩 페이지에서 광고주 정보 추출 유틸리티.

모든 매체 공용 — 광고 URL을 새 탭에서 열어
페이지 타이틀, og:site_name, 푸터, 도메인 등에서 광고주명 파악.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import BrowserContext

# 광고 인프라 도메인 (랜딩이 아닌 리다이렉터)
_INFRA_HOSTS = {
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "google.com", "google.co.kr", "gstatic.com", "googleapis.com",
    "googletagmanager.com", "google-analytics.com",
    "facebook.com", "facebook.net", "fbcdn.net",
    "youtube.com", "youtu.be", "t.co", "bit.ly",
}

# 랜딩 페이지에서 광고주 정보 추출하는 JS
_EXTRACT_JS = """() => {
    const getMeta = (attr, val) => {
        const el = document.querySelector(`meta[${attr}="${val}"]`);
        return el ? (el.content || '').trim() : null;
    };

    // og:site_name이 가장 정확한 브랜드명
    const siteName = getMeta('property', 'og:site_name')
                  || getMeta('name', 'og:site_name');
    const ogTitle = getMeta('property', 'og:title');
    const desc = getMeta('property', 'og:description')
              || getMeta('name', 'description');
    const author = getMeta('name', 'author');
    const title = document.title || '';

    // 푸터에서 회사명/저작권 추출
    let footerText = null;
    const footer = document.querySelector('footer')
                || document.querySelector('[class*="footer"]')
                || document.querySelector('[id*="footer"]');
    if (footer) {
        footerText = (footer.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 500);
    }

    // 저작권 텍스트 패턴 검색
    let copyright = null;
    const bodyText = document.body ? document.body.innerText : '';
    const cpMatch = bodyText.match(/(?:©|ⓒ|Copyright|저작권)\\s*\\d{0,4}\\s*([^.\\n]{2,50})/i);
    if (cpMatch) copyright = cpMatch[1].trim();

    return {
        site_name: siteName,
        og_title: ogTitle ? ogTitle.slice(0, 200) : null,
        description: desc ? desc.slice(0, 300) : null,
        author: author,
        title: title.slice(0, 200),
        footer_text: footerText,
        copyright: copyright,
        url: location.href,
    };
}"""


def _is_infra_host(host: str) -> bool:
    """광고 인프라 도메인인지 확인."""
    h = host.lower()
    return any(infra in h for infra in _INFRA_HOSTS)


def _clean_brand(raw: str | None) -> str | None:
    """브랜드명 정제 — 너무 길거나 의미없는 것 필터."""
    if not raw:
        return None
    s = raw.strip()
    # 너무 짧거나 너무 긴 건 스킵
    if len(s) < 2 or len(s) > 60:
        return None
    # URL 형태는 스킵
    if s.startswith("http"):
        return None
    return s


async def resolve_landing(
    context: BrowserContext,
    url: str,
    timeout_ms: int = 8000,
) -> dict | None:
    """광고 URL을 새 탭에서 열어 광고주 정보 추출.

    Returns:
        {
            "advertiser_name": "브랜드명",
            "landing_url": "최종 URL",
            "landing_domain": "example.com",
            "og_title": "...",
            "description": "...",
            "source": "landing_page",
        }
    """
    if not url or not url.startswith("http"):
        return None

    page = None
    try:
        page = await context.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # 리다이렉트 후 최종 URL
        final_url = page.url
        final_domain = urlparse(final_url).netloc.lower().removeprefix("www.")

        # 인프라 도메인에 머물면 실패 (리다이렉트 안됨)
        if _is_infra_host(final_domain):
            return None

        # 페이지 로딩 약간 대기
        await page.wait_for_timeout(1500)

        info = await page.evaluate(_EXTRACT_JS)
        if not info:
            return None

        # 광고주명 우선순위: og:site_name > copyright > author > 도메인
        advertiser = (
            _clean_brand(info.get("site_name"))
            or _clean_brand(info.get("copyright"))
            or _clean_brand(info.get("author"))
        )
        if not advertiser:
            # 도메인에서 core 부분 추출 (예: coupang.com → coupang)
            advertiser = final_domain

        return {
            "advertiser_name": advertiser,
            "landing_url": final_url,
            "landing_domain": final_domain,
            "og_title": info.get("og_title"),
            "description": info.get("description"),
            "page_title": info.get("title"),
            "footer_text": info.get("footer_text"),
            "source": "landing_page",
        }

    except Exception as exc:
        logger.debug(f"[landing_resolver] 랜딩 해석 실패 {url[:80]}: {exc}")
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def resolve_landings_batch(
    context: BrowserContext,
    ads: list[dict],
    max_resolve: int = 10,
    timeout_ms: int = 8000,
    url_key: str = "url",
) -> int:
    """광고 리스트에서 advertiser_name이 없는 것들의 URL을 따라가서 광고주 채움.

    Args:
        ads: 광고 딕셔너리 리스트 (in-place 수정)
        max_resolve: 최대 해석 건수
        timeout_ms: 각 랜딩 페이지 타임아웃
        url_key: URL이 들어있는 키명

    Returns:
        해석 성공 건수
    """
    resolved = 0
    for ad in ads:
        if resolved >= max_resolve:
            break

        # 이미 광고주가 있으면 스킵
        if ad.get("advertiser_name"):
            continue

        ad_url = ad.get(url_key)
        if not ad_url or not ad_url.startswith("http"):
            continue

        # 인프라 URL이면 스킵
        try:
            host = urlparse(ad_url).netloc.lower()
            if _is_infra_host(host):
                continue
        except Exception:
            continue

        landing = await resolve_landing(context, ad_url, timeout_ms=timeout_ms)
        if landing and landing.get("advertiser_name"):
            ad["advertiser_name"] = landing["advertiser_name"]
            ad.setdefault("extra_data", {})
            ad["extra_data"]["landing_url"] = landing.get("landing_url")
            ad["extra_data"]["landing_domain"] = landing.get("landing_domain")
            ad["extra_data"]["advertiser_source"] = "landing_page"
            ad["extra_data"]["og_title"] = landing.get("og_title")
            # display_url도 업데이트
            if not ad.get("display_url") and landing.get("landing_domain"):
                ad["display_url"] = landing["landing_domain"]
            resolved += 1
            logger.debug(
                f"[landing_resolver] 광고주 해석: {landing['advertiser_name']} "
                f"← {landing.get('landing_domain')}"
            )

    return resolved
