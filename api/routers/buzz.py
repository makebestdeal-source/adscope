"""Brand Buzz dashboard API -- overview, sentiment matrix, alerts."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    Advertiser,
    BrandChannelContent,
    Industry,
    NewsMention,
    SocialImpactScore,
)

router = APIRouter(prefix="/api/buzz", tags=["buzz"],
    dependencies=[Depends(get_current_user)])

KST = timezone(timedelta(hours=9))


@router.get("/overview")
async def buzz_overview(
    days: int = Query(30, ge=1, le=365),
    industry_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Overall buzz volume, avg sentiment, timeline, industry breakdown."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    # --- News mentions volume + sentiment ---
    news_q = select(
        func.count(NewsMention.id).label("total_mentions"),
        func.avg(NewsMention.sentiment_score).label("avg_sentiment"),
        func.sum(case((NewsMention.sentiment == "positive", 1), else_=0)).label("positive"),
        func.sum(case((NewsMention.sentiment == "neutral", 1), else_=0)).label("neutral"),
        func.sum(case((NewsMention.sentiment == "negative", 1), else_=0)).label("negative"),
    ).where(NewsMention.published_at >= cutoff)
    if industry_id:
        news_q = news_q.join(Advertiser, Advertiser.id == NewsMention.advertiser_id).where(
            Advertiser.industry_id == industry_id
        )
    news_row = (await db.execute(news_q)).one()

    # --- Social posts volume ---
    social_q = select(func.count(BrandChannelContent.id)).where(
        BrandChannelContent.discovered_at >= cutoff
    )
    social_count = (await db.scalar(social_q)) or 0

    # --- Daily timeline (news + social) ---
    news_daily = (
        await db.execute(
            select(
                func.date(NewsMention.published_at).label("day"),
                func.count(NewsMention.id).label("cnt"),
            )
            .where(NewsMention.published_at >= cutoff)
            .group_by(func.date(NewsMention.published_at))
            .order_by(func.date(NewsMention.published_at))
        )
    ).all()

    social_daily = (
        await db.execute(
            select(
                func.date(BrandChannelContent.discovered_at).label("day"),
                func.count(BrandChannelContent.id).label("cnt"),
            )
            .where(BrandChannelContent.discovered_at >= cutoff)
            .group_by(func.date(BrandChannelContent.discovered_at))
            .order_by(func.date(BrandChannelContent.discovered_at))
        )
    ).all()

    # merge timelines
    timeline_map: dict[str, dict] = {}
    for row in news_daily:
        d = str(row.day)
        timeline_map.setdefault(d, {"date": d, "news": 0, "social": 0})
        timeline_map[d]["news"] = row.cnt
    for row in social_daily:
        d = str(row.day)
        timeline_map.setdefault(d, {"date": d, "news": 0, "social": 0})
        timeline_map[d]["social"] = row.cnt
    timeline = sorted(timeline_map.values(), key=lambda x: x["date"])

    # --- Top industries ---
    industry_rows = (
        await db.execute(
            select(
                Industry.name,
                func.count(NewsMention.id).label("cnt"),
            )
            .join(Advertiser, Advertiser.id == NewsMention.advertiser_id)
            .join(Industry, Industry.id == Advertiser.industry_id)
            .where(NewsMention.published_at >= cutoff)
            .group_by(Industry.name)
            .order_by(func.count(NewsMention.id).desc())
            .limit(10)
        )
    ).all()

    return {
        "total_mentions": news_row.total_mentions or 0,
        "social_posts": social_count,
        "avg_sentiment": round(news_row.avg_sentiment or 0, 3),
        "positive": news_row.positive or 0,
        "neutral": news_row.neutral or 0,
        "negative": news_row.negative or 0,
        "timeline": timeline,
        "top_industries": [{"name": r.name, "count": r.cnt} for r in industry_rows],
    }


@router.get("/sentiment-matrix")
async def buzz_sentiment_matrix(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Industry x Sentiment matrix for heatmap."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    rows = (
        await db.execute(
            select(
                Industry.name.label("industry"),
                func.sum(case((NewsMention.sentiment == "positive", 1), else_=0)).label("positive"),
                func.sum(case((NewsMention.sentiment == "neutral", 1), else_=0)).label("neutral"),
                func.sum(case((NewsMention.sentiment == "negative", 1), else_=0)).label("negative"),
                func.count(NewsMention.id).label("total"),
            )
            .join(Advertiser, Advertiser.id == NewsMention.advertiser_id)
            .join(Industry, Industry.id == Advertiser.industry_id)
            .where(NewsMention.published_at >= cutoff)
            .group_by(Industry.name)
            .order_by(func.count(NewsMention.id).desc())
        )
    ).all()

    return [
        {
            "industry": r.industry,
            "positive": r.positive or 0,
            "neutral": r.neutral or 0,
            "negative": r.negative or 0,
            "total": r.total or 0,
        }
        for r in rows
    ]


@router.get("/alerts")
async def buzz_alerts(
    days: int = Query(7, ge=1, le=30),
    threshold: float = Query(30, ge=10, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Brands with sudden buzz score changes (>threshold% day-over-day)."""
    now = datetime.now(KST).replace(tzinfo=None)
    cutoff = now - timedelta(days=days)

    # Get latest 2 scores per advertiser within window
    scores = (
        await db.execute(
            select(
                SocialImpactScore.advertiser_id,
                SocialImpactScore.date,
                SocialImpactScore.composite_score,
            )
            .where(SocialImpactScore.date >= cutoff)
            .order_by(SocialImpactScore.advertiser_id, SocialImpactScore.date.desc())
        )
    ).all()

    # Group by advertiser, find max change
    from collections import defaultdict
    adv_scores: dict[int, list] = defaultdict(list)
    for s in scores:
        adv_scores[s.advertiser_id].append((s.date, s.composite_score or 0))

    alerts = []
    for adv_id, entries in adv_scores.items():
        if len(entries) < 2:
            continue
        latest = entries[0][1]
        prev = entries[1][1]
        if prev == 0:
            continue
        change_pct = ((latest - prev) / prev) * 100
        if abs(change_pct) >= threshold:
            alerts.append({
                "advertiser_id": adv_id,
                "latest_score": round(latest, 1),
                "prev_score": round(prev, 1),
                "change_pct": round(change_pct, 1),
                "direction": "up" if change_pct > 0 else "down",
                "date": str(entries[0][0]),
            })

    # Enrich with advertiser names
    if alerts:
        adv_ids = [a["advertiser_id"] for a in alerts]
        advs = (
            await db.execute(
                select(Advertiser.id, Advertiser.name, Advertiser.industry_id).where(
                    Advertiser.id.in_(adv_ids)
                )
            )
        ).all()
        name_map = {a.id: a.name for a in advs}
        for alert in alerts:
            alert["advertiser_name"] = name_map.get(alert["advertiser_id"], "")

    alerts.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return alerts[:20]


@router.get("/top-brands")
async def buzz_top_brands(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=5, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Top brands by buzz volume with sentiment breakdown."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    rows = (
        await db.execute(
            select(
                Advertiser.id,
                Advertiser.name,
                Industry.name.label("industry"),
                func.count(NewsMention.id).label("mention_count"),
                func.avg(NewsMention.sentiment_score).label("avg_sentiment"),
                func.sum(case((NewsMention.sentiment == "positive", 1), else_=0)).label("positive"),
                func.sum(case((NewsMention.sentiment == "negative", 1), else_=0)).label("negative"),
            )
            .join(Advertiser, Advertiser.id == NewsMention.advertiser_id)
            .outerjoin(Industry, Industry.id == Advertiser.industry_id)
            .where(NewsMention.published_at >= cutoff)
            .group_by(Advertiser.id, Advertiser.name, Industry.name)
            .order_by(func.count(NewsMention.id).desc())
            .limit(limit)
        )
    ).all()

    return [
        {
            "advertiser_id": r.id,
            "name": r.name,
            "industry": r.industry,
            "mention_count": r.mention_count,
            "avg_sentiment": round(r.avg_sentiment or 0, 3),
            "positive": r.positive or 0,
            "negative": r.negative or 0,
        }
        for r in rows
    ]


@router.get("/news-feed")
async def buzz_news_feed(
    days: int = Query(7, ge=1, le=90),
    sentiment: str | None = Query(None),
    industry_id: int | None = Query(None),
    limit: int = Query(30, ge=5, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Global news feed (all advertisers). Per-advertiser news: /api/social-impact/{id}/news"""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    q = (
        select(
            NewsMention.id,
            NewsMention.article_title,
            NewsMention.article_url,
            NewsMention.publisher,
            NewsMention.published_at,
            NewsMention.sentiment,
            NewsMention.sentiment_score,
            NewsMention.is_pr,
            Advertiser.id.label("advertiser_id"),
            Advertiser.name.label("advertiser_name"),
        )
        .join(Advertiser, Advertiser.id == NewsMention.advertiser_id)
        .where(NewsMention.published_at >= cutoff)
    )
    if sentiment:
        q = q.where(NewsMention.sentiment == sentiment)
    if industry_id:
        q = q.where(Advertiser.industry_id == industry_id)

    q = q.order_by(NewsMention.published_at.desc()).limit(limit)
    rows = (await db.execute(q)).all()

    return [
        {
            "id": r.id,
            "title": r.article_title,
            "url": r.article_url,
            "publisher": r.publisher,
            "published_at": str(r.published_at) if r.published_at else None,
            "sentiment": r.sentiment,
            "sentiment_score": round(r.sentiment_score, 2) if r.sentiment_score else None,
            "is_pr": r.is_pr,
            "advertiser_id": r.advertiser_id,
            "advertiser_name": r.advertiser_name,
        }
        for r in rows
    ]
