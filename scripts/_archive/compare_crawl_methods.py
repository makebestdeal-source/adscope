"""3가지 크롤링 방법 비교 테스트.

Method A: 기존 Playwright (vanilla, no stealth)
Method B: playwright-stealth (무료 안티봇 우회)
Method C: Bright Data Web Unlocker API (유료 프록시)

비교 항목: 수집 건수, 차단 여부, 소요 시간
대상 사이트: Naver, Kakao/Daum, YouTube, Coupang(차단 사이트)
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from playwright.async_api import async_playwright
from crawler.personas.device_config import PC_DEVICE, MOBILE_GALAXY

# ---------- Bright Data config ----------
BD_API_TOKEN = os.getenv("BRIGHTDATA_API_TOKEN", "b085557d-bdf5-4f35-9533-64ed4ade9c9e")
BD_WS_ENDPOINT = os.getenv("BRIGHTDATA_WS_ENDPOINT", "")

# ---------- Test targets ----------
TEST_SITES = [
    {
        "name": "Naver Main",
        "url": "https://www.naver.com/",
        "ad_patterns": ["siape.veta.naver.com", "adsun.naver.com", "adcr.naver.com",
                        "nstat.naver.com/m", "displayad.naver.com"],
        "blocked": False,
    },
    {
        "name": "Daum Main",
        "url": "https://www.daum.net/",
        "ad_patterns": ["display.ad.daum.net", "t1.daumcdn.net/adfit", "ad.daum.net",
                        "adfit.kakao.com", "track.tiara.kakao.com"],
        "blocked": False,
    },
    {
        "name": "YouTube Trending",
        "url": "https://www.youtube.com/feed/trending",
        "ad_patterns": ["doubleclick.net", "googlesyndication.com", "googleads.g.doubleclick",
                        "youtube.com/pagead", "youtube.com/api/stats/ads"],
        "blocked": False,
    },
    {
        "name": "Coupang Main",
        "url": "https://www.coupang.com/",
        "ad_patterns": ["ads.coupang.com", "display.coupang.com", "campaign",
                        "ad-api", "ad.coupang"],
        "blocked": True,
    },
]

# ---------- Stealth JS (same as base_crawler) ----------
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' },
    ],
});
Object.defineProperty(navigator, 'languages', { get: () => ['ko-KR', 'ko', 'en-US', 'en'] });
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, p);
};
"""


async def _capture_ads(page, url, ad_patterns, timeout_ms=15000):
    """Navigate and capture ad-related network responses."""
    captured = []

    async def on_response(response):
        resp_url = response.url
        for pat in ad_patterns:
            if pat in resp_url:
                try:
                    status = response.status
                    ct = response.headers.get("content-type", "")
                    size = 0
                    if status == 200 and ("json" in ct or "html" in ct or "javascript" in ct):
                        try:
                            body = await response.body()
                            size = len(body)
                        except Exception:
                            pass
                    captured.append({
                        "url": resp_url[:120],
                        "status": status,
                        "type": ct[:40],
                        "size": size,
                        "pattern": pat,
                    })
                except Exception:
                    captured.append({"url": resp_url[:120], "status": -1, "pattern": pat})
                break

    page.on("response", on_response)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        # Scroll and wait for ads to load
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 600)")
            await asyncio.sleep(1.0)
        await asyncio.sleep(2.0)
    except Exception as e:
        err_msg = str(e)[:80]
        logger.warning(f"Navigate error: {err_msg}")
        captured.append({"url": url, "status": -1, "error": err_msg, "pattern": "BLOCKED"})

    return captured


async def method_a_vanilla(site: dict) -> dict:
    """Method A: Vanilla Playwright (no stealth)."""
    t0 = time.time()
    result = {"method": "A_Vanilla", "site": site["name"], "ads": [], "blocked": False, "error": None}

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-first-run", "--no-default-browser-check", "--disable-infobars"],
        )
        ctx = await browser.new_context(
            viewport={"width": PC_DEVICE.viewport_width, "height": PC_DEVICE.viewport_height},
            user_agent=PC_DEVICE.user_agent,
        )
        page = await ctx.new_page()
        captured = await _capture_ads(page, site["url"], site["ad_patterns"])
        result["ads"] = captured
        if any(c.get("pattern") == "BLOCKED" for c in captured):
            result["blocked"] = True
        await browser.close()
    except Exception as e:
        result["error"] = str(e)[:100]
        result["blocked"] = True
    finally:
        await pw.stop()

    result["duration_s"] = round(time.time() - t0, 1)
    result["ad_count"] = len([a for a in result["ads"] if a.get("status", -1) == 200])
    return result


async def method_b_stealth(site: dict) -> dict:
    """Method B: playwright-stealth (free anti-bot bypass)."""
    t0 = time.time()
    result = {"method": "B_Stealth", "site": site["name"], "ads": [], "blocked": False, "error": None}

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
            ],
        )
        ctx = await browser.new_context(
            viewport={"width": PC_DEVICE.viewport_width, "height": PC_DEVICE.viewport_height},
            user_agent=PC_DEVICE.user_agent,
        )

        # Apply playwright-stealth v2.x API
        page = await ctx.new_page()
        from playwright_stealth import Stealth
        stealth = Stealth(
            navigator_languages_override=("ko-KR", "ko"),
            navigator_platform_override="Win32",
        )
        await stealth.apply_stealth_async(page)

        # Also inject manual stealth JS as extra layer
        await page.add_init_script(STEALTH_JS)

        captured = await _capture_ads(page, site["url"], site["ad_patterns"])
        result["ads"] = captured
        if any(c.get("pattern") == "BLOCKED" for c in captured):
            result["blocked"] = True
        await browser.close()
    except Exception as e:
        result["error"] = str(e)[:100]
        result["blocked"] = True
    finally:
        await pw.stop()

    result["duration_s"] = round(time.time() - t0, 1)
    result["ad_count"] = len([a for a in result["ads"] if a.get("status", -1) == 200])
    return result


async def method_c_brightdata(site: dict) -> dict:
    """Method C: Bright Data MCP hosted endpoint (scrape_as_markdown)."""
    t0 = time.time()
    result = {"method": "C_BrightData", "site": site["name"], "ads": [], "blocked": False, "error": None}

    if not BD_API_TOKEN:
        result["error"] = "No BRIGHTDATA_API_TOKEN"
        result["blocked"] = True
        result["duration_s"] = 0
        result["ad_count"] = 0
        return result

    import requests

    try:
        # Bright Data scrape_as_markdown via direct API
        # First try: Simple HTTPS GET via Bright Data proxy
        from urllib.parse import quote
        api_url = f"https://api.brightdata.com/datasets/v3/scrape?url={quote(site['url'])}&format=json"
        headers_bd = {"Authorization": f"Bearer {BD_API_TOKEN}"}
        resp = requests.get(api_url, headers=headers_bd, timeout=30)

        if resp.status_code == 200:
            try:
                data = resp.json()
                text = json.dumps(data, ensure_ascii=False)
            except Exception:
                text = resp.text
            text_len = len(text)

            ad_hits = []
            for pat in site["ad_patterns"]:
                count = text.lower().count(pat.lower())
                if count > 0:
                    ad_hits.append({"pattern": pat, "count": count, "status": 200})
            result["ads"] = ad_hits
            result["html_length"] = text_len
        else:
            # Fallback: Try MCP Streamable HTTP endpoint
            mcp_url = f"https://mcp.brightdata.com/sse?token={BD_API_TOKEN}"
            resp2 = requests.get(mcp_url, timeout=10, stream=True)
            if resp2.status_code == 200:
                # SSE established - send tool call
                result["error"] = f"MCP SSE OK but needs full client"
            else:
                result["error"] = f"API {resp.status_code}: {resp.text[:150]}"

    except Exception as e:
        result["error"] = str(e)[:100]
        result["blocked"] = True

    result["duration_s"] = round(time.time() - t0, 1)
    result["ad_count"] = len([a for a in result["ads"] if a.get("status", -1) == 200 or a.get("count", 0) > 0])
    return result


async def run_comparison():
    """Run all 3 methods on all test sites and compare."""
    logger.info("=" * 60)
    logger.info("Ad Crawling Method Comparison Test")
    logger.info("=" * 60)

    all_results = []

    for site in TEST_SITES:
        logger.info(f"\n--- Testing: {site['name']} ({site['url']}) ---")

        # Method A: Vanilla Playwright
        logger.info(f"[A] Vanilla Playwright...")
        ra = await method_a_vanilla(site)
        all_results.append(ra)
        logger.info(f"[A] {ra['site']}: {ra['ad_count']} ads, {ra['duration_s']}s, blocked={ra['blocked']}")

        # Method B: Stealth Playwright
        logger.info(f"[B] Stealth Playwright...")
        rb = await method_b_stealth(site)
        all_results.append(rb)
        logger.info(f"[B] {rb['site']}: {rb['ad_count']} ads, {rb['duration_s']}s, blocked={rb['blocked']}")

        # Method C: Bright Data
        logger.info(f"[C] Bright Data API...")
        rc = await method_c_brightdata(site)
        all_results.append(rc)
        logger.info(f"[C] {rc['site']}: {rc['ad_count']} ads, {rc['duration_s']}s, blocked={rc['blocked']}")

    # ── Summary Report ──
    logger.info("\n" + "=" * 70)
    logger.info("COMPARISON RESULTS")
    logger.info("=" * 70)
    logger.info(f"{'Site':<18} {'Method':<14} {'Ads':>5} {'Time':>6} {'Blocked':>8} {'Error'}")
    logger.info("-" * 70)

    for r in all_results:
        err = (r.get("error") or "-")[:30]
        logger.info(
            f"{r['site']:<18} {r['method']:<14} {r['ad_count']:>5} "
            f"{r['duration_s']:>5.1f}s {str(r['blocked']):>8} {err}"
        )

    # ── Per-site winner ──
    logger.info("\n--- Per-Site Winner ---")
    for site in TEST_SITES:
        site_results = [r for r in all_results if r["site"] == site["name"]]
        best = max(site_results, key=lambda x: (x["ad_count"], -x["duration_s"]))
        logger.info(f"  {site['name']}: {best['method']} ({best['ad_count']} ads)")

    # ── Totals ──
    for method in ["A_Vanilla", "B_Stealth", "C_BrightData"]:
        method_results = [r for r in all_results if r["method"] == method]
        total_ads = sum(r["ad_count"] for r in method_results)
        total_time = sum(r["duration_s"] for r in method_results)
        blocked = sum(1 for r in method_results if r["blocked"])
        logger.info(f"\n  {method}: Total {total_ads} ads, {total_time:.1f}s, {blocked} blocked")

    # Save results to file
    out_path = Path(_root) / "comparison_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"\nResults saved to {out_path}")

    return all_results


if __name__ == "__main__":
    asyncio.run(run_comparison())
