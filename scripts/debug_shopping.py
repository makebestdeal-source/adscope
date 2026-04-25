"""Debug Naver Shopping search to understand product data structure."""

import asyncio
import json
import re
from urllib.parse import quote


async def debug():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        await context.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined});'
        )
        page = await context.new_page()

        keyword = "에어컨"
        url = f"https://search.naver.com/search.naver?where=shopping&query={quote(keyword)}&pagingSize=40"
        print(f"Navigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Extract product data using page.evaluate
        products = await page.evaluate(
            """() => {
            const results = [];
            // Try finding product list items
            const selectors = [
                '[class*="basicList_item"]',
                '[class*="product_item"]',
                'li.product_item',
                '.shopping_list li',
                '[data-nclick*="shp"]'
            ];

            let items = [];
            for (const sel of selectors) {
                items = document.querySelectorAll(sel);
                if (items.length > 0) break;
            }

            if (items.length === 0) {
                // Fallback: find all LI/DIV with product-like content
                const allElements = document.querySelectorAll('li, div');
                for (const el of allElements) {
                    if (el.querySelector('img') && el.textContent.length > 50 && el.textContent.length < 500) {
                        const hasPrice = /[0-9,]+원/.test(el.textContent);
                        if (hasPrice) {
                            items = [el, ...items];
                            if (items.length >= 3) break;
                        }
                    }
                }
            }

            return {
                itemCount: items.length,
                sampleClasses: items.length > 0 ? items[0].className : '',
                sampleHTML: items.length > 0 ? items[0].outerHTML.substring(0, 500) : ''
            };
        }"""
        )
        print(f"\nDOM items found: {products['itemCount']}")
        print(f"Sample class: {products['sampleClasses'][:100]}")
        if products["sampleHTML"]:
            print(f"Sample HTML: {products['sampleHTML'][:400]}")

        # Now look at the script content more carefully
        content = await page.content()

        # Find the big script with product data
        scripts = re.findall(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
        for i, s in enumerate(scripts):
            if "productName" in s and len(s) > 5000:
                print(f"\n=== Script #{i}: {len(s)} bytes ===")

                # Extract productName values
                names = re.findall(r'"productName"\s*:\s*"([^"]*)"', s)
                print(f"Product names found: {len(names)}")
                for name in names[:5]:
                    print(f"  - {name}")

                # Extract price values near productName
                prices = re.findall(r'"(?:price|lowPrice|salePrice)"\s*:\s*"?(\d+)"?', s)
                print(f"Prices found: {len(prices)}")
                for pr in prices[:5]:
                    print(f"  - {pr}")

                # Extract mallName
                malls = re.findall(r'"mallName"\s*:\s*"([^"]*)"', s)
                print(f"Mall names found: {len(malls)}")
                for m in malls[:5]:
                    print(f"  - {m}")

                # Extract reviewCount
                reviews = re.findall(r'"reviewCount"\s*:\s*(\d+)', s)
                print(f"Review counts: {len(reviews)}")
                for r in reviews[:5]:
                    print(f"  - {r}")

                # Extract purchaseCnt
                purchases = re.findall(r'"purchaseCnt"\s*:\s*(\d+)', s)
                print(f"Purchase counts: {len(purchases)}")
                for pc in purchases[:5]:
                    print(f"  - {pc}")

                # Extract image URLs
                images = re.findall(r'"imageUrl"\s*:\s*"([^"]*)"', s)
                print(f"Image URLs: {len(images)}")
                for img in images[:3]:
                    print(f"  - {img}")

                # Try to extract individual product objects
                # Look for the pattern: {"slotType":"CARD","data":{...productName...}}
                product_blocks = re.findall(
                    r'\{"slotType"\s*:\s*"CARD"\s*,\s*"data"\s*:\s*\{[^}]*"productName"\s*:\s*"[^"]*"[^}]*\}',
                    s,
                )
                print(f"\nProduct card blocks found: {len(product_blocks)}")

                # Look for cardType to distinguish ads from organic
                card_types = re.findall(r'"cardType"\s*:\s*"([^"]*)"', s)
                print(f"Card types: {card_types[:10]}")

                # sourceType
                source_types = re.findall(r'"sourceType"\s*:\s*"([^"]*)"', s)
                print(f"Source types: {source_types[:10]}")

                break

        await context.close()
        await browser.close()


asyncio.run(debug())
