"""네이버 검색 결과 DOM 구조 분석 스크립트."""

import asyncio
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playwright.async_api import async_playwright


async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
        )

        await page.goto("https://search.naver.com/search.naver?query=%EB%8C%80%EC%B6%9C", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 광고 관련 섹션 찾기
        print("=== 광고 영역 분석 ===\n")

        # 다양한 셀렉터로 광고 영역 탐색
        selectors_to_check = [
            ("div.sp_keyword", "sp_keyword"),
            ("#power_link_body", "power_link_body"),
            ("div[class*='keyword']", "keyword class"),
            ("div[class*='power']", "power class"),
            ("div[class*='ad_']", "ad_ class"),
            ("div[class*='_ad']", "_ad class"),
            ("div[data-ad-area]", "data-ad-area"),
            ("section[data-tab]", "data-tab sections"),
            ("div.api_subject_bx", "api_subject_bx"),
            ("div[class*='lst_total']", "lst_total"),
            ("#sp_nkwd", "sp_nkwd"),
            ("#sp_keyword", "sp_keyword (id)"),
            ("div[class*='_svp_item']", "_svp_item"),
        ]

        for selector, name in selectors_to_check:
            elements = await page.query_selector_all(selector)
            if elements:
                print(f"[O] {name}: {len(elements)}개 발견 ({selector})")
                for i, el in enumerate(elements[:2]):
                    tag = await el.evaluate("el => el.tagName + '.' + el.className.split(' ').slice(0,3).join('.')")
                    text_preview = await el.inner_text()
                    text_preview = text_preview[:100].replace('\n', ' ')
                    print(f"    [{i}] <{tag}> {text_preview}...")

        # 전체 광고 관련 id/class 탐색
        print("\n=== 광고 관련 id 속성 ===")
        ad_ids = await page.evaluate("""
            () => {
                const elements = document.querySelectorAll('[id]');
                const adIds = [];
                for (const el of elements) {
                    const id = el.id.toLowerCase();
                    if (id.includes('ad') || id.includes('power') || id.includes('keyword') ||
                        id.includes('sp_') || id.includes('biz') || id.includes('brand')) {
                        adIds.push({id: el.id, tag: el.tagName, childCount: el.children.length});
                    }
                }
                return adIds.slice(0, 20);
            }
        """)
        for item in ad_ids:
            print(f"  #{item['id']} <{item['tag']}> children={item['childCount']}")

        # 파워링크 구체적 탐색
        print("\n=== 파워링크 상세 구조 ===")
        powerlink_html = await page.evaluate("""
            () => {
                // 파워링크가 포함된 섹션 찾기
                const sections = document.querySelectorAll('div, section');
                for (const sec of sections) {
                    const text = sec.innerText || '';
                    const html = sec.outerHTML || '';
                    if ((text.includes('파워링크') || html.includes('power_link') || html.includes('sp_keyword'))
                        && sec.children.length > 0 && sec.children.length < 20) {
                        return {
                            tag: sec.tagName,
                            id: sec.id,
                            className: sec.className.substring(0, 100),
                            childCount: sec.children.length,
                            html: sec.outerHTML.substring(0, 2000),
                        };
                    }
                }
                return null;
            }
        """)
        if powerlink_html:
            print(f"  태그: {powerlink_html['tag']}")
            print(f"  ID: {powerlink_html['id']}")
            print(f"  Class: {powerlink_html['className']}")
            print(f"  Children: {powerlink_html['childCount']}")
            print(f"  HTML 미리보기:\n{powerlink_html['html'][:1500]}")
        else:
            print("  파워링크 영역을 찾을 수 없음")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect())
