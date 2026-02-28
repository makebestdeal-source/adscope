"""Naver Shopping top results -> SmartStore URL discovery + Advertiser matching.

For each major Naver Shopping category, searches search.naver.com?where=shopping,
extracts SmartStore/brand store URLs from organic + ad results, and maps them
to existing advertisers in DB by brand name fuzzy matching.

Usage:
    python scripts/collect_smartstore_top.py              # all categories
    python scripts/collect_smartstore_top.py --dry-run    # preview only, no DB write
    python scripts/collect_smartstore_top.py --categories "패션의류,뷰티"
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

# ── Category -> search queries mapping ──
CATEGORY_QUERIES: dict[str, list[str]] = {
    "패션의류": [
        "여성원피스", "남성자켓", "니트", "청바지", "블라우스",
        "맨투맨", "코트", "패딩", "티셔츠 인기",
    ],
    "뷰티": [
        "스킨케어", "선크림", "파운데이션", "클렌징", "마스크팩",
        "립스틱", "샴푸 인기", "향수 베스트",
    ],
    "식품": [
        "건강식품", "다이어트식품", "커피 원두", "견과류", "밀키트",
        "프로틴", "비타민", "홍삼",
    ],
    "생활건강": [
        "영양제", "유산균", "칫솔 전동", "세탁세제", "섬유유연제",
        "핸드워시", "방향제", "물티슈",
    ],
    "가전디지털": [
        "노트북", "무선이어폰", "공기청정기", "로봇청소기", "모니터",
        "키보드 기계식", "태블릿",
    ],
    "스포츠레저": [
        "러닝화", "요가매트", "등산화", "골프용품", "캠핑텐트",
        "자전거", "수영복",
    ],
    "출산육아": [
        "기저귀", "분유", "유모차", "아기띠", "유아식기",
        "젖병", "이유식",
    ],
    "반려동물": [
        "강아지사료", "고양이간식", "펫샴푸", "고양이모래",
        "강아지간식", "펫용품",
    ],
    "가구인테리어": [
        "침대 매트리스", "소파", "책상", "의자 사무용", "커튼",
        "조명 인테리어",
    ],
    "잡화": [
        "가방 여성", "지갑 남성", "시계", "선글라스", "벨트",
    ],
}

# SmartStore + BrandStore URL patterns
# Store names: alphanumeric, hyphens, underscores only
_STORE_PATTERNS = [
    re.compile(r"https?://smartstore\.naver\.com/([a-zA-Z0-9_-]+)"),
    re.compile(r"https?://brand\.naver\.com/([a-zA-Z0-9_-]+)"),
]

_SKIP_NAMES = frozenset([
    "products", "category", "search", "best", "live",
    "main", "inflow", "gate", "login", "join", "seller",
    "stores", "home", "checkout", "cart", "order", "member",
])


def _extract_store_name_from_url(url: str) -> tuple[str | None, str | None]:
    """Extract (store_name, store_base_url) from a URL."""
    for pat in _STORE_PATTERNS:
        m = pat.search(url)
        if m:
            store_name = m.group(1)
            if store_name in _SKIP_NAMES:
                continue
            base = url[:m.end()]
            return store_name, base
    return None, None


async def _scrape_shopping_results(query: str) -> list[dict]:
    """Search Naver Shopping and extract store URLs from results.

    Three extraction methods:
    1. JSON API response capture (most reliable)
    2. Rendered page DOM link extraction
    3. Raw HTML regex fallback
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("playwright not installed")
        return []

    results: list[dict] = []
    captured_json: list[dict] = []
    seen_stores: set[str] = set()

    async def _on_response(response):
        """Capture JSON API responses from Naver Shopping."""
        try:
            if response.status != 200:
                return
            resp_url = response.url
            ct = response.headers.get("content-type", "")

            # Capture JSON from shopping/search APIs
            if "json" in ct:
                if ("shopping" in resp_url or "shopsearch" in resp_url
                        or "search.naver" in resp_url):
                    body = await response.text()
                    if body and len(body) > 100:
                        try:
                            data = json.loads(body)
                            captured_json.append(data)
                        except Exception:
                            pass
        except Exception:
            pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.on("response", _on_response)

            url = f"https://search.naver.com/search.naver?where=shopping&query={quote(query)}"
            logger.info("[smartstore_top] searching: {}", query)

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)

                # Scroll to trigger lazy-loaded content
                for _ in range(4):
                    await page.evaluate("window.scrollBy(0, 1000)")
                    await page.wait_for_timeout(500)

                # Method 1: Extract from captured JSON
                for data in captured_json:
                    _extract_from_json(data, results, seen_stores)

                json_count = len(results)

                # Method 2: Extract from live DOM
                page_stores = await page.evaluate("""() => {
                    const results = [];
                    const seen = new Set();
                    const SKIP = new Set([
                        'products','category','search','best','live',
                        'main','inflow','gate','login','join','seller',
                        'stores','home','checkout','cart','order','member'
                    ]);

                    // All links
                    for (const a of document.querySelectorAll('a[href]')) {
                        const href = a.getAttribute('href') || '';
                        const m = href.match(
                            /https?:\\/\\/(smartstore|brand)\\.naver\\.com\\/([a-zA-Z0-9_-]+)/
                        );
                        if (!m) continue;
                        const sn = m[2];
                        if (SKIP.has(sn) || seen.has(sn)) continue;
                        seen.add(sn);

                        let mallName = '';
                        let title = '';
                        const parent = a.closest(
                            'li, [class*="item"], [class*="product"], [class*="card"], [class*="_product"]'
                        );
                        if (parent) {
                            const mallEl = parent.querySelector(
                                '[class*="mall"], [class*="store"], [class*="seller"], ' +
                                '[class*="shop"], [class*="brand"], [class*="source"]'
                            );
                            if (mallEl) mallName = mallEl.textContent.trim().substring(0, 100);
                            const titleEl = parent.querySelector(
                                '[class*="tit"], [class*="name"], [class*="title"]'
                            );
                            if (titleEl) title = titleEl.textContent.trim().substring(0, 200);
                        }

                        results.push({
                            store_name: sn,
                            store_url: 'https://' + m[1] + '.naver.com/' + sn,
                            mall_name: mallName || sn,
                            product_title: title,
                        });
                    }

                    // data attributes
                    for (const el of document.querySelectorAll('[data-mall-url],[data-shop-url]')) {
                        const url = el.getAttribute('data-mall-url')
                                 || el.getAttribute('data-shop-url') || '';
                        const m = url.match(
                            /https?:\\/\\/(smartstore|brand)\\.naver\\.com\\/([a-zA-Z0-9_-]+)/
                        );
                        if (!m) continue;
                        const sn = m[2];
                        if (SKIP.has(sn) || seen.has(sn)) continue;
                        seen.add(sn);
                        results.push({
                            store_name: sn,
                            store_url: url,
                            mall_name: el.getAttribute('data-mall-name') || sn,
                            product_title: '',
                        });
                    }

                    return results;
                }""")

                for item in page_stores:
                    sn = item["store_name"]
                    if sn not in seen_stores:
                        seen_stores.add(sn)
                        results.append(item)

                dom_count = len(results) - json_count

                # Method 3: Raw HTML regex fallback
                if len(results) < 5:
                    html = await page.content()
                    _extract_from_html(html, results, seen_stores)

                html_count = len(results) - json_count - dom_count

                logger.info(
                    "[smartstore_top] '{}' -> {} stores (json={}, dom={}, html={})",
                    query, len(results), json_count, dom_count, html_count,
                )

            finally:
                await page.close()
                await context.close()
                await browser.close()

    except Exception as e:
        logger.warning("[smartstore_top] error searching '{}': {}", query, e)

    return results


def _extract_from_json(data, results: list, seen: set):
    """Recursively extract store info from Naver Shopping API JSON."""
    if isinstance(data, list):
        for item in data:
            _extract_from_json(item, results, seen)
        return
    if not isinstance(data, dict):
        return

    # Check if this dict has mall/store info
    store_url = ""
    store_name = ""
    mall_name = ""

    # Common JSON keys for store URLs in Naver Shopping API
    for url_key in ("mallUrl", "mall_url", "shopUrl", "storeUrl",
                    "smartstoreUrl", "brandUrl", "mallProductUrl",
                    "adcrUrl", "crUrl", "link", "url",
                    "lowMallUrl", "productUrl"):
        val = data.get(url_key, "")
        if not val or not isinstance(val, str):
            continue
        for pat in _STORE_PATTERNS:
            m = pat.search(val)
            if m:
                sn = m.group(1)
                if sn not in _SKIP_NAMES:
                    store_name = sn
                    store_url = f"https://{pat.pattern.split('//')[1].split('\\.')[0]}.naver.com/{sn}"
                    break
        if store_url:
            break

    # Common JSON keys for mall/store display names
    for name_key in ("mallName", "mall_name", "mallNm", "shopName",
                     "storeName", "brandName", "sellerName", "seller",
                     "lowMallName", "mallDisplayName"):
        val = data.get(name_key, "")
        if val and isinstance(val, str) and len(val.strip()) > 0:
            mall_name = val.strip()
            break

    if store_name and store_name not in seen:
        seen.add(store_name)
        if not mall_name:
            mall_name = store_name
        title = (data.get("productTitle", "") or data.get("title", "")
                 or data.get("name", "") or data.get("productName", ""))
        if title:
            title = re.sub(r"<[^>]+>", "", str(title)).strip()[:200]
        results.append({
            "store_name": store_name,
            "store_url": store_url,
            "mall_name": mall_name,
            "product_title": title or "",
        })

    # Recurse into nested structures
    for key, val in data.items():
        if isinstance(val, (dict, list)):
            _extract_from_json(val, results, seen)


def _extract_from_html(html: str, results: list, seen: set):
    """Fallback: regex extraction from raw HTML."""
    for pat in _STORE_PATTERNS:
        for m in pat.finditer(html):
            store_name = m.group(1)
            if store_name in _SKIP_NAMES or store_name in seen:
                continue
            seen.add(store_name)
            results.append({
                "store_name": store_name,
                "store_url": html[m.start():m.end()],
                "mall_name": store_name,
                "product_title": "",
            })


def _normalize_name(name: str) -> str:
    """Normalize a brand/store name for fuzzy matching."""
    name = name.lower().strip()
    for suffix in ["스토어", "몰", "공식", "official", "shop", "store", "mall"]:
        name = name.replace(suffix, "")
    name = re.sub(r"[^a-z0-9가-힣]", "", name)
    return name


def _name_match_score(store_name: str, advertiser_name: str, aliases: list) -> float:
    """Calculate match score between store name and advertiser."""
    norm_store = _normalize_name(store_name)
    if not norm_store or len(norm_store) < 2:
        return 0.0

    norm_adv = _normalize_name(advertiser_name)
    if not norm_adv or len(norm_adv) < 2:
        return 0.0

    # Exact match
    if norm_store == norm_adv:
        return 1.0

    # Substring match - only if the shorter string is at least 4 chars
    # to avoid false positives with short names
    shorter = min(len(norm_store), len(norm_adv))
    if shorter >= 4 and (norm_store in norm_adv or norm_adv in norm_store):
        # Penalize if length ratio is too different (e.g. "lg" in "lgcarepet")
        ratio = shorter / max(len(norm_store), len(norm_adv))
        if ratio >= 0.5:
            return 0.85
        elif ratio >= 0.3:
            return 0.75

    # Check aliases
    for alias in (aliases or []):
        norm_alias = _normalize_name(str(alias))
        if not norm_alias or len(norm_alias) < 2:
            continue
        if norm_store == norm_alias:
            return 1.0
        shorter_a = min(len(norm_store), len(norm_alias))
        if shorter_a >= 4 and (norm_store in norm_alias or norm_alias in norm_store):
            ratio = shorter_a / max(len(norm_store), len(norm_alias))
            if ratio >= 0.5:
                return 0.85

    # Jaccard bigram similarity
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s)-1)) if len(s) >= 2 else {s}

    bg_store = bigrams(norm_store)
    bg_adv = bigrams(norm_adv)
    if bg_store and bg_adv:
        jaccard = len(bg_store & bg_adv) / len(bg_store | bg_adv)
        if jaccard > 0.6:
            return jaccard * 0.8

    return 0.0


async def main():
    parser = argparse.ArgumentParser(description="Collect top SmartStore URLs from Naver Shopping")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    parser.add_argument("--categories", type=str, default="",
                        help="Comma-separated category names (default: all)")
    parser.add_argument("--max-queries", type=int, default=5,
                        help="Max queries per category (default: 5)")
    parser.add_argument("--match-threshold", type=float, default=0.7,
                        help="Minimum name match score (default: 0.7)")
    args = parser.parse_args()

    if args.categories:
        selected = [c.strip() for c in args.categories.split(",")]
        cats = {k: v for k, v in CATEGORY_QUERIES.items() if k in selected}
        if not cats:
            logger.error("No matching categories found. Available: {}",
                         ", ".join(CATEGORY_QUERIES.keys()))
            return
    else:
        cats = CATEGORY_QUERIES

    # Phase 1: Collect store URLs
    all_stores: dict[str, dict] = {}

    for category, queries in cats.items():
        logger.info("=== Category: {} ({} queries) ===", category, len(queries[:args.max_queries]))
        for query in queries[:args.max_queries]:
            stores = await _scrape_shopping_results(query)
            for s in stores:
                sn = s["store_name"]
                if sn not in all_stores:
                    all_stores[sn] = {**s, "category": category, "queries": [query]}
                else:
                    all_stores[sn]["queries"].append(query)
            await asyncio.sleep(2)

    logger.info(
        "Phase 1 complete: {} unique stores from {} categories",
        len(all_stores), len(cats),
    )

    if not all_stores:
        logger.warning("No stores found. Exiting.")
        return

    # Phase 2: Match with DB advertisers
    from database import async_session, init_db
    from database.models import Advertiser
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    await init_db()

    async with async_session() as session:
        result = await session.execute(select(Advertiser))
        advertisers = result.scalars().all()
        logger.info("Loaded {} advertisers from DB", len(advertisers))

        adv_with_store = 0
        adv_without_store = 0
        for adv in advertisers:
            has_store = False
            if adv.website and "smartstore.naver.com" in (adv.website or ""):
                has_store = True
            channels = adv.official_channels or {}
            for key in ("smartstore", "naver_store", "shopping"):
                if key in channels and "smartstore.naver.com" in str(channels.get(key, "")):
                    has_store = True
            if has_store:
                adv_with_store += 1
            else:
                adv_without_store += 1

        logger.info(
            "Advertisers with SmartStore: {} | without: {}",
            adv_with_store, adv_without_store,
        )

        matched = 0
        new_stores_set = 0
        already_has = 0
        unmatched_stores: list[dict] = []

        for store_name, store_info in all_stores.items():
            mall_name = store_info.get("mall_name", "") or store_name
            store_url = store_info["store_url"]

            best_adv = None
            best_score = 0.0

            for adv in advertisers:
                score1 = _name_match_score(store_name, adv.name, adv.aliases)
                score2 = _name_match_score(mall_name, adv.name, adv.aliases) if mall_name != store_name else 0.0
                score3 = 0.0
                if adv.brand_name:
                    score3 = max(
                        _name_match_score(store_name, adv.brand_name, []),
                        _name_match_score(mall_name, adv.brand_name, []) if mall_name != store_name else 0.0,
                    )
                score = max(score1, score2, score3)
                if score > best_score:
                    best_score = score
                    best_adv = adv

            if best_score >= args.match_threshold and best_adv:
                existing_urls = []
                if best_adv.website and "smartstore.naver.com" in (best_adv.website or ""):
                    existing_urls.append(best_adv.website)
                channels = best_adv.official_channels or {}
                for key in ("smartstore", "naver_store", "shopping"):
                    val = channels.get(key, "")
                    if val and "naver.com" in str(val):
                        existing_urls.append(str(val))

                if any(store_name in eu for eu in existing_urls):
                    already_has += 1
                    continue

                matched += 1
                logger.info(
                    "  [match] {} -> {} (score={:.2f}) url={}",
                    store_name, best_adv.name, best_score, store_url,
                )

                if not args.dry_run:
                    channels = dict(best_adv.official_channels or {})
                    channels["smartstore"] = store_url
                    best_adv.official_channels = channels
                    flag_modified(best_adv, "official_channels")
                    if not best_adv.website:
                        best_adv.website = store_url
                    new_stores_set += 1
            else:
                unmatched_stores.append({
                    "store_name": store_name,
                    "mall_name": mall_name,
                    "store_url": store_url,
                    "category": store_info.get("category", ""),
                    "best_match": best_adv.name if best_adv else "none",
                    "best_score": best_score,
                })

        if not args.dry_run:
            await session.commit()

        logger.info("")
        logger.info("=== Summary ===")
        logger.info("Total unique stores discovered: {}", len(all_stores))
        logger.info("Matched to advertisers: {}", matched)
        logger.info("Already had store URL: {}", already_has)
        logger.info("Unmatched stores: {}", len(unmatched_stores))
        if not args.dry_run:
            logger.info("DB updated: {} advertisers got new smartstore URL", new_stores_set)
        else:
            logger.info("[DRY RUN] No DB changes made")

        if unmatched_stores:
            logger.info("")
            logger.info("=== Top unmatched stores (for manual review) ===")
            for s in sorted(unmatched_stores,
                            key=lambda x: x.get("best_score", 0), reverse=True)[:30]:
                logger.info(
                    "  {} | mall={} | cat={} | best_match={}({:.2f}) | {}",
                    s["store_name"], s["mall_name"], s["category"],
                    s["best_match"], s["best_score"], s["store_url"],
                )


if __name__ == "__main__":
    asyncio.run(main())
