"""Instagram 크롤러 빠른 디버깅 — warmup 스킵하고 직접 테스트."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from loguru import logger
from playwright.async_api import async_playwright


async def main():
    logger.info("=== Instagram 디버그 시작 ===")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        )
        page = await context.new_page()

        # 네트워크 응답 캡처
        api_hits = []
        async def _on_response(response):
            url = response.url
            if '/graphql/' in url or '/api/v1/' in url:
                api_hits.append(url[:100])

        page.on('response', _on_response)

        # 1) Instagram 메인 페이지
        logger.info("1) Instagram 메인 페이지 방문")
        try:
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            title = await page.title()
            url = page.url
            logger.info(f"   URL: {url}, Title: {title}")
            logger.info(f"   API hits: {len(api_hits)}")
        except Exception as e:
            logger.error(f"   메인 실패: {e}")

        # 2) Explore 페이지
        logger.info("2) Explore 페이지")
        try:
            await page.goto("https://www.instagram.com/explore/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            url = page.url
            logger.info(f"   URL: {url}")
            logger.info(f"   API hits: {len(api_hits)}")
            # 로그인 리다이렉트 체크
            if 'accounts/login' in url:
                logger.warning("   → 로그인 페이지로 리다이렉트됨!")
        except Exception as e:
            logger.error(f"   Explore 실패: {e}")

        # 3) Reels
        logger.info("3) Reels 페이지")
        try:
            await page.goto("https://www.instagram.com/reels/", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(3000)
            url = page.url
            logger.info(f"   URL: {url}")
            logger.info(f"   API hits: {len(api_hits)}")
        except Exception as e:
            logger.error(f"   Reels 실패: {e}")

        # 4) Meta Ad Library (fallback 테스트)
        logger.info("4) Meta Ad Library (Instagram 필터) 테스트")
        try:
            lib_url = (
                "https://www.facebook.com/ads/library/"
                "?active_status=active&ad_type=all&country=KR&is_targeted_country=false"
                "&media_type=all&publisher_platforms[0]=instagram"
                "&search_type=keyword_unordered&q=한국"
            )
            await page.goto(lib_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)

            # 스크롤
            for i in range(3):
                await page.evaluate("window.scrollBy(0, 800)")
                await page.wait_for_timeout(1500)

            # 카드 파싱
            card_count = await page.evaluate("""() => {
                const selectors = [
                    '[data-testid*="ad"]',
                    'div[class*="x1plvlek"][class*="xryxfnj"]',
                    'div[class*="xrvj5dj"]',
                    'div[class*="x1dr59a3"]',
                    'div[role="article"]',
                    'div[class*="_8jg2"]',
                ];
                for (const sel of selectors) {
                    const cards = document.querySelectorAll(sel);
                    if (cards.length > 0) return {selector: sel, count: cards.length};
                }
                // fallback: check links
                const links = document.querySelectorAll('a[href*="ads/library"]');
                return {selector: 'a[ads/library]', count: links.length};
            }""")
            logger.info(f"   카드: {card_count}")

            body_len = await page.evaluate("() => document.body.innerText.length")
            logger.info(f"   Body text length: {body_len}")

        except Exception as e:
            logger.error(f"   Ad Library 실패: {e}")

        logger.info(f"=== 총 API hits: {len(api_hits)} ===")
        for h in api_hits[:10]:
            logger.debug(f"   {h}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
