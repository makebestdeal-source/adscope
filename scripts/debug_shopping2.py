"""Debug Naver Shopping - try different search approaches."""

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

        # Capture network responses
        json_responses = []

        async def on_response(response):
            try:
                if response.status != 200:
                    return
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    url = response.url
                    data = await response.json()
                    json_responses.append({"url": url[:150], "keys": list(data.keys())[:10] if isinstance(data, dict) else type(data).__name__})
            except Exception:
                pass

        page.on("response", on_response)

        keyword = "에어컨"

        # Approach 1: search.shopping.naver.com (may be blocked)
        print("=== Approach 1: search.shopping.naver.com ===")
        try:
            url1 = f"https://search.shopping.naver.com/search/all?query={quote(keyword)}&sort=rel"
            resp = await page.goto(url1, wait_until="domcontentloaded", timeout=15000)
            print(f"Status: {resp.status if resp else 'None'}")
            await page.wait_for_timeout(3000)
            title = await page.title()
            print(f"Title: {title}")
            content = await page.content()
            print(f"Content length: {len(content)}")
            # Count product mentions
            pn_count = content.count("productName")
            print(f"productName mentions: {pn_count}")
        except Exception as e:
            print(f"Error: {e}")

        # Approach 2: search.naver.com with scrolling
        print("\n=== Approach 2: search.naver.com + scroll ===")
        json_responses.clear()
        url2 = f"https://search.naver.com/search.naver?where=shopping&query={quote(keyword)}&pagingSize=80"
        await page.goto(url2, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Scroll down to load more products
        for _ in range(5):
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(500)

        await page.wait_for_timeout(2000)
        content = await page.content()
        print(f"Content length: {len(content)}")
        pn_count = content.count("productName")
        print(f"productName mentions: {pn_count}")

        # Check JSON responses after scrolling
        print(f"JSON responses captured: {len(json_responses)}")
        for jr in json_responses:
            if "shopping" in jr["url"].lower() or "product" in jr["url"].lower():
                print(f"  {jr['url'][:100]} -> {jr['keys']}")

        # Try extracting from page JS evaluate
        data = await page.evaluate("""() => {
            const products = [];
            // Look for all elements that look like product cards
            const allEls = document.querySelectorAll('a[href*="shopping-phinf"], a[href*="smartstore"], a[href*="brand.naver"]');
            allEls.forEach(el => {
                products.push({
                    href: el.href.substring(0, 100),
                    text: el.textContent.substring(0, 80).trim()
                });
            });

            // Also try to find product container
            const containers = document.querySelectorAll('[class*="product"], [class*="item"], [class*="shopping"]');
            const containerClasses = [];
            containers.forEach(el => {
                const cls = el.className;
                if (cls && cls.length < 100 && !containerClasses.includes(cls)) {
                    containerClasses.push(cls);
                }
            });

            return {
                productLinks: products.slice(0, 5),
                uniqueContainerClasses: containerClasses.slice(0, 20)
            };
        }""")
        print(f"\nProduct links: {len(data['productLinks'])}")
        for pl in data["productLinks"][:3]:
            print(f"  {pl}")
        print(f"Container classes: {data['uniqueContainerClasses'][:10]}")

        # Approach 3: Naver Shopping API via fetch
        print("\n=== Approach 3: Direct API call via browser ===")
        api_data = await page.evaluate("""async (keyword) => {
            try {
                const resp = await fetch(
                    `https://search.shopping.naver.com/api/search/all?sort=rel&pagingIndex=1&pagingSize=40&viewType=list&query=${encodeURIComponent(keyword)}&origQuery=${encodeURIComponent(keyword)}`,
                    {
                        headers: {
                            'Accept': 'application/json',
                            'Referer': 'https://search.shopping.naver.com/'
                        }
                    }
                );
                if (!resp.ok) return { error: resp.status };
                const data = await resp.json();
                const keys = Object.keys(data);
                let productCount = 0;
                let sampleProduct = null;

                if (data.shoppingResult && data.shoppingResult.products) {
                    productCount = data.shoppingResult.products.length;
                    if (productCount > 0) {
                        const p = data.shoppingResult.products[0];
                        sampleProduct = {
                            productTitle: p.productTitle,
                            price: p.price,
                            mallName: p.mallName,
                            reviewCount: p.reviewCount,
                            purchaseCnt: p.purchaseCnt,
                            imageUrl: p.imageUrl ? p.imageUrl.substring(0, 80) : null,
                            link: p.link ? p.link.substring(0, 100) : null,
                            category1: p.category1,
                            category2: p.category2,
                        };
                    }
                }

                return { keys, productCount, sampleProduct };
            } catch (e) {
                return { error: e.message };
            }
        }""", keyword)

        print(f"API result: {json.dumps(api_data, ensure_ascii=False, indent=2)}")

        await context.close()
        await browser.close()


asyncio.run(debug())
