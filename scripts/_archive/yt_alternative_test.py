"""YouTube ad capture alternative approaches test.

Tests 7 different methods to capture YouTube ads in headless mode.
Each approach is tested independently with real network interception.
"""
import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, unquote, quote

from playwright.async_api import async_playwright, Response, Page, BrowserContext

# ---- Shared State ----
RESULTS = {}

# Test video URLs (popular, monetized)
TEST_VIDEOS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Astley
    "https://www.youtube.com/watch?v=9bZkp7q19f0",  # Gangnam Style
]

# ---- Shared Helpers ----

def safe_print(msg: str):
    """Windows cp949-safe print."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode())


class AdTracker:
    """Track ad-related network requests for a test."""
    def __init__(self, label: str):
        self.label = label
        self.ad_network_hits: list[dict] = []
        self.player_api_ads: list[dict] = []
        self.doubleclick_hits: list[str] = []
        self.pagead_hits: list[str] = []
        self.stats_pings: list[str] = []
        self.ad_slot_detected = False
        self.dom_ad_detected = False
        self.all_urls: list[str] = []

    async def on_response(self, response: Response):
        url = response.url
        self.all_urls.append(url[:200])
        try:
            # Player API
            if "youtubei/v1/player" in url and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    data = await response.json()
                    placements = data.get("adPlacements", [])
                    player_ads = data.get("playerAds", [])
                    if placements or player_ads:
                        self.player_api_ads.append({
                            "placements": len(placements),
                            "playerAds": len(player_ads),
                        })
                        safe_print(f"    [{self.label}] PLAYER API: {len(placements)} placements, {len(player_ads)} playerAds")
                return

            # Doubleclick
            if "doubleclick.net" in url:
                self.doubleclick_hits.append(url[:200])
                if response.status == 200:
                    try:
                        body = await response.text()
                        ad_urls = re.findall(r"adurl=([^&\"'<>\s]+)", body)
                        for au in ad_urls:
                            decoded = unquote(au)
                            if decoded.startswith("http"):
                                domain = urlparse(decoded).netloc
                                self.ad_network_hits.append({
                                    "source": "doubleclick",
                                    "advertiser": domain,
                                    "url": decoded[:150],
                                })
                                safe_print(f"    [{self.label}] DOUBLECLICK AD: {domain}")
                    except Exception:
                        pass
                return

            # Pagead
            if "youtube.com/pagead/" in url or "googlesyndication.com" in url:
                self.pagead_hits.append(url[:200])
                return

            # Stats
            if "youtube.com/api/stats/ads" in url:
                self.stats_pings.append(url[:200])
                safe_print(f"    [{self.label}] AD STATS PING")
                return

        except Exception:
            pass

    def summary(self) -> dict:
        return {
            "player_api_ads": len(self.player_api_ads),
            "doubleclick_hits": len(self.doubleclick_hits),
            "pagead_hits": len(self.pagead_hits),
            "stats_pings": len(self.stats_pings),
            "ad_network_hits": len(self.ad_network_hits),
            "ad_slot_detected": self.ad_slot_detected,
            "dom_ad_detected": self.dom_ad_detected,
            "total_urls": len(self.all_urls),
        }

    @property
    def has_ads(self) -> bool:
        return (
            len(self.player_api_ads) > 0
            or len(self.ad_network_hits) > 0
            or len(self.stats_pings) > 0
            or self.ad_slot_detected
            or self.dom_ad_detected
        )


async def check_ad_slot(page: Page, tracker: AdTracker):
    """Check ytInitialPlayerResponse for ad slots."""
    try:
        result = await page.evaluate("""() => {
            const pr = window.ytInitialPlayerResponse;
            if (!pr) return null;
            const placements = pr.adPlacements || [];
            if (placements.length === 0) return null;
            return { slotCount: placements.length };
        }""")
        if result and result.get("slotCount", 0) > 0:
            tracker.ad_slot_detected = True
            safe_print(f"    [{tracker.label}] AD SLOT DETECTED: {result['slotCount']} slots")
    except Exception:
        pass


async def check_dom_ad(page: Page, tracker: AdTracker):
    """Check DOM for ad-showing class."""
    try:
        ad_playing = await page.evaluate("""() => {
            const player = document.querySelector('.html5-video-player, #movie_player');
            if (!player) return false;
            return player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting');
        }""")
        if ad_playing:
            tracker.dom_ad_detected = True
            safe_print(f"    [{tracker.label}] DOM AD-SHOWING DETECTED!")
    except Exception:
        pass


async def play_video(page: Page):
    """Try to play the video."""
    try:
        await page.evaluate("""() => {
            const v = document.querySelector('video');
            if (v) { v.muted = true; v.play().catch(() => {}); }
            const btn = document.querySelector('.ytp-large-play-button, .ytp-play-button, [aria-label*="Play"]');
            if (btn) btn.click();
        }""")
    except Exception:
        pass


async def watch_and_check(page: Page, tracker: AdTracker, wait_sec: int = 15):
    """Watch video and check for ads over time."""
    await play_video(page)
    await check_ad_slot(page, tracker)

    check_interval = (wait_sec * 1000) // 5
    for i in range(5):
        await page.wait_for_timeout(check_interval)
        await check_dom_ad(page, tracker)
        if tracker.dom_ad_detected:
            break


# ==================================================================
# APPROACH 1: YouTube Embed / IFrame
# ==================================================================
async def test_embed_iframe():
    """Test: Embed YouTube videos in a local HTML page with IFrame Player API."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 1: YouTube Embed / IFrame Player API")
    safe_print("=" * 60)

    tracker = AdTracker("EMBED")

    # Create local HTML with embedded YouTube players
    html_content = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>YT Embed Test</title></head>
<body>
<h1>YouTube Embed Ad Test</h1>
<!-- Standard iframe embeds with ads enabled -->
<iframe id="yt1" width="640" height="360"
    src="https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1&mute=1&enablejsapi=1"
    frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>
<br>
<iframe id="yt2" width="640" height="360"
    src="https://www.youtube.com/embed/9bZkp7q19f0?autoplay=1&mute=1&enablejsapi=1"
    frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>

<!-- IFrame Player API -->
<div id="player3"></div>
<script>
var tag = document.createElement('script');
tag.src = "https://www.youtube.com/iframe_api";
var firstScriptTag = document.getElementsByTagName('script')[0];
firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
var player;
function onYouTubeIframeAPIReady() {
    player = new YT.Player('player3', {
        height: '360', width: '640',
        videoId: 'kJQP7kiw5Fk',
        playerVars: { 'autoplay': 1, 'mute': 1 },
        events: {
            'onReady': function(e) { e.target.playVideo(); },
            'onStateChange': function(e) {
                window.__ytState = e.data;
            }
        }
    });
}
</script>
</body></html>"""

    html_path = Path(tempfile.gettempdir()) / "yt_embed_test.html"
    html_path.write_text(html_content, encoding="utf-8")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-web-security",  # Allow cross-origin iframe
                "--enable-gpu",
                "--enable-webgl",
            ],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await ctx.new_page()
        page.on("response", tracker.on_response)

        safe_print(f"  Loading local HTML with embedded YouTube players...")
        await page.goto(f"file:///{html_path.as_posix()}", wait_until="domcontentloaded")
        safe_print(f"  Waiting 20 seconds for embeds to load and serve ads...")
        await page.wait_for_timeout(20000)

        # Check iframe states
        try:
            state = await page.evaluate("() => window.__ytState")
            safe_print(f"  IFrame API player state: {state}")
        except Exception:
            pass

        # Also check for ad-related network via frame inspection
        frames = page.frames
        safe_print(f"  Number of frames: {len(frames)}")
        for frame in frames:
            url = frame.url
            if "youtube" in url:
                safe_print(f"  Frame: {url[:100]}")

        await browser.close()

    summary = tracker.summary()
    RESULTS["1_embed_iframe"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    safe_print(f"  doubleclick hits: {len(tracker.doubleclick_hits)}")
    safe_print(f"  pagead hits: {len(tracker.pagead_hits)}")
    return tracker.has_ads


# ==================================================================
# APPROACH 2: User Data Directory (Persistent Profile)
# ==================================================================
async def test_user_data_dir():
    """Test: Launch with --user-data-dir for persistent browser profile."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 2: User Data Directory (Persistent Profile)")
    safe_print("=" * 60)

    tracker = AdTracker("USER_DATA_DIR")

    # Create a persistent profile directory
    profile_dir = Path(tempfile.gettempdir()) / "yt_test_profile"
    profile_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        # Launch with persistent context (user-data-dir)
        safe_print(f"  Profile dir: {profile_dir}")
        safe_print(f"  Launching with persistent context...")

        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
                "--enable-gpu",
                "--enable-webgl",
                "--lang=ko-KR",
                "--window-size=1920,1080",
            ],
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # Add stealth scripts
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
        """)

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        page.on("response", tracker.on_response)

        # Set consent cookies
        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
            {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
             "domain": ".youtube.com", "path": "/"},
        ])

        # Phase 1: Build browsing history (seed the profile)
        safe_print("  Phase 1: Seeding profile with browsing history...")
        try:
            await page.goto("https://www.google.com/search?q=korean+music+2024&hl=ko", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            await page.goto("https://www.naver.com", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
        except Exception as e:
            safe_print(f"  Seeding failed: {e}")

        # Phase 2: Visit YouTube and watch videos
        safe_print("  Phase 2: Loading YouTube videos...")
        for video_url in TEST_VIDEOS[:2]:
            vid = video_url.split("v=")[1]
            safe_print(f"  Watching: {vid}")

            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await watch_and_check(page, tracker, wait_sec=15)
                safe_print(f"    Video {vid} done. Ads so far: {tracker.has_ads}")
            except Exception as e:
                safe_print(f"    Error: {e}")

        await ctx.close()

    summary = tracker.summary()
    RESULTS["2_user_data_dir"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker.has_ads


# ==================================================================
# APPROACH 3: CDP (Chrome DevTools Protocol) Direct
# ==================================================================
async def test_cdp_direct():
    """Test: Use CDP directly for lower-level network interception."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 3: CDP Direct Network Interception")
    safe_print("=" * 60)

    tracker = AdTracker("CDP")
    cdp_network_requests: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--enable-gpu",
                "--enable-webgl",
                "--lang=ko-KR",
            ],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await ctx.new_page()

        # Also attach standard response handler
        page.on("response", tracker.on_response)

        # Create CDP session
        cdp = await ctx.new_cdp_session(page)

        # Enable network at CDP level
        await cdp.send("Network.enable")

        # CDP-level network interception
        def on_cdp_request(params):
            url = params.get("request", {}).get("url", "")
            if any(d in url for d in (
                "doubleclick.net", "youtube.com/pagead/",
                "googlesyndication.com", "youtube.com/api/stats/ads",
                "youtubei/v1/player",
            )):
                cdp_network_requests.append({
                    "url": url[:200],
                    "method": params.get("request", {}).get("method", ""),
                    "type": params.get("type", ""),
                })
                if "doubleclick" in url:
                    safe_print(f"    [CDP] doubleclick request: {url[:100]}")
                elif "pagead" in url:
                    safe_print(f"    [CDP] pagead request: {url[:100]}")
                elif "stats/ads" in url:
                    safe_print(f"    [CDP] stats/ads request")
                elif "player" in url:
                    safe_print(f"    [CDP] player API request")

        cdp.on("Network.requestWillBeSent", on_cdp_request)

        # Also try to modify browser properties via CDP
        try:
            # Override webdriver detection
            await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    if (!window.chrome) window.chrome = {};
                    if (!window.chrome.runtime) window.chrome.runtime = { connect: () => {}, sendMessage: () => {} };
                """
            })
        except Exception as e:
            safe_print(f"  CDP script injection: {e}")

        # Set cookies
        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
        ])

        safe_print("  Loading YouTube videos with CDP interception...")
        for video_url in TEST_VIDEOS[:2]:
            vid = video_url.split("v=")[1]
            safe_print(f"  Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await watch_and_check(page, tracker, wait_sec=15)
            except Exception as e:
                safe_print(f"    Error: {e}")

        await cdp.detach()
        await browser.close()

    summary = tracker.summary()
    summary["cdp_ad_requests"] = len(cdp_network_requests)
    RESULTS["3_cdp_direct"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  CDP ad-related requests: {len(cdp_network_requests)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker.has_ads


# ==================================================================
# APPROACH 4: Playwright-Stealth Package
# ==================================================================
async def test_playwright_stealth():
    """Test: Use playwright-stealth package for browser-level patching."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 4: Playwright-Stealth Package")
    safe_print("=" * 60)

    try:
        from playwright_stealth import stealth_async
    except ImportError:
        safe_print("  ERROR: playwright-stealth not installed. Run: pip install playwright-stealth")
        RESULTS["4_playwright_stealth"] = {"error": "not installed"}
        return False

    tracker = AdTracker("STEALTH")

    async with async_playwright() as p:
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
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = await ctx.new_page()

        # Apply playwright-stealth
        await stealth_async(page)
        safe_print("  playwright-stealth applied!")

        page.on("response", tracker.on_response)

        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
            {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
             "domain": ".youtube.com", "path": "/"},
        ])

        # Verify stealth is working
        safe_print("  Checking stealth effectiveness...")
        try:
            await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            stealth_check = await page.evaluate("""() => {
                return {
                    webdriver: navigator.webdriver,
                    chrome: !!window.chrome,
                    chromeRuntime: !!window.chrome?.runtime,
                    plugins: navigator.plugins.length,
                    languages: navigator.languages,
                };
            }""")
            safe_print(f"  Stealth check: {json.dumps(stealth_check)}")
        except Exception as e:
            safe_print(f"  Stealth check error: {e}")

        safe_print("  Loading YouTube videos with stealth...")
        for video_url in TEST_VIDEOS[:2]:
            vid = video_url.split("v=")[1]
            safe_print(f"  Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await watch_and_check(page, tracker, wait_sec=15)
            except Exception as e:
                safe_print(f"    Error: {e}")

        await browser.close()

    summary = tracker.summary()
    RESULTS["4_playwright_stealth"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker.has_ads


# ==================================================================
# APPROACH 5: YouTube Music
# ==================================================================
async def test_youtube_music():
    """Test: YouTube Music may have different ad serving."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 5: YouTube Music")
    safe_print("=" * 60)

    tracker = AdTracker("YT_MUSIC")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--enable-gpu",
                "--enable-webgl",
                "--lang=ko-KR",
            ],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await ctx.new_page()
        page.on("response", tracker.on_response)

        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
        ])

        # YouTube Music
        music_urls = [
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=9bZkp7q19f0",
        ]

        safe_print("  Testing YouTube Music...")
        for url in music_urls:
            vid = url.split("v=")[1]
            safe_print(f"  Playing: {vid}")
            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)

                # Try to play
                try:
                    await page.evaluate("""() => {
                        const v = document.querySelector('video');
                        if (v) { v.muted = true; v.play().catch(() => {}); }
                        const btns = document.querySelectorAll('button, tp-yt-paper-icon-button');
                        for (const b of btns) {
                            if (b.getAttribute('aria-label')?.includes('Play') ||
                                b.getAttribute('aria-label')?.includes('play')) {
                                b.click(); break;
                            }
                        }
                    }""")
                except Exception:
                    pass

                # Wait for ads
                for i in range(5):
                    await page.wait_for_timeout(3000)
                    await check_dom_ad(page, tracker)
                    if tracker.dom_ad_detected:
                        break

                safe_print(f"    Done. Page title: {(await page.title())[:60]}")
            except Exception as e:
                safe_print(f"    Error: {e}")

        await browser.close()

    summary = tracker.summary()
    RESULTS["5_youtube_music"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker.has_ads


# ==================================================================
# APPROACH 6: YouTube on External Sites
# ==================================================================
async def test_external_embeds():
    """Test: YouTube videos embedded on external Korean news sites."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 6: YouTube on External Sites (Korean News)")
    safe_print("=" * 60)

    tracker = AdTracker("EXTERNAL")

    # Korean news/media sites that commonly embed YouTube videos
    external_urls = [
        "https://www.chosun.com/entertainments/",
        "https://www.donga.com/news/Entertainment",
        "https://sports.news.naver.com/",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--enable-gpu",
                "--lang=ko-KR",
            ],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await ctx.new_page()
        page.on("response", tracker.on_response)

        # Strategy: Find pages with YouTube embeds, then monitor ad traffic
        safe_print("  Searching for pages with YouTube embeds...")

        yt_embed_found = 0

        for site_url in external_urls:
            try:
                safe_print(f"  Visiting: {site_url[:60]}")
                await page.goto(site_url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(3000)

                # Scroll to load more content
                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, 600)")
                    await page.wait_for_timeout(1000)

                # Check for YouTube iframes
                yt_frames = await page.evaluate("""() => {
                    const iframes = document.querySelectorAll('iframe');
                    const ytFrames = [];
                    for (const f of iframes) {
                        const src = f.src || f.getAttribute('data-src') || '';
                        if (src.includes('youtube.com') || src.includes('youtu.be')) {
                            ytFrames.push(src);
                        }
                    }
                    return ytFrames;
                }""")

                if yt_frames:
                    yt_embed_found += len(yt_frames)
                    safe_print(f"    Found {len(yt_frames)} YouTube embeds!")
                    for yf in yt_frames[:3]:
                        safe_print(f"      {yf[:100]}")

                # Also look for YouTube links to follow
                yt_links = await page.evaluate("""() => {
                    const links = document.querySelectorAll('a[href*="youtube.com/watch"], a[href*="youtu.be/"]');
                    return Array.from(links).slice(0, 5).map(a => a.href);
                }""")

                if yt_links:
                    safe_print(f"    Found {len(yt_links)} YouTube links")
                    # Visit first link with YouTube embed
                    for link in yt_links[:1]:
                        try:
                            safe_print(f"    Following link: {link[:80]}")
                            await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                            await page.wait_for_timeout(5000)
                            await watch_and_check(page, tracker, wait_sec=10)
                        except Exception:
                            pass

            except Exception as e:
                safe_print(f"    Error visiting {site_url[:40]}: {str(e)[:60]}")

        # Also directly test an embed page
        safe_print("  Direct embed test on a simple page...")
        embed_html = """<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
<iframe width="640" height="360"
    src="https://www.youtube.com/embed/dQw4w9WgXcQ?autoplay=1&mute=1"
    allow="autoplay; encrypted-media" allowfullscreen></iframe>
</body></html>"""
        embed_path = Path(tempfile.gettempdir()) / "yt_external_embed.html"
        embed_path.write_text(embed_html, encoding="utf-8")

        try:
            await page.goto(f"file:///{embed_path.as_posix()}", wait_until="domcontentloaded")
            await page.wait_for_timeout(15000)
        except Exception:
            pass

        await browser.close()

    summary = tracker.summary()
    summary["yt_embeds_found"] = yt_embed_found
    RESULTS["6_external_embeds"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  YouTube embeds found on external sites: {yt_embed_found}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker.has_ads


# ==================================================================
# APPROACH 7: Mobile Web (m.youtube.com)
# ==================================================================
async def test_mobile_web():
    """Test: Mobile YouTube with full device emulation."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 7: Mobile Web (m.youtube.com)")
    safe_print("=" * 60)

    tracker = AdTracker("MOBILE")

    # Mobile device profiles
    devices_to_test = [
        {
            "name": "Galaxy S21",
            "user_agent": (
                "Mozilla/5.0 (Linux; Android 13; SM-G991B) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Mobile Safari/537.36"
            ),
            "viewport": {"width": 360, "height": 800},
            "device_scale_factor": 3,
            "is_mobile": True,
            "has_touch": True,
        },
        {
            "name": "iPhone 14",
            "user_agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "CriOS/121.0.6167.171 Mobile/15E148 Safari/604.1"
            ),
            "viewport": {"width": 390, "height": 844},
            "device_scale_factor": 3,
            "is_mobile": True,
            "has_touch": True,
        },
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--autoplay-policy=no-user-gesture-required",
                "--enable-gpu",
                "--lang=ko-KR",
            ],
        )

        for device_info in devices_to_test:
            safe_print(f"\n  Testing device: {device_info['name']}")

            ctx = await browser.new_context(
                viewport=device_info["viewport"],
                user_agent=device_info["user_agent"],
                is_mobile=device_info["is_mobile"],
                has_touch=device_info["has_touch"],
                device_scale_factor=device_info["device_scale_factor"],
                locale="ko-KR",
                timezone_id="Asia/Seoul",
            )

            # Stealth
            await ctx.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            page = await ctx.new_page()
            page.on("response", tracker.on_response)

            await ctx.add_cookies([
                {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
                 "domain": ".youtube.com", "path": "/"},
            ])

            # Use m.youtube.com
            mobile_videos = [
                "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
                "https://m.youtube.com/watch?v=9bZkp7q19f0",
            ]

            for video_url in mobile_videos:
                vid = video_url.split("v=")[1]
                safe_print(f"    Watching: {vid}")
                try:
                    await page.goto(video_url, wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                    # Mobile-specific play
                    try:
                        await page.evaluate("""() => {
                            const v = document.querySelector('video');
                            if (v) { v.muted = true; v.play().catch(() => {}); }
                            // Mobile play button
                            const btns = document.querySelectorAll(
                                '.ytp-large-play-button, button[aria-label*="play" i], .player-controls-play-pause-button'
                            );
                            for (const b of btns) b.click();
                        }""")
                    except Exception:
                        pass

                    # Simulate touch event to play
                    try:
                        await page.tap("video")
                    except Exception:
                        pass

                    await watch_and_check(page, tracker, wait_sec=12)

                except Exception as e:
                    safe_print(f"      Error: {e}")

            await ctx.close()

        await browser.close()

    summary = tracker.summary()
    RESULTS["7_mobile_web"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker.has_ads


# ==================================================================
# APPROACH 4B: Stealth + CDP combined (bonus)
# ==================================================================
async def test_stealth_cdp_combined():
    """Test: Combine playwright-stealth + CDP + persistent profile."""
    safe_print("\n" + "=" * 60)
    safe_print("APPROACH 4B: Stealth + CDP + Persistent Profile Combined")
    safe_print("=" * 60)

    try:
        from playwright_stealth import stealth_async
    except ImportError:
        safe_print("  ERROR: playwright-stealth not installed")
        RESULTS["4b_combined"] = {"error": "not installed"}
        return False

    tracker = AdTracker("COMBINED")
    profile_dir = Path(tempfile.gettempdir()) / "yt_combined_profile"
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
                "--enable-gpu",
                "--enable-webgl",
                "--enable-webgl2",
                "--use-gl=angle",
                "--use-angle=default",
                "--disable-features=MediaCapabilitiesForAutoplay",
                "--enable-features=AudioServiceOutOfProcess",
                "--lang=ko-KR",
                "--window-size=1920,1080",
            ],
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Apply stealth
        await stealth_async(page)
        safe_print("  Stealth applied to persistent context!")

        # CDP session
        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Network.enable")

        cdp_ad_reqs = []
        def on_cdp_req(params):
            url = params.get("request", {}).get("url", "")
            if any(d in url for d in ("doubleclick.net", "pagead", "stats/ads")):
                cdp_ad_reqs.append(url[:200])

        cdp.on("Network.requestWillBeSent", on_cdp_req)

        page.on("response", tracker.on_response)

        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
            {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
             "domain": ".youtube.com", "path": "/"},
        ])

        # Seed with some browsing
        safe_print("  Seeding browsing history...")
        try:
            await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            # Scroll homepage
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        safe_print("  Testing videos...")
        for video_url in TEST_VIDEOS:
            vid = video_url.split("v=")[1]
            safe_print(f"  Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await watch_and_check(page, tracker, wait_sec=18)
            except Exception as e:
                safe_print(f"    Error: {e}")

        await cdp.detach()
        await ctx.close()

    summary = tracker.summary()
    summary["cdp_ad_requests"] = len(cdp_ad_reqs)
    RESULTS["4b_combined"] = summary
    safe_print(f"\n  RESULT: {json.dumps(summary, indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker.has_ads


# ==================================================================
# MAIN: Run all tests
# ==================================================================
async def main():
    safe_print("=" * 70)
    safe_print("  YouTube Ad Capture - Alternative Approaches Test Suite")
    safe_print("  Testing 7+ methods to capture YouTube ads in headless mode")
    safe_print("=" * 70)

    start = time.time()

    # Run tests sequentially (each needs its own browser)
    tests = [
        ("1. Embed/IFrame", test_embed_iframe),
        ("2. User Data Dir", test_user_data_dir),
        ("3. CDP Direct", test_cdp_direct),
        ("4. Playwright-Stealth", test_playwright_stealth),
        ("4b. Combined (Stealth+CDP+Profile)", test_stealth_cdp_combined),
        ("5. YouTube Music", test_youtube_music),
        ("6. External Embeds", test_external_embeds),
        ("7. Mobile Web", test_mobile_web),
    ]

    results_summary = {}
    for name, test_func in tests:
        try:
            safe_print(f"\n>>> Starting {name} <<<")
            result = await test_func()
            results_summary[name] = "ADS FOUND" if result else "NO ADS"
        except Exception as e:
            safe_print(f"  FATAL ERROR in {name}: {e}")
            results_summary[name] = f"ERROR: {str(e)[:50]}"

    elapsed = time.time() - start

    # Final summary
    safe_print("\n" + "=" * 70)
    safe_print("  FINAL RESULTS SUMMARY")
    safe_print("=" * 70)
    safe_print(f"  Total time: {elapsed:.1f} seconds\n")

    for name, result in results_summary.items():
        status = "OK" if "ADS FOUND" in result else "FAIL" if "NO ADS" in result else "ERR"
        safe_print(f"  [{status}] {name}: {result}")

    safe_print("\n  Detailed metrics:")
    for key, metrics in RESULTS.items():
        safe_print(f"\n  {key}:")
        if isinstance(metrics, dict):
            for mk, mv in metrics.items():
                safe_print(f"    {mk}: {mv}")

    safe_print("\n" + "=" * 70)

    # Write results to file for later analysis
    result_path = Path("c:/Users/user/Desktop/adscopre/scripts/yt_alt_results.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": elapsed,
            "summary": results_summary,
            "details": RESULTS,
        }, f, indent=2, default=str)
    safe_print(f"\n  Results saved to: {result_path}")


if __name__ == "__main__":
    asyncio.run(main())
