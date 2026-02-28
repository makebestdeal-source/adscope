"""오픈애즈(OpenAds) 매체 데이터 수집기.

openads.co.kr에서 매체별 광고비 트렌드, 업종별 현황 등
시장 데이터를 수집한다. 나스미디어 운영.

수집 방식: Playwright headless로 네트워크 캡처 → 내부 API 파악
스케줄: 주 1회 (월요일 08:00)
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx
from loguru import logger

from database import async_session


# ── DB 테이블 ──

async def _ensure_openads_table():
    """openads_market_data 테이블 생성."""
    import aiosqlite
    async with aiosqlite.connect("adscope.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS openads_market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_type TEXT NOT NULL,
                category TEXT,
                medium TEXT,
                period TEXT,
                metric_name TEXT,
                metric_value REAL,
                raw_data TEXT,
                source_url TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS ix_openads_type_period
            ON openads_market_data(data_type, period)
        """)
        await db.commit()


async def collect_openads_data() -> dict:
    """오픈애즈에서 시장 데이터 수집.

    1단계: 사이트 구조 파악 (내부 API 캡처)
    2단계: 수집 가능 데이터 자동 추출

    Returns:
        {"collected": N, "api_endpoints": [...], "data_types": [...]}
    """
    await _ensure_openads_table()

    logger.info("[openads] Starting data collection from openads.co.kr")

    # Playwright로 사이트 탐색 + API 캡처
    api_endpoints: list[str] = []
    collected_data: list[dict] = []

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            # API 엔드포인트 캡처
            async def on_response(response):
                url = response.url
                try:
                    if response.status != 200:
                        return
                    ct = response.headers.get("content-type", "")

                    # API 호출 감지
                    if "api" in url.lower() or "json" in ct:
                        if "openads.co.kr" in url:
                            api_endpoints.append(url)
                            if "json" in ct:
                                try:
                                    body = await response.json()
                                    collected_data.append({
                                        "url": url,
                                        "data": body,
                                    })
                                except Exception:
                                    pass
                except Exception:
                    pass

            page.on("response", on_response)

            # 주요 페이지 순회
            pages_to_visit = [
                ("https://www.openads.co.kr", "main"),
                ("https://www.openads.co.kr/content/contentMain", "content"),
                ("https://www.openads.co.kr/trend/trendMain", "trend"),
            ]

            for url, page_type in pages_to_visit:
                try:
                    await page.goto(url, wait_until="networkidle", timeout=20000)
                    await page.wait_for_timeout(2000)
                    logger.debug("[openads] Visited {} ({})", page_type, url)
                except Exception as e:
                    logger.debug("[openads] Failed to visit {}: {}", page_type, str(e)[:60])

            await browser.close()

    except Exception as e:
        logger.error("[openads] Playwright failed: {}", str(e)[:100])

    # 발견된 API 엔드포인트 로깅
    unique_apis = list(set(api_endpoints))
    if unique_apis:
        logger.info("[openads] Discovered {} API endpoints", len(unique_apis))
        for ep in unique_apis[:10]:
            logger.debug("[openads]   -> {}", ep[:120])

    # 수집된 데이터 저장
    saved_count = 0
    if collected_data:
        import aiosqlite
        async with aiosqlite.connect("adscope.db") as db:
            for item in collected_data:
                try:
                    raw_json = json.dumps(item["data"], ensure_ascii=False, default=str)
                    await db.execute("""
                        INSERT INTO openads_market_data
                        (data_type, raw_data, source_url)
                        VALUES (?, ?, ?)
                    """, ("api_capture", raw_json[:5000], item["url"]))
                    saved_count += 1
                except Exception:
                    pass
            await db.commit()

    result = {
        "collected": saved_count,
        "api_endpoints": unique_apis[:20],
        "data_types": list({d.get("url", "").split("/")[-1].split("?")[0] for d in collected_data}),
    }
    logger.info("[openads] Collection done: {}", result)
    return result


async def collect_openads_reports() -> dict:
    """오픈애즈 콘텐츠/리포트 목록 수집.

    인크로스, 나스미디어 등 미디어렙 보고서 메타데이터 수집.
    """
    collected: list[dict] = []

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            )
            page = await context.new_page()

            # 콘텐츠 페이지
            await page.goto(
                "https://www.openads.co.kr/content/contentMain",
                wait_until="networkidle",
                timeout=20000,
            )
            await page.wait_for_timeout(2000)

            # 콘텐츠 카드에서 제목/링크 추출
            cards = page.locator("a[href*='contentDetail']")
            count = await cards.count()
            for i in range(min(count, 30)):
                try:
                    href = await cards.nth(i).get_attribute("href")
                    title = (await cards.nth(i).inner_text()).strip()
                    if title and href:
                        collected.append({
                            "title": title[:200],
                            "url": f"https://www.openads.co.kr{href}" if href.startswith("/") else href,
                        })
                except Exception:
                    pass

            await browser.close()

    except Exception as e:
        logger.error("[openads] Report collection failed: {}", str(e)[:100])

    logger.info("[openads] Collected {} report links", len(collected))
    return {"reports": collected, "count": len(collected)}
