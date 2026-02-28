"""YouTube headless에서 adPlacements 존재 여부 빠르게 확인."""
import asyncio
from playwright.async_api import async_playwright

TEST_VIDEOS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=9bZkp7q19f0",
    "https://www.youtube.com/watch?v=JGwWNGJdvx8",
]

JS_CHECK = """() => {
    const pr = window.ytInitialPlayerResponse;
    if (!pr) return {has_data: false, reason: 'no_ytInitialPlayerResponse'};
    const placements = pr.adPlacements || [];
    const playerAds = pr.playerAds || [];
    return {
        has_data: true,
        ad_placements: placements.length,
        player_ads: playerAds.length,
        has_ad_slots: placements.length > 0 || playerAds.length > 0,
    };
}"""


async def main():
    print("=== YouTube headless adPlacements 테스트 ===")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
        )
        ctx = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        await ctx.add_cookies([
            {
                "name": "CONSENT",
                "value": "YES+cb.20260215-00-p0.kr+FX+999",
                "domain": ".youtube.com",
                "path": "/",
            },
        ])
        page = await ctx.new_page()

        for url in TEST_VIDEOS:
            vid = url.split("v=")[1]
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(3000)
                result = await page.evaluate(JS_CHECK)
                print(
                    f"  {vid}: placements={result.get('ad_placements', 0)}, "
                    f"playerAds={result.get('player_ads', 0)}, "
                    f"has_slots={result.get('has_ad_slots')}"
                )
            except Exception as e:
                print(f"  {vid}: ERROR {str(e)[:100]}")

        # headful 모드도 테스트
        await browser.close()

        print("\n=== YouTube headful adPlacements 테스트 ===")
        browser2 = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
        )
        ctx2 = await browser2.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        await ctx2.add_cookies([
            {
                "name": "CONSENT",
                "value": "YES+cb.20260215-00-p0.kr+FX+999",
                "domain": ".youtube.com",
                "path": "/",
            },
        ])
        page2 = await ctx2.new_page()

        for url in TEST_VIDEOS:
            vid = url.split("v=")[1]
            try:
                await page2.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page2.wait_for_timeout(5000)
                result = await page2.evaluate(JS_CHECK)
                print(
                    f"  {vid}: placements={result.get('ad_placements', 0)}, "
                    f"playerAds={result.get('player_ads', 0)}, "
                    f"has_slots={result.get('has_ad_slots')}"
                )
            except Exception as e:
                print(f"  {vid}: ERROR {str(e)[:100]}")

        await browser2.close()

    print("\n=== 테스트 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
