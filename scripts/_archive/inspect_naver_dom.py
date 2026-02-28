"""네이버 메인 DOM 진단 스크립트 — naver_da 셀렉터 업데이트용."""

import asyncio
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from playwright.async_api import async_playwright


async def inspect_naver():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        # === PC 버전 ===
        print("=" * 60)
        print("  PC (www.naver.com) DOM 진단")
        print("=" * 60)

        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page = await ctx.new_page()
        await page.goto("https://www.naver.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await page.evaluate("window.scrollBy(0, 800)")
        await page.wait_for_timeout(2000)

        # 1. adcr 링크 찾기
        adcr_links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href*="adcr.naver.com"]')).map(a => ({
                href: a.href.substring(0, 150),
                text: (a.innerText || '').substring(0, 60).trim(),
                parent_class: (a.closest('div,section,article') || {}).className || '',
                parent_id: (a.closest('div,section,article') || {}).id || '',
            }));
        }""")
        print(f"\n[PC] adcr.naver.com 링크: {len(adcr_links)}개")
        for link in adcr_links[:10]:
            print(f"  text={link['text'][:40]}  class={link['parent_class'][:60]}  id={link['parent_id']}")

        # 2. 광고 관련 class/id 검색
        ad_elements = await page.evaluate("""() => {
            const sels = '[class*="ad"],[id*="ad"],[class*="Ad"],[class*="banner"],[class*="Banner"],[data-ad],[data-advertisement],[class*="sponsor"],[class*="Sponsor"]';
            const all = document.querySelectorAll(sels);
            return Array.from(all).slice(0, 30).map(el => ({
                tag: el.tagName,
                id: el.id || '',
                className: (el.className || '').toString().substring(0, 120),
                childCount: el.children.length,
                hasImg: !!el.querySelector('img'),
                text: (el.innerText || '').substring(0, 80).trim().replace(/\\n/g, ' | '),
            }));
        }""")
        print(f"\n[PC] 광고 관련 요소: {len(ad_elements)}개")
        for el in ad_elements[:20]:
            print(f"  <{el['tag']} id=\"{el['id']}\" class=\"{el['className'][:70]}\"> children={el['childCount']} img={el['hasImg']}")
            if el['text']:
                print(f"    text: {el['text'][:70]}")

        # 3. 대형 이미지 (배너 후보)
        large_images = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('img')).filter(img => {
                const w = img.naturalWidth || img.width || 0;
                const h = img.naturalHeight || img.height || 0;
                return w > 200 && h > 80;
            }).map(img => ({
                src: (img.src || '').substring(0, 120),
                alt: (img.alt || '').substring(0, 60),
                width: img.naturalWidth || img.width,
                height: img.naturalHeight || img.height,
                parent_class: (img.closest('a,div') || {}).className || '',
                parent_href: (img.closest('a') || {}).href || '',
            }));
        }""")
        print(f"\n[PC] 대형 이미지 (>200px): {len(large_images)}개")
        for img in large_images[:10]:
            is_ad = 'adcr' in img['parent_href'] or 'ad' in img['parent_class'].lower()
            print(f"  {img['width']}x{img['height']} alt=\"{img['alt'][:30]}\" ad={is_ad}")
            print(f"    class={img['parent_class'][:60]}  href={img['parent_href'][:80]}")

        # 4. 기존 셀렉터 테스트
        test_selectors = [
            'div[class*="timeboard"]', 'div[data-tiara-area="timeboard"]', '#timeboard',
            'div[class*="rolling"]', 'div[data-tiara-area="rolling"]',
            'div[class*="brand"]', 'div[class*="shop_ad"]',
            'div.sc_timeboard', 'div.sc_rolling', 'div.sc_branding',
        ]
        print(f"\n[PC] 기존 셀렉터 테스트:")
        for sel in test_selectors:
            count = await page.locator(sel).count()
            status = "OK" if count > 0 else "X "
            print(f"  {status}  {sel} -> {count}개")

        # 5. data- 속성 검색
        data_attrs = await page.evaluate("""() => {
            const all = document.querySelectorAll('[data-tiara-area],[data-clk],[data-area],[data-componentid]');
            const areas = {};
            all.forEach(el => {
                const area = el.getAttribute('data-tiara-area') || el.getAttribute('data-area') || el.getAttribute('data-componentid') || '';
                const clk = el.getAttribute('data-clk') || '';
                const key = area || clk;
                if (key && !areas[key]) {
                    areas[key] = {
                        tag: el.tagName,
                        className: (el.className || '').toString().substring(0, 80),
                        area: area,
                        clk: clk,
                        childCount: el.children.length,
                        hasImg: !!el.querySelector('img'),
                    };
                }
            });
            return areas;
        }""")
        print(f"\n[PC] data 속성들: {len(data_attrs)}개")
        for key, val in sorted(data_attrs.items()):
            img_mark = " [IMG]" if val.get("hasImg") else ""
            print(f"  {key}: <{val['tag']}> class={val['className'][:50]} children={val['childCount']}{img_mark}")

        # 6. iframe 검사 (광고가 iframe에 있을 수 있음)
        iframes = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('iframe')).map(f => ({
                src: (f.src || '').substring(0, 150),
                id: f.id || '',
                className: (f.className || '').toString().substring(0, 80),
                width: f.width || f.offsetWidth || 0,
                height: f.height || f.offsetHeight || 0,
                parent_class: (f.closest('div') || {}).className || '',
            }));
        }""")
        print(f"\n[PC] iframe: {len(iframes)}개")
        for f in iframes[:10]:
            is_ad = 'ad' in f['src'].lower() or 'ad' in f['className'].lower()
            print(f"  [{f['width']}x{f['height']}] id={f['id']} src={f['src'][:80]} ad={is_ad}")

        await ctx.close()

        # === 모바일 버전 ===
        print(f"\n{'='*60}")
        print("  모바일 (m.naver.com) DOM 진단")
        print("=" * 60)

        ctx_m = await browser.new_context(
            viewport={"width": 375, "height": 812},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            is_mobile=True,
            has_touch=True,
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )
        page_m = await ctx_m.new_page()
        await page_m.goto("https://m.naver.com/", wait_until="domcontentloaded")
        await page_m.wait_for_timeout(3000)
        await page_m.evaluate("window.scrollBy(0, 1200)")
        await page_m.wait_for_timeout(2000)

        # 모바일 adcr 링크
        m_adcr = await page_m.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href*="adcr.naver.com"]')).map(a => ({
                href: a.href.substring(0, 150),
                text: (a.innerText || '').substring(0, 60).trim(),
                parent_class: (a.closest('div,section') || {}).className || '',
            }));
        }""")
        print(f"\n[모바일] adcr.naver.com 링크: {len(m_adcr)}개")
        for link in m_adcr[:10]:
            print(f"  text={link['text'][:40]}  class={link['parent_class'][:60]}")

        # 모바일 광고 요소
        m_ad_els = await page_m.evaluate("""() => {
            const sels = '[class*="ad"],[class*="Ad"],[class*="banner"],[class*="channel"],[class*="Channel"],[class*="sponsor"],[class*="Sponsor"]';
            const all = document.querySelectorAll(sels);
            return Array.from(all).slice(0, 30).map(el => ({
                tag: el.tagName,
                id: el.id || '',
                className: (el.className || '').toString().substring(0, 120),
                childCount: el.children.length,
                hasImg: !!el.querySelector('img'),
                text: (el.innerText || '').substring(0, 60).trim().replace(/\\n/g, ' | '),
            }));
        }""")
        print(f"\n[모바일] 광고/채널 관련 요소: {len(m_ad_els)}개")
        for el in m_ad_els[:15]:
            print(f"  <{el['tag']} class=\"{el['className'][:70]}\"> children={el['childCount']} img={el['hasImg']}")
            if el['text']:
                print(f"    text: {el['text'][:60]}")

        # 모바일 data 속성
        m_data = await page_m.evaluate("""() => {
            const all = document.querySelectorAll('[data-tiara-area],[data-clk],[data-area],[data-componentid]');
            const areas = {};
            all.forEach(el => {
                const area = el.getAttribute('data-tiara-area') || el.getAttribute('data-area') || el.getAttribute('data-componentid') || '';
                const clk = el.getAttribute('data-clk') || '';
                const key = area || clk;
                if (key && !areas[key]) {
                    areas[key] = {
                        tag: el.tagName,
                        className: (el.className || '').toString().substring(0, 80),
                        childCount: el.children.length,
                        hasImg: !!el.querySelector('img'),
                    };
                }
            });
            return areas;
        }""")
        print(f"\n[모바일] data 속성들: {len(m_data)}개")
        for key, val in sorted(m_data.items()):
            img_mark = " [IMG]" if val.get("hasImg") else ""
            print(f"  {key}: <{val['tag']}> class={val['className'][:50]} children={val['childCount']}{img_mark}")

        # 모바일 기존 셀렉터 테스트
        m_test = [
            'div[class*="smart_channel"]', 'div[class*="sc_"]', 'a[class*="smart_channel"]',
            'div[class*="feed_ad"]', 'div[class*="ad_area"]',
            'div[class*="ContentFeedAd"]', 'div[data-tiara-area="smartchannel"]',
        ]
        print(f"\n[모바일] 기존 셀렉터 테스트:")
        for sel in m_test:
            count = await page_m.locator(sel).count()
            status = "OK" if count > 0 else "X "
            print(f"  {status}  {sel} -> {count}개")

        # 모바일 iframe
        m_iframes = await page_m.evaluate("""() => {
            return Array.from(document.querySelectorAll('iframe')).map(f => ({
                src: (f.src || '').substring(0, 150),
                id: f.id || '',
                className: (f.className || '').toString().substring(0, 80),
                width: f.width || f.offsetWidth || 0,
                height: f.height || f.offsetHeight || 0,
            }));
        }""")
        print(f"\n[모바일] iframe: {len(m_iframes)}개")
        for f in m_iframes[:10]:
            print(f"  [{f['width']}x{f['height']}] id={f['id']} src={f['src'][:100]}")

        await ctx_m.close()
        await browser.close()

asyncio.run(inspect_naver())
