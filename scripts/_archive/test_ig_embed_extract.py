"""Extract coauthor data from Instagram embed HTML.

The embed page embeds post data in script tags. Extract and analyze it.
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


PROFILES = ["samsung", "innisfreeofficial", "hyundai", "nike"]


async def extract_embed_data(ctx, profile: str) -> list[dict]:
    """Extract coauthor data from profile embed page."""
    page = await ctx.new_page()
    results = []

    try:
        await page.goto(
            f"https://www.instagram.com/{profile}/embed/",
            wait_until="domcontentloaded", timeout=15000,
        )
        await page.wait_for_timeout(2000)

        # Extract ALL JavaScript data from the page
        embed_data = await page.evaluate("""() => {
            const results = [];
            const html = document.documentElement.outerHTML;

            // Method 1: Find ServerJS handle data
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const text = s.textContent || '';
                if (text.length < 200) continue;

                // Look for embedded media data
                if (text.includes('shortcode') || text.includes('edge_') || text.includes('coauthor')) {
                    // Try to extract JSON objects
                    // Look for patterns like: {"shortcode":"xxx","edge_..."}
                    // or xdt_api__v1__media__shortcode__web_info patterns
                    results.push({
                        scriptLen: text.length,
                        hasShortcode: text.includes('shortcode'),
                        hasEdge: text.includes('edge_'),
                        hasCoauthor: text.includes('coauthor'),
                        hasMedia: text.includes('media'),
                        preview: text.slice(0, 200),
                    });
                }
            }

            // Method 2: Look for structured data in page
            // Instagram embeds use window.__additionalDataLoaded or similar
            const additionalData = window.__additionalData || window.__additionalDataLoaded;
            if (additionalData) {
                results.push({type: 'additionalData', data: JSON.stringify(additionalData).slice(0, 500)});
            }

            return results;
        }""")

        print(f"\n  [{profile}] Script analysis: {len(embed_data)} interesting scripts")
        for i, ed in enumerate(embed_data):
            print(f"    Script {i}: len={ed.get('scriptLen')}, "
                  f"shortcode={ed.get('hasShortcode')}, "
                  f"coauthor={ed.get('hasCoauthor')}, "
                  f"edge={ed.get('hasEdge')}")

        # Now extract the actual coauthor data
        coauthor_data = await page.evaluate("""() => {
            const html = document.documentElement.outerHTML;
            const results = [];

            // Find coauthor JSON patterns in the HTML
            // Pattern: "coauthor_producers":[{...}]
            const coauthorMatches = html.matchAll(/"coauthor_producers"\\s*:\\s*(\\[[^\\]]*\\])/g);
            for (const m of coauthorMatches) {
                try {
                    const arr = JSON.parse(m[1]);
                    results.push({
                        type: 'coauthor_producers',
                        data: arr,
                        context: html.slice(Math.max(0, m.index - 100), m.index + m[0].length + 100),
                    });
                } catch(e) {
                    results.push({
                        type: 'coauthor_producers_raw',
                        raw: m[1].slice(0, 200),
                    });
                }
            }

            // Find shortcodes near coauthor data
            const shortcodeMatches = html.matchAll(/"shortcode"\\s*:\\s*"([^"]+)"/g);
            const shortcodes = [];
            for (const m of shortcodeMatches) {
                shortcodes.push(m[1]);
            }
            results.push({type: 'shortcodes', data: [...new Set(shortcodes)]});

            return results;
        }""")

        print(f"  [{profile}] Coauthor data extraction: {len(coauthor_data)} results")
        for cd in coauthor_data:
            if cd['type'] == 'coauthor_producers':
                arr = cd['data']
                if arr and len(arr) > 0:
                    usernames = [
                        item.get('username', '?') if isinstance(item, dict) else '?'
                        for item in arr
                    ]
                    context_safe = cd.get('context', '').encode('ascii', 'replace').decode('ascii')[:150]
                    print(f"    COAUTHOR: {usernames}")
                    print(f"    Context: {context_safe}")
                    results.append({
                        'profile': profile,
                        'coauthors': usernames,
                        'type': 'producers',
                    })
                else:
                    # Empty array - post has coauthor field but no coauthors
                    pass
            elif cd['type'] == 'coauthor_producers_raw':
                raw = cd.get('raw', '')
                if raw and raw != '[]':
                    print(f"    COAUTHOR_RAW: {raw[:100]}")
            elif cd['type'] == 'shortcodes':
                scs = cd.get('data', [])
                print(f"    Shortcodes: {scs[:10]}")

        # Also try to get user/caption data around coauthor mentions
        post_data = await page.evaluate("""() => {
            const html = document.documentElement.outerHTML;
            const posts = [];

            // Find JSON blocks that contain both shortcode and coauthor
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const text = s.textContent || '';
                if (!text.includes('coauthor_producers')) continue;

                // Try to find complete node objects
                // They typically have: shortcode, edge_media_to_caption, coauthor_producers
                const nodePattern = /\\{"__typename":"\\w+","id":"\\d+"[^}]*"shortcode":"([^"]+)"[^]*?"coauthor_producers":(\\[[^\\]]*\\])/g;
                let m;
                while ((m = nodePattern.exec(text)) !== null) {
                    const shortcode = m[1];
                    try {
                        const coauthors = JSON.parse(m[2]);
                        posts.push({shortcode, coauthors});
                    } catch(e) {}
                }
            }

            return posts;
        }""")

        if post_data:
            print(f"  [{profile}] Post-level coauthor data: {len(post_data)} posts")
            for pd in post_data:
                sc = pd.get('shortcode', '?')
                cas = pd.get('coauthors', [])
                if cas:
                    names = [c.get('username', '?') if isinstance(c, dict) else '?' for c in cas]
                    print(f"    Post {sc}: coauthors={names}")
                    results.append({
                        'profile': profile,
                        'shortcode': sc,
                        'coauthors': names,
                        'type': 'post',
                    })

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
        results = await extract_embed_data(ctx, profile)
        all_results.extend(results)

    print(f"\n{'='*60}")
    print(f"  SUMMARY: {len(all_results)} coauthor items found")
    print(f"{'='*60}")
    for r in all_results:
        if r['type'] == 'post':
            print(f"  {r['profile']} -> post {r.get('shortcode')}: {r['coauthors']}")
        elif r['type'] == 'producers':
            print(f"  {r['profile']} -> coauthors: {r['coauthors']}")

    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
