"""Target Audience API -- channel priority, audience overlap, targeting recommendation."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    AdDetail,
    AdSnapshot,
    Advertiser,
    Persona,
)

router = APIRouter(prefix="/api/target-audience", tags=["target-audience"],
    dependencies=[Depends(get_current_user)])

KST = timezone(timedelta(hours=9))


@router.get("/channel-priority")
async def channel_priority(
    advertiser_id: int | None = Query(None),
    industry_id: int | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Channel ad share for advertiser vs industry average."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    # Advertiser channel distribution
    adv_data = []
    if advertiser_id:
        adv_rows = (
            await db.execute(
                select(
                    AdSnapshot.channel,
                    func.count(AdDetail.id).label("cnt"),
                )
                .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
                .where(
                    and_(
                        AdDetail.advertiser_id == advertiser_id,
                        AdSnapshot.captured_at >= cutoff,
                    )
                )
                .group_by(AdSnapshot.channel)
                .order_by(func.count(AdDetail.id).desc())
            )
        ).all()
        total = sum(r.cnt for r in adv_rows) or 1
        adv_data = [
            {"channel": r.channel, "count": r.cnt, "share_pct": round(r.cnt / total * 100, 1)}
            for r in adv_rows
        ]

    # Industry average channel distribution
    ind_q = (
        select(
            AdSnapshot.channel,
            func.count(AdDetail.id).label("cnt"),
        )
        .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Advertiser, Advertiser.id == AdDetail.advertiser_id)
        .where(AdSnapshot.captured_at >= cutoff)
    )
    if industry_id:
        ind_q = ind_q.where(Advertiser.industry_id == industry_id)
    elif advertiser_id:
        # Use same industry as the advertiser
        adv = (await db.execute(
            select(Advertiser.industry_id).where(Advertiser.id == advertiser_id)
        )).scalar_one_or_none()
        if adv:
            ind_q = ind_q.where(Advertiser.industry_id == adv)

    ind_q = ind_q.group_by(AdSnapshot.channel).order_by(func.count(AdDetail.id).desc())
    ind_rows = (await db.execute(ind_q)).all()
    ind_total = sum(r.cnt for r in ind_rows) or 1
    industry_data = [
        {"channel": r.channel, "count": r.cnt, "share_pct": round(r.cnt / ind_total * 100, 1)}
        for r in ind_rows
    ]

    return {
        "advertiser": adv_data,
        "industry_avg": industry_data,
    }


@router.get("/audience-overlap")
async def audience_overlap(
    industry_id: int | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Demographic competition density: how many advertisers target each persona."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    q = (
        select(
            Persona.age_group,
            Persona.gender,
            func.count(func.distinct(AdDetail.advertiser_id)).label("unique_advertisers"),
            func.count(AdDetail.id).label("total_ads"),
        )
        .join(AdDetail, AdDetail.persona_id == Persona.id)
        .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
        .where(AdSnapshot.captured_at >= cutoff)
    )
    if industry_id:
        q = q.join(Advertiser, Advertiser.id == AdDetail.advertiser_id).where(
            Advertiser.industry_id == industry_id
        )
    q = q.group_by(Persona.age_group, Persona.gender).order_by(
        func.count(func.distinct(AdDetail.advertiser_id)).desc()
    )

    rows = (await db.execute(q)).all()

    max_advs = max((r.unique_advertisers for r in rows), default=1) or 1

    return [
        {
            "age_group": r.age_group,
            "gender": r.gender,
            "unique_advertisers": r.unique_advertisers,
            "total_ads": r.total_ads,
            "competition_level": "high" if r.unique_advertisers >= max_advs * 0.7
                else "medium" if r.unique_advertisers >= max_advs * 0.3
                else "low",
        }
        for r in rows
    ]


@router.get("/recommendation")
async def targeting_recommendation(
    advertiser_id: int,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Rule-based targeting recommendation: compare advertiser vs industry peers."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    # Get advertiser info
    adv = (await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )).scalar_one_or_none()
    if not adv:
        return {"error": "Advertiser not found"}

    # Advertiser persona distribution
    adv_persona = (
        await db.execute(
            select(
                Persona.age_group,
                Persona.gender,
                func.count(AdDetail.id).label("cnt"),
            )
            .join(AdDetail, AdDetail.persona_id == Persona.id)
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(
                and_(
                    AdDetail.advertiser_id == advertiser_id,
                    AdSnapshot.captured_at >= cutoff,
                )
            )
            .group_by(Persona.age_group, Persona.gender)
            .order_by(func.count(AdDetail.id).desc())
        )
    ).all()

    # Advertiser channel distribution
    adv_channel = (
        await db.execute(
            select(
                AdSnapshot.channel,
                func.count(AdDetail.id).label("cnt"),
            )
            .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
            .where(
                and_(
                    AdDetail.advertiser_id == advertiser_id,
                    AdSnapshot.captured_at >= cutoff,
                )
            )
            .group_by(AdSnapshot.channel)
            .order_by(func.count(AdDetail.id).desc())
        )
    ).all()

    # Industry peers channel distribution
    ind_channel = {}
    if adv.industry_id:
        ind_rows = (
            await db.execute(
                select(
                    AdSnapshot.channel,
                    func.count(AdDetail.id).label("cnt"),
                )
                .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
                .join(Advertiser, Advertiser.id == AdDetail.advertiser_id)
                .where(
                    and_(
                        Advertiser.industry_id == adv.industry_id,
                        AdSnapshot.captured_at >= cutoff,
                    )
                )
                .group_by(AdSnapshot.channel)
            )
        ).all()
        ind_total = sum(r.cnt for r in ind_rows) or 1
        ind_channel = {r.channel: r.cnt / ind_total for r in ind_rows}

    # Build recommendations
    adv_total = sum(r.cnt for r in adv_channel) or 1
    adv_ch_pct = {r.channel: r.cnt / adv_total for r in adv_channel}

    recommendations = []

    # Find underused channels (industry uses but advertiser doesn't)
    for ch, ind_pct in ind_channel.items():
        adv_pct = adv_ch_pct.get(ch, 0)
        if ind_pct > 0.1 and adv_pct < ind_pct * 0.3:
            recommendations.append({
                "type": "channel_gap",
                "message": f"{ch} 채널 확대 권장 (업종 평균 {ind_pct*100:.0f}%, 현재 {adv_pct*100:.0f}%)",
                "channel": ch,
                "industry_pct": round(ind_pct * 100, 1),
                "advertiser_pct": round(adv_pct * 100, 1),
            })

    # Primary persona
    primary_persona = None
    if adv_persona:
        p = adv_persona[0]
        primary_persona = f"{p.age_group} {p.gender}"
        recommendations.insert(0, {
            "type": "primary_target",
            "message": f"주요 타겟: {primary_persona} ({p.cnt}건 노출)",
            "age_group": p.age_group,
            "gender": p.gender,
            "count": p.cnt,
        })

    # Primary channel
    if adv_channel:
        c = adv_channel[0]
        recommendations.insert(1 if primary_persona else 0, {
            "type": "primary_channel",
            "message": f"주력 채널: {c.channel} ({c.cnt}건, {adv_ch_pct[c.channel]*100:.0f}%)",
            "channel": c.channel,
            "count": c.cnt,
        })

    return {
        "advertiser_name": adv.name,
        "industry_id": adv.industry_id,
        "persona_distribution": [
            {"age_group": r.age_group, "gender": r.gender, "count": r.cnt}
            for r in adv_persona
        ],
        "channel_distribution": [
            {"channel": r.channel, "count": r.cnt, "pct": round(adv_ch_pct.get(r.channel, 0) * 100, 1)}
            for r in adv_channel
        ],
        "recommendations": recommendations,
    }
