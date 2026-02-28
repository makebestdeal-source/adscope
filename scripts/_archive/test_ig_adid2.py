"""Capture ALL GraphQL responses and check for ANY ad-related fields."""
import asyncio
import io
import json
import os
import re
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["INSTAGRAM_USERNAME"] = "makebestdeal@gmail.com"
os.environ["INSTAGRAM_PASSWORD"] = "pjm990101@"


async def main():
    from playwright.async_api import async_playwright

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

        cookie_store_path = Path(_root) / "cookie_store" / "M10_instagram.json"
        if cookie_store_path.exists():
            data = json.loads(cookie_store_path.read_text(encoding="utf-8"))
            cookies = data.get("cookies", [])
            if cookies:
                await context.add_cookies(cookies)
                print(f"[+] Loaded {len(cookies)} cookies")

        page = await context.new_page()
        resp_count = [0]

        ad_patterns = ["ad_id", "is_ad", "is_sponsored", "sponsor", "ad_action",
                       "ad_type", "injected", "promoted", "boosted", "branded"]

        async def on_response(response):
            url = response.url
            if "/graphql" not in url or response.status != 200:
                return
            try:
                ct = response.headers.get("content-type", "")
                if "json" not in ct and "javascript" not in ct:
                    return
                body = await response.text()
                if not body or len(body) < 50:
                    return

                resp_count[0] += 1
                found = [p for p in ad_patterns if p in body.lower()]
                if found:
                    print(f"  [{resp_count[0]}] size={len(body):>8} ad_matches={found}")
                    # Show context for each match
                    for pat in found[:3]:
                        idx = body.lower().find(pat)
                        if idx >= 0:
                            start = max(0, idx - 100)
                            end = min(len(body), idx + 200)
                            ctx = body[start:end].replace('\n', ' ')[:300]
                            print(f"       {pat}: ...{ctx}...")
                else:
                    print(f"  [{resp_count[0]}] size={len(body):>8} (no ad fields)")
            except Exception as e:
                print(f"  [!] {e}")

        page.on("response", on_response)

        print("[*] Loading home page...")
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        print("\n[*] Scrolling feed...")
        for i in range(8):
            await page.evaluate(f"window.scrollBy(0, {500 + i * 100})")
            await page.wait_for_timeout(2500)

        print(f"\nTotal GraphQL responses: {resp_count[0]}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
