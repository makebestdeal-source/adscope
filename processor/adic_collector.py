"""ADIC(광고정보센터) 100대 광고주 광고비 수집기.

adic.or.kr에서 닐슨코리아 기반 광고주별 월간 광고비 데이터를 수집하여
DB advertiser 테이블과 매칭, 역추산 보정 기준선으로 활용.

수집 대상: 100대 광고주 4대매체+디지털 월별 광고비 (무료 공개)
스케줄: 월 1회 (1일 08:00)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

import httpx
from loguru import logger
from sqlalchemy import select, update, Column, Integer, Float, String, DateTime, Text
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from database.models import Advertiser, Base


# ── DB 테이블: adic_ad_expenses ──

class AdicAdExpense(Base):
    __tablename__ = "adic_ad_expenses"

    id = Column(Integer, primary_key=True)
    advertiser_name = Column(String(200), nullable=False)
    advertiser_id = Column(Integer, nullable=True)  # FK to advertisers (매칭 후)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=True)  # NULL이면 연간 합계
    medium = Column(String(50))  # tv, radio, newspaper, magazine, digital, total
    amount = Column(Float)  # 천원 단위
    rank = Column(Integer, nullable=True)
    industry = Column(String(100), nullable=True)
    source_url = Column(Text, nullable=True)
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── ADIC 페이지 URL ──

ADIC_BASE = "https://www.adic.or.kr"
# 100대 광고주 광고비 통계 페이지
ADIC_STATS_URL = f"{ADIC_BASE}/stat/main/getStats.do"


async def _ensure_adic_table():
    """adic_ad_expenses 테이블 생성 (없으면)."""
    import aiosqlite
    db_path = "adscope.db"
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS adic_ad_expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertiser_name TEXT NOT NULL,
                advertiser_id INTEGER,
                year INTEGER NOT NULL,
                month INTEGER,
                medium TEXT,
                amount REAL,
                rank INTEGER,
                industry TEXT,
                source_url TEXT,
                collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS ix_adic_advertiser_year
            ON adic_ad_expenses(advertiser_name, year, month)
        """)
        await db.commit()


def _parse_amount(val) -> float | None:
    """금액 값 파싱 (천원 단위, 쉼표 포함 문자열 처리)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fuzzy_match(name1: str, name2: str) -> float:
    """두 광고주명의 유사도 (0~1)."""
    n1 = re.sub(r'\s+', '', name1.lower().strip())
    n2 = re.sub(r'\s+', '', name2.lower().strip())
    if n1 == n2:
        return 1.0
    return SequenceMatcher(None, n1, n2).ratio()


async def _match_advertisers(
    session: AsyncSession,
    adic_names: list[str],
) -> dict[str, int]:
    """ADIC 광고주명 -> DB advertiser_id 매칭."""
    result = await session.execute(
        select(Advertiser.id, Advertiser.name, Advertiser.aliases)
    )
    db_advertisers = result.fetchall()

    mapping: dict[str, int] = {}
    for adic_name in adic_names:
        best_score = 0.0
        best_id = None
        for adv_id, adv_name, aliases in db_advertisers:
            # 직접 매칭
            score = _fuzzy_match(adic_name, adv_name)
            if score > best_score:
                best_score = score
                best_id = adv_id
            # aliases 매칭
            if aliases and isinstance(aliases, list):
                for alias in aliases:
                    s = _fuzzy_match(adic_name, alias)
                    if s > best_score:
                        best_score = s
                        best_id = adv_id
        if best_score >= 0.7 and best_id is not None:
            mapping[adic_name] = best_id
    return mapping


async def collect_adic_top100(year: int | None = None) -> dict:
    """ADIC 100대 광고주 광고비 수집.

    Returns:
        {"collected": N, "matched": M, "year": YYYY}
    """
    await _ensure_adic_table()

    target_year = year or datetime.now().year - 1  # 전년도 데이터

    logger.info("[adic] Collecting top 100 advertiser ad expenses for {}", target_year)

    collected_data: list[dict] = []

    # ── 1차: JSON API 직접 호출 ──
    # POST /stat/periodicalStat/list.json
    # params: className=AdvertiserAdOutlay, syear=YYYY, smonth=MM
    json_api_url = f"{ADIC_BASE}/stat/periodicalStat/list.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{ADIC_STATS_URL}?className=AdvertiserAdOutlay",
        "Origin": ADIC_BASE,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # 먼저 페이지 방문해서 세션 쿠키 획득
            await client.get(
                ADIC_STATS_URL,
                params={"className": "AdvertiserAdOutlay"},
                headers={"User-Agent": headers["User-Agent"]},
            )

            # 월별 데이터 수집 (12개월 또는 연간)
            months_to_try = list(range(12, 0, -1)) + [0]  # 12월부터, 0=연간
            for month in months_to_try:
                form_data = {
                    "className": "AdvertiserAdOutlay",
                    "syear": str(target_year),
                }
                if month > 0:
                    form_data["smonth"] = str(month)

                resp = await client.post(json_api_url, data=form_data, headers=headers)

                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        result_list = data.get("resultList", [])
                        if result_list:
                            for i, item in enumerate(result_list, 1):
                                name = item.get("name", "").strip()
                                if not name:
                                    continue
                                total = _parse_amount(item.get("total"))
                                tv = _parse_amount(item.get("tv"))
                                radio = _parse_amount(item.get("radio"))
                                newspaper = _parse_amount(item.get("newspaper"))
                                magazine = _parse_amount(item.get("magazine"))

                                collected_data.append({
                                    "advertiser_name": name,
                                    "year": target_year,
                                    "month": month if month > 0 else None,
                                    "medium": "total",
                                    "amount": total,
                                    "rank": i,
                                    "industry": item.get("industry", ""),
                                    "source_url": json_api_url,
                                })
                                # 매체별 개별 저장
                                for med_name, med_val in [
                                    ("tv", tv), ("radio", radio),
                                    ("newspaper", newspaper), ("magazine", magazine),
                                ]:
                                    if med_val and med_val > 0:
                                        collected_data.append({
                                            "advertiser_name": name,
                                            "year": target_year,
                                            "month": month if month > 0 else None,
                                            "medium": med_name,
                                            "amount": med_val,
                                            "rank": i,
                                            "industry": item.get("industry", ""),
                                            "source_url": json_api_url,
                                        })
                            logger.info(
                                "[adic] year={} month={}: {} advertisers",
                                target_year, month or "annual", len(result_list),
                            )
                            # 데이터 있으면 한 달만으로 충분 (최신 월)
                            if month > 0 and result_list:
                                break
                    except Exception as e:
                        logger.debug("[adic] JSON parse failed for month {}: {}", month, e)
                else:
                    logger.debug("[adic] API returned {} for month {}", resp.status_code, month)

                import asyncio
                await asyncio.sleep(1)  # rate limit

    except Exception as e:
        logger.warning("[adic] JSON API failed: {}", str(e)[:80])

    # ── 2차: Playwright 폴백 ──
    if not collected_data:
        logger.info("[adic] JSON API returned no data, trying Playwright")
        collected_data = await _collect_via_playwright(target_year)

    if not collected_data:
        logger.warning("[adic] No data collected")
        return {"collected": 0, "matched": 0, "year": target_year}

    # DB 저장 + 광고주 매칭
    import aiosqlite
    matched_count = 0

    async with async_session() as session:
        adic_names = list({d["advertiser_name"] for d in collected_data})
        name_to_id = await _match_advertisers(session, adic_names)
        matched_count = len(name_to_id)

    async with aiosqlite.connect("adscope.db") as db:
        for d in collected_data:
            adv_id = name_to_id.get(d["advertiser_name"])
            await db.execute("""
                INSERT INTO adic_ad_expenses
                (advertiser_name, advertiser_id, year, month, medium, amount, rank, industry, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                d["advertiser_name"],
                adv_id,
                d.get("year", target_year),
                d.get("month"),
                d.get("medium", "total"),
                d.get("amount"),
                d.get("rank"),
                d.get("industry"),
                d.get("source_url"),
            ))
        await db.commit()

    logger.info(
        "[adic] Collected {} records, matched {} advertisers for {}",
        len(collected_data), matched_count, target_year,
    )
    return {
        "collected": len(collected_data),
        "matched": matched_count,
        "year": target_year,
    }


def _parse_adic_html(html: str, year: int) -> list[dict]:
    """ADIC HTML 테이블에서 광고비 데이터 추출."""
    data: list[dict] = []

    # 테이블 행 파싱 (정규식 기반)
    # ADIC 테이블: 순위, 광고주, 업종, 금액(천원)
    table_pattern = re.compile(
        r'<tr[^>]*>\s*'
        r'<td[^>]*>\s*(\d+)\s*</td>\s*'          # 순위
        r'<td[^>]*>\s*([^<]+?)\s*</td>\s*'        # 광고주명
        r'<td[^>]*>\s*([^<]*?)\s*</td>\s*'        # 업종
        r'<td[^>]*>\s*([\d,]+)\s*</td>',          # 금액
        re.DOTALL,
    )

    for m in table_pattern.finditer(html):
        rank_str, name, industry, amount_str = m.groups()
        try:
            amount = float(amount_str.replace(",", ""))
        except ValueError:
            continue
        data.append({
            "advertiser_name": name.strip(),
            "year": year,
            "month": None,
            "medium": "total",
            "amount": amount,
            "rank": int(rank_str),
            "industry": industry.strip() or None,
            "source_url": f"{ADIC_STATS_URL}?className=AdvertiserAdOutlay",
        })

    return data


async def _collect_via_playwright(year: int) -> list[dict]:
    """Playwright headless로 ADIC 데이터 수집."""
    data: list[dict] = []

    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            # 네트워크 캡처
            api_responses: list[dict] = []

            async def on_response(response):
                url = response.url
                try:
                    if response.status == 200 and "getStats" in url:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            body = await response.json()
                            api_responses.append(body)
                        elif "html" in ct:
                            body = await response.text()
                            parsed = _parse_adic_html(body, year)
                            if parsed:
                                data.extend(parsed)
                except Exception:
                    pass

            page.on("response", on_response)

            url = f"{ADIC_STATS_URL}?className=AdvertiserAdOutlay"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)

            # 연도 선택이 필요하면 시도
            try:
                year_select = page.locator(f'select:has(option[value="{year}"])')
                if await year_select.count() > 0:
                    await year_select.select_option(str(year))
                    await page.wait_for_timeout(2000)
            except Exception:
                pass

            # 테이블이 없으면 HTML 직접 파싱
            if not data:
                html = await page.content()
                data = _parse_adic_html(html, year)

            # JSON API 응답이 있으면 처리
            for resp_data in api_responses:
                if isinstance(resp_data, dict) and "list" in resp_data:
                    for item in resp_data["list"]:
                        data.append({
                            "advertiser_name": item.get("advName", ""),
                            "year": year,
                            "month": item.get("month"),
                            "medium": item.get("medium", "total"),
                            "amount": item.get("amount", 0),
                            "rank": item.get("rank"),
                            "industry": item.get("industry"),
                            "source_url": url,
                        })

            await browser.close()

    except Exception as e:
        logger.error("[adic] Playwright collection failed: {}", str(e)[:100])

    return data


async def update_advertiser_benchmarks():
    """ADIC 데이터를 기반으로 광고주 벤치마크 업데이트.

    adic_ad_expenses에서 최근 연도 데이터를 조회하여
    매칭된 광고주의 annual_revenue 등을 보정.
    """
    import aiosqlite

    async with aiosqlite.connect("adscope.db") as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT advertiser_id, SUM(amount) as total_amount, year
            FROM adic_ad_expenses
            WHERE advertiser_id IS NOT NULL AND medium = 'total'
            GROUP BY advertiser_id, year
            ORDER BY year DESC
        """)
        rows = await cursor.fetchall()

    if not rows:
        return {"updated": 0}

    updated = 0
    async with async_session() as session:
        for row in rows:
            adv_id = row["advertiser_id"]
            total_kwon = row["total_amount"]  # 천원 단위
            total_won = total_kwon * 1000
            await session.execute(
                update(Advertiser)
                .where(Advertiser.id == adv_id)
                .values(
                    annual_revenue=total_won,
                    data_source="adic",
                    profile_updated_at=datetime.now(timezone.utc),
                )
            )
            updated += 1
        await session.commit()

    logger.info("[adic] Updated {} advertiser benchmarks", updated)
    return {"updated": updated}
