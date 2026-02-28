"""YouTube adPlacements 실제 파싱 테스트 — 광고주/URL 추출 확인."""
import asyncio
import json
from playwright.async_api import async_playwright

JS_EXTRACT = """() => {
    const pr = window.ytInitialPlayerResponse;
    if (!pr) return null;

    const result = {
        adPlacements: [],
        playerAds: [],
    };

    for (const p of (pr.adPlacements || [])) {
        const renderer = p.adPlacementRenderer || {};
        const config = renderer.config || {};
        const kind = (config.adPlacementConfig || {}).kind || '';
        const r = renderer.renderer || {};
        const rKeys = Object.keys(r);
        const rData = rKeys.length > 0 ? r[rKeys[0]] : {};

        // 광고주 정보 탐색
        let advertiser = null;
        let clickUrl = null;
        let adText = null;

        // 재귀적으로 키 찾기
        const findKey = (obj, keys, depth) => {
            if (!obj || typeof obj !== 'object' || depth > 5) return null;
            for (const k of keys) {
                if (obj[k] !== undefined) return obj[k];
            }
            for (const v of Object.values(obj)) {
                const found = findKey(v, keys, depth + 1);
                if (found) return found;
            }
            return null;
        };

        advertiser = findKey(rData, ['advertiserName', 'adTitle'], 0);
        if (typeof advertiser === 'object' && advertiser) {
            advertiser = advertiser.simpleText || (advertiser.runs && advertiser.runs[0] && advertiser.runs[0].text) || JSON.stringify(advertiser).slice(0, 100);
        }

        // headline
        const headline = findKey(rData, ['headline'], 0);
        if (!advertiser && headline) {
            advertiser = typeof headline === 'string' ? headline :
                (headline.simpleText || (headline.runs && headline.runs[0] && headline.runs[0].text) || null);
        }

        // clickthrough URL
        const clickEp = findKey(rData, ['clickthroughEndpoint', 'navigationEndpoint'], 0);
        if (clickEp) {
            const urlEp = clickEp.urlEndpoint || clickEp;
            clickUrl = urlEp.url || null;
        }

        // pings
        const pings = findKey(rData, ['pings'], 0);
        if (pings && pings.clickthroughPings) {
            const first = pings.clickthroughPings[0];
            if (!clickUrl) clickUrl = typeof first === 'string' ? first : (first && first.baseUrl);
        }

        result.adPlacements.push({
            kind: kind,
            rendererType: rKeys[0] || 'unknown',
            advertiser: advertiser,
            clickUrl: clickUrl ? clickUrl.slice(0, 200) : null,
            hasData: !!(advertiser || clickUrl),
        });
    }

    for (const pa of (pr.playerAds || [])) {
        const keys = Object.keys(pa);
        const rType = keys[0] || 'unknown';
        const rData = pa[rType] || {};

        let advertiser = null;
        const findKey2 = (obj, keys2, depth) => {
            if (!obj || typeof obj !== 'object' || depth > 5) return null;
            for (const k of keys2) {
                if (obj[k] !== undefined) return obj[k];
            }
            for (const v of Object.values(obj)) {
                const found = findKey2(v, keys2, depth + 1);
                if (found) return found;
            }
            return null;
        };

        advertiser = findKey2(rData, ['advertiserName', 'adTitle', 'headline'], 0);
        if (typeof advertiser === 'object' && advertiser) {
            advertiser = advertiser.simpleText || (advertiser.runs && advertiser.runs[0] && advertiser.runs[0].text) || null;
        }

        const clickEp = findKey2(rData, ['clickthroughEndpoint', 'navigationEndpoint'], 0);
        let clickUrl = null;
        if (clickEp) {
            const urlEp = clickEp.urlEndpoint || clickEp;
            clickUrl = urlEp.url || null;
        }

        result.playerAds.push({
            type: rType,
            advertiser: advertiser,
            clickUrl: clickUrl ? clickUrl.slice(0, 200) : null,
        });
    }

    return result;
}"""


async def main():
    print("=== YouTube 광고 파싱 상세 테스트 ===\n")

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
        ctx = await browser.new_context(locale="ko-KR")
        await ctx.add_cookies([
            {"name": "CONSENT", "value": "YES+cb.20260215-00-p0.kr+FX+999",
             "domain": ".youtube.com", "path": "/"},
        ])
        page = await ctx.new_page()

        for url in test_videos:
            vid = url.split("v=")[1]
            print(f"--- {vid} ---")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                await page.wait_for_timeout(3000)
                result = await page.evaluate(JS_EXTRACT)
                if result:
                    print(f"  adPlacements ({len(result['adPlacements'])}):")
                    for ap in result["adPlacements"]:
                        print(f"    kind={ap['kind']}, type={ap['rendererType']}, "
                              f"advertiser={ap['advertiser']}, hasData={ap['hasData']}")
                        if ap["clickUrl"]:
                            print(f"    clickUrl={ap['clickUrl'][:120]}")
                    print(f"  playerAds ({len(result['playerAds'])}):")
                    for pa in result["playerAds"]:
                        print(f"    type={pa['type']}, advertiser={pa['advertiser']}")
                        if pa["clickUrl"]:
                            print(f"    clickUrl={pa['clickUrl'][:120]}")
                else:
                    print("  ytInitialPlayerResponse 없음")
            except Exception as e:
                print(f"  ERROR: {str(e)[:120]}")
            print()

        await browser.close()
    print("=== 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
