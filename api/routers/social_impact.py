"""Social impact API router -- overview, timeline, news, breakdown, top-impact."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    Advertiser,
    Campaign,
    NewsMention,
    SocialImpactScore,
)
from database.schemas import (
    NewsMentionOut,
    SocialImpactOverviewOut,
    SocialImpactTimelineOut,
    SocialImpactTopItem,
)

router = APIRouter(prefix="/api/social-impact", tags=["social-impact"],
    dependencies=[Depends(get_current_user)])

KST = timezone(timedelta(hours=9))


@router.get("/{advertiser_id}/overview", response_model=SocialImpactOverviewOut)
async def get_social_impact_overview(
    advertiser_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get the latest social impact score for an advertiser."""
    adv = (
        await db.execute(select(Advertiser).where(Advertiser.id == advertiser_id))
    ).scalar_one_or_none()
    if not adv:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    score = (
        await db.execute(
            select(SocialImpactScore)
            .where(SocialImpactScore.advertiser_id == advertiser_id)
            .order_by(SocialImpactScore.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not score:
        return SocialImpactOverviewOut(advertiser_id=advertiser_id)

    return SocialImpactOverviewOut(
        advertiser_id=advertiser_id,
        date=score.date,
        news_impact_score=score.news_impact_score or 0,
        social_posting_score=score.social_posting_score or 0,
        search_lift_score=score.search_lift_score or 0,
        composite_score=score.composite_score or 0,
        news_article_count=score.news_article_count or 0,
        news_sentiment_avg=score.news_sentiment_avg,
        social_engagement_delta_pct=score.social_engagement_delta_pct,
        social_posting_delta_pct=score.social_posting_delta_pct,
        search_volume_delta_pct=score.search_volume_delta_pct,
        has_active_campaign=score.has_active_campaign or False,
        impact_phase=score.impact_phase,
        factors=score.factors,
    )


@router.get("/{advertiser_id}/timeline", response_model=list[SocialImpactTimelineOut])
async def get_social_impact_timeline(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get daily social impact score timeline."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)
    rows = (
        await db.execute(
            select(SocialImpactScore)
            .where(
                and_(
                    SocialImpactScore.advertiser_id == advertiser_id,
                    SocialImpactScore.date >= cutoff,
                )
            )
            .order_by(SocialImpactScore.date.asc())
        )
    ).scalars().all()

    return [
        SocialImpactTimelineOut(
            date=r.date,
            news_impact_score=r.news_impact_score or 0,
            social_posting_score=r.social_posting_score or 0,
            search_lift_score=r.search_lift_score or 0,
            composite_score=r.composite_score or 0,
            impact_phase=r.impact_phase,
            has_active_campaign=r.has_active_campaign or False,
        )
        for r in rows
    ]


@router.get("/{advertiser_id}/news", response_model=list[NewsMentionOut])
async def get_news_mentions(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    sentiment: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get news mentions for an advertiser."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)
    q = (
        select(NewsMention)
        .where(
            and_(
                NewsMention.advertiser_id == advertiser_id,
                NewsMention.collected_at >= cutoff,
            )
        )
    )
    if sentiment:
        q = q.where(NewsMention.sentiment == sentiment)
    q = q.order_by(NewsMention.published_at.desc()).limit(100)

    rows = (await db.execute(q)).scalars().all()
    return rows


@router.get("/{advertiser_id}/breakdown")
async def get_social_impact_breakdown(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed sub-score breakdown with contributing factors."""
    score = (
        await db.execute(
            select(SocialImpactScore)
            .where(SocialImpactScore.advertiser_id == advertiser_id)
            .order_by(SocialImpactScore.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not score:
        return {
            "advertiser_id": advertiser_id,
            "factors": None,
            "composite_score": 0,
        }

    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    # News stats
    news_stats = (
        await db.execute(
            select(
                func.count(NewsMention.id),
                func.sum(case((NewsMention.sentiment == "positive", 1), else_=0)),
                func.sum(case((NewsMention.sentiment == "negative", 1), else_=0)),
                func.sum(case((NewsMention.is_pr == True, 1), else_=0)),
            ).where(
                and_(
                    NewsMention.advertiser_id == advertiser_id,
                    NewsMention.collected_at >= cutoff,
                )
            )
        )
    ).one()

    # Campaign context
    active_camps = (
        await db.execute(
            select(
                func.count(Campaign.id),
                func.min(Campaign.first_seen),
                func.max(Campaign.last_seen),
            ).where(
                and_(
                    Campaign.advertiser_id == advertiser_id,
                    Campaign.is_active == True,
                )
            )
        )
    ).one()

    channels = (
        await db.execute(
            select(func.group_concat(func.distinct(Campaign.channel))).where(
                and_(
                    Campaign.advertiser_id == advertiser_id,
                    Campaign.is_active == True,
                )
            )
        )
    ).scalar_one() or ""

    return {
        "advertiser_id": advertiser_id,
        "composite_score": score.composite_score,
        "news_impact_score": score.news_impact_score,
        "social_posting_score": score.social_posting_score,
        "search_lift_score": score.search_lift_score,
        "impact_phase": score.impact_phase,
        "news": {
            "total_articles": news_stats[0] or 0,
            "positive_count": news_stats[1] or 0,
            "negative_count": news_stats[2] or 0,
            "pr_count": news_stats[3] or 0,
            "sentiment_avg": score.news_sentiment_avg,
        },
        "social": {
            "posting_delta_pct": score.social_posting_delta_pct,
            "engagement_delta_pct": score.social_engagement_delta_pct,
        },
        "search": {
            "volume_delta_pct": score.search_volume_delta_pct,
        },
        "campaign_context": {
            "active_campaigns": active_camps[0] or 0,
            "first_seen": active_camps[1].isoformat() if active_camps[1] else None,
            "last_seen": active_camps[2].isoformat() if active_camps[2] else None,
            "channels": channels.split(",") if channels else [],
        },
        "factors": score.factors,
    }


@router.get("/top-impact", response_model=list[SocialImpactTopItem])
async def get_top_social_impact(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get top advertisers by social impact score (dashboard widget)."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    # Subquery: latest score per advertiser
    latest_sq = (
        select(
            SocialImpactScore.advertiser_id,
            func.max(SocialImpactScore.date).label("max_date"),
        )
        .where(SocialImpactScore.date >= cutoff)
        .group_by(SocialImpactScore.advertiser_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(
                SocialImpactScore,
                Advertiser.name,
                Advertiser.brand_name,
            )
            .join(latest_sq, and_(
                SocialImpactScore.advertiser_id == latest_sq.c.advertiser_id,
                SocialImpactScore.date == latest_sq.c.max_date,
            ))
            .join(Advertiser, Advertiser.id == SocialImpactScore.advertiser_id)
            .order_by(SocialImpactScore.composite_score.desc())
            .limit(limit)
        )
    ).all()

    return [
        SocialImpactTopItem(
            advertiser_id=score.advertiser_id,
            advertiser_name=name,
            brand_name=brand,
            composite_score=score.composite_score or 0,
            impact_phase=score.impact_phase,
            news_impact_score=score.news_impact_score or 0,
            social_posting_score=score.social_posting_score or 0,
            search_lift_score=score.search_lift_score or 0,
        )
        for score, name, brand in rows
    ]
