"""Staging monitoring API -- view wash results, approve/reject quarantine ads."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import StagingAd
from processor.data_washer import promote_approved

router = APIRouter(prefix="/api/staging", tags=["staging"])


@router.get("/stats")
async def staging_stats(db: AsyncSession = Depends(get_db)):
    """Overall staging statistics."""
    result = await db.execute(
        select(
            StagingAd.status,
            func.count(StagingAd.id),
        ).group_by(StagingAd.status)
    )
    status_counts = {row[0]: row[1] for row in result.fetchall()}

    total = sum(status_counts.values())
    return {
        "total": total,
        "approved": status_counts.get("approved", 0),
        "rejected": status_counts.get("rejected", 0),
        "quarantine": status_counts.get("quarantine", 0),
        "pending": status_counts.get("pending", 0),
        "promoted": (
            await db.execute(
                select(func.count(StagingAd.id)).where(StagingAd.promoted_at.isnot(None))
            )
        ).scalar() or 0,
    }


@router.get("/batches")
async def list_batches(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List recent batches with status summary."""
    # Get distinct batch_ids ordered by most recent
    batch_q = (
        select(
            StagingAd.batch_id,
            StagingAd.channel,
            func.min(StagingAd.created_at).label("created_at"),
            func.count(StagingAd.id).label("total"),
            func.sum(func.iif(StagingAd.status == "approved", 1, 0)).label("approved"),
            func.sum(func.iif(StagingAd.status == "rejected", 1, 0)).label("rejected"),
            func.sum(func.iif(StagingAd.status == "quarantine", 1, 0)).label("quarantine"),
            func.sum(func.iif(StagingAd.status == "pending", 1, 0)).label("pending_count"),
            func.sum(func.iif(StagingAd.promoted_at.isnot(None), 1, 0)).label("promoted"),
        )
        .group_by(StagingAd.batch_id, StagingAd.channel)
        .order_by(func.min(StagingAd.created_at).desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(batch_q)
    batches = []
    for row in result.fetchall():
        batches.append({
            "batch_id": row.batch_id,
            "channel": row.channel,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "total": row.total,
            "approved": row.approved,
            "rejected": row.rejected,
            "quarantine": row.quarantine,
            "pending": row.pending_count,
            "promoted": row.promoted,
        })
    return batches


@router.get("/batch/{batch_id}")
async def batch_detail(batch_id: str, db: AsyncSession = Depends(get_db)):
    """Get all ads in a batch with wash results."""
    result = await db.execute(
        select(StagingAd).where(StagingAd.batch_id == batch_id).order_by(StagingAd.id)
    )
    rows = result.scalars().all()
    if not rows:
        raise HTTPException(404, "Batch not found")

    ads = []
    for r in rows:
        payload = r.raw_payload or {}
        ads.append({
            "id": r.id,
            "status": r.status,
            "rejection_reason": r.rejection_reason,
            "wash_score": r.wash_score,
            "channel": r.channel,
            "keyword": r.keyword,
            "advertiser_name": payload.get("advertiser_name"),
            "resolved_advertiser_name": r.resolved_advertiser_name,
            "ad_text": (payload.get("ad_text") or "")[:200],
            "url": payload.get("url"),
            "promoted_at": r.promoted_at.isoformat() if r.promoted_at else None,
            "promoted_ad_detail_id": r.promoted_ad_detail_id,
        })

    return {
        "batch_id": batch_id,
        "channel": rows[0].channel,
        "created_at": rows[0].created_at.isoformat() if rows[0].created_at else None,
        "total": len(ads),
        "ads": ads,
    }


@router.post("/approve/{batch_id}")
async def approve_batch(batch_id: str, db: AsyncSession = Depends(get_db)):
    """Approve quarantine ads in a batch and promote them."""
    # Move quarantine -> approved
    await db.execute(
        update(StagingAd)
        .where(
            StagingAd.batch_id == batch_id,
            StagingAd.status == "quarantine",
        )
        .values(status="approved", processed_at=datetime.utcnow())
    )
    await db.commit()

    # Promote newly approved
    result = await promote_approved(db, batch_id)
    return {"message": "Approved and promoted", **result}


@router.post("/reject/{batch_id}")
async def reject_batch(batch_id: str, db: AsyncSession = Depends(get_db)):
    """Reject all quarantine ads in a batch."""
    updated = await db.execute(
        update(StagingAd)
        .where(
            StagingAd.batch_id == batch_id,
            StagingAd.status == "quarantine",
        )
        .values(status="rejected", rejection_reason="manual_reject", processed_at=datetime.utcnow())
    )
    await db.commit()
    return {"message": "Rejected", "count": updated.rowcount}


@router.post("/approve-ad/{ad_id}")
async def approve_single_ad(ad_id: int, db: AsyncSession = Depends(get_db)):
    """Approve a single quarantine ad."""
    result = await db.execute(
        select(StagingAd).where(StagingAd.id == ad_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Staging ad not found")
    if row.status != "quarantine":
        raise HTTPException(400, f"Ad status is '{row.status}', not quarantine")

    row.status = "approved"
    row.processed_at = datetime.utcnow()
    await db.commit()

    # Promote this batch (only unpromoted approved ads)
    promote_result = await promote_approved(db, row.batch_id)
    return {"message": "Approved and promoted", **promote_result}


@router.post("/reject-ad/{ad_id}")
async def reject_single_ad(ad_id: int, reason: str = "manual_reject", db: AsyncSession = Depends(get_db)):
    """Reject a single quarantine ad."""
    result = await db.execute(
        select(StagingAd).where(StagingAd.id == ad_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Staging ad not found")

    row.status = "rejected"
    row.rejection_reason = reason
    row.processed_at = datetime.utcnow()
    await db.commit()
    return {"message": "Rejected"}
