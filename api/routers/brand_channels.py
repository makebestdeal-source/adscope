"""Brand channel monitoring API router.

Provides endpoints for managing advertiser official channels and
viewing monitored brand content.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from api.deps import get_current_user, require_admin, require_paid
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import Advertiser, BrandChannelContent, User
from database.schemas import BrandChannelContentOut, BrandChannelSummary

router = APIRouter(prefix="/api/brand-channels", tags=["brand-channels"],
    dependencies=[Depends(get_current_user)])


def _fix_thumbnail(row) -> BrandChannelContentOut:
    """IG CDN URL 만료 대비: extra_data.local_image_path가 있으면 thumbnail_url 교체."""
    out = BrandChannelContentOut.model_validate(row)
    extra = getattr(row, "extra_data", None) or {}
    local = extra.get("local_image_path") if isinstance(extra, dict) else None
    if local:
        import os
        if os.path.exists(local):
            # stored_images/xxx -> /images/xxx
            rel = local.replace("\\", "/")
            if rel.startswith("stored_images/"):
                rel = rel[len("stored_images/"):]
            out.thumbnail_url = f"/images/{rel}"
    return out


# ── Request schemas ──


class OfficialChannelsUpdate(BaseModel):
    """Request body for setting official channels on an advertiser."""
    official_channels: dict[str, str]


# ── Response schemas ──


class ChannelOverview(BaseModel):
    advertiser_id: int
    advertiser_name: str
    official_channels: dict[str, str] | None = None
    summaries: list[BrandChannelSummary] = []
    recent_contents: list[BrandChannelContentOut] = []


# ── Static-path endpoints (MUST come before /{advertiser_id} routes) ──


@router.get("/recent-uploads", response_model=list[BrandChannelContentOut])
async def get_recent_uploads(
    days: int = Query(7, le=90, description="Lookback period in days"),
    limit: int = Query(50, le=200, description="Max items to return"),
    platform: str | None = Query(None, description="Filter by platform"),
    is_ad: bool | None = Query(None, description="Filter by ad content flag"),
    db: AsyncSession = Depends(get_db),
):
    """Recent uploads across all monitored brand channels."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(BrandChannelContent)
        .where(BrandChannelContent.discovered_at >= cutoff)
    )

    if platform:
        stmt = stmt.where(BrandChannelContent.platform == platform)
    if is_ad is not None:
        stmt = stmt.where(BrandChannelContent.is_ad_content == is_ad)

    stmt = stmt.order_by(desc(BrandChannelContent.discovered_at)).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_fix_thumbnail(r) for r in rows]


@router.get("/stats/summary")
async def get_brand_channel_stats(
    db: AsyncSession = Depends(get_db),
):
    """KPI summary for brand channel monitoring.

    Returns counts of monitored brands, total channels, and new uploads this week.
    """
    # Count advertisers with official_channels
    brands_result = await db.execute(
        select(func.count(Advertiser.id)).where(
            Advertiser.official_channels.isnot(None)
        )
    )
    monitored_brands = brands_result.scalar() or 0

    # Total unique channel URLs
    channels_result = await db.execute(
        select(func.count(func.distinct(BrandChannelContent.channel_url)))
    )
    total_channels = channels_result.scalar() or 0

    # New uploads this week
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    new_result = await db.execute(
        select(func.count(BrandChannelContent.id)).where(
            BrandChannelContent.discovered_at >= week_ago
        )
    )
    new_this_week = new_result.scalar() or 0

    # Total content items
    total_result = await db.execute(
        select(func.count(BrandChannelContent.id))
    )
    total_contents = total_result.scalar() or 0

    # Ad content count
    ad_result = await db.execute(
        select(func.count(BrandChannelContent.id)).where(
            BrandChannelContent.is_ad_content == True  # noqa: E712
        )
    )
    ad_content_count = ad_result.scalar() or 0

    return {
        "monitored_brands": monitored_brands,
        "total_channels": total_channels,
        "total_contents": total_contents,
        "new_this_week": new_this_week,
        "ad_content_count": ad_content_count,
    }


# ── Dynamic-path endpoints ──


@router.get("/{advertiser_id}", response_model=ChannelOverview)
async def get_brand_channel_overview(
    advertiser_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Channel summary + recent contents for an advertiser.

    Returns advertiser info, channels dict, per-platform summaries,
    and the 20 most recent content items.
    """
    # Fetch advertiser
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    channels = advertiser.official_channels or {}

    # Per-platform summaries
    summaries = []
    platforms_result = await db.execute(
        select(
            BrandChannelContent.platform,
            BrandChannelContent.channel_url,
        )
        .where(BrandChannelContent.advertiser_id == advertiser_id)
        .group_by(BrandChannelContent.platform, BrandChannelContent.channel_url)
    )
    platform_rows = platforms_result.all()

    for row in platform_rows:
        platform, channel_url = row

        # Count totals
        count_result = await db.execute(
            select(func.count(BrandChannelContent.id)).where(
                BrandChannelContent.advertiser_id == advertiser_id,
                BrandChannelContent.platform == platform,
            )
        )
        total = count_result.scalar() or 0

        # Latest upload
        latest_result = await db.execute(
            select(func.max(BrandChannelContent.upload_date)).where(
                BrandChannelContent.advertiser_id == advertiser_id,
                BrandChannelContent.platform == platform,
            )
        )
        latest = latest_result.scalar()

        # Ad content count
        ad_result = await db.execute(
            select(func.count(BrandChannelContent.id)).where(
                BrandChannelContent.advertiser_id == advertiser_id,
                BrandChannelContent.platform == platform,
                BrandChannelContent.is_ad_content == True,  # noqa: E712
            )
        )
        ad_count = ad_result.scalar() or 0

        summaries.append(
            BrandChannelSummary(
                platform=platform,
                channel_url=channel_url,
                total_contents=total,
                latest_upload=latest,
                ad_content_count=ad_count,
            )
        )

    # Recent 20 contents
    recent_result = await db.execute(
        select(BrandChannelContent)
        .where(BrandChannelContent.advertiser_id == advertiser_id)
        .order_by(desc(BrandChannelContent.discovered_at))
        .limit(20)
    )
    recent_rows = recent_result.scalars().all()
    recent_contents = [_fix_thumbnail(r) for r in recent_rows]

    return ChannelOverview(
        advertiser_id=advertiser.id,
        advertiser_name=advertiser.name,
        official_channels=channels if isinstance(channels, dict) else None,
        summaries=summaries,
        recent_contents=recent_contents,
    )


@router.get("/{advertiser_id}/contents", response_model=list[BrandChannelContentOut])
async def get_brand_channel_contents(
    advertiser_id: int,
    platform: str | None = Query(None, description="Filter by platform (youtube/instagram)"),
    content_type: str | None = Query(None, description="Filter by content type (video/short/reel/post)"),
    is_ad: bool | None = Query(None, description="Filter by ad content flag"),
    days: int = Query(30, le=365, description="Lookback period in days"),
    limit: int = Query(50, le=200, description="Max items to return"),
    db: AsyncSession = Depends(get_db),
):
    """Filtered content list for an advertiser's brand channels."""
    # Verify advertiser exists
    adv_result = await db.execute(
        select(Advertiser.id).where(Advertiser.id == advertiser_id)
    )
    if not adv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Advertiser not found")

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = (
        select(BrandChannelContent)
        .where(
            BrandChannelContent.advertiser_id == advertiser_id,
            BrandChannelContent.discovered_at >= cutoff,
        )
    )

    if platform:
        stmt = stmt.where(BrandChannelContent.platform == platform)
    if content_type:
        stmt = stmt.where(BrandChannelContent.content_type == content_type)
    if is_ad is not None:
        stmt = stmt.where(BrandChannelContent.is_ad_content == is_ad)

    stmt = stmt.order_by(desc(BrandChannelContent.discovered_at)).limit(limit)

    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [_fix_thumbnail(r) for r in rows]


@router.put("/{advertiser_id}/channels")
async def set_official_channels(
    advertiser_id: int,
    body: OfficialChannelsUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set official_channels JSON on an advertiser.

    Example body:
    {
        "official_channels": {
            "youtube": "https://www.youtube.com/@BrandName",
            "instagram": "https://www.instagram.com/brandname/"
        }
    }
    """
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    advertiser.official_channels = body.official_channels
    advertiser.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "status": "ok",
        "advertiser_id": advertiser.id,
        "official_channels": body.official_channels,
    }
