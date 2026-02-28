"""SerpApi Google Ads Transparency Center 수집기.

SerpApi를 통해 Google Ads Transparency Center에서
광고주별 광고 크리에이티브(텍스트/이미지/영상)를 수집한다.

무료 100회/월이므로 ADIC 상위 광고주 위주로 효율적 사용.

.env 필요:
  SERPAPI_KEY=<API Key>
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import httpx
from loguru import logger

from database import async_session
from database.models import Advertiser

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
API_URL = "https://serpapi.com/search"
REGION_KR = "2410"  # South Korea (ISO 3166-1 numeric prefix)


async def search_advertiser_ads(
    query: str,
    *,
    creative_format: str | None = None,
    num: int = 100,
    region: str = REGION_KR,
    days_back: int = 30,
) -> dict:
    """SerpApi로 광고주의 Google Ads 크리에이티브 검색.

    Args:
        query: 도메인 또는 광고주명
        creative_format: text, image, video (None=전체)
        num: 결과 수 (max 100)
        region: 지역 코드
        days_back: 최근 N일

    Returns:
        {"ad_creatives": [...], "total_results": N, "query": str}
    """
    if not SERPAPI_KEY:
        logger.warning("[serpapi] SERPAPI_KEY not set in .env")
        return {"ad_creatives": [], "total_results": 0, "query": query}

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    params = {
        "engine": "google_ads_transparency_center",
        "text": query,
        "region": region,
        "num": str(num),
        "start_date": start_date.strftime("%Y%m%d"),
        "end_date": end_date.strftime("%Y%m%d"),
        "api_key": SERPAPI_KEY,
        "output": "json",
    }
    if creative_format:
        params["creative_format"] = creative_format

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_URL, params=params)

            if resp.status_code == 200:
                data = resp.json()
                creatives = data.get("ad_creatives", [])
                total = data.get("search_information", {}).get("total_results", len(creatives))
                logger.info(
                    "[serpapi] '{}': {} creatives (total: {})",
                    query, len(creatives), total,
                )
                return {
                    "ad_creatives": creatives,
                    "total_results": total,
                    "query": query,
                    "next_page_token": data.get("serpapi_pagination", {}).get("next_page_token"),
                }
            elif resp.status_code == 401:
                logger.error("[serpapi] Invalid API key")
            elif resp.status_code == 429:
                logger.warning("[serpapi] Rate limit / quota exceeded")
            else:
                logger.warning("[serpapi] HTTP {}: {}", resp.status_code, resp.text[:200])

    except Exception as e:
        logger.error("[serpapi] Request failed: {}", str(e)[:100])

    return {"ad_creatives": [], "total_results": 0, "query": query}


def _extract_domain(creative: dict) -> str | None:
    """크리에이티브에서 랜딩 도메인 추출."""
    target = creative.get("target_domain", "")
    if target:
        return target.lower().strip()
    return None


def _creative_to_ad_detail(creative: dict, advertiser_name: str) -> dict:
    """SerpApi 크리에이티브 -> pipeline 호환 dict 변환."""
    fmt = creative.get("format", "text")
    first_shown = creative.get("first_shown")
    last_shown = creative.get("last_shown")

    # timestamp -> datetime
    first_dt = None
    last_dt = None
    if first_shown:
        try:
            first_dt = datetime.fromtimestamp(first_shown, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            pass
    if last_shown:
        try:
            last_dt = datetime.fromtimestamp(last_shown, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            pass

    # 이미지/영상 URL
    media_url = creative.get("image") or creative.get("link", "")

    return {
        "channel": "google_gdn",
        "advertiser_name": advertiser_name,
        "ad_creative_id": creative.get("ad_creative_id", ""),
        "google_advertiser_id": creative.get("advertiser_id", ""),
        "format": fmt,
        "media_url": media_url,
        "target_domain": _extract_domain(creative),
        "width": creative.get("width"),
        "height": creative.get("height"),
        "first_shown": first_dt,
        "last_shown": last_dt,
        "details_link": creative.get("details_link", ""),
    }


async def _ensure_serpapi_table():
    """serpapi_ads 테이블 생성."""
    import aiosqlite
    async with aiosqlite.connect("adscope.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS serpapi_ads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertiser_name TEXT NOT NULL,
                advertiser_id INTEGER,
                serpapi_creative_id TEXT UNIQUE,
                google_advertiser_id TEXT,
                google_advertiser_name TEXT,
                format TEXT,
                media_url TEXT,
                target_domain TEXT,
                width INTEGER,
                height INTEGER,
                first_shown TIMESTAMP,
                last_shown TIMESTAMP,
                details_link TEXT,
                extra_data TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS ix_serpapi_advertiser
            ON serpapi_ads(advertiser_name)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS ix_serpapi_domain
            ON serpapi_ads(target_domain)
        """)
        await db.commit()


async def _save_serpapi_results(results: list[dict], advertiser_name: str) -> int:
    """SerpApi 결과를 serpapi_ads 테이블에 저장.

    중복 체크: serpapi_creative_id UNIQUE.
    """
    import aiosqlite

    if not results:
        return 0

    await _ensure_serpapi_table()

    saved = 0
    async with aiosqlite.connect("adscope.db") as db:
        # advertiser_id 매칭
        adv_id = None
        cursor = await db.execute(
            "SELECT id FROM advertisers WHERE name = ? OR brand_name = ?",
            (advertiser_name, advertiser_name),
        )
        row = await cursor.fetchone()
        if row:
            adv_id = row[0]

        for creative in results:
            ad = _creative_to_ad_detail(creative, advertiser_name)
            creative_id = ad["ad_creative_id"]
            if not creative_id:
                continue

            try:
                await db.execute("""
                    INSERT OR IGNORE INTO serpapi_ads
                    (advertiser_name, advertiser_id, serpapi_creative_id,
                     google_advertiser_id, google_advertiser_name,
                     format, media_url, target_domain,
                     width, height, first_shown, last_shown, details_link)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    advertiser_name,
                    adv_id,
                    creative_id,
                    ad["google_advertiser_id"],
                    creative.get("advertiser", ""),
                    ad["format"],
                    ad["media_url"],
                    ad["target_domain"],
                    ad["width"],
                    ad["height"],
                    ad["first_shown"].isoformat() if ad["first_shown"] else None,
                    ad["last_shown"].isoformat() if ad["last_shown"] else None,
                    ad["details_link"],
                ))
                if db.total_changes:
                    saved += 1
            except Exception:
                pass

        await db.commit()

    return saved


async def collect_top_advertiser_ads(
    max_queries: int = 50,
    days_back: int = 30,
) -> dict:
    """ADIC 상위 광고주 기준 Google Ads 수집.

    Args:
        max_queries: 최대 API 호출 수 (무료 100/월)
        days_back: 최근 N일

    Returns:
        {"queries": N, "total_creatives": M, "saved": S}
    """
    if not SERPAPI_KEY:
        logger.warning("[serpapi] SERPAPI_KEY not configured")
        return {"queries": 0, "total_creatives": 0, "saved": 0, "error": "no_api_key"}

    # 1. ADIC 상위 광고주 로드
    import aiosqlite
    queries: list[tuple[str, str | None]] = []  # (search_query, advertiser_name)

    async with aiosqlite.connect("adscope.db") as db:
        db.row_factory = aiosqlite.Row
        # ADIC 광고비 상위 + DB 매칭된 광고주 (website 있으면 도메인으로 검색)
        cursor = await db.execute("""
            SELECT ae.advertiser_name, ae.advertiser_id, a.website,
                   SUM(ae.amount) as total_spend
            FROM adic_ad_expenses ae
            LEFT JOIN advertisers a ON ae.advertiser_id = a.id
            WHERE ae.medium = 'total' AND ae.month IS NOT NULL
            GROUP BY ae.advertiser_name
            ORDER BY total_spend DESC
            LIMIT ?
        """, (max_queries * 2,))
        rows = await cursor.fetchall()

        for row in rows:
            name = row["advertiser_name"]
            website = row["website"] or ""

            # 도메인 추출
            if website:
                try:
                    parsed = urlparse(website)
                    domain = parsed.netloc or parsed.path
                    domain = domain.replace("www.", "")
                    if domain:
                        queries.append((domain, name))
                        continue
                except Exception:
                    pass

            # 도메인 없으면 이름으로 검색
            queries.append((name, name))

        # DB 광고주 중 website 있고 ADIC에 없는 것도 추가
        cursor = await db.execute("""
            SELECT name, website FROM advertisers
            WHERE website IS NOT NULL AND length(website) > 5
            AND name NOT IN (SELECT advertiser_name FROM adic_ad_expenses)
            ORDER BY id
            LIMIT ?
        """, (max_queries,))
        extra_rows = await cursor.fetchall()
        for row in extra_rows:
            try:
                parsed = urlparse(row["website"])
                domain = (parsed.netloc or parsed.path).replace("www.", "")
                if domain and len(domain) > 3:
                    queries.append((domain, row["name"]))
            except Exception:
                pass

    # 중복 제거 + 제한
    seen = set()
    unique_queries = []
    for q, name in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append((q, name))
    unique_queries = unique_queries[:max_queries]

    logger.info("[serpapi] Searching {} advertisers", len(unique_queries))

    total_creatives = 0
    total_saved = 0
    queries_used = 0

    for query, adv_name in unique_queries:
        result = await search_advertiser_ads(
            query, days_back=days_back,
        )
        creatives = result.get("ad_creatives", [])
        total_creatives += len(creatives)
        queries_used += 1

        if creatives:
            saved = await _save_serpapi_results(creatives, adv_name)
            total_saved += saved
            logger.info(
                "[serpapi] '{}' ({}): {} found, {} saved",
                adv_name, query, len(creatives), saved,
            )

        # Rate limit: 2초 간격
        await asyncio.sleep(2)

    result = {
        "queries": queries_used,
        "total_creatives": total_creatives,
        "saved": total_saved,
    }
    logger.info("[serpapi] Collection done: {}", result)
    return result


async def search_single(query: str, days_back: int = 30) -> dict:
    """단일 광고주/도메인 검색 (테스트용).

    Returns:
        {"query": str, "creatives": int, "saved": int, "samples": [...]}
    """
    result = await search_advertiser_ads(query, days_back=days_back)
    creatives = result.get("ad_creatives", [])

    saved = 0
    if creatives:
        saved = await _save_serpapi_results(creatives, query)

    samples = []
    for c in creatives[:5]:
        samples.append({
            "advertiser": c.get("advertiser", ""),
            "format": c.get("format", ""),
            "domain": c.get("target_domain", ""),
            "first_shown": c.get("first_shown"),
        })

    return {
        "query": query,
        "creatives": len(creatives),
        "saved": saved,
        "samples": samples,
    }


# ── 무료 Google Ads Transparency 직접 스크래핑 ──
# pip install Google-Ads-Transparency-Scraper
# API 키 불필요, 무제한

async def _free_scrape_advertiser(query: str, count: int = 100) -> list[dict]:
    """무료 스크래퍼로 Google Ads Transparency 직접 수집.

    Returns:
        SerpApi 호환 크리에이티브 리스트
    """
    try:
        from GoogleAds.main import GoogleAds
    except ImportError:
        logger.warning("[google_ads_free] GoogleAds package not installed")
        return []

    creatives = []

    def _scrape():
        ga = GoogleAds(region="anywhere")

        # 1. 검색으로 advertiser ID 찾기
        result = ga.get_creative_Ids(query, count=count)
        if not isinstance(result, dict):
            return []

        adv_id = result.get("Advertisor Id", "")
        adv_name = result.get("Advertisor", "")
        creative_ids = result.get("Creative_Ids", [])
        total = int(result.get("Ad Count", 0))

        if not creative_ids:
            return []

        items = []
        for cid in creative_ids[:count]:
            try:
                detail = ga.get_detailed_ad(adv_id, cid)
                if isinstance(detail, dict):
                    fmt = detail.get("Ad Format", "text").lower()
                    items.append({
                        "advertiser_id": adv_id,
                        "advertiser": adv_name,
                        "ad_creative_id": cid,
                        "format": fmt,
                        "image": detail.get("Image URL", ""),
                        "link": detail.get("Ad Link", ""),
                        "target_domain": "",
                        "last_shown": detail.get("Last Shown"),
                        "first_shown": detail.get("Last Shown"),
                    })
            except Exception:
                pass
        return items

    # 블로킹 호출이므로 executor에서 실행
    loop = asyncio.get_event_loop()
    creatives = await loop.run_in_executor(None, _scrape)
    return creatives


async def collect_free_google_ads(
    max_advertisers: int = 200,
) -> dict:
    """무료 스크래퍼로 대규모 Google Ads 수집.

    SerpApi 제한(100회/월) 없이 무제한 수집.

    Returns:
        {"advertisers_searched": N, "total_creatives": M, "saved": S}
    """
    import aiosqlite

    await _ensure_serpapi_table()

    # 1. 수집 대상 로드 (ADIC + DB 광고주)
    queries: list[tuple[str, str]] = []

    async with aiosqlite.connect("adscope.db") as db:
        db.row_factory = aiosqlite.Row

        # ADIC 상위 광고주 (도메인/이름)
        cursor = await db.execute("""
            SELECT ae.advertiser_name, a.website,
                   SUM(ae.amount) as total_spend
            FROM adic_ad_expenses ae
            LEFT JOIN advertisers a ON ae.advertiser_id = a.id
            WHERE ae.medium = 'total' AND ae.month IS NOT NULL
            GROUP BY ae.advertiser_name
            ORDER BY total_spend DESC
        """)
        for row in await cursor.fetchall():
            name = row["advertiser_name"]
            website = row["website"] or ""
            if website:
                try:
                    parsed = urlparse(website)
                    domain = (parsed.netloc or parsed.path).replace("www.", "")
                    if domain:
                        queries.append((domain, name))
                        continue
                except Exception:
                    pass
            queries.append((name, name))

        # DB 광고주 (website 있는 것)
        cursor = await db.execute("""
            SELECT name, website FROM advertisers
            WHERE website IS NOT NULL AND length(website) > 5
            ORDER BY id
        """)
        for row in await cursor.fetchall():
            try:
                parsed = urlparse(row["website"])
                domain = (parsed.netloc or parsed.path).replace("www.", "")
                if domain and len(domain) > 3:
                    queries.append((domain, row["name"]))
            except Exception:
                pass

    # 중복 제거
    seen = set()
    unique = []
    for q, name in queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique.append((q, name))
    unique = unique[:max_advertisers]

    logger.info("[google_ads_free] Scraping {} advertisers", len(unique))

    total_creatives = 0
    total_saved = 0
    searched = 0

    for query, adv_name in unique:
        try:
            creatives = await _free_scrape_advertiser(query, count=100)
            total_creatives += len(creatives)
            searched += 1

            if creatives:
                saved = await _save_serpapi_results(creatives, adv_name)
                total_saved += saved
                if saved > 0:
                    logger.info(
                        "[google_ads_free] '{}': {} found, {} saved",
                        adv_name, len(creatives), saved,
                    )
        except Exception as e:
            logger.debug("[google_ads_free] '{}' failed: {}", query, str(e)[:60])

        # Rate limit: 1초 간격
        await asyncio.sleep(1)

    result = {
        "advertisers_searched": searched,
        "total_creatives": total_creatives,
        "saved": total_saved,
    }
    logger.info("[google_ads_free] Done: {}", result)
    return result
