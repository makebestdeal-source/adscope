"""Quick: capture one GraphQL response and find ad_id context."""
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
        found_it = [False]

        async def on_response(response):
            if found_it[0]:
                return
            url = response.url
            if "/graphql" not in url or response.status != 200:
                return
            try:
                body = await response.text()
                if not body or len(body) < 10000:
                    return
                if "ad_id" not in body:
                    return

                found_it[0] = True
                print(f"\n[+] Found response with ad_id: size={len(body)}")

                # Find all ad_id contexts
                for m in re.finditer(r'"ad_id"', body):
                    start = max(0, m.start() - 300)
                    end = min(len(body), m.end() + 500)
                    ctx = body[start:end]
                    print(f"\n--- ad_id at pos {m.start()} ---")
                    print(ctx[:800])
                    print("---")

                # Also check structure
                data = json.loads(body)

                def find_ad_fields(obj, path="", depth=0, results=None):
                    if results is None:
                        results = []
                    if depth > 12:
                        return results
                    if isinstance(obj, dict):
                        if "ad_id" in obj:
                            info = {
                                "path": path,
                                "ad_id": obj.get("ad_id"),
                                "is_ad": obj.get("is_ad"),
                                "is_sponsored": obj.get("is_sponsored"),
                            }
                            user = obj.get("user") or obj.get("owner") or {}
                            if isinstance(user, dict):
                                info["username"] = user.get("username")
                            cap = obj.get("caption")
                            if isinstance(cap, dict):
                                info["caption"] = (cap.get("text") or "")[:100]
                            info["keys"] = sorted(obj.keys())[:20]
                            results.append(info)
                        for k, v in obj.items():
                            find_ad_fields(v, f"{path}.{k}", depth + 1, results)
                    elif isinstance(obj, list):
                        for i, v in enumerate(obj[:30]):
                            find_ad_fields(v, f"{path}[{i}]", depth + 1, results)
                    return results

                results = find_ad_fields(data)
                print(f"\n[+] Found {len(results)} nodes with ad_id")
                for r in results[:5]:
                    print(json.dumps(r, ensure_ascii=False, indent=2)[:500])

            except Exception as e:
                print(f"[!] Error: {e}")

        page.on("response", on_response)

        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        for i in range(5):
            await page.evaluate(f"window.scrollBy(0, {400 + i * 100})")
            await page.wait_for_timeout(2000)

        if not found_it[0]:
            print("[!] No GraphQL response with ad_id found during feed browse")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
