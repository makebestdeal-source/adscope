"""캠페인 추적 API.

금액 필드 규칙:
  - total_est_spend: Campaign 테이블 컬럼. 캠페인 누적 추정 매체비 (KRW).
  - total_spend (CampaignEffectOut): SUM(spend_estimates.est_daily_spend).
    캠페인 전체 기간 추정 매체비 합계 (KRW). 대행수수료 미포함 순수 매체비.
  - est_daily_spend: 일별 추정 매체비 (KRW).
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_paid
from database import get_db
from database.models import (
    Advertiser, Campaign, CampaignLift, JourneyEvent, SpendEstimate,
)
from database.schemas import (
    CampaignDetailOut, CampaignEffectOut, CampaignLiftOut,
    CampaignOut, CampaignUpdateIn, JourneyEventOut, SpendEstimateOut,
)

router = APIRouter(
    prefix="/api/campaigns",
    tags=["campaigns"],
    redirect_slashes=False,
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    advertiser_id: int | None = None,
    channel: str | None = None,
    is_active: bool | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """캠페인 목록 조회.

    CampaignOut.total_est_spend = 캠페인 누적 추정 매체비 (KRW).
    """
    query = select(Campaign).order_by(Campaign.last_seen.desc())

    if advertiser_id:
        query = query.where(Campaign.advertiser_id == advertiser_id)
    if channel:
        query = query.where(Campaign.channel == channel)
    if is_active is not None:
        query = query.where(Campaign.is_active == is_active)

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/enriched")
async def list_campaigns_enriched(
    channel: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    sort_by: str = Query(default="last_seen"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """캠페인 목록 (광고주명 포함). 프론트 캠페인 리스트 페이지용."""
    query = (
        select(
            Campaign.id,
            Campaign.advertiser_id,
            Advertiser.name.label("advertiser_name"),
            Campaign.channel,
            Campaign.campaign_name,
            Campaign.objective,
            Campaign.product_service,
            Campaign.model_info,
            Campaign.promotion_copy,
            Campaign.first_seen,
            Campaign.last_seen,
            Campaign.is_active,
            Campaign.total_est_spend,
            Campaign.snapshot_count,
            Campaign.status,
        )
        .outerjoin(Advertiser, Campaign.advertiser_id == Advertiser.id)
    )

    if channel:
        query = query.where(Campaign.channel == channel)
    if is_active is not None:
        query = query.where(Campaign.is_active == is_active)
    if search:
        pat = f"%{search}%"
        query = query.where(
            (Advertiser.name.ilike(pat))
            | (Campaign.campaign_name.ilike(pat))
            | (Campaign.product_service.ilike(pat))
            | (Campaign.model_info.ilike(pat))
        )

    # 정렬
    sort_col = {
        "last_seen": Campaign.last_seen,
        "first_seen": Campaign.first_seen,
        "total_est_spend": Campaign.total_est_spend,
        "advertiser_name": Advertiser.name,
        "channel": Campaign.channel,
        "snapshot_count": Campaign.snapshot_count,
    }.get(sort_by, Campaign.last_seen)

    if sort_dir == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # total count + total spend
    from sqlalchemy import func as fn
    sub = query.subquery()
    count_q = select(fn.count(), fn.sum(sub.c.total_est_spend)).select_from(sub)
    count_row = (await db.execute(count_q)).one()
    total = count_row[0] or 0
    total_spend_sum = round(count_row[1] or 0)

    rows = (await db.execute(query.offset(offset).limit(limit))).all()

    return {
        "total": total,
        "total_spend_sum": total_spend_sum,
        "items": [
            {
                "id": r.id,
                "advertiser_id": r.advertiser_id,
                "advertiser_name": r.advertiser_name,
                "channel": r.channel,
                "campaign_name": r.campaign_name,
                "objective": r.objective,
                "product_service": r.product_service,
                "model_info": r.model_info,
                "promotion_copy": r.promotion_copy,
                "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                "is_active": r.is_active,
                "total_est_spend": round(r.total_est_spend or 0),
                "snapshot_count": r.snapshot_count or 0,
                "status": r.status,
            }
            for r in rows
        ],
    }


@router.get("/stats/active")
async def active_campaign_stats(
    days: int = Query(default=30, le=90),
    db: AsyncSession = Depends(get_db),
):
    """최근 N일 기준 채널별 활성 캠페인 요약.

    Returns:
        list of dict, 각 항목:
        - channel: 매체 채널명
        - campaign_count: 활성 캠페인 수
        - total_est_spend: 해당 채널 활성 캠페인들의 누적 추정 매체비 합계 (KRW).
                           SUM(campaigns.total_est_spend). 대행수수료 미포함.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            Campaign.channel,
            func.count(Campaign.id).label("campaign_count"),
            func.sum(Campaign.total_est_spend).label("total_est_spend"),
        )
        .where(Campaign.is_active.is_(True))
        .where(Campaign.last_seen >= cutoff)
        .group_by(Campaign.channel)
        .order_by(func.count(Campaign.id).desc())
    )

    return [
        {
            "channel": row[0],
            "campaign_count": row[1],
            "total_est_spend": round(row[2] or 0),  # 누적 추정 매체비 합계 (KRW)
        }
        for row in result.all()
    ]


# ── Sub-path endpoints FIRST (before catch-all /{campaign_id}) ──

@router.get("/{campaign_id}/detail", response_model=CampaignDetailOut)
async def get_campaign_detail(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """캠페인 상세 조회 (체계화 필드 포함).

    total_est_spend = 캠페인 누적 추정 매체비 (KRW). Campaign 테이블 컬럼.
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


@router.get("/{campaign_id}/journey", response_model=list[JourneyEventOut])
async def get_campaign_journey(
    campaign_id: int,
    stage: str | None = Query(None),
    source: str | None = Query(None),
    days: int = Query(default=90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 저니 이벤트 타임라인."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    query = (
        select(JourneyEvent)
        .where(JourneyEvent.campaign_id == campaign_id)
        .where(JourneyEvent.ts >= cutoff)
        .order_by(JourneyEvent.ts)
    )
    if stage:
        query = query.where(JourneyEvent.stage == stage)
    if source:
        query = query.where(JourneyEvent.source == source)

    result = await db.execute(query.limit(1000))
    return result.scalars().all()


@router.get("/{campaign_id}/lift", response_model=CampaignLiftOut | None)
async def get_campaign_lift(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """캠페인 리프트 분석 결과."""
    result = await db.execute(
        select(CampaignLift).where(CampaignLift.campaign_id == campaign_id)
    )
    lift = result.scalar_one_or_none()
    if not lift:
        return None
    return lift


@router.get("/{campaign_id}/effect", response_model=CampaignEffectOut)
async def get_campaign_effect(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """캠페인 종합 효과 KPI (카드용).

    Returns CampaignEffectOut:
        - total_spend: 캠페인 전체 기간 추정 매체비 합계 (KRW).
                       SUM(spend_estimates.est_daily_spend). 대행수수료 미포함 순수 매체비.
        - est_impressions: journey_events에서 metric='impressions' 합산
        - est_clicks: est_impressions * 0.02 (CTR 2% 추정)
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    # 광고주명
    adv_name = None
    if campaign.advertiser_id:
        adv_result = await db.execute(
            select(Advertiser.name).where(Advertiser.id == campaign.advertiser_id)
        )
        adv_name = adv_result.scalar_one_or_none()

    # 총 추정 매체비 = SUM(est_daily_spend) (KRW)
    spend_result = await db.execute(
        select(func.sum(SpendEstimate.est_daily_spend))
        .where(SpendEstimate.campaign_id == campaign_id)
    )
    total_spend = spend_result.scalar() or 0.0

    # 추정 노출수 (journey_events에서)
    impr_result = await db.execute(
        select(func.sum(JourneyEvent.value))
        .where(JourneyEvent.campaign_id == campaign_id)
        .where(JourneyEvent.metric == "impressions")
    )
    est_impressions = impr_result.scalar() or 0.0

    # 추정 클릭수 (노출의 2% CTR 추정)
    est_clicks = est_impressions * 0.02

    # 기간
    duration = 0
    if campaign.start_at and campaign.end_at:
        duration = max(1, (campaign.end_at - campaign.start_at).days)

    # 채널 목록
    channels = [campaign.channel]
    if campaign.channels:
        channels = campaign.channels if isinstance(campaign.channels, list) else [campaign.channel]

    # Lift 데이터
    lift_result = await db.execute(
        select(CampaignLift).where(CampaignLift.campaign_id == campaign_id)
    )
    lift = lift_result.scalar_one_or_none()

    return CampaignEffectOut(
        campaign_id=campaign.id,
        campaign_name=campaign.campaign_name,
        advertiser_name=adv_name,
        objective=campaign.objective,
        status=campaign.status,
        duration_days=duration,
        channels=channels,
        total_spend=round(total_spend),           # 추정 매체비 합계 (KRW)
        est_impressions=round(est_impressions),
        est_clicks=round(est_clicks),
        query_lift_pct=lift.query_lift_pct if lift else None,
        social_lift_pct=lift.social_lift_pct if lift else None,
        sales_lift_pct=lift.sales_lift_pct if lift else None,
        confidence=lift.confidence if lift else None,
    )


@router.get("/{campaign_id}/spend", response_model=list[SpendEstimateOut])
async def get_campaign_spend(
    campaign_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """특정 캠페인의 광고비 추정 시계열 조회.

    각 레코드의 est_daily_spend = 해당일 추정 매체비 (KRW). 대행수수료 미포함.
    """
    query = (
        select(SpendEstimate)
        .where(SpendEstimate.campaign_id == campaign_id)
        .order_by(SpendEstimate.date.desc())
    )
    if date_from:
        query = query.where(SpendEstimate.date >= date_from)
    if date_to:
        query = query.where(SpendEstimate.date <= date_to)

    result = await db.execute(query.limit(limit))
    return result.scalars().all()


@router.put("/{campaign_id}", response_model=CampaignDetailOut)
async def update_campaign(
    campaign_id: int,
    body: CampaignUpdateIn,
    db: AsyncSession = Depends(get_db),
):
    """캠페인 메타데이터 수동 편집."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(campaign, key, value)

    campaign.enrichment_status = "manual_override"
    await db.commit()
    await db.refresh(campaign)
    return campaign


# ── Catch-all (must be LAST) ──

@router.get("/{campaign_id}", response_model=CampaignDetailOut)
async def get_campaign(campaign_id: int, db: AsyncSession = Depends(get_db)):
    """캠페인 기본 조회 (상세 필드 포함).

    total_est_spend = 캠페인 누적 추정 매체비 (KRW). Campaign 테이블 컬럼.
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign
