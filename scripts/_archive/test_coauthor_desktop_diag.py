"""Diagnose desktop context web_profile_info API - why 0 hits."""
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
os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

from playwright.async_api import async_playwright, Response


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )

    # Test 1: Standalone desktop context (like previous working test)
    print("=" * 60)
    print("  Test 1: Standalone desktop context (no crawler)")
    print("=" * 60)

    ctx = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        locale="ko-KR", timezone_id="Asia/Seoul",
    )
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
    """)

    page = await ctx.new_page()
    all_responses = []
    json_responses = []

    async def on_response(response: Response):
        url = response.url
        all_responses.append({
            "url": url[:150],
            "status": response.status,
            "ct": response.headers.get("content-type", "")[:50],
        })
        if response.status == 200:
            ct = response.headers.get("content-type", "")
            if "json" in ct and "instagram.com" in url:
                try:
                    body = await response.text()
                    json_responses.append({
                        "url": url[:150],
                        "size": len(body) if body else 0,
                    })
                    if "web_profile_info" in url:
                        print(f"  *** web_profile_info: {url[:100]} ({len(body)} bytes)")
                    elif "/graphql" in url:
                        print(f"  *** graphql: {url[:100]} ({len(body)} bytes)")
                    elif "/api/" in url:
                        print(f"  *** api: {url[:100]} ({len(body)} bytes)")
                except Exception:
                    pass

    page.on("response", on_response)

    # Visit innisfreeofficial
    print("  Visiting innisfreeofficial...")
    await page.goto("https://www.instagram.com/innisfreeofficial/",
                    wait_until="domcontentloaded", timeout=15000)

    # Check if redirected
    print(f"  URL after load: {page.url[:100]}")

    await page.wait_for_timeout(3000)

    # Scroll
    for i in range(4):
        await page.evaluate(f"window.scrollBy(0, {500 + i * 100})")
        await page.wait_for_timeout(800)

    await page.wait_for_timeout(2000)

    print(f"\n  Total responses: {len(all_responses)}")
    print(f"  JSON responses from instagram.com: {len(json_responses)}")
    for jr in json_responses:
        print(f"    - {jr['url'][:100]} ({jr['size']} bytes)")

    # Check some specific response patterns
    ig_responses = [r for r in all_responses if "instagram.com" in r["url"]]
    print(f"  Instagram responses total: {len(ig_responses)}")

    # Show non-200 responses
    non_200 = [r for r in ig_responses if r["status"] != 200]
    if non_200:
        print(f"  Non-200 Instagram responses:")
        for r in non_200[:10]:
            print(f"    {r['status']}: {r['url'][:80]}")

    # Show response by content-type
    ct_counts = {}
    for r in ig_responses:
        ct = r["ct"][:30] if r["ct"] else "(empty)"
        ct_counts[ct] = ct_counts.get(ct, 0) + 1
    print(f"  Response content-types:")
    for ct, count in sorted(ct_counts.items(), key=lambda x: -x[1]):
        print(f"    {ct}: {count}")

    await page.close()
    await ctx.close()

    # Test 2: Visit with the crawler's browser (same browser instance)
    print("\n" + "=" * 60)
    print("  Test 2: Visit samsung (second profile)")
    print("=" * 60)

    ctx2 = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        ),
        locale="ko-KR", timezone_id="Asia/Seoul",
    )
    await ctx2.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    page2 = await ctx2.new_page()
    json_responses2 = []

    async def on_response2(response: Response):
        url = response.url
        if response.status == 200:
            ct = response.headers.get("content-type", "")
            if "json" in ct and "instagram.com" in url:
                try:
                    body = await response.text()
                    json_responses2.append({
                        "url": url[:150],
                        "size": len(body) if body else 0,
                    })
                    if "web_profile_info" in url:
                        print(f"  *** web_profile_info: {url[:100]} ({len(body)} bytes)")
                    elif len(body) > 10000:
                        print(f"  *** large json: {url[:100]} ({len(body)} bytes)")
                except Exception:
                    pass

    page2.on("response", on_response2)

    print("  Visiting samsung...")
    await page2.goto("https://www.instagram.com/samsung/",
                    wait_until="domcontentloaded", timeout=15000)
    print(f"  URL after load: {page2.url[:100]}")

    await page2.wait_for_timeout(3000)
    for i in range(4):
        await page2.evaluate(f"window.scrollBy(0, {500 + i * 100})")
        await page2.wait_for_timeout(800)
    await page2.wait_for_timeout(2000)

    print(f"  JSON responses: {len(json_responses2)}")
    for jr in json_responses2:
        print(f"    - {jr['url'][:100]} ({jr['size']} bytes)")

    await page2.close()
    await ctx2.close()

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
