"""Campaign Effect API -- overview, before/after, sentiment shift, comparison."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.services.advertiser_links import (
    needs_context_advertiser_name,
    resolve_profile_advertiser_id,
)
from api.services.advertiser_names import (
    campaign_display_fields,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    AdDetail,
    Advertiser,
    Campaign,
    CampaignLift,
    NewsMention,
    SocialImpactScore,
    SpendEstimate,
    TrafficSignal,
)

router = APIRouter(prefix="/api/campaign-effect", tags=["campaign-effect"])

KST = timezone(timedelta(hours=9))


async def _display_spend(db: AsyncSession, campaign_id: int, fallback) -> int | None:
    """Return spend only when the estimate has enough evidence for UI display."""
    rows = (
        await db.execute(
            select(
                SpendEstimate.est_daily_spend,
                SpendEstimate.confidence,
                SpendEstimate.calculation_method,
            ).where(SpendEstimate.campaign_id == campaign_id)
        )
    ).all()
    if not rows:
        return round(fallback or 0) if fallback else None

    total = sum(float(r.est_daily_spend or 0) for r in rows)
    if (
        len(rows) == 1
        and rows[0].calculation_method == "market_share_inverse"
        and float(rows[0].confidence or 0) <= 0.4
    ):
        return None
    return round(total or fallback or 0) if (total or fallback) else None


def _needs_subject(advertiser_name) -> bool:
    return needs_context_advertiser_name(advertiser_name)


def _as_id_list(value) -> list[int]:
    if not value:
        return []
    if isinstance(value, list):
        return [int(v) for v in value if str(v).isdigit()]
    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [int(v) for v in parsed if str(v).isdigit()]
        except Exception:
            return [int(v) for v in value.split(",") if v.strip().isdigit()]
    return []


async def _first_ad_context(db: AsyncSession, creative_ids) -> dict:
    ids = _as_id_list(creative_ids)[:5]
    if not ids:
        return {}
    row = (
        await db.execute(
            select(
                AdDetail.advertiser_name_raw,
                AdDetail.ad_text,
                AdDetail.url,
                AdDetail.brand,
                AdDetail.extra_data,
            ).where(AdDetail.id.in_(ids)).limit(1)
        )
    ).first()
    if not row:
        return {}
    return {
        "advertiser_name_raw": row.advertiser_name_raw,
        "ad_text": row.ad_text,
        "url": row.url,
        "brand": row.brand,
        "extra_data": row.extra_data,
    }


def _context_brand_name(brand_name, advertiser_name, ad_ctx: dict):
    if brand_name:
        return brand_name
    if _needs_subject(advertiser_name):
        return ad_ctx.get("brand") or ad_ctx.get("advertiser_name_raw")
    return None


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
    ad_ctx = await _first_ad_context(db, campaign.creative_ids)
    display = campaign_display_fields(
        campaign_name=campaign.campaign_name,
        advertiser_name=adv.name if adv else None,
        brand_name=_context_brand_name(adv.brand_name if adv else None, adv.name if adv else None, ad_ctx),
        website=adv.website if adv else None,
        url=ad_ctx.get("url"),
        ad_text=ad_ctx.get("ad_text"),
        product_service=campaign.product_service,
        model_info=campaign.model_info,
        promotion_copy=campaign.promotion_copy,
        extra_data=ad_ctx.get("extra_data"),
        campaign_id=campaign.id,
    )
    profile_advertiser_id = await resolve_profile_advertiser_id(
        db,
        current_id=campaign.advertiser_id,
        current_name=adv.name if adv else None,
        display_name=display["advertiser_name"],
    )

    # Use SUM(SpendEstimate) for consistency with campaigns.py
    spend_sum = (
        await db.scalar(
            select(func.sum(SpendEstimate.est_daily_spend)).where(
                SpendEstimate.campaign_id == campaign_id
            )
        )
    ) or campaign.total_est_spend or 0

    display_spend = await _display_spend(db, campaign_id, spend_sum)

    return {
        "campaign_id": campaign.id,
        "campaign_name": display["campaign_name"],
        "advertiser_id": profile_advertiser_id or campaign.advertiser_id,
        "source_advertiser_id": campaign.advertiser_id,
        "profile_link_resolved": bool(profile_advertiser_id and profile_advertiser_id != campaign.advertiser_id),
        "advertiser_name": display["advertiser_name"],
        "channel": campaign.channel,
        "channels": campaign.channels,
        "objective": campaign.objective,
        "status": campaign.status,
        "first_seen": str(campaign.first_seen) if campaign.first_seen else None,
        "last_seen": str(campaign.last_seen) if campaign.last_seen else None,
        "total_est_spend": display_spend,
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

    items = []
    for r in rows:
        items.append({
            "campaign_id": r.id,
            "campaign_name": r.campaign_name or f"Campaign #{r.id}",
            "channel": r.channel,
            "channels": r.channels,
            "objective": r.objective,
            "first_seen": str(r.first_seen) if r.first_seen else None,
            "last_seen": str(r.last_seen) if r.last_seen else None,
            "total_est_spend": await _display_spend(db, r.id, r.spend),
            "query_lift_pct": round(r.query_lift_pct or 0, 1) if r.query_lift_pct else None,
            "social_lift_pct": round(r.social_lift_pct or 0, 1) if r.social_lift_pct else None,
            "sales_lift_pct": round(r.sales_lift_pct or 0, 1) if r.sales_lift_pct else None,
            "confidence": round(r.confidence or 0, 2) if r.confidence else None,
        })
    return items


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
            Campaign.product_service,
            Campaign.model_info,
            Campaign.promotion_copy,
            Campaign.creative_ids,
            Advertiser.id.label("advertiser_id"),
            Advertiser.name.label("advertiser_name"),
            Advertiser.brand_name.label("brand_name"),
            Advertiser.website.label("website"),
        )
        .join(Advertiser, Advertiser.id == Campaign.advertiser_id)
        .join(CampaignLift, CampaignLift.campaign_id == Campaign.id)
        .where(Campaign.first_seen >= cutoff)
        .where(
            (CampaignLift.query_lift_pct.isnot(None))
            | (CampaignLift.social_lift_pct.isnot(None))
            | (CampaignLift.sales_lift_pct.isnot(None))
        )
    )
    if advertiser_id:
        q = q.where(Campaign.advertiser_id == advertiser_id)

    q = q.order_by(Campaign.first_seen.desc()).limit(limit)
    rows = (await db.execute(q)).all()

    items = []
    for r in rows:
        ad_ctx = await _first_ad_context(db, r.creative_ids)
        display = campaign_display_fields(
            campaign_name=r.campaign_name,
            advertiser_name=r.advertiser_name,
            brand_name=_context_brand_name(r.brand_name, r.advertiser_name, ad_ctx),
            website=r.website,
            url=ad_ctx.get("url"),
            ad_text=ad_ctx.get("ad_text"),
            product_service=r.product_service,
            model_info=r.model_info,
            promotion_copy=r.promotion_copy,
            extra_data=ad_ctx.get("extra_data"),
            campaign_id=r.id,
        )
        if _needs_subject(r.advertiser_name) and not display["subject"]:
            continue

        profile_advertiser_id = await resolve_profile_advertiser_id(
            db,
            current_id=r.advertiser_id,
            current_name=r.advertiser_name,
            display_name=display["advertiser_name"],
        )

        items.append({
            "id": r.id,
            "campaign_name": display["campaign_name"],
            "channel": r.channel,
            "first_seen": str(r.first_seen) if r.first_seen else None,
            "last_seen": str(r.last_seen) if r.last_seen else None,
            "is_active": r.is_active,
            "total_est_spend": await _display_spend(db, r.id, r.total_est_spend),
            "advertiser_id": profile_advertiser_id or r.advertiser_id,
            "source_advertiser_id": r.advertiser_id,
            "profile_link_resolved": bool(profile_advertiser_id and profile_advertiser_id != r.advertiser_id),
            "advertiser_name": display["advertiser_name"],
        })
    return items
