"""네이버 파워링크 광고 항목 내부 구조 분석."""

import asyncio
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playwright.async_api import async_playwright


async def inspect_ads():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # === PC 분석 ===
        page = await browser.new_page(viewport={"width": 1920, "height": 1080}, locale="ko-KR")
        await page.goto("https://search.naver.com/search.naver?query=%EB%8C%80%EC%B6%9C", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        print("=== PC 파워링크 광고 항목 구조 ===\n")
        ad_items = await page.evaluate("""
            () => {
                const body = document.querySelector('#power_link_body');
                if (!body) return [];
                const items = body.querySelectorAll('.nad_area, li, [class*="item"]');
                return Array.from(items).slice(0, 5).map((item, idx) => {
                    // 제목 링크
                    const titleEl = item.querySelector('a[class*="lnk_head"], a[class*="tit"], .lnk_tit a, a.link_tit, a[class*="title"]');
                    // URL 영역
                    const urlEl = item.querySelector('[class*="url"], [class*="lnk_url"]');
                    // 설명
                    const descEl = item.querySelector('[class*="ad_dsc"], [class*="desc"], [class*="dsc"]');

                    return {
                        index: idx,
                        className: item.className.substring(0, 80),
                        html: item.outerHTML.substring(0, 1500),
                        title: titleEl ? {tag: titleEl.tagName, class: titleEl.className.substring(0,50), text: titleEl.innerText.substring(0,60), href: titleEl.href} : null,
                        url: urlEl ? {tag: urlEl.tagName, class: urlEl.className.substring(0,50), text: urlEl.innerText.substring(0,60)} : null,
                        desc: descEl ? {text: descEl.innerText.substring(0,80)} : null,
                    };
                });
            }
        """)

        for item in ad_items:
            print(f"--- 광고 [{item['index']}] class={item['className']} ---")
            if item['title']:
                print(f"  제목: {item['title']['text']}")
                print(f"  제목 selector: {item['title']['tag']}.{item['title']['class']}")
                print(f"  href: {item['title']['href'][:80] if item['title'].get('href') else 'N/A'}")
            if item['url']:
                print(f"  URL 텍스트: {item['url']['text']}")
                print(f"  URL selector: {item['url']['tag']}.{item['url']['class']}")
            if item['desc']:
                print(f"  설명: {item['desc']['text']}")
            print(f"  HTML:\n{item['html'][:800]}\n")

        # 총 광고 수 확인
        total_ads = await page.evaluate("""
            () => {
                const body = document.querySelector('#power_link_body');
                if (!body) return 0;
                return body.querySelectorAll('.nad_area').length;
            }
        """)
        print(f"\n총 PC 파워링크 광고 수: {total_ads}")

        # === 모바일 분석 ===
        await page.close()
        page = await browser.new_page(
            viewport={"width": 360, "height": 780},
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S926B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            is_mobile=True, has_touch=True, device_scale_factor=3.0, locale="ko-KR"
        )
        await page.goto("https://m.search.naver.com/search.naver?query=%EB%8C%80%EC%B6%9C", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        print("\n=== 모바일 파워링크 광고 구조 ===\n")
        mobile_ads = await page.evaluate("""
            () => {
                // 모바일 광고 영역 탐색
                const candidates = [
                    'div.sp_keyword', 'div._au_keyword_wgt',
                    'div[class*="keyword"]', 'div[class*="power"]',
                    'div.ad_area', '#power_link_body',
                    'div[class*="nad"]', 'div[class*="ad_section"]'
                ];
                let container = null;
                for (const sel of candidates) {
                    container = document.querySelector(sel);
                    if (container) break;
                }
                if (!container) {
                    // 전체에서 '파워링크' 텍스트 포함 영역 찾기
                    const all = document.querySelectorAll('div, section');
                    for (const el of all) {
                        if (el.innerText && el.innerText.includes('파워링크') && el.children.length < 30) {
                            container = el;
                            break;
                        }
                    }
                }
                if (!container) return {found: false};

                return {
                    found: true,
                    containerClass: container.className.substring(0, 100),
                    containerId: container.id,
                    containerTag: container.tagName,
                    html: container.outerHTML.substring(0, 2000),
                    childCount: container.children.length,
                };
            }
        """)

        if mobile_ads.get('found'):
            print(f"컨테이너: {mobile_ads['containerTag']}#{mobile_ads['containerId']}.{mobile_ads['containerClass']}")
            print(f"Children: {mobile_ads['childCount']}")
            print(f"HTML:\n{mobile_ads['html'][:1500]}")
        else:
            print("모바일 광고 영역 찾지 못함")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect_ads())
