"""DART 전자공시 광고선전비 수집기.

DART(전자공시시스템)에서 주요 한국 기업의 사업보고서를 검색하고,
판매비와관리비 항목에서 광고선전비/판매촉진비/마케팅비를 추출하여
AdScope 광고주 DB에 저장한다.

사용법:
    from processor.dart_collector import collect_dart_expenses
    stats = await collect_dart_expenses()
"""

import asyncio
import re
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger
from sqlalchemy import select, text

from database import async_session
from database.models import Advertiser
from processor.advertiser_matcher import AdvertiserMatcher

# ── Constants ──

DART_SEARCH_URL = "https://dart.fss.or.kr/dsab001/search.ax"
DART_REPORT_URL = "https://dart.fss.or.kr/dsaf001/main.do"
DART_VIEWER_URL = "https://dart.fss.or.kr/report/viewer.do"

REQUEST_DELAY = 3.0  # seconds between requests to avoid IP blocking

# User-Agent to mimic a real browser
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}

# Expense keywords to search for in financial statements
EXPENSE_KEYWORDS = ["광고선전비", "판매촉진비", "마케팅비", "광고비", "판촉비"]

# Company name normalization regex
_CORP_STRIP_RE = re.compile(
    r"[\(\(]?\s*(?:주식회사|주|株|㈜|유한회사|유|사단법인|재단법인)\s*[\)\)]?",
)

# Korean large-number suffixes (hierarchical: 조 > 억 > 만)
# "천"/"백" are sub-units used as multipliers within each tier
# e.g., "3천만" = 3000 * 만 = 30,000,000
_KR_TIERS = [
    ("조", 1_000_000_000_000),
    ("억", 100_000_000),
    ("만", 10_000),
]
# Sub-multipliers within a tier: "3천" = 3000, "5백" = 500
_KR_SUB = [("천", 1000), ("백", 100)]

# Number with commas pattern
_COMMA_NUM_RE = re.compile(r"[-−]?\s*[\d,]+(?:\.\d+)?")

# Top Korean advertisers to scrape
TOP_COMPANIES = [
    "삼성전자", "현대자동차", "LG전자", "SK텔레콤", "KT",
    "카카오", "네이버", "CJ제일제당", "롯데칠성음료", "아모레퍼시픽",
    "LG생활건강", "한화", "신한은행", "KB금융지주", "하나금융지주",
    "현대카드", "기아", "쿠팡", "배달의민족", "당근",
    "토스", "야놀자", "직방", "마켓컬리", "무신사",
    "올리브영", "이니스프리", "설화수", "삼성생명", "현대해상",
]


# ── Helpers ──

def _normalize_company_name(name: str) -> str:
    """Remove corporate suffixes for matching."""
    name = _CORP_STRIP_RE.sub("", name)
    return name.strip()


def _parse_korean_number(text: str) -> float | None:
    """Parse Korean-style numbers (e.g., '1,234', '5억 3천만', '(1,234)').

    Handles:
    - Comma-separated: '1,234,567'
    - Korean unit suffixes: '5억 3천만'
    - Parenthesized negatives: '(1,234)'
    - Unit indicators: numbers may be in 백만원, 천원, 원 etc.
    - Dash/minus prefixed negatives

    Returns value in 원 (won), or None if parsing fails.
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # Check for parenthesized negative
    is_negative = False
    if text.startswith("(") and text.endswith(")"):
        is_negative = True
        text = text[1:-1].strip()

    if text.startswith(("-", "\u2212")):  # minus or em-dash
        is_negative = True
        text = text.lstrip("-\u2212").strip()

    # Try Korean unit parsing (e.g., '5억 3천만', '15억', '3천5백만')
    # Korean number system: [N조] [N억] [N만] [N]
    # Each tier can have sub-multipliers: "3천만" = 3000 * 만, "5백억" = 500 * 억
    total = 0.0
    has_kr_unit = False
    remaining = text

    for tier_name, tier_value in _KR_TIERS:
        # Match pattern: optional (number+sub_unit)* + number + tier_unit
        # e.g., "3천5백만" → 3*1000 + 5*100 = 3500, then * 만(10000)
        tier_pattern = re.compile(
            rf"([\d,.\s천백]+?)\s*{tier_name}"
        )
        match = tier_pattern.search(remaining)
        if not match:
            continue

        has_kr_unit = True
        raw_coefficient = match.group(1).strip()

        # Parse coefficient: may contain sub-units like "3천5백"
        coeff = 0.0
        coeff_remaining = raw_coefficient
        for sub_name, sub_value in _KR_SUB:
            sub_pat = re.compile(rf"([\d,.]+)\s*{sub_name}")
            sub_match = sub_pat.search(coeff_remaining)
            if sub_match:
                try:
                    coeff += float(sub_match.group(1).replace(",", "")) * sub_value
                except ValueError:
                    pass
                coeff_remaining = (
                    coeff_remaining[:sub_match.start()]
                    + coeff_remaining[sub_match.end():]
                )

        # Pick up any remaining plain number in the coefficient
        plain = _COMMA_NUM_RE.search(coeff_remaining.strip())
        if plain:
            try:
                coeff += float(plain.group().replace(",", "").replace(" ", ""))
            except ValueError:
                pass

        if coeff == 0:
            coeff = 1.0  # bare "만" or "억" without prefix = 1

        total += coeff * tier_value
        remaining = remaining[:match.start()] + remaining[match.end():]

    if has_kr_unit:
        # Pick up any trailing plain number (단위 없는 나머지)
        trailing = _COMMA_NUM_RE.search(remaining.strip())
        if trailing:
            try:
                total += float(trailing.group().replace(",", "").replace(" ", ""))
            except ValueError:
                pass
        return -total if is_negative else total

    # Plain comma-separated number
    match = _COMMA_NUM_RE.search(text)
    if match:
        try:
            value = float(match.group().replace(",", "").replace(" ", ""))
            return -value if is_negative else value
        except ValueError:
            return None

    return None


def _detect_unit_multiplier(table_html: str) -> float:
    """Detect the reporting unit from table headers/captions.

    Returns multiplier to convert to 원.
    Common patterns: (단위: 백만원), (단위: 천원), (단위: 원)
    """
    unit_patterns = [
        (r"단위\s*[:\uff1a]\s*백만\s*원", 1_000_000),
        (r"단위\s*[:\uff1a]\s*천\s*원", 1_000),
        (r"단위\s*[:\uff1a]\s*억\s*원", 100_000_000),
        (r"단위\s*[:\uff1a]\s*만\s*원", 10_000),
        (r"단위\s*[:\uff1a]\s*원", 1),
        # Alternative formats
        (r"\(백만원\)", 1_000_000),
        (r"\(천원\)", 1_000),
        (r"\(억원\)", 100_000_000),
        (r"\(원\)", 1),
    ]
    for pattern, multiplier in unit_patterns:
        if re.search(pattern, table_html):
            return multiplier
    # Default: 백만원 (most common in Korean financial statements)
    return 1_000_000


# ── Core Functions ──

async def search_company_reports(
    session: aiohttp.ClientSession,
    company_name: str,
    year: int | None = None,
) -> list[dict]:
    """Search DART for a company's annual reports (사업보고서).

    Args:
        session: aiohttp client session
        company_name: Korean company name (e.g., '삼성전자')
        year: Fiscal year to search. Defaults to previous year.

    Returns:
        List of dicts: [{"rcp_no": "...", "company": "...", "title": "...", "date": "..."}]
    """
    if year is None:
        year = datetime.now().year - 1

    start_dt = f"{year}0101"
    end_dt = f"{year}1231"

    form_data = {
        "textCrpNm": company_name,
        "startDt": start_dt,
        "endDt": end_dt,
        "publicType": "A",  # A = annual report (사업보고서)
        "maxResults": "10",
        "currentPage": "1",
    }

    logger.info("[dart] searching reports: company={} year={}", company_name, year)

    try:
        async with session.post(
            DART_SEARCH_URL, data=form_data, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status != 200:
                logger.warning("[dart] search failed: HTTP {} for {}", resp.status, company_name)
                return []
            html = await resp.text()
    except Exception as e:
        logger.warning("[dart] search request error for {}: {}", company_name, str(e))
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # DART search results are in a table with class 'tbList' or similar
    table = soup.find("table")
    if not table:
        logger.debug("[dart] no results table for {}", company_name)
        return []

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        # Look for link containing rcpNo
        link = row.find("a", href=True)
        if not link:
            continue

        href = link.get("href", "")
        # Extract rcpNo from URL patterns like:
        # /dsaf001/main.do?rcpNo=20240315000123
        # javascript:openViewer('20240315000123')
        rcp_match = re.search(r"rcpNo[='](\d+)", href)
        if not rcp_match:
            # Try onclick attribute
            onclick = link.get("onclick", "")
            rcp_match = re.search(r"(?:rcpNo|openViewer)[=('](\d+)", onclick)
        if not rcp_match:
            # Try to find rcpNo in the row text
            rcp_match = re.search(r"(\d{14})", str(row))

        if not rcp_match:
            continue

        rcp_no = rcp_match.group(1)
        title = link.get_text(strip=True)

        # Only process annual reports (사업보고서)
        if "사업보고서" not in title and "분기보고서" not in title and "반기보고서" not in title:
            # Still include it - could be a variant title
            pass

        # Get company name and date from cells
        company_cell = cells[0].get_text(strip=True) if len(cells) > 0 else company_name
        date_cell = cells[-1].get_text(strip=True) if cells else ""

        results.append({
            "rcp_no": rcp_no,
            "company": company_cell or company_name,
            "title": title,
            "date": date_cell,
            "search_name": company_name,
        })

    logger.info("[dart] found {} reports for {} (year={})", len(results), company_name, year)
    return results


async def _fetch_report_document_urls(
    session: aiohttp.ClientSession,
    rcp_no: str,
) -> list[str]:
    """Fetch the sub-document URLs from a DART report page.

    DART reports have a tree/menu of sub-documents. We need to find
    the one containing financial statements (재무제표/판매비와관리비).

    Returns list of viewer URLs to check.
    """
    url = f"{DART_REPORT_URL}?rcpNo={rcp_no}"
    logger.debug("[dart] fetching report page: {}", url)

    try:
        async with session.get(url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logger.warning("[dart] report page failed: HTTP {} for rcpNo={}", resp.status, rcp_no)
                return []
            html = await resp.text()
    except Exception as e:
        logger.warning("[dart] report page error for rcpNo={}: {}", rcp_no, str(e))
        return []

    soup = BeautifulSoup(html, "html.parser")
    doc_urls = []

    # DART report pages use a tree structure with dcmNo parameters
    # Look for links/scripts with dcmNo values
    for script in soup.find_all("script"):
        script_text = script.string or ""
        # Pattern: node(..., "dcmNo", ...) or dcmNo=XXXX
        for match in re.finditer(r"dcmNo[=:'\"]?\s*(\d+)", script_text):
            dcm_no = match.group(1)
            doc_urls.append(
                f"{DART_VIEWER_URL}?rcpNo={rcp_no}&dcmNo={dcm_no}&eleId=0&offset=0&length=0&dtd=dart3.xsd"
            )

    # Also check for iframe sources
    for iframe in soup.find_all("iframe", src=True):
        src = iframe["src"]
        if "viewer" in src or "dcmNo" in src:
            if not src.startswith("http"):
                src = f"https://dart.fss.or.kr{src}"
            doc_urls.append(src)

    # Fallback: try common viewer URL pattern
    if not doc_urls:
        doc_urls.append(
            f"{DART_VIEWER_URL}?rcpNo={rcp_no}&dcmNo=&eleId=0&offset=0&length=0&dtd=dart3.xsd"
        )

    logger.debug("[dart] found {} sub-document URLs for rcpNo={}", len(doc_urls), rcp_no)
    return doc_urls[:10]  # Limit to avoid too many requests


async def extract_ad_expense(
    session: aiohttp.ClientSession,
    rcp_no: str,
) -> dict | None:
    """Extract advertising expense from a specific DART report.

    Navigates through the report to find the cost breakdown table
    (판매비와관리비) and extracts advertising-related line items.

    Returns:
        {"ad_expense": float (in won), "fiscal_year": str, "items": [...], "unit": str}
        or None if not found.
    """
    logger.info("[dart] extracting ad expense from rcpNo={}", rcp_no)

    doc_urls = await _fetch_report_document_urls(session, rcp_no)

    await asyncio.sleep(REQUEST_DELAY)

    for doc_url in doc_urls:
        try:
            async with session.get(
                doc_url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
        except Exception:
            continue

        # Check if this document contains relevant financial data
        if not any(kw in html for kw in ["판매비", "관리비", "광고선전비", "광고비"]):
            await asyncio.sleep(1.0)
            continue

        result = _parse_expense_table(html, rcp_no)
        if result:
            return result

        await asyncio.sleep(1.0)

    # Fallback: try the main report page directly
    main_url = f"{DART_REPORT_URL}?rcpNo={rcp_no}"
    try:
        async with session.get(
            main_url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            if resp.status == 200:
                html = await resp.text()
                result = _parse_expense_table(html, rcp_no)
                if result:
                    return result
    except Exception:
        pass

    logger.info("[dart] no ad expense data found for rcpNo={}", rcp_no)
    return None


def _parse_expense_table(html: str, rcp_no: str) -> dict | None:
    """Parse HTML to find ad expense rows in 판매비와관리비 table.

    Financial statements may vary by company, so we use flexible
    pattern matching across multiple table formats.
    """
    soup = BeautifulSoup(html, "html.parser")
    unit_multiplier = _detect_unit_multiplier(html)

    unit_label = {
        1: "원",
        1_000: "천원",
        10_000: "만원",
        1_000_000: "백만원",
        100_000_000: "억원",
    }.get(int(unit_multiplier), f"x{int(unit_multiplier)}")

    found_items = []
    total_ad_expense = 0.0

    # Search all tables for expense keywords
    tables = soup.find_all("table")

    for table in tables:
        table_text = table.get_text()
        # Quick check: does this table contain any expense keywords?
        if not any(kw in table_text for kw in EXPENSE_KEYWORDS):
            continue

        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            row_text = cells[0].get_text(strip=True)

            # Check if this row contains an expense keyword
            matched_keyword = None
            for kw in EXPENSE_KEYWORDS:
                if kw in row_text:
                    matched_keyword = kw
                    break

            if not matched_keyword:
                continue

            # Try to extract the number from subsequent cells
            # Financial tables typically have: label | current year | previous year
            for cell in cells[1:]:
                cell_text = cell.get_text(strip=True)
                if not cell_text or cell_text in ("-", "−", " "):
                    continue

                value = _parse_korean_number(cell_text)
                if value is not None and value != 0:
                    actual_value = value * unit_multiplier
                    found_items.append({
                        "keyword": matched_keyword,
                        "raw_text": cell_text,
                        "value_in_unit": value,
                        "value_in_won": actual_value,
                    })
                    total_ad_expense += actual_value
                    break  # Take first (current year) column

    if not found_items:
        return None

    # Determine fiscal year from document
    # Try to find year info in the HTML
    year_match = re.search(
        r"(\d{4})\s*[년.]\s*(?:1[0-2]|0?[1-9])\s*[월.]?\s*(?:3[01]|[12]\d|0?[1-9])\s*[일]?\s*(?:현재|기준|까지|말)",
        html,
    )
    fiscal_year = year_match.group(1) if year_match else str(datetime.now().year - 1)

    logger.info(
        "[dart] rcpNo={}: found {} expense items, total={:,.0f} won (unit={})",
        rcp_no, len(found_items), total_ad_expense, unit_label,
    )

    return {
        "ad_expense": total_ad_expense,
        "fiscal_year": fiscal_year,
        "items": found_items,
        "unit": unit_label,
        "rcp_no": rcp_no,
    }


async def collect_dart_expenses(
    company_names: list[str] | None = None,
    year: int | None = None,
) -> dict:
    """Main entry: collect ad expenses for all target companies.

    Args:
        company_names: List of company names to search. Defaults to TOP_COMPANIES.
        year: Fiscal year to search. Defaults to previous year.

    Returns:
        {"searched": int, "found": int, "matched": int, "stored": int, "results": [...]}
    """
    if company_names is None:
        company_names = TOP_COMPANIES

    if year is None:
        year = datetime.now().year - 1

    logger.info("[dart] starting DART expense collection: {} companies, year={}", len(company_names), year)

    dart_results = []

    async with aiohttp.ClientSession() as http_session:
        for company in company_names:
            try:
                reports = await search_company_reports(http_session, company, year)
                await asyncio.sleep(REQUEST_DELAY)

                if not reports:
                    logger.debug("[dart] no reports found for {}", company)
                    continue

                # Take the first (most recent) annual report
                report = reports[0]
                rcp_no = report["rcp_no"]

                expense_data = await extract_ad_expense(http_session, rcp_no)
                await asyncio.sleep(REQUEST_DELAY)

                if expense_data and expense_data["ad_expense"] > 0:
                    dart_results.append({
                        "company_name": company,
                        "dart_company": report.get("company", company),
                        "rcp_no": rcp_no,
                        "ad_expense": expense_data["ad_expense"],
                        "fiscal_year": expense_data["fiscal_year"],
                        "items": expense_data["items"],
                        "unit": expense_data["unit"],
                    })
                    logger.info(
                        "[dart] {} ad expense: {:,.0f} won (FY{})",
                        company, expense_data["ad_expense"], expense_data["fiscal_year"],
                    )
                else:
                    logger.debug("[dart] no ad expense found for {}", company)

            except Exception as e:
                logger.warning("[dart] error collecting {}: {}", company, str(e))
                await asyncio.sleep(REQUEST_DELAY)

    logger.info("[dart] collection done: {}/{} companies had expense data",
                len(dart_results), len(company_names))

    # Match and store results
    match_stats = await match_and_store(dart_results)

    return {
        "searched": len(company_names),
        "found": len(dart_results),
        "matched": match_stats["matched"],
        "stored": match_stats["stored"],
        "year": year,
        "results": dart_results,
    }


async def match_and_store(dart_results: list[dict]) -> dict:
    """Match DART companies to AdScope advertisers and store.

    Uses fuzzy matching via AdvertiserMatcher to link DART company names
    to existing advertisers in the database.

    Args:
        dart_results: List of dicts from collect_dart_expenses

    Returns:
        {"matched": int, "stored": int, "unmatched": list[str]}
    """
    if not dart_results:
        return {"matched": 0, "stored": 0, "unmatched": []}

    matcher = AdvertiserMatcher()
    matched = 0
    stored = 0
    unmatched = []

    async with async_session() as session:
        # Load all advertisers for matching
        result = await session.execute(
            select(Advertiser.id, Advertiser.name, Advertiser.website, Advertiser.aliases)
        )
        advertisers = [
            {
                "id": row.id,
                "name": row.name,
                "website": row.website,
                "aliases": row.aliases or [],
            }
            for row in result.fetchall()
        ]
        matcher.load_advertisers(advertisers)

        for dart_item in dart_results:
            company_name = dart_item["company_name"]
            normalized = _normalize_company_name(company_name)

            # Try matching with both original and normalized names
            adv_id, score = matcher.match(company_name)
            if adv_id is None:
                adv_id, score = matcher.match(normalized)

            if adv_id is None:
                unmatched.append(company_name)
                logger.debug("[dart] unmatched company: {}", company_name)
                continue

            matched += 1

            # Update advertiser with DART data
            try:
                adv = await session.get(Advertiser, adv_id)
                if adv:
                    adv.dart_ad_expense = dart_item["ad_expense"]
                    adv.dart_fiscal_year = dart_item["fiscal_year"]
                    # Append DART to data source
                    if adv.data_source:
                        if "dart" not in adv.data_source:
                            adv.data_source = f"{adv.data_source},dart"
                    else:
                        adv.data_source = "dart"
                    adv.profile_updated_at = datetime.utcnow()
                    stored += 1
                    logger.info(
                        "[dart] stored: {} (id={}) -> {:,.0f} won (FY{}, match_score={})",
                        company_name, adv_id, dart_item["ad_expense"],
                        dart_item["fiscal_year"], score,
                    )
            except Exception as e:
                logger.warning("[dart] failed to store for {}: {}", company_name, str(e))

        await session.commit()

    logger.info("[dart] match results: matched={}, stored={}, unmatched={}",
                matched, stored, len(unmatched))

    return {
        "matched": matched,
        "stored": stored,
        "unmatched": unmatched,
    }


# ── CLI entry point ──

async def _main():
    """Standalone CLI runner."""
    from database import init_db
    await init_db()
    stats = await collect_dart_expenses()
    logger.info("[dart] final stats: {}", stats)


if __name__ == "__main__":
    asyncio.run(_main())
