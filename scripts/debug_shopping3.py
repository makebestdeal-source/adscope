"""Extract product data from Naver Shopping using page.evaluate()."""

import asyncio
import json
from urllib.parse import quote


JS_EXTRACT_PRODUCTS = """() => {
    const products = [];
    const scripts = document.querySelectorAll('script');

    for (const script of scripts) {
        const text = script.textContent;
        if (!text || text.length < 3000) continue;
        if (!text.includes('productName')) continue;

        // Find slot data with product info
        // Pattern: "slotType":"CARD","data":{...}
        // We need to extract individual product objects

        // Strategy: find all productName values and their surrounding data
        // The data format is JS object literals, so we'll use regex-like search

        // Try to find __SEARCH_RESULT_CONTAINER__
        const containerMatch = text.match(/__SEARCH_RESULT_CONTAINER__\\s*=\\s*/);
        if (containerMatch) {
            try {
                const jsonStr = text.substring(containerMatch.index + containerMatch[0].length);
                // Won't work because of undefined values, but worth trying
            } catch(e) {}
        }
    }

    // Better approach: extract directly from rendered DOM
    // Naver Shopping results have product cards in the search results area

    // Find all product-like items in the shopping section
    const shopSection = document.querySelector('#_shopping_list') ||
                        document.querySelector('[data-slog-container*="shp"]') ||
                        document.querySelector('.shopping_list') ||
                        document.body;

    // Look for all anchor links that point to product pages
    const allLinks = shopSection.querySelectorAll('a[href]');
    const seen = new Set();

    allLinks.forEach(a => {
        const href = a.href || '';
        // Product links go to smartstore, brand.naver, or shopping.naver
        const isProductLink = (
            href.includes('smartstore.naver.com') ||
            href.includes('brand.naver.com') ||
            href.includes('shopping.naver.com/product') ||
            href.includes('ader.naver.com') ||
            href.includes('search.shopping.naver.com/gate')
        );
        if (!isProductLink) return;

        // Find the parent product card
        let card = a;
        for (let i = 0; i < 8; i++) {
            if (!card.parentElement) break;
            card = card.parentElement;
            // Check if this looks like a product card (has price and title-like text)
            if (card.tagName === 'LI' || card.tagName === 'DIV') {
                const text = card.textContent || '';
                if (text.match(/[0-9,]+원/) && text.length > 30 && text.length < 2000) {
                    break;
                }
            }
        }

        // Extract data from the card
        const cardText = (card.textContent || '').trim();
        if (cardText.length < 20) return;

        // Get unique identifier
        const id = href.substring(0, 150);
        if (seen.has(id)) return;
        seen.add(id);

        // Extract title: usually the first substantial text or the link title
        const titleEl = card.querySelector('[class*="title"] a, a[title], [class*="name"]');
        const title = (titleEl ? (titleEl.textContent || titleEl.getAttribute('title') || '') : '').trim();

        // Extract price: look for number+원 pattern
        const priceMatch = cardText.match(/([0-9,]+)원/);
        const price = priceMatch ? parseInt(priceMatch[1].replace(/,/g, '')) : null;

        // Extract mall/store name
        const mallEl = card.querySelector('[class*="mall"], [class*="store"], [class*="seller"]');
        const mall = mallEl ? mallEl.textContent.trim() : '';

        // Extract review count
        const reviewMatch = cardText.match(/리뷰\\s*([0-9,]+)|([0-9,]+)개\\s*리뷰/);
        const reviewCount = reviewMatch ?
            parseInt((reviewMatch[1] || reviewMatch[2] || '0').replace(/,/g, '')) : 0;

        // Extract image
        const img = card.querySelector('img[src*="shopping-phinf"], img[src*="pstatic"]');
        const imageUrl = img ? (img.src || img.getAttribute('data-src') || '') : '';

        // Determine if it's an ad
        const isAd = href.includes('ader.naver.com') ||
                     href.includes('adcr.naver.com') ||
                     cardText.includes('광고') ||
                     (card.getAttribute('data-slog-content') || '').includes('nad');

        if (title && title.length > 2) {
            products.push({
                title: title.substring(0, 200),
                price: price,
                mall: mall.substring(0, 100),
                link: href.substring(0, 500),
                reviewCount: reviewCount,
                imageUrl: imageUrl.substring(0, 300),
                isAd: isAd,
                cardText: cardText.substring(0, 300),
            });
        }
    });

    return products;
}"""


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
        url = f"https://search.naver.com/search.naver?where=shopping&query={quote(keyword)}&pagingSize=80"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Scroll to load more
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 2000)")
            await page.wait_for_timeout(800)

        products = await page.evaluate(JS_EXTRACT_PRODUCTS)
        print(f"Products found: {len(products)}")
        for i, p in enumerate(products):
            print(f"\n[{i+1}] {p['title'][:60]}")
            print(f"    Price: {p['price']}")
            print(f"    Mall: {p['mall'][:30]}")
            print(f"    Reviews: {p['reviewCount']}")
            print(f"    Ad: {p['isAd']}")
            print(f"    Link: {p['link'][:80]}")

        await context.close()
        await browser.close()


asyncio.run(debug())
