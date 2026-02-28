"""Product/service category analysis API router."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    AdDetail,
    AdSnapshot,
    Advertiser,
    Campaign,
    ProductCategory,
    SpendEstimate,
    ActivityScore,
)
from database.schemas import (
    ProductCategoryAdvertiserOut,
    ProductCategoryDetailOut,
    ProductCategoryTreeOut,
)

router = APIRouter(prefix="/api/products", tags=["products"], redirect_slashes=False,
    dependencies=[Depends(get_current_user)])

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


async def _count_ads_for_category(
    db: AsyncSession, category_id: int, days: int
) -> int:
    """Count ad_details linked to a category (by product_category_id or product_category text match)."""
    cutoff = _now_kst() - timedelta(days=days)

    # product_category_id FK match
    fk_count = await db.execute(
        select(func.count(AdDetail.id)).where(
            AdDetail.product_category_id == category_id
        )
    )
    count = fk_count.scalar() or 0

    # Also match by product_category text field (for legacy data without FK)
    cat_result = await db.execute(
        select(ProductCategory.name).where(ProductCategory.id == category_id)
    )
    cat_name = cat_result.scalar_one_or_none()
    if cat_name:
        text_count = await db.execute(
            select(func.count(AdDetail.id))
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(
                AdDetail.product_category == cat_name,
                AdDetail.product_category_id.is_(None),
                AdSnapshot.captured_at >= cutoff.replace(tzinfo=None),
            )
        )
        count += text_count.scalar() or 0

    return count


async def _count_advertisers_for_category(
    db: AsyncSession, category_id: int, days: int
) -> int:
    """Count unique advertisers for a category."""
    cutoff = _now_kst() - timedelta(days=days)

    # FK match
    fk_result = await db.execute(
        select(func.count(func.distinct(AdDetail.advertiser_id))).where(
            AdDetail.product_category_id == category_id,
            AdDetail.advertiser_id.isnot(None),
        )
    )
    fk_count = fk_result.scalar() or 0

    # Text match for legacy
    cat_result = await db.execute(
        select(ProductCategory.name).where(ProductCategory.id == category_id)
    )
    cat_name = cat_result.scalar_one_or_none()
    if cat_name:
        text_result = await db.execute(
            select(func.count(func.distinct(AdDetail.advertiser_id)))
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(
                AdDetail.product_category == cat_name,
                AdDetail.product_category_id.is_(None),
                AdDetail.advertiser_id.isnot(None),
                AdSnapshot.captured_at >= cutoff.replace(tzinfo=None),
            )
        )
        fk_count += text_result.scalar() or 0

    return fk_count


@router.get("/categories", response_model=list[ProductCategoryTreeOut])
async def list_categories(
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Return full category tree (parent categories with children)."""
    result = await db.execute(
        select(ProductCategory)
        .where(ProductCategory.parent_id.is_(None))
        .order_by(ProductCategory.name)
    )
    parents = result.scalars().all()

    tree: list[ProductCategoryTreeOut] = []
    for parent in parents:
        # children
        child_result = await db.execute(
            select(ProductCategory)
            .where(ProductCategory.parent_id == parent.id)
            .order_by(ProductCategory.name)
        )
        children = child_result.scalars().all()

        child_items: list[ProductCategoryTreeOut] = []
        parent_ad_count = 0
        parent_adv_count = 0

        for child in children:
            ad_count = await _count_ads_for_category(db, child.id, days)
            adv_count = await _count_advertisers_for_category(db, child.id, days)
            parent_ad_count += ad_count
            parent_adv_count += adv_count
            child_items.append(
                ProductCategoryTreeOut(
                    id=child.id,
                    name=child.name,
                    parent_id=child.parent_id,
                    industry_id=child.industry_id,
                    children=[],
                    advertiser_count=adv_count,
                    ad_count=ad_count,
                )
            )

        # parent-level counts include direct + children
        direct_ad = await _count_ads_for_category(db, parent.id, days)
        direct_adv = await _count_advertisers_for_category(db, parent.id, days)

        tree.append(
            ProductCategoryTreeOut(
                id=parent.id,
                name=parent.name,
                parent_id=None,
                industry_id=parent.industry_id,
                children=child_items,
                advertiser_count=direct_adv + parent_adv_count,
                ad_count=direct_ad + parent_ad_count,
            )
        )

    return tree


@router.get("/categories/{category_id}", response_model=ProductCategoryDetailOut)
async def get_category_detail(
    category_id: int,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Category detail: ad count, advertiser count, estimated spend."""
    cat_result = await db.execute(
        select(ProductCategory).where(ProductCategory.id == category_id)
    )
    category = cat_result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Children
    child_result = await db.execute(
        select(ProductCategory)
        .where(ProductCategory.parent_id == category_id)
        .order_by(ProductCategory.name)
    )
    children = child_result.scalars().all()

    child_items: list[ProductCategoryTreeOut] = []
    total_ad_count = 0
    total_adv_count = 0

    for child in children:
        ad_count = await _count_ads_for_category(db, child.id, days)
        adv_count = await _count_advertisers_for_category(db, child.id, days)
        total_ad_count += ad_count
        total_adv_count += adv_count
        child_items.append(
            ProductCategoryTreeOut(
                id=child.id,
                name=child.name,
                parent_id=child.parent_id,
                industry_id=child.industry_id,
                children=[],
                advertiser_count=adv_count,
                ad_count=ad_count,
            )
        )

    direct_ad = await _count_ads_for_category(db, category.id, days)
    direct_adv = await _count_advertisers_for_category(db, category.id, days)

    # Estimated spend for this category
    cutoff = _now_kst() - timedelta(days=days)
    # Get advertiser IDs for this category
    all_category_ids = [category.id] + [c.id for c in children]
    adv_ids_result = await db.execute(
        select(func.distinct(AdDetail.advertiser_id)).where(
            AdDetail.product_category_id.in_(all_category_ids),
            AdDetail.advertiser_id.isnot(None),
        )
    )
    adv_ids = [r[0] for r in adv_ids_result.all()]

    est_spend = 0.0
    if adv_ids:
        spend_result = await db.execute(
            select(func.sum(SpendEstimate.est_daily_spend))
            .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
            .where(
                Campaign.advertiser_id.in_(adv_ids),
                SpendEstimate.date >= cutoff.replace(tzinfo=None),
            )
        )
        est_spend = spend_result.scalar() or 0.0

    return ProductCategoryDetailOut(
        id=category.id,
        name=category.name,
        parent_id=category.parent_id,
        industry_id=category.industry_id,
        advertiser_count=direct_adv + total_adv_count,
        ad_count=direct_ad + total_ad_count,
        est_spend=round(est_spend, 2),
        children=child_items,
    )


@router.get(
    "/categories/{category_id}/advertisers",
    response_model=list[ProductCategoryAdvertiserOut],
)
async def get_category_advertisers(
    category_id: int,
    days: int = Query(default=30, le=365),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Advertiser ranking for a specific category."""
    cat_result = await db.execute(
        select(ProductCategory).where(ProductCategory.id == category_id)
    )
    category = cat_result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    cutoff = _now_kst() - timedelta(days=days)

    # Include child categories
    child_result = await db.execute(
        select(ProductCategory.id).where(ProductCategory.parent_id == category_id)
    )
    all_cat_ids = [category_id] + [r[0] for r in child_result.all()]

    # Get advertisers via FK
    fk_query = (
        select(
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("ad_count"),
            func.group_concat(AdSnapshot.channel).label("channels"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.product_category_id.in_(all_cat_ids),
            AdDetail.advertiser_id.isnot(None),
            AdSnapshot.captured_at >= cutoff.replace(tzinfo=None),
        )
        .group_by(AdDetail.advertiser_id)
        .order_by(func.count(AdDetail.id).desc())
        .limit(limit)
    )
    fk_rows = (await db.execute(fk_query)).all()

    # Also get from text match (legacy)
    cat_name = category.name
    child_names_result = await db.execute(
        select(ProductCategory.name).where(ProductCategory.parent_id == category_id)
    )
    all_cat_names = [cat_name] + [r[0] for r in child_names_result.all()]

    text_query = (
        select(
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("ad_count"),
            func.group_concat(AdSnapshot.channel).label("channels"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.product_category.in_(all_cat_names),
            AdDetail.product_category_id.is_(None),
            AdDetail.advertiser_id.isnot(None),
            AdSnapshot.captured_at >= cutoff.replace(tzinfo=None),
        )
        .group_by(AdDetail.advertiser_id)
        .order_by(func.count(AdDetail.id).desc())
        .limit(limit)
    )
    text_rows = (await db.execute(text_query)).all()

    # Merge results
    adv_stats: dict[int, dict] = {}
    for row in list(fk_rows) + list(text_rows):
        aid = row.advertiser_id
        channels_str = row.channels or ""
        channel_list = list(set(c.strip() for c in channels_str.split(",") if c.strip()))
        if aid in adv_stats:
            adv_stats[aid]["ad_count"] += row.ad_count
            adv_stats[aid]["channels"] = list(
                set(adv_stats[aid]["channels"]) | set(channel_list)
            )
        else:
            adv_stats[aid] = {"ad_count": row.ad_count, "channels": channel_list}

    if not adv_stats:
        return []

    # Fetch advertiser details
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id.in_(list(adv_stats.keys())))
    )
    advertisers = {a.id: a for a in adv_result.scalars().all()}

    # Spend per advertiser
    spend_result = await db.execute(
        select(
            Campaign.advertiser_id,
            func.sum(SpendEstimate.est_daily_spend).label("total_spend"),
        )
        .join(SpendEstimate, SpendEstimate.campaign_id == Campaign.id)
        .where(
            Campaign.advertiser_id.in_(list(adv_stats.keys())),
            SpendEstimate.date >= cutoff.replace(tzinfo=None),
        )
        .group_by(Campaign.advertiser_id)
    )
    spend_map: dict[int, float] = {}
    for row in spend_result.all():
        spend_map[row.advertiser_id] = row.total_spend or 0.0

    # Build output sorted by ad_count desc
    items: list[ProductCategoryAdvertiserOut] = []
    sorted_advs = sorted(adv_stats.items(), key=lambda x: x[1]["ad_count"], reverse=True)

    for rank, (aid, stats) in enumerate(sorted_advs[:limit], 1):
        adv = advertisers.get(aid)
        if not adv:
            continue
        items.append(
            ProductCategoryAdvertiserOut(
                advertiser_id=aid,
                advertiser_name=adv.name,
                brand_name=adv.brand_name,
                ad_count=stats["ad_count"],
                est_spend=round(spend_map.get(aid, 0.0), 2),
                channels=stats["channels"],
                rank=rank,
            )
        )

    return items


# ── Shopping Insight ──

@router.get("/shopping-insight")
async def shopping_insight(
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Shopping insight dashboard data."""
    cutoff = _now_kst() - timedelta(days=days)
    cutoff_naive = cutoff.replace(tzinfo=None)
    prev_cutoff = (cutoff - timedelta(days=days)).replace(tzinfo=None)

    # 1. Top categories by ad count
    cat_q = (
        select(
            AdDetail.product_category,
            func.count(AdDetail.id).label("ad_count"),
            func.count(func.distinct(AdDetail.advertiser_id)).label("adv_count"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.product_category.isnot(None),
            AdSnapshot.captured_at >= cutoff_naive,
        )
        .group_by(AdDetail.product_category)
        .order_by(func.count(AdDetail.id).desc())
        .limit(15)
    )
    cat_rows = (await db.execute(cat_q)).all()

    top_categories = []
    for row in cat_rows:
        # Spend for this category
        adv_ids_q = (
            select(func.distinct(AdDetail.advertiser_id))
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(
                AdDetail.product_category == row.product_category,
                AdDetail.advertiser_id.isnot(None),
                AdSnapshot.captured_at >= cutoff_naive,
            )
        )
        adv_ids = [r[0] for r in (await db.execute(adv_ids_q)).all()]
        spend = 0.0
        if adv_ids:
            spend_r = await db.execute(
                select(func.sum(SpendEstimate.est_daily_spend))
                .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
                .where(
                    Campaign.advertiser_id.in_(adv_ids),
                    SpendEstimate.date >= cutoff_naive,
                )
            )
            spend = spend_r.scalar() or 0.0

        # Previous period ad count for growth
        prev_q = (
            select(func.count(AdDetail.id))
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(
                AdDetail.product_category == row.product_category,
                AdSnapshot.captured_at >= prev_cutoff,
                AdSnapshot.captured_at < cutoff_naive,
            )
        )
        prev_count = (await db.execute(prev_q)).scalar() or 0
        growth = None
        if prev_count > 0:
            growth = round((row.ad_count - prev_count) / prev_count * 100, 1)

        top_categories.append({
            "category": row.product_category,
            "ad_count": row.ad_count,
            "advertiser_count": row.adv_count,
            "est_spend": round(spend, 0),
            "growth_pct": growth,
        })

    # 2. Channel distribution for product ads
    ch_q = (
        select(
            AdSnapshot.channel,
            func.count(AdDetail.id).label("ad_count"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.product_category.isnot(None),
            AdSnapshot.captured_at >= cutoff_naive,
        )
        .group_by(AdSnapshot.channel)
        .order_by(func.count(AdDetail.id).desc())
    )
    ch_rows = (await db.execute(ch_q)).all()
    channel_dist = [{"channel": r.channel, "ad_count": r.ad_count} for r in ch_rows]

    # 3. Top shopping advertisers (by ad count with product category)
    top_adv_q = (
        select(
            AdDetail.advertiser_id,
            Advertiser.name,
            Advertiser.brand_name,
            func.count(AdDetail.id).label("ad_count"),
            func.group_concat(AdDetail.product_category).label("categories"),
            func.group_concat(AdSnapshot.channel).label("channels"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Advertiser, AdDetail.advertiser_id == Advertiser.id)
        .where(
            AdDetail.product_category.isnot(None),
            AdDetail.advertiser_id.isnot(None),
            AdSnapshot.captured_at >= cutoff_naive,
        )
        .group_by(AdDetail.advertiser_id, Advertiser.name, Advertiser.brand_name)
        .order_by(func.count(AdDetail.id).desc())
        .limit(20)
    )
    top_adv_rows = (await db.execute(top_adv_q)).all()

    # Get spend for top advertisers
    top_adv_ids = [r.advertiser_id for r in top_adv_rows]
    spend_map: dict[int, float] = {}
    if top_adv_ids:
        spend_q = (
            select(
                Campaign.advertiser_id,
                func.sum(SpendEstimate.est_daily_spend).label("total"),
            )
            .join(SpendEstimate, SpendEstimate.campaign_id == Campaign.id)
            .where(
                Campaign.advertiser_id.in_(top_adv_ids),
                SpendEstimate.date >= cutoff_naive,
            )
            .group_by(Campaign.advertiser_id)
        )
        for sr in (await db.execute(spend_q)).all():
            spend_map[sr.advertiser_id] = sr.total or 0.0

    # Get activity state for top advertisers
    activity_map: dict[int, str] = {}
    if top_adv_ids:
        act_q = (
            select(ActivityScore.advertiser_id, ActivityScore.activity_state)
            .where(ActivityScore.advertiser_id.in_(top_adv_ids))
            .order_by(ActivityScore.date.desc())
        )
        seen = set()
        for ar in (await db.execute(act_q)).all():
            if ar.advertiser_id not in seen:
                activity_map[ar.advertiser_id] = ar.activity_state or "unknown"
                seen.add(ar.advertiser_id)

    top_advertisers = []
    for rank, r in enumerate(top_adv_rows, 1):
        cats = list(set(c.strip() for c in (r.categories or "").split(",") if c.strip()))
        chs = list(set(c.strip() for c in (r.channels or "").split(",") if c.strip()))
        top_advertisers.append({
            "rank": rank,
            "advertiser_id": r.advertiser_id,
            "name": r.name,
            "brand_name": r.brand_name,
            "ad_count": r.ad_count,
            "categories": cats[:3],
            "channels": chs,
            "est_spend": round(spend_map.get(r.advertiser_id, 0), 0),
            "activity_state": activity_map.get(r.advertiser_id),
        })

    # 4. Promotion type distribution
    promo_q = (
        select(
            AdDetail.promotion_type,
            func.count(AdDetail.id).label("cnt"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.promotion_type.isnot(None),
            AdSnapshot.captured_at >= cutoff_naive,
        )
        .group_by(AdDetail.promotion_type)
        .order_by(func.count(AdDetail.id).desc())
    )
    promo_rows = (await db.execute(promo_q)).all()
    promotion_types = [{"type": r.promotion_type, "count": r.cnt} for r in promo_rows]

    # 5. Summary stats
    total_ads = sum(c["ad_count"] for c in top_categories)
    total_advs_q = (
        select(func.count(func.distinct(AdDetail.advertiser_id)))
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.product_category.isnot(None),
            AdDetail.advertiser_id.isnot(None),
            AdSnapshot.captured_at >= cutoff_naive,
        )
    )
    total_advs = (await db.execute(total_advs_q)).scalar() or 0
    total_spend = sum(c["est_spend"] for c in top_categories)
    total_cats_q = (
        select(func.count(func.distinct(AdDetail.product_category)))
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.product_category.isnot(None),
            AdSnapshot.captured_at >= cutoff_naive,
        )
    )
    total_cats = (await db.execute(total_cats_q)).scalar() or 0

    return {
        "summary": {
            "total_ads": total_ads,
            "total_advertisers": total_advs,
            "total_spend": round(total_spend, 0),
            "total_categories": total_cats,
            "days": days,
        },
        "top_categories": top_categories,
        "channel_distribution": channel_dist,
        "top_advertisers": top_advertisers,
        "promotion_types": promotion_types,
    }
