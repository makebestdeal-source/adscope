"""Campaign Effect API -- overview, before/after, sentiment shift, comparison."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    Advertiser,
    Campaign,
    CampaignLift,
    NewsMention,
    SocialImpactScore,
    SpendEstimate,
    TrafficSignal,
)

router = APIRouter(prefix="/api/campaign-effect", tags=["campaign-effect"],
    dependencies=[Depends(get_current_user)])

KST = timezone(timedelta(hours=9))


@router.get("/overview")
async def campaign_effect_overview(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Campaign KPI summary: lift metrics + spend + period."""
    campaign = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    lift = (
        await db.execute(
            select(CampaignLift).where(CampaignLift.campaign_id == campaign_id)
        )
    ).scalar_one_or_none()

    adv = (
        await db.execute(select(Advertiser).where(Advertiser.id == campaign.advertiser_id))
    ).scalar_one_or_none()

    # Use SUM(SpendEstimate) for consistency with campaigns.py
    spend_sum = (
        await db.scalar(
            select(func.sum(SpendEstimate.est_daily_spend)).where(
                SpendEstimate.campaign_id == campaign_id
            )
        )
    ) or campaign.total_est_spend or 0

    return {
        "campaign_id": campaign.id,
        "campaign_name": campaign.campaign_name or f"Campaign #{campaign.id}",
        "advertiser_id": campaign.advertiser_id,
        "advertiser_name": adv.name if adv else "",
        "channel": campaign.channel,
        "channels": campaign.channels,
        "objective": campaign.objective,
        "status": campaign.status,
        "first_seen": str(campaign.first_seen) if campaign.first_seen else None,
        "last_seen": str(campaign.last_seen) if campaign.last_seen else None,
        "total_est_spend": spend_sum,
        "lift": {
            "query_lift_pct": round(lift.query_lift_pct or 0, 1) if lift else None,
            "social_lift_pct": round(lift.social_lift_pct or 0, 1) if lift else None,
            "sales_lift_pct": round(lift.sales_lift_pct or 0, 1) if lift else None,
            "pre_query_avg": round(lift.pre_query_avg or 0, 1) if lift else None,
            "post_query_avg": round(lift.post_query_avg or 0, 1) if lift else None,
            "confidence": round(lift.confidence or 0, 2) if lift else None,
        } if lift else None,
    }


@router.get("/before-after")
async def campaign_before_after(
    campaign_id: int,
    metric: str = Query("search", regex="^(search|news|social)$"),
    db: AsyncSession = Depends(get_db),
):
    """Before/after time series comparison around campaign period."""
    campaign = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    start = campaign.first_seen
    end = campaign.last_seen or start
    pre_start = start - timedelta(days=14)
    post_end = end + timedelta(days=14)

    series = []

    if metric == "search":
        rows = (
            await db.execute(
                select(
                    TrafficSignal.date,
                    TrafficSignal.composite_index,
                )
                .where(
                    and_(
                        TrafficSignal.advertiser_id == campaign.advertiser_id,
                        TrafficSignal.date >= pre_start,
                        TrafficSignal.date <= post_end,
                    )
                )
                .order_by(TrafficSignal.date)
            )
        ).all()
        series = [
            {
                "date": str(r.date),
                "value": r.composite_index or 0,
                "phase": "before" if r.date < start else ("during" if r.date <= end else "after"),
            }
            for r in rows
        ]

    elif metric == "news":
        rows = (
            await db.execute(
                select(
                    func.date(NewsMention.published_at).label("day"),
                    func.count(NewsMention.id).label("cnt"),
                    func.avg(NewsMention.sentiment_score).label("avg_sentiment"),
                )
                .where(
                    and_(
                        NewsMention.advertiser_id == campaign.advertiser_id,
                        NewsMention.published_at >= pre_start,
                        NewsMention.published_at <= post_end,
                    )
                )
                .group_by(func.date(NewsMention.published_at))
                .order_by(func.date(NewsMention.published_at))
            )
        ).all()
        series = [
            {
                "date": str(r.day),
                "value": r.cnt,
                "sentiment": round(r.avg_sentiment or 0, 2),
                "phase": "before" if str(r.day) < str(start.date()) else (
                    "during" if str(r.day) <= str(end.date()) else "after"
                ),
            }
            for r in rows
        ]

    elif metric == "social":
        rows = (
            await db.execute(
                select(
                    SocialImpactScore.date,
                    SocialImpactScore.composite_score,
                    SocialImpactScore.social_posting_score,
                )
                .where(
                    and_(
                        SocialImpactScore.advertiser_id == campaign.advertiser_id,
                        SocialImpactScore.date >= pre_start,
                        SocialImpactScore.date <= post_end,
                    )
                )
                .order_by(SocialImpactScore.date)
            )
        ).all()
        series = [
            {
                "date": str(r.date),
                "value": r.composite_score or 0,
                "social_posting": r.social_posting_score or 0,
                "phase": "before" if r.date < start else ("during" if r.date <= end else "after"),
            }
            for r in rows
        ]

    return {
        "campaign_id": campaign_id,
        "metric": metric,
        "campaign_start": str(start) if start else None,
        "campaign_end": str(end) if end else None,
        "series": series,
    }


@router.get("/sentiment-shift")
async def campaign_sentiment_shift(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Sentiment breakdown: pre vs during vs post campaign."""
    campaign = (
        await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one_or_none()
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    start = campaign.first_seen
    end = campaign.last_seen or start
    pre_start = start - timedelta(days=14)
    post_end = end + timedelta(days=14)

    async def _sentiment_counts(from_dt, to_dt):
        rows = (
            await db.execute(
                select(
                    NewsMention.sentiment,
                    func.count(NewsMention.id).label("cnt"),
                )
                .where(
                    and_(
                        NewsMention.advertiser_id == campaign.advertiser_id,
                        NewsMention.published_at >= from_dt,
                        NewsMention.published_at <= to_dt,
                    )
                )
                .group_by(NewsMention.sentiment)
            )
        ).all()
        result = {"positive": 0, "neutral": 0, "negative": 0}
        for r in rows:
            if r.sentiment in result:
                result[r.sentiment] = r.cnt
        return result

    pre = await _sentiment_counts(pre_start, start)
    during = await _sentiment_counts(start, end)
    post = await _sentiment_counts(end, post_end)

    return {
        "campaign_id": campaign_id,
        "pre": pre,
        "during": during,
        "post": post,
    }


@router.get("/comparison")
async def campaign_comparison(
    advertiser_id: int,
    campaign_ids: str = Query(None, description="Comma-separated campaign IDs"),
    limit: int = Query(10, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Compare lift metrics across multiple campaigns of an advertiser."""
    q = (
        select(
            Campaign.id,
            Campaign.campaign_name,
            Campaign.channel,
            Campaign.channels,
            Campaign.first_seen,
            Campaign.last_seen,
            Campaign.objective,
            CampaignLift.query_lift_pct,
            CampaignLift.social_lift_pct,
            CampaignLift.sales_lift_pct,
            CampaignLift.confidence,
            func.coalesce(
                select(func.sum(SpendEstimate.est_daily_spend))
                .where(SpendEstimate.campaign_id == Campaign.id)
                .correlate(Campaign)
                .scalar_subquery(),
                Campaign.total_est_spend,
                0,
            ).label("spend"),
        )
        .outerjoin(CampaignLift, CampaignLift.campaign_id == Campaign.id)
        .where(Campaign.advertiser_id == advertiser_id)
    )

    if campaign_ids:
        ids = [int(x.strip()) for x in campaign_ids.split(",") if x.strip().isdigit()]
        if ids:
            q = q.where(Campaign.id.in_(ids))

    q = q.order_by(Campaign.first_seen.desc()).limit(limit)
    rows = (await db.execute(q)).all()

    return [
        {
            "campaign_id": r.id,
            "campaign_name": r.campaign_name or f"Campaign #{r.id}",
            "channel": r.channel,
            "channels": r.channels,
            "objective": r.objective,
            "first_seen": str(r.first_seen) if r.first_seen else None,
            "last_seen": str(r.last_seen) if r.last_seen else None,
            "total_est_spend": r.spend or 0,
            "query_lift_pct": round(r.query_lift_pct or 0, 1) if r.query_lift_pct else None,
            "social_lift_pct": round(r.social_lift_pct or 0, 1) if r.social_lift_pct else None,
            "sales_lift_pct": round(r.sales_lift_pct or 0, 1) if r.sales_lift_pct else None,
            "confidence": round(r.confidence or 0, 2) if r.confidence else None,
        }
        for r in rows
    ]


@router.get("/campaigns")
async def list_campaigns_for_effect(
    advertiser_id: int | None = Query(None),
    days: int = Query(90, ge=1, le=365),
    limit: int = Query(30, ge=5, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List campaigns available for effect analysis."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    q = (
        select(
            Campaign.id,
            Campaign.campaign_name,
            Campaign.channel,
            Campaign.first_seen,
            Campaign.last_seen,
            Campaign.is_active,
            Campaign.total_est_spend,
            Advertiser.id.label("advertiser_id"),
            Advertiser.name.label("advertiser_name"),
        )
        .join(Advertiser, Advertiser.id == Campaign.advertiser_id)
        .where(Campaign.first_seen >= cutoff)
    )
    if advertiser_id:
        q = q.where(Campaign.advertiser_id == advertiser_id)

    q = q.order_by(Campaign.first_seen.desc()).limit(limit)
    rows = (await db.execute(q)).all()

    return [
        {
            "id": r.id,
            "campaign_name": r.campaign_name or f"Campaign #{r.id}",
            "channel": r.channel,
            "first_seen": str(r.first_seen) if r.first_seen else None,
            "last_seen": str(r.last_seen) if r.last_seen else None,
            "is_active": r.is_active,
            "total_est_spend": r.total_est_spend or 0,
            "advertiser_id": r.advertiser_id,
            "advertiser_name": r.advertiser_name,
        }
        for r in rows
    ]
