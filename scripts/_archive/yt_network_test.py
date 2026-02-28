"""YouTube 영상 로드 시 네트워크에서 광고 데이터 캡처 테스트."""
import asyncio
import json
from urllib.parse import urlparse, unquote
from playwright.async_api import async_playwright, Response

captured_ads = []
network_urls = []


async def on_response(response: Response):
    url = response.url
    try:
        # player API
        if "youtubei/v1/player" in url:
            if response.status == 200:
                ct = response.headers.get("content-type", "")
                if "json" in ct:
                    data = await response.json()
                    placements = data.get("adPlacements", [])
                    player_ads = data.get("playerAds", [])
                    if placements or player_ads:
                        captured_ads.append({
                            "source": "player_api",
                            "placements": len(placements),
                            "playerAds": len(player_ads),
                            "raw_keys": list(data.keys())[:10],
                        })
                        print(f"  [CAPTURE] player API: {len(placements)} placements, {len(player_ads)} playerAds")
            return

        # doubleclick / pagead
        if any(d in url for d in ("doubleclick.net", "youtube.com/pagead/", "googlesyndication.com")):
            if response.status == 200:
                # adurl 파라미터 추출
                import re
                try:
                    body = await response.text()
                    ad_urls = re.findall(r"adurl=([^&\"'<>\s]+)", body)
                    for au in ad_urls:
                        decoded = unquote(au)
                        if decoded.startswith("http"):
                            domain = urlparse(decoded).netloc
                            captured_ads.append({
                                "source": "doubleclick",
                                "advertiser": domain,
                                "url": decoded[:150],
                            })
                            print(f"  [CAPTURE] doubleclick ad: {domain}")
                except Exception:
                    pass
            return

        # ad stats
        if "youtube.com/api/stats/ads" in url:
            network_urls.append(url[:120])
            print(f"  [CAPTURE] ad stats ping")

    except Exception:
        pass


async def main():
    print("=== YouTube 네트워크 광고 캡처 테스트 ===\n")

    test_videos = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
        "https://www.youtube.com/watch?v=JGwWNGJdvx8",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
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
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
        ])
        page = await ctx.new_page()
        page.on("response", on_response)

        for url in test_videos:
            vid = url.split("v=")[1]
            captured_ads.clear()
            network_urls.clear()
            print(f"\n--- {vid} ---")

            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # 재생 시도
            try:
                await page.evaluate("""() => {
                    const v = document.querySelector('video');
                    if (v) { v.muted = true; v.play().catch(() => {}); }
                    const btn = document.querySelector('.ytp-large-play-button, .ytp-play-button');
                    if (btn) btn.click();
                }""")
            except Exception:
                pass

            # 15초 대기하면서 캡처
            for i in range(5):
                await page.wait_for_timeout(3000)
                # DOM에서 ad-showing 체크
                try:
                    ad_playing = await page.evaluate("""() => {
                        const player = document.querySelector('.html5-video-player, #movie_player');
                        if (!player) return null;
                        return player.classList.contains('ad-showing') || player.classList.contains('ad-interrupting');
                    }""")
                    if ad_playing:
                        print(f"  [DOM] ad-showing 감지! round={i}")
                except Exception:
                    pass

            print(f"  결과: 캡처 {len(captured_ads)}건, stats pings {len(network_urls)}건")

        await browser.close()

    print("\n=== 전체 캡처 요약 ===")
    for cap in captured_ads:
        print(f"  {cap}")


if __name__ == "__main__":
    asyncio.run(main())
