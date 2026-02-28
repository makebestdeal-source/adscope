"""Dump Instagram GraphQL responses to see actual data structure."""
import asyncio
import io
import json
import os
import sys
import random
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

os.environ["INSTAGRAM_USERNAME"] = "makebestdeal@gmail.com"
os.environ["INSTAGRAM_PASSWORD"] = "pjm990101@"


async def main():
    from playwright.async_api import async_playwright

    dump_dir = Path(_root) / "ig_debug_dump"
    dump_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
        ])
        context = await browser.new_context(
            viewport={"width": 430, "height": 932},
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.4 Mobile/15E148 Safari/604.1"
            ),
            is_mobile=True, has_touch=True,
            locale="ko-KR", timezone_id="Asia/Seoul",
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        # Load saved cookies
        cookie_store_path = Path(_root) / "cookie_store" / "M10_instagram.json"
        if cookie_store_path.exists():
            data = json.loads(cookie_store_path.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                print(f"[+] Loaded {len(cookies)} cookies")

        page = await context.new_page()
        dump_idx = [0]

        async def on_response(response):
            url = response.url
            if "/graphql" not in url:
                return
            if response.status != 200:
                return
            try:
                body = await response.text()
                if not body or len(body) < 100:
                    return
                data = json.loads(body)
                dump_idx[0] += 1
                fname = dump_dir / f"graphql_{dump_idx[0]:03d}.json"
                fname.write_text(json.dumps(data, ensure_ascii=False, indent=2)[:50000], encoding="utf-8")

                # Check for ad-related keys
                body_str = json.dumps(data)
                ad_keys = ["is_ad", "is_sponsored", "ad_id", "ad_action", "sponsor"]
                found_keys = [k for k in ad_keys if k in body_str]
                size = len(body)
                print(f"  [{dump_idx[0]}] {url[:80]} size={size} ad_keys={found_keys or 'none'}")
            except Exception as e:
                print(f"  [!] parse error: {e}")

        page.on("response", on_response)

        # Check login
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        if "accounts/login" in page.url.lower():
            print("[!] Not logged in, trying login...")
            await page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            try:
                await page.fill('input[name="username"]', os.environ["INSTAGRAM_USERNAME"])
                await page.fill('input[name="password"]', os.environ["INSTAGRAM_PASSWORD"])
                await asyncio.sleep(0.5)
                await page.click('button[type="submit"]')
                await page.wait_for_timeout(5000)
            except:
                pass
        else:
            print(f"[+] Already logged in: {page.url}")

        print("\n--- Browsing home feed ---")
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        for i in range(8):
            await page.evaluate(f"window.scrollBy(0, {400 + i*120})")
            await page.wait_for_timeout(random.randint(2000, 3000))

        print("\n--- Browsing explore ---")
        await page.goto("https://www.instagram.com/explore/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        for i in range(5):
            await page.evaluate(f"window.scrollBy(0, {400 + i*100})")
            await page.wait_for_timeout(random.randint(1500, 2500))

        print("\n--- Browsing reels ---")
        await page.goto("https://www.instagram.com/reels/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        for i in range(5):
            await page.evaluate(f"window.scrollBy(0, {600 + i*150})")
            await page.wait_for_timeout(random.randint(2000, 3000))

        print(f"\n{'='*50}")
        print(f"Total GraphQL dumps: {dump_idx[0]}")
        print(f"Saved to: {dump_dir}")
        print(f"{'='*50}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
