"""DART 광고선전비 수집 및 채널별 배분 추정

DART OpenAPI에서 상장사 법인 목록을 수집하고,
각 법인의 광고선전비를 수집하여 채널별로 배분한다.

사용법:
    python scripts/collect_dart_financials.py            # 전체 상장사 연간 수집
    python scripts/collect_dart_financials.py --year 2024 --quarter 1   # 특정 분기
    python scripts/collect_dart_financials.py --match-only   # 광고주 매칭만 재실행
    python scripts/collect_dart_financials.py --allocate-only # 배분 계산만 재실행

환경변수:
    DART_API_KEY: DART OpenAPI 인증키 (.env 파일에 설정)
    DART OpenAPI 신청: https://opendart.fss.or.kr/
"""
import argparse
import asyncio
import io
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

import aiohttp
from loguru import logger
from sqlalchemy import text

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

from database import async_session

# ── 상수 ──────────────────────────────────────────────────────────────────────

DART_API_KEY = os.getenv("DART_API_KEY", "")
DART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DART_FINANCIAL_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"

# reprt_code 매핑
REPRT_CODE = {
    "annual": "11011",   # 사업보고서 (연간)
    "half":   "11012",   # 반기보고서
    "q1":     "11013",   # 1분기보고서
    "q3":     "11014",   # 3분기보고서
}

# 분기 -> reprt_code 매핑 (1Q=1분기, 2Q=반기, 3Q=3분기, 4Q=사업보고서)
QUARTER_TO_REPRT = {
    1: "11013",
    2: "11012",
    3: "11014",
    4: "11011",
}

# 광고 관련 계정과목명 (포함 검사)
AD_ACCOUNT_NAMES = [
    "광고선전비", "광고비", "판매촉진비", "광고홍보비", "홍보비",
    "마케팅비", "마케팅비용",
]

# KAA 2024 기반 채널 배분 비율 (디지털 채널 합계 = 0.85)
KAA_2024_RATIOS = {
    "naver_search":      0.22,
    "naver_da":          0.08,
    "google_search_ads": 0.07,
    "google_gdn":        0.05,
    "youtube_ads":       0.18,
    "meta":              0.15,
    "kakao_da":          0.06,
    "tiktok_ads":        0.04,
}
_DIGITAL_TOTAL = sum(KAA_2024_RATIOS.values())  # 0.85

# 정규화된 비율 (디지털 채널 합계 = 1.0)
NORMALIZED_RATIOS = {ch: r / _DIGITAL_TOTAL for ch, r in KAA_2024_RATIOS.items()}

# 월별 계절 보정 계수 (합계 = 12.0 기준)
SEASONALITY = {
    1:  0.75, 2:  0.80, 3:  0.90, 4:  0.95,
    5:  1.05, 6:  1.00, 7:  0.85, 8:  0.90,
    9:  1.05, 10: 1.10, 11: 1.20, 12: 1.15,
}
_SEASON_SUM = sum(SEASONALITY.values())  # 12.0

REQUEST_INTERVAL = 0.5   # DART API 호출 간격 (초)
MAX_RETRY = 3
REQUEST_TIMEOUT = 30


# ── DB 스키마 보장 ─────────────────────────────────────────────────────────────

async def ensure_dart_tables():
    """dart_financials, spend_allocations 테이블 및 advertiser 컬럼을 생성/보장."""
    async with async_session() as session:
        conn = await session.connection()

        # advertisers 테이블에 corp_code, dart_matched_at 컬럼 추가
        rows = await conn.exec_driver_sql("PRAGMA table_info(advertisers)")
        existing_adv = {row[1] for row in rows.fetchall()}
        for col, typ in [
            ("corp_code", "VARCHAR(20)"),
            ("dart_matched_at", "DATETIME"),
        ]:
            if col not in existing_adv:
                try:
                    await conn.exec_driver_sql(
                        f"ALTER TABLE advertisers ADD COLUMN {col} {typ}"
                    )
                    logger.info(f"advertisers 테이블에 {col} 컬럼 추가")
                except Exception:
                    pass

        # dart_financials 테이블 생성
        await conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS dart_financials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertiser_id INTEGER REFERENCES advertisers(id) ON DELETE SET NULL,
                corp_code VARCHAR(20) NOT NULL,
                corp_name VARCHAR(200),
                stock_code VARCHAR(20),
                fiscal_year INTEGER NOT NULL,
                fiscal_quarter INTEGER,
                report_type VARCHAR(20),
                ad_expense REAL,
                sales_promo_expense REAL,
                total_selling_expense REAL,
                revenue REAL,
                report_filed_at DATETIME,
                dart_api_url TEXT,
                collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(corp_code, fiscal_year, fiscal_quarter)
            )
        """)

        # spend_allocations 테이블 생성
        await conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS spend_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                advertiser_id INTEGER NOT NULL REFERENCES advertisers(id) ON DELETE CASCADE,
                dart_financial_id INTEGER REFERENCES dart_financials(id) ON DELETE SET NULL,
                period_year INTEGER NOT NULL,
                period_month INTEGER NOT NULL,
                channel VARCHAR(50) NOT NULL,
                total_dart_expense REAL,
                allocation_ratio REAL,
                seasonality_factor REAL,
                allocated_spend REAL,
                allocation_basis VARCHAR(50),
                confidence REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(advertiser_id, period_year, period_month, channel)
            )
        """)

        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_dart_financials_corp_code "
            "ON dart_financials(corp_code)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_dart_financials_advertiser_id "
            "ON dart_financials(advertiser_id)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_spend_allocations_advertiser_year "
            "ON spend_allocations(advertiser_id, period_year, period_month)"
        )

        await session.commit()
        logger.info("dart_financials / spend_allocations 테이블 보장 완료")


# ── DART API 유틸 ──────────────────────────────────────────────────────────────

async def _request_with_retry(session: aiohttp.ClientSession, url: str, params: dict):
    """GET 요청, 실패 시 최대 MAX_RETRY회 재시도."""
    last_exc = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
                if resp.status == 200:
                    return resp
                logger.warning(f"HTTP {resp.status} (시도 {attempt}/{MAX_RETRY}): {url}")
        except Exception as exc:
            last_exc = exc
            logger.warning(f"요청 오류 (시도 {attempt}/{MAX_RETRY}): {exc}")
        if attempt < MAX_RETRY:
            await asyncio.sleep(REQUEST_INTERVAL * 2)
    raise RuntimeError(f"DART API 요청 실패 ({MAX_RETRY}회): {last_exc}")


async def fetch_corp_list() -> Dict[str, dict]:
    """DART corp_code.zip 다운로드 및 XML 파싱.

    Returns:
        dict: {corp_code: {corp_name, stock_code, corp_code, modify_date}}
    """
    if not DART_API_KEY:
        raise ValueError("DART_API_KEY 환경변수가 설정되지 않았습니다.")

    logger.info("DART 법인 목록 다운로드 중...")
    params = {"crtfc_key": DART_API_KEY}

    async with aiohttp.ClientSession() as http_session:
        resp = await _request_with_retry(http_session, DART_CORP_CODE_URL, params)
        content_type = resp.headers.get("content-type", "")

        # zip 파일로 응답
        raw = await resp.read()

    # zip 압축 해제 및 XML 파싱
    corp_map: Dict[str, dict] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            xml_name = next((n for n in zf.namelist() if n.endswith(".xml")), None)
            if not xml_name:
                raise ValueError("corp_code.zip 내부에 XML 파일 없음")
            with zf.open(xml_name) as xf:
                tree = ElementTree.parse(xf)
                root = tree.getroot()
                for item in root.findall("list"):
                    corp_code = (item.findtext("corp_code") or "").strip()
                    corp_name = (item.findtext("corp_name") or "").strip()
                    stock_code = (item.findtext("stock_code") or "").strip()
                    modify_date = (item.findtext("modify_date") or "").strip()
                    if corp_code:
                        corp_map[corp_code] = {
                            "corp_code": corp_code,
                            "corp_name": corp_name,
                            "stock_code": stock_code,
                            "modify_date": modify_date,
                        }
    except zipfile.BadZipFile:
        # ZIP이 아닌 경우 직접 XML로 시도
        try:
            root = ElementTree.fromstring(raw)
            for item in root.findall("list"):
                corp_code = (item.findtext("corp_code") or "").strip()
                corp_name = (item.findtext("corp_name") or "").strip()
                stock_code = (item.findtext("stock_code") or "").strip()
                modify_date = (item.findtext("modify_date") or "").strip()
                if corp_code:
                    corp_map[corp_code] = {
                        "corp_code": corp_code,
                        "corp_name": corp_name,
                        "stock_code": stock_code,
                        "modify_date": modify_date,
                    }
        except Exception as e:
            raise ValueError(f"DART 법인 목록 파싱 실패: {e}")

    logger.info(f"DART 법인 목록 로드 완료: {len(corp_map):,}개 법인")
    return corp_map


def _normalize_corp_name(name: str) -> str:
    """법인명 정규화: 주식회사/(주)/㈜ 등 제거, 공백 정리."""
    name = name.strip()
    # 앞뒤 괄호형 제거
    name = re.sub(r"^\(주\)\s*", "", name)
    name = re.sub(r"\s*\(주\)$", "", name)
    name = re.sub(r"^㈜\s*", "", name)
    name = re.sub(r"\s*㈜$", "", name)
    # "주식회사" 앞뒤 제거
    name = re.sub(r"^주식회사\s*", "", name)
    name = re.sub(r"\s*주식회사$", "", name)
    # 유한회사, 합자회사 등 제거
    name = re.sub(r"\s*(유한회사|합자회사|합명회사|유한책임회사)$", "", name)
    # 공백 정리
    name = re.sub(r"\s+", " ", name).strip()
    return name


async def match_advertisers_to_dart(corp_map: Dict[str, dict]) -> int:
    """advertisers 테이블 법인명과 DART 법인명 퍼지 매칭.

    매칭 성공 시 advertiser.corp_code, advertiser.dart_matched_at 업데이트.

    Returns:
        int: 매칭된 광고주 수
    """
    logger.info("광고주-DART 법인 매칭 시작...")

    # DART 법인명 정규화 인덱스 구축
    dart_normalized: Dict[str, str] = {}  # normalized_name -> corp_code
    for corp_code, info in corp_map.items():
        norm = _normalize_corp_name(info["corp_name"])
        if norm:
            dart_normalized[norm] = corp_code

    matched_count = 0
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async with async_session() as session:
        # advertiser 목록 조회 (corp_name 필드 사용, 없으면 name 사용)
        result = await session.execute(
            text("SELECT id, name FROM advertisers WHERE corp_code IS NULL OR corp_code = ''")
        )
        advertisers = result.fetchall()
        logger.info(f"매칭 대상 광고주: {len(advertisers):,}개")

        for adv_id, adv_name in advertisers:
            if not adv_name:
                continue
            norm_adv = _normalize_corp_name(adv_name)
            if not norm_adv:
                continue

            # 완전 일치 먼저 시도
            corp_code = dart_normalized.get(norm_adv)

            # 실패 시 앞뒤 부분 일치 시도 (법인명이 더 긴 경우 포함)
            if not corp_code:
                for dart_norm, dc in dart_normalized.items():
                    if norm_adv in dart_norm or dart_norm in norm_adv:
                        # 짧은 쪽이 5글자 이상이어야 매칭 인정
                        if len(min(norm_adv, dart_norm, key=len)) >= 5:
                            corp_code = dc
                            break

            if corp_code:
                try:
                    await session.execute(
                        text(
                            "UPDATE advertisers SET corp_code = :cc, dart_matched_at = :dt "
                            "WHERE id = :id"
                        ),
                        {"cc": corp_code, "dt": now_utc, "id": adv_id},
                    )
                    matched_count += 1
                except Exception as exc:
                    logger.warning(f"광고주 {adv_id} 매칭 업데이트 실패: {exc}")

        await session.commit()

    logger.info(f"광고주-DART 매칭 완료: {matched_count:,}개 매칭")
    return matched_count


# ── DART 재무제표 수집 ─────────────────────────────────────────────────────────

def _parse_ad_expense(items: list) -> dict:
    """재무제표 항목 리스트에서 광고 관련 비용을 파싱.

    Returns:
        {
            "ad_expense": float or None,
            "sales_promo_expense": float or None,
            "total_selling_expense": float or None,
            "revenue": float or None,
        }
    """
    result = {
        "ad_expense": None,
        "sales_promo_expense": None,
        "total_selling_expense": None,
        "revenue": None,
    }

    def _to_float(val: str) -> Optional[float]:
        if not val:
            return None
        cleaned = re.sub(r"[,\s]", "", str(val))
        try:
            return float(cleaned)
        except ValueError:
            return None

    for item in items:
        acnt_nm = (item.get("account_nm") or "").strip()
        sj_div = (item.get("sj_div") or "").strip()
        # 당기 금액 우선
        amount_str = item.get("thstrm_amount") or item.get("thstrm_add_amount") or ""
        amount = _to_float(amount_str)

        # 매출액
        if acnt_nm in ("매출액", "수익(매출액)", "영업수익", "매출"):
            if result["revenue"] is None:
                result["revenue"] = amount

        # 판관비 합계
        if acnt_nm in ("판매비와관리비", "판매비와관리비합계", "영업비용"):
            if result["total_selling_expense"] is None:
                result["total_selling_expense"] = amount

        # 광고선전비
        if "광고선전비" in acnt_nm or "광고비" in acnt_nm:
            if result["ad_expense"] is None:
                result["ad_expense"] = amount

        # 판매촉진비 (광고선전비와 별도 항목인 경우)
        if "판매촉진비" in acnt_nm and result["ad_expense"] is None:
            result["sales_promo_expense"] = amount
        elif "판매촉진비" in acnt_nm:
            result["sales_promo_expense"] = amount

    return result


async def fetch_dart_financial(
    http_session: aiohttp.ClientSession,
    corp_code: str,
    year: int,
    reprt_code: str,
) -> Optional[dict]:
    """DART API 단일회사 전체 재무제표 조회.

    Returns:
        파싱된 재무 데이터 dict or None (데이터 없음)
    """
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": str(year),
        "reprt_code": reprt_code,
        "fs_div": "OFS",  # 개별재무제표 (연결: CFS)
    }

    try:
        resp = await _request_with_retry(http_session, DART_FINANCIAL_URL, params)
        data = await resp.json(content_type=None)
    except Exception as exc:
        logger.warning(f"DART 재무제표 조회 실패 ({corp_code}, {year}): {exc}")
        return None

    status = data.get("status", "")
    if status == "013":  # 데이터 없음
        return None
    if status not in ("000", ""):
        logger.debug(f"DART API 상태 {status} ({corp_code}, {year}): {data.get('message','')}")
        return None

    items = data.get("list", [])
    if not items:
        return None

    parsed = _parse_ad_expense(items)
    return {
        **parsed,
        "corp_code": corp_code,
        "year": year,
        "reprt_code": reprt_code,
        "dart_api_url": f"{DART_FINANCIAL_URL}?corp_code={corp_code}&bsns_year={year}&reprt_code={reprt_code}",
    }


# ── DB 저장 ────────────────────────────────────────────────────────────────────

async def save_dart_financial(
    corp_code: str,
    corp_name: str,
    stock_code: str,
    fiscal_year: int,
    fiscal_quarter: Optional[int],
    report_type: str,
    financial_data: dict,
    advertiser_id: Optional[int] = None,
) -> Optional[int]:
    """dart_financials UPSERT (corp_code + fiscal_year + fiscal_quarter 기준).

    Returns:
        저장된 레코드 id or None
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async with async_session() as session:
        # 기존 레코드 확인
        existing = await session.execute(
            text(
                "SELECT id FROM dart_financials "
                "WHERE corp_code = :cc AND fiscal_year = :fy AND "
                "(fiscal_quarter IS :fq OR fiscal_quarter = :fq)"
            ),
            {"cc": corp_code, "fy": fiscal_year, "fq": fiscal_quarter},
        )
        row = existing.fetchone()

        params = {
            "advertiser_id": advertiser_id,
            "corp_code": corp_code,
            "corp_name": corp_name,
            "stock_code": stock_code or None,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "report_type": report_type,
            "ad_expense": financial_data.get("ad_expense"),
            "sales_promo_expense": financial_data.get("sales_promo_expense"),
            "total_selling_expense": financial_data.get("total_selling_expense"),
            "revenue": financial_data.get("revenue"),
            "dart_api_url": financial_data.get("dart_api_url"),
            "collected_at": now_utc,
        }

        if row:
            record_id = row[0]
            await session.execute(
                text("""
                    UPDATE dart_financials SET
                        advertiser_id = :advertiser_id,
                        corp_name = :corp_name,
                        stock_code = :stock_code,
                        report_type = :report_type,
                        ad_expense = :ad_expense,
                        sales_promo_expense = :sales_promo_expense,
                        total_selling_expense = :total_selling_expense,
                        revenue = :revenue,
                        dart_api_url = :dart_api_url,
                        collected_at = :collected_at
                    WHERE id = :id
                """),
                {**params, "id": record_id},
            )
        else:
            await session.execute(
                text("""
                    INSERT INTO dart_financials
                        (advertiser_id, corp_code, corp_name, stock_code,
                         fiscal_year, fiscal_quarter, report_type,
                         ad_expense, sales_promo_expense, total_selling_expense,
                         revenue, dart_api_url, collected_at)
                    VALUES
                        (:advertiser_id, :corp_code, :corp_name, :stock_code,
                         :fiscal_year, :fiscal_quarter, :report_type,
                         :ad_expense, :sales_promo_expense, :total_selling_expense,
                         :revenue, :dart_api_url, :collected_at)
                """),
                params,
            )
            result = await session.execute(text("SELECT last_insert_rowid()"))
            record_id = result.fetchone()[0]

        await session.commit()
        return record_id


# ── 채널별 배분 계산 ───────────────────────────────────────────────────────────

def _get_months_for_period(fiscal_year: int, fiscal_quarter: Optional[int]) -> List[Tuple[int, int]]:
    """해당 기간의 (year, month) 리스트 반환."""
    if fiscal_quarter is None:
        # 연간 -> 1~12월
        return [(fiscal_year, m) for m in range(1, 13)]
    elif fiscal_quarter == 1:
        return [(fiscal_year, 1), (fiscal_year, 2), (fiscal_year, 3)]
    elif fiscal_quarter == 2:
        return [(fiscal_year, 4), (fiscal_year, 5), (fiscal_year, 6)]
    elif fiscal_quarter == 3:
        return [(fiscal_year, 7), (fiscal_year, 8), (fiscal_year, 9)]
    elif fiscal_quarter == 4:
        return [(fiscal_year, 10), (fiscal_year, 11), (fiscal_year, 12)]
    else:
        return [(fiscal_year, m) for m in range(1, 13)]


async def calculate_allocations(
    dart_financial_id: int,
    advertiser_id: int,
    fiscal_year: int,
    fiscal_quarter: Optional[int],
    ad_expense: Optional[float],
    sales_promo_expense: Optional[float],
) -> int:
    """dart_financial 데이터를 기반으로 spend_allocations 생성.

    - 분기 데이터: 해당 분기 3개월에 배분 (계절 보정 적용)
    - 연간 데이터: 12개월에 배분 (계절 보정 적용)

    Returns:
        저장된 레코드 수
    """
    # 광고선전비 결정: ad_expense 우선, 없으면 sales_promo_expense 사용
    total_expense = ad_expense
    allocation_basis = "dart_ad_expense"
    if total_expense is None:
        total_expense = sales_promo_expense
        allocation_basis = "dart_sales_promo"
    if total_expense is None or total_expense <= 0:
        return 0

    months = _get_months_for_period(fiscal_year, fiscal_quarter)

    # 해당 기간 계절 계수 합
    season_weights = {(y, m): SEASONALITY[m] for y, m in months}
    total_season = sum(season_weights.values())

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    saved_count = 0

    async with async_session() as session:
        for (year, month), season_w in season_weights.items():
            # 월별 비중 = 계절 계수 / 기간 계절 합
            month_ratio = season_w / total_season

            for channel, norm_ratio in NORMALIZED_RATIOS.items():
                # 이 채널, 이 달에 배분할 금액
                allocated = total_expense * month_ratio * norm_ratio
                seasonality_factor = season_w / (total_season / len(months))  # 평균 대비

                try:
                    await session.execute(
                        text("""
                            INSERT INTO spend_allocations
                                (advertiser_id, dart_financial_id,
                                 period_year, period_month, channel,
                                 total_dart_expense, allocation_ratio,
                                 seasonality_factor, allocated_spend,
                                 allocation_basis, confidence, created_at)
                            VALUES
                                (:adv_id, :df_id,
                                 :yr, :mo, :ch,
                                 :total_exp, :alloc_ratio,
                                 :season_f, :alloc_spend,
                                 :basis, :conf, :created_at)
                            ON CONFLICT(advertiser_id, period_year, period_month, channel)
                            DO UPDATE SET
                                dart_financial_id = excluded.dart_financial_id,
                                total_dart_expense = excluded.total_dart_expense,
                                allocation_ratio = excluded.allocation_ratio,
                                seasonality_factor = excluded.seasonality_factor,
                                allocated_spend = excluded.allocated_spend,
                                allocation_basis = excluded.allocation_basis,
                                confidence = excluded.confidence,
                                created_at = excluded.created_at
                        """),
                        {
                            "adv_id": advertiser_id,
                            "df_id": dart_financial_id,
                            "yr": year,
                            "mo": month,
                            "ch": channel,
                            "total_exp": total_expense,
                            "alloc_ratio": norm_ratio,
                            "season_f": seasonality_factor,
                            "alloc_spend": allocated,
                            "basis": allocation_basis,
                            "conf": 0.6,  # KAA 업계 평균 기반 신뢰도
                            "created_at": now_utc,
                        },
                    )
                    saved_count += 1
                except Exception as exc:
                    logger.warning(f"spend_allocations 저장 실패 ({advertiser_id}, {year}-{month}, {channel}): {exc}")

        await session.commit()

    return saved_count


# ── 배분 재계산 ────────────────────────────────────────────────────────────────

async def run_allocate_only():
    """기존 dart_financials에서 spend_allocations만 재계산."""
    logger.info("spend_allocations 재계산 시작...")
    total_alloc = 0

    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT df.id, df.advertiser_id, df.fiscal_year, df.fiscal_quarter,
                       df.ad_expense, df.sales_promo_expense
                FROM dart_financials df
                WHERE df.advertiser_id IS NOT NULL
            """)
        )
        records = result.fetchall()

    logger.info(f"배분 대상 재무 레코드: {len(records):,}개")
    for rec in records:
        df_id, adv_id, fy, fq, ad_exp, sp_exp = rec
        count = await calculate_allocations(df_id, adv_id, fy, fq, ad_exp, sp_exp)
        total_alloc += count

    logger.info(f"spend_allocations 재계산 완료: {total_alloc:,}개 레코드 생성/갱신")


# ── 전체 수집 흐름 ─────────────────────────────────────────────────────────────

async def run_collection(year: int, quarter: Optional[int] = None):
    """전체 수집 흐름: DART 법인 목록 -> 광고주 매칭 -> 재무제표 수집 -> 배분 계산."""
    if not DART_API_KEY:
        print("=" * 60)
        print("[오류] DART_API_KEY 환경변수가 설정되지 않았습니다.")
        print("")
        print("설정 방법:")
        print("  1. https://opendart.fss.or.kr/ 에서 API 키 신청")
        print("  2. .env 파일에 DART_API_KEY=발급받은키 추가")
        print("=" * 60)
        return

    await ensure_dart_tables()

    # 1. DART 법인 목록 수집
    corp_map = await fetch_corp_list()

    # 상장사만 필터링 (stock_code가 있는 법인)
    listed_corps = {cc: info for cc, info in corp_map.items() if info.get("stock_code", "").strip()}
    logger.info(f"상장 법인 수: {len(listed_corps):,}개")

    # 2. 광고주 매칭
    await match_advertisers_to_dart(corp_map)

    # 매칭된 광고주의 corp_code 가져오기
    async with async_session() as session:
        result = await session.execute(
            text("SELECT id, corp_code, name FROM advertisers WHERE corp_code IS NOT NULL AND corp_code != ''")
        )
        matched_advertisers = {row[1]: (row[0], row[2]) for row in result.fetchall()}

    logger.info(f"매칭된 광고주: {len(matched_advertisers):,}개")

    # 수집할 reprt_code 결정
    if quarter is not None:
        reprt_code = QUARTER_TO_REPRT.get(quarter, "11011")
        period_label = f"{year}년 {quarter}분기"
        fiscal_quarter = quarter
    else:
        reprt_code = REPRT_CODE["annual"]
        period_label = f"{year}년 연간"
        fiscal_quarter = None

    logger.info(f"수집 기간: {period_label} (reprt_code={reprt_code})")

    # 매칭된 광고주 + 상장사 전체 대상 수집
    # 매칭 광고주는 advertiser_id 연결, 나머지 상장사는 corp_code만 저장
    targets: List[Tuple[str, dict, Optional[int]]] = []

    # 매칭 광고주 우선
    for corp_code, (adv_id, adv_name) in matched_advertisers.items():
        info = corp_map.get(corp_code, {"corp_name": adv_name, "stock_code": ""})
        targets.append((corp_code, info, adv_id))

    # 나머지 상장사 (매칭 안 된 법인)
    matched_corp_codes = set(matched_advertisers.keys())
    for corp_code, info in listed_corps.items():
        if corp_code not in matched_corp_codes:
            targets.append((corp_code, info, None))

    logger.info(f"수집 대상: {len(targets):,}개 법인 ({period_label})")

    collected = 0
    skipped = 0
    total_alloc = 0

    async with aiohttp.ClientSession() as http_session:
        for idx, (corp_code, corp_info, adv_id) in enumerate(targets):
            corp_name = corp_info.get("corp_name", "")
            stock_code = corp_info.get("stock_code", "")

            # 진행 상황 출력 (100건마다)
            if idx % 100 == 0:
                logger.info(f"진행: {idx:,}/{len(targets):,} | 수집: {collected:,} | 건너뜀: {skipped:,}")

            financial_data = await fetch_dart_financial(http_session, corp_code, year, reprt_code)
            await asyncio.sleep(REQUEST_INTERVAL)

            if financial_data is None:
                skipped += 1
                continue

            # 광고 관련 비용이 전혀 없으면 저장 안 함
            if (
                financial_data.get("ad_expense") is None
                and financial_data.get("sales_promo_expense") is None
            ):
                skipped += 1
                continue

            # 저장
            report_type = "annual" if fiscal_quarter is None else f"q{fiscal_quarter}"
            df_id = await save_dart_financial(
                corp_code=corp_code,
                corp_name=corp_name,
                stock_code=stock_code,
                fiscal_year=year,
                fiscal_quarter=fiscal_quarter,
                report_type=report_type,
                financial_data=financial_data,
                advertiser_id=adv_id,
            )
            collected += 1

            # 광고주가 연결된 경우에만 배분 계산
            if adv_id and df_id:
                alloc_count = await calculate_allocations(
                    dart_financial_id=df_id,
                    advertiser_id=adv_id,
                    fiscal_year=year,
                    fiscal_quarter=fiscal_quarter,
                    ad_expense=financial_data.get("ad_expense"),
                    sales_promo_expense=financial_data.get("sales_promo_expense"),
                )
                total_alloc += alloc_count

    logger.info(
        f"수집 완료 -- 기간: {period_label} | "
        f"수집: {collected:,}건 | 건너뜀: {skipped:,}건 | "
        f"배분 레코드: {total_alloc:,}건"
    )


# ── 매칭 전용 실행 ─────────────────────────────────────────────────────────────

async def run_match_only():
    """광고주-DART 법인 매칭만 재실행."""
    if not DART_API_KEY:
        print("[오류] DART_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    await ensure_dart_tables()
    corp_map = await fetch_corp_list()
    await match_advertisers_to_dart(corp_map)


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="DART 광고선전비 수집 및 채널별 배분 추정"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=datetime.now().year - 1,
        help="수집 연도 (기본값: 전년도)",
    )
    parser.add_argument(
        "--quarter",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="수집 분기 (미입력 시 연간 사업보고서)",
    )
    parser.add_argument(
        "--match-only",
        action="store_true",
        help="광고주-DART 법인 매칭만 재실행",
    )
    parser.add_argument(
        "--allocate-only",
        action="store_true",
        help="기존 dart_financials에서 spend_allocations만 재계산",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    if args.match_only:
        await run_match_only()
    elif args.allocate_only:
        await ensure_dart_tables()
        await run_allocate_only()
    else:
        await run_collection(year=args.year, quarter=args.quarter)


if __name__ == "__main__":
    asyncio.run(main())
