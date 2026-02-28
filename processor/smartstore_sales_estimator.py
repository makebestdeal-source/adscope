"""SmartStore sales estimation engine.

3 methods combined with weighted average:
  1. Stock delta (weight 0.5) -- prev_stock - curr_stock
  2. purchaseCnt delta (weight 0.3) -- cumulative purchase count changes
  3. Review velocity (weight 0.2) -- review_delta * 35 (mid-point ratio)

Run after smartstore_collector to update estimated_daily_sales on latest snapshots.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, distinct, func, select, update

from database import async_session
from database.models import SmartStoreSnapshot

logger = logging.getLogger(__name__)

WEIGHTS = {"stock": 0.5, "purchase_cnt": 0.3, "review": 0.2}
REVIEW_TO_PURCHASE_RATIO = 35  # 1 review ~ 20-50 purchases, use midpoint


def _estimate_from_stock(snapshots: list[SmartStoreSnapshot]) -> int | None:
    """Sales from stock quantity decreases (ignoring restocks)."""
    deltas = []
    for i in range(1, len(snapshots)):
        prev = snapshots[i - 1].stock_quantity
        curr = snapshots[i].stock_quantity
        if prev is not None and curr is not None:
            d = prev - curr
            if d > 0:  # decrease = sales
                deltas.append(d)
    return round(sum(deltas) / len(deltas)) if deltas else None


def _estimate_from_purchase_cnt(snapshots: list[SmartStoreSnapshot]) -> int | None:
    """Sales from cumulative purchaseCnt daily changes."""
    deltas = []
    for i in range(1, len(snapshots)):
        prev = snapshots[i - 1].purchase_cnt
        curr = snapshots[i].purchase_cnt
        if prev is not None and curr is not None:
            d = curr - prev
            if d >= 0:
                deltas.append(d)
    return round(sum(deltas) / len(deltas)) if deltas else None


def _estimate_from_reviews(snapshots: list[SmartStoreSnapshot]) -> int | None:
    """Sales from review growth rate * purchase-to-review ratio."""
    review_deltas = [
        s.review_delta for s in snapshots
        if s.review_delta is not None and s.review_delta > 0
    ]
    if not review_deltas:
        return None
    avg_delta = sum(review_deltas) / len(review_deltas)
    return round(avg_delta * REVIEW_TO_PURCHASE_RATIO)


def estimate_product_sales(snapshots: list[SmartStoreSnapshot]) -> dict:
    """Compute composite sales estimate from multiple methods.

    Returns:
        {
            "estimated_daily_sales": int,
            "estimated_daily_revenue": int,
            "estimated_monthly_revenue": int,
            "methods": {"stock": N, "purchase_cnt": N, "review": N},
            "primary_method": str,
            "confidence": float (0.0 ~ 1.0),
        }
    """
    if not snapshots:
        return {
            "estimated_daily_sales": 0,
            "estimated_daily_revenue": 0,
            "estimated_monthly_revenue": 0,
            "methods": {},
            "primary_method": None,
            "confidence": 0.0,
        }

    estimates = {}

    stock_est = _estimate_from_stock(snapshots)
    if stock_est is not None:
        estimates["stock"] = stock_est

    purchase_est = _estimate_from_purchase_cnt(snapshots)
    if purchase_est is not None:
        estimates["purchase_cnt"] = purchase_est

    review_est = _estimate_from_reviews(snapshots)
    if review_est is not None:
        estimates["review"] = review_est

    if not estimates:
        return {
            "estimated_daily_sales": 0,
            "estimated_daily_revenue": 0,
            "estimated_monthly_revenue": 0,
            "methods": {},
            "primary_method": None,
            "confidence": 0.0,
        }

    total_w = sum(WEIGHTS[m] for m in estimates)
    composite = sum(estimates[m] * WEIGHTS[m] for m in estimates) / total_w

    latest_price = next(
        (s.price for s in reversed(snapshots) if s.price), 0
    )
    daily_sales = round(composite)
    daily_revenue = daily_sales * latest_price
    monthly_revenue = daily_revenue * 30

    # Confidence: more methods + more data points = higher confidence
    method_factor = len(estimates) / 3.0
    data_factor = min(1.0, len(snapshots) / 7.0)
    confidence = round(method_factor * 0.6 + data_factor * 0.4, 2)

    primary = max(estimates, key=lambda m: WEIGHTS[m]) if estimates else None

    return {
        "estimated_daily_sales": daily_sales,
        "estimated_daily_revenue": daily_revenue,
        "estimated_monthly_revenue": monthly_revenue,
        "methods": estimates,
        "primary_method": primary,
        "confidence": confidence,
    }


async def update_sales_estimates(session=None) -> dict:
    """Update estimated_daily_sales for all product URLs with recent data.

    Returns: {"updated": N, "urls_processed": N}
    """
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=7)

        # Get distinct product_urls with recent data
        urls_result = await session.execute(
            select(distinct(SmartStoreSnapshot.product_url)).where(
                and_(
                    SmartStoreSnapshot.captured_at >= cutoff,
                    SmartStoreSnapshot.product_url.isnot(None),
                )
            )
        )
        urls = [r[0] for r in urls_result.fetchall() if r[0]]

        updated = 0
        for url in urls:
            snaps_result = await session.execute(
                select(SmartStoreSnapshot)
                .where(
                    and_(
                        SmartStoreSnapshot.product_url == url,
                        SmartStoreSnapshot.captured_at >= cutoff,
                    )
                )
                .order_by(SmartStoreSnapshot.captured_at.asc())
            )
            snaps = snaps_result.scalars().all()
            if len(snaps) < 2:
                continue

            est = estimate_product_sales(snaps)
            if est["estimated_daily_sales"] > 0:
                # Update the latest snapshot
                latest = snaps[-1]
                latest.estimated_daily_sales = est["estimated_daily_sales"]
                latest.estimation_method = est["primary_method"] or "composite"
                updated += 1

        await session.commit()
        logger.info(
            "[smartstore_estimator] urls_processed=%d updated=%d",
            len(urls), updated,
        )
        return {"urls_processed": len(urls), "updated": updated}

    finally:
        if own_session:
            await session.close()
