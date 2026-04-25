"""네이버 쇼핑 검색광고 크롤러 -- 네트워크 Response 캡처 방식.

search.naver.com 의 쇼핑탭(where=shopping) 결과 HTML을 네트워크 캡처하여
쇼핑검색광고(파워링크) 상품을 추출한다.

※ search.shopping.naver.com 은 봇 차단(418)이 강해서,
  search.naver.com?where=shopping 경로를 사용 (기존 naver_search와 동일 도메인).

광고 식별 (네트워크 기반):
  - adcr.naver.com 클릭 추적 URL을 포함하는 링크 = 광고
  - ad.search.naver.com 광고 API 응답 JSON
  - nbimp*.naver.com 비콘 요청 (임프레션 트래킹)

로그인 불필요, headless OK.
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.image_utils import detect_image_ext, is_valid_image
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile
from crawler.url_utils import resolve_redirect_url

MAX_ADS = max(1, int(os.getenv("NAVER_SHOP_MAX_ADS", "60")))
_SHOPPING_UI_ONLY_RE = re.compile(
    r"^(?:재생시간\s*\d{1,2}:\d{2}\s*)?(?:닫기|광고)$",
    re.IGNORECASE,
)
_SHOPPING_DOMAIN_HINT_RE = re.compile(
    r"((?:https?://)?(?:www\.)?[A-Za-z0-9가-힣][A-Za-z0-9가-힣._-]*\.(?:com|co\.kr|kr|net|org|io|shop|store|biz))",
    re.IGNORECASE,
)
_SHOPPING_BOILERPLATE_RE = re.compile(
    r"(?:네이버 로그인|네이버 아이디로 로그인이 가능합니다\.?|서비스 자세히 보기|이전으로 이동|다음으로 이동)",
    re.IGNORECASE,
)
_SHOPPING_NAVER_STORE_RE = re.compile(
    r"https?://(?:smartstore|brand)\.naver\.com/([^/?#]+)",
    re.IGNORECASE,
)
_SHOPPING_NAVER_PATH_HINT_RE = re.compile(
    r"((?:smartstore|brand|blog)\.naver\.com/[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)
_SHOPPING_GENERIC_DISPLAY_URL = "search.naver.com/shopping"
_SHOPPING_GENERIC_TOKENS = {
    "sale",
    "deal",
    "event",
    "광고",
    "특가",
    "할인",
    "공식스토어",
    "스토어",
    "store",
    "무료",
    "추천",
}


def _resolve_adcr_url(click_url: str) -> str:
    """adcr.naver.com 리다이렉트 URL 해석 — url_utils.resolve_redirect_url 래퍼."""
    return resolve_redirect_url(click_url) or click_url


def _clean_shopping_text(value: str | None) -> str:
    cleaned = _SHOPPING_BOILERPLATE_RE.sub(" ", str(value or ""))
    return re.sub(r"\s+", " ", cleaned).strip()[:200]


def _looks_invalid_shopping_title(title: str | None) -> bool:
    cleaned = _clean_shopping_text(title)
    if not cleaned:
        return True
    normalized = cleaned.lower()
    if _SHOPPING_UI_ONLY_RE.match(cleaned):
        return True
    if normalized.startswith("재생시간") and len(cleaned) <= 20:
        return True
    token_count = len(re.sub(r"[^0-9a-z가-힣]", "", normalized))
    return token_count < 2


def _extract_shopping_display_hint(*values: str | None) -> str | None:
    for value in values:
        text = _clean_shopping_text(value)
        if not text:
            continue
        naver_match = _SHOPPING_NAVER_PATH_HINT_RE.search(text)
        if naver_match:
            return naver_match.group(1).lower()
        domain_match = _SHOPPING_DOMAIN_HINT_RE.search(text)
        if not domain_match:
            continue
        candidate = domain_match.group(1)
        if not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        try:
            parsed = urlparse(candidate)
        except ValueError:
            continue
        host = parsed.netloc.lower().removeprefix("www.")
        if host:
            return host
    return None


def _derive_shopping_display_url(
    url: str | None,
    title: str | None = None,
    ad_text: str | None = None,
) -> str:
    target_url = str(url or "").strip()
    if target_url.startswith(("http://", "https://")):
        try:
            parsed = urlparse(target_url)
        except ValueError:
            parsed = None
        if parsed:
            host = parsed.netloc.lower().removeprefix("www.")
            if host:
                if host.endswith(".naver.com"):
                    match = _SHOPPING_NAVER_PATH_HINT_RE.search(target_url)
                    if match:
                        return match.group(1).lower()
                if host not in {"search.naver.com", "m.search.naver.com", "ad.search.naver.com", "m.ad.search.naver.com", "adcr.naver.com"}:
                    return host

    return _extract_shopping_display_hint(ad_text, title) or _SHOPPING_GENERIC_DISPLAY_URL


def _derive_shopping_text_advertiser(text: str | None) -> str | None:
    cleaned = _clean_shopping_text(text)
    if not cleaned:
        return None

    display_hint = _extract_shopping_display_hint(cleaned)
    prefix = cleaned
    if display_hint:
        idx = cleaned.lower().find(display_hint.lower())
        if idx >= 0:
            prefix = cleaned[:idx]
    prefix = re.sub(r"^(?:naverpay|네이버페이)\s+", "", prefix, flags=re.IGNORECASE).strip()

    tokens = [token for token in re.split(r"\s+", prefix) if token]
    token_iter = reversed(tokens) if display_hint else iter(tokens)
    for candidate in token_iter:
        normalized = re.sub(r"^[^\w]+|[^\w]+$", "", candidate)
        if normalized.lower() in _SHOPPING_GENERIC_TOKENS:
            continue
        if 1 <= len(normalized) <= 50:
            return normalized

    if display_hint:
        if ".naver.com/" in display_hint:
            path = display_hint.rsplit("/", 1)[-1].strip()
            if path:
                return path
        if not display_hint.endswith(".naver.com"):
            return display_hint.split(".")[0] or None
    return None


def _derive_shopping_advertiser(
    raw_name: str | None,
    url: str | None,
    title: str | None = None,
    ad_text: str | None = None,
) -> str | None:
    mall = _clean_shopping_text(raw_name)
    if 1 <= len(mall) <= 50:
        return mall

    target_url = str(url or "").strip()
    match = _SHOPPING_NAVER_STORE_RE.search(target_url)
    if match:
        return match.group(1)

    path_hint = _SHOPPING_NAVER_PATH_HINT_RE.search(target_url)
    if path_hint:
        return path_hint.group(1).rsplit("/", 1)[-1]

    try:
        host = urlparse(target_url).netloc.lower().removeprefix("www.")
    except ValueError:
        host = ""
    if not host:
        return _derive_shopping_text_advertiser(ad_text) or _derive_shopping_text_advertiser(title)
    if host.endswith(".naver.com"):
        text_hint = _derive_shopping_text_advertiser(ad_text) or _derive_shopping_text_advertiser(title)
        if text_hint:
            return text_hint
        return None
    return host.split(".")[0] or _derive_shopping_text_advertiser(ad_text) or _derive_shopping_text_advertiser(title)


def _build_fallback_shopping_ad(
    item: dict,
    position: int,
    keyword: str,
    detection_method: str,
) -> dict | None:
    title = _clean_shopping_text(item.get("title"))
    if _looks_invalid_shopping_title(title):
        return None

    url = _resolve_adcr_url(item.get("href") or "")
    if not url.startswith(("http://", "https://")):
        return None

    advertiser = _derive_shopping_advertiser(item.get("mall"), url, title=title, ad_text=title)
    price_str = re.sub(r"[^0-9]", "", str(item.get("price") or ""))
    display_url = _derive_shopping_display_url(url, title=title, ad_text=title)

    return {
        "advertiser_name": advertiser,
        "ad_text": title,
        "ad_description": None,
        "url": url,
        "display_url": display_url,
        "position": position,
        "ad_type": "naver_shopping_ad",
        "ad_placement": "naver_shopping_search",
        "ad_product_name": "shopping_search_ad",
        "ad_format_type": "shopping",
        "campaign_purpose": "commerce",
        "creative_image_path": None,
        "extra_data": {
            "detection_method": detection_method,
            "ad_id": item.get("ad_id", ""),
            "price": price_str,
            "product_image": item.get("img_src", ""),
            "keyword": keyword,
            "shopping_category": item.get("shopping_category", ""),
        },
        "verification_status": "verified",
        "verification_source": "naver_shopping_adcr",
    }


class NaverShoppingCrawler(BaseCrawler):
    """네이버 쇼핑탭 검색 결과 응답을 캡처하여 광고 추출."""

    channel = "naver_shopping"

    # search.shopping.naver.com 은 418 봇차단 → search.naver.com 쇼핑탭 사용
    SEARCH_PC_URL = "https://search.naver.com/search.naver?where=shopping&query={query}"
    SEARCH_MOBILE_URL = "https://m.search.naver.com/search.naver?where=shopping&query={query}"

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)
        page = await context.new_page()

        try:
            captured_html: list[str] = []
            captured_api_ads: list[dict] = []
            adcr_urls: list[str] = []

            async def _on_response(response: Response):
                url = response.url
                try:
                    if response.status != 200:
                        return

                    ct = response.headers.get("content-type", "")

                    # 1) 메인 HTML 응답 캡처
                    if "search.naver.com" in url and "text/html" in ct:
                        html = await response.text()
                        if html and len(html) > 1000:
                            captured_html.append(html)
                            logger.debug(
                                "[naver_shopping] HTML response: {} bytes",
                                len(html),
                            )

                    # 2) 쇼핑 광고 API JSON 응답 캡처
                    if "json" in ct and any(
                        p in url for p in (
                            "ad.search.naver.com",
                            "shopsearch",
                            "shopping/v1",
                            "api/search",
                            "adpost",
                        )
                    ):
                        try:
                            data = await response.json()
                            if isinstance(data, dict):
                                # API 응답에서 광고 아이템 추출
                                ads = _extract_ads_from_json(data)
                                if ads:
                                    captured_api_ads.extend(ads)
                                    logger.info(
                                        "[naver_shopping] API ads: {} from {}",
                                        len(ads), url[:80],
                                    )
                        except Exception:
                            pass

                except Exception:
                    pass

            async def _on_request(request):
                url = request.url
                # 3) adcr.naver.com 광고 클릭 트래킹 URL 캡처
                if "adcr.naver.com" in url:
                    adcr_urls.append(url)

            page.on("response", _on_response)
            page.on("request", _on_request)

            base_url = (
                self.SEARCH_MOBILE_URL if device.is_mobile
                else self.SEARCH_PC_URL
            )
            url = base_url.format(query=quote(keyword))
            logger.info("[naver_shopping] loading: {}", url[:120])
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000 + random.randint(500, 1000))

            # 깊이 스크롤: lazy-load 광고 상품 전체 트리거
            for s in range(12):
                await page.evaluate(f'window.scrollBy(0, {400 + s * 80})')
                await page.wait_for_timeout(400 + random.randint(100, 300))

            # 스크롤 후 추가 대기 (네트워크 응답 수집)
            await page.wait_for_timeout(2000)

            # HTML에서 adcr.naver.com 기반 광고 추출
            ads: list[dict] = []

            # 방법 1: API JSON 응답에서 추출된 광고 (가장 정확)
            if captured_api_ads:
                for i, item in enumerate(captured_api_ads[:MAX_ADS]):
                    ad = _normalize_api_ad(item, i + 1, keyword)
                    if ad:
                        ads.append(ad)
                logger.info(
                    "[naver_shopping] '{}' -> {} ads from API JSON",
                    keyword, len(ads),
                )

            # 방법 2: HTML 내 adcr.naver.com 링크 기반 추출
            if len(ads) < MAX_ADS and captured_html:
                html_ads = await _extract_ads_from_html_adcr(
                    page, captured_html[0], keyword
                )
                # 중복 제거 (title 기준)
                existing_titles = {a.get("ad_text", "").lower() for a in ads}
                for ad in html_ads:
                    if len(ads) >= MAX_ADS:
                        break
                    title = ad.get("ad_text", "").lower()
                    if title and title not in existing_titles:
                        existing_titles.add(title)
                        ads.append(ad)
                if html_ads:
                    logger.info(
                        "[naver_shopping] '{}' -> +{} ads from HTML adcr links",
                        keyword, len(html_ads),
                    )

            # 방법 3: 페이지 내 adcr 링크 직접 탐색 (fallback)
            if len(ads) < MAX_ADS:
                page_ads = await _extract_ads_from_page_links(page, keyword)
                existing_titles = {a.get("ad_text", "").lower() for a in ads}
                for ad in page_ads:
                    if len(ads) >= MAX_ADS:
                        break
                    title = ad.get("ad_text", "").lower()
                    if title and title not in existing_titles:
                        existing_titles.add(title)
                        ads.append(ad)
                if page_ads:
                    logger.info(
                        "[naver_shopping] '{}' -> +{} ads from page links",
                        keyword, len(page_ads),
                    )

            if adcr_urls:
                logger.debug(
                    "[naver_shopping] adcr beacons captured: {}",
                    len(adcr_urls),
                )

            logger.info(
                "[naver_shopping] '{}' -> {} total ads", keyword, len(ads),
            )

            # Download product images
            await self._download_product_images(ads)

            elapsed = int(
                (datetime.now(timezone.utc) - start_time).total_seconds()
                * 1000
            )
            return {
                "keyword": keyword,
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.now(timezone.utc),
                "page_url": page.url,
                "screenshot_path": None,
                "ads": ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            await page.close()
            await context.close()

    async def _download_product_images(self, ads: list[dict]):
        """Download product images from extra_data['product_image'] URLs."""
        download_count = 0
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for ad in ads:
                img_url = (ad.get("extra_data") or {}).get("product_image")
                if not img_url or not img_url.startswith("http"):
                    continue
                try:
                    resp = await client.get(img_url)
                    if resp.status_code != 200:
                        continue
                    content_bytes = resp.content
                    if len(content_bytes) < 500:
                        continue

                    if not is_valid_image(content_bytes):
                        continue

                    screenshot_dir = (
                        Path(self.settings.screenshot_dir)
                        / self.channel
                        / datetime.now(timezone.utc).strftime("%Y%m%d")
                    )
                    screenshot_dir.mkdir(parents=True, exist_ok=True)

                    ts = datetime.now(timezone.utc).strftime("%H%M%S%f")
                    ext = detect_image_ext(content_bytes)

                    pos = ad.get("position", 0)
                    filename = f"nshop_{pos}_{ts}{ext}"
                    filepath = screenshot_dir / filename
                    filepath.write_bytes(content_bytes)

                    try:
                        stored = await self._image_store.save(
                            str(filepath), self.channel, "creative"
                        )
                        ad["creative_image_path"] = stored
                    except Exception:
                        ad["creative_image_path"] = str(filepath)

                    download_count += 1
                except Exception as exc:
                    logger.debug(
                        "[naver_shopping] product image download failed: {}",
                        str(exc)[:80],
                    )

        if download_count:
            logger.info(
                "[naver_shopping] product images: {} saved / {} total",
                download_count, len(ads),
            )

    # is_valid_image / detect_image_ext → crawler.image_utils


def _extract_ads_from_json(data: dict) -> list[dict]:
    """API JSON 응답에서 광고 상품 추출.

    네이버 쇼핑 API는 다양한 형태로 광고 데이터를 반환:
    - data.ads[]: 광고 아이템 배열
    - data.items[]: 아이템 중 ad 마커가 있는 것
    - data.shoppingResult.products[]: 상품 중 isAd=true
    """
    ads = []

    def _collect(items: list, is_ad_field: str = "isAd"):
        for item in items:
            if not isinstance(item, dict):
                continue
            # 광고 여부 확인 (여러 필드명 체크)
            is_ad = (
                item.get(is_ad_field)
                or item.get("isAd")
                or item.get("is_ad")
                or item.get("adId")
                or item.get("ad_id")
                or "adcr.naver.com" in str(item.get("link", ""))
                or "adcr.naver.com" in str(item.get("adcrUrl", ""))
                or "adcr.naver.com" in str(item.get("clickUrl", ""))
            )
            if is_ad:
                ads.append(item)

    # 직접 ads 배열
    if isinstance(data.get("ads"), list):
        ads.extend(data["ads"])
    # items 배열에서 광고만
    if isinstance(data.get("items"), list):
        _collect(data["items"])
    # shoppingResult.products
    sr = data.get("shoppingResult") or data.get("shopping_result") or {}
    if isinstance(sr, dict) and isinstance(sr.get("products"), list):
        _collect(sr["products"])
    # data.data.items (중첩)
    inner = data.get("data")
    if isinstance(inner, dict):
        if isinstance(inner.get("items"), list):
            _collect(inner["items"])
        if isinstance(inner.get("ads"), list):
            ads.extend(inner["ads"])

    return ads


def _normalize_api_ad(item: dict, position: int, keyword: str) -> dict | None:
    """API에서 추출한 광고 아이템을 정규화."""
    title = (
        item.get("productTitle")
        or item.get("title")
        or item.get("productName")
        or item.get("name")
        or ""
    )
    # HTML 태그 제거
    title = re.sub(r"<[^>]+>", "", str(title)).strip()
    if not title or len(title) < 2:
        return None

    price = (
        item.get("price")
        or item.get("lowPrice")
        or item.get("salePrice")
        or ""
    )
    price_str = re.sub(r"[^0-9]", "", str(price))

    mall = (
        item.get("mallName")
        or item.get("storeName")
        or item.get("brand")
        or item.get("seller")
        or ""
    )
    mall = str(mall).strip()

    # 직접 URL 우선 (adcr은 pipeline _TRACKING_HOSTS에서 필터됨)
    link = (
        item.get("productUrl")
        or item.get("mallProductUrl")
        or item.get("link")
        or ""
    )
    # 직접 URL 없거나 트래킹 URL이면 → adcr에서 목적지 추출
    if not link or "adcr.naver.com" in link or "ad.search.naver.com" in link:
        tracking_url = (
            item.get("adcrUrl")
            or item.get("clickUrl")
            or link
            or ""
        )
        resolved = _resolve_adcr_url(tracking_url)
        if resolved and resolved != tracking_url:
            link = resolved
        elif not link:
            link = tracking_url

    mall = _derive_shopping_advertiser(mall, str(link), title=title, ad_text=title)
    display_url = _derive_shopping_display_url(str(link), title=title, ad_text=title)

    image = (
        item.get("imageUrl")
        or item.get("image")
        or item.get("thumbnailUrl")
        or ""
    )

    ad_id = str(item.get("adId") or item.get("ad_id") or item.get("id") or "")

    return {
        "advertiser_name": mall or None,
        "ad_text": title[:200],
        "ad_description": None,
        "url": str(link),
        "display_url": display_url,
        "position": position,
        "ad_type": "naver_shopping_ad",
        "ad_placement": "naver_shopping_search",
        "ad_product_name": "shopping_search_ad",
        "ad_format_type": "shopping",
        "campaign_purpose": "commerce",
        "creative_image_path": None,
        "extra_data": {
            "detection_method": "api_json_capture",
            "ad_id": ad_id,
            "price": price_str,
            "product_image": str(image),
            "keyword": keyword,
            "shopping_category": item.get("category1Name") or item.get("mallProductCategory") or "",
        },
        "verification_status": "verified",
        "verification_source": "naver_shopping_api",
    }


async def _extract_ads_from_html_adcr(
    page: Page, html: str, keyword: str,
) -> list[dict]:
    """캡처된 HTML에서 adcr.naver.com 링크를 가진 상품을 추출.

    DOM 클래스 셀렉터 대신 adcr.naver.com URL 패턴으로 광고를 탐지.
    """
    raw = await page.evaluate(
        """(html) => {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const results = [];
            const seen = new Set();

            // adcr.naver.com 또는 ad.search.naver.com 링크를 가진 모든 <a> 태그 탐색
            const allLinks = doc.querySelectorAll(
                'a[href*="adcr.naver.com"], a[href*="ad.search.naver.com"]'
            );

            allLinks.forEach(link => {
                const href = link.getAttribute('href') || '';

                // 상위 상품 컨테이너 찾기 (li, div, article 등)
                let container = link.closest('li') || link.closest('div[class*="item"]')
                    || link.closest('div[class*="product"]') || link.closest('article')
                    || link.parentElement?.parentElement || link.parentElement;
                if (!container) container = link;

                // 제목 추출 (여러 전략)
                let title = '';
                // 1) link 자체의 텍스트
                const linkText = link.textContent.trim();
                if (linkText.length > 3 && linkText.length < 200) {
                    title = linkText;
                }
                // 2) container 내 제목 요소
                if (!title || title.length < 3) {
                    const titleEl = container.querySelector(
                        '[class*="tit"], [class*="name"], [class*="title"], h3, h4, strong'
                    );
                    if (titleEl) title = titleEl.textContent.trim();
                }
                // 3) 이미지 alt
                if (!title || title.length < 3) {
                    const img = container.querySelector('img[alt]');
                    if (img) title = img.getAttribute('alt') || '';
                }

                title = title.substring(0, 200).trim();
                if (!title || title.length < 2) return;

                // 중복 방지
                const key = title.toLowerCase().replace(/\\s+/g, '');
                if (seen.has(key)) return;
                seen.add(key);

                // 가격 추출
                let price = '';
                const priceEl = container.querySelector(
                    '[class*="price"] em, [class*="price"] span, [class*="price"], em, .num'
                );
                if (priceEl) {
                    const priceText = priceEl.textContent.trim();
                    price = priceText.replace(/[^0-9]/g, '');
                }

                // 판매자/몰 추출
                let mall = '';
                const mallEl = container.querySelector(
                    '[class*="mall"], [class*="store"], [class*="seller"], [class*="shop"], [class*="brand"], [class*="vendor"]'
                );
                if (mallEl) {
                    mall = mallEl.textContent.trim();
                }
                // data-nclick에서 mall 정보 추출 (fallback)
                if (!mall) {
                    const nclickEl = container.querySelector('[data-nclick]');
                    if (nclickEl) {
                        const nclick = nclickEl.getAttribute('data-nclick') || '';
                        const mallMatch = nclick.match(/mall:([^,]+)/);
                        if (mallMatch) mall = mallMatch[1].trim();
                    }
                }
                // URL에서 스마트스토어 판매자명 추출 (fallback)
                if (!mall && href) {
                    const ssMatch = href.match(/smartstore\\.naver\\.com\\/([^\\/\\?]+)/);
                    if (ssMatch) mall = ssMatch[1];
                }
                // 판매자 이름이 너무 길거나 짧으면 무시
                if (mall.length > 50 || mall.length < 1) mall = '';

                // 이미지
                const imgEl = container.querySelector('img[src]');
                const imgSrc = imgEl ? (imgEl.getAttribute('src') || '') : '';

                results.push({
                    title: title,
                    price: price,
                    mall: mall,
                    href: href,
                    img_src: imgSrc,
                });
            });

            // 추가: data-ad-id 속성을 가진 요소도 탐색 (광고 마커)
            const adIdElements = doc.querySelectorAll('[data-ad-id]');
            adIdElements.forEach(el => {
                const adId = el.getAttribute('data-ad-id') || '';
                const link = el.querySelector('a') || el.closest('a');
                const href = link ? (link.getAttribute('href') || '') : '';

                let title = '';
                const titleEl = el.querySelector(
                    '[class*="tit"], [class*="name"], [class*="title"], h3, h4, strong'
                );
                if (titleEl) title = titleEl.textContent.trim();
                if (!title) title = el.textContent.trim().substring(0, 100);

                title = title.substring(0, 200).trim();
                if (!title || title.length < 2) return;

                const key = title.toLowerCase().replace(/\\s+/g, '');
                if (seen.has(key)) return;
                seen.add(key);

                let price = '';
                const priceEl = el.querySelector(
                    '[class*="price"] em, [class*="price"] span, em, .num'
                );
                if (priceEl) {
                    price = priceEl.textContent.trim().replace(/[^0-9]/g, '');
                }

                let mall = '';
                const mallEl = el.querySelector(
                    '[class*="mall"], [class*="store"], [class*="seller"], [class*="brand"], [class*="vendor"]'
                );
                if (mallEl) mall = mallEl.textContent.trim();
                // data-nclick fallback
                if (!mall) {
                    const nclick = el.getAttribute('data-nclick') || '';
                    const mallMatch = nclick.match(/mall:([^,]+)/);
                    if (mallMatch) mall = mallMatch[1].trim();
                }
                // URL 스마트스토어 fallback
                if (!mall && href) {
                    const ssMatch = href.match(/smartstore\\.naver\\.com\\/([^\\/\\?]+)/);
                    if (ssMatch) mall = ssMatch[1];
                }
                if (mall.length > 50 || mall.length < 1) mall = '';

                const imgEl = el.querySelector('img[src]');
                const imgSrc = imgEl ? (imgEl.getAttribute('src') || '') : '';

                results.push({
                    ad_id: adId,
                    title: title,
                    price: price,
                    mall: mall,
                    href: href,
                    img_src: imgSrc,
                });
            });

            return results;
        }""",
        html,
    )

    ads: list[dict] = []
    for item in raw:
        ad = _build_fallback_shopping_ad(
            item,
            position=len(ads) + 1,
            keyword=keyword,
            detection_method="html_adcr_url",
        )
        if not ad:
            continue
        ads.append(ad)
        if len(ads) >= MAX_ADS:
            break

    return ads


async def _extract_ads_from_page_links(page: Page, keyword: str) -> list[dict]:
    """라이브 페이지에서 adcr.naver.com 링크를 직접 탐색 (fallback).

    이미 로드된 페이지의 실제 DOM에서 adcr 링크와 data-nclick 광고 마커를 찾는다.
    """
    raw = await page.evaluate(
        """() => {
            const results = [];
            const seen = new Set();

            // 1) adcr.naver.com 또는 ad.search.naver.com 링크
            const adcrLinks = document.querySelectorAll(
                'a[href*="adcr.naver.com"], a[href*="ad.search.naver.com"]'
            );
            adcrLinks.forEach(link => {
                const href = link.getAttribute('href') || '';
                let container = link.closest('li') || link.closest('div[class*="item"]')
                    || link.closest('div[class*="product"]') || link.closest('article')
                    || link.parentElement?.parentElement || link.parentElement;
                if (!container) container = link;

                let title = '';
                const titleEl = container.querySelector(
                    '[class*="tit"], [class*="name"], [class*="title"], h3, h4, strong'
                );
                if (titleEl) title = titleEl.textContent.trim();
                if (!title || title.length < 3) {
                    title = link.textContent.trim();
                }
                if (!title || title.length < 3) {
                    const img = container.querySelector('img[alt]');
                    if (img) title = img.getAttribute('alt') || '';
                }

                title = title.substring(0, 200).trim();
                if (!title || title.length < 2) return;

                const key = title.toLowerCase().replace(/\\s+/g, '');
                if (seen.has(key)) return;
                seen.add(key);

                let price = '';
                const priceEl = container.querySelector(
                    '[class*="price"] em, [class*="price"] span, [class*="price"], em'
                );
                if (priceEl) {
                    price = priceEl.textContent.trim().replace(/[^0-9]/g, '');
                }

                let mall = '';
                const mallEl = container.querySelector(
                    '[class*="mall"], [class*="store"], [class*="seller"], [class*="shop"]'
                );
                if (mallEl) mall = mallEl.textContent.trim();
                if (mall.length > 50) mall = '';

                const imgEl = container.querySelector('img[src]');
                const imgSrc = imgEl ? (imgEl.getAttribute('src') || '') : '';

                results.push({
                    title: title,
                    price: price,
                    mall: mall,
                    href: href,
                    img_src: imgSrc,
                });
            });

            // 2) data-nclick에 'ad' 포함된 쇼핑 아이템
            const nclickAds = document.querySelectorAll('[data-nclick*="ad"]');
            nclickAds.forEach(el => {
                let container = el.closest('li') || el.closest('div[class*="item"]')
                    || el.closest('div[class*="product"]') || el;

                let title = '';
                const titleEl = container.querySelector(
                    '[class*="tit"], [class*="name"], [class*="title"], h3, h4, strong'
                );
                if (titleEl) title = titleEl.textContent.trim();
                if (!title || title.length < 3) title = el.textContent.trim().substring(0, 100);

                title = title.substring(0, 200).trim();
                if (!title || title.length < 2) return;

                const key = title.toLowerCase().replace(/\\s+/g, '');
                if (seen.has(key)) return;
                seen.add(key);

                const link = container.querySelector('a[href]') || el.closest('a');
                const href = link ? (link.getAttribute('href') || '') : '';

                let price = '';
                const priceEl = container.querySelector(
                    '[class*="price"] em, [class*="price"] span, em'
                );
                if (priceEl) {
                    price = priceEl.textContent.trim().replace(/[^0-9]/g, '');
                }

                let mall = '';
                const mallEl = container.querySelector(
                    '[class*="mall"], [class*="store"], [class*="seller"]'
                );
                if (mallEl) mall = mallEl.textContent.trim();
                if (mall.length > 50) mall = '';

                const imgEl = container.querySelector('img[src]');
                const imgSrc = imgEl ? (imgEl.getAttribute('src') || '') : '';

                results.push({
                    title: title,
                    price: price,
                    mall: mall,
                    href: href,
                    img_src: imgSrc,
                });
            });

            return results;
        }""",
    )

    ads: list[dict] = []
    for item in raw:
        ad = _build_fallback_shopping_ad(
            item,
            position=len(ads) + 1,
            keyword=keyword,
            detection_method="page_link_scan",
        )
        if not ad:
            continue
        ads.append(ad)
        if len(ads) >= MAX_ADS:
            break

    return ads
