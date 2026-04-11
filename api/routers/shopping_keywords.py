"""Shopping keyword analysis API router."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from database.models import (
    AdDetail, AdSnapshot, Keyword, ShoppingKeyword, SmartStoreSnapshot, User,
)

router = APIRouter(
    prefix="/api/shopping-keywords",
    tags=["shopping-keywords"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/analysis")
async def keyword_analysis(
    category: str = Query("", description="Filter by category"),
    db: AsyncSession = Depends(get_db),
):
    """Shopping keyword analysis with ad counts per keyword."""
    # Get all active shopping keywords
    kw_query = select(ShoppingKeyword).where(ShoppingKeyword.is_active == True)
    if category:
        kw_query = kw_query.where(ShoppingKeyword.category == category)
    kw_query = kw_query.order_by(ShoppingKeyword.priority, ShoppingKeyword.id)
    kw_rows = (await db.execute(kw_query)).scalars().all()

    # Get ad counts per keyword from ad_snapshots
    ad_counts: dict[str, dict] = {}
    if kw_rows:
        kw_texts = [kw.keyword for kw in kw_rows]
        # Query ad_snapshots joined with ad_details to get per-keyword ad counts
        for kw_text in kw_texts:
            count_q = (
                select(
                    func.count(func.distinct(AdDetail.id)).label("ad_count"),
                    func.count(func.distinct(AdDetail.advertiser_id)).label("adv_count"),
                )
                .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
                .where(Keyword.keyword == kw_text)
            )
            row = (await db.execute(count_q)).one()
            ad_counts[kw_text] = {"ad_count": row.ad_count, "advertiser_count": row.adv_count}

    # Build response
    keywords = []
    for kw in kw_rows:
        counts = ad_counts.get(kw.keyword, {"ad_count": 0, "advertiser_count": 0})
        keywords.append({
            "id": kw.id,
            "keyword": kw.keyword,
            "category": kw.category,
            "subcategory": kw.subcategory,
            "monthly_search_vol": kw.monthly_search_vol,
            "avg_product_price": kw.avg_product_price,
            "competition_level": kw.competition_level,
            "ad_count": counts["ad_count"],
            "advertiser_count": counts["advertiser_count"],
            "last_crawled_at": kw.last_crawled_at.isoformat() if kw.last_crawled_at else None,
        })

    # Category stats
    cat_stats_q = (
        select(
            ShoppingKeyword.category,
            func.count(ShoppingKeyword.id).label("keyword_count"),
        )
        .where(ShoppingKeyword.is_active == True)
        .group_by(ShoppingKeyword.category)
        .order_by(func.count(ShoppingKeyword.id).desc())
    )
    cat_rows = (await db.execute(cat_stats_q)).all()

    # Ad count per category
    category_stats = []
    for cat_name, kw_count in cat_rows:
        cat_ad_count = sum(
            ad_counts.get(kw.keyword, {}).get("ad_count", 0)
            for kw in kw_rows
            if kw.category == cat_name
        )
        category_stats.append({
            "category": cat_name,
            "keyword_count": kw_count,
            "ad_count": cat_ad_count,
        })

    total_ads = sum(c["ad_count"] for c in category_stats)

    return {
        "summary": {
            "total_keywords": len(kw_rows),
            "active_keywords": len([k for k in kw_rows if k.is_active]),
            "categories": len(cat_rows),
            "total_ads_collected": total_ads,
        },
        "keywords": keywords,
        "category_stats": category_stats,
    }


@router.get("/sales-overview")
async def sales_overview(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Overview of SmartStore sales estimations."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Get latest snapshot per product_url
    latest_sub = (
        select(
            SmartStoreSnapshot.product_url,
            func.max(SmartStoreSnapshot.id).label("max_id"),
        )
        .where(SmartStoreSnapshot.captured_at >= cutoff)
        .group_by(SmartStoreSnapshot.product_url)
        .subquery()
    )

    snap_q = (
        select(SmartStoreSnapshot)
        .join(latest_sub, SmartStoreSnapshot.id == latest_sub.c.max_id)
        .order_by(SmartStoreSnapshot.estimated_daily_sales.desc().nullslast())
    )
    snapshots = (await db.execute(snap_q)).scalars().all()

    products = []
    total_revenue = 0
    for s in snapshots:
        daily_revenue = (s.estimated_daily_sales or 0) * (s.price or 0)
        total_revenue += daily_revenue * 30
        adv = await db.get(s.__class__.__mro__[1], s.advertiser_id) if False else None
        products.append({
            "advertiser_id": s.advertiser_id,
            "advertiser_name": "",
            "store_name": s.store_name or "",
            "product_name": s.product_name or "",
            "product_url": s.product_url or "",
            "price": s.price,
            "review_count": s.review_count,
            "review_delta": s.review_delta or 0,
            "purchase_cnt": s.purchase_cnt,
            "purchase_cnt_delta": s.purchase_cnt_delta or 0,
            "estimated_daily_sales": s.estimated_daily_sales,
            "estimation_method": s.estimation_method,
            "seller_grade": s.seller_grade,
            "category_name": s.category_name,
            "captured_at": s.captured_at.isoformat() if s.captured_at else None,
        })

    unique_stores = len(set(s.store_name for s in snapshots if s.store_name))
    avg_sales = (
        sum(s.estimated_daily_sales for s in snapshots if s.estimated_daily_sales) / len(snapshots)
        if snapshots else 0
    )

    return {
        "summary": {
            "total_products": len(products),
            "total_stores": unique_stores,
            "avg_daily_sales": round(avg_sales, 1),
            "total_estimated_revenue": round(total_revenue),
        },
        "products": products,
        "top_sellers": sorted(products, key=lambda p: p["estimated_daily_sales"] or 0, reverse=True)[:10],
    }
