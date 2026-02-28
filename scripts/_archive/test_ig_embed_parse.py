"""Parse Instagram embed page script data for coauthor_producers.

The data is in ServerJS handle() calls with escaped JSON.
We need to unescape and parse it.
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


async def extract_coauthors_from_embed(ctx, profile: str) -> list[dict]:
    """Extract coauthor data from a profile embed page using JS evaluation."""
    page = await ctx.new_page()
    results = []

    try:
        await page.goto(
            f"https://www.instagram.com/{profile}/embed/",
            wait_until="domcontentloaded", timeout=15000,
        )
        await page.wait_for_timeout(2000)

        # Use JavaScript to parse the embedded data directly in the browser
        # This avoids the escaped JSON issue since JS can evaluate it natively
        embed_results = await page.evaluate("""() => {
            const results = [];
            const scripts = document.querySelectorAll('script');

            for (const s of scripts) {
                const text = s.textContent || '';
                if (text.length < 5000 || !text.includes('coauthor_producers')) continue;

                // The data is in a ServerJS handle() call
                // Try to find and evaluate the JSON data
                // Look for the pattern: "shortcode_media":{"__typename":"Graph..."
                // Each post is wrapped in {"shortcode_media":{...}}

                // Strategy: Find all coauthor_producers occurrences and extract
                // surrounding post data using balanced brace matching
                let idx = 0;
                while (true) {
                    const caIdx = text.indexOf('"coauthor_producers":', idx);
                    if (caIdx === -1) break;

                    // Extract the array after coauthor_producers
                    const arrStart = text.indexOf('[', caIdx);
                    if (arrStart === -1) { idx = caIdx + 1; continue; }

                    // Find matching ]
                    let depth = 0;
                    let arrEnd = arrStart;
                    for (let i = arrStart; i < text.length && i < arrStart + 5000; i++) {
                        if (text[i] === '[') depth++;
                        if (text[i] === ']') depth--;
                        if (depth === 0) { arrEnd = i + 1; break; }
                    }

                    const arrStr = text.slice(arrStart, arrEnd);

                    // Look backwards for shortcode
                    const beforeContext = text.slice(Math.max(0, caIdx - 3000), caIdx);
                    const shortcodeMatch = beforeContext.match(/"shortcode"\\s*:\\s*"([^"]+)"/g);
                    let shortcode = null;
                    if (shortcodeMatch && shortcodeMatch.length > 0) {
                        // Get the last shortcode before this coauthor occurrence
                        const last = shortcodeMatch[shortcodeMatch.length - 1];
                        const m = last.match(/"shortcode"\\s*:\\s*"([^"]+)"/);
                        if (m) shortcode = m[1];
                    }

                    // Look for caption text
                    const captionMatch = beforeContext.match(/"text"\\s*:\\s*"([^"]{0,200})"/g);
                    let caption = null;
                    if (captionMatch && captionMatch.length > 0) {
                        const last = captionMatch[captionMatch.length - 1];
                        const m = last.match(/"text"\\s*:\\s*"([^"]{0,200})"/);
                        if (m) caption = m[1];
                    }

                    // Try to parse the coauthor array
                    try {
                        // Unescape the JSON (handle \\/ -> /)
                        const clean = arrStr.replace(/\\\\\\//g, '/');
                        const arr = JSON.parse(clean);

                        results.push({
                            shortcode: shortcode,
                            caption: caption ? caption.slice(0, 100) : null,
                            coauthors: arr.map(c => ({
                                id: c.id,
                                username: c.username,
                                is_verified: c.is_verified,
                            })),
                            isEmpty: arr.length === 0,
                        });
                    } catch(e) {
                        // Try without cleanup
                        try {
                            const arr = JSON.parse(arrStr);
                            results.push({
                                shortcode: shortcode,
                                caption: caption ? caption.slice(0, 100) : null,
                                coauthors: arr.map(c => ({
                                    id: c.id,
                                    username: c.username,
                                    is_verified: c.is_verified,
                                })),
                                isEmpty: arr.length === 0,
                            });
                        } catch(e2) {
                            results.push({
                                shortcode: shortcode,
                                error: e2.message,
                                rawArr: arrStr.slice(0, 200),
                            });
                        }
                    }

                    idx = caIdx + 1;
                }
            }
            return results;
        }""")

        print(f"  [{profile}] Found {len(embed_results)} posts with coauthor_producers field")
        for r in embed_results:
            coauthors = r.get("coauthors", [])
            shortcode = r.get("shortcode", "?")
            caption = r.get("caption", "")
            is_empty = r.get("isEmpty", True)

            if r.get("error"):
                print(f"    Post {shortcode}: PARSE ERROR: {r['error']}")
                print(f"      Raw: {r.get('rawArr', '')[:100]}")
                continue

            if not is_empty and coauthors:
                usernames = [c.get("username", c.get("id", "?")) for c in coauthors]
                caption_safe = (caption or "").encode("ascii", "replace").decode("ascii")
                print(f"    Post {shortcode}: COAUTHORS={usernames} caption='{caption_safe[:60]}'")
                results.append({
                    "profile": profile,
                    "shortcode": shortcode,
                    "coauthors": coauthors,
                    "caption": caption,
                })
            else:
                pass  # Empty coauthor array, skip

    except Exception as exc:
        print(f"  [{profile}] error: {exc}")
    finally:
        await page.close()

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
        results = await extract_coauthors_from_embed(ctx, profile)
        all_results.extend(results)

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  Total collab posts found: {len(all_results)}")
    for r in all_results:
        usernames = [c.get("username", c.get("id")) for c in r["coauthors"]]
        print(f"  {r['profile']} / {r['shortcode']}: {usernames}")

    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
