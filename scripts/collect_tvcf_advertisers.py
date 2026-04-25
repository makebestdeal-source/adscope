"""TVCF 광고주 풀 수집 스크립트.

https://tvcf.co.kr/portfolio/advertiser?country_code_value=410 에서
한국 광고주명 + 공식 웹사이트를 수집하여 known_advertisers 테이블에 저장.

수집 전략:
- TVCF router API 직접 호출 (Playwright 컨텍스트 이용, 403 우회)
- web 필드가 있으면 공식사이트로 사용
- web 없으면 Naver 검색으로 공식사이트 탐색 (--search 플래그 필요)
- TVCF 내부 링크(tvcf.co.kr)는 광고주 URL로 절대 사용하지 않음

Usage:
    python scripts/collect_tvcf_advertisers.py
    python scripts/collect_tvcf_advertisers.py --pages 200 --search
    python scripts/collect_tvcf_advertisers.py --min-docs 10
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import sys
import time
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from loguru import logger
from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

# TVCF 내부 도메인 — 광고주 URL로 절대 사용 금지
_TVCF_DOMAINS = {"tvcf.co.kr", "www.tvcf.co.kr", "router.tvcf.co.kr"}

TVCF_API = (
    "https://router.tvcf.co.kr/api/main/v1/portfolio/portfolio_search"
    "?country_code_value=410&iscorp=2&sort_by=doc_count&page={page}"
)

# URL 정규화
def _normalize_web(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    # TVCF 내부 링크 제거
    try:
        from urllib.parse import urlparse
        if "://" not in url:
            url = f"https://{url}"
        domain = urlparse(url).netloc.lstrip("www.").lower()
        if domain in _TVCF_DOMAINS or "tvcf" in domain:
            return None
    except Exception:
        return None
    # 프로토콜 정규화 (http → https, 프로토콜 없는 경우 https 추가)
    if "://" in url:
        url = re.sub(r'^https?://', 'https://', url, flags=re.IGNORECASE)
    else:
        url = f"https://{url}"
    # 도메인 소문자 정규화 (경로는 그대로 유지)
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        url = urlunparse(p._replace(netloc=p.netloc.lower()))
    except Exception:
        pass
    return url


async def fetch_page_via_browser(page, page_num: int) -> dict | None:
    """Playwright 컨텍스트에서 TVCF API 호출 (CORS/403 우회)."""
    url = TVCF_API.format(page=page_num)
    try:
        result = await page.evaluate(f"""
            fetch('{url}', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Accept-Language': 'ko-KR,ko;q=0.9'
                }},
                body: JSON.stringify({{staff_role_code_value: [2]}})
            }}).then(r => r.json()).catch(e => null)
        """)
        return result
    except Exception as e:
        logger.warning(f"Page {page_num} fetch error: {e}")
        return None


async def collect_tvcf(
    max_pages: int = 150,
    min_docs: int = 3,
    enable_search: bool = False,
) -> list[dict]:
    """TVCF API에서 한국 광고주 목록 수집."""
    advertisers = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # TVCF 첫 페이지 로드 (쿠키/세션 확보)
        logger.info("TVCF 페이지 초기화...")
        await page.goto(
            "https://tvcf.co.kr/portfolio/advertiser?country_code_value=410&sort_by=doc_count&published_date_min=All",
            wait_until="networkidle",
            timeout=30000,
        )

        # 첫 페이지로 total 확인
        first = await fetch_page_via_browser(page, 1)
        if not first or first.get("status") != 200:
            logger.error("TVCF API 응답 없음")
            await browser.close()
            return advertisers

        total_docs = first["data"]["total_docs"]
        items_per_page = first["data"]["page_info"]["items_per_page"]
        total_pages = min(max_pages, (total_docs // items_per_page) + 1)
        logger.info(f"총 docs: {total_docs:,} | 페이지당: {items_per_page} | 수집 예정: {total_pages}페이지")

        # 첫 페이지 결과 처리
        def extract_staffs(response: dict) -> list[dict]:
            try:
                return response["data"]["results"]["staffs"]
            except (KeyError, TypeError):
                return []

        def parse_staff(s: dict) -> dict | None:
            name = (s.get("user_name") or "").strip()
            if not name:
                return None
            doc_count = s.get("doc_count", 0)
            web = _normalize_web(s.get("web", ""))
            name_en = (s.get("user_name_en") or "").strip()
            return {
                "name": name,
                "name_en": name_en,
                "website": web,
                "tvcf_doc_count": doc_count,
            }

        for s in extract_staffs(first):
            parsed = parse_staff(s)
            if parsed and parsed["tvcf_doc_count"] >= min_docs:
                advertisers.append(parsed)

        # 나머지 페이지 수집
        for pg in range(2, total_pages + 1):
            resp = await fetch_page_via_browser(page, pg)
            if not resp:
                break
            staffs = extract_staffs(resp)
            if not staffs:
                break

            page_max_docs = max((s.get("doc_count", 0) for s in staffs), default=0)
            if page_max_docs < min_docs:
                # 페이지 최대값도 min_docs 미만이면 중단 (이후 페이지는 더 낮음)
                logger.info(f"페이지 {pg}: 최대 doc_count {page_max_docs} < {min_docs}, 수집 중단")
                break

            for s in staffs:
                parsed = parse_staff(s)
                if parsed and parsed["tvcf_doc_count"] >= min_docs:
                    advertisers.append(parsed)

            if pg % 10 == 0:
                logger.info(f"  {pg}/{total_pages}페이지 완료, 현재 {len(advertisers)}개")

            await asyncio.sleep(0.1)  # 서버 부하 방지

        await browser.close()

    logger.info(f"TVCF 수집 완료: {len(advertisers)}개 광고주")

    # Naver 검색으로 web 보완 (--search 시)
    if enable_search:
        advertisers = await enrich_with_naver(advertisers)

    return advertisers


async def enrich_with_naver(advertisers: list[dict]) -> list[dict]:
    """web이 없는 광고주에 대해 Naver 검색으로 공식사이트 탐색."""
    from processor.url_resolver import search_naver, _is_excluded_domain, MIN_SEARCH_LEN

    no_web = [a for a in advertisers if not a.get("website")]
    logger.info(f"Naver 검색 대상: {len(no_web)}개 (web 없는 광고주)")

    found = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for i, adv in enumerate(no_web):
            name = adv["name"]
            if len(name) < MIN_SEARCH_LEN or len(name) > 40:
                continue
            url = await search_naver(client, name)
            if url:
                adv["website"] = url
                found += 1
            if (i + 1) % 50 == 0:
                logger.info(f"  Naver 검색 {i+1}/{len(no_web)} 완료, 발견 {found}개")
            await asyncio.sleep(0.3)

    logger.info(f"Naver 검색 완료: {found}/{len(no_web)}개 사이트 발견")
    return advertisers


async def save_to_db(advertisers: list[dict], dry_run: bool = False) -> int:
    """known_advertisers 테이블에 upsert."""
    from database import init_db, async_session
    from database.models import KnownAdvertiser

    await init_db()

    saved = 0
    async with async_session() as session:
        for adv in advertisers:
            name = adv["name"]
            if not name:
                continue

            # 이미 존재하면 website/doc_count 업데이트
            stmt = sqlite_insert(KnownAdvertiser).values(
                name=name,
                name_en=adv.get("name_en") or None,
                website=adv.get("website") or None,
                source="tvcf",
                tvcf_doc_count=adv.get("tvcf_doc_count", 0),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "name_en": stmt.excluded.name_en,
                    "website": stmt.excluded.website,
                    "tvcf_doc_count": stmt.excluded.tvcf_doc_count,
                },
            )
            if not dry_run:
                await session.execute(stmt)
            saved += 1

        if not dry_run:
            await session.commit()

    return saved


async def main():
    parser = argparse.ArgumentParser(description="TVCF 광고주 풀 수집")
    parser.add_argument("--pages", type=int, default=150, help="최대 수집 페이지 수 (기본 150)")
    parser.add_argument("--min-docs", type=int, default=3, help="최소 광고 편수 (기본 3)")
    parser.add_argument("--search", action="store_true", help="Naver 검색으로 web 보완")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 시뮬레이션")
    args = parser.parse_args()

    logger.info(f"수집 시작 | pages={args.pages}, min_docs={args.min_docs}, search={args.search}")

    advertisers = await collect_tvcf(
        max_pages=args.pages,
        min_docs=args.min_docs,
        enable_search=args.search,
    )

    if not advertisers:
        logger.warning("수집된 광고주 없음")
        return

    # 결과 미리보기
    has_web = sum(1 for a in advertisers if a.get("website"))
    logger.info(f"수집 결과: {len(advertisers)}개 | 웹사이트 있음: {has_web}개")
    logger.info("상위 20개 샘플:")
    for a in advertisers[:20]:
        logger.info(f"  [{a['tvcf_doc_count']}편] {a['name']} | {a.get('website','(없음)')}")

    saved = await save_to_db(advertisers, dry_run=args.dry_run)
    if args.dry_run:
        logger.info(f"DRY RUN: {saved}개 저장 예정 (실제 저장 안 함)")
    else:
        logger.info(f"DB 저장 완료: {saved}개")


if __name__ == "__main__":
    asyncio.run(main())
