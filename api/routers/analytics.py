"""광고 접촉율 + 경쟁사 SOV 분석 API."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import AdDetail, AdSnapshot, Persona
from database.schemas import (
    ContactRateOut, ContactRateTrendPoint, CompetitiveSOVOut, SOVOut,
    PersonaAdvertiserRankOut, PersonaHeatmapCellOut, PersonaRankingTrendPoint,
)
from processor.contact_rate import (
    calculate_contact_rate_trend,
    calculate_contact_rates,
    compare_advertiser_contact_rates,
)
from processor.sov_analyzer import (
    calculate_competitive_sov,
    calculate_sov,
    calculate_sov_trend,
)

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


# ── 광고 접촉율 ──


@router.get("/contact-rate", response_model=list[ContactRateOut])
async def get_contact_rates(
    days: int = Query(default=30, le=365),
    channel: str | None = None,
    age_group: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """연령대별 광고 접촉율 분석.

    세션당 평균 광고 노출 건수를 연령대×성별×채널로 분류.
    """
    results = await calculate_contact_rates(
        db, days=days, channel=channel, age_group=age_group
    )
    return [
        ContactRateOut(
            age_group=r.age_group,
            gender=r.gender,
            channel=r.channel,
            total_sessions=r.total_sessions,
            total_ad_impressions=r.total_ad_impressions,
            contact_rate=r.contact_rate,
            unique_advertisers=r.unique_advertisers,
            avg_ads_per_session=r.avg_ads_per_session,
            top_ad_types=r.top_ad_types,
            position_distribution=r.position_distribution,
        )
        for r in results
    ]


@router.get("/contact-rate/trend", response_model=list[ContactRateTrendPoint])
async def get_contact_rate_trend(
    days: int = Query(default=30, le=365),
    age_group: str | None = None,
    channel: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """광고 접촉율 시계열 추이."""
    results = await calculate_contact_rate_trend(
        db, days=days, channel=channel, age_group=age_group
    )
    return [
        ContactRateTrendPoint(
            date=r.date,
            age_group=r.age_group,
            gender=r.gender,
            contact_rate=r.contact_rate,
        )
        for r in results
    ]


@router.get("/contact-rate/comparison")
async def compare_contact_rates(
    advertiser_id: int = Query(...),
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """특정 광고주의 연령대별 접촉율 비교.

    해당 광고주가 어느 연령대에 가장 많이 노출되는지 분석.
    """
    return await compare_advertiser_contact_rates(db, advertiser_id=advertiser_id, days=days)


# ── SOV (Share of Voice) ──


@router.get("/sov", response_model=list[SOVOut])
async def get_sov(
    keyword: str | None = None,
    industry_id: int | None = None,
    channel: str | None = None,
    days: int = Query(default=30, le=365),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """키워드/업종별 광고주 점유율(SOV) 분석."""
    results = await calculate_sov(
        db,
        keyword=keyword,
        industry_id=industry_id,
        channel=channel,
        days=days,
        limit=limit,
    )
    return [
        SOVOut(
            advertiser_name=r.advertiser_name,
            advertiser_id=r.advertiser_id,
            channel=r.channel,
            sov_percentage=r.sov_percentage,
            total_impressions=r.total_impressions,
        )
        for r in results
    ]


@router.get("/sov/competitive/{advertiser_id}")
async def get_competitive_sov(
    advertiser_id: int,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """특정 광고주의 경쟁사 대비 윈도우 점유율.

    같은 업종 내 경쟁사 자동 매칭 → 채널별·연령대별 점유율 비교.
    """
    return await calculate_competitive_sov(db, advertiser_id=advertiser_id, days=days)


@router.get("/sov/trend")
async def get_sov_trend(
    advertiser_id: int = Query(...),
    competitor_ids: str | None = Query(None, description="콤마 구분 경쟁사 ID"),
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """SOV 시계열 추이 — 광고주 vs 경쟁사."""
    comp_ids = []
    if competitor_ids:
        comp_ids = [int(x.strip()) for x in competitor_ids.split(",") if x.strip().isdigit()]

    results = await calculate_sov_trend(
        db, advertiser_id=advertiser_id, competitor_ids=comp_ids, days=days
    )
    return [
        {
            "date": r.date,
            "advertiser_name": r.advertiser_name,
            "advertiser_id": r.advertiser_id,
            "sov_percentage": r.sov_percentage,
        }
        for r in results
    ]


# ── Persona Ranking ──

from processor.persona_ranking import (
    calculate_persona_advertiser_ranking,
    calculate_persona_heatmap,
    calculate_persona_ranking_trend,
)


@router.get("/persona-ranking", response_model=list[PersonaAdvertiserRankOut])
async def get_persona_ranking(
    persona_code: str | None = None,
    days: int = Query(default=30, le=365),
    channel: str | None = None,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Persona-level advertiser ranking.

    Shows which advertisers appear most for each persona profile.
    """
    results = await calculate_persona_advertiser_ranking(
        db, persona_code=persona_code, days=days, channel=channel, limit=limit
    )
    return [
        PersonaAdvertiserRankOut(
            persona_code=r.persona_code,
            age_group=r.age_group,
            gender=r.gender,
            advertiser_name=r.advertiser_name,
            advertiser_id=r.advertiser_id,
            impression_count=r.impression_count,
            session_count=r.session_count,
            avg_per_session=r.avg_per_session,
            channels=r.channels,
            rank=r.rank,
        )
        for r in results
    ]


@router.get("/persona-ranking/heatmap", response_model=list[PersonaHeatmapCellOut])
async def get_persona_heatmap(
    days: int = Query(default=30, le=365),
    channel: str | None = None,
    top_advertisers: int = Query(default=15, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Persona x Advertiser heatmap matrix.

    Returns normalized intensity (0.0-1.0) for each persona-advertiser pair.
    """
    results = await calculate_persona_heatmap(
        db, days=days, channel=channel, top_advertisers=top_advertisers
    )
    return [
        PersonaHeatmapCellOut(
            persona_code=r.persona_code,
            age_group=r.age_group,
            gender=r.gender,
            advertiser_name=r.advertiser_name,
            advertiser_id=r.advertiser_id,
            impression_count=r.impression_count,
            intensity=r.intensity,
        )
        for r in results
    ]


@router.get("/persona-ranking/trend")
async def get_persona_ranking_trend(
    persona_code: str = Query(...),
    days: int = Query(default=30, le=365),
    channel: str | None = None,
    limit: int = Query(default=10, le=30),
    db: AsyncSession = Depends(get_db),
):
    """Daily impression trend for a persona's top advertisers."""
    return await calculate_persona_ranking_trend(
        db, persona_code=persona_code, days=days, channel=channel, limit=limit
    )


# ── Ad-level Persona Breakdown ──


@router.get("/ad-persona-breakdown")
async def get_ad_persona_breakdown(
    advertiser_id: int = Query(..., description="광고주 ID"),
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """개별 광고 단위 페르소나 타겟 분석.

    특정 광고주의 광고들이 어떤 연령대/성별 페르소나에게 가장 많이 노출됐는지 분석.
    AdDetail.persona_id FK를 통해 Persona와 조인하며, AdSnapshot.captured_at으로 기간 필터링.

    NOTE: AdDetail.persona_id는 비정규화 컬럼 (원본: AdSnapshot.persona_id).
    이 엔드포인트는 성능상 AdDetail.persona_id를 직접 사용하지만,
    새 쿼리를 작성할 때는 AdSnapshot.persona_id JOIN을 권장.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Main aggregation: age_group x gender -> ad_count, unique_ads
    # NOTE: AdDetail.persona_id 사용 (비정규화). 대안: AdSnapshot.persona_id JOIN
    main_q = (
        select(
            Persona.age_group,
            Persona.gender,
            func.count(AdDetail.id).label("ad_count"),
            func.count(func.distinct(AdDetail.creative_hash)).label("unique_ads"),
        )
        .join(Persona, AdDetail.persona_id == Persona.id)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id == advertiser_id)
        .where(AdSnapshot.captured_at >= cutoff)
        .group_by(Persona.age_group, Persona.gender)
        .order_by(func.count(AdDetail.id).desc())
    )

    main_rows = (await db.execute(main_q)).all()

    if not main_rows:
        return []

    # Channels sub-aggregation: for each (age_group, gender) pair collect distinct channels
    # NOTE: AdDetail.persona_id 사용 (비정규화). 대안: AdSnapshot.persona_id JOIN
    channels_q = (
        select(
            Persona.age_group,
            Persona.gender,
            AdSnapshot.channel,
        )
        .join(Persona, AdDetail.persona_id == Persona.id)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id == advertiser_id)
        .where(AdSnapshot.captured_at >= cutoff)
        .distinct()
    )

    channels_rows = (await db.execute(channels_q)).all()

    # Build a lookup: (age_group, gender) -> sorted list of channels
    channels_map: dict[tuple, list[str]] = {}
    for row in channels_rows:
        key = (row.age_group, row.gender)
        if key not in channels_map:
            channels_map[key] = []
        if row.channel and row.channel not in channels_map[key]:
            channels_map[key].append(row.channel)

    for channels_list in channels_map.values():
        channels_list.sort()

    return [
        {
            "age_group": row.age_group,
            "gender": row.gender,
            "ad_count": row.ad_count,
            "unique_ads": row.unique_ads,
            "channels": channels_map.get((row.age_group, row.gender), []),
        }
        for row in main_rows
    ]
