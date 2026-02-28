"""Meta 광고 크롤러 — 브라우저 기반 멀티 페르소나 수집 + 광고 투명성 센터 크로스체킹.

수집 모드:
  - browser (기본): Playwright로 Facebook/Instagram 피드 크롤링 → 광고 수집
    + Meta 광고 라이브러리 웹에서 광고주 검증
  - api (META_ACCESS_TOKEN 설정 시): 기존 Graph API 방식 fallback

검증 소스:
  - Meta 광고 라이브러리: https://www.facebook.com/ads/library/
  - Google 광고 투명성 센터: https://adstransparency.google.com/
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime
from urllib.parse import urlparse

import httpx
from loguru import logger
from playwright.async_api import Page

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile

# ── 설정 ──

AUTH_ERROR_CODES = {102, 104, 190}
QUOTA_ERROR_CODES = {4, 17, 32, 613}

META_CRAWL_MODE = os.getenv("META_CRAWL_MODE", "browser").strip().lower()
META_FEED_SCROLL_COUNT = max(1, int(os.getenv("META_FEED_SCROLL_COUNT", "15")))
META_TRUST_CHECK = os.getenv("META_TRUST_CHECK", "true").lower() in ("1", "true", "yes", "on")
META_TRUST_CHECK_LIMIT = max(1, int(os.getenv("META_TRUST_CHECK_LIMIT", "10")))
META_TRUST_CHECK_TIMEOUT_MS = max(3000, int(os.getenv("META_TRUST_CHECK_TIMEOUT_MS", "10000")))

META_AD_LIBRARY_URL = "https://www.facebook.com/ads/library/"
# 키워드 검색용 (country=ALL → 전체 국가에서 가져와서 korean_filter로 필터)
META_AD_LIBRARY_SEARCH_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=ALL"
    "&media_type=all&search_type=keyword_unordered"
    "&publisher_platforms[0]=facebook&q={query}"
)
# 검색어 없이 KR 전체 활성 광고 브라우징
META_AD_LIBRARY_BROWSE_URL = (
    "https://www.facebook.com/ads/library/"
    "?active_status=active&ad_type=all&country=KR"
    "&media_type=all&search_type=keyword_unordered"
)
GOOGLE_TRANSPARENCY_URL = "https://adstransparency.google.com/"


# ── 검증 결과 분류 ──

def classify_meta_library_result(body_text: str, hint: str | None) -> str:
    """Meta 광고 라이브러리 검색 결과를 분류."""
    text = body_text.lower()

    no_result_phrases = (
        "no results", "no ads found", "검색 결과가 없습니다",
        "일치하는 결과가 없습니다", "0 results",
    )
    if any(phrase in text for phrase in no_result_phrases):
        return "unverified"

    if hint and hint.lower() in text:
        return "verified"

    if any(token in text for token in ("advertiser", "광고주", "ads library", "광고 라이브러리")):
        return "likely_verified"

    return "unknown"


def classify_google_transparency_result(body_text: str, hint: str | None) -> str:
    """Google 광고 투명성 센터 검색 결과를 분류."""
    text = body_text.lower()

    if any(phrase in text for phrase in (
        "no results", "no ads found", "결과가 없습니다",
        "일치하는 광고가 없습니다",
    )):
        return "unverified"

    if hint and hint.lower() in text:
        return "verified"

    if any(token in text for token in ("advertiser", "광고주", "ads transparency")):
        return "likely_verified"

    return "unknown"


# ── API 에러 분류 (기존 유지) ──

def _first_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = " ".join(value.split()).strip()
        return cleaned or None
    if isinstance(value, dict):
        for key in ("text", "title", "name", "body", "value"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return " ".join(candidate.split()).strip()
        return None
    if isinstance(value, list):
        for item in value:
            found = _first_text(item)
            if found:
                return found
    return None


def classify_meta_api_error(
    status_code: int, payload: dict | None, response_text: str = "",
) -> tuple[str, bool, str]:
    """Classify Meta API failures into operational categories."""
    error = payload.get("error") if isinstance(payload, dict) else None

    message = ""
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
    if not message:
        message = (response_text or "").strip()
    message = message[:240]

    code_int: int | None = None
    if isinstance(error, dict):
        try:
            code_int = int(error.get("code")) if error.get("code") is not None else None
        except Exception:
            code_int = None

    lower_message = message.lower()
    if (
        status_code in {401, 403}
        or code_int in AUTH_ERROR_CODES
        or ("oauth" in lower_message and "invalid" in lower_message)
    ):
        return ("auth", False, message or "authentication error")

    if (
        status_code == 429
        or code_int in QUOTA_ERROR_CODES
        or "rate limit" in lower_message
        or "request limit" in lower_message
    ):
        return ("quota", True, message or "rate limit error")

    if status_code >= 500 or status_code in {408, 409, 425}:
        return ("transient", True, message or "transient server error")

    if status_code >= 400:
        return ("fatal", False, message or f"http {status_code}")

    return ("unknown", False, message or f"http {status_code}")


# ── 크롤러 ──

class MetaLibraryCrawler(BaseCrawler):
    """Meta 광고 크롤러 — 브라우저 기반 + API fallback."""

    channel = "facebook"

    def __init__(self):
        super().__init__()
        self.access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
        self.api_version = os.getenv("META_API_VERSION", "v22.0").strip()
        self.reached_country = os.getenv("META_AD_COUNTRY", "KR").strip().upper() or "KR"
        self.page_limit = max(1, int(os.getenv("META_MAX_PAGES", "5")))
        self.api_limit = max(1, min(200, int(os.getenv("META_AD_LIMIT", "100"))))
        self.max_retries = max(0, int(os.getenv("META_MAX_RETRIES", "3")))
        self.retry_backoff_ms = max(200, int(os.getenv("META_RETRY_BACKOFF_MS", "800")))
        self._client: httpx.AsyncClient | None = None
        self._use_api = META_CRAWL_MODE == "api" and bool(self.access_token)

    # ── Lifecycle ──

    async def start(self):
        if self._use_api:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(25.0, connect=10.0))
            logger.info("[{}] API client started (version={})", self.channel, self.api_version)
        else:
            await super().start()
            logger.info("[{}] 브라우저 모드 시작", self.channel)

    async def stop(self):
        if self._use_api:
            if self._client:
                await self._client.aclose()
                self._client = None
            logger.info("[{}] API client stopped", self.channel)
        else:
            await super().stop()

    # ── 메인 진입점 ──

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        if self._use_api:
            return await self._crawl_via_api(keyword, persona, device)
        return await self._crawl_via_browser(keyword, persona, device)

    # ──────────────────────────────────────────
    # 모드 1: 브라우저 기반 크롤링
    # ──────────────────────────────────────────

    async def _crawl_via_browser(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        """Meta 광고 라이브러리를 Playwright로 직접 크롤링."""
        start_time = datetime.utcnow()
        context = await self._create_context(persona, device)

        try:
            # 1단계: 광고 라이브러리에서 키워드 검색
            ads = await self._search_ad_library(
                context, keyword, persona.code
            )

            # 2단계: 수집된 광고에 대해 투명성 센터 크로스체킹
            if META_TRUST_CHECK and ads:
                await self._apply_cross_verification(context, ads)

            screenshot_path = None  # full-page 스크린샷 비활성화

            elapsed = int((datetime.utcnow() - start_time).total_seconds() * 1000)

            return {
                "keyword": keyword,
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.utcnow(),
                "page_url": META_AD_LIBRARY_URL,
                "screenshot_path": screenshot_path,
                "ads": ads,
                "crawl_duration_ms": elapsed,
            }
        finally:
            for p in context.pages:
                await p.close()
            await context.close()

    async def _search_ad_library(
        self, context, keyword: str, persona_code: str,
    ) -> list[dict]:
        """Meta 광고 라이브러리 웹에서 키워드로 광고를 검색.

        keyword가 빈 문자열이면 KR 전체 활성 광고 브라우징 모드.
        """
        page = await context.new_page()
        if keyword:
            search_url = META_AD_LIBRARY_SEARCH_URL.format(query=keyword)
        else:
            search_url = META_AD_LIBRARY_BROWSE_URL

        # Redirect URL tracking (l.facebook.com/l.php -> landing page)
        redirect_urls: list[str] = []

        def _on_request(req):
            url = req.url
            if "l.facebook.com/l.php" in url or "lm.facebook.com/l.php" in url:
                redirect_urls.append(url)

        page.on("request", _on_request)

        try:
            await page.goto(search_url, wait_until="domcontentloaded")
            # Facebook 리다이렉트 대기 -- context destroyed 방지
            await page.wait_for_timeout(5000)
            # 리다이렉트 후 URL 확인
            current_url = page.url
            if "login" in current_url or "checkpoint" in current_url:
                logger.info("[{}] Facebook 로그인 리다이렉트 감지, 재시도", self.channel)
                await page.goto(search_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)

            # 스크롤하여 더 많은 결과 로드
            for _ in range(META_FEED_SCROLL_COUNT):
                try:
                    await self._human_scroll(page, random.randint(800, 1200))
                except Exception:
                    pass

            # ── 광고 크리에이티브(이미지/영상)만 정밀 캡처 ──
            card_screenshot_map: dict[int, str] = {}
            try:
                creative_info = await page.evaluate("""() => {
                    const results = [];
                    // 카드 컨테이너 탐색
                    const cardSels = [
                        '[data-testid*="ad-content-body"]',
                        'div[role="article"]',
                    ];
                    let cards = [];
                    let useParent = false;
                    for (const sel of cardSels) {
                        cards = Array.from(document.querySelectorAll(sel));
                        if (cards.length > 0) {
                            useParent = sel.includes('ad-content-body');
                            break;
                        }
                    }
                    for (let i = 0; i < Math.min(cards.length, 30); i++) {
                        let card = cards[i];
                        if (useParent) {
                            for (let j = 0; j < 3; j++) {
                                if (card.parentElement) card = card.parentElement;
                            }
                        }
                        // 크리에이티브 요소 탐색: 영상 > 이미지 순
                        const video = card.querySelector('video');
                        if (video) {
                            const rect = video.getBoundingClientRect();
                            if (rect.width > 50 && rect.height > 50) {
                                results.push({idx: i, type: 'video'});
                                continue;
                            }
                        }
                        // 광고 이미지 (scontent/fbcdn = 실제 크리에이티브)
                        const img = card.querySelector(
                            'img[src*="scontent"], img[src*="fbcdn"]'
                        );
                        if (img) {
                            const rect = img.getBoundingClientRect();
                            if (rect.width > 80 && rect.height > 50) {
                                results.push({idx: i, type: 'image'});
                                continue;
                            }
                        }
                        results.push({idx: i, type: null});
                    }
                    return results;
                }""")

                if creative_info:
                    for info in creative_info:
                        idx = info["idx"]
                        ctype = info.get("type")
                        if not ctype:
                            continue
                        try:
                            # 카드 내부에서 크리에이티브 요소만 선택
                            card_sels = [
                                '[data-testid*="ad-content-body"]',
                                'div[role="article"]',
                            ]
                            card_el = None
                            for cs in card_sels:
                                loc = page.locator(cs)
                                if await loc.count() > idx:
                                    card_el = loc.nth(idx)
                                    if "ad-content-body" in cs:
                                        card_el = card_el.locator("xpath=ancestor::*[3]")
                                    break
                            if not card_el:
                                continue

                            if ctype == "video":
                                target = card_el.locator("video").first
                            else:
                                target = card_el.locator(
                                    'img[src*="scontent"], img[src*="fbcdn"]'
                                ).first

                            if await target.count() > 0 and await target.is_visible():
                                path = await self._capture_ad_element(
                                    page, target, keyword, persona_code,
                                    placement_name=f"meta_creative_{idx}",
                                )
                                if path:
                                    card_screenshot_map[idx] = path
                        except Exception:
                            pass
                    logger.debug(
                        "[{}] creative screenshots: {} captured",
                        self.channel, len(card_screenshot_map),
                    )
            except Exception:
                pass

            # 광고 카드 파싱 — data-testid 부모 탐색 방식
            raw_ads = await page.evaluate(
                """
                () => {
                    const clean = (v) => (v || "").replace(/\\s+/g, " ").trim();

                    // ── 1차: data-testid 기반 파싱 (현재 Facebook DOM) ──
                    const adBodies = document.querySelectorAll(
                        '[data-testid*="ad-content-body"]'
                    );
                    if (adBodies.length > 0) {
                        const results = [];
                        for (const body of Array.from(adBodies).slice(0, 200)) {
                            // 3단계 부모로 올라가면 실제 카드 컨테이너
                            let card = body;
                            for (let i = 0; i < 3; i++) {
                                if (card.parentElement) card = card.parentElement;
                            }

                            // 광고주명: 첫 번째 의미있는 span 텍스트
                            let advertiserName = null;
                            const spans = card.querySelectorAll("span");
                            for (const span of spans) {
                                const t = span.textContent.trim();
                                if (t.length < 2 || /^\\d+:\\d+/.test(t)) continue;
                                if (/started|running|active|inactive|disclaimer/i.test(t)) continue;
                                if (/About this ad|See ad details/i.test(t)) continue;
                                advertiserName = t.slice(0, 150);
                                break;
                            }

                            // 광고 텍스트
                            const bodyText = clean(body.innerText || "").slice(0, 500);

                            // 이미지
                            const img = card.querySelector('img[src*="scontent"], img[src*="fbcdn"]');
                            const imageUrl = img ? (img.currentSrc || img.src) : null;

                            // 플랫폼
                            const platformText = clean(card.innerText || "").toLowerCase();
                            const platforms = [];
                            if (platformText.includes("facebook")) platforms.push("facebook");
                            if (platformText.includes("instagram")) platforms.push("instagram");
                            if (platformText.includes("messenger")) platforms.push("messenger");
                            if (platformText.includes("audience")) platforms.push("audience_network");

                            // 시작일
                            const dateMatch = (card.innerText || "").match(
                                /(\\d{4}[./-]\\d{1,2}[./-]\\d{1,2}|\\w+ \\d{1,2}, \\d{4})/
                            );

                            // 스냅샷 URL
                            const snapshotLink = card.querySelector('a[href*="ad_snapshot_url"], a[href*="ads/archive"], a[href*="/ads/library"]');
                            const pageLink = card.querySelector('a[href*="/ads/?"]');

                            results.push({
                                advertiser_name: advertiserName,
                                ad_text: bodyText || advertiserName || null,
                                ad_description: null,
                                url: snapshotLink?.href || pageLink?.href || null,
                                image_url: imageUrl,
                                platforms: platforms,
                                started: dateMatch ? dateMatch[0] : null,
                                position: results.length + 1,
                            });
                        }
                        return results;
                    }

                    // ── 2차: 기존 카드 셀렉터 fallback ──
                    const cardSelectors = [
                        'div[class*="x1plvlek"][class*="xryxfnj"]',
                        'div[class*="xrvj5dj"]',
                        'div[role="article"]',
                        'div[class*="_8jg2"]',
                    ];
                    let cards = [];
                    for (const sel of cardSelectors) {
                        cards = Array.from(document.querySelectorAll(sel));
                        if (cards.length > 0) break;
                    }

                    if (cards.length === 0) {
                        // 링크 기반 최종 fallback
                        const allLinks = Array.from(document.querySelectorAll('a[href*="ads/library"]'));
                        return allLinks.slice(0, 20).map((a, idx) => ({
                            advertiser_name: clean(a.innerText).slice(0, 100) || null,
                            ad_text: clean(a.getAttribute("aria-label") || a.title || ""),
                            ad_description: null,
                            url: a.href || null,
                            image_url: null,
                            platforms: [],
                            started: null,
                            position: idx + 1,
                        }));
                    }

                    return cards.slice(0, 200).map((card, idx) => {
                        // 광고주명: span 순회
                        let name = null;
                        const spans = card.querySelectorAll("span");
                        for (const span of spans) {
                            const t = span.textContent.trim();
                            if (t.length < 2 || /^\\d+:\\d+/.test(t)) continue;
                            if (/started|running|active|inactive|disclaimer/i.test(t)) continue;
                            name = t.slice(0, 150);
                            break;
                        }
                        // strong fallback
                        if (!name) {
                            const nameEl = card.querySelector('strong, [class*="page_name"]');
                            name = clean(nameEl?.innerText || "");
                        }

                        const bodyEl = card.querySelector('[class*="body"], p, [class*="text"]');
                        const body = clean(bodyEl?.innerText || card.innerText || "").slice(0, 500);
                        const img = card.querySelector('img[src*="scontent"], img[src*="fbcdn"]');
                        const imageUrl = img ? (img.currentSrc || img.src) : null;
                        const platformText = clean(card.innerText || "").toLowerCase();
                        const platforms = [];
                        if (platformText.includes("facebook")) platforms.push("facebook");
                        if (platformText.includes("instagram")) platforms.push("instagram");
                        if (platformText.includes("messenger")) platforms.push("messenger");
                        if (platformText.includes("audience")) platforms.push("audience_network");
                        const dateMatch = (card.innerText || "").match(
                            /(\\d{4}[./-]\\d{1,2}[./-]\\d{1,2}|\\w+ \\d{1,2}, \\d{4})/
                        );
                        const snapshotLink = card.querySelector('a[href*="ad_snapshot_url"], a[href*="ads/archive"]');

                        return {
                            advertiser_name: name || null,
                            ad_text: body || name || null,
                            ad_description: null,
                            url: snapshotLink?.href || null,
                            image_url: imageUrl,
                            platforms: platforms,
                            started: dateMatch ? dateMatch[0] : null,
                            position: idx + 1,
                        };
                    });
                }
                """
            )

            ads: list[dict] = []
            seen: set[tuple] = set()

            for item in raw_ads:
                advertiser_name = item.get("advertiser_name")
                ad_text = item.get("ad_text") or advertiser_name or "meta_ad"
                url = item.get("url")
                # URL fallback: Meta Ad Library 소재에 랜딩 URL 없으면
                # 광고주 Facebook 페이지를 URL로 사용 (광고주 식별용)
                if not url and advertiser_name:
                    url = f"https://www.facebook.com/{advertiser_name.replace(' ', '')}"

                signature = (advertiser_name, ad_text)
                if signature in seen:
                    continue
                seen.add(signature)

                display_url = None
                if url:
                    try:
                        display_url = urlparse(url).netloc or None
                    except Exception:
                        pass

                # 카드 스크린샷 매핑 (위에서 캡처한 card_screenshot_map 사용)
                position = item.get("position", len(ads) + 1)
                card_idx = position - 1
                creative_image_path = card_screenshot_map.get(card_idx)

                # Fingerprint for dedup
                import hashlib as _hashlib
                fp_src = f"meta|{advertiser_name or ''}|{ad_text or ''}|{item.get('image_url') or ''}"
                fingerprint = _hashlib.sha256(fp_src.encode()).hexdigest()[:16]

                # ── 마케팅 플랜 계층 필드 ──
                _has_video = (
                    creative_info
                    and any(
                        ci.get("type") == "video"
                        for ci in creative_info
                        if ci.get("idx") == card_idx
                    )
                ) if creative_info else False
                _has_multiple_images = (
                    creative_info
                    and sum(
                        1 for ci in creative_info
                        if ci.get("idx") == card_idx and ci.get("type") == "image"
                    ) > 1
                ) if creative_info else False
                if _has_video:
                    _ad_product_name = "피드 동영상"
                elif _has_multiple_images:
                    _ad_product_name = "캐러셀(슬라이드)"
                else:
                    _ad_product_name = "피드 이미지"

                # Infer campaign_purpose from URL patterns
                _url_lower = (url or "").lower()
                if any(kw in _url_lower for kw in ("shop", "product", "buy", "store", "cart")):
                    _campaign_purpose = "commerce"
                elif any(kw in _url_lower for kw in ("event", "promo", "sale", "offer")):
                    _campaign_purpose = "promotion"
                else:
                    _campaign_purpose = "awareness"

                ads.append({
                    "advertiser_name": advertiser_name,
                    "ad_text": ad_text,
                    "ad_description": item.get("ad_description"),
                    "url": url,
                    "display_url": display_url,
                    "position": len(ads) + 1,
                    "ad_type": "social_library",
                    "ad_placement": "meta_ads_library",
                    "ad_product_name": _ad_product_name,
                    "ad_format_type": "social",
                    "campaign_purpose": _campaign_purpose,
                    "creative_image_path": creative_image_path,
                    "verification_status": "verified",
                    "verification_source": "meta_ads_library",
                    "extra_data": {
                        "image_url": item.get("image_url"),
                        "publisher_platforms": item.get("platforms", []),
                        "source_channel": "facebook",
                        "ad_delivery_start_time": item.get("started"),
                        "verification_status": "verified",
                        "verification_source": "meta_ads_library",
                        "crawl_mode": "browser",
                        "fingerprint": fingerprint,
                        "redirect_urls": redirect_urls[:20],
                    },
                })

            logger.info(
                "[{}] 광고 라이브러리 검색 '{}' → {}건 수집",
                self.channel, keyword, len(ads),
            )
            return ads

        except Exception as e:
            logger.error("[{}] 광고 라이브러리 크롤링 실패: {}", self.channel, e)
            return []
        finally:
            await page.close()

    # ── 크로스 검증 ──

    async def _apply_cross_verification(self, context, ads: list[dict]):
        """수집된 광고를 Google 광고 투명성 센터에서 크로스체킹."""
        unique_hints: list[str] = []
        seen_hints: set[str] = set()
        for ad in ads:
            hint = ad.get("advertiser_name") or ad.get("display_url")
            if hint and hint not in seen_hints:
                seen_hints.add(hint)
                unique_hints.append(hint)

        hint_cache: dict[str, str] = {}
        for hint in unique_hints[:META_TRUST_CHECK_LIMIT]:
            result = await self._verify_with_google_transparency(context, hint)
            hint_cache[hint] = result

        for ad in ads:
            hint = ad.get("advertiser_name") or ad.get("display_url")
            if hint and hint in hint_cache:
                google_status = hint_cache[hint]
                extra = ad.get("extra_data", {})
                extra["google_transparency_status"] = google_status
                ad["extra_data"] = extra

                # Meta에서 verified이고 Google에서도 verified면 → cross_verified
                if ad.get("verification_status") == "verified" and google_status == "verified":
                    ad["verification_status"] = "cross_verified"
                    extra["verification_status"] = "cross_verified"
                    extra["cross_verification_sources"] = [
                        "meta_ads_library",
                        "google_ads_transparency_center",
                    ]

    async def _verify_with_google_transparency(
        self, context, advertiser_hint: str,
    ) -> str:
        """Google 광고 투명성 센터에서 광고주를 검색하여 검증."""
        page = await context.new_page()
        try:
            await page.goto(GOOGLE_TRANSPARENCY_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 검색창 찾기
            search_selectors = [
                'input[type="search"]',
                'input[aria-label*="Search"]',
                'input[aria-label*="search"]',
                'input[placeholder*="Search"]',
                'input[placeholder*="검색"]',
            ]
            search_input = None
            for sel in search_selectors:
                if await page.locator(sel).count() > 0:
                    search_input = page.locator(sel).first
                    break

            if not search_input:
                return "unknown"

            await search_input.fill(advertiser_hint)
            await search_input.press("Enter")
            await page.wait_for_timeout(META_TRUST_CHECK_TIMEOUT_MS)

            body_text = await page.locator("body").inner_text()
            return classify_google_transparency_result(body_text, advertiser_hint)

        except Exception as exc:
            logger.warning("[{}] Google 투명성 센터 검증 실패: {}", self.channel, exc)
            return "unknown"
        finally:
            await page.close()

    # ──────────────────────────────────────────
    # 모드 2: Graph API (fallback)
    # ──────────────────────────────────────────

    async def _crawl_via_api(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        """기존 Meta Graph API 방식 (META_ACCESS_TOKEN 필요)."""
        if not self.access_token:
            raise RuntimeError("META_ACCESS_TOKEN is not configured")
        if not self._client:
            raise RuntimeError("MetaLibraryCrawler client is not initialized")

        start_time = datetime.utcnow()
        endpoint = f"https://graph.facebook.com/{self.api_version}/ads_archive"

        params = {
            "search_terms": keyword,
            "ad_type": "ALL",
            "ad_active_status": "ALL",
            "ad_reached_countries": json.dumps([self.reached_country]),
            "limit": self.api_limit,
            "fields": ",".join([
                "id", "page_id", "page_name",
                "ad_creation_time", "ad_delivery_start_time", "ad_delivery_stop_time",
                "ad_creative_bodies", "ad_creative_link_titles",
                "ad_creative_link_descriptions", "ad_snapshot_url", "publisher_platforms",
                # Spend/impression (null for non-EU commercial, but available for political)
                "spend", "impressions", "currency",
                "demographic_distribution", "delivery_by_region",
                "estimated_audience_size", "bylines",
            ]),
            "access_token": self.access_token,
        }

        ads: list[dict] = []
        next_url: str | None = endpoint
        next_params: dict | None = params
        pages = 0
        seen: set[tuple[str | None, str | None]] = set()

        while next_url and pages < self.page_limit:
            payload = await self._request_ads_archive(
                url=next_url, params=next_params,
                keyword=keyword, page_index=pages + 1,
            )
            data = payload.get("data") or []
            pages += 1

            for item in data:
                snapshot_url = item.get("ad_snapshot_url")
                ad_text = _first_text(item.get("ad_creative_bodies"))
                title = _first_text(item.get("ad_creative_link_titles"))
                description = _first_text(item.get("ad_creative_link_descriptions"))
                advertiser_name = item.get("page_name") or f"page_{item.get('page_id')}"
                # URL fallback: snapshot_url 없으면 Facebook 페이지를 URL로 사용
                if not snapshot_url and advertiser_name:
                    page_id = item.get("page_id")
                    if page_id:
                        snapshot_url = f"https://www.facebook.com/{page_id}"
                    else:
                        snapshot_url = f"https://www.facebook.com/{advertiser_name.replace(' ', '')}"

                if not ad_text:
                    ad_text = title or description or advertiser_name or "meta_ad"

                signature = (item.get("id"), ad_text)
                if signature in seen:
                    continue
                seen.add(signature)

                display_url = None
                if snapshot_url:
                    try:
                        display_url = urlparse(snapshot_url).netloc or None
                    except Exception:
                        pass

                # ── 마케팅 플랜 계층 필드 (API 모드) ──
                _platforms = item.get("publisher_platforms") or []
                _bodies = item.get("ad_creative_bodies") or []
                # API doesn't expose media type directly; infer from available fields
                _ad_product_name_api = "피드 이미지"  # default
                if len(_bodies) > 1:
                    _ad_product_name_api = "캐러셀(슬라이드)"

                _snap_lower = (snapshot_url or "").lower()
                if any(kw in _snap_lower for kw in ("shop", "product", "buy", "store", "cart")):
                    _campaign_purpose_api = "commerce"
                elif any(kw in _snap_lower for kw in ("event", "promo", "sale", "offer")):
                    _campaign_purpose_api = "promotion"
                else:
                    _campaign_purpose_api = "awareness"

                ads.append({
                    "advertiser_name": advertiser_name,
                    "ad_text": ad_text,
                    "ad_description": description,
                    "url": snapshot_url,
                    "display_url": display_url,
                    "position": len(ads) + 1,
                    "ad_type": "social_library",
                    "ad_placement": "meta_ads_library",
                    "ad_product_name": _ad_product_name_api,
                    "ad_format_type": "social",
                    "campaign_purpose": _campaign_purpose_api,
                    "verification_status": "verified",
                    "verification_source": "meta_ads_library",
                    "extra_data": {
                        "ad_id": item.get("id"),
                        "page_id": item.get("page_id"),
                        "ad_creation_time": item.get("ad_creation_time"),
                        "ad_delivery_start_time": item.get("ad_delivery_start_time"),
                        "ad_delivery_stop_time": item.get("ad_delivery_stop_time"),
                        "publisher_platforms": item.get("publisher_platforms"),
                        # Spend/impression ranges (may be null for KR commercial ads)
                        "spend_lower": (item.get("spend") or {}).get("lower_bound"),
                        "spend_upper": (item.get("spend") or {}).get("upper_bound"),
                        "currency": item.get("currency"),
                        "impressions_lower": (item.get("impressions") or {}).get("lower_bound"),
                        "impressions_upper": (item.get("impressions") or {}).get("upper_bound"),
                        # Audience/demographic proxy signals for spend estimation
                        "estimated_audience_size": item.get("estimated_audience_size"),
                        "demographic_distribution": item.get("demographic_distribution"),
                        "delivery_by_region": item.get("delivery_by_region"),
                        "bylines": item.get("bylines"),
                        "verification_status": "verified",
                        "verification_source": "meta_ads_library",
                        "crawl_mode": "api",
                    },
                })

            next_url = (payload.get("paging") or {}).get("next")
            next_params = None

        elapsed = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        return {
            "keyword": keyword,
            "persona_code": persona.code,
            "device": device.device_type,
            "channel": self.channel,
            "captured_at": datetime.utcnow(),
            "page_url": endpoint,
            "screenshot_path": None,
            "ads": ads,
            "crawl_duration_ms": elapsed,
        }

    async def _request_ads_archive(
        self, url: str, params: dict | None, keyword: str, page_index: int,
    ) -> dict:
        if not self._client:
            raise RuntimeError("MetaLibraryCrawler client is not initialized")

        max_attempts = self.max_retries + 1
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.get(url, params=params)
            except httpx.RequestError as exc:
                if attempt >= max_attempts:
                    raise RuntimeError(f"Meta API request failed: {exc}") from exc
                wait_ms = self.retry_backoff_ms * (2 ** (attempt - 1))
                logger.warning(
                    "[{}] request error keyword='{}' page={} attempt {}/{}; retry in {}ms: {}",
                    self.channel, keyword, page_index, attempt, max_attempts, wait_ms, exc,
                )
                await asyncio.sleep(wait_ms / 1000)
                continue

            payload: dict | None = None
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = None

            if response.status_code == 200 and payload is not None:
                return payload

            category, retryable, message = classify_meta_api_error(
                status_code=response.status_code,
                payload=payload,
                response_text=response.text,
            )

            if category == "auth":
                logger.error(
                    "[{}][ALERT] auth/token error keyword='{}' page={} status={} msg={}",
                    self.channel, keyword, page_index, response.status_code, message,
                )
            elif category == "quota":
                logger.error(
                    "[{}][ALERT] quota/rate-limit keyword='{}' page={} status={} msg={}",
                    self.channel, keyword, page_index, response.status_code, message,
                )
            else:
                logger.warning(
                    "[{}] API error [{}] keyword='{}' page={} status={} msg={}",
                    self.channel, category, keyword, page_index, response.status_code, message,
                )

            if retryable and attempt < max_attempts:
                wait_ms = self.retry_backoff_ms * (2 ** (attempt - 1))
                await asyncio.sleep(wait_ms / 1000)
                continue

            raise RuntimeError(
                f"Meta API {category} error {response.status_code}: {message}"
            )

        raise RuntimeError("Meta API request exhausted retries")
