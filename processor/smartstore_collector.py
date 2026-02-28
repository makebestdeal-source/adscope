"""Smart Store meta-signal collector -- store homepage network interception.

Collects from Naver Smart Store / Brand Store homepages via JSON API capture:
  - Product list with review counts, ratings, prices, stock
  - Visit data (today / total)
  - Seller grade, category info
  - Aggregated store-level snapshot (top product as representative)

Strategy: navigate to store homepage (not product pages, which return 490).
The store homepage triggers JSON APIs (simple-products, best-products, visit)
that we intercept via Playwright network events.

Legal: Only public page numbers. No login, no full text storage.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select

from database import async_session
from database.models import Advertiser, SmartStoreSnapshot, SmartStoreTrackedProduct

logger = logging.getLogger(__name__)


def _extract_smartstore_urls(advertiser: Advertiser) -> list[str]:
    """Extract smartstore/brand store URLs from advertiser smartstore_url, website and official_channels."""
    urls = []
    _store_domains = ("smartstore.naver.com", "brand.naver.com")

    # Priority 1: dedicated smartstore_url column
    if getattr(advertiser, "smartstore_url", None):
        urls.append(advertiser.smartstore_url)

    if advertiser.website:
        for domain in _store_domains:
            if domain in advertiser.website:
                urls.append(advertiser.website)
                break

    channels = advertiser.official_channels or {}
    for key in ("smartstore", "naver_store", "shopping", "brand_store"):
        val = str(channels.get(key, ""))
        if val:
            for domain in _store_domains:
                if domain in val:
                    urls.append(val)
                    break

    return list(set(urls))


def _extract_store_name(url: str) -> str | None:
    """Extract store name from smartstore/brand store URL path."""
    match = re.search(r"(?:smartstore|brand)\.naver\.com/([^/?#]+)", url)
    return match.group(1) if match else None


def _parse_product_from_list(product: dict) -> dict:
    """Parse a single product from simple-products / best-products list."""
    out = {}
    out["product_name"] = product.get("name") or product.get("dispName")
    out["price"] = product.get("salePrice") or product.get("dispSalePrice")
    out["stock_quantity"] = product.get("stockQuantity")

    # reviewAmount is a nested dict with totalReviewCount, averageReviewScore
    review_amount = product.get("reviewAmount") or {}
    out["review_count"] = review_amount.get("totalReviewCount", 0) or 0
    out["avg_rating"] = review_amount.get("averageReviewScore") or review_amount.get("averageStarScore")

    out["purchase_cnt"] = (
        product.get("totalPurchaseCnt")
        or product.get("purchaseCnt")
        or product.get("cumulationSaleCount")
    )
    out["wishlist_count"] = product.get("wishCount") or product.get("zzimCount")
    out["qa_count"] = product.get("qnaCount") or product.get("totalQnaCount")

    # Category
    cat = product.get("category") or {}
    if isinstance(cat, dict):
        out["category_name"] = cat.get("wholeCategoryName") or cat.get("categoryName")

    # Channel / seller grade
    channel = product.get("channel") or {}
    if isinstance(channel, dict):
        out["seller_grade"] = channel.get("sellerGrade") or channel.get("grade")
        if channel.get("channelName"):
            out["store_name"] = channel["channelName"]

    # Product ID for URL construction
    out["product_no"] = product.get("productNo") or product.get("id")

    return out


async def _scrape_store_homepage(store_url: str) -> dict | None:
    """Scrape SmartStore homepage, capturing network JSON APIs.

    Returns a dict with aggregated store data:
      - products: list of parsed product dicts
      - visit_today / visit_total
      - store_name, seller_grade, channel_name
      - top_product: the best product data for snapshot
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error("[smartstore] playwright not installed")
        return None

    captured_json = {}

    async def _on_response(response):
        try:
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            resp_url = response.url
            body = await response.json()
            # Store by endpoint type
            if "simple-products" in resp_url:
                captured_json["simple_products"] = body
            elif "best-products" in resp_url:
                captured_json["best_products"] = body
            elif "/visit" in resp_url:
                captured_json["visit"] = body
            elif "category-products" in resp_url:
                captured_json["category_products"] = body
            elif "individual-info" in resp_url:
                captured_json["individual_info"] = body
        except Exception:
            pass

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = await browser.new_context(
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            await context.add_init_script(
                'Object.defineProperty(navigator, "webdriver", {get: () => undefined});'
            )
            page = await context.new_page()
            page.on("response", _on_response)

            try:
                await page.goto(store_url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)

                title = await page.title()
                if not title or "error" in title.lower():
                    logger.warning("[smartstore] store page error for %s: title=%s", store_url, title)
                    return None

                result = {
                    "store_title": title,
                    "products": [],
                    "visit_today": 0,
                    "visit_total": 0,
                    "store_name": None,
                    "seller_grade": None,
                }

                # Extract channel info from page HTML
                content = await page.content()
                grade_m = re.findall(r'"sellerGrade"\s*:\s*"([^"]+)"', content)
                if grade_m:
                    result["seller_grade"] = grade_m[0]
                name_m = re.findall(r'"channelName"\s*:\s*"([^"]+)"', content)
                if name_m:
                    result["store_name"] = name_m[0]

                # Visit data
                visit = captured_json.get("visit", {})
                if isinstance(visit, dict):
                    result["visit_today"] = visit.get("today", 0) or 0
                    result["visit_total"] = visit.get("total", 0) or 0

                # Products from simple-products (brand stores)
                sp = captured_json.get("simple_products")
                if isinstance(sp, list):
                    for prod in sp:
                        parsed = _parse_product_from_list(prod)
                        if parsed.get("product_name"):
                            result["products"].append(parsed)

                # Products from best-products (fallback)
                if not result["products"]:
                    bp = captured_json.get("best_products", {})
                    if isinstance(bp, dict):
                        for period in ("REALTIME", "DAILY", "WEEKLY", "MONTHLY"):
                            items = bp.get(period, [])
                            if isinstance(items, list):
                                for prod in items:
                                    if isinstance(prod, dict):
                                        parsed = _parse_product_from_list(prod)
                                        if parsed.get("product_name"):
                                            result["products"].append(parsed)
                                if result["products"]:
                                    break

                logger.debug(
                    "[smartstore] %s: title=%s, products=%d, visit_today=%d",
                    store_url, title, len(result["products"]), result["visit_today"],
                )
                return result

            finally:
                await context.close()
                await browser.close()

    except Exception as e:
        logger.warning("[smartstore] scrape error for %s: %s", store_url, e)
        return None


def _aggregate_store_data(store_data: dict, store_url: str) -> dict:
    """Aggregate store-level data from homepage scrape into snapshot fields.

    Strategy: pick the top product (by review count) as representative,
    but sum up total review counts across all products.
    """
    products = store_data.get("products", [])
    out = {
        "store_name": store_data.get("store_name") or store_data.get("store_title"),
        "seller_grade": store_data.get("seller_grade"),
        "visit_today": store_data.get("visit_today", 0),
        "visit_total": store_data.get("visit_total", 0),
    }

    if not products:
        # Even without products, visit data is useful
        return out

    # Aggregate across all products
    total_reviews = sum((p.get("review_count") or 0) for p in products)
    total_purchases = sum((p.get("purchase_cnt") or 0) for p in products)
    total_stock = sum((p.get("stock_quantity") or 0) for p in products)
    prices = [p["price"] for p in products if p.get("price")]
    avg_price = int(sum(prices) / len(prices)) if prices else None

    # Pick top product by review count for representative data
    top = max(products, key=lambda p: p.get("review_count") or 0)

    out.update({
        "product_name": top.get("product_name"),
        "price": top.get("price") or avg_price,
        "avg_price": avg_price,
        "review_count": total_reviews,
        "avg_rating": top.get("avg_rating"),
        "stock_quantity": total_stock,
        "purchase_cnt": total_purchases,
        "category_name": top.get("category_name"),
        "product_count": len(products),
        "product_url": store_url,
    })

    return out


def _estimate_sales_level(review_delta: int, price: int | None) -> str:
    """Estimate sales level from review delta and price."""
    if price and price > 0:
        est_daily_revenue = review_delta * 30 * (price or 10000)
        if est_daily_revenue >= 5_000_000:
            return "high"
        if est_daily_revenue >= 1_000_000:
            return "mid"
    elif review_delta >= 10:
        return "high"
    elif review_delta >= 3:
        return "mid"
    return "low"


async def collect_smartstore_signals(
    session=None,
    advertiser_ids: list[int] | None = None,
) -> dict:
    """Collect smartstore meta-signals for advertisers + tracked products.

    Returns: {"processed": N, "created": N, "skipped": N, "errors": N}
    """
    own_session = session is None
    if own_session:
        session = async_session()
        await session.__aenter__()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        yesterday = now - timedelta(days=1)

        created = 0
        skipped = 0
        errors = 0
        processed_count = 0

        # --- Part 1: Advertiser-based collection ---
        adv_query = select(Advertiser)
        if advertiser_ids:
            adv_query = adv_query.where(Advertiser.id.in_(advertiser_ids))

        result = await session.execute(adv_query)
        advertisers = result.scalars().all()

        for adv in advertisers:
            store_urls = _extract_smartstore_urls(adv)
            if not store_urls:
                continue

            processed_count += 1

            for url in store_urls[:3]:
                # Strip /products/... suffix -- navigate to store homepage
                store_home = re.sub(r"/products/.*$", "", url)

                store_data = await _scrape_store_homepage(store_home)
                if store_data is None:
                    errors += 1
                    continue

                agg = _aggregate_store_data(store_data, store_home)
                if not agg.get("product_name") and not agg.get("visit_today"):
                    skipped += 1
                    continue

                snap = await _save_snapshot(
                    session, agg, adv.id, None, yesterday, now,
                )
                if snap:
                    created += 1

        # --- Part 2: User-tracked products ---
        tracked_q = select(SmartStoreTrackedProduct).where(
            SmartStoreTrackedProduct.is_active == True  # noqa: E712
        )
        tracked_result = await session.execute(tracked_q)
        tracked_products = tracked_result.scalars().all()

        for tp in tracked_products:
            processed_count += 1
            # For tracked products, try store homepage
            store_home = re.sub(r"/products/.*$", "", tp.product_url)
            store_data = await _scrape_store_homepage(store_home)
            if store_data is None:
                errors += 1
                continue

            agg = _aggregate_store_data(store_data, store_home)
            snap = await _save_snapshot(
                session, agg, tp.advertiser_id or 0, tp.id, yesterday, now,
            )
            if snap:
                created += 1
                if snap.product_name and not tp.product_name:
                    tp.product_name = snap.product_name
                if snap.store_name and not tp.store_name:
                    tp.store_name = snap.store_name

        await session.commit()
        logger.info(
            "[smartstore] processed=%d created=%d skipped=%d errors=%d",
            processed_count, created, skipped, errors,
        )
        return {
            "processed": processed_count,
            "created": created,
            "skipped": skipped,
            "errors": errors,
        }

    finally:
        if own_session:
            await session.__aexit__(None, None, None)


async def _save_snapshot(
    session, agg: dict, advertiser_id: int, tracked_product_id: int | None,
    yesterday: datetime, now: datetime,
) -> SmartStoreSnapshot | None:
    """Save aggregated store data as a SmartStoreSnapshot."""
    product_url = agg.get("product_url", "")
    review_count = agg.get("review_count", 0) or 0
    purchase_cnt = agg.get("purchase_cnt")

    # Get previous snapshot for delta calculations
    prev_snap = (
        await session.execute(
            select(SmartStoreSnapshot)
            .where(
                and_(
                    SmartStoreSnapshot.advertiser_id == advertiser_id,
                    SmartStoreSnapshot.captured_at >= yesterday,
                )
            )
            .order_by(SmartStoreSnapshot.captured_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    review_delta = 0
    if prev_snap and prev_snap.review_count and review_count:
        review_delta = max(0, review_count - prev_snap.review_count)

    purchase_cnt_delta = 0
    if prev_snap and prev_snap.purchase_cnt and purchase_cnt:
        purchase_cnt_delta = max(0, purchase_cnt - prev_snap.purchase_cnt)

    price = agg.get("price")
    sales_level = _estimate_sales_level(review_delta, price)

    snap = SmartStoreSnapshot(
        advertiser_id=advertiser_id,
        tracked_product_id=tracked_product_id,
        store_name=agg.get("store_name"),
        product_url=product_url,
        product_name=agg.get("product_name"),
        review_count=review_count,
        review_delta=review_delta,
        avg_rating=agg.get("avg_rating"),
        price=price,
        discount_pct=0,
        ranking_position=None,
        ranking_category=agg.get("category_name"),
        wishlist_count=None,
        qa_count=None,
        estimated_sales_level=sales_level,
        stock_quantity=agg.get("stock_quantity"),
        purchase_cnt=purchase_cnt,
        purchase_cnt_delta=purchase_cnt_delta,
        category_name=agg.get("category_name"),
        seller_grade=agg.get("seller_grade"),
        captured_at=now,
    )
    session.add(snap)
    return snap
