"""광고주 트렌드 종합 API — 급상승/하강, 신규/이탈, 채널믹스, 산업별."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import and_, func, select, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    ActivityScore,
    AdDetail,
    AdSnapshot,
    Advertiser,
    Campaign,
    Industry,
    SpendEstimate,
)

router = APIRouter(prefix="/api/advertiser-trends", tags=["advertiser-trends"],
    dependencies=[Depends(get_current_user)])


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("/summary")
async def get_trend_summary(
    days: int = Query(30, ge=7, le=90),
    limit: int = Query(20, ge=5, le=50),
    db: AsyncSession = Depends(get_db),
):
    now = _now()
    half = days // 2
    cutoff = now - timedelta(days=days)
    cutoff_mid = now - timedelta(days=half)

    # ── A. 급상승 / 급하강 (ActivityScore 반분 비교) ──
    # 현재 반기 평균
    cur_sub = (
        select(
            ActivityScore.advertiser_id,
            func.avg(ActivityScore.composite_score).label("cur_score"),
        )
        .where(ActivityScore.date >= cutoff_mid)
        .group_by(ActivityScore.advertiser_id)
    ).subquery("cur")

    # 이전 반기 평균
    prev_sub = (
        select(
            ActivityScore.advertiser_id,
            func.avg(ActivityScore.composite_score).label("prev_score"),
        )
        .where(and_(ActivityScore.date >= cutoff, ActivityScore.date < cutoff_mid))
        .group_by(ActivityScore.advertiser_id)
    ).subquery("prev")

    # 최신 activity_state (SQLite 호환: max(date) 서브쿼리)
    max_date_sub = (
        select(
            ActivityScore.advertiser_id,
            func.max(ActivityScore.date).label("max_date"),
        )
        .where(ActivityScore.date >= cutoff_mid)
        .group_by(ActivityScore.advertiser_id)
    ).subquery("maxd")

    latest_state = (
        select(
            ActivityScore.advertiser_id,
            ActivityScore.activity_state,
        )
        .join(
            max_date_sub,
            and_(
                ActivityScore.advertiser_id == max_date_sub.c.advertiser_id,
                ActivityScore.date == max_date_sub.c.max_date,
            ),
        )
    ).subquery("state")

    delta_q = (
        select(
            cur_sub.c.advertiser_id,
            Advertiser.name.label("advertiser_name"),
            Advertiser.brand_name,
            Advertiser.industry_id,
            cur_sub.c.cur_score,
            prev_sub.c.prev_score,
            (cur_sub.c.cur_score - prev_sub.c.prev_score).label("delta"),
            latest_state.c.activity_state,
        )
        .join(prev_sub, cur_sub.c.advertiser_id == prev_sub.c.advertiser_id)
        .join(Advertiser, cur_sub.c.advertiser_id == Advertiser.id)
        .outerjoin(latest_state, cur_sub.c.advertiser_id == latest_state.c.advertiser_id)
        .where(prev_sub.c.prev_score > 0)
    )

    # Rising
    rising_rows = (await db.execute(
        delta_q.order_by(literal_column("delta").desc()).limit(limit)
    )).fetchall()

    # Falling
    falling_rows = (await db.execute(
        delta_q.order_by(literal_column("delta").asc()).limit(limit)
    )).fetchall()

    def _fmt_trend(rows):
        out = []
        for r in rows:
            cur = round(r.cur_score or 0, 1)
            prev = round(r.prev_score or 0, 1)
            delta = round(r.delta or 0, 1)
            delta_pct = round((delta / prev * 100) if prev else 0, 1)
            out.append({
                "advertiser_id": r.advertiser_id,
                "advertiser_name": r.advertiser_name,
                "brand_name": r.brand_name,
                "industry_id": r.industry_id,
                "current_score": cur,
                "prev_score": prev,
                "delta": delta,
                "delta_pct": delta_pct,
                "activity_state": r.activity_state,
            })
        return out

    rising = _fmt_trend(rising_rows)
    falling = _fmt_trend(falling_rows)

    # ── B. 신규 진입 / 이탈 ──
    # 신규: cutoff 이후 첫 캠페인 & cutoff 이전 캠페인 없음
    had_before = select(Campaign.advertiser_id).where(
        Campaign.first_seen < cutoff
    ).distinct().correlate(None)

    new_q = (
        select(
            Campaign.advertiser_id,
            func.min(Campaign.first_seen).label("entered_at"),
            func.count(Campaign.id).label("campaign_count"),
        )
        .where(Campaign.first_seen >= cutoff)
        .where(~Campaign.advertiser_id.in_(had_before))
        .group_by(Campaign.advertiser_id)
        .order_by(func.min(Campaign.first_seen).desc())
        .limit(limit)
    )
    new_rows = (await db.execute(new_q)).fetchall()

    # 이름 조인
    new_ids = [r.advertiser_id for r in new_rows]
    if new_ids:
        adv_map_rows = (await db.execute(
            select(Advertiser.id, Advertiser.name, Advertiser.brand_name)
            .where(Advertiser.id.in_(new_ids))
        )).fetchall()
        adv_map = {r.id: r for r in adv_map_rows}
    else:
        adv_map = {}

    new_entrants = []
    for r in new_rows:
        adv = adv_map.get(r.advertiser_id)
        new_entrants.append({
            "advertiser_id": r.advertiser_id,
            "advertiser_name": adv.name if adv else None,
            "brand_name": adv.brand_name if adv else None,
            "entered_at": r.entered_at.isoformat() if r.entered_at else None,
            "campaign_count": r.campaign_count,
        })

    # 이탈: 이전 반기 활성이었으나 현재 반기 캠페인 없음
    active_now = select(Campaign.advertiser_id).where(
        Campaign.last_seen >= cutoff_mid
    ).distinct().correlate(None)

    exit_q = (
        select(
            Campaign.advertiser_id,
            func.max(Campaign.last_seen).label("last_active"),
        )
        .where(and_(
            Campaign.last_seen < cutoff_mid,
            Campaign.last_seen >= cutoff,
        ))
        .where(~Campaign.advertiser_id.in_(active_now))
        .group_by(Campaign.advertiser_id)
        .order_by(func.max(Campaign.last_seen).desc())
        .limit(limit)
    )
    exit_rows = (await db.execute(exit_q)).fetchall()

    exit_ids = [r.advertiser_id for r in exit_rows]
    if exit_ids:
        exit_adv_rows = (await db.execute(
            select(Advertiser.id, Advertiser.name, Advertiser.brand_name)
            .where(Advertiser.id.in_(exit_ids))
        )).fetchall()
        exit_adv_map = {r.id: r for r in exit_adv_rows}
    else:
        exit_adv_map = {}

    exited = []
    for r in exit_rows:
        adv = exit_adv_map.get(r.advertiser_id)
        exited.append({
            "advertiser_id": r.advertiser_id,
            "advertiser_name": adv.name if adv else None,
            "brand_name": adv.brand_name if adv else None,
            "last_active": r.last_active.isoformat() if r.last_active else None,
        })

    # ── C. 채널 믹스 변화 ──
    cur_ch = (await db.execute(
        select(
            AdSnapshot.channel,
            func.count(AdDetail.id).label("cnt"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at >= cutoff_mid)
        .group_by(AdSnapshot.channel)
    )).fetchall()

    prev_ch = (await db.execute(
        select(
            AdSnapshot.channel,
            func.count(AdDetail.id).label("cnt"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(and_(AdSnapshot.captured_at >= cutoff, AdSnapshot.captured_at < cutoff_mid))
        .group_by(AdSnapshot.channel)
    )).fetchall()

    prev_ch_map = {r.channel: r.cnt for r in prev_ch}
    channel_trends = []
    for r in cur_ch:
        prev_cnt = prev_ch_map.get(r.channel, 0)
        growth = round(((r.cnt - prev_cnt) / prev_cnt * 100) if prev_cnt else 0, 1)
        channel_trends.append({
            "channel": r.channel,
            "current_count": r.cnt,
            "prev_count": prev_cnt,
            "growth_pct": growth,
        })
    channel_trends.sort(key=lambda x: x["growth_pct"], reverse=True)

    # ── D. 산업별 요약 ──
    ind_q = (
        select(
            Industry.id.label("industry_id"),
            Industry.name.label("industry_name"),
            func.count(func.distinct(Advertiser.id)).label("active_advertisers"),
            func.avg(ActivityScore.composite_score).label("avg_activity"),
        )
        .join(Advertiser, Advertiser.industry_id == Industry.id)
        .join(
            ActivityScore,
            and_(
                ActivityScore.advertiser_id == Advertiser.id,
                ActivityScore.date >= cutoff,
            ),
        )
        .group_by(Industry.id, Industry.name)
        .order_by(func.avg(ActivityScore.composite_score).desc())
    )
    ind_rows = (await db.execute(ind_q)).fetchall()
    industry_summary = [
        {
            "industry_id": r.industry_id,
            "industry_name": r.industry_name,
            "active_advertisers": r.active_advertisers,
            "avg_activity": round(r.avg_activity or 0, 1),
        }
        for r in ind_rows
    ]

    # ── 활성 광고주 총수 ──
    total_active = (await db.execute(
        select(func.count(func.distinct(Campaign.advertiser_id)))
        .where(Campaign.last_seen >= cutoff)
    )).scalar_one() or 0

    # 전체 평균 활동점수
    avg_score_val = (await db.execute(
        select(func.avg(ActivityScore.composite_score))
        .where(ActivityScore.date >= cutoff_mid)
    )).scalar_one() or 0

    return {
        "period_days": days,
        "analysis_date": now.strftime("%Y-%m-%d"),
        "total_active_advertisers": total_active,
        "avg_activity_score": round(avg_score_val, 1),
        "rising": rising,
        "falling": falling,
        "new_entrants": new_entrants,
        "exited": exited,
        "channel_trends": channel_trends,
        "industry_summary": industry_summary,
    }


@router.get("/advertiser/{advertiser_id}/trajectory")
async def get_advertiser_trajectory(
    advertiser_id: int,
    days: int = Query(30, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
):
    """개별 광고주 트렌드 궤적 — 활동점수 + 광고비 일별."""
    now = _now()
    cutoff = now - timedelta(days=days)

    adv = (await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )).scalar_one_or_none()
    if not adv:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Advertiser not found")

    # 활동 점수 타임라인
    activity_rows = (await db.execute(
        select(ActivityScore)
        .where(and_(
            ActivityScore.advertiser_id == advertiser_id,
            ActivityScore.date >= cutoff,
        ))
        .order_by(ActivityScore.date.asc())
    )).scalars().all()

    # 일별 광고비
    spend_rows = (await db.execute(
        select(
            SpendEstimate.date,
            func.sum(SpendEstimate.est_daily_spend).label("total_spend"),
        )
        .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
        .where(and_(
            Campaign.advertiser_id == advertiser_id,
            SpendEstimate.date >= cutoff,
        ))
        .group_by(SpendEstimate.date)
        .order_by(SpendEstimate.date.asc())
    )).fetchall()
    spend_map = {r.date.strftime("%Y-%m-%d"): round(r.total_spend or 0) for r in spend_rows}

    timeline = []
    for a in activity_rows:
        d = a.date.strftime("%Y-%m-%d")
        timeline.append({
            "date": d,
            "activity_score": round(a.composite_score or 0, 1),
            "activity_state": a.activity_state,
            "active_campaigns": a.active_campaigns or 0,
            "new_creatives": a.new_creatives or 0,
            "est_daily_spend": spend_map.get(d, 0),
        })

    # 현재 상태 판단
    current_state = activity_rows[-1].activity_state if activity_rows else None
    if len(activity_rows) >= 2:
        last = activity_rows[-1].composite_score or 0
        first = activity_rows[0].composite_score or 0
        score_trend = "rising" if last > first else ("falling" if last < first else "stable")
    else:
        score_trend = "stable"

    return {
        "advertiser_id": advertiser_id,
        "advertiser_name": adv.name,
        "brand_name": adv.brand_name,
        "timeline": timeline,
        "current_state": current_state,
        "score_trend": score_trend,
    }
