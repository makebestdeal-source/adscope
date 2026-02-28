"""Test playwright-stealth v2 with YouTube ad detection.

Also tests the best combination: stealth v2 + persistent profile.
"""
import asyncio
import json
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse, unquote

from playwright.async_api import async_playwright, Response
from playwright_stealth import Stealth


def safe_print(msg: str):
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode())


TEST_VIDEOS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=9bZkp7q19f0",
    "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
]


class AdTracker:
    def __init__(self, label: str):
        self.label = label
        self.ad_slots = []
        self.dom_ads = []
        self.stats_pings = []
        self.pagead_urls = []
        self.doubleclick_hits = []
        self.doubleclick_ads = []
        self.player_api_data = []

    async def on_response(self, response: Response):
        url = response.url
        try:
            if "youtubei/v1/player" in url and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    data = await response.json()
                    placements = data.get("adPlacements", [])
                    player_ads = data.get("playerAds", [])
                    if placements or player_ads:
                        self.player_api_data.append({
                            "placements": len(placements),
                            "playerAds": len(player_ads),
                        })
                        safe_print(f"    [{self.label}] PLAYER API: {len(placements)} placements, {len(player_ads)} playerAds")
                return

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
                                self.doubleclick_ads.append({"advertiser": domain, "url": decoded[:200]})
                                safe_print(f"    [{self.label}] DOUBLECLICK AD: {domain}")
                    except Exception:
                        pass
                return

            if "youtube.com/pagead/" in url or "googlesyndication.com" in url:
                self.pagead_urls.append(url[:200])
                if "/pagead/adview" in url or "/pagead/interaction" in url:
                    safe_print(f"    [{self.label}] AD IMPRESSION: {url[:100]}")
                return

            if "youtube.com/api/stats/ads" in url:
                self.stats_pings.append(url[:200])
                safe_print(f"    [{self.label}] AD STATS PING")
                return

        except Exception:
            pass

    def summary(self):
        return {
            "player_api_ads": len(self.player_api_data),
            "doubleclick_hits": len(self.doubleclick_hits),
            "doubleclick_ads": len(self.doubleclick_ads),
            "pagead_urls": len(self.pagead_urls),
            "stats_pings": len(self.stats_pings),
            "ad_slots": len(self.ad_slots),
            "dom_ads": len(self.dom_ads),
        }

    @property
    def has_ads(self):
        return (
            len(self.player_api_data) > 0
            or len(self.doubleclick_ads) > 0
            or len(self.stats_pings) > 0
            or len(self.dom_ads) > 0
            or len(self.ad_slots) > 0
        )


async def detect_ads(page, tracker):
    try:
        result = await page.evaluate("""() => {
            const pr = window.ytInitialPlayerResponse;
            if (!pr) return null;
            const placements = pr.adPlacements || [];
            if (placements.length === 0) return null;
            const slots = [];
            for (const p of placements) {
                const r = (p.adPlacementRenderer || {});
                const config = r.config || {};
                const kind = (config.adPlacementConfig || {}).kind || '';
                const renderer = r.renderer || {};
                const rendererType = Object.keys(renderer)[0] || 'unknown';
                slots.push({ kind, rendererType });
            }
            return { slotCount: placements.length, slots };
        }""")
        if result and result.get("slotCount", 0) > 0:
            tracker.ad_slots.append(result)
            safe_print(f"    [{tracker.label}] AD SLOTS: {result['slotCount']}")
            for s in result.get("slots", []):
                safe_print(f"      {s['kind']} -> {s['rendererType']}")
    except Exception:
        pass

    try:
        ad_playing = await page.evaluate("""() => {
            const player = document.querySelector('.html5-video-player, #movie_player');
            if (!player) return false;
            return player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting');
        }""")
        if ad_playing:
            tracker.dom_ads.append(True)
            safe_print(f"    [{tracker.label}] DOM AD-SHOWING!")
    except Exception:
        pass


async def play_and_watch(page, tracker, wait_sec=18):
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
    await detect_ads(page, tracker)

    check_interval = (wait_sec * 1000) // 6
    for i in range(6):
        await page.wait_for_timeout(check_interval)
        await detect_ads(page, tracker)


# ===========================================================
# Test 1: Stealth v2 with standard browser
# ===========================================================
async def test_stealth_standard():
    safe_print("\n" + "=" * 60)
    safe_print("TEST A: Stealth v2 - Standard Browser Context")
    safe_print("=" * 60)

    tracker = AdTracker("STEALTH_STD")
    stealth = Stealth()

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
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # Apply stealth to context
        await stealth.apply_stealth_async(ctx)
        safe_print("  Stealth applied to context!")

        page = await ctx.new_page()
        page.on("response", tracker.on_response)

        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
            {"name": "PREF", "value": "tz=Asia.Seoul&hl=ko&gl=KR",
             "domain": ".youtube.com", "path": "/"},
        ])

        # Check stealth effectiveness
        safe_print("  Verifying stealth...")
        try:
            await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            info = await page.evaluate("""() => ({
                webdriver: navigator.webdriver,
                chrome: !!window.chrome,
                plugins: navigator.plugins.length,
                connection: !!navigator.connection,
            })""")
            safe_print(f"  Stealth check: {json.dumps(info)}")
        except Exception as e:
            safe_print(f"  Check failed: {e}")

        for video_url in TEST_VIDEOS:
            vid = video_url.split("v=")[1]
            safe_print(f"\n  Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await play_and_watch(page, tracker, wait_sec=15)
            except Exception as e:
                safe_print(f"    Error: {e}")

        await browser.close()

    safe_print(f"\n  RESULT: {json.dumps(tracker.summary(), indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker


# ===========================================================
# Test 2: Stealth v2 + Persistent Profile
# ===========================================================
async def test_stealth_persistent():
    safe_print("\n" + "=" * 60)
    safe_print("TEST B: Stealth v2 + Persistent Profile")
    safe_print("=" * 60)

    tracker = AdTracker("STEALTH_PERSIST")
    stealth = Stealth()

    profile_dir = Path(tempfile.gettempdir()) / "yt_stealth_persist"
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
                "--enable-gpu",
                "--enable-webgl",
                "--enable-webgl2",
                "--lang=ko-KR",
                "--window-size=1920,1080",
            ],
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # Apply stealth to persistent context
        await stealth.apply_stealth_async(ctx)
        safe_print("  Stealth applied to persistent context!")

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
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, 500)")
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        for video_url in TEST_VIDEOS:
            vid = video_url.split("v=")[1]
            safe_print(f"\n  Watching: {vid}")
            try:
                await page.goto(video_url, wait_until="domcontentloaded")
                await page.wait_for_timeout(2000)
                await play_and_watch(page, tracker, wait_sec=18)
            except Exception as e:
                safe_print(f"    Error: {e}")

        await ctx.close()

    safe_print(f"\n  RESULT: {json.dumps(tracker.summary(), indent=2)}")
    safe_print(f"  HAS ADS: {tracker.has_ads}")
    return tracker


# ===========================================================
# MAIN
# ===========================================================
async def main():
    safe_print("=" * 70)
    safe_print("  Playwright-Stealth v2 + YouTube Ad Tests")
    safe_print("=" * 70)

    start = time.time()

    safe_print("\n>>> Test A: Stealth Standard <<<")
    t1 = await test_stealth_standard()

    safe_print("\n>>> Test B: Stealth + Persistent <<<")
    t2 = await test_stealth_persistent()

    elapsed = time.time() - start

    safe_print("\n\n" + "=" * 70)
    safe_print("  FINAL COMPARISON")
    safe_print("=" * 70)
    safe_print(f"  Time: {elapsed:.1f}s\n")

    for name, t in [("Stealth Standard", t1), ("Stealth + Persistent", t2)]:
        s = t.summary()
        has = t.has_ads
        safe_print(f"  [{('ADS' if has else 'NONE'):4s}] {name}:")
        safe_print(f"         slots={s['ad_slots']}, dom={s['dom_ads']}, player_api={s['player_api_ads']}")
        safe_print(f"         dc_hits={s['doubleclick_hits']}, dc_ads={s['doubleclick_ads']}")
        safe_print(f"         pagead={s['pagead_urls']}, pings={s['stats_pings']}")


if __name__ == "__main__":
    asyncio.run(main())
