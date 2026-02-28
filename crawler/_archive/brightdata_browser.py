"""Bright Data Scraping Browser 연동.

Playwright를 통해 Bright Data의 스크래핑 브라우저에 연결.
CAPTCHA 자동 해결 + 봇탐지 우회로 차단된 사이트(쿠팡 등) 수집 가능.

.env 필요:
  BRIGHTDATA_WS_ENDPOINT=wss://brd-customer-{ID}-zone-{ZONE}:{PASSWORD}@brd.superproxy.io:9515

사용법:
  from crawler.brightdata_browser import create_brightdata_browser
  browser, page = await create_brightdata_browser()
  await page.goto('https://www.coupang.com')
  # ... 수집 로직
  await browser.close()
"""

from __future__ import annotations

import os

from loguru import logger
from playwright.async_api import async_playwright, Browser, Page


# Bright Data WebSocket endpoint
BD_ENDPOINT = os.getenv("BRIGHTDATA_WS_ENDPOINT", "")


async def create_brightdata_browser(
    endpoint: str | None = None,
) -> tuple[Browser, Page]:
    """Bright Data Scraping Browser에 Playwright로 연결.

    Args:
        endpoint: WebSocket endpoint (None이면 .env에서 로드)

    Returns:
        (browser, page) tuple
    """
    ws_url = endpoint or BD_ENDPOINT
    if not ws_url:
        raise ValueError(
            "BRIGHTDATA_WS_ENDPOINT not set. "
            "Format: wss://brd-customer-{ID}-zone-{ZONE}:{PW}@brd.superproxy.io:9515"
        )

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(ws_url)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = context.pages[0] if context.pages else await context.new_page()

    logger.info("[brightdata] Connected to scraping browser")
    return browser, page


async def scrape_with_brightdata(
    url: str,
    wait_selector: str | None = None,
    timeout: int = 30000,
) -> dict:
    """Bright Data로 단일 URL 스크래핑.

    Returns:
        {"url": str, "title": str, "html_length": int, "success": bool}
    """
    if not BD_ENDPOINT:
        return {"url": url, "success": False, "error": "no_endpoint"}

    try:
        browser, page = await create_brightdata_browser()

        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

        if wait_selector:
            await page.wait_for_selector(wait_selector, timeout=10000)

        title = await page.title()
        html = await page.content()

        await browser.close()

        return {
            "url": url,
            "title": title,
            "html_length": len(html),
            "success": True,
        }
    except Exception as e:
        logger.error("[brightdata] Scrape failed: {}", str(e)[:100])
        return {"url": url, "success": False, "error": str(e)[:100]}


async def collect_coupang_ads() -> dict:
    """Bright Data로 쿠팡 광고 수집 (Akamai 우회).

    쿠팡 메인/카테고리 페이지에서 광고 배너 수집.
    """
    if not BD_ENDPOINT:
        logger.warning("[brightdata] No endpoint configured, skipping Coupang")
        return {"collected": 0, "error": "no_endpoint"}

    urls = [
        "https://www.coupang.com/",
        "https://www.coupang.com/np/categories/194176",  # 식품
        "https://www.coupang.com/np/categories/115573",  # 뷰티
        "https://www.coupang.com/np/categories/176557",  # 가전
    ]

    collected = []

    try:
        browser, page = await create_brightdata_browser()

        # 네트워크 캡처 (광고 응답)
        ad_responses = []

        async def on_response(response):
            url = response.url
            try:
                if response.status == 200:
                    # 쿠팡 광고 API 패턴
                    if any(kw in url for kw in ["ad", "banner", "campaign", "display"]):
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.json()
                            ad_responses.append({"url": url, "data": body})
            except Exception:
                pass

        page.on("response", on_response)

        for url in urls:
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(3000)
                logger.debug("[brightdata] Visited: {}", url[:60])
            except Exception as e:
                logger.debug("[brightdata] Failed: {} - {}", url[:40], str(e)[:40])

        await browser.close()

        # 수집된 광고 저장
        if ad_responses:
            import aiosqlite
            import json
            from datetime import datetime, timezone

            async with aiosqlite.connect("adscope.db") as db:
                for resp in ad_responses:
                    await db.execute("""
                        INSERT INTO serpapi_ads
                        (advertiser_name, format, target_domain, extra_data)
                        VALUES (?, 'image', 'coupang.com', ?)
                    """, (
                        "coupang_ad",
                        json.dumps(resp["data"], ensure_ascii=False, default=str)[:5000],
                    ))
                    collected.append(resp["url"])
                await db.commit()

    except Exception as e:
        logger.error("[brightdata] Coupang collection failed: {}", str(e)[:100])

    result = {"collected": len(collected), "ad_api_endpoints": [r["url"] for r in ad_responses[:10]]}
    logger.info("[brightdata] Coupang done: {}", result)
    return result
