"""네이버 브랜드검색 광고 존재 여부 점검.

모든 광고주를 대상으로 PC/모바일에서 브랜드명을 검색하여
브랜드검색 광고가 집행되고 있는지 확인 → DB 기록.

Usage:
    python scripts/check_brand_search.py
    python scripts/check_brand_search.py --limit 50
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from playwright.async_api import async_playwright


DB_PATH = os.path.join(_root, "adscope.db")
SEARCH_PRODUCTS = {
    "brand_search": False,      # 브랜드검색 (대형 배너)
    "powerlink": False,         # 파워링크 (텍스트 검색광고)
    "shopping_ad": False,       # 쇼핑검색광고
    "place_ad": False,          # 플레이스 광고
    "brand_contents": False,    # 브랜드콘텐츠 (지식/블로그)
}


async def check_brand_search(limit: int = 0):
    """모든 광고주 대상 네이버 브랜드검색 점검."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 테이블 생성 (없으면)
    c.execute("""
        CREATE TABLE IF NOT EXISTS naver_search_products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            advertiser_id INTEGER NOT NULL,
            advertiser_name TEXT NOT NULL,
            has_brand_search INTEGER DEFAULT 0,
            has_powerlink INTEGER DEFAULT 0,
            has_shopping_ad INTEGER DEFAULT 0,
            has_place_ad INTEGER DEFAULT 0,
            has_brand_contents INTEGER DEFAULT 0,
            pc_checked INTEGER DEFAULT 0,
            mobile_checked INTEGER DEFAULT 0,
            brand_search_url TEXT,
            check_date TEXT DEFAULT (datetime('now')),
            UNIQUE(advertiser_id)
        )
    """)
    conn.commit()

    # 광고주 목록
    query = "SELECT id, name FROM advertisers ORDER BY id"
    if limit > 0:
        query += f" LIMIT {limit}"
    advertisers = c.execute(query).fetchall()
    total = len(advertisers)
    print(f"[brand_search] {total} advertisers to check", flush=True)

    stats = {"checked": 0, "brand_search": 0, "powerlink": 0, "shopping": 0, "errors": 0}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # PC context
        pc_ctx = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        # Mobile context
        mobile_ctx = await browser.new_context(
            viewport={"width": 375, "height": 812},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        )

        for idx, (adv_id, adv_name) in enumerate(advertisers):
            # 검색어 정제 (영문/한글 브랜드명만)
            search_name = re.sub(r'\s+\S+\.(com|co\.kr|net|co|kr)\S*', '', adv_name).strip()
            if len(search_name) < 2:
                continue

            result = {
                "brand_search": False,
                "powerlink": False,
                "shopping_ad": False,
                "place_ad": False,
                "brand_contents": False,
                "brand_search_url": None,
                "pc_checked": False,
                "mobile_checked": False,
            }

            try:
                # --- PC 검색 ---
                pc_page = await pc_ctx.new_page()
                pc_responses = []

                async def on_pc_response(response):
                    url = response.url
                    if response.status == 200:
                        # 브랜드검색 API 응답 감지
                        if "brand" in url and ("searchad" in url or "nx" in url or "sa." in url):
                            pc_responses.append(("brand", url))
                        elif "ad.search.naver.com" in url:
                            pc_responses.append(("searchad", url))

                pc_page.on("response", on_pc_response)

                search_url = f"https://search.naver.com/search.naver?query={search_name}"
                await pc_page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
                await pc_page.wait_for_timeout(2000)

                # 네트워크 캡처 기반 탐지: 페이지 HTML에서 키워드 검색
                html = await pc_page.content()

                # 브랜드검색 영역 감지 (HTML 내 특정 패턴)
                if "brand_area" in html or "brandSearch" in html or "nx_brand" in html or "bra_area" in html:
                    result["brand_search"] = True
                    stats["brand_search"] += 1

                # 파워링크 감지
                if "powerlink" in html or "ct_powerlink" in html or "sp_tit" in html:
                    result["powerlink"] = True
                    stats["powerlink"] += 1

                # 쇼핑 광고 감지
                if "ad.search.naver.com/search/ad" in html or "shp_tit" in html:
                    result["shopping_ad"] = True
                    stats["shopping"] += 1

                # 플레이스 광고 감지
                if "place_bluelink" in html or "local_info" in html:
                    result["place_ad"] = True

                result["pc_checked"] = True
                await pc_page.close()

                # --- Mobile 검색 ---
                m_page = await mobile_ctx.new_page()
                m_search_url = f"https://m.search.naver.com/search.naver?query={search_name}"
                await m_page.goto(m_search_url, wait_until="domcontentloaded", timeout=15000)
                await m_page.wait_for_timeout(1500)

                m_html = await m_page.content()
                if not result["brand_search"] and ("brand_area" in m_html or "brandSearch" in m_html or "bra_head" in m_html):
                    result["brand_search"] = True
                    stats["brand_search"] += 1

                if not result["powerlink"] and ("powerlink" in m_html or "spw_txt" in m_html):
                    result["powerlink"] = True
                    stats["powerlink"] += 1

                result["mobile_checked"] = True
                await m_page.close()

                # DB 저장 (UPSERT)
                c.execute("""
                    INSERT INTO naver_search_products
                    (advertiser_id, advertiser_name, has_brand_search, has_powerlink,
                     has_shopping_ad, has_place_ad, has_brand_contents,
                     pc_checked, mobile_checked, brand_search_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(advertiser_id) DO UPDATE SET
                        has_brand_search = excluded.has_brand_search,
                        has_powerlink = excluded.has_powerlink,
                        has_shopping_ad = excluded.has_shopping_ad,
                        has_place_ad = excluded.has_place_ad,
                        has_brand_contents = excluded.has_brand_contents,
                        pc_checked = excluded.pc_checked,
                        mobile_checked = excluded.mobile_checked,
                        brand_search_url = excluded.brand_search_url,
                        check_date = datetime('now')
                """, (
                    adv_id, search_name,
                    1 if result["brand_search"] else 0,
                    1 if result["powerlink"] else 0,
                    1 if result["shopping_ad"] else 0,
                    1 if result["place_ad"] else 0,
                    1 if result["brand_contents"] else 0,
                    1 if result["pc_checked"] else 0,
                    1 if result["mobile_checked"] else 0,
                    result["brand_search_url"],
                ))

                stats["checked"] += 1

                # 50건마다 커밋 + 로그
                if stats["checked"] % 50 == 0:
                    conn.commit()
                    print(f"[brand_search] {stats['checked']}/{total} checked | "
                          f"brand={stats['brand_search']} powerlink={stats['powerlink']} "
                          f"shopping={stats['shopping']}", flush=True)

                # Rate limit
                await asyncio.sleep(0.5)

            except Exception as e:
                stats["errors"] += 1
                err_msg = str(e)[:80]
                if stats["errors"] <= 5:
                    print(f"[brand_search] ERROR {adv_id} '{search_name}': {err_msg}", flush=True)
                try:
                    await pc_page.close()
                except:
                    pass
                try:
                    await m_page.close()
                except:
                    pass

        await pc_ctx.close()
        await mobile_ctx.close()
        await browser.close()

    conn.commit()
    conn.close()

    print(f"\n[brand_search] DONE: checked={stats['checked']}, "
          f"brand_search={stats['brand_search']}, powerlink={stats['powerlink']}, "
          f"shopping={stats['shopping']}, errors={stats['errors']}", flush=True)
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(check_brand_search(limit=args.limit))
