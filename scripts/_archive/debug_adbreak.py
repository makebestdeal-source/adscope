"""YouTube innertube API 직접 호출로 광고 데이터 추출."""
import asyncio, json, sys, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from playwright.async_api import async_playwright

INNERTUBE_API = "https://www.youtube.com/youtubei/v1/player"
INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"

# 실제 Chrome 브라우저를 시뮬레이션하는 innertube context
INNERTUBE_CONTEXT = {
    "client": {
        "hl": "ko",
        "gl": "KR",
        "clientName": "WEB",
        "clientVersion": "2.20260213.01.00",
        "platform": "DESKTOP",
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "osName": "Windows",
        "osVersion": "10.0",
        "browserName": "Chrome",
        "browserVersion": "120.0.0.0",
    }
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        )
        page = await ctx.new_page()
        await ctx.add_cookies([
            {'name': 'CONSENT', 'value': 'YES+cb.20260215-00-p0.kr+FX+999', 'domain': '.youtube.com', 'path': '/'},
        ])

        # 먼저 YouTube 방문해서 쿠키 획득
        await page.goto("https://www.youtube.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # 인기 영상 ID 수집
        video_ids = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href*="/watch?v="]');
            const ids = new Set();
            for (const a of links) {
                const m = (a.href || '').match(/v=([a-zA-Z0-9_-]{11})/);
                if (m) ids.add(m[1]);
                if (ids.size >= 5) break;
            }
            return [...ids];
        }""")

        if not video_ids:
            video_ids = ["ZeerrnuLi5E", "dQw4w9WgXcQ", "9bZkp7q19f0"]

        print(f"Test video IDs: {video_ids}")

        for vid in video_ids:
            print(f"\n>>> Video: {vid}")

            # innertube API 직접 호출
            body = {
                "videoId": vid,
                "context": INNERTUBE_CONTEXT,
                "contentCheckOk": True,
                "racyCheckOk": True,
                "params": "CgIQBg==",  # 광고 포함 파라미터
            }

            try:
                resp = await page.request.post(
                    f"{INNERTUBE_API}?key={INNERTUBE_KEY}&prettyPrint=false",
                    data=json.dumps(body),
                    headers={
                        "Content-Type": "application/json",
                        "X-YouTube-Client-Name": "1",
                        "X-YouTube-Client-Version": "2.20260213.01.00",
                        "Origin": "https://www.youtube.com",
                        "Referer": f"https://www.youtube.com/watch?v={vid}",
                    },
                    timeout=10000,
                )
                if resp.status != 200:
                    print(f"  Status: {resp.status}")
                    continue

                data = await resp.json()

                # adPlacements 확인
                ap = data.get('adPlacements', [])
                pa = data.get('playerAds', [])
                print(f"  adPlacements={len(ap)}, playerAds={len(pa)}")

                for i, pl in enumerate(ap):
                    renderer = pl.get('adPlacementRenderer', {})
                    config = renderer.get('config', {}).get('adPlacementConfig', {})
                    kind = config.get('kind', 'unknown')
                    r = renderer.get('renderer', {})
                    keys = list(r.keys())
                    print(f"  placement[{i}]: kind={kind}, renderer={keys}")

                    for k, v in r.items():
                        if isinstance(v, dict):
                            # 광고 데이터 필드 탐색
                            for field in ('advertiserName', 'headline', 'adTitle', 'description',
                                         'clickthroughEndpoint', 'getAdBreakUrl', 'adVideoId',
                                         'companionAdRenderers'):
                                if field in v:
                                    val = v[field]
                                    if isinstance(val, (str, int, bool)):
                                        print(f"    {field}: {val}")
                                    elif isinstance(val, dict):
                                        print(f"    {field}: {json.dumps(val, ensure_ascii=False)[:150]}")
                                    elif isinstance(val, list):
                                        print(f"    {field}: [{len(val)} items]")

                for i, pad in enumerate(pa):
                    print(f"  playerAd[{i}]: {list(pad.keys())}")
                    for k, v in pad.items():
                        if isinstance(v, dict):
                            for field in ('advertiserName', 'headline', 'adTitle', 'clickthroughEndpoint'):
                                if field in v:
                                    print(f"    {field}: {json.dumps(v[field], ensure_ascii=False)[:150]}")

                # adSlots 확인 (다른 광고 구조)
                ad_slots = data.get('adSlots', [])
                if ad_slots:
                    print(f"  adSlots: {len(ad_slots)}")
                    for i, slot in enumerate(ad_slots):
                        print(f"    slot[{i}]: {list(slot.keys())[:5]}")

            except Exception as e:
                print(f"  Error: {e}")

        await browser.close()

asyncio.run(main())
