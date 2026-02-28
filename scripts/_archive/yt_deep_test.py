"""Deep test of the most promising YouTube ad capture approaches.

Approach 2 (User Data Dir) and Approach 3 (CDP) both showed real ad activity.
This test does a thorough investigation with:
- More videos
- Longer wait times
- Detailed ad data extraction
- Comparison between approaches
- Playwright-stealth v2 API test
"""
import asyncio
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

from playwright.async_api import async_playwright, Response, Page


def safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode())


TEST_VIDEOS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=9bZkp7q19f0",
    "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
    "https://www.youtube.com/watch?v=hY7m5jjJ9mM",
    "https://www.youtube.com/watch?v=36YnV9STBqc",
]


class DetailedAdTracker:
    """Enhanced ad tracker with full data capture."""
    def __init__(self, label: str):
        self.label = label
        self.player_api_data: list[dict] = []
        self.doubleclick_ads: list[dict] = []
        self.pagead_urls: list[str] = []
        self.stats_pings: list[str] = []
        self.ad_slots: list[dict] = []
        self.dom_ads: list[dict] = []
        self.ad_break_urls: list[str] = []
        self.all_ad_urls: list[str] = []

    async def on_response(self, response: Response):
        url = response.url
        try:
            # Player API - extract full ad data
            if "youtubei/v1/player" in url and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    data = await response.json()
                    placements = data.get("adPlacements", [])
                    player_ads = data.get("playerAds", [])
                    if placements or player_ads:
                        self.player_api_data.append({
                            "placements_count": len(placements),
                            "player_ads_count": len(player_ads),
                            "placements_raw": placements[:2],  # Sample
                            "player_ads_raw": player_ads[:2],
                        })
                        safe_print(f"    [{self.label}] PLAYER API: {len(placements)} placements, {len(player_ads)} playerAds")

                        # Extract advertiser info from placements
                        for p in placements:
                            renderer = p.get("adPlacementRenderer", {})
                            items = renderer.get("renderer", {})
                            for key, val in items.items():
                                if isinstance(val, dict):
                                    adv = self._extract_advertiser(val)
                                    click = self._extract_click_url(val)
                                    if adv or click:
                                        safe_print(f"      Advertiser: {adv}, Click: {(click or '')[:80]}")
                return

            # get_midroll_info / ad_break
            if "get_midroll_info" in url or "get_ad_break" in url or "getAdBreakUrl" in url:
                self.ad_break_urls.append(url[:200])
                safe_print(f"    [{self.label}] AD BREAK URL: {url[:100]}")
                return

            # Doubleclick - detailed extraction
            if "doubleclick.net" in url:
                self.all_ad_urls.append(url[:200])
                if response.status == 200:
                    try:
                        body = await response.text()
                        ad_urls = re.findall(r"adurl=([^&\"'<>\s]+)", body)
                        for au in ad_urls:
                            decoded = unquote(au)
                            if decoded.startswith("http"):
                                domain = urlparse(decoded).netloc
                                self.doubleclick_ads.append({
                                    "advertiser": domain,
                                    "url": decoded[:200],
                                })
                                safe_print(f"    [{self.label}] DOUBLECLICK AD: {domain}")
                    except Exception:
                        pass
                return

            # Pagead
            if "youtube.com/pagead/" in url or "googlesyndication.com" in url:
                self.pagead_urls.append(url[:200])
                # Check for adview (actual ad impression)
                if "/pagead/adview" in url or "/pagead/interaction" in url:
                    safe_print(f"    [{self.label}] AD IMPRESSION/INTERACTION: {url[:100]}")
                return

            # Stats
            if "youtube.com/api/stats/ads" in url:
                self.stats_pings.append(url[:200])
                safe_print(f"    [{self.label}] AD STATS PING")
                return

        except Exception:
            pass

    def _extract_advertiser(self, val: dict) -> str:
        if val.get("advertiserName"):
            return val["advertiserName"]
        ad_title = val.get("adTitle", {})
        if isinstance(ad_title, dict):
            runs = ad_title.get("runs", [])
            if runs:
                return runs[0].get("text", "")
        headline = val.get("headline", {})
        if isinstance(headline, dict):
            return headline.get("simpleText", "")
        return ""

    def _extract_click_url(self, val: dict) -> str:
        for ep_key in ("clickthroughEndpoint", "navigationEndpoint", "urlEndpoint"):
            ep = val.get(ep_key, {})
            if isinstance(ep, dict):
                url_ep = ep.get("urlEndpoint", ep)
                if isinstance(url_ep, dict) and url_ep.get("url"):
                    return url_ep["url"]
        return ""

    def summary(self) -> dict:
        return {
            "player_api_ads": len(self.player_api_data),
            "doubleclick_ads": len(self.doubleclick_ads),
            "pagead_urls": len(self.pagead_urls),
            "stats_pings": len(self.stats_pings),
            "ad_slots": len(self.ad_slots),
            "dom_ads": len(self.dom_ads),
            "ad_break_urls": len(self.ad_break_urls),
            "total_ad_urls": len(self.all_ad_urls),
            "unique_advertisers": list(set(
                ad["advertiser"] for ad in self.doubleclick_ads if ad.get("advertiser")
            )),
        }

    @property
    def has_real_ads(self) -> bool:
        """Check if we got actual ad data (not just tracking/infrastructure)."""
        return (
            len(self.player_api_data) > 0
            or len(self.doubleclick_ads) > 0
            or len(self.stats_pings) > 0
            or len(self.dom_ads) > 0
        )


async def detect_ad_data(page: Page, tracker: DetailedAdTracker):
    """Extract ad data from page state."""
    # ytInitialPlayerResponse
    try:
        result = await page.evaluate("""() => {
            const pr = window.ytInitialPlayerResponse;
            if (!pr) return null;
            const placements = pr.adPlacements || [];
            const playerAds = pr.playerAds || [];
            if (placements.length === 0 && playerAds.length === 0) return null;

            const info = {
                slotCount: placements.length,
                playerAdsCount: playerAds.length,
                slots: []
            };

            for (const p of placements) {
                const r = (p.adPlacementRenderer || {});
                const config = r.config || {};
                const kind = (config.adPlacementConfig || {}).kind || '';
                const renderer = r.renderer || {};
                const rendererType = Object.keys(renderer)[0] || 'unknown';

                // Try to extract ad details
                const rendererData = renderer[rendererType] || {};
                const advertiser = rendererData.advertiserName || '';
                const adTitle = rendererData.adTitle;
                let titleText = '';
                if (adTitle && adTitle.runs) {
                    titleText = adTitle.runs.map(r => r.text).join('');
                } else if (adTitle && adTitle.simpleText) {
                    titleText = adTitle.simpleText;
                }

                info.slots.push({
                    kind, rendererType, advertiser, titleText: titleText.slice(0, 100)
                });
            }
            return info;
        }""")
        if result and (result.get("slotCount", 0) > 0 or result.get("playerAdsCount", 0) > 0):
            tracker.ad_slots.append(result)
            safe_print(f"    [{tracker.label}] AD SLOTS: {result['slotCount']} slots, {result.get('playerAdsCount', 0)} playerAds")
            for slot in result.get("slots", []):
                safe_print(f"      kind={slot['kind']}, type={slot['rendererType']}, adv={slot['advertiser']}, title={slot['titleText'][:50]}")
    except Exception:
        pass

    # DOM ad-showing
    try:
        dom_ad = await page.evaluate("""() => {
            const player = document.querySelector('.html5-video-player, #movie_player');
            if (!player) return null;
            const adShowing = player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting');
            if (!adShowing) return null;
            const getText = (sel) => {
                const el = document.querySelector(sel);
                return el ? el.textContent.trim() : null;
            };
            const getHref = (sel) => {
                const el = document.querySelector(sel);
                return el ? (el.href || null) : null;
            };
            return {
                ad_text: getText('.ytp-ad-text, .ytp-ad-preview-text'),
                cta_text: getText('.ytp-ad-button-text, .ytp-ad-visit-advertiser-button-text'),
                advertiser: getText('.ytp-ad-info-dialog-advertiser-name'),
                skip_text: getText('.ytp-skip-ad-button, .ytp-ad-skip-button-modern'),
                ad_url: getHref('a.ytp-ad-button, .ytp-ad-visit-advertiser-link'),
            };
        }""")
        if dom_ad:
            tracker.dom_ads.append(dom_ad)
            safe_print(f"    [{tracker.label}] DOM AD PLAYING! adv={dom_ad.get('advertiser')}, cta={dom_ad.get('cta_text')}, url={dom_ad.get('ad_url')}")
    except Exception:
        pass


async def play_and_watch(page: Page, tracker: DetailedAdTracker, wait_sec: int = 20):
    """Play video and monitor for ads with detailed extraction."""
    # Force play
    try:
        await page.evaluate("""() => {
            const v = document.querySelector('video');
            if (v) { v.muted = true; v.play().catch(() => {}); }
            const btn = document.querySelector('.ytp-large-play-button, .ytp-play-button');
            if (btn) btn.click();
        }""")
    except Exception:
        pass

    await page.wait_for_timeout(2000)
    await detect_ad_data(page, tracker)

    # Check periodically
    check_interval = (wait_sec * 1000) // 6
    for i in range(6):
        await page.wait_for_timeout(check_interval)
        await detect_ad_data(page, tracker)
        if tracker.dom_ads:
            break


# ==================================================================
# DEEP TEST: Persistent Profile + CDP
# ==================================================================
async def deep_test_persistent_cdp():
    """Comprehensive test combining persistent profile with CDP interception."""
    safe_print("\n" + "=" * 60)
    safe_print("DEEP TEST: Persistent Profile + CDP Interception")
    safe_print("=" * 60)

    tracker = DetailedAdTracker("DEEP")
    cdp_ad_reqs: list[dict] = []

    profile_dir = Path(tempfile.gettempdir()) / "yt_deep_profile"
    profile_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--enable-gpu",
                "--enable-webgl",
                "--enable-webgl2",
                "--use-gl=angle",
                "--use-angle=default",
                "--enable-features=AudioServiceOutOfProcess",
                "--disable-features=MediaCapabilitiesForAutoplay",
                "--disable-dev-shm-usage",
                "--lang=ko-KR",
                "--window-size=1920,1080",
            ],
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # Stealth init script
        await ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    const p = [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin' },
                    ];
                    p.length = 3;
                    return p;
                }
            });
            Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
            if (!window.chrome) window.chrome = {};
            if (!window.chrome.runtime) window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };
            if (!window.chrome.app) {
                window.chrome.app = {
                    isInstalled: false,
                    InstallState: {DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed'},
                    RunningState: {CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running'},
                    getDetails: function() { return null; },
                    getIsInstalled: function() { return false; },
                    installState: function(cb) { if (cb) cb('not_installed'); },
                };
            }
            if (!window.chrome.csi) {
                window.chrome.csi = function() {
                    return { startE: Date.now(), onloadT: Date.now(), pageT: Math.random() * 500, tran: 15 };
                };
            }
            if (!window.chrome.loadTimes) {
                window.chrome.loadTimes = function() {
                    return {
                        commitLoadTime: Date.now() / 1000, connectionInfo: 'h2',
                        finishDocumentLoadTime: Date.now() / 1000, finishLoadTime: Date.now() / 1000,
                        firstPaintTime: Date.now() / 1000, navigationType: 'Other',
                        npnNegotiatedProtocol: 'h2', requestTime: Date.now() / 1000 - 0.3,
                        startLoadTime: Date.now() / 1000 - 0.5, wasFetchedViaSpdy: true, wasNpnNegotiated: true,
                    };
                };
            }
            if (!navigator.connection) {
                Object.defineProperty(navigator, 'connection', {
                    get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10, saveData: false }),
                });
            }
            if (window.outerWidth === 0) {
                Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
                Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 85 });
            }
        """)

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page.on("response", tracker.on_response)

        # CDP
        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Network.enable")

        def on_cdp_req(params):
            url = params.get("request", {}).get("url", "")
            if any(d in url for d in (
                "doubleclick.net", "pagead", "stats/ads", "adservice",
                "youtubei/v1/player",
            )):
                cdp_ad_reqs.append({
                    "url": url[:200],
                    "type": params.get("type", ""),
                })

        cdp.on("Network.requestWillBeSent", on_cdp_req)

        # Consent cookies
        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
            {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
             "domain": ".youtube.com", "path": "/"},
        ])

        # Phase 1: Warm up the profile
        safe_print("\n  Phase 1: Warming up profile...")
        try:
            await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            # Scroll and browse
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(1500)
        except Exception as e:
            safe_print(f"    Warmup error: {e}")

        # Phase 2: Watch videos
        safe_print("\n  Phase 2: Watching videos for ad capture...")
        for i, video_url in enumerate(TEST_VIDEOS, 1):
            vid = video_url.split("v=")[1]
            safe_print(f"\n  [{i}/{len(TEST_VIDEOS)}] Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await play_and_watch(page, tracker, wait_sec=20)
                safe_print(f"    Video done. Total ads: slots={len(tracker.ad_slots)}, dom={len(tracker.dom_ads)}, dc={len(tracker.doubleclick_ads)}, pings={len(tracker.stats_pings)}")
            except Exception as e:
                safe_print(f"    Error: {e}")

            await page.wait_for_timeout(1000)

        await cdp.detach()
        await ctx.close()

    summary = tracker.summary()
    summary["cdp_ad_requests"] = len(cdp_ad_reqs)
    safe_print(f"\n  DEEP TEST RESULTS:")
    safe_print(f"  {json.dumps(summary, indent=2)}")
    return tracker, summary


# ==================================================================
# STEALTH v2 TEST
# ==================================================================
async def test_stealth_v2():
    """Test playwright-stealth v2 API."""
    safe_print("\n" + "=" * 60)
    safe_print("TEST: Playwright-Stealth v2.0")
    safe_print("=" * 60)

    try:
        from playwright_stealth import Stealth
        safe_print("  playwright_stealth.Stealth imported successfully!")
    except ImportError:
        safe_print("  ERROR: Cannot import Stealth from playwright_stealth")
        return None

    tracker = DetailedAdTracker("STEALTH_V2")

    async with async_playwright() as p:
        stealth = Stealth()

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--enable-gpu",
                "--enable-webgl",
                "--lang=ko-KR",
                "--window-size=1920,1080",
            ],
        )

        # Use Stealth to create context
        ctx = await stealth.create_context(
            browser,
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        page = await ctx.new_page()
        page.on("response", tracker.on_response)

        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
            {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
             "domain": ".youtube.com", "path": "/"},
        ])

        # Verify stealth
        safe_print("  Checking stealth effectiveness...")
        try:
            await page.goto("https://bot.sannysoft.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            stealth_info = await page.evaluate("""() => {
                return {
                    webdriver: navigator.webdriver,
                    chrome: !!window.chrome,
                    plugins: navigator.plugins.length,
                    languages: JSON.stringify(navigator.languages),
                    platform: navigator.platform,
                };
            }""")
            safe_print(f"  Stealth info: {json.dumps(stealth_info)}")
        except Exception as e:
            safe_print(f"  Stealth check error: {e}")

        safe_print("  Testing YouTube videos with stealth v2...")
        for video_url in TEST_VIDEOS[:3]:
            vid = video_url.split("v=")[1]
            safe_print(f"  Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await play_and_watch(page, tracker, wait_sec=15)
            except Exception as e:
                safe_print(f"    Error: {e}")

        await browser.close()

    summary = tracker.summary()
    safe_print(f"\n  STEALTH V2 RESULTS:")
    safe_print(f"  {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS REAL ADS: {tracker.has_real_ads}")
    return tracker, summary


# ==================================================================
# STEALTH v2 + PERSISTENT PROFILE TEST
# ==================================================================
async def test_stealth_v2_persistent():
    """Test playwright-stealth v2 with persistent profile."""
    safe_print("\n" + "=" * 60)
    safe_print("TEST: Playwright-Stealth v2.0 + Persistent Profile")
    safe_print("=" * 60)

    try:
        from playwright_stealth import Stealth
    except ImportError:
        safe_print("  ERROR: Cannot import Stealth")
        return None

    tracker = DetailedAdTracker("STEALTH_V2_PERSIST")
    profile_dir = Path(tempfile.gettempdir()) / "yt_stealth_v2_profile"
    profile_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        stealth = Stealth()

        ctx = await stealth.create_persistent_context(
            p.chromium,
            user_data_dir=str(profile_dir),
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--no-first-run",
                "--no-default-browser-check",
                "--enable-gpu",
                "--enable-webgl",
                "--lang=ko-KR",
                "--window-size=1920,1080",
            ],
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page.on("response", tracker.on_response)

        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
            {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
             "domain": ".youtube.com", "path": "/"},
        ])

        # Warm up
        safe_print("  Warming up...")
        try:
            await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
        except Exception:
            pass

        safe_print("  Testing YouTube videos...")
        for video_url in TEST_VIDEOS[:3]:
            vid = video_url.split("v=")[1]
            safe_print(f"  Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await play_and_watch(page, tracker, wait_sec=18)
            except Exception as e:
                safe_print(f"    Error: {e}")

        await ctx.close()

    summary = tracker.summary()
    safe_print(f"\n  STEALTH V2 + PERSISTENT RESULTS:")
    safe_print(f"  {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS REAL ADS: {tracker.has_real_ads}")
    return tracker, summary


# ==================================================================
# MAIN
# ==================================================================
async def main():
    safe_print("=" * 70)
    safe_print("  YouTube Ad Capture - Deep Investigation")
    safe_print("=" * 70)

    start = time.time()
    all_results = {}

    # Test 1: Deep persistent + CDP
    safe_print("\n\n>>> DEEP TEST: Persistent Profile + CDP <<<")
    tracker1, result1 = await deep_test_persistent_cdp()
    all_results["persistent_cdp"] = result1

    # Test 2: Stealth v2
    safe_print("\n\n>>> TEST: Stealth v2 <<<")
    res2 = await test_stealth_v2()
    if res2:
        tracker2, result2 = res2
        all_results["stealth_v2"] = result2

    # Test 3: Stealth v2 + Persistent
    safe_print("\n\n>>> TEST: Stealth v2 + Persistent <<<")
    res3 = await test_stealth_v2_persistent()
    if res3:
        tracker3, result3 = res3
        all_results["stealth_v2_persistent"] = result3

    elapsed = time.time() - start

    safe_print("\n\n" + "=" * 70)
    safe_print("  COMPREHENSIVE RESULTS")
    safe_print("=" * 70)
    safe_print(f"  Total time: {elapsed:.1f} seconds\n")

    for name, result in all_results.items():
        has_ads = (
            result.get("player_api_ads", 0) > 0
            or result.get("doubleclick_ads", 0) > 0
            or result.get("stats_pings", 0) > 0
            or result.get("dom_ads", 0) > 0
        )
        status = "ADS FOUND" if has_ads else "NO ADS"
        safe_print(f"\n  [{status}] {name}:")
        for k, v in result.items():
            safe_print(f"    {k}: {v}")

    # Save results
    result_path = Path("c:/Users/user/Desktop/adscopre/scripts/yt_deep_results.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": elapsed,
            "results": all_results,
        }, f, indent=2, default=str)
    safe_print(f"\n  Results saved to: {result_path}")


if __name__ == "__main__":
    asyncio.run(main())
