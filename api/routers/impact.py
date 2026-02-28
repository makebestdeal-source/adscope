"""Impact Media Source Management API -- CRUD for media sources, parse profiles, crawl triggers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_admin, require_paid
from database import get_db
from database.models import (
    Advertiser,
    LaunchImpactScore,
    LaunchMention,
    LaunchProduct,
    MediaSource,
    ParseProfile,
    ReactionTimeseries,
    User,
)
from database.schemas import (
    MediaSourceCreate,
    MediaSourceOut,
    MediaSourceUpdate,
    ParseProfileCreate,
    ParseProfileOut,
    ReactionTimeseriesOut,
)

router = APIRouter(prefix="/api/impact", tags=["impact"],
    dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────
# Media Source CRUD (admin)
# ──────────────────────────────────────────

@router.post("/media-sources", response_model=MediaSourceOut)
async def create_media_source(
    data: MediaSourceCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if data.connector_type not in ("rss", "api_youtube", "html_list_detail"):
        raise HTTPException(400, "connector_type must be rss, api_youtube, or html_list_detail")
    source = MediaSource(**data.model_dump())
    db.add(source)
    await db.commit()
    await db.refresh(source)
    out = MediaSourceOut.model_validate(source)
    out.mention_count = 0
    return out


@router.get("/media-sources", response_model=list[MediaSourceOut])
async def list_media_sources(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MediaSource).order_by(MediaSource.created_at.desc())
    )
    sources = result.scalars().all()

    out = []
    for s in sources:
        count = (await db.execute(
            select(func.count(LaunchMention.id)).where(LaunchMention.media_source_id == s.id)
        )).scalar_one()
        item = MediaSourceOut.model_validate(s)
        item.mention_count = count
        out.append(item)
    return out


@router.patch("/media-sources/{source_id}", response_model=MediaSourceOut)
async def update_media_source(
    source_id: int,
    data: MediaSourceUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    source = (await db.execute(
        select(MediaSource).where(MediaSource.id == source_id)
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(404, "Media source not found")

    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(source, key, val)
    source.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(source)
    count = (await db.execute(
        select(func.count(LaunchMention.id)).where(LaunchMention.media_source_id == source.id)
    )).scalar_one()
    item = MediaSourceOut.model_validate(source)
    item.mention_count = count
    return item


# ──────────────────────────────────────────
# Parse Profile CRUD (admin)
# ──────────────────────────────────────────

@router.post("/parse-profiles", response_model=ParseProfileOut)
async def create_parse_profile(
    data: ParseProfileCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    profile = ParseProfile(**data.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return ParseProfileOut.model_validate(profile)


@router.get("/parse-profiles", response_model=list[ParseProfileOut])
async def list_parse_profiles(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ParseProfile).order_by(ParseProfile.id.desc()))
    return [ParseProfileOut.model_validate(p) for p in result.scalars().all()]


@router.post("/parse-profiles/{profile_id}/test")
async def test_parse_profile(
    profile_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Test a parse profile against its test_url; return up to 5 preview items."""
    profile = (await db.execute(
        select(ParseProfile).where(ParseProfile.id == profile_id)
    )).scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Parse profile not found")
    if not profile.test_url:
        raise HTTPException(400, "No test_url configured")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise HTTPException(500, "playwright not installed")

    results = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(profile.test_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)

            if profile.list_selector:
                elements = await page.query_selector_all(profile.list_selector)
                for el in elements[:5]:
                    href = await el.get_attribute("href")
                    text = (await el.inner_text()).strip()
                    results.append({"title": text, "url": href})

            await browser.close()
    except Exception as e:
        raise HTTPException(500, f"Test failed: {str(e)}")

    return {"profile_id": profile_id, "test_url": profile.test_url, "preview": results}


# ──────────────────────────────────────────
# Reactions timeseries
# ──────────────────────────────────────────

@router.get("/products/{product_id}/reactions", response_model=list[ReactionTimeseriesOut])
async def get_product_reactions(
    product_id: int,
    metric_type: str | None = None,
    days: int = Query(30, ge=1, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = select(ReactionTimeseries).where(and_(
        ReactionTimeseries.launch_product_id == product_id,
        ReactionTimeseries.timestamp >= cutoff,
    ))
    if metric_type:
        query = query.where(ReactionTimeseries.metric_type == metric_type)
    query = query.order_by(ReactionTimeseries.timestamp.asc())
    result = await db.execute(query)
    return [ReactionTimeseriesOut.model_validate(r) for r in result.scalars().all()]


# ──────────────────────────────────────────
# Advertiser lookup (find products by advertiser)
# ──────────────────────────────────────────

@router.get("/by-advertiser/{advertiser_id}")
async def get_impact_by_advertiser(
    advertiser_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all launch products and their latest scores for an advertiser."""
    products = (await db.execute(
        select(LaunchProduct)
        .where(LaunchProduct.advertiser_id == advertiser_id)
        .order_by(LaunchProduct.launch_date.desc())
    )).scalars().all()

    results = []
    for product in products:
        latest = (await db.execute(
            select(LaunchImpactScore)
            .where(LaunchImpactScore.launch_product_id == product.id)
            .order_by(LaunchImpactScore.date.desc())
            .limit(1)
        )).scalar_one_or_none()

        mention_count = (await db.execute(
            select(func.count(LaunchMention.id))
            .where(LaunchMention.launch_product_id == product.id)
        )).scalar_one()

        results.append({
            "product": {
                "id": product.id,
                "name": product.name,
                "category": product.category,
                "launch_date": product.launch_date.isoformat() if product.launch_date else None,
                "is_active": product.is_active,
            },
            "latest_score": {
                "lii_score": latest.lii_score if latest else 0.0,
                "mrs_score": latest.mrs_score if latest else 0.0,
                "rv_score": latest.rv_score if latest else 0.0,
                "cs_score": latest.cs_score if latest else 0.0,
                "total_mentions": latest.total_mentions if latest else 0,
                "impact_phase": latest.impact_phase if latest else None,
                "date": latest.date.isoformat() if latest and latest.date else None,
            },
            "mention_count": mention_count,
        })
    return results


# ──────────────────────────────────────────
# Admin: collection controls
# ──────────────────────────────────────────

@router.get("/crawl-log")
async def get_crawl_log(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Collection status per media source."""
    result = await db.execute(
        select(MediaSource).order_by(MediaSource.last_crawl_at.desc().nullslast())
    )
    sources = result.scalars().all()

    log_items = []
    for s in sources:
        count = (await db.execute(
            select(func.count(LaunchMention.id)).where(LaunchMention.media_source_id == s.id)
        )).scalar_one()
        log_items.append({
            "media_source_id": s.id,
            "media_source_name": s.name,
            "connector_type": s.connector_type,
            "is_active": s.is_active,
            "last_crawl_at": s.last_crawl_at.isoformat() if s.last_crawl_at else None,
            "error_count": s.error_count,
            "error_rate": s.error_rate,
            "mention_count": count,
        })
    return log_items


@router.post("/crawl-now")
async def trigger_crawl_now(
    admin: User = Depends(require_admin),
):
    """Trigger immediate mention collection from all media sources."""
    try:
        from processor.launch_mention_collector import crawl_media_sources
        stats = await crawl_media_sources()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("[impact] crawl-now failed")
        raise HTTPException(500, f"Crawl failed: {str(e)}")


@router.post("/calc-scores")
async def trigger_calc_scores(
    admin: User = Depends(require_admin),
):
    """Trigger immediate score calculation."""
    try:
        from processor.launch_impact_scorer import calculate_launch_impact_scores
        stats = await calculate_launch_impact_scores()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.exception("[impact] calc-scores failed")
        raise HTTPException(500, f"Score calculation failed: {str(e)}")
