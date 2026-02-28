"""Marketing Schedule / Plan Detection API.

Endpoints for product portfolio management, advertising activity timeline,
and marketing pattern detection.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    Advertiser, AdvertiserProduct, ProductAdActivity, ProductCategory,
    AdDetail, AdSnapshot, AdProductMaster,
)

logger = logging.getLogger("adscope.api.marketing_schedule")
router = APIRouter(prefix="/api/marketing-schedule", tags=["marketing-schedule"],
    dependencies=[Depends(get_current_user)])


def _format_product(p) -> dict:
    return {
        "id": p.id,
        "advertiser_id": p.advertiser_id,
        "product_name": p.product_name,
        "product_category_id": p.product_category_id,
        "is_flagship": p.is_flagship or False,
        "status": p.status or "active",
        "source": p.source or "ad_observed",
        "first_ad_seen": p.first_ad_seen.isoformat() if p.first_ad_seen else None,
        "last_ad_seen": p.last_ad_seen.isoformat() if p.last_ad_seen else None,
        "total_campaigns": p.total_campaigns or 0,
        "total_spend_est": round(p.total_spend_est or 0),
        "channels": p.channels or [],
        "ad_count": p.ad_count or 0,
    }


@router.get("")
async def get_marketing_schedule(
    advertiser_id: int = Query(...),
    days: int = Query(default=90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Product x date activity matrix for Gantt chart."""
    adv = (await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )).scalar_one_or_none()
    if not adv:
        raise HTTPException(404, "Advertiser not found")

    cutoff = datetime.utcnow() - timedelta(days=days)

    # Get products
    products = (await db.execute(
        select(AdvertiserProduct)
        .where(AdvertiserProduct.advertiser_id == advertiser_id)
        .order_by(AdvertiserProduct.ad_count.desc())
    )).scalars().all()

    # Category names
    cat_ids = [p.product_category_id for p in products if p.product_category_id]
    cat_names = {}
    if cat_ids:
        cats = (await db.execute(
            select(ProductCategory.id, ProductCategory.name)
            .where(ProductCategory.id.in_(cat_ids))
        )).all()
        cat_names = {c[0]: c[1] for c in cats}

    product_ids = [p.id for p in products]
    activities = []
    if product_ids:
        activities = (await db.execute(
            select(ProductAdActivity)
            .where(
                ProductAdActivity.advertiser_product_id.in_(product_ids),
                ProductAdActivity.date >= cutoff,
            )
            .order_by(ProductAdActivity.date.asc())
        )).scalars().all()

    # Get model_names and ad_products per product from ad_details
    product_extras = {}
    if products:
        for p in products:
            extras_q = (
                select(
                    AdDetail.model_name,
                    AdDetail.ad_product_name,
                    AdDetail.campaign_purpose,
                )
                .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
                .where(
                    AdDetail.advertiser_id == advertiser_id,
                    func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown") == p.product_name,
                )
                .limit(100)
            )
            detail_rows = (await db.execute(extras_q)).all()

            models = set()
            ad_prods = set()
            purposes = set()
            for row in detail_rows:
                if row[0]:
                    models.add(row[0])
                if row[1]:
                    ad_prods.add(row[1])
                if row[2]:
                    purposes.add(row[2])

            product_extras[p.id] = {
                "model_names": sorted(models),
                "ad_products_used": sorted(ad_prods),
                "purposes": sorted(purposes),
            }

    return {
        "advertiser_id": adv.id,
        "advertiser_name": adv.name,
        "period_days": days,
        "products": [
            {
                **_format_product(p),
                "product_category_name": cat_names.get(p.product_category_id),
                **(product_extras.get(p.id, {})),
            }
            for p in products
        ],
        "activity_matrix": [
            {
                "product_id": a.advertiser_product_id,
                "date": a.date.strftime("%Y-%m-%d") if a.date else None,
                "channel": a.channel,
                "ad_product_name": a.ad_product_name,
                "ad_count": a.ad_count or 0,
                "est_daily_spend": round(a.est_daily_spend or 0),
                "unique_creatives": a.unique_creatives or 0,
            }
            for a in activities
        ],
    }


@router.get("/portfolio")
async def get_portfolio(
    advertiser_id: int = Query(...),
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Full product portfolio for an advertiser."""
    query = (
        select(AdvertiserProduct)
        .where(AdvertiserProduct.advertiser_id == advertiser_id)
        .order_by(AdvertiserProduct.total_spend_est.desc())
    )
    if status:
        query = query.where(AdvertiserProduct.status == status)

    products = (await db.execute(query)).scalars().all()

    cat_ids = [p.product_category_id for p in products if p.product_category_id]
    cat_names = {}
    if cat_ids:
        cats = (await db.execute(
            select(ProductCategory.id, ProductCategory.name)
            .where(ProductCategory.id.in_(cat_ids))
        )).all()
        cat_names = {c[0]: c[1] for c in cats}

    return [
        {
            **_format_product(p),
            "product_category_name": cat_names.get(p.product_category_id),
        }
        for p in products
    ]


@router.get("/overview")
async def get_overview(
    days: int = Query(default=30, le=365),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Top advertisers by tracked products count."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            Advertiser.id,
            Advertiser.name,
            Advertiser.brand_name,
            func.count(AdvertiserProduct.id).label("total_products"),
            func.sum(
                case(
                    (AdvertiserProduct.last_ad_seen >= cutoff, 1),
                    else_=0,
                )
            ).label("active_products"),
            func.sum(AdvertiserProduct.total_spend_est).label("total_spend"),
        )
        .join(AdvertiserProduct, AdvertiserProduct.advertiser_id == Advertiser.id)
        .group_by(Advertiser.id)
        .order_by(func.count(AdvertiserProduct.id).desc())
        .limit(limit)
    )

    return [
        {
            "advertiser_id": row[0],
            "advertiser_name": row[1],
            "brand_name": row[2],
            "total_products": row[3],
            "active_products": int(row[4] or 0),
            "total_spend": round(row[5] or 0),
        }
        for row in result.all()
    ]


@router.get("/detection")
async def get_detections(
    days: int = Query(default=7, le=30),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Recent marketing pattern changes."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    detections = []

    # 1. New products started
    new_products = (await db.execute(
        select(AdvertiserProduct, Advertiser.name.label("adv_name"))
        .join(Advertiser, Advertiser.id == AdvertiserProduct.advertiser_id)
        .where(AdvertiserProduct.first_ad_seen >= cutoff)
        .order_by(AdvertiserProduct.first_ad_seen.desc())
        .limit(limit)
    )).all()
    for row in new_products:
        p = row.AdvertiserProduct
        detections.append({
            "advertiser_id": p.advertiser_id,
            "advertiser_name": row.adv_name,
            "product_name": p.product_name,
            "event_type": "new_product_started",
            "detected_at": p.first_ad_seen.isoformat() if p.first_ad_seen else None,
            "details": {"channels": p.channels, "source": p.source},
        })

    # 2. Products that stopped
    stop_cutoff = datetime.utcnow() - timedelta(days=14)
    stopped = (await db.execute(
        select(AdvertiserProduct, Advertiser.name.label("adv_name"))
        .join(Advertiser, Advertiser.id == AdvertiserProduct.advertiser_id)
        .where(
            AdvertiserProduct.last_ad_seen < stop_cutoff,
            AdvertiserProduct.status == "active",
            AdvertiserProduct.ad_count > 3,
        )
        .order_by(AdvertiserProduct.last_ad_seen.desc())
        .limit(limit)
    )).all()
    for row in stopped:
        p = row.AdvertiserProduct
        detections.append({
            "advertiser_id": p.advertiser_id,
            "advertiser_name": row.adv_name,
            "product_name": p.product_name,
            "event_type": "product_stopped",
            "detected_at": p.last_ad_seen.isoformat() if p.last_ad_seen else None,
            "details": {"last_channels": p.channels, "total_ads": p.ad_count},
        })

    detections.sort(key=lambda d: d.get("detected_at") or "", reverse=True)
    return detections[:limit]


@router.get("/ad-products")
async def get_ad_products(
    channel: str | None = None,
    format_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all ad product master entries."""
    query = select(AdProductMaster).order_by(AdProductMaster.channel, AdProductMaster.product_code)
    if channel:
        query = query.where(AdProductMaster.channel == channel)
    if format_type:
        query = query.where(AdProductMaster.format_type == format_type)

    products = (await db.execute(query)).scalars().all()
    return [
        {
            "id": p.id,
            "channel": p.channel,
            "product_code": p.product_code,
            "product_name_ko": p.product_name_ko,
            "product_name_en": p.product_name_en,
            "format_type": p.format_type,
            "billing_type": p.billing_type,
            "description": p.description,
            # pricing (absorbed from legacy media_ad_products)
            "position_zone": p.position_zone,
            "base_price": p.base_price,
            "price_range_min": p.price_range_min,
            "price_range_max": p.price_range_max,
            "device": getattr(p, "device", "all") or "all",
            "is_active": getattr(p, "is_active", True),
        }
        for p in products
    ]


@router.post("/rebuild")
async def trigger_rebuild(
    db: AsyncSession = Depends(get_db),
):
    """Trigger full rebuild of marketing schedule data (runs inline)."""
    try:
        from processor.marketing_schedule_builder import update_marketing_schedule
        result = await update_marketing_schedule(days_back=365)
        return {"status": "ok", "result": result}
    except ImportError:
        # Fallback: run backfill inline
        return {"status": "error", "message": "marketing_schedule_builder not available"}
