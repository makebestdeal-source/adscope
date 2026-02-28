"""Industry landscape analysis API router."""

from datetime import datetime, timedelta

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
    Industry,
    SpendEstimate,
)
from database.schemas import (
    IndustryAdvertiserOut,
    IndustryLandscapeOut,
    IndustryMarketMapOut,
    IndustryOut,
    MarketMapPoint,
)

router = APIRouter(
    prefix="/api/industries",
    tags=["industries"],
    redirect_slashes=False,
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[IndustryOut])
async def list_industries(db: AsyncSession = Depends(get_db)):
    """List all industries."""
    result = await db.execute(select(Industry).order_by(Industry.name))
    return result.scalars().all()


async def _build_landscape_advertisers(
    db: AsyncSession, industry_id: int, days: int
) -> list[IndustryAdvertiserOut]:
    """Build advertiser landscape data for an industry within a time window."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Fetch all advertisers in the industry
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.industry_id == industry_id)
    )
    advertisers = adv_result.scalars().all()

    if not advertisers:
        return []

    adv_ids = [a.id for a in advertisers]

    # Ad count and channels per advertiser (via ad_details -> ad_snapshots)
    ad_stats = await db.execute(
        select(
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("ad_count"),
            func.group_concat(AdSnapshot.channel.distinct()).label("channels"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.advertiser_id.in_(adv_ids),
            AdSnapshot.captured_at >= cutoff,
        )
        .group_by(AdDetail.advertiser_id)
    )
    ad_stats_map: dict[int, dict] = {}
    for row in ad_stats.all():
        channels_str = row.channels or ""
        channel_list = [c.strip() for c in channels_str.split(",") if c.strip()]
        ad_stats_map[row.advertiser_id] = {
            "ad_count": row.ad_count,
            "channels": channel_list,
        }

    # Total ads across all advertisers in the industry (for SOV calculation)
    total_ads_result = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.advertiser_id.in_(adv_ids),
            AdSnapshot.captured_at >= cutoff,
        )
    )
    total_ads = total_ads_result.scalar() or 0

    # Estimated spend per advertiser (via campaigns -> spend_estimates)
    spend_result = await db.execute(
        select(
            Campaign.advertiser_id,
            func.sum(SpendEstimate.est_daily_spend).label("total_spend"),
        )
        .join(SpendEstimate, SpendEstimate.campaign_id == Campaign.id)
        .where(
            Campaign.advertiser_id.in_(adv_ids),
            SpendEstimate.date >= cutoff,
        )
        .group_by(Campaign.advertiser_id)
    )
    spend_map: dict[int, float] = {}
    for row in spend_result.all():
        spend_map[row.advertiser_id] = row.total_spend or 0.0

    # Build output list
    items: list[IndustryAdvertiserOut] = []
    for adv in advertisers:
        stats = ad_stats_map.get(adv.id, {"ad_count": 0, "channels": []})
        ad_count = stats["ad_count"]
        sov = (ad_count / total_ads * 100) if total_ads > 0 else 0.0
        est_spend = spend_map.get(adv.id, 0.0)

        items.append(
            IndustryAdvertiserOut(
                id=adv.id,
                name=adv.name,
                brand_name=adv.brand_name,
                annual_revenue=adv.annual_revenue,
                employee_count=adv.employee_count,
                is_public=adv.is_public or False,
                est_ad_spend=round(est_spend, 2),
                sov_percentage=round(sov, 2),
                channel_count=len(stats["channels"]),
                channel_mix=stats["channels"],
                ad_count=ad_count,
            )
        )

    # Sort by SOV descending
    items.sort(key=lambda x: x.sov_percentage, reverse=True)
    return items


@router.get("/{industry_id}/landscape", response_model=IndustryLandscapeOut)
async def get_industry_landscape(
    industry_id: int,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Industry landscape analysis: advertisers ranked by share-of-voice."""
    # Fetch industry
    ind_result = await db.execute(
        select(Industry).where(Industry.id == industry_id)
    )
    industry = ind_result.scalar_one_or_none()
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")

    advertisers = await _build_landscape_advertisers(db, industry_id, days)

    # Revenue ranking (only those with annual_revenue)
    revenue_ranking = sorted(
        [a for a in advertisers if a.annual_revenue],
        key=lambda x: x.annual_revenue or 0,
        reverse=True,
    )

    # Spend ranking
    spend_ranking = sorted(
        advertisers, key=lambda x: x.est_ad_spend, reverse=True
    )

    # Total market size estimate (sum of all estimated spends)
    total_market = sum(a.est_ad_spend for a in advertisers)

    return IndustryLandscapeOut(
        industry=IndustryOut.model_validate(industry),
        total_market_size=round(total_market, 2) if total_market > 0 else None,
        advertiser_count=len(advertisers),
        advertisers=advertisers,
        revenue_ranking=revenue_ranking[:20],
        spend_ranking=spend_ranking[:20],
    )


@router.get("/{industry_id}/market-map", response_model=IndustryMarketMapOut)
async def get_industry_market_map(
    industry_id: int,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Market map scatter plot: X=revenue, Y=ad_spend, size=SOV."""
    # Fetch industry
    ind_result = await db.execute(
        select(Industry).where(Industry.id == industry_id)
    )
    industry = ind_result.scalar_one_or_none()
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")

    advertisers = await _build_landscape_advertisers(db, industry_id, days)

    points: list[MarketMapPoint] = []
    for adv in advertisers:
        # Only include advertisers that have revenue data for meaningful scatter plot
        revenue = adv.annual_revenue or 0
        points.append(
            MarketMapPoint(
                id=adv.id,
                name=adv.name,
                x=revenue,
                y=adv.est_ad_spend,
                size=max(adv.sov_percentage, 1.0),  # Minimum bubble size
                is_public=adv.is_public,
            )
        )

    return IndustryMarketMapOut(
        industry=IndustryOut.model_validate(industry),
        points=points,
        axis_labels={
            "x": "Annual Revenue (KRW)",
            "y": "Estimated Ad Spend (KRW)",
            "size": "Share of Voice (%)",
        },
    )
