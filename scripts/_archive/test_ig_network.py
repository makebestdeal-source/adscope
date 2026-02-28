"""Instagram network request debugger - check what API calls happen during browsing."""
import asyncio
import io
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

os.environ["INSTAGRAM_USERNAME"] = "makebestdeal@gmail.com"
os.environ["INSTAGRAM_PASSWORD"] = "pjm990101@"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")


async def main():
    from playwright.async_api import async_playwright
    import random

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 430, "height": 932},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.4 Mobile/15E148 Safari/604.1"
            ),
            is_mobile=True,
            has_touch=True,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        # Track all API requests
        api_urls = []
        graphql_count = [0]
        api_v1_count = [0]

        async def on_response(response):
            url = response.url
            # Count relevant endpoints
            if "/graphql" in url:
                graphql_count[0] += 1
                ct = response.headers.get("content-type", "")
                size = len(await response.body()) if response.status == 200 else 0
                api_urls.append(f"[GRAPHQL] {response.status} {url[:120]} ct={ct[:30]} size={size}")
            elif "/api/v1/" in url:
                api_v1_count[0] += 1
                ct = response.headers.get("content-type", "")
                api_urls.append(f"[API_V1] {response.status} {url[:120]} ct={ct[:30]}")
            elif "instagram.com" in url and response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct or "javascript" in ct:
                    api_urls.append(f"[OTHER] {response.status} {url[:120]} ct={ct[:30]}")

        page.on("response", on_response)

        # Login
        print("[*] Logging in...")
        await page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        try:
            await page.fill('input[name="username"]', os.environ["INSTAGRAM_USERNAME"])
            await page.fill('input[name="password"]', os.environ["INSTAGRAM_PASSWORD"])
            await asyncio.sleep(0.5)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"[!] Login failed: {e}")

        print(f"[*] Current URL: {page.url}")
        if "accounts/login" in page.url.lower():
            print("[!] Still on login page")
        else:
            print("[+] Login OK")

        # Browse feed
        print("\n[*] Browsing home feed...")
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        for i in range(5):
            await page.evaluate(f"window.scrollBy(0, {400 + i*100})")
            await page.wait_for_timeout(random.randint(1500, 2500))

        # Browse explore
        print("[*] Browsing explore...")
        await page.goto("https://www.instagram.com/explore/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        for i in range(3):
            await page.evaluate(f"window.scrollBy(0, {400 + i*100})")
            await page.wait_for_timeout(random.randint(1500, 2500))

        # Browse reels
        print("[*] Browsing reels...")
        await page.goto("https://www.instagram.com/reels/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        for i in range(3):
            await page.evaluate(f"window.scrollBy(0, {600 + i*100})")
            await page.wait_for_timeout(random.randint(1500, 2500))

        print(f"\n{'='*60}")
        print(f"GraphQL requests: {graphql_count[0]}")
        print(f"API v1 requests: {api_v1_count[0]}")
        print(f"Total tracked requests: {len(api_urls)}")
        print(f"{'='*60}")
        for u in api_urls[:50]:
            print(f"  {u}")
        if len(api_urls) > 50:
            print(f"  ... +{len(api_urls)-50} more")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
