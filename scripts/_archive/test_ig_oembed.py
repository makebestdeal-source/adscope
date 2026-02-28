"""Test Instagram oEmbed API and other remaining public endpoints.

oEmbed: https://api.instagram.com/oembed/?url=...
This is an official, documented public API.
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

    # Test 1: oEmbed API for a profile
    print("=" * 60)
    print("  Test 1: oEmbed API for samsung profile")
    print("=" * 60)

    await page.goto(
        "https://api.instagram.com/oembed/?url=https://www.instagram.com/samsung/",
        wait_until="domcontentloaded", timeout=15000,
    )
    body = await page.evaluate("() => document.body.innerText")
    print(f"  Response: {body[:500]}")

    try:
        data = json.loads(body)
        print(f"  Keys: {list(data.keys())}")
        # The oEmbed for profiles returns html that contains embedded posts
        html = data.get("html", "")
        if html:
            print(f"  HTML length: {len(html)}")
            print(f"  HTML preview: {html[:300]}")
    except Exception:
        pass

    # Test 2: oEmbed for a specific post
    print("\n" + "=" * 60)
    print("  Test 2: oEmbed API for a specific post")
    print("=" * 60)

    # We need a post URL. Let's try to discover one via the embed
    # First, let's see if the profile embed has any data
    await page.goto("https://www.instagram.com/samsung/embed/",
                    wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)

    # Extract all hrefs from the embed
    all_hrefs = await page.evaluate("""() => {
        const allLinks = document.querySelectorAll('a');
        return Array.from(allLinks).map(a => ({
            href: a.href,
            text: (a.textContent || '').slice(0, 50),
        }));
    }""")
    print(f"  Links in embed: {len(all_hrefs)}")
    for link in all_hrefs[:10]:
        print(f"    {link['href'][:80]}  ({link['text'][:30]})")

    # Check if there are image tags
    images = await page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        return Array.from(imgs).map(img => ({
            src: (img.src || '').slice(0, 100),
            alt: (img.alt || '').slice(0, 50),
            width: img.naturalWidth || img.width,
            height: img.naturalHeight || img.height,
        }));
    }""")
    print(f"\n  Images in embed: {len(images)}")
    for img in images[:5]:
        print(f"    {img['src'][:80]}  ({img['width']}x{img['height']})")

    # Extract the full HTML to look for data
    html = await page.evaluate("() => document.documentElement.outerHTML")
    print(f"\n  HTML length: {len(html)}")

    # Look for embedded data patterns
    import re
    # Look for post data in JavaScript
    patterns = [
        r'"shortcode"\s*:\s*"([^"]+)"',
        r'/p/([A-Za-z0-9_-]{6,})',
        r'"edge_owner_to_timeline_media"',
        r'"coauthor',
        r'"sponsored_data"',
    ]
    for pat in patterns:
        matches = re.findall(pat, html)
        if matches:
            unique = list(set(matches))[:5]
            print(f"  Pattern '{pat[:30]}': {len(matches)} matches -> {unique[:3]}")

    # Test 3: Try fetching oEmbed with the IG graph API
    print("\n" + "=" * 60)
    print("  Test 3: graph.facebook.com oEmbed endpoint")
    print("=" * 60)

    # The Graph API oEmbed endpoint (public)
    oembed_url = (
        "https://graph.facebook.com/v18.0/instagram_oembed"
        "?url=https://www.instagram.com/samsung/"
        "&access_token=<needs_token>"
    )
    # This needs a token, so let's try without
    await page.goto(
        "https://graph.facebook.com/v18.0/instagram_oembed"
        "?url=https://www.instagram.com/samsung/",
        wait_until="domcontentloaded", timeout=15000,
    )
    body3 = await page.evaluate("() => document.body.innerText")
    print(f"  Response: {body3[:300]}")

    # Test 4: Try the i.instagram.com API (app API)
    print("\n" + "=" * 60)
    print("  Test 4: i.instagram.com user info endpoint")
    print("=" * 60)

    result = await page.evaluate("""async () => {
        try {
            const resp = await fetch(
                'https://i.instagram.com/api/v1/users/web_profile_info/?username=samsung',
                {
                    headers: {
                        'X-IG-App-ID': '936619743392459',
                        'X-IG-WWW-Claim': '0',
                        'X-Requested-With': 'XMLHttpRequest',
                    }
                }
            );
            const text = await resp.text();
            return {status: resp.status, body: text.slice(0, 300)};
        } catch(e) {
            return {error: e.message};
        }
    }""")
    print(f"  Status: {result.get('status')}")
    print(f"  Body: {result.get('body', result.get('error', ''))[:200]}")

    # Test 5: Check if ?__a=1 still works on profiles
    print("\n" + "=" * 60)
    print("  Test 5: Profile with ?__a=1")
    print("=" * 60)

    await page.goto("https://www.instagram.com/samsung/?__a=1&__d=dis",
                    wait_until="domcontentloaded", timeout=15000)
    print(f"  URL: {page.url[:100]}")
    body5 = await page.evaluate("() => document.body.innerText.slice(0, 300)")
    print(f"  Body: {body5[:200]}")

    await page.close()
    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
