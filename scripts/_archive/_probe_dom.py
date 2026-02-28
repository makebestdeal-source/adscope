"""Probe broken channel DOMs to find current ad selectors."""
import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


async def probe():
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # === 1. Naver Shopping ===
        print("\n" + "=" * 60)
        print("  NAVER SHOPPING DOM PROBE")
        print("=" * 60)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="ko-KR"
        )
        page = await ctx.new_page()
        await page.goto(
            "https://search.shopping.naver.com/search/all?query=%EB%85%B8%ED%8A%B8%EB%B6%81",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(3000)
        for _ in range(3):
            await page.evaluate("window.scrollBy(0,800)")
            await page.wait_for_timeout(500)

        result = await page.evaluate(
            """() => {
            const info = {classes: [], adIndicators: [], productItems: []};
            // Find all elements with 'ad' in class name
            document.querySelectorAll('[class*="ad" i]').forEach(el => {
                if (info.classes.length < 20) {
                    info.classes.push({
                        tag: el.tagName, className: el.className.substring(0, 150),
                        text: el.innerText?.substring(0, 80) || ''
                    });
                }
            });
            // Find AD/광고 text badges
            document.querySelectorAll('span, div, em').forEach(el => {
                const t = el.innerText?.trim();
                if (t === 'AD' || t === '광고' || t === 'ad') {
                    if (info.adIndicators.length < 10) {
                        const parent = el.closest('li, div[class], article');
                        info.adIndicators.push({
                            tag: el.tagName, className: el.className?.substring(0, 100) || '',
                            parentTag: parent?.tagName || 'none',
                            parentClass: parent?.className?.substring(0, 100) || '', text: t
                        });
                    }
                }
            });
            // Find product list items
            document.querySelectorAll('li').forEach(el => {
                if (el.className && el.querySelector('a') && info.productItems.length < 5) {
                    info.productItems.push({
                        className: el.className.substring(0, 150),
                        hasAdBadge: !!el.querySelector('[class*="ad" i]'),
                        hasDataAdId: !!el.getAttribute('data-ad-id'),
                        childCount: el.children.length
                    });
                }
            });
            // data-ad-id elements
            const dataAdIds = document.querySelectorAll('[data-ad-id]');
            info.dataAdIdCount = dataAdIds.length;
            if (dataAdIds.length > 0) {
                info.dataAdIdSample = {
                    tag: dataAdIds[0].tagName, className: dataAdIds[0].className?.substring(0, 100) || '',
                    adId: dataAdIds[0].getAttribute('data-ad-id')
                };
            }
            info.nclickAdCount = document.querySelectorAll('[data-nclick*="ad"]').length;
            return info;
        }"""
        )
        print("Ad-related classes:", len(result.get("classes", [])))
        for c in result.get("classes", [])[:10]:
            print(f"  <{c['tag']}> class='{c['className'][:80]}' text='{c['text'][:50]}'")
        print(f"\nAD badges found: {len(result.get('adIndicators', []))}")
        for a in result.get("adIndicators", []):
            print(
                f"  <{a['tag']}> class='{a['className'][:60]}' "
                f"parent=<{a['parentTag']}> parentClass='{a['parentClass'][:60]}'"
            )
        print(f"\ndata-ad-id elements: {result.get('dataAdIdCount', 0)}")
        if result.get("dataAdIdSample"):
            s = result["dataAdIdSample"]
            print(f"  sample: <{s['tag']}> class='{s['className']}'")
        print(f"data-nclick[ad] elements: {result.get('nclickAdCount', 0)}")
        print("\nProduct list items (first 5):")
        for p in result.get("productItems", []):
            print(
                f"  class='{p['className'][:80]}' adBadge={p['hasAdBadge']} dataAdId={p['hasDataAdId']}"
            )
        await ctx.close()

        # === 2. YouTube ===
        print("\n" + "=" * 60)
        print("  YOUTUBE ADS DOM PROBE")
        print("=" * 60)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="ko-KR"
        )
        page = await ctx.new_page()
        await page.goto(
            "https://www.youtube.com/results?search_query=%EB%8C%80%EC%B6%9C",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(5000)
        for _ in range(3):
            await page.evaluate("window.scrollBy(0,800)")
            await page.wait_for_timeout(1000)

        result = await page.evaluate(
            """() => {
            const info = {renderers: [], sponsoredTexts: []};
            // Find all custom youtube elements with ad-related names
            document.querySelectorAll('*').forEach(el => {
                const tag = el.tagName.toLowerCase();
                if (tag.startsWith('ytd-') && (tag.includes('ad') || tag.includes('promot') || tag.includes('sparkle'))) {
                    if (info.renderers.length < 15) {
                        info.renderers.push({tag, childCount: el.children.length, text: el.innerText?.substring(0, 100) || ''});
                    }
                }
            });
            // Look for "Sponsored" / "광고" text
            document.querySelectorAll('span, div').forEach(el => {
                const t = el.innerText?.trim()?.toLowerCase();
                if (t && (t === 'sponsored' || t === '광고' || t === 'ad' || t.includes('sponsored')) && el.innerText.trim().length < 30) {
                    if (info.sponsoredTexts.length < 10) {
                        const parent = el.closest('ytd-video-renderer, ytd-ad-slot-renderer, [class*="ad"], div[id]');
                        info.sponsoredTexts.push({
                            text: el.innerText.trim(), tag: el.tagName,
                            className: el.className?.substring(0, 100) || '',
                            parentTag: parent?.tagName?.toLowerCase() || 'none',
                            parentClass: parent?.className?.substring(0, 100) || ''
                        });
                    }
                }
            });
            info.adSlotCount = document.querySelectorAll('ytd-ad-slot-renderer').length;
            const adSlots = document.querySelectorAll('ytd-ad-slot-renderer');
            if (adSlots.length > 0) info.adSlotSample = adSlots[0].innerHTML.substring(0, 300);
            info.pyvCount = document.querySelectorAll('ytd-search-pyv-renderer').length;
            const allYtd = new Set();
            document.querySelectorAll('[class]').forEach(el => {
                if (el.tagName.toLowerCase().startsWith('ytd-')) allYtd.add(el.tagName.toLowerCase());
            });
            info.allYtdTags = Array.from(allYtd).filter(t =>
                t.includes('ad') || t.includes('promo') || t.includes('sponsor') || t.includes('slot') || t.includes('sparkle')
            );
            return info;
        }"""
        )
        print("Ad-related renderers:")
        for r in result.get("renderers", []):
            print(f"  <{r['tag']}> children={r['childCount']} text='{r['text'][:60]}'")
        print(f"\nytd-ad-slot-renderer count: {result.get('adSlotCount', 0)}")
        if result.get("adSlotSample"):
            print(f"  sample: {result['adSlotSample'][:200]}")
        print(f"ytd-search-pyv-renderer count: {result.get('pyvCount', 0)}")
        print(f"\nAd-related ytd tags: {result.get('allYtdTags', [])}")
        print(f"\nSponsored texts: {len(result.get('sponsoredTexts', []))}")
        for s in result.get("sponsoredTexts", []):
            print(f"  '{s['text']}' in <{s['tag']}> parent=<{s['parentTag']}>")
        await ctx.close()

        # === 3. Kakao DA (Daum) ===
        print("\n" + "=" * 60)
        print("  KAKAO DA (DAUM) DOM PROBE")
        print("=" * 60)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="ko-KR"
        )
        page = await ctx.new_page()
        await page.goto("https://www.daum.net/", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        result = await page.evaluate(
            """() => {
            const info = {adLinks: [], adIframes: [], tiaraLayers: [], adWrappers: []};
            // Ad-related anchors
            document.querySelectorAll('a[href]').forEach(el => {
                const h = el.href || '';
                if (h.includes('ad.daum') || h.includes('kakaoad') || h.includes('adfit') ||
                    h.includes('doubleclick') || h.includes('adservice') ||
                    h.includes('t1.daumcdn') || h.includes('display.ad')) {
                    if (info.adLinks.length < 15) {
                        info.adLinks.push({href: h.substring(0, 150), text: el.innerText?.substring(0, 80) || '', className: el.className?.substring(0, 80) || ''});
                    }
                }
            });
            // iframes
            document.querySelectorAll('iframe').forEach(el => {
                const src = el.src || el.getAttribute('data-src') || '';
                info.adIframes.push({src: src.substring(0, 150), id: el.id || '', name: el.name || '', width: el.width || '', height: el.height || ''});
            });
            // tiara layers
            document.querySelectorAll('[data-tiara-layer]').forEach(el => {
                info.tiaraLayers.push({layer: el.getAttribute('data-tiara-layer'), tag: el.tagName, className: el.className?.substring(0, 80) || ''});
            });
            // ad wrappers
            document.querySelectorAll('[class*="ad"], [class*="Ad"], [id*="ad"], [id*="Ad"]').forEach(el => {
                if (info.adWrappers.length < 15) {
                    info.adWrappers.push({tag: el.tagName, id: el.id?.substring(0, 60) || '', className: el.className?.substring(0, 100) || '', text: el.innerText?.substring(0, 60) || ''});
                }
            });
            return info;
        }"""
        )
        print(f"Ad-related links: {len(result.get('adLinks', []))}")
        for a in result.get("adLinks", []):
            print(f"  href='{a['href'][:100]}' text='{a['text'][:40]}'")
        print(f"\niframes: {len(result.get('adIframes', []))}")
        for f in result.get("adIframes", []):
            print(f"  id='{f['id']}' src='{f['src'][:100]}' size={f['width']}x{f['height']}")
        print(f"\ntiara layers: {len(result.get('tiaraLayers', []))}")
        for t in result.get("tiaraLayers", []):
            print(f"  [{t['layer']}] <{t['tag']}> class='{t['className'][:60]}'")
        print(f"\nad wrappers: {len(result.get('adWrappers', []))}")
        for w in result.get("adWrappers", [])[:8]:
            print(f"  <{w['tag']}> id='{w['id']}' class='{w['className'][:60]}'")
        await ctx.close()

        # === 4. Meta Ad Library ===
        print("\n" + "=" * 60)
        print("  META AD LIBRARY DOM PROBE")
        print("=" * 60)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080}, locale="ko-KR"
        )
        page = await ctx.new_page()
        await page.goto(
            "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=KR&q=%EB%8C%80%EC%B6%9C",
            wait_until="domcontentloaded",
        )
        await page.wait_for_timeout(7000)
        for _ in range(5):
            await page.evaluate("window.scrollBy(0,500)")
            await page.wait_for_timeout(1500)

        result = await page.evaluate(
            """() => {
            const info = {cards: [], adTexts: [], articles: []};
            const selectors = [
                '[data-testid*="ad"]', 'div[role="article"]', '[class*="ad-card"]',
                '[class*="_8jg2"]', '[class*="x1lliihq"]', '[class*="_99s5"]',
            ];
            selectors.forEach(sel => {
                const els = document.querySelectorAll(sel);
                if (els.length > 0) info.cards.push({selector: sel, count: els.length});
            });
            // Find ad-related text
            document.querySelectorAll('div, span, a').forEach(el => {
                const t = el.innerText?.trim();
                if (t && (t.includes('See ad details') || t.includes('ad details') || t.includes('Started running') || t.includes('Library ID'))) {
                    if (info.adTexts.length < 10) {
                        info.adTexts.push({text: t.substring(0, 100), tag: el.tagName, className: el.className?.substring(0, 80) || ''});
                    }
                }
            });
            info.bodyTextLength = document.body?.innerText?.length || 0;
            info.pageTitle = document.title;
            info.url = window.location.href;
            // Potential card containers
            document.querySelectorAll('div').forEach(el => {
                if (el.children.length > 3 && el.children.length < 30) {
                    const imgs = el.querySelectorAll('img');
                    const links = el.querySelectorAll('a[href]');
                    if (imgs.length > 0 && links.length > 0 && info.articles.length < 5) {
                        info.articles.push({
                            className: el.className?.substring(0, 100) || '', childCount: el.children.length,
                            imgCount: imgs.length, linkCount: links.length, text: el.innerText?.substring(0, 100) || ''
                        });
                    }
                }
            });
            return info;
        }"""
        )
        print("Matching card selectors:")
        for c in result.get("cards", []):
            print(f"  {c['selector']} -> {c['count']} elements")
        print(f"\nPage title: {result.get('pageTitle', '')}")
        print(f"Body text length: {result.get('bodyTextLength', 0)}")
        print(f"\nAd-related texts: {len(result.get('adTexts', []))}")
        for t in result.get("adTexts", [])[:5]:
            print(f"  '{t['text'][:60]}' in <{t['tag']}> class='{t['className'][:40]}'")
        print(f"\nPotential card containers:")
        for a in result.get("articles", []):
            print(f"  class='{a['className'][:60]}' children={a['childCount']} imgs={a['imgCount']}")
        await ctx.close()

        await browser.close()
        print("\n=== PROBE COMPLETE ===")


asyncio.run(probe())
