"""Launch Impact Analysis API -- product CRUD + impact scores."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_paid
from database import get_db
from database.models import (
    Advertiser,
    LaunchImpactScore,
    LaunchMention,
    LaunchProduct,
    User,
)
from database.schemas import (
    LaunchImpactOverviewOut,
    LaunchImpactRankingItem,
    LaunchImpactTimelineOut,
    LaunchMentionOut,
    LaunchProductCreateIn,
    LaunchProductOut,
    LaunchProductUpdateIn,
)

router = APIRouter(prefix="/api/launch-impact", tags=["launch-impact"],
    dependencies=[Depends(get_current_user)])


# ── Product CRUD ──

@router.post("/products", response_model=LaunchProductOut)
async def create_product(
    data: LaunchProductCreateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new launch product for tracking."""
    if data.category not in ("game", "commerce", "product"):
        raise HTTPException(400, "category must be game, commerce, or product")
    if not data.keywords:
        raise HTTPException(400, "At least one keyword required")

    # Verify advertiser exists
    adv = (await db.execute(
        select(Advertiser).where(Advertiser.id == data.advertiser_id)
    )).scalar_one_or_none()
    if not adv:
        raise HTTPException(404, "Advertiser not found")

    product = LaunchProduct(
        advertiser_id=data.advertiser_id,
        name=data.name,
        category=data.category,
        launch_date=data.launch_date,
        product_url=data.product_url,
        external_id=data.external_id,
        keywords=data.keywords,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/products", response_model=list[LaunchProductOut])
async def list_products(
    category: str | None = None,
    advertiser_id: int | None = None,
    is_active: bool = True,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List tracked launch products."""
    query = select(LaunchProduct).where(
        LaunchProduct.is_active == is_active
    ).order_by(LaunchProduct.launch_date.desc()).limit(limit)

    if category:
        query = query.where(LaunchProduct.category == category)
    if advertiser_id:
        query = query.where(LaunchProduct.advertiser_id == advertiser_id)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/products/{product_id}", response_model=LaunchProductOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    """Get a single product."""
    product = (await db.execute(
        select(LaunchProduct).where(LaunchProduct.id == product_id)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@router.put("/products/{product_id}", response_model=LaunchProductOut)
async def update_product(
    product_id: int,
    data: LaunchProductUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a product's details."""
    product = (await db.execute(
        select(LaunchProduct).where(LaunchProduct.id == product_id)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    product.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a product (soft delete)."""
    product = (await db.execute(
        select(LaunchProduct).where(LaunchProduct.id == product_id)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    product.is_active = False
    product.updated_at = datetime.utcnow()
    await db.commit()
    return {"status": "ok"}


# ── Score Endpoints ──

@router.get("/{product_id}/overview")
async def get_overview(product_id: int, db: AsyncSession = Depends(get_db)):
    """Get latest impact scores for a product."""
    product = (await db.execute(
        select(LaunchProduct).where(LaunchProduct.id == product_id)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")

    score = (await db.execute(
        select(LaunchImpactScore)
        .where(LaunchImpactScore.launch_product_id == product_id)
        .order_by(LaunchImpactScore.date.desc())
        .limit(1)
    )).scalar_one_or_none()

    launch_dt = product.launch_date
    if launch_dt and launch_dt.tzinfo:
        launch_dt = launch_dt.replace(tzinfo=None)
    days_since = (datetime.utcnow() - launch_dt).days if launch_dt else 0

    return {
        "launch_product_id": product.id,
        "product_name": product.name,
        "category": product.category,
        "launch_date": product.launch_date.isoformat() if product.launch_date else None,
        "days_since_launch": days_since,
        "date": score.date.isoformat() if score else None,
        "mrs_score": score.mrs_score if score else 0.0,
        "rv_score": score.rv_score if score else 0.0,
        "cs_score": score.cs_score if score else 0.0,
        "lii_score": score.lii_score if score else 0.0,
        "total_mentions": score.total_mentions if score else 0,
        "impact_phase": score.impact_phase if score else None,
        "factors": score.factors if score else None,
    }


@router.get("/{product_id}/timeline")
async def get_timeline(
    product_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get daily score time-series."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    result = await db.execute(
        select(LaunchImpactScore)
        .where(
            and_(
                LaunchImpactScore.launch_product_id == product_id,
                LaunchImpactScore.date >= cutoff,
            )
        )
        .order_by(LaunchImpactScore.date.asc())
    )
    rows = result.scalars().all()
    return [
        {
            "date": r.date.isoformat(),
            "mrs_score": r.mrs_score,
            "rv_score": r.rv_score,
            "cs_score": r.cs_score,
            "lii_score": r.lii_score,
            "total_mentions": r.total_mentions,
            "impact_phase": r.impact_phase,
        }
        for r in rows
    ]


@router.get("/{product_id}/mentions")
async def get_mentions(
    product_id: int,
    days: int = Query(30, ge=1, le=365),
    source_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get recent mentions for a product."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    query = (
        select(LaunchMention)
        .where(
            and_(
                LaunchMention.launch_product_id == product_id,
                LaunchMention.collected_at >= cutoff,
            )
        )
        .order_by(LaunchMention.published_at.desc().nullslast())
        .limit(limit)
    )
    if source_type:
        query = query.where(LaunchMention.source_type == source_type)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "source_type": r.source_type,
            "source_platform": r.source_platform,
            "url": r.url,
            "title": r.title,
            "author": r.author,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "view_count": r.view_count,
            "like_count": r.like_count,
            "comment_count": r.comment_count,
            "sentiment": r.sentiment,
            "matched_keyword": r.matched_keyword,
        }
        for r in rows
    ]


@router.get("/ranking")
async def get_ranking(
    days: int = Query(30, ge=1, le=365),
    category: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get top products ranked by LII score."""
    # Subquery: latest score per product
    latest_sq = (
        select(
            LaunchImpactScore.launch_product_id,
            func.max(LaunchImpactScore.date).label("max_date"),
        )
        .group_by(LaunchImpactScore.launch_product_id)
        .subquery()
    )

    query = (
        select(
            LaunchImpactScore,
            LaunchProduct.name.label("product_name"),
            LaunchProduct.advertiser_id,
            LaunchProduct.category,
            LaunchProduct.launch_date,
            Advertiser.name.label("advertiser_name"),
        )
        .join(
            latest_sq,
            and_(
                LaunchImpactScore.launch_product_id == latest_sq.c.launch_product_id,
                LaunchImpactScore.date == latest_sq.c.max_date,
            ),
        )
        .join(LaunchProduct, LaunchProduct.id == LaunchImpactScore.launch_product_id)
        .join(Advertiser, Advertiser.id == LaunchProduct.advertiser_id)
        .where(LaunchProduct.is_active == True)  # noqa: E712
        .order_by(LaunchImpactScore.lii_score.desc())
        .limit(limit)
    )

    if category:
        query = query.where(LaunchProduct.category == category)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "launch_product_id": row.LaunchImpactScore.launch_product_id,
            "product_name": row.product_name,
            "advertiser_id": row.advertiser_id,
            "advertiser_name": row.advertiser_name,
            "category": row.category,
            "launch_date": row.launch_date.isoformat() if row.launch_date else None,
            "lii_score": row.LaunchImpactScore.lii_score,
            "mrs_score": row.LaunchImpactScore.mrs_score,
            "rv_score": row.LaunchImpactScore.rv_score,
            "cs_score": row.LaunchImpactScore.cs_score,
            "total_mentions": row.LaunchImpactScore.total_mentions,
            "impact_phase": row.LaunchImpactScore.impact_phase,
        }
        for row in rows
    ]


# ── Admin Triggers ──

@router.post("/collect")
async def trigger_collection(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger immediate mention collection (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")

    from processor.launch_mention_collector import collect_launch_mentions
    result = await collect_launch_mentions()
    return result


@router.post("/calculate")
async def trigger_calculation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger immediate score calculation (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")

    from processor.launch_impact_scorer import calculate_launch_impact_scores
    result = await calculate_launch_impact_scores()
    return result
