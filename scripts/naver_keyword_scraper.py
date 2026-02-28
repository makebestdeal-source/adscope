"""Naver Search Ads Keyword Planner scraper.

Logs into manage.searchad.naver.com, uses the keyword planner tool
to look up commercial keywords, and captures keyword suggestions
(CPC, monthly search volume) via network interception.

Saves results to the Keyword table in the database.

Usage:
    python scripts/naver_keyword_scraper.py
    python scripts/naver_keyword_scraper.py --categories "finance,medical"
    python scripts/naver_keyword_scraper.py --dry-run
"""

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

import httpx
from loguru import logger
from playwright.async_api import async_playwright, Page, Response, BrowserContext
from sqlalchemy import select

from database import async_session, init_db
from database.models import Keyword, Industry

# ========================================================================
# Configuration
# ========================================================================

NAVER_AD_LOGIN_URL = "https://searchad.naver.com/"
NAVER_AD_MANAGE_URL = "https://manage.searchad.naver.com"
KEYWORD_PLANNER_URL = "https://manage.searchad.naver.com/customers/{customer_id}/tool/keyword-planner"

# Default credentials (override via env or CLI)
DEFAULT_ID = os.getenv("NAVER_AD_ID", "dingojm")
DEFAULT_PW = os.getenv("NAVER_AD_PW", "type5810@")
DEFAULT_CUSTOMER_ID = os.getenv("NAVER_AD_CUSTOMER_ID", "1903273")

# REST API credentials (no browser needed)
NAVER_AD_API_KEY = os.getenv("NAVER_AD_API_KEY", "")
NAVER_AD_SECRET_KEY = os.getenv("NAVER_AD_SECRET_KEY", "")
NAVER_AD_API_BASE = "https://api.naver.com"

# Keyword categories to search, mapped to industry IDs
# industry_id: name from industries.json
# 1=finance, 2=medical/beauty, 3=education, 4=real_estate, 5=law
# 6=shopping, 7=IT, 8=travel, 9=food, 10=auto
KEYWORD_CATEGORIES = {
    "finance": {
        "industry_id": 1,
        "seeds": ["loan", "insurance", "credit card", "savings"],
        "seeds_kr": ["대출", "보험", "신용카드 추천", "적금"],
    },
    "medical": {
        "industry_id": 2,
        "seeds": ["plastic surgery", "dermatology", "dental"],
        "seeds_kr": ["성형외과", "피부과", "치과", "임플란트", "다이어트"],
    },
    "education": {
        "industry_id": 3,
        "seeds": ["english academy", "study abroad"],
        "seeds_kr": ["영어학원", "유학", "코딩교육", "자격증"],
    },
    "real_estate": {
        "industry_id": 4,
        "seeds": ["apartment", "interior design", "moving"],
        "seeds_kr": ["아파트 분양", "인테리어", "이사", "부동산"],
    },
    "law": {
        "industry_id": 5,
        "seeds": ["lawyer", "divorce"],
        "seeds_kr": ["변호사", "이혼 소송", "법무사"],
    },
    "shopping": {
        "industry_id": 6,
        "seeds": ["cosmetics", "fashion", "health food"],
        "seeds_kr": ["화장품", "패션", "건강식품", "가구"],
    },
    "IT": {
        "industry_id": 7,
        "seeds": ["web hosting", "app development"],
        "seeds_kr": ["홈페이지제작", "앱개발", "클라우드"],
    },
    "travel": {
        "industry_id": 8,
        "seeds": ["hotel reservation", "rental car"],
        "seeds_kr": ["호텔 예약", "렌터카", "패키지 여행"],
    },
    "food": {
        "industry_id": 9,
        "seeds": ["franchise", "meal kit"],
        "seeds_kr": ["프랜차이즈 창업", "밀키트", "배달"],
    },
    "auto": {
        "industry_id": 10,
        "seeds": ["new car", "used car", "car insurance"],
        "seeds_kr": ["신차", "중고차", "자동차 보험", "장기렌트"],
    },
    "wedding": {
        "industry_id": None,  # will use "etc" industry
        "seeds_kr": ["웨딩", "웨딩홀", "스드메"],
    },
    "funeral": {
        "industry_id": None,
        "seeds_kr": ["장례", "장례식장", "상조"],
    },
}

# Network patterns to capture from the keyword planner
KEYWORD_API_PATTERNS = [
    "/keywordstool",
    "/keyword-planner",
    "RelKwdStat",
    "managetool",
    "/tool/keyword",
    "estimate/",
]


# ========================================================================
# Naver Search Ads REST API (no browser needed)
# ========================================================================

class NaverKeywordAPI:
    """REST API client for Naver Search Ads keyword tool.

    Requires API_KEY and SECRET_KEY from Naver Search Ads console:
    Tools > API Manager > generate Access License + Secret Key.
    """

    def __init__(
        self,
        customer_id: str = DEFAULT_CUSTOMER_ID,
        api_key: str = NAVER_AD_API_KEY,
        secret_key: str = NAVER_AD_SECRET_KEY,
    ):
        self.customer_id = customer_id
        self.api_key = api_key
        self.secret_key = secret_key

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    def _signature(self, timestamp: str, method: str, uri: str) -> str:
        message = f"{timestamp}.{method}.{uri}"
        h = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(h.digest()).decode("utf-8")

    def _headers(self, method: str, uri: str) -> dict:
        ts = str(int(time.time() * 1000))
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": ts,
            "X-API-KEY": self.api_key,
            "X-Customer": self.customer_id,
            "X-Signature": self._signature(ts, method, uri),
        }

    async def get_keywords(self, hint: str) -> list[dict]:
        """Fetch keyword suggestions for a hint keyword."""
        uri = "/keywordstool"
        params = {"hintKeywords": hint, "showDetail": "1"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{NAVER_AD_API_BASE}{uri}",
                params=params,
                headers=self._headers("GET", uri),
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("keywordList", [])

    async def search_all(
        self,
        categories: dict,
        parse_vol_fn=None,
    ) -> list[dict]:
        """Search all seed keywords across categories via REST API."""
        if parse_vol_fn is None:
            parse_vol_fn = NaverKeywordScraper._parse_vol

        all_results: list[dict] = []
        seen: set[str] = set()

        for cat_name, cat_config in categories.items():
            seeds = cat_config.get("seeds_kr", [])
            industry_id = cat_config.get("industry_id") or 1
            logger.info("[API] Category '{}': {} seeds", cat_name, len(seeds))

            for seed in seeds:
                try:
                    items = await self.get_keywords(seed)
                    count = 0
                    for item in items:
                        kw = (
                            item.get("relKeyword")
                            or item.get("keyword")
                            or ""
                        ).strip()
                        if not kw or kw in seen:
                            continue
                        seen.add(kw)

                        pc_vol = parse_vol_fn(item.get("monthlyPcQcCnt", 0))
                        mo_vol = parse_vol_fn(item.get("monthlyMobileQcCnt", 0))
                        total_vol = pc_vol + mo_vol

                        cpc = item.get("plAvgDepth") or 0
                        if isinstance(cpc, str):
                            cpc = int(re.sub(r"[^0-9]", "", cpc) or "0")

                        competition = item.get("compIdx", "")

                        all_results.append({
                            "keyword": kw,
                            "industry_id": industry_id,
                            "naver_cpc": int(cpc) if cpc else None,
                            "monthly_search_vol": total_vol if total_vol else None,
                            "extra": {
                                "pc_search_vol": pc_vol,
                                "mobile_search_vol": mo_vol,
                                "competition": str(competition),
                                "source": "naver_keyword_api",
                            },
                        })
                        count += 1

                    logger.info("[API] '{}' -> {} keywords", seed, count)
                except Exception as e:
                    logger.error("[API] '{}' error: {}", seed, str(e)[:200])

                await asyncio.sleep(0.5)

        return all_results


# ========================================================================
# Naver Search Ads Keyword Planner Scraper (browser fallback)
# ========================================================================

class NaverKeywordScraper:
    """Scrapes keyword data from Naver Search Ads Keyword Planner."""

    def __init__(
        self,
        naver_id: str = DEFAULT_ID,
        naver_pw: str = DEFAULT_PW,
        customer_id: str = DEFAULT_CUSTOMER_ID,
        headless: bool = True,
        dry_run: bool = False,
    ):
        self.naver_id = naver_id
        self.naver_pw = naver_pw
        self.customer_id = customer_id
        self.headless = headless
        self.dry_run = dry_run
        self._playwright = None
        self._browser = None
        self._captured_responses: list[dict] = []
        self._all_keywords: list[dict] = []

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
            ],
        )
        logger.info("Browser started (headless={})", self.headless)

    async def stop(self):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser stopped")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    # ----------------------------------------------------------------
    # Login
    # ----------------------------------------------------------------

    async def login(self) -> BrowserContext:
        """Log into Naver Search Ads via Naver login."""
        context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await context.new_page()

        # Navigate to Naver Search Ads login
        logger.info("Navigating to Naver Search Ads login...")
        await page.goto(NAVER_AD_LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Click login button if present on the landing page
        try:
            login_btn = page.locator('a:has-text("login"), a:has-text("Login"), '
                                     'button:has-text("login"), '
                                     'a[href*="naver.com/login"], '
                                     'a.login, button.login, '
                                     'a:has-text("Start"), '
                                     'a:has-text("sign in")')
            if await login_btn.count() > 0:
                await login_btn.first.click()
                await asyncio.sleep(2)
        except Exception:
            pass

        # Check if we're on a Naver login page
        current_url = page.url
        logger.info("Current URL: {}", current_url)

        # If we need to go to Naver login directly
        if "nid.naver.com" not in current_url and "naver.com/naver/login" not in current_url:
            # mode=form forces traditional ID/PW form (default shows QR code)
            await page.goto(
                "https://nid.naver.com/nidlogin.login?"
                "mode=form&url=https://manage.searchad.naver.com",
                wait_until="domcontentloaded",
            )
            await asyncio.sleep(2)

        # Fill in credentials using clipboard paste to avoid bot detection
        logger.info("Entering credentials...")
        await self._fill_login_form(page)

        # Wait for redirect to manage page
        try:
            await page.wait_for_url(
                "**/manage.searchad.naver.com/**",
                timeout=30000,
            )
            logger.info("Login successful! URL: {}", page.url)
        except Exception:
            # Check if there's a CAPTCHA or 2FA
            current_url = page.url
            logger.warning("Login may require manual intervention. URL: {}", current_url)

            # Check for common obstacles
            page_text = await page.inner_text("body")
            if "captcha" in page_text.lower() or "보안" in page_text:
                logger.error("CAPTCHA detected. Try running with --headful")
                raise RuntimeError("CAPTCHA detected during login")
            if "2단계" in page_text or "two-step" in page_text.lower():
                logger.error("2FA required. Add phone verification first.")
                raise RuntimeError("2FA required")

            # Maybe we got redirected somewhere else useful
            if "searchad" in current_url:
                logger.info("Appears to be on searchad domain, continuing...")
            else:
                raise RuntimeError(
                    f"Login failed. Stuck at: {current_url}"
                )

        return context

    async def _fill_login_form(self, page: Page):
        """Fill in the Naver login form.

        Naver's bot detection checks for:
        - Direct element.value assignment (flagged)
        - Playwright's type() speed patterns (flagged)
        - Missing clipboard events (flagged)

        We use clipboard paste via keyboard shortcut, which is the most
        reliable method to bypass their detection.
        """
        # Wait for the login form
        await page.wait_for_selector("#id, input[name='id']", timeout=10000)
        await asyncio.sleep(1)

        id_selector = "#id"
        pw_selector = "#pw"

        # Method: Clipboard paste via pyperclip-style approach
        # Focus ID field, select all, paste
        await page.click(id_selector)
        await asyncio.sleep(0.3)
        await page.keyboard.press("Control+A")
        await asyncio.sleep(0.1)

        # Use Playwright's clipboard to paste the ID
        await page.evaluate(
            """async (text) => {
                await navigator.clipboard.writeText(text);
            }""",
            self.naver_id,
        )
        await page.keyboard.press("Control+V")
        await asyncio.sleep(0.5)

        # If clipboard didn't work (common in headless), use fallback
        id_value = await page.evaluate(
            f'document.querySelector("{id_selector}").value'
        )
        if not id_value or id_value != self.naver_id:
            logger.debug("Clipboard paste failed, using character-by-character input")
            await page.click(id_selector, click_count=3)  # select all
            await asyncio.sleep(0.2)
            # Type character by character with random delays
            for ch in self.naver_id:
                await page.keyboard.press(ch)
                await asyncio.sleep(0.05 + 0.05 * (hash(ch) % 3))
            await asyncio.sleep(0.3)

        # Focus and fill password
        await page.click(pw_selector)
        await asyncio.sleep(0.3)
        await page.keyboard.press("Control+A")
        await asyncio.sleep(0.1)

        await page.evaluate(
            """async (text) => {
                await navigator.clipboard.writeText(text);
            }""",
            self.naver_pw,
        )
        await page.keyboard.press("Control+V")
        await asyncio.sleep(0.5)

        # Verify password was entered
        pw_value = await page.evaluate(
            f'document.querySelector("{pw_selector}").value'
        )
        if not pw_value or pw_value != self.naver_pw:
            logger.debug("Clipboard paste failed for PW, using character input")
            await page.click(pw_selector, click_count=3)
            await asyncio.sleep(0.2)
            for ch in self.naver_pw:
                await page.keyboard.press(ch)
                await asyncio.sleep(0.05 + 0.05 * (hash(ch) % 3))
            await asyncio.sleep(0.3)

        # Click login button
        login_btn = page.locator(
            '#log\\.login, button[type="submit"], '
            'input[type="submit"], button:has-text("Log"), '
            'button.btn_login, .btn_global'
        )
        if await login_btn.count() > 0:
            await login_btn.first.click()
        else:
            await page.keyboard.press("Enter")

        await asyncio.sleep(3)

    # ----------------------------------------------------------------
    # Keyword Planner Interaction
    # ----------------------------------------------------------------

    async def search_keywords(
        self,
        context: BrowserContext,
        seed_keywords: list[str],
        industry_id: int,
        category_name: str = "",
    ) -> list[dict]:
        """Search for keywords using the keyword planner tool.

        Uses two strategies:
        1. Network interception of the keyword planner's internal API
        2. Direct parsing of the results table if network capture fails
        """
        page = await context.new_page()
        results: list[dict] = []

        try:
            # Set up network interception
            captured_data: list[dict] = []

            async def _on_response(response: Response):
                url = response.url
                # Capture keyword tool API responses
                is_keyword_api = any(p in url for p in KEYWORD_API_PATTERNS)
                is_manage_api = "manage.searchad.naver.com" in url and (
                    "/api/" in url or "/tool/" in url
                )
                is_ad_api = "api.searchad.naver.com" in url

                if is_keyword_api or is_manage_api or is_ad_api:
                    try:
                        if response.status == 200:
                            ct = response.headers.get("content-type", "")
                            if "json" in ct or "javascript" in ct:
                                body = await response.text()
                                if body and len(body) > 10:
                                    try:
                                        data = json.loads(body)
                                        captured_data.append({
                                            "url": url,
                                            "data": data,
                                        })
                                        logger.debug(
                                            "Captured API response: {} ({} bytes)",
                                            url[:100], len(body),
                                        )
                                    except json.JSONDecodeError:
                                        pass
                    except Exception:
                        pass

            page.on("response", _on_response)

            # Navigate to keyword planner
            planner_url = KEYWORD_PLANNER_URL.format(
                customer_id=self.customer_id,
            )
            logger.info("Navigating to keyword planner: {}", planner_url)
            await page.goto(planner_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Check if we're on the right page
            if "tool/keyword" not in page.url:
                logger.warning(
                    "Not on keyword planner page. URL: {}", page.url,
                )
                # Try direct navigation
                await page.goto(planner_url, wait_until="networkidle")
                await asyncio.sleep(3)

            # Process each seed keyword
            for seed in seed_keywords:
                logger.info(
                    "[{}] Searching keyword: {}",
                    category_name, seed,
                )
                captured_data.clear()

                try:
                    kw_results = await self._search_single_keyword(
                        page, seed, captured_data, industry_id,
                    )
                    results.extend(kw_results)
                    logger.info(
                        "[{}] '{}' -> {} keywords found",
                        category_name, seed, len(kw_results),
                    )
                except Exception as e:
                    logger.error(
                        "[{}] Error searching '{}': {}",
                        category_name, seed, str(e)[:200],
                    )

                # Brief pause between searches
                await asyncio.sleep(2)

        finally:
            await page.close()

        return results

    async def _search_single_keyword(
        self,
        page: Page,
        seed: str,
        captured_data: list[dict],
        industry_id: int,
    ) -> list[dict]:
        """Search for a single seed keyword and extract results."""
        results = []

        # Find the keyword input field
        input_selectors = [
            'input[placeholder*="keyword"]',
            'input[placeholder*="Keyword"]',
            'textarea[placeholder*="keyword"]',
            'input[type="text"]',
            'textarea',
            '.keyword-input input',
            '.search-input input',
            'input[name*="keyword"]',
            'input[name*="query"]',
            '#keyword',
            '.tool_keyword input',
            '[class*="keyword"] input',
            '[class*="search"] input',
        ]

        input_el = None
        for sel in input_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    input_el = page.locator(sel).first
                    # Verify it's visible
                    if await input_el.is_visible():
                        break
                    input_el = None
            except Exception:
                continue

        if not input_el:
            logger.warning("Could not find keyword input field")
            # Try to find any text input on the page
            all_inputs = page.locator('input[type="text"], textarea')
            count = await all_inputs.count()
            if count > 0:
                input_el = all_inputs.first
                logger.info("Using fallback text input")
            else:
                logger.error("No text input found on page at all")
                return results

        # Clear and type the keyword
        await input_el.click()
        await asyncio.sleep(0.3)
        await input_el.fill("")
        await asyncio.sleep(0.2)
        await input_el.fill(seed)
        await asyncio.sleep(0.5)

        # Click search/query button
        search_btn_selectors = [
            'button:has-text("search")',
            'button:has-text("Search")',
            'button:has-text("query")',
            'button:has-text("Query")',
            'button[type="submit"]',
            '.btn-search',
            '.search-btn',
            'button.btn_search',
            '[class*="search"] button',
            '[class*="query"] button',
            'button:has-text("view")',
        ]

        clicked = False
        for sel in search_btn_selectors:
            try:
                btn = page.locator(sel)
                if await btn.count() > 0 and await btn.first.is_visible():
                    await btn.first.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            # Try Enter key
            await input_el.press("Enter")

        # Wait for results to load
        await asyncio.sleep(5)

        # Strategy 1: Parse captured network data
        if captured_data:
            results = self._parse_captured_keyword_data(
                captured_data, industry_id,
            )
            if results:
                logger.info(
                    "Strategy 1 (network capture): {} keywords", len(results),
                )
                return results

        # Strategy 2: Parse the results table from the DOM
        results = await self._parse_keyword_table(page, industry_id)
        if results:
            logger.info(
                "Strategy 2 (DOM table parse): {} keywords", len(results),
            )
            return results

        # Strategy 3: Try scrolling and waiting more
        await page.mouse.wheel(0, 500)
        await asyncio.sleep(3)

        if captured_data:
            results = self._parse_captured_keyword_data(
                captured_data, industry_id,
            )
        if not results:
            results = await self._parse_keyword_table(page, industry_id)

        logger.info(
            "Strategy 3 (scroll + retry): {} keywords", len(results),
        )
        return results

    @staticmethod
    def _parse_vol(val) -> int:
        """Parse a volume value that may be int, str like '< 10', or other."""
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val)
        if isinstance(val, str):
            cleaned = re.sub(r"[^0-9]", "", val)
            return int(cleaned) if cleaned else 0
        return 0

    def _parse_captured_keyword_data(
        self,
        captured_data: list[dict],
        industry_id: int,
    ) -> list[dict]:
        """Parse keyword data from captured network responses."""
        results = []
        seen = set()

        for entry in captured_data:
            data = entry.get("data")
            if not data:
                continue

            # Handle various response formats from Naver keyword API
            keyword_items = []

            # Format 1: {"keywordList": [...]}
            if isinstance(data, dict) and "keywordList" in data:
                keyword_items = data["keywordList"]

            # Format 2: list of keyword objects directly
            elif isinstance(data, list):
                keyword_items = data

            # Format 3: nested data.keywordList
            elif isinstance(data, dict):
                for key in ["data", "result", "results", "items", "keywords"]:
                    if key in data:
                        inner = data[key]
                        if isinstance(inner, list):
                            keyword_items = inner
                            break
                        elif isinstance(inner, dict) and "keywordList" in inner:
                            keyword_items = inner["keywordList"]
                            break

            for item in keyword_items:
                if not isinstance(item, dict):
                    continue

                # Extract keyword text
                kw = (
                    item.get("relKeyword")
                    or item.get("keyword")
                    or item.get("siteKeyword")
                    or item.get("name")
                    or ""
                ).strip()
                if not kw or kw in seen:
                    continue
                seen.add(kw)

                # Extract CPC
                cpc = (
                    item.get("avgCpc")
                    or item.get("cpc")
                    or item.get("monthlyAveCpc")
                    or item.get("plAvgDepth")
                    or 0
                )
                # Some fields return string like "> 100"
                if isinstance(cpc, str):
                    cpc = int(re.sub(r"[^0-9]", "", cpc) or "0")

                # Extract monthly search volume (PC + Mobile)
                pc_vol = item.get("monthlyPcQcCnt", 0)
                mo_vol = item.get("monthlyMobileQcCnt", 0)
                total_vol = item.get("monthlyQcCnt", 0)

                # Naver sometimes returns "< 10" as a string
                pc_vol = self._parse_vol(pc_vol)
                mo_vol = self._parse_vol(mo_vol)
                total_vol = self._parse_vol(total_vol)

                if total_vol == 0:
                    total_vol = pc_vol + mo_vol

                # Competition level
                competition = (
                    item.get("compIdx")
                    or item.get("competition")
                    or item.get("compLevel")
                    or ""
                )

                results.append({
                    "keyword": kw,
                    "industry_id": industry_id,
                    "naver_cpc": int(cpc) if cpc else None,
                    "monthly_search_vol": total_vol if total_vol else None,
                    "extra": {
                        "pc_search_vol": pc_vol,
                        "mobile_search_vol": mo_vol,
                        "competition": str(competition),
                        "source": "naver_keyword_planner_api",
                    },
                })

        return results

    async def _parse_keyword_table(
        self, page: Page, industry_id: int,
    ) -> list[dict]:
        """Parse keyword results from the visible DOM table."""
        results = await page.evaluate(
            """(industryId) => {
                const results = [];
                const seen = new Set();

                // Find table rows
                const selectors = [
                    'table tbody tr',
                    '.table-body tr',
                    '[class*="keyword"] tr',
                    '[class*="result"] tr',
                    '.data-table tr',
                    'table tr',
                ];

                let rows = [];
                for (const sel of selectors) {
                    const found = document.querySelectorAll(sel);
                    if (found.length > 1) {
                        rows = found;
                        break;
                    }
                }

                if (rows.length === 0) {
                    // Try grid/list layout instead of table
                    const listItems = document.querySelectorAll(
                        '[class*="keyword-item"], [class*="result-item"], '
                        + '[class*="list-item"], .item'
                    );
                    rows = listItems;
                }

                for (const row of rows) {
                    const cells = row.querySelectorAll('td, [class*="cell"]');
                    if (cells.length < 2) continue;

                    // First cell is usually the keyword
                    const kwText = cells[0].textContent.trim();
                    if (!kwText || kwText.length < 2 || seen.has(kwText)) continue;
                    if (kwText.match(/^[0-9.,]+$/)) continue;  // skip pure numbers
                    seen.add(kwText);

                    // Parse numeric values from other cells
                    let cpc = null;
                    let searchVol = null;
                    let pcVol = null;
                    let mobileVol = null;

                    for (let i = 1; i < cells.length; i++) {
                        const text = cells[i].textContent.trim()
                            .replace(/,/g, '').replace(/\\s/g, '');
                        const num = parseInt(text, 10);
                        if (isNaN(num)) continue;

                        // Heuristic: large numbers are search volume,
                        // smaller ones are CPC
                        if (num > 100000) {
                            if (!searchVol) searchVol = num;
                        } else if (num > 50) {
                            if (!cpc) cpc = num;
                            else if (!searchVol) searchVol = num;
                        }
                    }

                    results.push({
                        keyword: kwText,
                        industry_id: industryId,
                        naver_cpc: cpc,
                        monthly_search_vol: searchVol,
                        extra: {
                            source: 'naver_keyword_planner_dom',
                        },
                    });
                }

                return results;
            }""",
            industry_id,
        )
        return results

    # ----------------------------------------------------------------
    # Alternative: Direct API access
    # ----------------------------------------------------------------

    async def try_direct_api(
        self,
        context: BrowserContext,
        seed_keywords: list[str],
        industry_id: int,
    ) -> list[dict]:
        """Try using the Naver Search Ads REST API directly.

        The keyword planner page might expose API credentials in its
        JavaScript context. We try to extract them and call the API.
        """
        page = await context.new_page()
        results = []

        try:
            planner_url = KEYWORD_PLANNER_URL.format(
                customer_id=self.customer_id,
            )
            await page.goto(planner_url, wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # Try to extract API credentials from the page context
            creds = await page.evaluate(
                """() => {
                    // Look for API key/secret in global variables
                    const checks = [
                        window.__SA_CONFIG__,
                        window.__NEXT_DATA__,
                        window.__config__,
                        window.SA,
                        window.searchAd,
                    ];
                    for (const obj of checks) {
                        if (obj && typeof obj === 'object') {
                            return JSON.stringify(obj).substring(0, 2000);
                        }
                    }

                    // Check meta tags
                    const metas = document.querySelectorAll('meta');
                    const metaData = {};
                    metas.forEach(m => {
                        const name = m.getAttribute('name') || m.getAttribute('property');
                        const content = m.getAttribute('content');
                        if (name && content) metaData[name] = content;
                    });

                    // Check cookies for auth tokens
                    const cookies = document.cookie;

                    return JSON.stringify({
                        metas: metaData,
                        cookies: cookies.substring(0, 500),
                        url: window.location.href,
                    });
                }"""
            )
            logger.debug("Page context data: {}", str(creds)[:300])

            # Try to make API calls using the browser's session
            for seed in seed_keywords:
                try:
                    api_result = await page.evaluate(
                        """async (params) => {
                            const { keyword, customerId } = params;
                            try {
                                // Try the internal manage API
                                const url = `/api/ncc/keywordstool?`
                                    + `siteId=&biztpId=&hintKeywords=${encodeURIComponent(keyword)}`
                                    + `&event=&month=&showDetail=1`;
                                const resp = await fetch(url, {
                                    credentials: 'include',
                                    headers: {
                                        'Accept': 'application/json',
                                    },
                                });
                                if (resp.ok) {
                                    return await resp.json();
                                }

                                // Try the public API endpoint
                                const url2 = `https://manage.searchad.naver.com/customers/${customerId}/api/ncc/keywordstool?`
                                    + `siteId=&biztpId=&hintKeywords=${encodeURIComponent(keyword)}`
                                    + `&event=&month=&showDetail=1`;
                                const resp2 = await fetch(url2, {
                                    credentials: 'include',
                                    headers: {
                                        'Accept': 'application/json',
                                    },
                                });
                                if (resp2.ok) {
                                    return await resp2.json();
                                }

                                return {error: `HTTP ${resp.status} / ${resp2.status}`};
                            } catch (e) {
                                return {error: e.message};
                            }
                        }""",
                        {"keyword": seed, "customerId": self.customer_id},
                    )

                    if api_result and "error" not in api_result:
                        parsed = self._parse_captured_keyword_data(
                            [{"url": "direct_api", "data": api_result}],
                            industry_id,
                        )
                        results.extend(parsed)
                        logger.info(
                            "Direct API for '{}': {} keywords",
                            seed, len(parsed),
                        )
                    else:
                        logger.debug(
                            "Direct API failed for '{}': {}",
                            seed, api_result,
                        )

                    await asyncio.sleep(1)

                except Exception as e:
                    logger.debug("Direct API error for '{}': {}", seed, e)

        finally:
            await page.close()

        return results

    # ----------------------------------------------------------------
    # Database save
    # ----------------------------------------------------------------

    async def save_to_db(self, keywords: list[dict]) -> tuple[int, int]:
        """Save keyword results to database. Returns (added, updated)."""
        if not keywords:
            return 0, 0

        await init_db()
        added = 0
        updated = 0

        async with async_session() as session:
            # Ensure "etc" industry exists for unmapped categories
            etc_industry = await session.execute(
                select(Industry).where(Industry.name == "etc")
            )
            etc_row = etc_industry.scalar_one_or_none()
            if not etc_row:
                # Check for Korean name
                etc_industry2 = await session.execute(
                    select(Industry).where(Industry.name == "etc")
                )
                etc_row = etc_industry2.scalar_one_or_none()

            etc_id = etc_row.id if etc_row else 1  # fallback to finance

            # Get existing keywords
            existing_result = await session.execute(select(Keyword))
            existing_map = {}
            for row in existing_result.scalars().all():
                existing_map[row.keyword] = row

            for kw_data in keywords:
                kw_text = kw_data["keyword"].strip()
                ind_id = kw_data.get("industry_id") or etc_id

                if kw_text in existing_map:
                    # Update CPC and search volume if we have new data
                    existing = existing_map[kw_text]
                    changed = False

                    new_cpc = kw_data.get("naver_cpc")
                    if new_cpc and (not existing.naver_cpc or new_cpc != existing.naver_cpc):
                        existing.naver_cpc = new_cpc
                        changed = True

                    new_vol = kw_data.get("monthly_search_vol")
                    if new_vol and (not existing.monthly_search_vol or new_vol != existing.monthly_search_vol):
                        existing.monthly_search_vol = new_vol
                        changed = True

                    if changed:
                        updated += 1
                else:
                    session.add(Keyword(
                        industry_id=ind_id,
                        keyword=kw_text,
                        naver_cpc=kw_data.get("naver_cpc"),
                        monthly_search_vol=kw_data.get("monthly_search_vol"),
                    ))
                    added += 1

            if added > 0 or updated > 0:
                await session.commit()

        return added, updated


# ========================================================================
# Main
# ========================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="Naver Search Ads Keyword Planner Scraper",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="",
        help="Comma-separated category names to scrape (default: all)",
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Run browser in headful mode (visible)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without saving to DB",
    )
    parser.add_argument(
        "--id",
        type=str,
        default=DEFAULT_ID,
        help="Naver Search Ads login ID",
    )
    parser.add_argument(
        "--pw",
        type=str,
        default=DEFAULT_PW,
        help="Naver Search Ads login password",
    )
    parser.add_argument(
        "--customer-id",
        type=str,
        default=DEFAULT_CUSTOMER_ID,
        help="Naver Search Ads customer ID",
    )
    args = parser.parse_args()

    # Determine categories to process
    if args.categories:
        cat_names = [c.strip() for c in args.categories.split(",")]
        categories = {
            k: v for k, v in KEYWORD_CATEGORIES.items()
            if k in cat_names
        }
        if not categories:
            print(f"[ERROR] Unknown categories: {args.categories}")
            print(f"Available: {', '.join(KEYWORD_CATEGORIES.keys())}")
            return
    else:
        categories = KEYWORD_CATEGORIES

    # Check if REST API is available
    api_client = NaverKeywordAPI(
        customer_id=args.customer_id,
        api_key=os.getenv("NAVER_AD_API_KEY", ""),
        secret_key=os.getenv("NAVER_AD_SECRET_KEY", ""),
    )
    use_api = api_client.is_configured

    print("=" * 60)
    print("  Naver Keyword Planner Scraper")
    print(f"  Mode: {'REST API' if use_api else 'Browser'}")
    print(f"  Categories: {', '.join(categories.keys())}")
    if not use_api:
        print(f"  Headless: {not args.headful}")
    print(f"  Dry run: {args.dry_run}")
    print("=" * 60)

    all_results: list[dict] = []

    if use_api:
        # REST API mode (no browser needed)
        print("\n[1/2] Fetching keywords via REST API...")
        all_results = await api_client.search_all(categories)
        print(f"  Total: {len(all_results)} keywords")
    else:
        print("\n[!] REST API not configured (NAVER_AD_API_KEY/SECRET_KEY)")
        print("    Falling back to browser login mode...")
        print("    Tip: Set NAVER_AD_API_KEY and NAVER_AD_SECRET_KEY in .env")
        print("    Get them from: searchad.naver.com > Tools > API Manager\n")

        async with NaverKeywordScraper(
            naver_id=args.id,
            naver_pw=args.pw,
            customer_id=args.customer_id,
            headless=not args.headful,
            dry_run=args.dry_run,
        ) as scraper:
            # Login
            print("[1/3] Logging in to Naver Search Ads...")
            try:
                context = await scraper.login()
                print("  Login OK")
            except Exception as e:
                print(f"  Login FAILED: {str(e)[:200]}")
                print("  Tip: Try --headful to see the browser")
                return

            # Scrape each category
            print("\n[2/3] Searching keywords by category...")
            total_categories = len(categories)

            for idx, (cat_name, cat_config) in enumerate(categories.items(), 1):
                seeds = cat_config.get("seeds_kr", [])
                industry_id = cat_config.get("industry_id") or 1

                print(f"\n  [{idx}/{total_categories}] {cat_name} ({len(seeds)} seeds)")

                results = await scraper.search_keywords(
                    context, seeds, industry_id, cat_name,
                )

                if len(results) < 5:
                    logger.info("Few results, trying direct API...")
                    api_results = await scraper.try_direct_api(
                        context, seeds, industry_id,
                    )
                    existing_kws = {r["keyword"] for r in results}
                    for r in api_results:
                        if r["keyword"] not in existing_kws:
                            results.append(r)

                all_results.extend(results)
                print(f"    -> {len(results)} keywords collected")

                if idx < total_categories:
                    await asyncio.sleep(2)

            await context.close()

    # Results summary
    print("\n" + "=" * 60)
    print(f"  Total keywords collected: {len(all_results)}")

    if args.dry_run:
        print("\n  [DRY RUN] Sample results:")
        for kw in all_results[:20]:
            cpc = kw.get("naver_cpc") or "?"
            vol = kw.get("monthly_search_vol") or "?"
            print(f"    {kw['keyword']:30s}  CPC={cpc:>8}  Vol={vol:>10}")
        print(f"\n  ... and {max(0, len(all_results) - 20)} more")
    else:
        print("\n[3/3] Saving to database...")
        scraper_instance = NaverKeywordScraper(dry_run=False)
        added, updated = await scraper_instance.save_to_db(all_results)
        print(f"  Added: {added}, Updated: {updated}")

    # Also export to JSON for reference
    output_path = Path(_root) / "data" / "keyword_planner_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export_data = []
    for kw in all_results:
        export_data.append({
            "keyword": kw["keyword"],
            "industry_id": kw.get("industry_id"),
            "naver_cpc": kw.get("naver_cpc"),
            "monthly_search_vol": kw.get("monthly_search_vol"),
            "extra": kw.get("extra", {}),
        })
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    print(f"\n  Results exported to: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
