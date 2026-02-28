"""Test if Instagram embed pages contain coauthor/collab data.

Since profile pages now require login, embeds might be our way in.
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
        args=["--disable-blink-features=AutomationControlled"],
    )

    # Test 1: Profile embed page
    print("=" * 60)
    print("  Test 1: Profile embed page for samsung")
    print("=" * 60)

    ctx = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    page = await ctx.new_page()
    all_json = []

    async def on_response(r: Response):
        if r.status == 200 and "instagram.com" in r.url:
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = await r.text()
                    all_json.append({
                        "url": r.url[:200],
                        "size": len(body),
                        "data": json.loads(body) if body else None,
                    })
                except Exception:
                    pass

    page.on("response", on_response)

    await page.goto("https://www.instagram.com/samsung/embed/",
                    wait_until="domcontentloaded", timeout=15000)
    print(f"  URL: {page.url[:100]}")

    await page.wait_for_timeout(3000)

    # Get page content
    title = await page.evaluate("() => document.title")
    print(f"  Title: {title}")

    # Check for script data in page
    try:
        embed_data = await page.evaluate("""() => {
            // Look for JSON data in script tags
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const text = s.textContent || '';
                if (text.includes('edge_owner_to_timeline_media') ||
                    text.includes('coauthor') ||
                    text.includes('shortcode')) {
                    return text.slice(0, 500);
                }
            }
            // Look for shared data
            if (window.__additionalData) return JSON.stringify(window.__additionalData).slice(0, 500);
            if (window._sharedData) return JSON.stringify(window._sharedData).slice(0, 500);
            return null;
        }""")
        if embed_data:
            print(f"  Script data found: {str(embed_data)[:200]}")
        else:
            print("  No script data found")
    except Exception as exc:
        print(f"  Script check error: {exc}")

    # What does the page look like?
    body_text = await page.evaluate("() => document.body ? document.body.innerText.slice(0, 500) : 'no body'")
    print(f"  Body text: {body_text[:200]}")

    print(f"\n  JSON responses: {len(all_json)}")
    for j in all_json:
        print(f"    {j['url'][:100]} ({j['size']} bytes)")
        if j['data'] and isinstance(j['data'], dict):
            keys = list(j['data'].keys())[:10]
            print(f"    Top keys: {keys}")

    await page.close()
    await ctx.close()

    # Test 2: Individual post embed URLs
    print("\n" + "=" * 60)
    print("  Test 2: Individual post embed page")
    print("=" * 60)

    ctx2 = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await ctx2.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    p2 = await ctx2.new_page()
    json2 = []

    async def on_resp2(r: Response):
        if r.status == 200 and "instagram.com" in r.url:
            ct = r.headers.get("content-type", "")
            if "json" in ct:
                try:
                    body = await r.text()
                    json2.append({
                        "url": r.url[:200],
                        "size": len(body),
                        "body": body,
                    })
                except Exception:
                    pass

    p2.on("response", on_resp2)

    # Try a known Samsung post embed
    # First, let's try the embed endpoint directly
    await p2.goto("https://www.instagram.com/samsung/embed/",
                  wait_until="domcontentloaded", timeout=15000)
    await p2.wait_for_timeout(2000)

    # Extract post links from the embed page
    try:
        post_links = await p2.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/p/"]');
            return Array.from(links).slice(0, 10).map(a => ({
                href: a.href,
                text: (a.textContent || '').slice(0, 50),
            }));
        }""")
        print(f"  Post links found: {len(post_links)}")
        for pl in post_links[:5]:
            print(f"    {pl['href'][:80]}  ({pl['text'][:30]})")
    except Exception as exc:
        print(f"  Post link extraction error: {exc}")

    # Try the embed page HTML for embedded data
    try:
        html_data = await p2.evaluate("""() => {
            const html = document.documentElement.outerHTML;
            // Look for edge_owner_to_timeline_media or similar data
            const match = html.match(/window\\.(__additionalData|_sharedData)\\s*=\\s*(\\{.+?\\});/s);
            if (match) return match[2].slice(0, 1000);

            // Check for embedded JSON in script tags
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const t = s.textContent || '';
                if (t.length > 500 && (t.includes('"shortcode"') || t.includes('"media"'))) {
                    return t.slice(0, 1000);
                }
            }
            return null;
        }""")
        if html_data:
            print(f"\n  Embedded data: {str(html_data)[:300]}")

            # Try to parse and look for coauthor data
            try:
                data = json.loads(html_data)
                print(f"  Parsed keys: {list(data.keys())[:10]}")
            except Exception:
                pass
    except Exception as exc:
        print(f"  HTML data error: {exc}")

    print(f"\n  JSON network responses: {len(json2)}")
    for j in json2:
        print(f"    {j['url'][:100]} ({j['size']} bytes)")
        try:
            data = json.loads(j['body'])
            if isinstance(data, dict):
                # Look for coauthor data
                data_str = json.dumps(data)
                has_coauthor = "coauthor" in data_str
                has_collab = "collab" in data_str.lower()
                has_shortcode = "shortcode" in data_str
                print(f"    has_coauthor={has_coauthor}, has_collab={has_collab}, has_shortcode={has_shortcode}")
                if has_coauthor:
                    # Find the coauthor data
                    idx = data_str.find("coauthor")
                    print(f"    coauthor context: ...{data_str[max(0,idx-50):idx+100]}...")
        except Exception:
            pass

    await p2.close()
    await ctx2.close()

    # Test 3: Check graphql.instagram.com endpoint
    print("\n" + "=" * 60)
    print("  Test 3: GraphQL endpoint with query")
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

    # Visit Instagram home first to get session
    await p3.goto("https://www.instagram.com/",
                  wait_until="domcontentloaded", timeout=15000)
    await p3.wait_for_timeout(2000)

    # Try to fetch user info via GraphQL
    try:
        result = await p3.evaluate("""async () => {
            try {
                // Try the public user info endpoint
                const resp = await fetch(
                    'https://www.instagram.com/api/v1/users/web_profile_info/?username=samsung',
                    {
                        headers: {
                            'X-IG-App-ID': '936619743392459',
                            'X-Requested-With': 'XMLHttpRequest',
                        },
                        credentials: 'include',
                    }
                );
                const text = await resp.text();
                return {status: resp.status, body: text.slice(0, 500)};
            } catch(e) {
                return {error: e.message};
            }
        }""")
        print(f"  GraphQL result: status={result.get('status')}")
        print(f"  Body: {result.get('body', result.get('error', ''))[:200]}")
    except Exception as exc:
        print(f"  GraphQL error: {exc}")

    await p3.close()
    await ctx3.close()

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
