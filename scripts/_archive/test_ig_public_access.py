"""Test if Instagram public profiles are accessible at all.

Check various methods:
1. Direct profile URL
2. Profile with ?__a=1 API param
3. Profile embed
4. Shared data / page source parsing
"""
import asyncio
import io
import json
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.async_api import async_playwright, Response


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )

    # Test 1: Direct profile visit with different user agents
    print("=" * 60)
    print("  Test 1: Profile with desktop Chrome UA")
    print("=" * 60)

    ctx1 = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="en-US", timezone_id="America/New_York",
    )
    await ctx1.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)
    p1 = await ctx1.new_page()
    json_hits = []

    async def on_resp1(r: Response):
        if r.status == 200 and "json" in r.headers.get("content-type", ""):
            if "instagram.com" in r.url:
                try:
                    body = await r.text()
                    json_hits.append({"url": r.url[:120], "size": len(body)})
                except Exception:
                    pass

    p1.on("response", on_resp1)
    await p1.goto("https://www.instagram.com/samsung/",
                  wait_until="domcontentloaded", timeout=15000)
    final_url = p1.url
    print(f"  Final URL: {final_url[:100]}")
    redirected_to_login = "login" in final_url.lower()
    print(f"  Redirected to login: {redirected_to_login}")

    if not redirected_to_login:
        await p1.wait_for_timeout(3000)
        print(f"  JSON hits: {len(json_hits)}")
        for jh in json_hits:
            print(f"    {jh['url'][:80]} ({jh['size']} bytes)")

    await p1.close()
    await ctx1.close()

    # Test 2: Try embed URL
    print("\n" + "=" * 60)
    print("  Test 2: Post embed URL (no login required)")
    print("=" * 60)

    ctx2 = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    p2 = await ctx2.new_page()
    json_hits2 = []

    async def on_resp2(r: Response):
        if r.status == 200 and "json" in r.headers.get("content-type", ""):
            if "instagram.com" in r.url:
                try:
                    body = await r.text()
                    json_hits2.append({"url": r.url[:120], "size": len(body)})
                except Exception:
                    pass

    p2.on("response", on_resp2)
    await p2.goto("https://www.instagram.com/samsung/embed/",
                  wait_until="domcontentloaded", timeout=15000)
    print(f"  Final URL: {p2.url[:100]}")
    print(f"  Redirected to login: {'login' in p2.url.lower()}")

    await p2.wait_for_timeout(2000)
    print(f"  JSON hits: {len(json_hits2)}")

    await p2.close()
    await ctx2.close()

    # Test 3: Try the public graphql query endpoint directly
    print("\n" + "=" * 60)
    print("  Test 3: Direct GraphQL query for web_profile_info")
    print("=" * 60)

    ctx3 = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await ctx3.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    p3 = await ctx3.new_page()
    # First visit instagram.com to get cookies/tokens
    await p3.goto("https://www.instagram.com/",
                  wait_until="domcontentloaded", timeout=15000)
    print(f"  Instagram home URL: {p3.url[:100]}")

    # Check if we can access the page at all
    page_content = await p3.evaluate("() => document.title")
    print(f"  Page title: {page_content}")

    # Try to get shared data from the page
    try:
        shared_data = await p3.evaluate("""() => {
            // Check for _sharedData on window
            if (window._sharedData) return JSON.stringify(window._sharedData).slice(0, 200);
            // Check for __initialData
            if (window.__initialData) return JSON.stringify(window.__initialData).slice(0, 200);
            return 'no shared data found';
        }""")
        print(f"  Shared data: {shared_data[:150]}")
    except Exception as exc:
        print(f"  Shared data error: {exc}")

    await p3.close()
    await ctx3.close()

    # Test 4: Try with Google bot UA (Instagram often serves content to bots)
    print("\n" + "=" * 60)
    print("  Test 4: Googlebot UA (may bypass login wall)")
    print("=" * 60)

    ctx4 = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (compatible; Googlebot/2.1; "
            "+http://www.google.com/bot.html)"
        ),
    )
    p4 = await ctx4.new_page()

    await p4.goto("https://www.instagram.com/samsung/",
                  wait_until="domcontentloaded", timeout=15000)
    print(f"  Final URL: {p4.url[:100]}")
    print(f"  Redirected to login: {'login' in p4.url.lower()}")

    if "login" not in p4.url.lower():
        title = await p4.evaluate("() => document.title")
        print(f"  Page title: {title}")
        # Look for JSON data in the page source
        try:
            has_json = await p4.evaluate("""() => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                if (scripts.length > 0) return scripts[0].textContent.slice(0, 200);
                return 'no ld+json found';
            }""")
            print(f"  LD+JSON: {has_json[:150]}")
        except Exception:
            pass

    await p4.close()
    await ctx4.close()

    # Test 5: Try ?__a=1&__d=dis
    print("\n" + "=" * 60)
    print("  Test 5: Profile with ?__a=1&__d=dis param")
    print("=" * 60)

    ctx5 = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await ctx5.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    p5 = await ctx5.new_page()
    resp5_data = []

    async def on_resp5(r: Response):
        if "instagram.com" in r.url:
            resp5_data.append({
                "url": r.url[:150],
                "status": r.status,
                "ct": r.headers.get("content-type", "")[:40]
            })

    p5.on("response", on_resp5)

    url5 = "https://www.instagram.com/api/v1/users/web_profile_info/?username=samsung"
    await p5.goto(url5, wait_until="domcontentloaded", timeout=15000)
    print(f"  Final URL: {p5.url[:120]}")

    # Check what we got
    try:
        body = await p5.evaluate("() => document.body.innerText.slice(0, 300)")
        print(f"  Body: {body[:200]}")
    except Exception:
        pass

    for rd in resp5_data[:5]:
        print(f"  Response: {rd['status']} {rd['url'][:80]} ({rd['ct']})")

    await p5.close()
    await ctx5.close()

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
