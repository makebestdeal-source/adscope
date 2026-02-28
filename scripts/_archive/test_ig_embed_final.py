"""Final test: Extract coauthor data from embed pages using page content.

Since textContent doesn't preserve the escaped JSON, we'll use
the page's innerHTML and parse it in Python.
"""
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

from playwright.async_api import async_playwright


PROFILES = ["samsung", "innisfreeofficial", "hyundai", "nike", "adidas", "starbucks"]


def extract_coauthors_from_html(html: str, profile: str) -> list[dict]:
    """Extract coauthor data from embed page HTML."""
    results = []

    # Find all coauthor_producers occurrences
    idx = 0
    while True:
        # Look for non-empty coauthor arrays
        marker = 'coauthor_producers\\":[{\\"id\\"'
        idx = html.find(marker, idx)
        if idx == -1:
            break

        # Extract the array - find the matching ]
        arr_start = html.index('[', idx + len('coauthor_producers\\":'))
        depth = 0
        arr_end = arr_start
        for i in range(arr_start, min(len(html), arr_start + 5000)):
            if html[i] == '[':
                depth += 1
            elif html[i] == ']':
                depth -= 1
            if depth == 0:
                arr_end = i + 1
                break

        arr_str = html[arr_start:arr_end]

        # Unescape the JSON
        # \\" -> "
        # \\/ -> /
        unescaped = arr_str.replace('\\"', '"').replace('\\/', '/')

        try:
            arr = json.loads(unescaped)
        except json.JSONDecodeError:
            # Try double unescape
            unescaped2 = unescaped.replace('\\"', '"').replace('\\/', '/')
            try:
                arr = json.loads(unescaped2)
            except Exception:
                idx = idx + 1
                continue

        if not arr:
            idx = idx + 1
            continue

        # Extract coauthor info
        coauthors = []
        for c in arr:
            if isinstance(c, dict):
                coauthors.append({
                    "id": c.get("id"),
                    "username": c.get("username"),
                    "is_verified": c.get("is_verified"),
                })

        # Look backwards for shortcode
        before = html[max(0, idx - 5000):idx]
        sc_matches = re.findall(r'"shortcode\\":\\"([^"\\]+)"', before)
        if not sc_matches:
            sc_matches = re.findall(r'shortcode\\":\\"([A-Za-z0-9_-]+)', before)
        shortcode = sc_matches[-1] if sc_matches else None

        # Look for caption text
        cap_matches = re.findall(r'"text\\":\\"([^"\\]{0,200})"', before)
        caption = cap_matches[-1] if cap_matches else None

        results.append({
            "profile": profile,
            "shortcode": shortcode,
            "coauthors": coauthors,
            "caption": caption,
        })

        idx = idx + 1

    return results


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
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    await ctx.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    all_results = []
    for profile in PROFILES:
        print(f"\n{'='*60}")
        print(f"  Profile: {profile}")
        print(f"{'='*60}")

        page = await ctx.new_page()
        try:
            await page.goto(
                f"https://www.instagram.com/{profile}/embed/",
                wait_until="domcontentloaded", timeout=15000,
            )
            await page.wait_for_timeout(2000)

            # Get full page HTML
            html = await page.evaluate("() => document.documentElement.outerHTML")
            print(f"  HTML length: {len(html)}")

            results = extract_coauthors_from_html(html, profile)
            print(f"  Coauthor posts: {len(results)}")

            for r in results:
                usernames = [c.get("username", c.get("id", "?")) for c in r["coauthors"]]
                caption_safe = (r.get("caption") or "").encode("ascii", "replace").decode("ascii")[:60]
                print(f"    Post {r['shortcode']}: coauthors={usernames} caption='{caption_safe}'")
                all_results.append(r)

        except Exception as exc:
            print(f"  Error: {exc}")
        finally:
            await page.close()

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {len(all_results)} collab posts found")
    print(f"{'='*60}")
    for r in all_results:
        usernames = [c.get("username", c.get("id", "?")) for c in r["coauthors"]]
        print(f"  {r['profile']} / {r['shortcode']}: {usernames}")

    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
