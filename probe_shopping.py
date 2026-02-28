import asyncio
import json
from playwright.async_api import async_playwright

JS_CODE = r"""() => {
    const r = {};
    r.li_total = document.querySelectorAll('li').length;
    r.ad_badge_exact = (() => {
        let c = 0;
        document.querySelectorAll('li').forEach(li => {
            const badges = li.querySelectorAll('span, em');
            for (const b of badges) {
                const t = b.innerText?.trim();
                if (t === 'AD' || t === '광고') { c++; break; }
            }
        });
        return c;
    })();
    r.data_ad_id = document.querySelectorAll('[data-ad-id]').length;
    r.ad_nclick = document.querySelectorAll('[data-nclick*="ad"]').length;
    r.class_ad = document.querySelectorAll('[class*="ad"]').length;
    r.class_adProduct = document.querySelectorAll('[class*="adProduct"]').length;
    r.class_ad_item = document.querySelectorAll('[class*="ad_"]').length;
    r.sponsored_text = (document.body.innerText.match(/AD\b/g) || []).length;
    r.brand_store = document.querySelectorAll('[class*="brandStore"]').length;
    r.brand_zone = document.querySelectorAll('[class*="brand_zone"]').length;
    r.brand_banner = document.querySelectorAll('[class*="brandBanner"]').length;
    r.basicList = document.querySelectorAll('[class*="basicList"]').length;
    r.product_item = document.querySelectorAll('[class*="product_item"]').length;

    r.ad_sections = [];
    document.querySelectorAll('div, section').forEach(el => {
        const cls = el.className || '';
        if (typeof cls === 'string' && (cls.includes('ad') || cls.includes('Ad') || cls.includes('sponsor') || cls.includes('promote'))) {
            r.ad_sections.push(cls.substring(0, 80));
        }
    });
    r.ad_sections = [...new Set(r.ad_sections)].slice(0, 20);

    r.ad_samples = [];
    document.querySelectorAll('li').forEach(li => {
        if (r.ad_samples.length >= 5) return;
        const badges = li.querySelectorAll('span, em');
        let isAd = false;
        for (const b of badges) {
            const t = b.innerText?.trim();
            if (t === 'AD' || t === '광고') { isAd = true; break; }
        }
        if (!isAd) return;
        const text = (li.innerText || '').replace(/\s+/g, ' ').trim().substring(0, 300);
        const links = Array.from(li.querySelectorAll('a[href]')).slice(0, 3).map(a => ({
            text: a.innerText?.trim().substring(0, 80),
            href: a.href?.substring(0, 100)
        }));
        r.ad_samples.push({text, links, classes: li.className?.substring(0, 100)});
    });

    r.all_items_check = [];
    const items = document.querySelectorAll('li[class*="item"]');
    for (const item of Array.from(items).slice(0, 30)) {
        const hasAdBadge = Array.from(item.querySelectorAll('span, em')).some(b => /^(AD|광고)$/.test(b.innerText?.trim()));
        const hasAdAttr = !!item.querySelector('[data-ad-id]');
        const text = (item.innerText || '').substring(0, 100).replace(/\s+/g, ' ');
        if (hasAdBadge || hasAdAttr) {
            r.all_items_check.push({ad: true, text: text.substring(0, 80), cls: item.className?.substring(0, 60)});
        }
    }
    r.total_ad_items = r.all_items_check.length;

    return r;
}"""

async def probe():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(channel='chrome', headless=False, args=['--disable-blink-features=AutomationControlled'])
    ctx = await browser.new_context(locale='ko-KR', timezone_id='Asia/Seoul')
    page = await ctx.new_page()

    await page.goto('https://www.naver.com/', wait_until='domcontentloaded')
    await page.wait_for_timeout(2000)
    await page.goto('https://search.shopping.naver.com/search/all?query=%EB%8B%A4%EC%9D%B4%EC%96%B4%ED%8A%B8', wait_until='domcontentloaded')
    await page.wait_for_timeout(4000)

    for _ in range(5):
        await page.evaluate('window.scrollBy(0, 600)')
        await page.wait_for_timeout(800)

    counts = await page.evaluate(JS_CODE)
    print(json.dumps(counts, ensure_ascii=False, indent=2))

    await browser.close()
    await pw.stop()

asyncio.run(probe())
