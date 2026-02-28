"""Test alternative Instagram ad capture approaches.

Tests 7 different approaches to capture Instagram ad data without login:
1. Instagram Threads (threads.net)
2. Instagram Web Embeds
3. Instagram CDN/API Endpoints
4. Facebook Audience Network on Korean sites
5. Instagram Explore Page variations (tags, locations)
6. Meta Ad Library API (graph.facebook.com)
7. Instagram Reels Web

Each approach captures network traffic and reports what ad-related
data was found. Network interception only -- no DOM-based detection.
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

# Minimal dwell times for testing
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"
os.environ["CRAWLER_DWELL_MIN_MS"] = "1000"
os.environ["CRAWLER_DWELL_MAX_MS"] = "2000"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from playwright.async_api import async_playwright, Response, Page


# ---- Shared network capture infrastructure ----

class NetworkCapture:
    """Captures network responses matching patterns."""

    def __init__(self):
        self.responses: list[dict] = []
        self.ad_responses: list[dict] = []
        self.all_urls: list[str] = []

    async def on_response(self, response: Response):
        url = response.url
        self.all_urls.append(url)

        # Capture ad-related responses
        ad_patterns = (
            "an.facebook.com", "facebook.com/tr", "facebook.com/ads",
            "connect.facebook.net", "graph.facebook.com",
            "graph.instagram.com", "i.instagram.com/api/v1/",
            "instagram.com/graphql", "doubleclick.net",
            "googlesyndication.com", "googleadservices.com",
            "threads.net/api", "threads.net/graphql",
            "/ads/", "/sponsored", "ad_id", "is_ad",
            "logging_client_events", "pixel.facebook.com",
            "/ajax/bz/", "z-m-graph.facebook.com",
            "bidder.criteo.com", "adsrvr.org",
        )

        is_ad = any(pat in url for pat in ad_patterns)
        if not is_ad:
            return

        try:
            status = response.status
            ct = response.headers.get("content-type", "")
            body_preview = ""

            if status == 200 and ("json" in ct or "javascript" in ct or "text" in ct):
                try:
                    body = await response.text()
                    body_preview = body[:500] if body else ""
                except Exception:
                    pass

            entry = {
                "url": url[:200],
                "status": status,
                "content_type": ct,
                "body_preview": body_preview[:300],
            }
            self.ad_responses.append(entry)

            # Try to parse JSON for ad data
            if body_preview and ("json" in ct):
                try:
                    clean = body_preview
                    if clean.startswith("for (;;);"):
                        clean = clean[len("for (;;);"):]
                    data = json.loads(await response.text())
                    ads = self._extract_ads(data)
                    if ads:
                        entry["extracted_ads"] = ads
                except Exception:
                    pass

        except Exception as exc:
            self.ad_responses.append({
                "url": url[:200],
                "error": str(exc)[:100],
            })

    def _extract_ads(self, data, depth=0) -> list[dict]:
        """Recursively find ad markers in JSON."""
        if depth > 15:
            return []
        ads = []
        if isinstance(data, dict):
            if (data.get("is_ad") or data.get("is_sponsored")
                    or data.get("ad_id") or data.get("sponsor")):
                user = data.get("user") or data.get("owner") or {}
                ads.append({
                    "advertiser": user.get("username") if isinstance(user, dict) else None,
                    "ad_id": data.get("ad_id"),
                    "type": "sponsored_content",
                })
            for v in data.values():
                ads.extend(self._extract_ads(v, depth + 1))
        elif isinstance(data, list):
            for item in data:
                ads.extend(self._extract_ads(item, depth + 1))
        return ads

    def summary(self) -> dict:
        return {
            "total_requests": len(self.all_urls),
            "ad_related_requests": len(self.ad_responses),
            "extracted_ads": sum(
                len(r.get("extracted_ads", []))
                for r in self.ad_responses
            ),
            "ad_urls": [r["url"] for r in self.ad_responses[:20]],
        }


async def create_browser():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-infobars",
        ],
    )
    return pw, browser


async def create_context(browser, mobile=True):
    if mobile:
        ctx = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
    else:
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

    # Stealth
    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['ko-KR', 'ko', 'en-US', 'en']
        });
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.runtime) window.chrome.runtime = {
            connect: () => {}, sendMessage: () => {}
        };
    """)
    return ctx


# ================================================================
# APPROACH 1: Instagram Threads (threads.net)
# ================================================================

async def test_threads(browser) -> dict:
    """Test if threads.net shows ads to non-logged-in users."""
    print("\n" + "=" * 60)
    print("APPROACH 1: Instagram Threads (threads.net)")
    print("=" * 60)

    capture = NetworkCapture()
    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()
    page.on("response", capture.on_response)

    results = {"approach": "threads", "pages_visited": 0, "ads_found": 0}

    urls_to_try = [
        "https://www.threads.net/",
        "https://www.threads.net/search?q=korea",
        "https://www.threads.net/search?q=shopping",
        "https://www.threads.net/@samsung",
        "https://www.threads.net/@nike",
    ]

    for url in urls_to_try:
        try:
            print(f"  Visiting: {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            results["pages_visited"] += 1

            # Check if redirected to login
            current = page.url.lower()
            print(f"    Final URL: {current[:80]}")
            if "login" in current or "accounts" in current:
                print(f"    -> Redirected to login, skipping")
                continue

            await page.wait_for_timeout(3000)

            # Scroll to trigger lazy loading
            for i in range(5):
                await page.evaluate(f"window.scrollBy(0, {500 + i * 100})")
                await page.wait_for_timeout(800)

            await page.wait_for_timeout(2000)

            # Check page content for sponsored indicators
            try:
                body_text = await page.evaluate(
                    "() => document.body ? document.body.innerText.substring(0, 5000) : ''"
                )
                if "sponsor" in body_text.lower() or "ad" in body_text.lower()[:200]:
                    print(f"    -> Found potential ad indicators in page text")
            except Exception:
                pass

        except Exception as exc:
            print(f"    -> Error: {str(exc)[:100]}")

    summary = capture.summary()
    results["network_summary"] = summary
    results["ads_found"] = summary["extracted_ads"]

    print(f"\n  Network: {summary['total_requests']} total, "
          f"{summary['ad_related_requests']} ad-related, "
          f"{summary['extracted_ads']} extracted ads")
    if summary["ad_urls"]:
        print(f"  Ad URLs found:")
        for u in summary["ad_urls"][:10]:
            print(f"    - {u}")

    await page.close()
    await ctx.close()
    return results


# ================================================================
# APPROACH 2: Instagram Web Embeds
# ================================================================

async def test_embeds(browser) -> dict:
    """Test Instagram embed pages for ad network requests."""
    print("\n" + "=" * 60)
    print("APPROACH 2: Instagram Web Embeds")
    print("=" * 60)

    capture = NetworkCapture()
    ctx = await create_context(browser, mobile=False)
    page = await ctx.new_page()
    page.on("response", capture.on_response)

    results = {"approach": "embeds", "pages_visited": 0, "ads_found": 0}

    # Popular Korean brand post shortcodes (these are public)
    embed_urls = [
        "https://www.instagram.com/p/C1234567/embed/",  # placeholder
        "https://www.instagram.com/reel/C1234567/embed/",  # placeholder
    ]

    # First, try to discover real shortcodes from known public profiles
    try:
        print("  Discovering real embed URLs from public profiles...")
        await page.goto(
            "https://www.instagram.com/samsung/",
            wait_until="domcontentloaded", timeout=15000,
        )
        await page.wait_for_timeout(3000)

        # Dismiss login wall
        try:
            await page.evaluate("""() => {
                const btns = document.querySelectorAll('button, div[role="button"]');
                for (const btn of btns) {
                    const t = (btn.textContent || '').trim();
                    if (/Not Now|나중에|닫기|Close/i.test(t)) { btn.click(); return; }
                }
                const overlay = document.querySelector('div[class*="RnEpo"], div[class*="LoginAndSignupPage"]');
                if (overlay) overlay.remove();
            }""")
            await page.wait_for_timeout(1000)
        except Exception:
            pass

        links = await page.evaluate("""() => {
            const anchors = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]');
            return Array.from(anchors).slice(0, 8).map(a => a.href);
        }""")

        if links:
            embed_urls = [f"{link.rstrip('/')}embed/" if "/embed" not in link
                          else link for link in links]
            # Fix: ensure proper embed URL format
            embed_urls = []
            for link in links[:8]:
                # Extract shortcode from URL
                parts = link.rstrip("/").split("/")
                shortcode = parts[-1] if parts else None
                if shortcode and len(shortcode) > 5:
                    post_type = "reel" if "/reel/" in link else "p"
                    embed_urls.append(
                        f"https://www.instagram.com/{post_type}/{shortcode}/embed/"
                    )
            print(f"  Found {len(embed_urls)} embed URLs")

    except Exception as exc:
        print(f"  Could not discover embed URLs: {str(exc)[:100]}")

    for url in embed_urls[:6]:
        try:
            print(f"  Loading embed: {url[:80]}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=12000)
            results["pages_visited"] += 1

            if resp:
                print(f"    Status: {resp.status}")

            await page.wait_for_timeout(3000)

            # Check what loaded
            try:
                embed_content = await page.evaluate("""() => {
                    return {
                        title: document.title,
                        bodyLen: document.body ? document.body.innerText.length : 0,
                        hasIframe: !!document.querySelector('iframe'),
                        scripts: Array.from(document.querySelectorAll('script[src]'))
                            .map(s => s.src).filter(s => s.includes('facebook') || s.includes('instagram')),
                    }
                }""")
                print(f"    Content: title='{embed_content.get('title', '')[:40]}', "
                      f"bodyLen={embed_content.get('bodyLen', 0)}")
            except Exception:
                pass

        except Exception as exc:
            print(f"    -> Error: {str(exc)[:100]}")

    summary = capture.summary()
    results["network_summary"] = summary
    results["ads_found"] = summary["extracted_ads"]

    print(f"\n  Network: {summary['total_requests']} total, "
          f"{summary['ad_related_requests']} ad-related, "
          f"{summary['extracted_ads']} extracted ads")
    if summary["ad_urls"]:
        print(f"  Ad URLs found:")
        for u in summary["ad_urls"][:10]:
            print(f"    - {u}")

    await page.close()
    await ctx.close()
    return results


# ================================================================
# APPROACH 3: Instagram CDN/API Endpoints
# ================================================================

async def test_api_endpoints(browser) -> dict:
    """Test Instagram's public API endpoints for ad data."""
    print("\n" + "=" * 60)
    print("APPROACH 3: Instagram CDN/API Endpoints")
    print("=" * 60)

    capture = NetworkCapture()
    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()
    page.on("response", capture.on_response)

    results = {"approach": "api_endpoints", "endpoints_tested": 0, "ads_found": 0}
    api_results = []

    # Test various public API endpoints
    endpoints = [
        # Explore/discover endpoints
        ("https://i.instagram.com/api/v1/discover/web/explore/", "explore"),
        ("https://i.instagram.com/api/v1/discover/topical_explore/", "topical_explore"),
        ("https://i.instagram.com/api/v1/feed/reels_tray/", "reels_tray"),
        ("https://i.instagram.com/api/v1/feed/reels_media/", "reels_media"),
        # Web GraphQL endpoints with common query hashes
        ("https://www.instagram.com/graphql/query/?query_hash=c9100bf9110dd6361671f113dd02e7d6&variables=%7B%22first%22%3A20%7D", "graphql_explore"),
        ("https://www.instagram.com/graphql/query/?query_hash=e769aa130647d2571c27c36fb2e5eefbv&variables=%7B%22first%22%3A20%7D", "graphql_feed"),
        # Public web data endpoint
        ("https://www.instagram.com/api/v1/web/explore/explore_landing/", "explore_landing"),
        ("https://www.instagram.com/api/v1/discover/web/explore/", "web_explore"),
    ]

    for url, name in endpoints:
        try:
            print(f"  Testing: {name} ({url[:60]}...)")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=10000)
            results["endpoints_tested"] += 1

            if resp:
                status = resp.status
                ct = resp.headers.get("content-type", "")
                print(f"    Status: {status}, Content-Type: {ct[:50]}")

                if status == 200 and "json" in ct:
                    try:
                        data = await resp.json()
                        # Check for ad-related fields
                        data_str = json.dumps(data)[:2000]
                        has_ads = any(k in data_str for k in [
                            '"is_ad"', '"ad_id"', '"is_sponsored"',
                            '"sponsored"', '"ad_action"',
                        ])
                        print(f"    JSON size: {len(data_str)} chars, "
                              f"has_ads: {has_ads}")
                        if has_ads:
                            print(f"    *** AD DATA FOUND ***")
                        api_results.append({
                            "endpoint": name,
                            "status": status,
                            "has_ads": has_ads,
                            "data_preview": data_str[:200],
                        })
                    except Exception:
                        pass
                elif status in (401, 403, 429):
                    print(f"    -> Access denied (auth required)")
                    api_results.append({
                        "endpoint": name, "status": status, "has_ads": False,
                    })
                else:
                    # Check if redirected to login
                    current = page.url.lower()
                    if "login" in current:
                        print(f"    -> Redirected to login page")
                    api_results.append({
                        "endpoint": name, "status": status, "has_ads": False,
                    })

        except Exception as exc:
            print(f"    -> Error: {str(exc)[:100]}")
            api_results.append({
                "endpoint": name, "error": str(exc)[:100],
            })

    results["api_results"] = api_results
    results["ads_found"] = sum(1 for r in api_results if r.get("has_ads"))

    summary = capture.summary()
    results["network_summary"] = summary

    print(f"\n  Endpoints tested: {results['endpoints_tested']}")
    print(f"  Endpoints with ads: {results['ads_found']}")

    await page.close()
    await ctx.close()
    return results


# ================================================================
# APPROACH 4: Facebook Audience Network on Korean sites
# ================================================================

async def test_audience_network(browser) -> dict:
    """Visit Korean sites that use Facebook Audience Network."""
    print("\n" + "=" * 60)
    print("APPROACH 4: Facebook Audience Network on Korean Sites")
    print("=" * 60)

    capture = NetworkCapture()
    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()
    page.on("response", capture.on_response)

    results = {"approach": "audience_network", "sites_visited": 0, "ads_found": 0}
    an_captures = []

    # Korean sites known to use Facebook Audience Network
    korean_sites = [
        "https://m.insight.co.kr/",
        "https://m.wikitree.co.kr/",
        "https://m.dispatch.co.kr/",
        "https://m.topstarnews.net/",
        "https://m.instiz.net/",
        "https://m.theqoo.net/",
        "https://m.pann.nate.com/",
        "https://m.ruliweb.com/",
        "https://m.fmkorea.com/",
        "https://m.ppomppu.co.kr/",
    ]

    for site_url in korean_sites[:6]:
        try:
            print(f"  Visiting: {site_url}")
            resp = await page.goto(
                site_url, wait_until="domcontentloaded", timeout=15000,
            )
            results["sites_visited"] += 1

            if resp:
                print(f"    Status: {resp.status}")

            await page.wait_for_timeout(3000)

            # Scroll to trigger lazy ads
            for i in range(5):
                await page.evaluate(f"window.scrollBy(0, {400 + i * 150})")
                await page.wait_for_timeout(800)

            await page.wait_for_timeout(2000)

            # Check for Facebook SDK / AN presence
            try:
                fb_info = await page.evaluate("""() => {
                    return {
                        hasFBSDK: typeof window.FB !== 'undefined',
                        hasAN: !!document.querySelector('[data-ad-slot*="facebook"], [data-ad*="audience"]'),
                        fbScripts: Array.from(document.querySelectorAll('script[src]'))
                            .map(s => s.src)
                            .filter(s => s.includes('facebook') || s.includes('fbcdn')),
                        adIframes: Array.from(document.querySelectorAll('iframe'))
                            .map(f => f.src)
                            .filter(s => s && (s.includes('facebook') || s.includes('an.') || s.includes('doubleclick'))),
                    }
                }""")
                if fb_info.get("fbScripts") or fb_info.get("adIframes"):
                    print(f"    FB scripts: {len(fb_info.get('fbScripts', []))}")
                    print(f"    Ad iframes: {len(fb_info.get('adIframes', []))}")
                    for iframe_src in fb_info.get("adIframes", [])[:3]:
                        print(f"      iframe: {iframe_src[:80]}")
            except Exception:
                pass

        except Exception as exc:
            print(f"    -> Error: {str(exc)[:100]}")

    summary = capture.summary()
    results["network_summary"] = summary
    results["ads_found"] = summary["ad_related_requests"]

    # Filter for an.facebook.com specifically
    an_urls = [u for u in summary["ad_urls"] if "an.facebook.com" in u]
    results["an_facebook_urls"] = len(an_urls)

    print(f"\n  Sites visited: {results['sites_visited']}")
    print(f"  Ad-related requests: {summary['ad_related_requests']}")
    print(f"  an.facebook.com requests: {len(an_urls)}")
    if summary["ad_urls"]:
        print(f"  Ad URLs found:")
        for u in summary["ad_urls"][:15]:
            print(f"    - {u}")

    await page.close()
    await ctx.close()
    return results


# ================================================================
# APPROACH 5: Instagram Explore Page variations
# ================================================================

async def test_explore_variations(browser) -> dict:
    """Test Instagram explore page variations (tags, locations)."""
    print("\n" + "=" * 60)
    print("APPROACH 5: Instagram Explore Page Variations")
    print("=" * 60)

    capture = NetworkCapture()
    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()
    page.on("response", capture.on_response)

    results = {"approach": "explore_variations", "pages_visited": 0, "ads_found": 0}

    explore_urls = [
        # Hashtag pages (public)
        "https://www.instagram.com/explore/tags/seoul/",
        "https://www.instagram.com/explore/tags/korea/",
        "https://www.instagram.com/explore/tags/fashion/",
        "https://www.instagram.com/explore/tags/beauty/",
        # Location pages (public)
        "https://www.instagram.com/explore/locations/236693918/seoul-korea/",
        "https://www.instagram.com/explore/locations/213163910/gangnam-gu/",
        # Topic/category explore
        "https://www.instagram.com/explore/",
        # Direct topic URLs
        "https://www.instagram.com/topics/beauty/",
        "https://www.instagram.com/topics/food/",
    ]

    for url in explore_urls:
        try:
            print(f"  Visiting: {url}")
            resp = await page.goto(
                url, wait_until="domcontentloaded", timeout=12000,
            )
            results["pages_visited"] += 1

            current = page.url.lower()
            print(f"    Final URL: {current[:80]}")

            if "login" in current or "accounts" in current:
                print(f"    -> Redirected to login")
                continue

            if resp:
                print(f"    Status: {resp.status}")

            # Dismiss popups
            try:
                await page.evaluate("""() => {
                    const btns = document.querySelectorAll('button, div[role="button"]');
                    for (const btn of btns) {
                        const t = (btn.textContent || '').trim();
                        if (/Not Now|Later|Close|Cancel/i.test(t)) { btn.click(); break; }
                    }
                    const overlay = document.querySelector('div[class*="RnEpo"]');
                    if (overlay) overlay.remove();
                }""")
            except Exception:
                pass

            await page.wait_for_timeout(2000)

            # Scroll
            for i in range(5):
                await page.evaluate(f"window.scrollBy(0, {400 + i * 100})")
                await page.wait_for_timeout(600)

            await page.wait_for_timeout(1500)

        except Exception as exc:
            print(f"    -> Error: {str(exc)[:100]}")

    summary = capture.summary()
    results["network_summary"] = summary
    results["ads_found"] = summary["extracted_ads"]

    print(f"\n  Pages visited: {results['pages_visited']}")
    print(f"  Network: {summary['total_requests']} total, "
          f"{summary['ad_related_requests']} ad-related, "
          f"{summary['extracted_ads']} extracted ads")
    if summary["ad_urls"]:
        print(f"  Ad URLs found:")
        for u in summary["ad_urls"][:10]:
            print(f"    - {u}")

    await page.close()
    await ctx.close()
    return results


# ================================================================
# APPROACH 6: Meta Ad Library API (graph.facebook.com)
# ================================================================

async def test_ad_library_api(browser) -> dict:
    """Test the Meta Ad Library API for structured ad data."""
    print("\n" + "=" * 60)
    print("APPROACH 6: Meta Ad Library API (graph.facebook.com)")
    print("=" * 60)

    capture = NetworkCapture()
    ctx = await create_context(browser, mobile=False)
    page = await ctx.new_page()
    page.on("response", capture.on_response)

    results = {"approach": "ad_library_api", "endpoints_tested": 0, "ads_found": 0}
    api_results = []

    # Test the Ad Library API endpoints
    # The public Ad Library API requires an access token, but let's check
    # what's available without one and what the web interface exposes.
    endpoints = [
        # Public API (may require token)
        (
            "https://graph.facebook.com/ads_archive"
            "?search_terms=samsung&ad_reached_countries=['KR']"
            "&ad_active_status=ACTIVE&publisher_platform=instagram"
            "&fields=ad_creative_bodies,ad_creative_link_titles,"
            "ad_creative_link_captions,page_name,publisher_platforms"
            "&limit=25",
            "ads_archive_api"
        ),
        # Ad Library report endpoint
        (
            "https://www.facebook.com/ads/library/report/"
            "?source=archive-landing-page&country=KR",
            "ad_library_report"
        ),
        # Ad Library search API (used by the web UI)
        (
            "https://www.facebook.com/ads/library/"
            "?active_status=active&ad_type=all&country=KR"
            "&publisher_platforms[0]=instagram&q=samsung"
            "&search_type=keyword_unordered",
            "ad_library_web"
        ),
    ]

    for url, name in endpoints:
        try:
            print(f"  Testing: {name}")
            print(f"    URL: {url[:100]}...")

            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            results["endpoints_tested"] += 1

            if resp:
                status = resp.status
                ct = resp.headers.get("content-type", "")
                print(f"    Status: {status}, CT: {ct[:50]}")

                current = page.url
                print(f"    Final URL: {current[:80]}")

                if status == 200:
                    if "json" in ct:
                        try:
                            data = await resp.json()
                            data_str = json.dumps(data, ensure_ascii=False)[:1000]
                            print(f"    JSON preview: {data_str[:200]}")
                            api_results.append({
                                "endpoint": name, "status": status,
                                "data": data_str[:500],
                            })
                        except Exception:
                            pass
                    elif "html" in ct:
                        # Web UI - check if ads loaded
                        await page.wait_for_timeout(5000)
                        # Scroll to load more
                        for i in range(5):
                            await page.evaluate(f"window.scrollBy(0, {800 + i * 100})")
                            await page.wait_for_timeout(1000)

                        try:
                            ad_count = await page.evaluate("""() => {
                                const cards = document.querySelectorAll(
                                    '[data-testid*="ad-content"], div[role="article"]'
                                );
                                return cards.length;
                            }""")
                            print(f"    Ad cards found: {ad_count}")
                            api_results.append({
                                "endpoint": name, "status": status,
                                "ad_cards": ad_count,
                            })
                        except Exception:
                            pass
                else:
                    try:
                        body = await resp.text()
                        print(f"    Error body: {body[:200]}")
                    except Exception:
                        pass
                    api_results.append({
                        "endpoint": name, "status": status,
                    })

        except Exception as exc:
            print(f"    -> Error: {str(exc)[:100]}")

    # Check what API calls the web UI makes
    print(f"\n  Checking Ad Library web UI API calls...")
    relevant_api_urls = [
        u for u in capture.all_urls
        if "graph.facebook.com" in u or "ads/library" in u or "ads_archive" in u
    ]
    if relevant_api_urls:
        print(f"  API calls detected ({len(relevant_api_urls)}):")
        for u in relevant_api_urls[:10]:
            print(f"    - {u[:120]}")

    summary = capture.summary()
    results["network_summary"] = summary
    results["api_results"] = api_results
    results["api_urls_detected"] = relevant_api_urls[:10]

    await page.close()
    await ctx.close()
    return results


# ================================================================
# APPROACH 7: Instagram Reels Web
# ================================================================

async def test_reels_web(browser) -> dict:
    """Test Instagram Reels web page for ad content."""
    print("\n" + "=" * 60)
    print("APPROACH 7: Instagram Reels Web")
    print("=" * 60)

    capture = NetworkCapture()
    ctx = await create_context(browser, mobile=True)
    page = await ctx.new_page()
    page.on("response", capture.on_response)

    results = {"approach": "reels_web", "pages_visited": 0, "ads_found": 0}

    reels_urls = [
        "https://www.instagram.com/reels/",
        "https://www.instagram.com/reels/videos/",
        "https://www.instagram.com/reels/trending/",
    ]

    for url in reels_urls:
        try:
            print(f"  Visiting: {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            results["pages_visited"] += 1

            current = page.url.lower()
            print(f"    Final URL: {current[:80]}")

            if "login" in current or "accounts" in current:
                print(f"    -> Redirected to login")
                continue

            if resp:
                print(f"    Status: {resp.status}")

            # Dismiss popups
            try:
                await page.evaluate("""() => {
                    const btns = document.querySelectorAll('button, div[role="button"]');
                    for (const btn of btns) {
                        const t = (btn.textContent || '').trim();
                        if (/Not Now|Later|Close/i.test(t)) { btn.click(); break; }
                    }
                    const overlay = document.querySelector('div[class*="RnEpo"]');
                    if (overlay) overlay.remove();
                }""")
            except Exception:
                pass

            await page.wait_for_timeout(3000)

            # Scroll/swipe through reels
            for i in range(10):
                await page.evaluate(f"window.scrollBy(0, {600 + i * 50})")
                await page.wait_for_timeout(1500)

            # Check page content
            try:
                page_info = await page.evaluate("""() => {
                    return {
                        title: document.title,
                        videoCount: document.querySelectorAll('video').length,
                        hasContent: document.body ? document.body.innerText.length > 100 : false,
                    }
                }""")
                print(f"    Videos: {page_info.get('videoCount', 0)}, "
                      f"Has content: {page_info.get('hasContent', False)}")
            except Exception:
                pass

        except Exception as exc:
            print(f"    -> Error: {str(exc)[:100]}")

    # Also try accessing individual popular reels if we can find shortcodes
    try:
        print(f"\n  Trying to find individual reel shortcodes...")
        await page.goto(
            "https://www.instagram.com/explore/",
            wait_until="domcontentloaded", timeout=12000,
        )
        try:
            await page.evaluate("""() => {
                const btns = document.querySelectorAll('button, div[role="button"]');
                for (const btn of btns) {
                    const t = (btn.textContent || '').trim();
                    if (/Not Now|Later|Close/i.test(t)) { btn.click(); break; }
                }
                const overlay = document.querySelector('div[class*="RnEpo"]');
                if (overlay) overlay.remove();
            }""")
        except Exception:
            pass

        await page.wait_for_timeout(2000)

        reel_links = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/reel/"]');
            return Array.from(links).slice(0, 5).map(a => a.href);
        }""")

        if reel_links:
            print(f"  Found {len(reel_links)} reel links")
            for reel_url in reel_links[:3]:
                try:
                    print(f"  Visiting reel: {reel_url[:60]}")
                    await page.goto(
                        reel_url, wait_until="domcontentloaded", timeout=10000,
                    )
                    await page.wait_for_timeout(3000)
                    results["pages_visited"] += 1
                except Exception as exc:
                    print(f"    -> Error: {str(exc)[:80]}")
        else:
            print("  No reel links found on explore page")

    except Exception as exc:
        print(f"  Reel discovery error: {str(exc)[:100]}")

    summary = capture.summary()
    results["network_summary"] = summary
    results["ads_found"] = summary["extracted_ads"]

    print(f"\n  Pages visited: {results['pages_visited']}")
    print(f"  Network: {summary['total_requests']} total, "
          f"{summary['ad_related_requests']} ad-related, "
          f"{summary['extracted_ads']} extracted ads")
    if summary["ad_urls"]:
        print(f"  Ad URLs found:")
        for u in summary["ad_urls"][:10]:
            print(f"    - {u}")

    await page.close()
    await ctx.close()
    return results


# ================================================================
# MAIN
# ================================================================

async def main():
    print("=" * 60)
    print("  Instagram Alternative Ad Capture Test")
    print("  Testing 7 approaches for non-login ad capture")
    print("=" * 60)

    pw, browser = await create_browser()

    all_results = {}
    approaches = [
        ("1_threads", test_threads),
        ("2_embeds", test_embeds),
        ("3_api_endpoints", test_api_endpoints),
        ("4_audience_network", test_audience_network),
        ("5_explore_variations", test_explore_variations),
        ("6_ad_library_api", test_ad_library_api),
        ("7_reels_web", test_reels_web),
    ]

    for name, test_fn in approaches:
        try:
            t0 = time.time()
            result = await asyncio.wait_for(test_fn(browser), timeout=120)
            result["elapsed_sec"] = round(time.time() - t0, 1)
            all_results[name] = result
        except asyncio.TimeoutError:
            print(f"\n  [TIMEOUT] {name} exceeded 120s limit")
            all_results[name] = {"approach": name, "error": "timeout"}
        except Exception as exc:
            print(f"\n  [ERROR] {name}: {str(exc)[:200]}")
            all_results[name] = {"approach": name, "error": str(exc)[:200]}

    await browser.close()
    await pw.stop()

    # ---- Final Summary ----
    print("\n" + "=" * 60)
    print("  FINAL SUMMARY")
    print("=" * 60)

    for name, result in all_results.items():
        ads = result.get("ads_found", 0)
        elapsed = result.get("elapsed_sec", "?")
        error = result.get("error", "")
        net = result.get("network_summary", {})
        ad_reqs = net.get("ad_related_requests", 0)

        status = "ADS FOUND" if ads > 0 else ("ERROR" if error else "NO ADS")
        print(f"  {name:25s} | {status:10s} | "
              f"ads={ads:3d} | ad_reqs={ad_reqs:3d} | {elapsed}s")
        if error:
            print(f"    Error: {error[:80]}")

    # Save detailed results
    output_path = Path(_root) / "scripts" / "ig_alternatives_results.json"
    # Serialize results (remove non-serializable items)
    serializable = {}
    for k, v in all_results.items():
        serializable[k] = {
            sk: sv for sk, sv in v.items()
            if isinstance(sv, (str, int, float, bool, list, dict, type(None)))
        }
    output_path.write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  Detailed results saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
