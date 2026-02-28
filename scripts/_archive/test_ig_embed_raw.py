"""Extract and parse the raw JavaScript data from Instagram embed pages.

The embed page has a ~170KB+ script with all the profile data.
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

    print("Visiting samsung embed...")
    await page.goto("https://www.instagram.com/samsung/embed/",
                    wait_until="domcontentloaded", timeout=15000)
    await page.wait_for_timeout(2000)

    # Get the large script content
    script_content = await page.evaluate("""() => {
        const scripts = document.querySelectorAll('script');
        for (const s of scripts) {
            const text = s.textContent || '';
            if (text.length > 50000 && text.includes('coauthor')) {
                return text;
            }
        }
        return null;
    }""")

    if not script_content:
        print("No large script with coauthor data found!")
        await page.close()
        await ctx.close()
        await browser.close()
        await pw.stop()
        return

    print(f"Script length: {len(script_content)}")

    # Save to file for analysis
    with open("c:/Users/user/Desktop/adscopre/scripts/_embed_script.txt", "w",
              encoding="utf-8") as f:
        f.write(script_content)
    print("Saved to _embed_script.txt")

    # Find all occurrences of "coauthor" with context
    idx = 0
    occurrences = []
    while True:
        idx = script_content.find("coauthor", idx)
        if idx == -1:
            break
        context = script_content[max(0, idx-200):idx+200]
        occurrences.append({
            "pos": idx,
            "context": context,
        })
        idx += 1

    print(f"\nCoauthor occurrences: {len(occurrences)}")
    for i, occ in enumerate(occurrences):
        # Clean the context for printing
        ctx_clean = occ["context"].encode("ascii", "replace").decode("ascii")
        # Truncate for readability
        print(f"\n  [{i}] pos={occ['pos']}:")
        print(f"    ...{ctx_clean[:300]}...")

    # Find shortcode occurrences
    shortcode_matches = re.findall(r'"shortcode"\s*:\s*"([^"]+)"', script_content)
    unique_shortcodes = list(set(shortcode_matches))
    print(f"\nShortcodes found: {len(unique_shortcodes)}")
    for sc in unique_shortcodes[:12]:
        print(f"  {sc}")

    # Try to find JSON-like structures
    # The data is likely in a ServerJS handle call
    # Pattern: s.handle({"define":...,"require":...})
    handle_match = re.search(r's\.handle\((\{.+\})\)', script_content, re.DOTALL)
    if handle_match:
        try:
            handle_data = json.loads(handle_match.group(1))
            print(f"\nServerJS handle data keys: {list(handle_data.keys())}")
        except json.JSONDecodeError as exc:
            print(f"\nServerJS JSON parse failed: {exc}")
            # Try to find the relevant section manually
            handle_text = handle_match.group(1)
            print(f"Handle text length: {len(handle_text)}")

    # Alternative: try to find xdt_api__v1__media patterns
    xdt_matches = re.findall(r'xdt_api__v1__\w+', script_content)
    if xdt_matches:
        unique_xdt = list(set(xdt_matches))
        print(f"\nXDT API references: {unique_xdt[:10]}")

    # Look for JSON objects that contain coauthor_producers
    # Try to find: ,"coauthor_producers":[ ... ]
    ca_pattern = re.findall(
        r'"coauthor_producers"\s*:\s*(\[(?:[^\[\]]*|\[(?:[^\[\]]*|\[[^\[\]]*\])*\])*\])',
        script_content
    )
    print(f"\ncoauthor_producers arrays found: {len(ca_pattern)}")
    for i, ca in enumerate(ca_pattern[:10]):
        try:
            arr = json.loads(ca)
            if arr:
                print(f"  [{i}] Non-empty: {json.dumps(arr)[:200]}")
            else:
                print(f"  [{i}] Empty array")
        except json.JSONDecodeError:
            print(f"  [{i}] Parse failed: {ca[:100]}")

    await page.close()
    await ctx.close()
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
