"""네이버 검색광고 크롤러 -- 네트워크 Response 캡처 방식.

검색 페이지 응답 HTML을 네트워크 Response로 캡처한 뒤,
DOMParser로 파싱하여 파워링크/비즈사이트 광고를 추출한다.
DOM 셀렉터 직접 조회 대신 캡처된 응답 본문을 파싱.
"""

from datetime import datetime, timezone
from urllib.parse import quote

from loguru import logger
from playwright.async_api import Page, Response

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile


class NaverSearchCrawler(BaseCrawler):
    """네이버 검색 결과 페이지 응답을 캡처하여 광고 추출."""

    channel = "naver_search"

    NAVER_SEARCH_PC_URL = "https://search.naver.com/search.naver?query={query}"
    NAVER_SEARCH_MOBILE_URL = "https://m.search.naver.com/search.naver?query={query}"

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        """네이버에서 키워드 검색 후 광고 데이터 수집."""
        start_time = datetime.now(timezone.utc)

        context = await self._create_context(persona, device)
        page = await context.new_page()

        try:
            # -- 네트워크 Response 캡처 설정 --
            captured_html: list[str] = []

            async def _on_response(response: Response):
                url = response.url
                if "search.naver.com/search.naver" not in url:
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
                            "[{}] search response captured: {} bytes",
                            self.channel, len(html),
                        )
                except Exception:
                    pass

            page.on("response", _on_response)

            base_url = (
                self.NAVER_SEARCH_MOBILE_URL
                if device.is_mobile
                else self.NAVER_SEARCH_PC_URL
            )
            url = base_url.format(query=quote(keyword))
            await page.goto(url, wait_until="domcontentloaded")
            await self._dwell_on_page(page)

            # -- 캡처된 Response HTML에서 광고 파싱 --
            ads: list[dict] = []
            if captured_html:
                if device.is_mobile:
                    ads = await self._parse_mobile_from_html(
                        page, captured_html[0],
                    )
                else:
                    ads = await self._parse_pc_from_html(
                        page, captured_html[0],
                    )
                logger.info(
                    "[{}] response capture: {} ads from HTML",
                    self.channel, len(ads),
                )

                # 검색광고는 텍스트 전용 — 이미지 캡처 생략
                # (이미지/텍스트 불일치 방지, 사용자 요청 2/25)
            else:
                logger.warning(
                    "[{}] no search response captured, 0 ads",
                    self.channel,
                )

            screenshot_path = None  # full-page 스크린샷 비활성화
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
                "screenshot_path": screenshot_path,
                "ads": ads,
                "crawl_duration_ms": elapsed,
            }

        finally:
            await page.close()
            await context.close()

    # ── PC: 캡처된 HTML에서 파싱 ──

    async def _parse_pc_from_html(
        self, page: Page, html: str,
    ) -> list[dict]:
        """캡처된 HTML을 DOMParser로 파싱하여 PC 광고 추출."""
        ads = await page.evaluate(
            """(html) => {
                const BLACKLIST = [
                    '네이버 로그인', '네이버로그인', '네이버 톡톡',
                    '네이버톡톡', '네이버페이', 'NAVER', ''
                ];
                function inferPurpose(url) {
                    if (!url) return 'awareness';
                    const u = url.toLowerCase();
                    if (/shop|buy|purchase|order|cart|product|store|mall/.test(u)) return 'commerce';
                    if (/event|promo|coupon|sale|discount/.test(u)) return 'event';
                    return 'awareness';
                }
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const results = [];

                // 파워링크
                const plBody = doc.querySelector('#power_link_body');
                if (plBody) {
                    const items = plBody.querySelectorAll('li.lst');
                    items.forEach((item, idx) => {
                        const titleEl = item.querySelector('a.lnk_head');
                        const title = titleEl
                            ? titleEl.textContent.trim() : null;
                        const href = titleEl
                            ? titleEl.getAttribute('href') : null;

                        const urlArea = item.querySelector(
                            '.title_url_area'
                        );
                        let advName = null;
                        let displayUrl = null;
                        if (urlArea) {
                            const lines = urlArea.textContent
                                .trim().split('\\n')
                                .map(l => l.trim())
                                .filter(l => l.length > 0);
                            for (const line of lines) {
                                if (BLACKLIST.includes(line)) continue;
                                if (
                                    line.includes('.')
                                    && !line.includes(' ')
                                ) {
                                    displayUrl = line;
                                } else if (!advName) {
                                    advName = line;
                                }
                            }
                        }
                        if (!advName && displayUrl) {
                            advName = displayUrl
                                .replace(/^(https?:\\/\\/)?(www\\.)?/, '')
                                .split('/')[0];
                        }
                        if (!advName && href) {
                            try {
                                advName = new URL(href).hostname
                                    .replace('www.', '');
                            } catch(e) {}
                        }
                        const descEl = item.querySelector(
                            '.ad_dsc_inner, .dsc_area, [class*="ad_dsc"]'
                        );
                        const desc = descEl
                            ? descEl.textContent.trim() : null;

                        if (title) {
                            results.push({
                                advertiser_name: advName,
                                ad_text: title,
                                ad_description: desc,
                                url: href,
                                display_url: displayUrl,
                                position: results.length + 1,
                                ad_type: 'powerlink',
                                ad_product_name: '파워링크',
                                ad_format_type: 'search',
                                campaign_purpose: inferPurpose(href),
                                extra_data: {
                                    detection_method:
                                        'response_capture_domparser',
                                },
                            });
                        }
                    });
                }

                // 비즈사이트
                const bzBody = doc.querySelector('#sp_bzsite');
                if (bzBody) {
                    const items = bzBody.querySelectorAll('li.lst');
                    items.forEach((item, idx) => {
                        const titleEl = item.querySelector('a.lnk_head');
                        const title = titleEl
                            ? titleEl.textContent.trim() : null;
                        const href = titleEl
                            ? titleEl.getAttribute('href') : null;

                        const urlArea = item.querySelector(
                            '.title_url_area'
                        );
                        let advName = null;
                        if (urlArea) {
                            const lines = urlArea.textContent
                                .trim().split('\\n')
                                .map(l => l.trim())
                                .filter(l => l.length > 0);
                            for (const line of lines) {
                                if (BLACKLIST.includes(line)) continue;
                                if (
                                    !line.includes('.')
                                    || line.includes(' ')
                                ) {
                                    advName = line;
                                    break;
                                }
                            }
                        }
                        if (!advName && href) {
                            try {
                                advName = new URL(href).hostname
                                    .replace('www.', '');
                            } catch(e) {}
                        }
                        const descEl = item.querySelector(
                            '.ad_dsc_inner, [class*="ad_dsc"]'
                        );
                        const desc = descEl
                            ? descEl.textContent.trim() : null;

                        if (title) {
                            results.push({
                                advertiser_name: advName,
                                ad_text: title,
                                ad_description: desc,
                                url: href,
                                display_url: null,
                                position: results.length + 1,
                                ad_type: 'bizsite',
                                ad_product_name: '비즈사이트',
                                ad_format_type: 'search',
                                campaign_purpose: inferPurpose(href),
                                extra_data: {
                                    detection_method:
                                        'response_capture_domparser',
                                },
                            });
                        }
                    });
                }
                return results;
            }""",
            html,
        )
        logger.debug(
            "[{}] PC ads: {} (powerlink + bizsite)",
            self.channel, len(ads),
        )
        return ads

    # ── 모바일: 캡처된 HTML에서 파싱 ──

    async def _parse_mobile_from_html(
        self, page: Page, html: str,
    ) -> list[dict]:
        """캡처된 HTML을 DOMParser로 파싱하여 모바일 광고 추출."""
        ads = await page.evaluate(
            """(html) => {
                const BLACKLIST = [
                    '네이버 로그인', '네이버로그인', '네이버 톡톡',
                    '네이버톡톡', '네이버페이', 'NAVER', '네이버',
                    '더보기', ''
                ];
                function inferPurpose(url) {
                    if (!url) return 'awareness';
                    const u = url.toLowerCase();
                    if (/shop|buy|purchase|order|cart|product|store|mall/.test(u)) return 'commerce';
                    if (/event|promo|coupon|sale|discount/.test(u)) return 'event';
                    return 'awareness';
                }
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                const results = [];

                // 전략 1: 알려진 광고 컨테이너
                let container = null;
                const CONTAINER_SELS = [
                    '#power_link_body',
                    '.sp_keyword',
                    '[class*="ad_area"]',
                    '[data-ad-area]',
                    '#ct_powerlink',
                    '[class*="powerlink"]',
                ];
                for (const sel of CONTAINER_SELS) {
                    const el = doc.querySelector(sel);
                    if (el && el.querySelectorAll('a[href]').length >= 1) {
                        container = el;
                        break;
                    }
                }

                // 전략 2: "파워링크" 텍스트 기반
                if (!container) {
                    const allEls = doc.querySelectorAll('*');
                    for (const el of allEls) {
                        if (el.children.length > 0) continue;
                        const t = (el.textContent || '').trim();
                        if (t === '파워링크' || t === 'Power Link') {
                            let parent = el.parentElement;
                            for (let i = 0; i < 8 && parent; i++) {
                                const links = parent.querySelectorAll(
                                    'a[href]'
                                );
                                if (links.length >= 2) {
                                    container = parent;
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                            if (container) break;
                        }
                    }
                }

                // 전략 3: 광고 배지 기반
                if (!container) {
                    const badges = doc.querySelectorAll(
                        '[class*="ad_badge"], [class*="ad_label"],'
                        + ' [class*="ad-badge"]'
                    );
                    for (const label of badges) {
                        let item = label.closest(
                            'li, [class*="item"], [class*="bx"], div'
                        );
                        if (!item) continue;
                        const a = item.querySelector(
                            'a[href]:not([href="#"])'
                        );
                        if (!a) continue;
                        const title = a.textContent.trim();
                        const href = a.getAttribute('href');
                        if (!title || title.length < 2) continue;
                        let advName = null;
                        if (href) {
                            try {
                                advName = new URL(href).hostname
                                    .replace('www.', '');
                            } catch(e) {}
                        }
                        results.push({
                            advertiser_name: advName,
                            ad_text: title.substring(0, 200),
                            ad_description: null,
                            url: href,
                            display_url: null,
                            position: results.length + 1,
                            ad_type: 'powerlink',
                            ad_product_name: '파워링크',
                            ad_format_type: 'search',
                            campaign_purpose: inferPurpose(href),
                            extra_data: {
                                detection_method:
                                    'response_capture_badge',
                            },
                        });
                    }
                    if (results.length > 0) return results;
                }

                if (!container) return results;

                // 컨테이너 내 광고 아이템 추출
                let items = container.querySelectorAll(
                    'li.lst, li.bx, li[class], [class*="item"]'
                );
                if (items.length === 0) {
                    items = container.querySelectorAll('li, > div');
                }

                items.forEach((item, idx) => {
                    const titleSels = [
                        'a.lnk_head', 'a[class*="tit"]',
                        'a[class*="title"]',
                        '[class*="tit"] a', '[class*="title"] a',
                    ];
                    let titleEl = null;
                    for (const sel of titleSels) {
                        titleEl = item.querySelector(sel);
                        if (titleEl) break;
                    }
                    if (!titleEl) {
                        const allLinks = item.querySelectorAll(
                            'a[href]:not([href="#"])'
                        );
                        for (const a of allLinks) {
                            const t = a.textContent.trim();
                            if (
                                t && t.length > 2
                                && !BLACKLIST.some(b => t.includes(b))
                            ) {
                                titleEl = a;
                                break;
                            }
                        }
                    }
                    if (!titleEl) return;

                    const title = titleEl.textContent.trim();
                    const href = titleEl.getAttribute('href') || null;
                    if (!title || title.length < 2) return;

                    let advName = null;
                    let displayUrl = null;
                    const urlSels = [
                        '.title_url_area', '[class*="url"]',
                        '[class*="source"]', '[class*="info_area"]',
                        '[class*="sub_txt"]',
                    ];
                    for (const sel of urlSels) {
                        const urlEl = item.querySelector(sel);
                        if (!urlEl) continue;
                        const lines = urlEl.textContent
                            .trim().split('\\n')
                            .map(l => l.trim())
                            .filter(l => l.length > 0);
                        for (const line of lines) {
                            if (BLACKLIST.includes(line)) continue;
                            if (
                                line.includes('.')
                                && !line.includes(' ')
                                && line.length < 50
                            ) {
                                displayUrl = line;
                            } else if (
                                !advName
                                && line.length > 1
                                && line.length < 50
                            ) {
                                advName = line;
                            }
                        }
                        if (advName || displayUrl) break;
                    }
                    if (!advName && displayUrl) {
                        advName = displayUrl
                            .replace(/^(https?:\\/\\/)?(www\\.)?/, '')
                            .split('/')[0];
                    }
                    if (!advName && href) {
                        try {
                            advName = new URL(href).hostname
                                .replace('www.', '');
                        } catch(e) {}
                    }

                    let desc = null;
                    const descSels = [
                        '.ad_dsc_inner', '[class*="ad_dsc"]',
                        '[class*="dsc"]', '[class*="desc"]',
                        '[class*="detail"]',
                    ];
                    for (const sel of descSels) {
                        const descEl = item.querySelector(sel);
                        if (descEl) {
                            desc = descEl.textContent.trim();
                            break;
                        }
                    }

                    results.push({
                        advertiser_name: advName,
                        ad_text: title.substring(0, 200),
                        ad_description: desc
                            ? desc.substring(0, 200) : null,
                        url: href,
                        display_url: displayUrl,
                        position: results.length + 1,
                        ad_type: 'powerlink',
                        ad_product_name: '파워링크',
                        ad_format_type: 'search',
                        campaign_purpose: inferPurpose(href),
                        extra_data: {
                            detection_method:
                                'response_capture_domparser',
                        },
                    });
                });

                return results;
            }""",
            html,
        )
        logger.debug(
            "[{}] mobile ads: {} items",
            self.channel, len(ads),
        )
        return ads

    # -- 광고 리스트 아이템 element 캡처 --

    async def _capture_ad_list_items(
        self,
        page: Page,
        ads: list[dict],
        keyword: str,
        persona_code: str,
        is_mobile: bool,
    ):
        """실제 페이지의 광고 리스트 아이템(li) 영역을 캡처하여 creative_image_path에 저장.

        텍스트 광고이므로 최소 사이즈 체크 없이 캡처한다.
        """
        if not ads:
            return

        # PC: #power_link_body li.lst, 모바일: 파워링크 컨테이너 내 li
        if is_mobile:
            container_selectors = [
                "#power_link_body li.lst",
                "#power_link_body li",
                "#ct_powerlink li",
                ".sp_keyword li",
                "[class*='powerlink'] li",
                "[class*='ad_area'] li",
            ]
        else:
            container_selectors = [
                "#power_link_body li.lst",
                "#power_link_body li",
                "#sp_bzsite li.lst",
            ]

        captured_items: list = []
        for selector in container_selectors:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    for idx in range(count):
                        captured_items.append(page.locator(selector).nth(idx))
                    break
            except Exception:
                continue

        if not captured_items:
            logger.debug("[{}] no ad list items found on live page", self.channel)
            return

        capture_count = 0
        for i, ad in enumerate(ads):
            if i >= len(captured_items):
                break
            try:
                loc = captured_items[i]
                # 텍스트 광고이므로 사이즈 체크 없이 캡처
                creative_path = await self._capture_ad_element(
                    page, loc, keyword, persona_code, "naver_search_ad"
                )
                if creative_path:
                    ad["creative_image_path"] = creative_path
                    capture_count += 1
            except Exception as e:
                logger.debug("[{}] ad item capture failed at {}: {}", self.channel, i, e)

        logger.debug(
            "[{}] ad list item capture: {}/{}",
            self.channel, capture_count, len(ads),
        )
