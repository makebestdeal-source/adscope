"""Meta-signal API router -- overview, smartstore, traffic, activity, panel."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from api.deps import get_current_user, require_paid
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    ActivityScore,
    Advertiser,
    MetaSignalComposite,
    PanelObservation,
    SmartStoreSnapshot,
    TrafficSignal,
    User,
)
from database.schemas import (
    ActivityScoreOut,
    MetaSignalOverviewOut,
    PanelSubmitIn,
    PanelSummaryOut,
    SmartStoreSnapshotOut,
    TrafficSignalOut,
)

router = APIRouter(prefix="/api/meta-signals", tags=["meta-signals"],
    dependencies=[Depends(get_current_user)])


@router.get("/{advertiser_id}/overview", response_model=MetaSignalOverviewOut)
async def get_meta_signal_overview(
    advertiser_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get the latest composite meta-signal for an advertiser."""
    # Verify advertiser exists
    adv = (await db.execute(select(Advertiser).where(Advertiser.id == advertiser_id))).scalar_one_or_none()
    if not adv:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    composite = (
        await db.execute(
            select(MetaSignalComposite)
            .where(MetaSignalComposite.advertiser_id == advertiser_id)
            .order_by(MetaSignalComposite.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    # Get activity state from latest ActivityScore
    activity = (
        await db.execute(
            select(ActivityScore.activity_state)
            .where(ActivityScore.advertiser_id == advertiser_id)
            .order_by(ActivityScore.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if composite:
        return MetaSignalOverviewOut(
            advertiser_id=advertiser_id,
            date=composite.date,
            smartstore_score=composite.smartstore_score,
            traffic_score=composite.traffic_score,
            activity_score=composite.activity_score,
            panel_calibration=composite.panel_calibration,
            composite_score=composite.composite_score,
            spend_multiplier=composite.spend_multiplier,
            activity_state=activity,
            raw_factors=composite.raw_factors,
        )

    return MetaSignalOverviewOut(
        advertiser_id=advertiser_id,
        activity_state=activity,
    )


@router.get("/{advertiser_id}/smartstore", response_model=list[SmartStoreSnapshotOut])
async def get_smartstore_timeline(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get smartstore snapshot timeline for an advertiser."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    result = await db.execute(
        select(SmartStoreSnapshot)
        .where(
            and_(
                SmartStoreSnapshot.advertiser_id == advertiser_id,
                SmartStoreSnapshot.captured_at >= cutoff,
            )
        )
        .order_by(SmartStoreSnapshot.captured_at.asc())
    )
    return result.scalars().all()


@router.get("/{advertiser_id}/traffic", response_model=list[TrafficSignalOut])
async def get_traffic_timeline(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get traffic signal timeline for an advertiser."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    result = await db.execute(
        select(TrafficSignal)
        .where(
            and_(
                TrafficSignal.advertiser_id == advertiser_id,
                TrafficSignal.date >= cutoff,
            )
        )
        .order_by(TrafficSignal.date.asc())
    )
    return result.scalars().all()


@router.get("/{advertiser_id}/activity", response_model=list[ActivityScoreOut])
async def get_activity_timeline(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get activity score timeline for an advertiser."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    result = await db.execute(
        select(ActivityScore)
        .where(
            and_(
                ActivityScore.advertiser_id == advertiser_id,
                ActivityScore.date >= cutoff,
            )
        )
        .order_by(ActivityScore.date.asc())
    )
    return result.scalars().all()


@router.get("/{advertiser_id}/panel", response_model=PanelSummaryOut)
async def get_panel_summary(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get panel observation summary for an advertiser."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # AI panel count
    ai_count = (
        await db.execute(
            select(func.count(PanelObservation.id)).where(
                and_(
                    PanelObservation.advertiser_id == advertiser_id,
                    PanelObservation.panel_type == "ai",
                    PanelObservation.observed_at >= cutoff,
                )
            )
        )
    ).scalar_one() or 0

    # Human panel count
    human_count = (
        await db.execute(
            select(func.count(PanelObservation.id)).where(
                and_(
                    PanelObservation.advertiser_id == advertiser_id,
                    PanelObservation.panel_type == "human",
                    PanelObservation.observed_at >= cutoff,
                )
            )
        )
    ).scalar_one() or 0

    # Channels observed
    channels_rows = (
        await db.execute(
            select(func.distinct(PanelObservation.channel)).where(
                and_(
                    PanelObservation.advertiser_id == advertiser_id,
                    PanelObservation.observed_at >= cutoff,
                    PanelObservation.channel.isnot(None),
                )
            )
        )
    ).scalars().all()

    # Panel calibration from latest MetaSignalComposite
    calibration = (
        await db.execute(
            select(MetaSignalComposite.panel_calibration)
            .where(MetaSignalComposite.advertiser_id == advertiser_id)
            .order_by(MetaSignalComposite.date.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or 1.0

    return PanelSummaryOut(
        advertiser_id=advertiser_id,
        ai_observations=ai_count,
        human_observations=human_count,
        total_observations=ai_count + human_count,
        channels=list(channels_rows),
        panel_calibration=calibration,
    )


@router.post("/panel/submit")
async def submit_panel_observation(
    data: PanelSubmitIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a human panel observation (ad exposure report). Requires login."""
    advertiser_id = data.advertiser_id

    # If advertiser_name provided but no ID, try to find
    if not advertiser_id and data.advertiser_name:
        adv = (
            await db.execute(
                select(Advertiser.id).where(Advertiser.name == data.advertiser_name).limit(1)
            )
        ).scalar_one_or_none()
        advertiser_id = adv

    obs = PanelObservation(
        panel_type="human",
        panel_id="web_submit",
        advertiser_id=advertiser_id,
        channel=data.channel,
        device=data.device,
        location=data.location,
        is_verified=False,
        extra_data=data.extra_data,
    )
    db.add(obs)
    await db.commit()

    return {"status": "ok", "id": obs.id}


@router.get("/top-active")
async def get_top_active_advertisers(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Get top advertisers by meta-signal composite score (for dashboard widget)."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    # Latest composite per advertiser with activity_state from ActivityScore
    result = await db.execute(
        select(
            MetaSignalComposite.advertiser_id,
            MetaSignalComposite.composite_score,
            MetaSignalComposite.spend_multiplier,
            MetaSignalComposite.activity_score,
            MetaSignalComposite.smartstore_score,
            MetaSignalComposite.traffic_score,
            MetaSignalComposite.date,
            Advertiser.name,
            Advertiser.brand_name,
            ActivityScore.activity_state,
        )
        .join(Advertiser, MetaSignalComposite.advertiser_id == Advertiser.id)
        .outerjoin(
            ActivityScore,
            and_(
                ActivityScore.advertiser_id == MetaSignalComposite.advertiser_id,
                ActivityScore.date == MetaSignalComposite.date,
            ),
        )
        .where(MetaSignalComposite.date >= cutoff)
        .order_by(MetaSignalComposite.composite_score.desc())
        .limit(limit)
    )

    rows = result.fetchall()
    return [
        {
            "advertiser_id": r[0],
            "composite_score": r[1],
            "spend_multiplier": r[2],
            "activity_score": r[3],
            "smartstore_score": r[4],
            "traffic_score": r[5],
            "date": r[6].isoformat() if r[6] else None,
            "advertiser_name": r[7],
            "brand_name": r[8],
            "activity_state": r[9],
        }
        for r in rows
    ]
