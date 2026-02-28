"""Check which API endpoints Instagram mobile uses for profiles."""
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
logger.add(sys.stderr, level="INFO")

from playwright.async_api import async_playwright, Response


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )

    # Mobile context (same as crawler uses)
    ctx = await browser.new_context(
        viewport={"width": 390, "height": 844},
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        is_mobile=True, has_touch=True,
        device_scale_factor=3,
        locale="ko-KR", timezone_id="Asia/Seoul",
    )

    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    page = await ctx.new_page()
    api_calls = []

    async def on_response(response: Response):
        url = response.url
        if response.status != 200:
            return
        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        if "instagram.com" in url and ("/api/" in url or "/graphql/" in url):
            try:
                body = await response.text()
                api_calls.append({
                    "url": url[:200],
                    "size": len(body) if body else 0,
                })
                # Check for coauthor data
                if body and "coauthor" in body:
                    print(f"  *** COAUTHOR data in: {url[:80]} ({len(body)} bytes)")
                if body and "web_profile_info" in url:
                    print(f"  *** web_profile_info: {url[:80]} ({len(body)} bytes)")
            except Exception:
                pass

    page.on("response", on_response)

    # Visit Samsung profile with mobile UA
    print("MOBILE CONTEXT:")
    print("  Visiting samsung profile...")
    await page.goto("https://www.instagram.com/samsung/", wait_until="domcontentloaded", timeout=15000)

    # Dismiss popups
    try:
        await page.evaluate("""() => {
            const overlay = document.querySelector('div[class*="RnEpo"]');
            if (overlay) overlay.remove();
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (/Not Now|Close/i.test(b.textContent)) b.click();
            }
        }""")
    except Exception:
        pass

    await page.wait_for_timeout(3000)
    for i in range(3):
        await page.evaluate(f"window.scrollBy(0, {500})")
        await page.wait_for_timeout(800)
    await page.wait_for_timeout(2000)

    print(f"  API calls captured: {len(api_calls)}")
    for call in api_calls:
        print(f"    - {call['url'][:100]} ({call['size']} bytes)")

    await page.close()
    await ctx.close()

    # Now try with desktop context
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
    api_calls2 = []

    async def on_response2(response: Response):
        url = response.url
        if response.status != 200:
            return
        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        if "instagram.com" in url and ("/api/" in url or "/graphql/" in url):
            try:
                body = await response.text()
                api_calls2.append({
                    "url": url[:200],
                    "size": len(body) if body else 0,
                })
                if body and "coauthor" in body:
                    print(f"  *** COAUTHOR data in: {url[:80]} ({len(body)} bytes)")
            except Exception:
                pass

    page2.on("response", on_response2)

    print("\nDESKTOP CONTEXT:")
    print("  Visiting samsung profile...")
    await page2.goto("https://www.instagram.com/samsung/", wait_until="domcontentloaded", timeout=15000)

    try:
        await page2.evaluate("""() => {
            const overlay = document.querySelector('div[class*="RnEpo"]');
            if (overlay) overlay.remove();
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (/Not Now|Close/i.test(b.textContent)) b.click();
            }
        }""")
    except Exception:
        pass

    await page2.wait_for_timeout(3000)
    for i in range(3):
        await page2.evaluate(f"window.scrollBy(0, {500})")
        await page2.wait_for_timeout(800)
    await page2.wait_for_timeout(2000)

    print(f"  API calls captured: {len(api_calls2)}")
    for call in api_calls2:
        print(f"    - {call['url'][:100]} ({call['size']} bytes)")

    await page2.close()
    await ctx2.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
