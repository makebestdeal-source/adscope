"""Social channel analytics API router.

Provides endpoints for social channel overview, rankings, comparisons,
and per-advertiser detail with stats from ChannelStats and BrandChannelContent.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from api.deps import require_plan
from pydantic import BaseModel
from sqlalchemy import func, select, desc, and_, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from database import get_db
from database.models import Advertiser, BrandChannelContent, ChannelStats

router = APIRouter(
    prefix="/api/social-channels",
    tags=["social-channels"],
    dependencies=[Depends(require_plan("full"))],
)

KST = timezone(timedelta(hours=9))


# ── Response schemas ──


class OverviewResponse(BaseModel):
    total_monitored_channels: int
    total_posts_tracked: int
    avg_engagement_rate: float | None
    # MoM (month-over-month) growth fields
    engagement_rate_mom_change: float | None = None
    subscribers_mom_change: float | None = None
    content_count_mom_change: float | None = None
    total_subscribers: int | None = None


class PlatformStats(BaseModel):
    platform: str
    subscribers: int | None = None
    followers: int | None = None
    total_posts: int | None = None
    avg_likes: float | None = None
    avg_views: float | None = None
    engagement_rate: float | None = None
    posting_frequency: float | None = None  # posts per week


class RankingItem(BaseModel):
    advertiser_id: int
    name: str
    brand_name: str | None = None
    logo_url: str | None = None
    platforms: list[PlatformStats] = []


class RankingsResponse(BaseModel):
    items: list[RankingItem]
    total: int


class DailyPostCount(BaseModel):
    date: str  # YYYY-MM-DD
    count: int


class CompareItem(BaseModel):
    advertiser_id: int
    name: str
    brand_name: str | None = None
    logo_url: str | None = None
    platforms: list[PlatformStats] = []
    posting_trend: list[DailyPostCount] = []


class CompareResponse(BaseModel):
    items: list[CompareItem]


class ContentItem(BaseModel):
    id: int
    platform: str
    channel_url: str
    content_id: str
    content_type: str | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    upload_date: datetime | None = None
    view_count: int | None = None
    like_count: int | None = None
    duration_seconds: int | None = None
    is_ad_content: bool | None = None
    discovered_at: datetime | None = None


class AdvertiserDetailResponse(BaseModel):
    advertiser_id: int
    name: str
    brand_name: str | None = None
    logo_url: str | None = None
    platforms: list[PlatformStats] = []
    recent_posts: list[ContentItem] = []
    posting_trend: list[DailyPostCount] = []


# ── Helper functions ──


async def _get_latest_channel_stats(
    db: AsyncSession,
    advertiser_id: int | None = None,
    platform: str | None = None,
) -> list[ChannelStats]:
    """Return the latest ChannelStats row per advertiser+platform combination."""
    # Subquery: max collected_at per (advertiser_id, platform)
    latest_sub = (
        select(
            ChannelStats.advertiser_id,
            ChannelStats.platform,
            func.max(ChannelStats.collected_at).label("max_collected"),
        )
        .group_by(ChannelStats.advertiser_id, ChannelStats.platform)
    )
    if advertiser_id is not None:
        latest_sub = latest_sub.where(ChannelStats.advertiser_id == advertiser_id)
    if platform:
        latest_sub = latest_sub.where(ChannelStats.platform == platform)

    latest_sub = latest_sub.subquery()

    stmt = (
        select(ChannelStats)
        .join(
            latest_sub,
            and_(
                ChannelStats.advertiser_id == latest_sub.c.advertiser_id,
                ChannelStats.platform == latest_sub.c.platform,
                ChannelStats.collected_at == latest_sub.c.max_collected,
            ),
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _compute_content_stats(
    db: AsyncSession,
    advertiser_id: int,
    platform: str | None,
    cutoff: datetime,
) -> dict[str, PlatformStats]:
    """Compute stats from BrandChannelContent when ChannelStats is unavailable."""
    stmt = (
        select(
            BrandChannelContent.platform,
            func.count(BrandChannelContent.id).label("post_count"),
            func.avg(BrandChannelContent.view_count).label("avg_views"),
            func.avg(BrandChannelContent.like_count).label("avg_likes"),
        )
        .where(
            BrandChannelContent.advertiser_id == advertiser_id,
            BrandChannelContent.discovered_at >= cutoff,
        )
        .group_by(BrandChannelContent.platform)
    )
    if platform:
        stmt = stmt.where(BrandChannelContent.platform == platform)

    result = await db.execute(stmt)
    rows = result.all()

    out: dict[str, PlatformStats] = {}
    for row in rows:
        out[row.platform] = PlatformStats(
            platform=row.platform,
            total_posts=row.post_count,
            avg_views=round(row.avg_views, 1) if row.avg_views else None,
            avg_likes=round(row.avg_likes, 1) if row.avg_likes else None,
        )
    return out


async def _posting_frequency(
    db: AsyncSession,
    advertiser_id: int,
    platform: str | None,
    cutoff: datetime,
) -> dict[str, float]:
    """Return posts per week per platform for the given period."""
    stmt = (
        select(
            BrandChannelContent.platform,
            func.count(BrandChannelContent.id).label("cnt"),
        )
        .where(
            BrandChannelContent.advertiser_id == advertiser_id,
            BrandChannelContent.discovered_at >= cutoff,
        )
        .group_by(BrandChannelContent.platform)
    )
    if platform:
        stmt = stmt.where(BrandChannelContent.platform == platform)

    result = await db.execute(stmt)
    rows = result.all()

    now = datetime.now(KST)
    weeks = max((now - cutoff).days / 7.0, 1.0)

    return {row.platform: round(row.cnt / weeks, 2) for row in rows}


async def _daily_post_counts(
    db: AsyncSession,
    advertiser_id: int,
    cutoff: datetime,
) -> list[DailyPostCount]:
    """Return daily post counts over the period from BrandChannelContent."""
    stmt = (
        select(
            func.date(BrandChannelContent.discovered_at).label("day"),
            func.count(BrandChannelContent.id).label("cnt"),
        )
        .where(
            BrandChannelContent.advertiser_id == advertiser_id,
            BrandChannelContent.discovered_at >= cutoff,
        )
        .group_by(func.date(BrandChannelContent.discovered_at))
        .order_by(func.date(BrandChannelContent.discovered_at))
    )
    result = await db.execute(stmt)
    return [
        DailyPostCount(date=str(row.day), count=row.cnt)
        for row in result.all()
    ]


async def _compute_engagement_from_content(
    db: AsyncSession,
    cutoff: datetime,
) -> float | None:
    """Compute a global average engagement rate from BrandChannelContent.

    Engagement proxy = avg(view_count) across all content with view_count > 0.
    If like_count data exists, use avg(like_count) / avg_followers * 100.
    Otherwise fall back to computing per-advertiser+platform engagement
    using ChannelStats subscribers/followers and BrandChannelContent views.
    """
    # First try: per-advertiser engagement using ChannelStats follower data
    # For each advertiser+platform with ChannelStats, compute:
    #   engagement = (avg_likes or avg_views * 0.03) / followers * 100
    latest_stats_q = await db.execute(
        select(ChannelStats)
        .where(
            (ChannelStats.subscribers > 0) | (ChannelStats.followers > 0)
        )
    )
    stats_rows = latest_stats_q.scalars().all()

    if stats_rows:
        rates = []
        for s in stats_rows:
            base = s.subscribers or s.followers or 0
            if base <= 0:
                continue
            # If engagement_rate already computed, use it
            if s.engagement_rate is not None and s.engagement_rate > 0:
                rates.append(s.engagement_rate)
                continue
            # Compute from content: get avg views/likes for this advertiser+platform
            content_q = await db.execute(
                select(
                    func.avg(BrandChannelContent.like_count).label("avg_likes"),
                    func.avg(BrandChannelContent.view_count).label("avg_views"),
                )
                .where(
                    BrandChannelContent.advertiser_id == s.advertiser_id,
                    BrandChannelContent.platform == s.platform,
                    BrandChannelContent.discovered_at >= cutoff,
                )
            )
            crow = content_q.one_or_none()
            if crow is None:
                continue
            avg_likes = crow.avg_likes
            avg_views = crow.avg_views
            # Prefer likes, fall back to views * 0.03 proxy
            interaction = avg_likes if (avg_likes and avg_likes > 0) else (
                (avg_views * 0.03) if (avg_views and avg_views > 0) else None
            )
            if interaction and interaction > 0:
                rate = (interaction / base) * 100
                if rate < 100:  # sanity cap
                    rates.append(round(rate, 4))
        if rates:
            return round(sum(rates) / len(rates), 2)

    return None


async def _get_period_stats(
    db: AsyncSession,
    period_start: datetime,
    period_end: datetime,
) -> dict:
    """Compute aggregate stats for a date range for MoM comparison.

    Returns dict with keys:
      total_channels, total_posts, avg_engagement_rate, total_subscribers
    """
    # Channels from ChannelStats collected in the period
    cs_channels_result = await db.execute(
        select(func.count(func.distinct(
            ChannelStats.advertiser_id.op("||")(literal_column("'-'")).op("||")(ChannelStats.platform)
        )))
        .where(
            ChannelStats.collected_at >= period_start,
            ChannelStats.collected_at < period_end,
        )
    )
    cs_channels = cs_channels_result.scalar() or 0

    # Fallback to BrandChannelContent
    if cs_channels == 0:
        bcc_channels_result = await db.execute(
            select(func.count(func.distinct(
                BrandChannelContent.advertiser_id.op("||")(literal_column("'-'")).op("||")(BrandChannelContent.platform)
            )))
            .where(
                BrandChannelContent.discovered_at >= period_start,
                BrandChannelContent.discovered_at < period_end,
            )
        )
        cs_channels = bcc_channels_result.scalar() or 0

    # Posts in period
    posts_result = await db.execute(
        select(func.count(BrandChannelContent.id))
        .where(
            BrandChannelContent.discovered_at >= period_start,
            BrandChannelContent.discovered_at < period_end,
        )
    )
    total_posts = posts_result.scalar() or 0

    # Subscribers sum from ChannelStats in the period (latest per advertiser+platform)
    sub_result = await db.execute(
        select(
            func.sum(
                func.coalesce(ChannelStats.subscribers, 0)
                + func.coalesce(ChannelStats.followers, 0)
            )
        )
        .where(
            ChannelStats.collected_at >= period_start,
            ChannelStats.collected_at < period_end,
        )
    )
    total_subs = sub_result.scalar() or 0

    # Engagement rates from ChannelStats in the period
    eng_result = await db.execute(
        select(func.avg(ChannelStats.engagement_rate))
        .where(
            ChannelStats.collected_at >= period_start,
            ChannelStats.collected_at < period_end,
            ChannelStats.engagement_rate.isnot(None),
            ChannelStats.engagement_rate > 0,
        )
    )
    avg_eng = eng_result.scalar()

    return {
        "total_channels": cs_channels,
        "total_posts": total_posts,
        "avg_engagement_rate": round(avg_eng, 2) if avg_eng else None,
        "total_subscribers": total_subs,
    }


def _calc_mom_change(current: float | int | None, previous: float | int | None) -> float | None:
    """Calculate month-over-month percentage change.

    Returns percentage change (e.g. +12.5 or -3.2) or None if not computable.
    """
    if current is None or previous is None:
        return None
    if previous == 0:
        if current > 0:
            return 100.0  # new data appeared
        return None
    change = ((current - previous) / abs(previous)) * 100
    return round(change, 1)


# ── Endpoints (static paths first) ──


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(db: AsyncSession = Depends(get_db)):
    """Summary stats: total monitored channels, total posts, avg engagement, MoM growth."""
    now = datetime.now(KST)

    # Current period: last 30 days
    current_start = now - timedelta(days=30)
    current_end = now

    # Previous period: 30-60 days ago
    prev_start = now - timedelta(days=60)
    prev_end = now - timedelta(days=30)

    # ── Current period stats ──

    # Total unique channels from ChannelStats
    channels_result = await db.execute(
        select(func.count(func.distinct(
            ChannelStats.advertiser_id.op("||")(literal_column("'-'")).op("||")(ChannelStats.platform)
        )))
    )
    total_channels = channels_result.scalar() or 0

    # Fallback: count from BrandChannelContent if no ChannelStats
    if total_channels == 0:
        bcc_result = await db.execute(
            select(func.count(func.distinct(
                BrandChannelContent.advertiser_id.op("||")(literal_column("'-'")).op("||")(BrandChannelContent.platform)
            )))
        )
        total_channels = bcc_result.scalar() or 0

    # Total posts tracked in BrandChannelContent
    posts_result = await db.execute(
        select(func.count(BrandChannelContent.id))
    )
    total_posts = posts_result.scalar() or 0

    # Average engagement rate from latest ChannelStats
    latest_stats = await _get_latest_channel_stats(db)
    rates = [s.engagement_rate for s in latest_stats if s.engagement_rate is not None]
    avg_rate = round(sum(rates) / len(rates), 2) if rates else None

    # If no engagement rates in ChannelStats, compute from content
    if avg_rate is None:
        avg_rate = await _compute_engagement_from_content(db, current_start)

    # Total subscribers/followers (current)
    total_subs = sum(
        (s.subscribers or 0) + (s.followers or 0)
        for s in latest_stats
    )

    # ── Previous period stats for MoM ──
    prev_stats = await _get_period_stats(db, prev_start, prev_end)

    # Current period content count (last 30 days)
    current_posts_result = await db.execute(
        select(func.count(BrandChannelContent.id))
        .where(BrandChannelContent.discovered_at >= current_start)
    )
    current_content_count = current_posts_result.scalar() or 0

    prev_content_count = prev_stats["total_posts"]

    # MoM calculations
    engagement_rate_mom = _calc_mom_change(avg_rate, prev_stats["avg_engagement_rate"])
    subscribers_mom = _calc_mom_change(total_subs, prev_stats["total_subscribers"])
    content_count_mom = _calc_mom_change(current_content_count, prev_content_count)

    return OverviewResponse(
        total_monitored_channels=total_channels,
        total_posts_tracked=total_posts,
        avg_engagement_rate=avg_rate,
        engagement_rate_mom_change=engagement_rate_mom,
        subscribers_mom_change=subscribers_mom,
        content_count_mom_change=content_count_mom,
        total_subscribers=total_subs if total_subs > 0 else None,
    )


@router.get("/rankings", response_model=RankingsResponse)
async def get_rankings(
    platform: str | None = Query(None, description="Filter by platform (youtube/instagram)"),
    days: int = Query(30, le=365, description="Lookback period in days"),
    sort_by: str = Query("subscribers", description="Sort field: subscribers, posts, engagement"),
    limit: int = Query(20, le=100, description="Max items to return"),
    db: AsyncSession = Depends(get_db),
):
    """All advertisers ranked by social activity."""
    cutoff = datetime.now(KST) - timedelta(days=days)

    # Get latest ChannelStats per advertiser+platform
    latest_stats = await _get_latest_channel_stats(db, platform=platform)

    # Group by advertiser_id
    adv_stats: dict[int, list[ChannelStats]] = {}
    for s in latest_stats:
        adv_stats.setdefault(s.advertiser_id, []).append(s)

    # Also find advertisers with content but no ChannelStats
    content_advs_stmt = (
        select(func.distinct(BrandChannelContent.advertiser_id))
        .where(BrandChannelContent.discovered_at >= cutoff)
    )
    if platform:
        content_advs_stmt = content_advs_stmt.where(
            BrandChannelContent.platform == platform
        )
    content_result = await db.execute(content_advs_stmt)
    content_adv_ids = {row[0] for row in content_result.all()}

    # Merge: all advertiser IDs that have either stats or content
    all_adv_ids = set(adv_stats.keys()) | content_adv_ids
    if not all_adv_ids:
        return RankingsResponse(items=[], total=0)

    # Fetch advertiser info
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id.in_(all_adv_ids))
    )
    advertisers = {a.id: a for a in adv_result.scalars().all()}

    items: list[RankingItem] = []
    for adv_id in all_adv_ids:
        adv = advertisers.get(adv_id)
        if not adv:
            continue

        platforms_list: list[PlatformStats] = []
        freq = await _posting_frequency(db, adv_id, platform, cutoff)

        if adv_id in adv_stats:
            for cs in adv_stats[adv_id]:
                eng_rate = cs.engagement_rate
                avg_likes_val = cs.avg_likes
                avg_views_val = cs.avg_views

                # Compute engagement from content if missing from ChannelStats
                if eng_rate is None or avg_likes_val is None:
                    content_stats = await _compute_content_stats(db, adv_id, cs.platform, cutoff)
                    cs_fallback = content_stats.get(cs.platform)
                    if cs_fallback:
                        if avg_likes_val is None:
                            avg_likes_val = cs_fallback.avg_likes
                        if avg_views_val is None:
                            avg_views_val = cs_fallback.avg_views

                    if eng_rate is None:
                        base = cs.subscribers or cs.followers or 0
                        if base > 0:
                            interaction = avg_likes_val if (avg_likes_val and avg_likes_val > 0) else (
                                (avg_views_val * 0.03) if (avg_views_val and avg_views_val > 0) else None
                            )
                            if interaction and interaction > 0:
                                eng_rate = round((interaction / base) * 100, 4)

                platforms_list.append(PlatformStats(
                    platform=cs.platform,
                    subscribers=cs.subscribers,
                    followers=cs.followers,
                    total_posts=cs.total_posts,
                    avg_likes=avg_likes_val,
                    avg_views=avg_views_val,
                    engagement_rate=eng_rate,
                    posting_frequency=freq.get(cs.platform),
                ))
        else:
            # Fallback: compute from BrandChannelContent
            fallback = await _compute_content_stats(db, adv_id, platform, cutoff)
            for plat, ps in fallback.items():
                ps.posting_frequency = freq.get(plat)
                platforms_list.append(ps)

        if not platforms_list:
            continue

        items.append(RankingItem(
            advertiser_id=adv.id,
            name=adv.name,
            brand_name=adv.brand_name,
            logo_url=adv.logo_url,
            platforms=platforms_list,
        ))

    # Sort
    def _sort_key(item: RankingItem) -> float:
        vals: list[float] = []
        for p in item.platforms:
            if sort_by == "subscribers":
                vals.append(float(p.subscribers or p.followers or 0))
            elif sort_by == "posts":
                vals.append(float(p.total_posts or 0))
            elif sort_by == "engagement":
                vals.append(float(p.engagement_rate or 0.0))
            else:
                vals.append(float(p.subscribers or p.followers or 0))
        return max(vals) if vals else 0.0

    items.sort(key=_sort_key, reverse=True)
    total = len(items)
    items = items[:limit]

    return RankingsResponse(items=items, total=total)


@router.get("/compare", response_model=CompareResponse)
async def compare_advertisers(
    advertiser_ids: str = Query(..., description="Comma-separated advertiser IDs"),
    days: int = Query(30, le=365, description="Lookback period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Compare specific advertisers side by side."""
    try:
        parsed_ids = [int(x.strip()) for x in advertiser_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="advertiser_ids must be comma-separated integers")
    if not parsed_ids:
        raise HTTPException(status_code=400, detail="advertiser_ids is required")
    if len(parsed_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 advertisers for comparison")

    cutoff = datetime.now(KST) - timedelta(days=days)

    # Fetch advertisers
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id.in_(parsed_ids))
    )
    advertisers = {a.id: a for a in adv_result.scalars().all()}

    items: list[CompareItem] = []
    for adv_id in parsed_ids:
        adv = advertisers.get(adv_id)
        if not adv:
            continue

        # Channel stats
        stats = await _get_latest_channel_stats(db, advertiser_id=adv_id)
        freq = await _posting_frequency(db, adv_id, None, cutoff)

        platforms_list: list[PlatformStats] = []
        if stats:
            for cs in stats:
                eng_rate = cs.engagement_rate
                avg_likes_val = cs.avg_likes
                avg_views_val = cs.avg_views

                if eng_rate is None or avg_likes_val is None:
                    cs_content = await _compute_content_stats(db, adv_id, cs.platform, cutoff)
                    cs_fb = cs_content.get(cs.platform)
                    if cs_fb:
                        if avg_likes_val is None:
                            avg_likes_val = cs_fb.avg_likes
                        if avg_views_val is None:
                            avg_views_val = cs_fb.avg_views
                    if eng_rate is None:
                        base = cs.subscribers or cs.followers or 0
                        if base > 0:
                            interaction = avg_likes_val if (avg_likes_val and avg_likes_val > 0) else (
                                (avg_views_val * 0.03) if (avg_views_val and avg_views_val > 0) else None
                            )
                            if interaction and interaction > 0:
                                eng_rate = round((interaction / base) * 100, 4)

                platforms_list.append(PlatformStats(
                    platform=cs.platform,
                    subscribers=cs.subscribers,
                    followers=cs.followers,
                    total_posts=cs.total_posts,
                    avg_likes=avg_likes_val,
                    avg_views=avg_views_val,
                    engagement_rate=eng_rate,
                    posting_frequency=freq.get(cs.platform),
                ))
        else:
            fallback = await _compute_content_stats(db, adv_id, None, cutoff)
            for plat, ps in fallback.items():
                ps.posting_frequency = freq.get(plat)
                platforms_list.append(ps)

        # Posting trend
        trend = await _daily_post_counts(db, adv_id, cutoff)

        items.append(CompareItem(
            advertiser_id=adv.id,
            name=adv.name,
            brand_name=adv.brand_name,
            logo_url=adv.logo_url,
            platforms=platforms_list,
            posting_trend=trend,
        ))

    return CompareResponse(items=items)


# ── Dynamic-path endpoint ──


@router.get("/{advertiser_id}", response_model=AdvertiserDetailResponse)
async def get_advertiser_detail(
    advertiser_id: int,
    days: int = Query(30, le=365, description="Lookback period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Single advertiser social channel detail."""
    # Fetch advertiser
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    adv = result.scalar_one_or_none()
    if not adv:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    cutoff = datetime.now(KST) - timedelta(days=days)

    # Channel stats
    stats = await _get_latest_channel_stats(db, advertiser_id=advertiser_id)
    freq = await _posting_frequency(db, advertiser_id, None, cutoff)

    platforms_list: list[PlatformStats] = []
    if stats:
        for cs in stats:
            eng_rate = cs.engagement_rate
            avg_likes_val = cs.avg_likes
            avg_views_val = cs.avg_views

            if eng_rate is None or avg_likes_val is None:
                cs_content = await _compute_content_stats(db, advertiser_id, cs.platform, cutoff)
                cs_fb = cs_content.get(cs.platform)
                if cs_fb:
                    if avg_likes_val is None:
                        avg_likes_val = cs_fb.avg_likes
                    if avg_views_val is None:
                        avg_views_val = cs_fb.avg_views
                if eng_rate is None:
                    base = cs.subscribers or cs.followers or 0
                    if base > 0:
                        interaction = avg_likes_val if (avg_likes_val and avg_likes_val > 0) else (
                            (avg_views_val * 0.03) if (avg_views_val and avg_views_val > 0) else None
                        )
                        if interaction and interaction > 0:
                            eng_rate = round((interaction / base) * 100, 4)

            platforms_list.append(PlatformStats(
                platform=cs.platform,
                subscribers=cs.subscribers,
                followers=cs.followers,
                total_posts=cs.total_posts,
                avg_likes=avg_likes_val,
                avg_views=avg_views_val,
                engagement_rate=eng_rate,
                posting_frequency=freq.get(cs.platform),
            ))
    else:
        fallback = await _compute_content_stats(db, advertiser_id, None, cutoff)
        for plat, ps in fallback.items():
            ps.posting_frequency = freq.get(plat)
            platforms_list.append(ps)

    # Recent posts
    recent_result = await db.execute(
        select(BrandChannelContent)
        .where(BrandChannelContent.advertiser_id == advertiser_id)
        .order_by(desc(BrandChannelContent.discovered_at))
        .limit(20)
    )
    recent_rows = recent_result.scalars().all()
    recent_posts = [
        ContentItem(
            id=r.id,
            platform=r.platform,
            channel_url=r.channel_url,
            content_id=r.content_id,
            content_type=r.content_type,
            title=r.title,
            thumbnail_url=r.thumbnail_url,
            upload_date=r.upload_date,
            view_count=r.view_count,
            like_count=r.like_count,
            duration_seconds=r.duration_seconds,
            is_ad_content=r.is_ad_content,
            discovered_at=r.discovered_at,
        )
        for r in recent_rows
    ]

    # Posting trend
    trend = await _daily_post_counts(db, advertiser_id, cutoff)

    return AdvertiserDetailResponse(
        advertiser_id=adv.id,
        name=adv.name,
        brand_name=adv.brand_name,
        logo_url=adv.logo_url,
        platforms=platforms_list,
        recent_posts=recent_posts,
        posting_trend=trend,
    )
