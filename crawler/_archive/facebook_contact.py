"""Facebook contact measurement crawler -- network intercept on public pages.

Visits public Facebook pages (Watch, public Pages, Reels) WITHOUT login,
captures ad delivery network responses, and extracts ad data.

This is contact measurement (is_contact=True) -- actual ad exposure
during real browsing, NOT catalog scraping from Ad Library.

Ad network endpoints captured:
  - www.facebook.com/ads/  (ad metadata)
  - web.facebook.com/ajax/ads/  (ad AJAX delivery)
  - an.facebook.com  (Audience Network)
  - www.facebook.com/ajax/pagelet/  (pagelet ad slots)
  - z-m-graph.facebook.com  (mobile graph API ad data)
  - edge-chat.facebook.com  (ad event tracking)
  - pixel.facebook.com  (ad pixel with advertiser data)
  - www.facebook.com/tr/  (tracking pixel with ad info)
  - bidder.criteo.com / doubleclick.net  (third-party ad fills)
  - fbcdn.net/ads/  (ad creative assets)
  - Ad-related JSON responses containing 'sponsored' / 'ad_id' fields

Detection method: Pure network interception (no DOM-based ad detection).
"""

from __future__ import annotations

import json
import os
import random
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, unquote, urlparse

from loguru import logger
from playwright.async_api import Page, Response, Request

from crawler.base_crawler import BaseCrawler
from crawler.personas.device_config import DeviceConfig
from crawler.personas.profiles import PersonaProfile


# ---- Facebook ad delivery URL patterns ----
# These are network endpoints that carry ad data in their responses.

_FB_AD_RESPONSE_PATTERNS = (
    "/ads/",
    "/ajax/ads/",
    "/ajax/bz/",
    "/ajax/mercury/",
    "an.facebook.com",
    "/adnw_request",
    "/impression.php",
    "z-m-graph.facebook.com",
)

_FB_AD_REQUEST_PATTERNS = (
    "/tr/",
    "/tr?",
    "pixel.facebook.com",
    "connect.facebook.net",
    "/ads/measurement",
    "/ads/process",
)

# Third-party ad fill patterns (Facebook pages can serve these)
_THIRDPARTY_AD_PATTERNS = (
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "bidder.criteo.com",
    "adsrvr.org",
    "amazon-adsystem.com",
)

# Ad infra domains (not real advertiser landing pages)
_AD_INFRA_DOMAINS = {
    "facebook.com", "facebook.net", "fbcdn.net", "fb.com",
    "instagram.com", "meta.com",
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "gstatic.com", "googleapis.com", "google.com", "google-analytics.com",
    "criteo.com", "criteo.net", "bidswitch.net", "adsrvr.org",
    "amazon-adsystem.com", "taboola.com", "outbrain.com",
}

# Public Facebook pages to visit for ad exposure (high traffic pages)
_PUBLIC_PAGES = [
    "https://www.facebook.com/watch",
    "https://www.facebook.com/watch/live/",
    "https://www.facebook.com/reel/",
    "https://www.facebook.com/gaming/",
    "https://www.facebook.com/marketplace/",
]

# Korean brand / public pages for targeted browsing
_PUBLIC_BRAND_PAGES = [
    "https://www.facebook.com/Samsung",
    "https://www.facebook.com/samsungkorea",
    "https://www.facebook.com/hyundai",
    "https://www.facebook.com/meta",
    "https://www.facebook.com/coupang",
    "https://www.facebook.com/LGKorea",
    "https://www.facebook.com/NikeKorea",
    "https://www.facebook.com/AdidasKorea",
    "https://www.facebook.com/starbuckskorea",
    "https://www.facebook.com/NetflixKR",
]

# Domain to brand name mapping (for advertiser resolution)
_DOMAIN_BRAND_MAP: dict[str, str] = {
    "samsung.com": "Samsung", "samsungsds.com": "Samsung SDS",
    "lge.co.kr": "LG", "lg.co.kr": "LG",
    "hyundai.com": "Hyundai", "kia.com": "Kia",
    "coupang.com": "Coupang", "11st.co.kr": "11st",
    "temu.com": "Temu", "aliexpress.com": "AliExpress",
    "nike.com": "Nike", "adidas.co.kr": "Adidas",
    "apple.com": "Apple", "netflix.com": "Netflix",
    "toss.im": "Toss", "baemin.com": "Baemin",
    "musinsa.com": "Musinsa", "oliveyoung.co.kr": "Olive Young",
    "kurly.com": "Kurly", "ssg.com": "SSG",
}

# Environment variable controls
FB_CONTACT_MAX_PAGES = max(1, int(os.getenv("FB_CONTACT_MAX_PAGES", "5")))
FB_CONTACT_SCROLL_ROUNDS = max(1, int(os.getenv("FB_CONTACT_SCROLL_ROUNDS", "8")))
FB_CONTACT_PAGE_DWELL_MS = max(2000, int(os.getenv("FB_CONTACT_PAGE_DWELL_MS", "6000")))


def _domain_to_brand(domain: str | None) -> str | None:
    """Map domain to brand name."""
    if not domain:
        return None
    d = domain.lower().removeprefix("www.").removeprefix("m.")
    if d in _DOMAIN_BRAND_MAP:
        return _DOMAIN_BRAND_MAP[d]
    parts = d.split(".")
    if len(parts) >= 2:
        base = ".".join(parts[-2:])
        if base in _DOMAIN_BRAND_MAP:
            return _DOMAIN_BRAND_MAP[base]
    return None


def _is_ad_infra_url(url: str) -> bool:
    """Check if URL belongs to ad infrastructure (not a real advertiser)."""
    try:
        host = urlparse(url).netloc.lower()
        return any(infra in host for infra in _AD_INFRA_DOMAINS)
    except Exception:
        return False


def _extract_landing_url(raw_url: str | None) -> str | None:
    """Extract real landing URL from Facebook redirect/tracking URLs."""
    if not raw_url:
        return None
    try:
        parsed = urlparse(raw_url)
        query = parse_qs(parsed.query)
        # Facebook tracking pixel parameters
        for key in ("u", "url", "next", "redirect_url", "dl", "r"):
            values = query.get(key)
            if not values:
                continue
            candidate = unquote(values[0]).strip()
            if candidate.startswith(("http://", "https://")):
                if not _is_ad_infra_url(candidate):
                    return candidate
        return raw_url
    except Exception:
        return raw_url


def _extract_domain(url: str | None) -> str | None:
    """Extract domain from URL."""
    if not url:
        return None
    try:
        return urlparse(url).netloc or None
    except Exception:
        return None


class FacebookContactCrawler(BaseCrawler):
    """Facebook contact measurement via network interception on public pages.

    Visits Facebook Watch, public pages, Reels, and Marketplace WITHOUT login.
    Captures ad delivery network responses to measure real ad contact.
    """

    channel = "facebook_contact"
    keyword_dependent = False

    def __init__(self):
        super().__init__()
        self.max_pages = FB_CONTACT_MAX_PAGES
        self.scroll_rounds = FB_CONTACT_SCROLL_ROUNDS
        self.page_dwell_ms = FB_CONTACT_PAGE_DWELL_MS

    async def crawl_keyword(
        self,
        keyword: str,
        persona: PersonaProfile,
        device: DeviceConfig,
    ) -> dict:
        start_time = datetime.now(timezone.utc)
        context = await self._create_context(persona, device)

        try:
            page = await context.new_page()

            # ---- Network interception setup ----
            captured_ads: list[dict] = []
            captured_landings: dict[str, str] = {}  # request_id -> landing_url
            tracking_pixels: list[dict] = []

            async def _on_fb_response(response: Response):
                """Intercept Facebook ad delivery responses."""
                url = response.url
                try:
                    # Check if this is an ad-related response
                    is_ad_response = any(
                        pat in url for pat in _FB_AD_RESPONSE_PATTERNS
                    )
                    is_thirdparty = any(
                        pat in url for pat in _THIRDPARTY_AD_PATTERNS
                    )

                    if not is_ad_response and not is_thirdparty:
                        return

                    status = response.status

                    # Redirect responses -- extract landing URL
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("location", "")
                        if location and location.startswith("http"):
                            landing = _extract_landing_url(location)
                            if landing and not _is_ad_infra_url(landing):
                                captured_landings[url[:80]] = landing
                        return

                    if status != 200:
                        return

                    ct = response.headers.get("content-type", "")

                    # JSON responses -- parse ad data
                    if "json" in ct or "javascript" in ct:
                        try:
                            body = await response.text()
                            if not body:
                                return
                            # Facebook often prefixes JSON with for(;;);
                            clean_body = body
                            if body.startswith("for (;;);"):
                                clean_body = body[len("for (;;);"):]
                            elif body.startswith("for(;;);"):
                                clean_body = body[len("for(;;);"):]

                            try:
                                data = json.loads(clean_body)
                            except json.JSONDecodeError:
                                # Try to extract ad data from JS response
                                ads = _parse_js_ad_data(body, url)
                                captured_ads.extend(ads)
                                return

                            ads = _parse_json_ad_data(data, url)
                            captured_ads.extend(ads)
                        except Exception:
                            pass
                        return

                    # HTML responses -- extract ad metadata from markup
                    if "html" in ct or "text" in ct:
                        try:
                            body = await response.text()
                            if body and len(body) < 500_000:
                                ads = _parse_html_ad_data(body, url)
                                captured_ads.extend(ads)
                        except Exception:
                            pass
                        return

                except Exception as exc:
                    logger.debug(
                        "[{}] response intercept error: {}",
                        self.channel, str(exc)[:100],
                    )

            def _on_fb_request(request: Request):
                """Capture outgoing ad tracking requests for landing URLs."""
                url = request.url
                is_tracking = any(
                    pat in url for pat in _FB_AD_REQUEST_PATTERNS
                )
                is_thirdparty = any(
                    pat in url for pat in _THIRDPARTY_AD_PATTERNS
                )
                if not is_tracking and not is_thirdparty:
                    return

                landing = _extract_landing_url(url)
                if landing and landing != url and not _is_ad_infra_url(landing):
                    captured_landings[url[:80]] = landing

                # Extract advertiser info from tracking pixel params
                try:
                    parsed = urlparse(url)
                    query = parse_qs(parsed.query)

                    # Facebook pixel ev (event) + cd (custom data) parameters
                    ev = query.get("ev", [""])[0]
                    if ev in ("ViewContent", "Purchase", "AddToCart", "Lead"):
                        domain = parsed.netloc
                        # The referer often contains the advertiser page
                        tracking_pixels.append({
                            "event": ev,
                            "url": url,
                            "params": {
                                k: v[0] for k, v in query.items()
                                if k in ("cd[content_name]", "cd[content_type]",
                                         "dl", "rl", "id")
                            },
                        })
                except Exception:
                    pass

            page.on("response", _on_fb_response)
            page.on("request", _on_fb_request)

            # ---- Browse public Facebook pages ----

            # Build browsing list: Watch + random brand pages
            browse_urls = list(_PUBLIC_PAGES[:2])  # Watch and Watch/Live
            brand_sample = random.sample(
                _PUBLIC_BRAND_PAGES,
                min(self.max_pages - 2, len(_PUBLIC_BRAND_PAGES)),
            )
            browse_urls.extend(brand_sample)
            browse_urls = browse_urls[:self.max_pages]

            for i, target_url in enumerate(browse_urls):
                try:
                    logger.debug(
                        "[{}] visiting {} ({}/{})",
                        self.channel, target_url, i + 1, len(browse_urls),
                    )
                    await page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=20000,
                    )
                    await page.wait_for_timeout(3000)

                    # Handle login wall / cookie consent without login
                    await self._dismiss_fb_popups(page)

                    # Scroll to trigger lazy-loaded ads
                    await self._browse_and_scroll(page)

                    # Dwell on page to allow ad delivery
                    await page.wait_for_timeout(
                        self.page_dwell_ms + random.randint(-1000, 1000)
                    )

                    # Inter-page cooldown
                    if i < len(browse_urls) - 1:
                        await page.wait_for_timeout(random.randint(1500, 3000))

                except Exception as exc:
                    logger.debug(
                        "[{}] page visit failed {}: {}",
                        self.channel, target_url, str(exc)[:100],
                    )

            # ---- Process captured data ----
            logger.info(
                "[{}] raw captures: {} ads, {} landings, {} pixels",
                self.channel,
                len(captured_ads),
                len(captured_landings),
                len(tracking_pixels),
            )

            # Build final ad list from all capture sources
            all_ads = self._build_contact_ads(
                captured_ads, captured_landings, tracking_pixels,
            )

            # Deduplicate
            all_ads = self._dedupe_ads(all_ads)

            # Re-number positions
            for idx, ad in enumerate(all_ads, 1):
                ad["position"] = idx

            elapsed = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            logger.info(
                "[{}] contact measurement done: {} ads in {}ms",
                self.channel, len(all_ads), elapsed,
            )

            return {
                "keyword": keyword or "facebook_browse",
                "persona_code": persona.code,
                "device": device.device_type,
                "channel": self.channel,
                "captured_at": datetime.now(timezone.utc),
                "page_url": page.url,
                "screenshot_path": None,
                "ads": all_ads,
                "crawl_duration_ms": elapsed,
            }

        finally:
            for p in context.pages:
                await p.close()
            await context.close()

    # ================================================================
    # Browsing helpers
    # ================================================================

    async def _browse_and_scroll(self, page: Page):
        """Scroll through page to trigger lazy-loaded ad content."""
        for s in range(self.scroll_rounds):
            dist = 500 + s * 120 + random.randint(-80, 80)
            await page.evaluate(f"window.scrollBy(0, {dist})")
            await page.wait_for_timeout(random.randint(600, 1200))

            # Occasional mouse jiggle to appear human
            if random.random() < 0.3:
                try:
                    viewport = page.viewport_size
                    if viewport:
                        x = random.randint(100, viewport["width"] - 100)
                        y = random.randint(100, viewport["height"] - 100)
                        await page.mouse.move(x, y, steps=random.randint(3, 8))
                except Exception:
                    pass

    async def _dismiss_fb_popups(self, page: Page):
        """Dismiss Facebook login walls, cookie consent, and other popups.

        Does NOT perform login -- just closes blocking overlays.
        """
        for _ in range(3):
            try:
                dismissed = await page.evaluate("""() => {
                    // Cookie consent
                    const cookieBtn = document.querySelector(
                        'button[data-cookiebanner="accept_button"]'
                    );
                    if (cookieBtn) { cookieBtn.click(); return 'cookie'; }

                    // "Not Now" / "Close" / dismiss buttons
                    const btns = document.querySelectorAll(
                        'button, div[role="button"], a[role="button"]'
                    );
                    for (const btn of btns) {
                        const t = (btn.textContent || '').trim().toLowerCase();
                        if (/^(not now|close|dismiss|cancel|later|skip)$/.test(t)
                            || /^(나중에|닫기|취소|건너뛰기)$/.test(t)) {
                            btn.click();
                            return 'dismiss:' + t;
                        }
                    }

                    // Close button (X) on modals
                    const closeBtn = document.querySelector(
                        '[aria-label="Close"], [aria-label="닫기"]'
                    );
                    if (closeBtn) { closeBtn.click(); return 'close_x'; }

                    // Remove login overlay if it blocks content
                    const loginModal = document.querySelector(
                        'div[role="dialog"][aria-label*="Log"]'
                    );
                    if (loginModal) {
                        loginModal.remove();
                        return 'removed_login_modal';
                    }

                    // Remove fixed-position login banners
                    const fixedBanners = document.querySelectorAll(
                        'div[data-nosnippet], div[class*="login"]'
                    );
                    for (const banner of fixedBanners) {
                        const style = window.getComputedStyle(banner);
                        if (style.position === 'fixed' || style.position === 'sticky') {
                            banner.remove();
                            return 'removed_fixed_banner';
                        }
                    }

                    return null;
                }""")
                if dismissed:
                    logger.debug("[{}] popup dismissed: {}", "facebook_contact", dismissed)
                    await page.wait_for_timeout(1500)
                else:
                    break
            except Exception:
                pass
            await page.wait_for_timeout(800)

    # ================================================================
    # Ad data building
    # ================================================================

    def _build_contact_ads(
        self,
        captured_ads: list[dict],
        captured_landings: dict[str, str],
        tracking_pixels: list[dict],
    ) -> list[dict]:
        """Combine all capture sources into normalized ad records."""
        ads: list[dict] = []

        # Source 1: Direct ad data from JSON/HTML responses
        for raw in captured_ads:
            advertiser = raw.get("advertiser_name")
            ad_text = raw.get("ad_text") or advertiser or "facebook_ad"
            url = raw.get("url")
            display_url = _extract_domain(url)

            if not advertiser and display_url:
                advertiser = _domain_to_brand(display_url) or display_url

            if not advertiser and not url:
                continue

            # ── 마케팅 플랜 계층 필드 (Source 1) ──
            _src_url = (raw.get("source_url") or "").lower()
            if "reel" in _src_url:
                _ad_product_name = "릴스 광고"
            elif "watch" in _src_url:
                _ad_product_name = "피드 동영상"
            elif "marketplace" in _src_url:
                _ad_product_name = "마켓플레이스 광고"
            else:
                _ad_product_name = "피드 광고"
            _campaign_purpose = "commerce" if "marketplace" in _src_url else "awareness"

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": ad_text[:300],
                "ad_description": raw.get("ad_description"),
                "url": url,
                "display_url": display_url,
                "position": len(ads) + 1,
                "ad_type": "social_contact",
                "ad_placement": "facebook_browse",
                "ad_product_name": _ad_product_name,
                "ad_format_type": "social",
                "campaign_purpose": _campaign_purpose,
                "creative_image_path": None,
                "verification_status": "contact_measured",
                "verification_source": "network_intercept",
                "is_contact": True,
                "extra_data": {
                    "source_url": raw.get("source_url"),
                    "ad_id": raw.get("ad_id"),
                    "campaign_id": raw.get("campaign_id"),
                    "image_url": raw.get("image_url"),
                    "detection_method": raw.get("detection_method", "network_json"),
                    "crawl_mode": "contact",
                },
            })

        # Source 2: Landing URLs from redirect captures
        used_landings: set[str] = set()
        for req_key, landing in captured_landings.items():
            if landing in used_landings:
                continue
            if _is_ad_infra_url(landing):
                continue

            display_url = _extract_domain(landing)
            if not display_url:
                continue

            advertiser = _domain_to_brand(display_url) or display_url
            used_landings.add(landing)

            # ── 마케팅 플랜 계층 필드 (Source 2) ──
            _rk_lower = req_key.lower()
            if "reel" in _rk_lower:
                _ad_product_name_s2 = "릴스 광고"
            elif "watch" in _rk_lower:
                _ad_product_name_s2 = "피드 동영상"
            elif "marketplace" in _rk_lower:
                _ad_product_name_s2 = "마켓플레이스 광고"
            else:
                _ad_product_name_s2 = "피드 광고"
            _campaign_purpose_s2 = "commerce" if "marketplace" in _rk_lower else "awareness"

            ads.append({
                "advertiser_name": advertiser,
                "ad_text": f"facebook_contact_ad ({advertiser})",
                "ad_description": None,
                "url": landing,
                "display_url": display_url,
                "position": len(ads) + 1,
                "ad_type": "social_contact",
                "ad_placement": "facebook_browse",
                "ad_product_name": _ad_product_name_s2,
                "ad_format_type": "social",
                "campaign_purpose": _campaign_purpose_s2,
                "creative_image_path": None,
                "verification_status": "contact_measured",
                "verification_source": "network_redirect",
                "is_contact": True,
                "extra_data": {
                    "source_request": req_key,
                    "detection_method": "network_redirect",
                    "crawl_mode": "contact",
                },
            })

        # Source 3: Tracking pixels (lower confidence but useful)
        for pixel in tracking_pixels:
            params = pixel.get("params", {})
            dl_url = params.get("dl")
            if dl_url and not _is_ad_infra_url(dl_url):
                display_url = _extract_domain(dl_url)
                if display_url and display_url not in used_landings:
                    advertiser = _domain_to_brand(display_url) or display_url
                    used_landings.add(display_url)

                    # ── 마케팅 플랜 계층 필드 (Source 3) ──
                    _pixel_event = (pixel.get("event") or "").lower()
                    if _pixel_event in ("purchase", "addtocart"):
                        _campaign_purpose_s3 = "commerce"
                    else:
                        _campaign_purpose_s3 = "awareness"

                    ads.append({
                        "advertiser_name": advertiser,
                        "ad_text": f"facebook_pixel_ad ({pixel.get('event', '')})",
                        "ad_description": None,
                        "url": dl_url,
                        "display_url": display_url,
                        "position": len(ads) + 1,
                        "ad_type": "social_contact",
                        "ad_placement": "facebook_pixel",
                        "ad_product_name": "피드 광고",
                        "ad_format_type": "social",
                        "campaign_purpose": _campaign_purpose_s3,
                        "creative_image_path": None,
                        "verification_status": "contact_measured",
                        "verification_source": "tracking_pixel",
                        "is_contact": True,
                        "extra_data": {
                            "pixel_event": pixel.get("event"),
                            "detection_method": "tracking_pixel",
                            "crawl_mode": "contact",
                        },
                    })

        return ads

    @staticmethod
    def _dedupe_ads(ads: list[dict]) -> list[dict]:
        """Deduplicate ads by advertiser + URL combination."""
        out: list[dict] = []
        seen: set[str] = set()

        for ad in ads:
            url = ad.get("url") or ""
            advertiser = ad.get("advertiser_name") or ""
            sig = f"{advertiser}|{url}"

            if sig in seen:
                continue
            seen.add(sig)
            out.append(ad)

        return out


# ================================================================
# Network response parsers (module-level for testability)
# ================================================================

def _parse_json_ad_data(data, source_url: str) -> list[dict]:
    """Recursively walk JSON response looking for ad data.

    Facebook JSON responses (both web and API) contain ad metadata in
    various nested structures. We look for common patterns:
    - 'sponsored' / 'is_sponsored' / 'is_ad' flags
    - 'ad_id' / 'adId' fields
    - 'sponsor' / 'page_name' advertiser identifiers
    - Audience Network ad fills
    """
    ads: list[dict] = []
    _walk_json(data, ads, source_url, depth=0)
    return ads


def _walk_json(obj, ads: list[dict], source_url: str, depth: int):
    """Recursive JSON walker for ad detection."""
    if depth > 20:  # prevent infinite recursion
        return

    if isinstance(obj, dict):
        # Check for sponsored/ad markers
        is_sponsored = (
            obj.get("is_sponsored")
            or obj.get("is_ad")
            or obj.get("__typename") == "SponsoredStory"
            or obj.get("story_type") == "SponsoredStory"
            or "sponsored" in str(obj.get("__typename", "")).lower()
        )

        has_ad_id = bool(
            obj.get("ad_id") or obj.get("adId") or obj.get("tracking")
        )

        # Audience Network ad fill
        is_an_fill = bool(
            obj.get("placement_id") and obj.get("bid_payload")
        )

        if is_sponsored or has_ad_id or is_an_fill:
            ad = _extract_ad_from_node(obj, source_url)
            if ad:
                ads.append(ad)
            # Don't recurse further into this ad node
            return

        # Check for ad containers
        if obj.get("ads") and isinstance(obj["ads"], list):
            for ad_item in obj["ads"]:
                if isinstance(ad_item, dict):
                    ad = _extract_ad_from_node(ad_item, source_url)
                    if ad:
                        ads.append(ad)
            return

        # Recurse into values
        for v in obj.values():
            _walk_json(v, ads, source_url, depth + 1)

    elif isinstance(obj, list):
        for item in obj:
            _walk_json(item, ads, source_url, depth + 1)


def _extract_ad_from_node(node: dict, source_url: str) -> dict | None:
    """Extract ad data from a JSON node identified as an ad."""
    if not isinstance(node, dict):
        return None

    # Advertiser name extraction
    advertiser = None
    for key in ("page_name", "sponsor_name", "advertiser_name", "name"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            advertiser = val.strip()[:150]
            break

    # Nested sponsor/page object
    if not advertiser:
        for container_key in ("sponsor", "page", "owner", "actor"):
            container = node.get(container_key)
            if isinstance(container, dict):
                for name_key in ("name", "title", "username"):
                    val = container.get(name_key)
                    if isinstance(val, str) and val.strip():
                        advertiser = val.strip()[:150]
                        break
            if advertiser:
                break

    # Ad text / body
    ad_text = None
    for key in ("message", "body", "text", "ad_text", "description"):
        val = node.get(key)
        if isinstance(val, str) and val.strip():
            ad_text = val.strip()[:300]
            break
    if not ad_text:
        # Try nested message object
        msg = node.get("message")
        if isinstance(msg, dict):
            ad_text = (msg.get("text") or "")[:300]

    # URL / landing page
    url = None
    for key in ("link", "url", "cta_url", "landing_url", "target_url"):
        val = node.get(key)
        if isinstance(val, str) and val.startswith("http"):
            resolved = _extract_landing_url(val)
            if resolved and not _is_ad_infra_url(resolved):
                url = resolved
                break

    # CTA link in nested structure
    if not url:
        cta = node.get("cta") or node.get("call_to_action")
        if isinstance(cta, dict):
            link = cta.get("link") or cta.get("url")
            if isinstance(link, str) and link.startswith("http"):
                url = _extract_landing_url(link)

    # Image URL
    image_url = None
    for key in ("image_url", "picture", "thumbnail_url", "full_picture"):
        val = node.get(key)
        if isinstance(val, str) and val.startswith("http"):
            image_url = val
            break

    # Ad IDs
    ad_id = node.get("ad_id") or node.get("adId")
    campaign_id = node.get("campaign_id") or node.get("campaignId")

    if not advertiser and not url and not ad_text:
        return None

    return {
        "advertiser_name": advertiser,
        "ad_text": ad_text or advertiser or "facebook_ad",
        "ad_description": None,
        "url": url,
        "image_url": image_url,
        "ad_id": str(ad_id) if ad_id else None,
        "campaign_id": str(campaign_id) if campaign_id else None,
        "source_url": source_url,
        "detection_method": "network_json",
    }


def _parse_js_ad_data(body: str, source_url: str) -> list[dict]:
    """Extract ad data from JavaScript response body.

    Facebook often returns JS with embedded JSON or ad configuration data.
    """
    ads: list[dict] = []

    # Pattern 1: Embedded JSON objects with ad markers
    # e.g., {"ad_id":"123","sponsor_name":"Brand",...}
    json_pattern = re.compile(
        r'\{[^{}]*"(?:ad_id|adId|sponsor_name|is_sponsored)"[^{}]*\}',
        re.DOTALL,
    )
    for match in json_pattern.finditer(body[:200_000]):
        try:
            obj = json.loads(match.group())
            ad = _extract_ad_from_node(obj, source_url)
            if ad:
                ad["detection_method"] = "network_js_embedded"
                ads.append(ad)
        except json.JSONDecodeError:
            pass

    # Pattern 2: Ad configuration in JS variables
    # e.g., adConfig = {"advertiser": "Brand", "link": "https://..."}
    config_pattern = re.compile(
        r'(?:adConfig|adData|sponsoredData|ad_payload)\s*[:=]\s*(\{[^;]{10,2000}\})',
    )
    for match in config_pattern.finditer(body[:200_000]):
        try:
            obj = json.loads(match.group(1))
            ad = _extract_ad_from_node(obj, source_url)
            if ad:
                ad["detection_method"] = "network_js_config"
                ads.append(ad)
        except json.JSONDecodeError:
            pass

    # Pattern 3: Landing URLs in ad delivery JS
    landing_pattern = re.compile(
        r'(?:landingUrl|click_url|clickUrl|redirect_url|adurl)'
        r'\s*[=:]\s*["\']([^"\']+)["\']'
    )
    for match in landing_pattern.finditer(body[:200_000]):
        url = unquote(match.group(1)).strip()
        if url.startswith("http") and not _is_ad_infra_url(url):
            display_url = _extract_domain(url)
            advertiser = _domain_to_brand(display_url) if display_url else None
            if display_url:
                ads.append({
                    "advertiser_name": advertiser or None,
                    "ad_text": f"facebook_js_ad ({advertiser or display_url})",
                    "ad_description": None,
                    "url": url,
                    "image_url": None,
                    "ad_id": None,
                    "campaign_id": None,
                    "source_url": source_url,
                    "detection_method": "network_js_landing",
                })

    return ads


def _parse_html_ad_data(body: str, source_url: str) -> list[dict]:
    """Extract ad data from HTML ad responses.

    Some Facebook ad endpoints return HTML fragments with ad creative markup.
    """
    ads: list[dict] = []

    # Pattern 1: Anchor tags with ad tracking URLs containing landing URLs
    href_pattern = re.compile(
        r'href=["\']([^"\']*(?:l\.facebook\.com/l\.php|facebook\.com/ads/|'
        r'an\.facebook\.com)[^"\']*)["\']',
    )
    for match in href_pattern.finditer(body[:200_000]):
        raw_url = match.group(1)
        landing = _extract_landing_url(unquote(raw_url))
        if landing and not _is_ad_infra_url(landing):
            display_url = _extract_domain(landing)
            advertiser = _domain_to_brand(display_url) if display_url else None
            if display_url:
                ads.append({
                    "advertiser_name": advertiser or None,
                    "ad_text": f"facebook_html_ad ({advertiser or display_url})",
                    "ad_description": None,
                    "url": landing,
                    "image_url": None,
                    "ad_id": None,
                    "campaign_id": None,
                    "source_url": source_url,
                    "detection_method": "network_html_link",
                })

    # Pattern 2: data-ad attributes
    data_ad_pattern = re.compile(
        r'data-(?:ad-id|adid|ad_id)\s*=\s*["\']([^"\']+)["\']'
    )
    ad_name_pattern = re.compile(
        r'data-(?:ad-name|advertiser|sponsor)\s*=\s*["\']([^"\']+)["\']'
    )

    ad_ids = data_ad_pattern.findall(body[:200_000])
    ad_names = ad_name_pattern.findall(body[:200_000])

    for i, ad_id in enumerate(ad_ids):
        advertiser = ad_names[i] if i < len(ad_names) else None
        if ad_id:
            ads.append({
                "advertiser_name": advertiser,
                "ad_text": f"facebook_html_ad (id:{ad_id})",
                "ad_description": None,
                "url": None,
                "image_url": None,
                "ad_id": ad_id,
                "campaign_id": None,
                "source_url": source_url,
                "detection_method": "network_html_data_attr",
            })

    return ads
