"""Shopping analytics API -- insights from smartstore product data."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from database.models import SmartStoreSnapshot, ShoppingKeyword, Advertiser, User

router = APIRouter(
    prefix="/api/shopping",
    tags=["shopping-analytics"],
    dependencies=[Depends(get_current_user)],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ranking_category stores the search keyword used to discover the product.
# category_name uses " > " as separator (e.g. "식품/건강 > 즉석밥 > 일반즉석밥").
# We extract the top-level category via SQL substr.

_TOP_CATEGORY_EXPR = func.substr(
    SmartStoreSnapshot.category_name,
    1,
    func.instr(SmartStoreSnapshot.category_name, " > ") - 1,
)

# When category_name has no " > " separator, instr returns 0 and substr
# would return empty string.  Use CASE to fall back to full category_name.
TOP_CATEGORY = case(
    (func.instr(SmartStoreSnapshot.category_name, " > ") > 0, _TOP_CATEGORY_EXPR),
    else_=SmartStoreSnapshot.category_name,
).label("top_category")

# Price distribution bucket ranges
PRICE_RANGES = [
    (0, 10_000),
    (10_000, 30_000),
    (30_000, 50_000),
    (50_000, 100_000),
    (100_000, 300_000),
    (300_000, 500_000),
    (500_000, 1_000_000),
    (1_000_000, None),  # 1M+
]


def _price_distribution_cases():
    """Build a list of (label, case_expr) for price buckets."""
    cases = []
    for low, high in PRICE_RANGES:
        if high is None:
            label = f"{low:,}+"
            cond = SmartStoreSnapshot.price >= low
        else:
            label = f"{low:,}-{high:,}"
            cond = (SmartStoreSnapshot.price >= low) & (SmartStoreSnapshot.price < high)
        cases.append((label, cond))
    return cases


async def _latest_date(db: AsyncSession):
    """Return the most recent captured_at date in smartstore_snapshots."""
    result = await db.execute(
        select(func.max(func.date(SmartStoreSnapshot.captured_at)))
    )
    return result.scalar()


# ---------------------------------------------------------------------------
# 1. GET /api/shopping/summary
# ---------------------------------------------------------------------------
@router.get("/summary")
async def shopping_summary(
    db: AsyncSession = Depends(get_db),
):
    """Overall shopping data summary."""
    latest_date = await _latest_date(db)
    if not latest_date:
        return {
            "total_products": 0,
            "total_stores": 0,
            "total_keywords": 0,
            "total_categories": 0,
            "avg_price": 0,
            "date_range": {"from": None, "to": None},
            "category_distribution": [],
        }

    # Basic stats from snapshots
    stats_q = select(
        func.count(SmartStoreSnapshot.id).label("total_products"),
        func.count(func.distinct(SmartStoreSnapshot.store_name)).label("total_stores"),
        func.avg(SmartStoreSnapshot.price).label("avg_price"),
        func.min(func.date(SmartStoreSnapshot.captured_at)).label("date_from"),
        func.max(func.date(SmartStoreSnapshot.captured_at)).label("date_to"),
    )
    stats = (await db.execute(stats_q)).one()

    # Keyword count from shopping_keywords
    kw_count = (await db.execute(
        select(func.count(ShoppingKeyword.id))
    )).scalar() or 0

    # Category distribution (top-level)
    cat_q = (
        select(
            TOP_CATEGORY,
            func.count(SmartStoreSnapshot.id).label("count"),
            func.round(func.avg(SmartStoreSnapshot.price)).label("avg_price"),
        )
        .where(SmartStoreSnapshot.category_name.isnot(None))
        .group_by(literal_column("top_category"))
        .order_by(func.count(SmartStoreSnapshot.id).desc())
    )
    cat_rows = (await db.execute(cat_q)).all()

    return {
        "total_products": stats.total_products,
        "total_stores": stats.total_stores,
        "total_keywords": kw_count,
        "total_categories": len(cat_rows),
        "avg_price": int(stats.avg_price) if stats.avg_price else 0,
        "date_range": {
            "from": stats.date_from,
            "to": stats.date_to,
        },
        "category_distribution": [
            {
                "category": row.top_category or "Unknown",
                "count": row.count,
                "avg_price": int(row.avg_price) if row.avg_price else 0,
            }
            for row in cat_rows
        ],
    }


# ---------------------------------------------------------------------------
# 2. GET /api/shopping/keywords
# ---------------------------------------------------------------------------
@router.get("/keywords")
async def shopping_keywords(
    category: str = Query("", description="Filter by shopping_keywords.category"),
    sort: str = Query("product_count", description="Sort field: product_count|price_avg|store_count|search_volume"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Per-keyword analysis joining shopping_keywords with smartstore snapshots."""
    # Subquery: aggregate snapshots by ranking_category (= search keyword)
    snap_sub = (
        select(
            SmartStoreSnapshot.ranking_category.label("keyword"),
            func.count(SmartStoreSnapshot.id).label("product_count"),
            func.round(func.avg(SmartStoreSnapshot.price)).label("avg_price"),
            func.min(SmartStoreSnapshot.price).label("min_price"),
            func.max(SmartStoreSnapshot.price).label("max_price"),
            func.count(func.distinct(SmartStoreSnapshot.store_name)).label("store_count"),
        )
        .where(SmartStoreSnapshot.ranking_category.isnot(None))
        .group_by(SmartStoreSnapshot.ranking_category)
        .subquery()
    )

    # Join with shopping_keywords for metadata (category, search_volume)
    q = (
        select(
            snap_sub.c.keyword,
            ShoppingKeyword.category,
            snap_sub.c.product_count,
            snap_sub.c.avg_price,
            snap_sub.c.min_price,
            snap_sub.c.max_price,
            snap_sub.c.store_count,
            ShoppingKeyword.monthly_search_vol.label("search_volume"),
        )
        .outerjoin(ShoppingKeyword, ShoppingKeyword.keyword == snap_sub.c.keyword)
    )

    if category:
        q = q.where(ShoppingKeyword.category == category)

    # Sorting
    sort_map = {
        "product_count": snap_sub.c.product_count.desc(),
        "price_avg": snap_sub.c.avg_price.desc(),
        "store_count": snap_sub.c.store_count.desc(),
        "search_volume": ShoppingKeyword.monthly_search_vol.desc().nulls_last(),
    }
    q = q.order_by(sort_map.get(sort, snap_sub.c.product_count.desc()))
    q = q.limit(limit)

    rows = (await db.execute(q)).all()

    return {
        "keywords": [
            {
                "keyword": row.keyword,
                "category": row.category,
                "product_count": row.product_count,
                "avg_price": int(row.avg_price) if row.avg_price else 0,
                "min_price": row.min_price,
                "max_price": row.max_price,
                "store_count": row.store_count,
                "search_volume": row.search_volume,
            }
            for row in rows
        ],
    }


# ---------------------------------------------------------------------------
# 3. GET /api/shopping/category/{category_name}
# ---------------------------------------------------------------------------
@router.get("/category/{category_name}")
async def shopping_category_detail(
    category_name: str,
    limit: int = Query(20, ge=1, le=100, description="Top stores limit"),
    db: AsyncSession = Depends(get_db),
):
    """Detailed analysis for a top-level category."""
    # Match top-level category: category_name starts with the given name
    cat_filter = SmartStoreSnapshot.category_name.like(f"{category_name}%")

    # Basic stats
    stats_q = select(
        func.count(SmartStoreSnapshot.id).label("total_products"),
        func.count(func.distinct(SmartStoreSnapshot.store_name)).label("total_stores"),
        func.round(func.avg(SmartStoreSnapshot.price)).label("avg"),
        func.min(SmartStoreSnapshot.price).label("min"),
        func.max(SmartStoreSnapshot.price).label("max"),
    ).where(cat_filter, SmartStoreSnapshot.price.isnot(None))
    stats = (await db.execute(stats_q)).one()

    if stats.total_products == 0:
        raise HTTPException(404, f"Category '{category_name}' not found")

    # Median price (SQLite doesn't have PERCENTILE, use subquery)
    median_q = (
        select(SmartStoreSnapshot.price)
        .where(cat_filter, SmartStoreSnapshot.price.isnot(None))
        .order_by(SmartStoreSnapshot.price)
        .limit(1)
        .offset(stats.total_products // 2)
    )
    median_price = (await db.execute(median_q)).scalar() or 0

    # Price distribution
    price_dist = []
    for label, cond in _price_distribution_cases():
        cnt_q = select(func.count(SmartStoreSnapshot.id)).where(
            cat_filter,
            SmartStoreSnapshot.price.isnot(None),
            cond,
        )
        cnt = (await db.execute(cnt_q)).scalar() or 0
        if cnt > 0:
            price_dist.append({"range": label, "count": cnt})

    # Top stores
    stores_q = (
        select(
            SmartStoreSnapshot.store_name,
            func.count(SmartStoreSnapshot.id).label("product_count"),
            func.round(func.avg(SmartStoreSnapshot.price)).label("avg_price"),
        )
        .where(cat_filter, SmartStoreSnapshot.store_name.isnot(None))
        .group_by(SmartStoreSnapshot.store_name)
        .order_by(func.count(SmartStoreSnapshot.id).desc())
        .limit(limit)
    )
    store_rows = (await db.execute(stores_q)).all()

    return {
        "category": category_name,
        "total_products": stats.total_products,
        "total_stores": stats.total_stores,
        "price_stats": {
            "avg": int(stats.avg) if stats.avg else 0,
            "median": median_price,
            "min": stats.min,
            "max": stats.max,
        },
        "price_distribution": price_dist,
        "top_stores": [
            {
                "store_name": row.store_name,
                "product_count": row.product_count,
                "avg_price": int(row.avg_price) if row.avg_price else 0,
            }
            for row in store_rows
        ],
    }


# ---------------------------------------------------------------------------
# 4. GET /api/shopping/store/{store_name}
# ---------------------------------------------------------------------------
@router.get("/store/{store_name}")
async def shopping_store_detail(
    store_name: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Store-level analysis."""
    store_filter = SmartStoreSnapshot.store_name == store_name

    # Basic stats
    stats_q = select(
        func.count(SmartStoreSnapshot.id).label("total_products"),
        func.round(func.avg(SmartStoreSnapshot.price)).label("avg_price"),
    ).where(store_filter)
    stats = (await db.execute(stats_q)).one()

    if stats.total_products == 0:
        raise HTTPException(404, f"Store '{store_name}' not found")

    # Categories this store operates in (top-level)
    cat_q = (
        select(func.distinct(TOP_CATEGORY))
        .where(store_filter, SmartStoreSnapshot.category_name.isnot(None))
    )
    cat_rows = (await db.execute(cat_q)).scalars().all()

    # Products list
    products_q = (
        select(
            SmartStoreSnapshot.product_name,
            SmartStoreSnapshot.price,
            SmartStoreSnapshot.category_name,
            SmartStoreSnapshot.product_url,
        )
        .where(store_filter)
        .order_by(SmartStoreSnapshot.price.desc().nulls_last())
        .limit(limit)
    )
    product_rows = (await db.execute(products_q)).all()

    return {
        "store_name": store_name,
        "total_products": stats.total_products,
        "categories": [c for c in cat_rows if c],
        "avg_price": int(stats.avg_price) if stats.avg_price else 0,
        "products": [
            {
                "product_name": row.product_name,
                "price": row.price,
                "category": row.category_name,
                "product_url": row.product_url,
            }
            for row in product_rows
        ],
    }


# ---------------------------------------------------------------------------
# 5. GET /api/shopping/price-range
# ---------------------------------------------------------------------------
@router.get("/price-range")
async def shopping_price_range(
    min_price: int = Query(0, ge=0, alias="min"),
    max_price: int = Query(1_000_000, ge=0, alias="max"),
    category: str = Query("", description="Top-level category filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Search products by price range with optional category filter."""
    conditions = [
        SmartStoreSnapshot.price.isnot(None),
        SmartStoreSnapshot.price >= min_price,
        SmartStoreSnapshot.price <= max_price,
    ]
    if category:
        conditions.append(SmartStoreSnapshot.category_name.like(f"{category}%"))

    total_q = select(func.count(SmartStoreSnapshot.id)).where(*conditions)
    total = (await db.execute(total_q)).scalar() or 0

    products_q = (
        select(
            SmartStoreSnapshot.product_name,
            SmartStoreSnapshot.store_name,
            SmartStoreSnapshot.price,
            SmartStoreSnapshot.category_name,
            SmartStoreSnapshot.product_url,
        )
        .where(*conditions)
        .order_by(SmartStoreSnapshot.price.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(products_q)).all()

    return {
        "total": total,
        "products": [
            {
                "product_name": row.product_name,
                "store_name": row.store_name,
                "price": row.price,
                "category": row.category_name,
                "product_url": row.product_url,
            }
            for row in rows
        ],
    }


# ---------------------------------------------------------------------------
# 6. GET /api/shopping/competition
# ---------------------------------------------------------------------------
@router.get("/competition")
async def shopping_competition(
    keyword: str = Query(..., description="Search keyword to analyze"),
    db: AsyncSession = Depends(get_db),
):
    """Competition analysis for a specific keyword (ranking_category)."""
    kw_filter = SmartStoreSnapshot.ranking_category == keyword

    # Overall stats
    stats_q = select(
        func.count(SmartStoreSnapshot.id).label("total_products"),
        func.round(func.avg(SmartStoreSnapshot.price)).label("avg_price"),
        func.min(SmartStoreSnapshot.price).label("min_price"),
        func.max(SmartStoreSnapshot.price).label("max_price"),
    ).where(kw_filter, SmartStoreSnapshot.price.isnot(None))
    stats = (await db.execute(stats_q)).one()

    if stats.total_products == 0:
        raise HTTPException(404, f"No products found for keyword '{keyword}'")

    # Per-store breakdown
    stores_q = (
        select(
            SmartStoreSnapshot.store_name,
            func.count(SmartStoreSnapshot.id).label("product_count"),
            func.min(SmartStoreSnapshot.price).label("min_price"),
            func.round(func.avg(SmartStoreSnapshot.price)).label("avg_price"),
        )
        .where(kw_filter, SmartStoreSnapshot.store_name.isnot(None))
        .group_by(SmartStoreSnapshot.store_name)
        .order_by(func.count(SmartStoreSnapshot.id).desc())
        .limit(50)
    )
    store_rows = (await db.execute(stores_q)).all()

    # Price distribution
    price_dist = []
    for label, cond in _price_distribution_cases():
        cnt_q = select(func.count(SmartStoreSnapshot.id)).where(
            kw_filter,
            SmartStoreSnapshot.price.isnot(None),
            cond,
        )
        cnt = (await db.execute(cnt_q)).scalar() or 0
        if cnt > 0:
            price_dist.append({"range": label, "count": cnt})

    return {
        "keyword": keyword,
        "total_products": stats.total_products,
        "avg_price": int(stats.avg_price) if stats.avg_price else 0,
        "price_range": {
            "min": stats.min_price,
            "max": stats.max_price,
        },
        "stores": [
            {
                "store_name": row.store_name,
                "product_count": row.product_count,
                "min_price": row.min_price,
                "avg_price": int(row.avg_price) if row.avg_price else 0,
            }
            for row in store_rows
        ],
        "price_distribution": price_dist,
    }
