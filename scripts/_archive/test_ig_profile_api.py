"""Test Instagram web_profile_info API for ad/sponsor data.

The embeds deep-dive showed Instagram returns large JSON responses
(400KB+) from /api/v1/users/web_profile_info/ for public profiles.
These may contain branded_content or paid_partnership markers.

Also tests: Threads.net search with Korean queries for more scrolling.
"""
import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

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
    print("=" * 60)
    print("  Instagram Profile API & Threads Korean Search")
    print("=" * 60)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )

    # ================================================================
    # Part 1: Instagram web_profile_info API analysis
    # ================================================================
    print("\n--- Part 1: Instagram web_profile_info API ---")

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
    profile_data: list[dict] = []
    sponsored_posts: list[dict] = []

    async def on_profile_response(response: Response):
        url = response.url
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return

            if "web_profile_info" in url:
                body = await response.text()
                if body:
                    data = json.loads(body)
                    profile_data.append({
                        "url": url[:200],
                        "size": len(body),
                        "data": data,
                    })
                    # Walk for sponsored content
                    _walk_profile(data, sponsored_posts)

            elif "/graphql/" in url and "instagram.com" in url:
                body = await response.text()
                if body and len(body) > 500:
                    data = json.loads(body)
                    data_str = json.dumps(data)
                    markers = ["is_paid_partnership", "branded_content", "is_ad", "sponsor"]
                    found = [m for m in markers if m in data_str]
                    if found:
                        print(f"    GraphQL markers: {found} in {url[:60]}")
                        _walk_profile(data, sponsored_posts)

        except Exception:
            pass

    page.on("response", on_profile_response)

    # Visit Korean brand profiles
    brands = [
        "samsung", "hyundai", "innisfreeofficial", "oliveyoung",
        "nike", "adidas", "starbucks", "netflixkr",
        "samsungmobile", "coupang.official",
    ]

    for brand in brands:
        try:
            url = f"https://www.instagram.com/{brand}/"
            print(f"\n  Profile: {brand}")
            await page.goto(url, wait_until="domcontentloaded", timeout=12000)

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

            await page.wait_for_timeout(2000)

            # Scroll to load more posts
            for i in range(3):
                await page.evaluate(f"window.scrollBy(0, {600 + i * 200})")
                await page.wait_for_timeout(800)

        except Exception as exc:
            print(f"    Error: {str(exc)[:80]}")

    print(f"\n  Profile API responses: {len(profile_data)}")
    print(f"  Sponsored posts found: {len(sponsored_posts)}")

    # Analyze profile data structure
    for pd in profile_data[:3]:
        data = pd["data"]
        user_data = data.get("data", {}).get("user", {})
        if user_data:
            username = user_data.get("username", "?")
            media = user_data.get("edge_owner_to_timeline_media", {})
            edges = media.get("edges", []) if isinstance(media, dict) else []
            print(f"\n  Profile: {username}, posts: {len(edges)}")

            for i, edge in enumerate(edges[:12]):
                node = edge.get("node", {})
                is_ad = node.get("is_ad")
                is_pp = node.get("is_paid_partnership")
                bc_tag = node.get("coauthor_producers", [])
                sponsor = node.get("sponsor_users", [])
                text = ""
                captions = node.get("edge_media_to_caption", {}).get("edges", [])
                if captions:
                    text = captions[0].get("node", {}).get("text", "")[:60]
                text_safe = text.encode("ascii", "replace").decode("ascii")

                if is_ad or is_pp or bc_tag or sponsor:
                    print(f"    [{i}] **AD/SPONSOR** is_ad={is_ad} is_pp={is_pp} "
                          f"coauthor={len(bc_tag)} sponsor={len(sponsor)} "
                          f"text={text_safe}")
                elif i < 3:
                    print(f"    [{i}] normal: is_ad={is_ad} is_pp={is_pp} text={text_safe}")

    if sponsored_posts:
        print(f"\n  SPONSORED POSTS DETAIL:")
        for sp in sponsored_posts[:10]:
            print(f"    {sp}")

    await page.close()
    await ctx.close()

    # ================================================================
    # Part 2: Threads Korean search + extensive scrolling
    # ================================================================
    print("\n\n--- Part 2: Threads.net Korean Search ---")

    ctx2 = await browser.new_context(
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
    await ctx2.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    page2 = await ctx2.new_page()
    threads_graphql: list[dict] = []
    threads_ads: list[dict] = []

    async def on_threads_response(response: Response):
        url = response.url
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            if ("threads.com" in url or "threads.net" in url) and "/graphql" in url:
                body = await response.text()
                if body and len(body) > 100:
                    data = json.loads(body)
                    threads_graphql.append({"size": len(body)})

                    # Walk for paid partnerships
                    _walk_threads(data, threads_ads)
        except Exception:
            pass

    page2.on("response", on_threads_response)

    # Korean search queries
    queries = [
        "samsung korea",
        "hyundai",
        "nike korea",
        "beauty korea",
        "fashion seoul",
    ]

    for query in queries:
        try:
            url = f"https://www.threads.net/search?q={query}&serp_type=default"
            print(f"\n  Threads search: {query}")
            await page2.goto(url, wait_until="domcontentloaded", timeout=15000)
            current = page2.url.lower()
            if "login" in current:
                print("    -> Login redirect")
                continue

            await page2.wait_for_timeout(3000)

            # Scroll extensively
            for i in range(15):
                await page2.evaluate(f"window.scrollBy(0, {500 + i * 50})")
                await page2.wait_for_timeout(1000)

            print(f"    GraphQL: {len(threads_graphql)}, Ads: {len(threads_ads)}")

        except Exception as exc:
            print(f"    Error: {str(exc)[:80]}")

    # Also try Threads home with more scrolling
    print(f"\n  Threads home (extended scroll)...")
    try:
        await page2.goto("https://www.threads.net/", wait_until="domcontentloaded", timeout=15000)
        current = page2.url.lower()
        if "login" not in current:
            await page2.wait_for_timeout(3000)
            for i in range(40):
                await page2.evaluate(f"window.scrollBy(0, {600 + i * 30})")
                await page2.wait_for_timeout(800)
                if (i + 1) % 10 == 0:
                    print(f"    Scroll {i+1}/40 - GraphQL: {len(threads_graphql)}, Ads: {len(threads_ads)}")
    except Exception as exc:
        print(f"    Error: {str(exc)[:80]}")

    print(f"\n  THREADS RESULTS:")
    print(f"  GraphQL responses: {len(threads_graphql)}")
    print(f"  Ads/partnerships found: {len(threads_ads)}")
    if threads_ads:
        for ad in threads_ads[:10]:
            print(f"    - {ad}")

    await page2.close()
    await ctx2.close()

    await browser.close()
    await pw.stop()

    print(f"\n{'=' * 60}")
    print(f"  FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Instagram profile sponsored posts: {len(sponsored_posts)}")
    print(f"  Threads paid partnerships: {len(threads_ads)}")


def _walk_profile(data, results, depth=0):
    """Walk Instagram profile JSON for sponsored/ad content."""
    if depth > 20:
        return
    if isinstance(data, dict):
        # Check for various ad indicators
        if (data.get("is_ad") or data.get("is_paid_partnership") or
                data.get("branded_content_tag_info")):
            user = data.get("owner", {}) or data.get("user", {})
            username = user.get("username", "") if isinstance(user, dict) else ""
            results.append({
                "username": username,
                "is_ad": data.get("is_ad"),
                "is_paid_partnership": data.get("is_paid_partnership"),
                "has_branded_content": bool(data.get("branded_content_tag_info")),
            })
        for v in data.values():
            _walk_profile(v, results, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _walk_profile(item, results, depth + 1)


def _walk_threads(data, results, depth=0):
    """Walk Threads JSON for paid partnerships."""
    if depth > 20:
        return
    if isinstance(data, dict):
        if data.get("is_paid_partnership") is True:
            user = data.get("user", {}) or {}
            username = user.get("username", "") if isinstance(user, dict) else ""
            caption = data.get("caption", {})
            text = caption.get("text", "")[:100] if isinstance(caption, dict) else ""
            results.append({
                "username": username,
                "text": text,
                "type": "paid_partnership",
            })
        if data.get("is_ad") is True or data.get("is_sponsored") is True:
            user = data.get("user", {}) or {}
            username = user.get("username", "") if isinstance(user, dict) else ""
            results.append({
                "username": username,
                "type": "is_ad/is_sponsored",
            })
        for v in data.values():
            _walk_threads(v, results, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _walk_threads(item, results, depth + 1)


if __name__ == "__main__":
    asyncio.run(main())
