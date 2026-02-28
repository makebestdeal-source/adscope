"""Debug the coauthor extraction to see exactly what the API returns."""
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
    """)

    page = await ctx.new_page()
    captured = []

    async def on_response(response: Response):
        url = response.url
        if response.status != 200:
            return
        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        if "web_profile_info" in url or ("/graphql/" in url and "instagram.com" in url):
            try:
                body = await response.text()
                if body and len(body) > 500:
                    data = json.loads(body)
                    captured.append({
                        "url": url[:200],
                        "size": len(body),
                        "data": data,
                    })
                    print(f"  Captured: {url[:80]} ({len(body)} bytes)")
            except Exception as exc:
                print(f"  Parse error: {exc}")

    page.on("response", on_response)

    # Visit Samsung profile
    print("Visiting Samsung profile...")
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

    # Scroll
    for i in range(3):
        await page.evaluate(f"window.scrollBy(0, {500 + i * 200})")
        await page.wait_for_timeout(800)

    await page.wait_for_timeout(2000)

    print(f"\nCaptured {len(captured)} responses")

    for cap in captured:
        data = cap["data"]
        url = cap["url"]

        if "web_profile_info" in url:
            print(f"\n=== web_profile_info response ({cap['size']} bytes) ===")
            user_data = data.get("data", {}).get("user", {})
            if user_data:
                username = user_data.get("username", "?")
                print(f"  Username: {username}")

                # Check timeline media
                media = user_data.get("edge_owner_to_timeline_media", {})
                edges = media.get("edges", []) if isinstance(media, dict) else []
                print(f"  Timeline posts: {len(edges)}")

                for i, edge in enumerate(edges[:12]):
                    node = edge.get("node", {})
                    coauthors = node.get("coauthor_producers") or []
                    shortcode = node.get("shortcode", "")

                    caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
                    text = ""
                    if caption_edges:
                        text = caption_edges[0].get("node", {}).get("text", "")[:60]
                    text_safe = text.encode("ascii", "replace").decode("ascii")

                    if coauthors:
                        coauthor_names = []
                        for ca in coauthors:
                            if isinstance(ca, dict):
                                ca_name = ca.get("username", "?")
                                coauthor_names.append(ca_name)
                        print(f"  [{i}] COAUTHOR: {shortcode} coauthors={coauthor_names} text={text_safe}")
                    elif i < 3:
                        # Print first few normal posts too
                        all_keys = list(node.keys())
                        print(f"  [{i}] normal: {shortcode} keys={all_keys[:10]} text={text_safe}")

                    # Check all keys that might be ad-related
                    ad_keys = [k for k in node.keys() if any(
                        w in k.lower() for w in ['ad', 'sponsor', 'partner', 'brand', 'paid', 'coauthor', 'collab']
                    )]
                    if ad_keys:
                        vals = {k: node[k] for k in ad_keys}
                        print(f"        ad-related keys: {vals}")
            else:
                # Different data structure?
                print(f"  No user data found. Top keys: {list(data.keys())}")
                if "data" in data:
                    inner = data["data"]
                    if isinstance(inner, dict):
                        print(f"  data keys: {list(inner.keys())}")

        elif "/graphql/" in url:
            print(f"\n=== GraphQL response ({cap['size']} bytes) ===")
            data_str = json.dumps(data)[:200]
            print(f"  Preview: {data_str}")

    await page.close()
    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
