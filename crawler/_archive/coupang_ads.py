"""쿠팡 리테일미디어(검색광고) 크롤러 -- 네트워크 Response 캡처 방식.

coupang.com 검색 결과 HTML을 네트워크 캡처하여
스폰서드 상품(광고 배지 부착 상품)을 추출한다.

광고 식별:
  - search-product__ad-badge 클래스 → 광고 상품
  - ad-badge 관련 마크업

로그인 불필요, headless OK.
"""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone
from urllib.parse import quote

from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

MAX_ADS = max(1, int(os.getenv("COUPANG_MAX_ADS", "30")))
_warmup_done: set[str] = set()  # context-key -> True (세션 내 1회만 워밍업)


class CoupangAdsCrawler(BaseCrawler):
    """쿠팡 검색 결과 응답을 캡처하여 스폰서드 광고 추출."""

    channel = "coupang_ads"

    SEARCH_URL = "https://www.coupang.com/np/search?component=&q={query}&channel=user"

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

            async def _on_response(response: Response):
                url = response.url
                if "coupang.com" not in url:
                    return
                try:
                    if response.status != 200:
                        return
                    ct = response.headers.get("content-type", "")
                    if "text/html" not in ct:
                        return
                    html = await response.text()
                    if html and len(html) > 1000:
                        captured_html.append(html)
                        logger.debug(
                            "[coupang_ads] response captured: {} bytes",
                            len(html),
                        )
                except Exception:
                    pass

            page.on("response", _on_response)

            # Akamai 우회: 메인 페이지 워밍업 (매 키워드마다 메인에서 시작)
            try:
                await page.goto(
                    "https://www.coupang.com",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                await page.wait_for_timeout(random.randint(2000, 4000))
                await page.mouse.move(
                    random.randint(100, 500), random.randint(100, 400)
                )
                await page.evaluate("window.scrollBy(0, 300)")
                await page.wait_for_timeout(random.randint(1000, 2000))
                logger.info("[coupang_ads] warmup done for {}", persona.code)
            except Exception as e:
                logger.warning("[coupang_ads] warmup failed: {}", str(e)[:60])

            # 검색창에 키워드 입력 (URL 직접 접근 시 Akamai 차단)
            logger.info("[coupang_ads] searching: {}", keyword)
            try:
                search_box = await page.wait_for_selector(
                    'input.search-input, input[name="q"], #headerSearchKeyword, input[type="search"]',
                    timeout=8000,
                )
                if search_box:
                    await search_box.click()
                    await page.wait_for_timeout(random.randint(300, 700))
                    await search_box.fill("")
                    await search_box.type(keyword, delay=random.randint(50, 150))
                    await page.wait_for_timeout(random.randint(500, 1000))
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("domcontentloaded", timeout=15000)
                else:
                    # 폴백: URL 직접 접근
                    url = self.SEARCH_URL.format(query=quote(keyword))
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                # 검색창 못 찾으면 URL 직접 접근
                url = self.SEARCH_URL.format(query=quote(keyword))
                logger.debug("[coupang_ads] search box fallback: direct URL")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            await page.wait_for_timeout(random.randint(2000, 4000))
            # 스크롤하여 광고 영역 로드
            await page.evaluate("window.scrollBy(0, 500)")
            await page.wait_for_timeout(random.randint(1000, 2000))

            ads: list[dict] = []
            # 1순위: response 캡처된 HTML, 2순위: page.content() 폴백
            html_to_parse = captured_html[0] if captured_html else None
            if not html_to_parse:
                html_to_parse = await page.content()
                if html_to_parse and len(html_to_parse) > 1000:
                    logger.debug(
                        "[coupang_ads] using page.content() fallback: {} bytes",
                        len(html_to_parse),
                    )
            if html_to_parse:
                ads = await self._parse_ads_from_html(page, html_to_parse, keyword)
                logger.info(
                    "[coupang_ads] '{}' -> {} ads from HTML",
                    keyword, len(ads),
                )
            else:
                logger.warning("[coupang_ads] no HTML captured")

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

    async def _parse_ads_from_html(
        self, page: Page, html: str, keyword: str,
    ) -> list[dict]:
        """캡처된 HTML을 DOMParser로 파싱하여 쿠팡 광고 추출."""
        raw = await page.evaluate(
            """(html) => {
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const results = [];

                // 방법1: ad-badge 클래스가 있는 상품
                const adItems = doc.querySelectorAll(
                    'li.search-product__ad-badge, li[class*="ad-badge"], [class*="ad_badge"]'
                );
                adItems.forEach(item => {
                    const titleEl = item.querySelector(
                        'div.name, [class*="name"], a[title], [class*="title"]'
                    );
                    const title = titleEl
                        ? titleEl.textContent.trim() : '';

                    const priceEl = item.querySelector(
                        'strong.price-value, [class*="price-value"], em.sale'
                    );
                    const price = priceEl
                        ? priceEl.textContent.trim().replace(/[^0-9]/g, '')
                        : '';

                    const linkEl = item.querySelector('a[href]');
                    const href = linkEl
                        ? linkEl.getAttribute('href') : '';

                    const imgEl = item.querySelector('img[src]');
                    const imgSrc = imgEl
                        ? (imgEl.getAttribute('src') || imgEl.getAttribute('data-img-src') || '')
                        : '';

                    const ratingEl = item.querySelector(
                        '[class*="rating"]'
                    );
                    const rating = ratingEl
                        ? ratingEl.textContent.trim() : '';

                    const sellerEl = item.querySelector(
                        '[class*="seller"], [class*="vendor"]'
                    );
                    const seller = sellerEl
                        ? sellerEl.textContent.trim() : '';

                    if (title && title.length > 1) {
                        results.push({
                            title: title.substring(0, 200),
                            price: price,
                            href: href.startsWith('/')
                                ? 'https://www.coupang.com' + href : href,
                            img_src: imgSrc,
                            rating: rating,
                            seller: seller.substring(0, 100),
                        });
                    }
                });

                // 방법2: productList 내 모든 상품 중 AD 표시 있는 것
                if (results.length === 0) {
                    const allProducts = doc.querySelectorAll(
                        '#productList li, ul[class*="search"] li[class*="product"]'
                    );
                    allProducts.forEach(item => {
                        const cls = item.className || '';
                        const innerHtml = item.innerHTML || '';
                        // 광고 배지가 있는지 확인
                        const isAd = cls.includes('ad-badge')
                            || cls.includes('ad_badge')
                            || innerHtml.includes('ad-badge')
                            || innerHtml.includes('광고');

                        if (!isAd) return;

                        const titleEl = item.querySelector(
                            'div.name, [class*="name"], a[title]'
                        );
                        const title = titleEl
                            ? titleEl.textContent.trim() : '';

                        const priceEl = item.querySelector(
                            'strong.price-value, [class*="price"]'
                        );
                        const price = priceEl
                            ? priceEl.textContent.trim().replace(/[^0-9]/g, '')
                            : '';

                        const linkEl = item.querySelector('a[href]');
                        const href = linkEl
                            ? linkEl.getAttribute('href') : '';

                        const imgEl = item.querySelector('img[src]');
                        const imgSrc = imgEl
                            ? (imgEl.getAttribute('src') || '') : '';

                        if (title && title.length > 1) {
                            results.push({
                                title: title.substring(0, 200),
                                price: price,
                                href: href.startsWith('/')
                                    ? 'https://www.coupang.com' + href : href,
                                img_src: imgSrc,
                                rating: '',
                                seller: '',
                            });
                        }
                    });
                }

                return results;
            }""",
            html,
        )

        ads: list[dict] = []
        for i, item in enumerate(raw[:MAX_ADS]):
            ads.append({
                "advertiser_name": item.get("seller") or None,
                "ad_text": item.get("title") or f"coupang_ad_{i}",
                "ad_description": None,
                "url": item.get("href") or "",
                "display_url": "www.coupang.com",
                "position": i + 1,
                "ad_type": "coupang_sponsored",
                "ad_placement": "coupang_search",
                "creative_image_path": None,
                "extra_data": {
                    "detection_method": "response_capture_ad_badge",
                    "price": item.get("price", ""),
                    "product_image": item.get("img_src", ""),
                    "rating": item.get("rating", ""),
                    "keyword": keyword,
                },
                "verification_status": "verified",
                "verification_source": "coupang_ad_badge",
            })

        return ads
