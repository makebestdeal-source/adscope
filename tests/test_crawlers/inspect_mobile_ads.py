"""모바일 네이버 파워링크 광고 구조 상세 분석."""

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
            viewport={"width": 360, "height": 780},
            user_agent="Mozilla/5.0 (Linux; Android 14; SM-S926B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
            is_mobile=True, has_touch=True, device_scale_factor=3.0, locale="ko-KR"
        )
        await page.goto("https://m.search.naver.com/search.naver?query=%EB%8C%80%EC%B6%9C", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 광고 관련 모든 요소 탐색
        result = await page.evaluate("""
            () => {
                const output = {};

                // 1) 파워링크 컨텐츠 요소
                const pwc = document.querySelectorAll('[class*="power_content"], [class*="_fe_view_power"]');
                output.power_content_count = pwc.length;
                output.power_content_classes = Array.from(pwc).map(el => el.className.substring(0, 80));

                // 2) 모바일 광고 섹션
                const adSections = document.querySelectorAll('[class*="ad_section"], [class*="ad_area"]');
                output.ad_section_count = adSections.length;

                // 3) data-power 관련
                const dataPower = document.querySelectorAll('[data-power-content-url]');
                output.data_power_count = dataPower.length;
                output.data_power_items = Array.from(dataPower).slice(0, 5).map(el => {
                    const titleEl = el.querySelector('a');
                    const allText = el.innerText.substring(0, 200);
                    return {
                        class: el.className.substring(0, 60),
                        url: el.dataset.powerContentUrl ? el.dataset.powerContentUrl.substring(0, 60) : null,
                        firstLink: titleEl ? titleEl.href.substring(0, 60) : null,
                        text: allText,
                    };
                });

                // 4) 모바일 파워링크 래퍼
                const wrappers = document.querySelectorAll('[class*="keyword"], [class*="nkwd"]');
                output.keyword_wrapper_count = wrappers.length;
                output.keyword_wrapper_classes = Array.from(wrappers).slice(0, 5).map(el =>
                    ({class: el.className.substring(0, 80), tag: el.tagName, children: el.children.length})
                );

                // 5) 섹션 제목에 "파워링크" 포함
                const allElements = document.querySelectorAll('*');
                const plSections = [];
                for (const el of allElements) {
                    if (el.children.length > 0 && el.children.length < 30) {
                        const ownText = Array.from(el.childNodes)
                            .filter(n => n.nodeType === 3)
                            .map(n => n.textContent.trim())
                            .join('');
                        const cn = typeof el.className === 'string' ? el.className : '';
                        if (ownText.includes('파워링크') || cn.includes('power_link')) {
                            plSections.push({
                                tag: el.tagName,
                                class: el.className.substring(0, 80),
                                id: el.id,
                                children: el.children.length,
                                text: el.innerText.substring(0, 100),
                            });
                            if (plSections.length >= 5) break;
                        }
                    }
                }
                output.powerlink_sections = plSections;

                return output;
            }
        """)

        print("=== 모바일 광고 구조 분석 ===\n")
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect())
