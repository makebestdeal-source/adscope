"""SmartStore sales estimation API router."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_paid
from database import get_db
from database.models import SmartStoreSnapshot, SmartStoreTrackedProduct, User
from database.schemas import (
    SmartStoreCompareIn,
    SmartStoreSalesEstimation,
    SmartStoreSnapshotOut,
    SmartStoreTrackIn,
    SmartStoreTrackedOut,
)
from processor.smartstore_sales_estimator import estimate_product_sales

router = APIRouter(prefix="/api/smartstore", tags=["smartstore"],
    dependencies=[Depends(get_current_user)])


# ── Tracking CRUD ──

@router.post("/track", response_model=SmartStoreTrackedOut)
async def track_product(
    data: SmartStoreTrackIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a SmartStore product URL to tracking."""
    if "smartstore.naver.com" not in data.product_url:
        raise HTTPException(400, "Only smartstore.naver.com URLs are supported")

    # Check duplicate
    existing = (
        await db.execute(
            select(SmartStoreTrackedProduct).where(
                and_(
                    SmartStoreTrackedProduct.user_id == current_user.id,
                    SmartStoreTrackedProduct.product_url == data.product_url,
                    SmartStoreTrackedProduct.is_active == True,  # noqa: E712
                )
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Already tracking this product")

    import re
    match = re.search(r"smartstore\.naver\.com/([^/?#]+)", data.product_url)
    store_name = match.group(1) if match else None

    tp = SmartStoreTrackedProduct(
        user_id=current_user.id,
        product_url=data.product_url,
        store_name=store_name,
        label=data.label,
    )
    db.add(tp)
    await db.commit()
    await db.refresh(tp)
    return tp


@router.get("/tracked", response_model=list[SmartStoreTrackedOut])
async def list_tracked(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's tracked products."""
    result = await db.execute(
        select(SmartStoreTrackedProduct)
        .where(
            and_(
                SmartStoreTrackedProduct.user_id == current_user.id,
                SmartStoreTrackedProduct.is_active == True,  # noqa: E712
            )
        )
        .order_by(SmartStoreTrackedProduct.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/tracked/{tracked_id}")
async def untrack_product(
    tracked_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a tracked product."""
    tp = (
        await db.execute(
            select(SmartStoreTrackedProduct).where(
                and_(
                    SmartStoreTrackedProduct.id == tracked_id,
                    SmartStoreTrackedProduct.user_id == current_user.id,
                )
            )
        )
    ).scalar_one_or_none()
    if not tp:
        raise HTTPException(404, "Tracked product not found")
    tp.is_active = False
    await db.commit()
    return {"status": "ok"}


# ── Sales data ──

@router.get("/sales")
async def get_sales_estimation(
    product_url: str,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get sales estimation + timeline for a product URL."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    result = await db.execute(
        select(SmartStoreSnapshot)
        .where(
            and_(
                SmartStoreSnapshot.product_url == product_url,
                SmartStoreSnapshot.captured_at >= cutoff,
            )
        )
        .order_by(SmartStoreSnapshot.captured_at.asc())
    )
    snapshots = result.scalars().all()

    estimation = estimate_product_sales(snapshots)

    latest = snapshots[-1] if snapshots else None

    timeline = []
    for s in snapshots:
        timeline.append({
            "date": s.captured_at.isoformat() if s.captured_at else None,
            "stock_quantity": s.stock_quantity,
            "purchase_cnt": s.purchase_cnt,
            "review_count": s.review_count,
            "review_delta": s.review_delta,
            "price": s.price,
            "wishlist_count": s.wishlist_count,
            "avg_rating": s.avg_rating,
            "estimated_daily_sales": s.estimated_daily_sales,
        })

    return {
        "product_url": product_url,
        "store_name": latest.store_name if latest else None,
        "product_name": latest.product_name if latest else None,
        "category_name": latest.category_name if latest else None,
        "seller_grade": latest.seller_grade if latest else None,
        "latest": {
            "stock_quantity": latest.stock_quantity if latest else None,
            "purchase_cnt": latest.purchase_cnt if latest else None,
            "review_count": latest.review_count if latest else None,
            "price": latest.price if latest else None,
            "avg_rating": latest.avg_rating if latest else None,
            "wishlist_count": latest.wishlist_count if latest else None,
            "discount_pct": latest.discount_pct if latest else None,
        } if latest else None,
        "estimation": estimation,
        "timeline": timeline,
        "snapshot_count": len(snapshots),
    }


# ── Compare ──

@router.post("/compare")
async def compare_products(
    data: SmartStoreCompareIn,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Compare up to 5 products side by side."""
    if len(data.product_urls) > 5:
        raise HTTPException(400, "Maximum 5 products for comparison")

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    products = []

    for url in data.product_urls:
        result = await db.execute(
            select(SmartStoreSnapshot)
            .where(
                and_(
                    SmartStoreSnapshot.product_url == url,
                    SmartStoreSnapshot.captured_at >= cutoff,
                )
            )
            .order_by(SmartStoreSnapshot.captured_at.asc())
        )
        snaps = result.scalars().all()
        estimation = estimate_product_sales(snaps)
        latest = snaps[-1] if snaps else None

        products.append({
            "product_url": url,
            "store_name": latest.store_name if latest else None,
            "product_name": latest.product_name if latest else None,
            "price": latest.price if latest else None,
            "review_count": latest.review_count if latest else None,
            "avg_rating": latest.avg_rating if latest else None,
            "stock_quantity": latest.stock_quantity if latest else None,
            "purchase_cnt": latest.purchase_cnt if latest else None,
            "seller_grade": latest.seller_grade if latest else None,
            "estimation": estimation,
            "snapshot_count": len(snaps),
        })

    return {"products": products}


# ── Dashboard ──

@router.get("/dashboard")
async def smartstore_dashboard(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard summary for current user's tracked products."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Get user's tracked products
    tracked_result = await db.execute(
        select(SmartStoreTrackedProduct).where(
            and_(
                SmartStoreTrackedProduct.user_id == current_user.id,
                SmartStoreTrackedProduct.is_active == True,  # noqa: E712
            )
        )
    )
    tracked = tracked_result.scalars().all()
    tracked_urls = [t.product_url for t in tracked]

    total_tracked = len(tracked)
    products_with_data = []

    for url in tracked_urls:
        result = await db.execute(
            select(SmartStoreSnapshot)
            .where(
                and_(
                    SmartStoreSnapshot.product_url == url,
                    SmartStoreSnapshot.captured_at >= cutoff,
                )
            )
            .order_by(SmartStoreSnapshot.captured_at.asc())
        )
        snaps = result.scalars().all()
        if not snaps:
            continue

        estimation = estimate_product_sales(snaps)
        latest = snaps[-1]
        products_with_data.append({
            "product_url": url,
            "store_name": latest.store_name,
            "product_name": latest.product_name,
            "price": latest.price,
            "review_count": latest.review_count,
            "stock_quantity": latest.stock_quantity,
            "estimation": estimation,
        })

    # Sort by daily sales descending
    products_with_data.sort(
        key=lambda x: x["estimation"]["estimated_daily_sales"],
        reverse=True,
    )

    total_daily_sales = sum(
        p["estimation"]["estimated_daily_sales"] for p in products_with_data
    )
    total_daily_revenue = sum(
        p["estimation"]["estimated_daily_revenue"] for p in products_with_data
    )

    # Alerts: low stock, price drops, etc.
    alerts = []
    for p in products_with_data:
        if p.get("stock_quantity") is not None and p["stock_quantity"] < 10:
            alerts.append({
                "product_url": p["product_url"],
                "type": "stock_low",
                "message": f"{p.get('product_name', 'Unknown')} - stock {p['stock_quantity']}",
            })

    return {
        "total_tracked": total_tracked,
        "total_with_data": len(products_with_data),
        "total_daily_sales": total_daily_sales,
        "total_daily_revenue": total_daily_revenue,
        "total_monthly_revenue": total_daily_revenue * 30,
        "top_sellers": products_with_data[:10],
        "alerts": alerts,
    }


# ── Collect Now (admin) ──

@router.post("/collect-now")
async def collect_now(
    current_user: User = Depends(get_current_user),
):
    """Trigger immediate SmartStore collection (admin only)."""
    if current_user.role != "admin":
        raise HTTPException(403, "Admin only")

    from processor.smartstore_collector import collect_smartstore_signals
    stats = await collect_smartstore_signals()

    from processor.smartstore_sales_estimator import update_sales_estimates
    est_stats = await update_sales_estimates()

    return {"collection": stats, "estimation": est_stats}
