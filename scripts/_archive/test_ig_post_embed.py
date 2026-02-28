"""Test individual post embed pages for coauthor data.

Instagram individual post embeds (/p/{shortcode}/embed/) may expose
coauthor/collaboration data in the embedded HTML.
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

from playwright.async_api import async_playwright, Response


# Known Samsung posts (some may have coauthors)
# We'll get these from the embed page itself
KNOWN_POSTS = [
    # Try to fetch a few known recent shortcodes
]


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )

    # Step 1: Get post shortcodes from profile embed page
    print("=" * 60)
    print("  Step 1: Get shortcodes from profile embed HTML")
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

    # Visit samsung embed to get shortcodes
    await page.goto("https://www.instagram.com/samsung/embed/",
                    wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)

    # Extract shortcodes from the embed HTML
    shortcodes = await page.evaluate("""() => {
        const html = document.documentElement.outerHTML;
        // Look for shortcodes in the HTML
        const matches = html.match(/\\/p\\/([A-Za-z0-9_-]+)/g);
        if (!matches) return [];
        // Deduplicate
        const unique = [...new Set(matches.map(m => m.replace('/p/', '')))];
        return unique.slice(0, 12);
    }""")
    print(f"  Shortcodes found: {len(shortcodes)}")
    for sc in shortcodes:
        print(f"    {sc}")

    await page.close()

    # Also check innisfreeofficial
    page2 = await ctx.new_page()
    await page2.goto("https://www.instagram.com/innisfreeofficial/embed/",
                     wait_until="domcontentloaded", timeout=15000)
    await page2.wait_for_timeout(2000)

    shortcodes2 = await page2.evaluate("""() => {
        const html = document.documentElement.outerHTML;
        const matches = html.match(/\\/p\\/([A-Za-z0-9_-]+)/g);
        if (!matches) return [];
        const unique = [...new Set(matches.map(m => m.replace('/p/', '')))];
        return unique.slice(0, 12);
    }""")
    print(f"\n  Innisfree shortcodes: {len(shortcodes2)}")
    for sc in shortcodes2:
        print(f"    {sc}")

    await page2.close()

    # Step 2: Visit individual post embed pages and check for coauthor data
    print("\n" + "=" * 60)
    print("  Step 2: Individual post embed pages")
    print("=" * 60)

    all_shortcodes = shortcodes[:6] + shortcodes2[:6]
    for sc in all_shortcodes:
        try:
            p = await ctx.new_page()
            all_json = []

            async def on_resp(r: Response, captured=all_json):
                if r.status == 200 and "instagram.com" in r.url:
                    ct = r.headers.get("content-type", "")
                    if "json" in ct:
                        try:
                            body = await r.text()
                            captured.append({"url": r.url[:150], "body": body})
                        except Exception:
                            pass

            p.on("response", on_resp)

            embed_url = f"https://www.instagram.com/p/{sc}/embed/"
            await p.goto(embed_url, wait_until="domcontentloaded", timeout=12000)
            await p.wait_for_timeout(1500)

            # Extract data from embed page
            embed_info = await p.evaluate("""() => {
                const result = {
                    title: document.title,
                    bodyText: (document.body ? document.body.innerText : '').slice(0, 300),
                };

                // Look for embedded media data
                const html = document.documentElement.outerHTML;

                // Check for coauthor mentions
                result.hasCoauthor = html.includes('coauthor');
                result.hasCollab = html.toLowerCase().includes('collab');
                result.hasPaidPartnership = html.includes('paid_partnership') || html.includes('Paid partnership');
                result.hasSponsor = html.includes('sponsor');

                // Extract caption text
                const captionEl = document.querySelector('.Caption, [class*="caption"]');
                if (captionEl) {
                    result.caption = captionEl.textContent.slice(0, 200);
                }

                // Check for tagged users in embed
                const tagLinks = document.querySelectorAll('a[href*="instagram.com/"]');
                result.taggedUsers = Array.from(tagLinks)
                    .map(a => a.href.replace('https://www.instagram.com/', '').replace('/', ''))
                    .filter(u => u && u.length > 0 && !u.includes('?') && !u.startsWith('p/'))
                    .slice(0, 10);

                // Look for ServerJS data
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const t = s.textContent || '';
                    if (t.includes('media') && t.includes('user') && t.length > 500) {
                        // Try to find embedded JSON
                        const jsonMatch = t.match(/\\{"graphql".*?\\}/);
                        if (jsonMatch) {
                            result.hasGraphqlData = true;
                        }
                        // Check for specific fields
                        result.hasIsAd = t.includes('"is_ad"');
                        result.hasIsPaidPartnershipInScript = t.includes('is_paid_partnership');
                        result.hasCoauthorInScript = t.includes('coauthor');
                    }
                }

                return result;
            }""")

            markers = []
            if embed_info.get("hasCoauthor"): markers.append("COAUTHOR")
            if embed_info.get("hasCollab"): markers.append("COLLAB")
            if embed_info.get("hasPaidPartnership"): markers.append("PAID_PARTNERSHIP")
            if embed_info.get("hasSponsor"): markers.append("SPONSOR")
            if embed_info.get("hasCoauthorInScript"): markers.append("COAUTHOR_SCRIPT")

            marker_str = " ".join(markers) if markers else "none"
            tagged = embed_info.get("taggedUsers", [])

            print(f"\n  [{sc}] markers: {marker_str}")
            print(f"    tagged_users: {tagged[:5]}")
            print(f"    body: {embed_info.get('bodyText', '')[:100]}")

            if markers:
                # Get the full HTML for detailed analysis
                html = await p.evaluate("() => document.documentElement.outerHTML")
                # Find coauthor context
                for marker in ["coauthor", "paid_partnership", "collab"]:
                    idx = html.lower().find(marker)
                    if idx >= 0:
                        context_str = html[max(0, idx-100):idx+200]
                        # Clean it
                        context_str = re.sub(r'<[^>]+>', '', context_str)[:200]
                        safe = context_str.encode("ascii", "replace").decode("ascii")
                        print(f"    {marker} context: {safe}")

            await p.close()

        except Exception as exc:
            print(f"  [{sc}] error: {exc}")

    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
