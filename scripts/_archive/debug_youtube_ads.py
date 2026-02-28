"""YouTube 광고 캡처 빠른 디버그 스크립트."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # headed로 확인
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        await context.add_cookies([
            {'name': 'CONSENT', 'value': 'YES+cb.20260215-00-p0.kr+FX+999',
             'domain': '.youtube.com', 'path': '/'},
            {'name': 'PREF', 'value': 'tz=Asia.Seoul&hl=ko&gl=KR',
             'domain': '.youtube.com', 'path': '/'},
        ])

        player_data_list = []
        ad_network_hits = []

        async def on_response(response):
            url = response.url
            if 'youtubei/v1/player' in url:
                try:
                    if response.status == 200:
                        ct = response.headers.get('content-type', '')
                        if 'json' in ct:
                            data = await response.json()
                            placements = data.get('adPlacements', [])
                            player_ads = data.get('playerAds', [])
                            print(f"\n[PLAYER] adPlacements={len(placements)}, playerAds={len(player_ads)}")
                            for i, pl in enumerate(placements):
                                renderer = pl.get('adPlacementRenderer', {}).get('renderer', {})
                                for k, v in renderer.items():
                                    if isinstance(v, dict):
                                        print(f"  placement[{i}].{k}: keys={list(v.keys())[:8]}")
                                        # 실제 광고 데이터 깊이 탐색
                                        _print_ad_data(v, f"    ")
                            player_data_list.append(data)
                except Exception as e:
                    print(f"  Player error: {e}")

            if any(d in url for d in (
                'doubleclick.net/pagead/ads',
                'youtube.com/api/stats/ads',
                'youtube.com/pagead/',
                'googlesyndication.com/pagead/',
            )):
                try:
                    ct = response.headers.get('content-type', '')
                    status = response.status
                    ad_network_hits.append(url[:150])
                    if status == 200 and 'json' in ct:
                        data = await response.json()
                        print(f"\n[AD-JSON] {url[:80]}")
                        print(f"  keys: {list(data.keys())[:10]}")
                    elif status == 200 and ('text' in ct or 'javascript' in ct):
                        body = await response.text()
                        if 'adurl=' in body:
                            import re
                            adup = re.findall(r'adurl=([^&"\'<>\s]{10,200})', body)
                            print(f"\n[AD-TEXT] adurl found: {len(adup)}")
                            for u in adup[:5]:
                                print(f"  {u[:120]}")
                except:
                    pass

        def _print_ad_data(d, indent=""):
            """광고 데이터 핵심 필드 출력."""
            for key in ('advertiserName', 'adTitle', 'headline', 'description',
                        'clickthroughEndpoint', 'navigationEndpoint',
                        'companionAdRenderers', 'adVideoId', 'vastMediaWidth',
                        'getAdBreakUrl', 'prefetchMilliseconds'):
                if key in d:
                    val = d[key]
                    if isinstance(val, (str, int, float, bool)):
                        print(f"{indent}{key}: {str(val)[:150]}")
                    elif isinstance(val, dict):
                        print(f"{indent}{key}: {json.dumps(val, ensure_ascii=False)[:200]}")
                    elif isinstance(val, list):
                        print(f"{indent}{key}: [{len(val)} items]")

        page.on('response', on_response)

        # YouTube 홈 -> 영상 수집
        print(">>> YouTube home...")
        await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # 스크롤해서 영상 링크 로딩
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, 800)")
            await page.wait_for_timeout(1500)

        video_urls = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/watch?v="]');
            const seen = new Set();
            const urls = [];
            for (const a of links) {
                const href = a.href || '';
                if (!href.includes('/watch?v=')) continue;
                const clean = href.split('&')[0];
                if (seen.has(clean)) continue;
                seen.add(clean);
                urls.push(clean);
                if (urls.length >= 5) break;
            }
            return urls;
        }""")
        print(f"  Videos found: {len(video_urls)}")
        for v in video_urls:
            print(f"    {v}")

        # 영상 3개 방문
        targets = video_urls[:3] if video_urls else [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ]

        for i, vurl in enumerate(targets):
            print(f"\n>>> [{i+1}/{len(targets)}] Loading: {vurl[:70]}...")
            await page.goto(vurl, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            try:
                await page.evaluate("""() => {
                    const v = document.querySelector('video');
                    if (v && v.paused) v.play().catch(() => {});
                }""")
            except:
                pass

            # 광고 대기 15초
            print("  Waiting 15s for ads...")
            await page.wait_for_timeout(15000)

            # ytInitialPlayerResponse
            try:
                initial = await page.evaluate(
                    "() => window.ytInitialPlayerResponse || null"
                )
                if initial:
                    ap = initial.get('adPlacements', [])
                    pa = initial.get('playerAds', [])
                    print(f"  [ytInitial] adPlacements={len(ap)}, playerAds={len(pa)}")
                    for j, pl in enumerate(ap):
                        r = pl.get('adPlacementRenderer', {}).get('renderer', {})
                        for k, v in r.items():
                            if isinstance(v, dict):
                                print(f"    initial.placement[{j}].{k}: {list(v.keys())[:8]}")
                                _print_ad_data(v, "      ")
            except Exception as e:
                print(f"  ytInitial error: {e}")

        # 요약
        print(f"\n=== SUMMARY ===")
        print(f"Player API responses: {len(player_data_list)}")
        print(f"Ad network hits: {len(ad_network_hits)}")
        for h in ad_network_hits[:20]:
            print(f"  {h}")

        await page.wait_for_timeout(2000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
