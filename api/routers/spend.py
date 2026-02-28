"""광고비 추정 API.

금액 필드 규칙:
  - total_spend: 조회 기간 내 SUM(est_daily_spend) -- 추정 매체비 합계 (KRW)
  - media_spend: 순수 매체비 (KRW). 대행수수료 미포함.
  - est_total_spend: 매체비 x 매체별 총광고비 배수 = 수주액 추정 (KRW).
  - est_monthly_spend: 역추산 월 수주액 (매체비+마진, KRW).
  - est_monthly_media_cost: 역추산 월 순수 매체비 (KRW).
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import Advertiser, Campaign, SpendEstimate
from database.schemas import SpendEstimateOut
from processor.spend_reverse_estimator import (
    REAL_EXECUTION_BENCHMARKS,
    estimate_catalog_daily_spend,
    estimate_from_meta_signals,
    get_total_spend_multiplier,
)

router = APIRouter(
    prefix="/api/spend",
    tags=["spend"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/estimates", response_model=list[SpendEstimateOut])
async def list_estimates(
    campaign_id: int | None = None,
    channel: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """광고비 추정 데이터 조회.

    spend_estimates 테이블 레코드를 반환합니다.
    각 레코드의 est_daily_spend는 해당일 해당 채널의 추정 매체비(KRW)입니다.
    """
    query = select(SpendEstimate).order_by(SpendEstimate.date.desc())

    if campaign_id:
        query = query.where(SpendEstimate.campaign_id == campaign_id)
    if channel:
        query = query.where(SpendEstimate.channel == channel)
    if date_from:
        query = query.where(SpendEstimate.date >= date_from)
    if date_to:
        query = query.where(SpendEstimate.date <= date_to)

    query = query.limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/summary")
async def spend_summary(
    days: int = Query(default=30, le=90),
    channel: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """채널별 추정 광고비 요약.

    campaigns.total_est_spend (30일 투영) 기준으로 집계합니다.
    캠페인 페이지와 동일한 수치를 반환합니다.
    """
    query = (
        select(
            Campaign.channel,
            func.sum(Campaign.total_est_spend).label("total_spend"),
            func.count(Campaign.id).label("data_points"),
        )
        .where(Campaign.total_est_spend > 0)
        .group_by(Campaign.channel)
    )

    if channel:
        query = query.where(Campaign.channel == channel)

    result = await db.execute(query)

    # avg_confidence from spend_estimates
    conf_query = (
        select(
            SpendEstimate.channel,
            func.avg(SpendEstimate.confidence).label("avg_confidence"),
        )
        .group_by(SpendEstimate.channel)
    )
    conf_result = await db.execute(conf_query)
    conf_map = {row[0]: round(row[1] or 0, 2) for row in conf_result.all()}

    return [
        {
            "channel": row[0],
            "total_spend": round(row[1] or 0),
            "avg_confidence": conf_map.get(row[0], 0.5),
            "data_points": row[2],
        }
        for row in result.all()
    ]


@router.get("/by-advertiser")
async def spend_by_advertiser(
    days: int = Query(default=30, le=90),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """광고주별 추정 광고비 랭킹.

    campaigns.total_est_spend (30일 투영) 기준으로 집계합니다.
    캠페인 페이지와 동일한 수치를 반환합니다.
    """
    query = (
        select(
            Advertiser.name,
            func.sum(Campaign.total_est_spend).label("total_spend"),
        )
        .join(Advertiser, Advertiser.id == Campaign.advertiser_id)
        .where(Campaign.total_est_spend > 0)
        .group_by(Advertiser.name)
        .order_by(func.sum(Campaign.total_est_spend).desc())
        .limit(limit)
    )

    result = await db.execute(query)
    return [
        {
            "advertiser": row[0],
            "total_spend": round(row[1] or 0),
        }
        for row in result.all()
    ]


@router.get("/reverse-estimate")
async def reverse_estimate_from_signals(
    advertiser_name: str = Query(..., description="광고주명"),
    search_query_delta: float = Query(default=0, description="검색쿼리 변화량"),
    channel_views_delta: float = Query(default=0, description="채널조회수 변화량"),
    social_engagement_delta: float = Query(default=0, description="소셜인게이지먼트 변화량"),
    period_days: int = Query(default=30, description="측정 기간(일)"),
):
    """메타시그널 기반 광고비 역추산.

    검색쿼리/채널조회/소셜인게이지먼트 변화량에서 광고비를 역산합니다.
    계수: search_query=0.07, channel_views=0.03, social_engagement=0.04

    Returns:
        - est_monthly_spend: 월간 총 수주액 추정 (매체비 + 대행마진, KRW)
        - est_monthly_media_cost: 월간 순수 매체비 추정 (KRW)
        - confidence: 추정 신뢰도 (0.0~1.0)
        - method: 사용된 역추산 방법
        - factors: 역추산에 사용된 세부 계수
    """
    est = estimate_from_meta_signals(
        advertiser_name=advertiser_name,
        search_query_delta=search_query_delta,
        channel_views_delta=channel_views_delta,
        social_engagement_delta=social_engagement_delta,
        period_days=period_days,
    )
    if est is None:
        return {"error": "No signal deltas provided", "estimated_spend": 0}

    return {
        "advertiser": advertiser_name,
        "method": est.method,
        "est_monthly_spend": est.est_monthly_spend,          # 월 수주액 추정 (매체비+마진, KRW)
        "est_monthly_media_cost": est.est_monthly_media_cost,  # 월 순수 매체비 추정 (KRW)
        "confidence": est.confidence,
        "factors": est.factors,
    }


@router.get("/execution-benchmarks")
async def execution_benchmarks():
    """실제 집행 데이터 기반 매체별 벤치마크 반환.

    매체비율, 대행사수수료율, 총광고비 배수(media_spend -> total_cost 변환 계수) 등.
    Source: 미디어광고결과 CSV (160건 실제 집행 데이터).
    """
    return {
        "benchmarks": REAL_EXECUTION_BENCHMARKS,
        "description": "Source: media_20260219.csv (160건 실제 집행 데이터). "
                       "total_multiplier = 매체비 -> 수주액(매체비+대행마진) 변환 배수.",
    }


@router.get("/by-advertiser-enriched")
async def spend_by_advertiser_enriched(
    days: int = Query(default=30, le=90),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """광고주별 채널별 추정 광고비 (매체비 + 수주액 환산 포함).

    campaigns.total_est_spend (30일 투영) 기준으로 집계합니다.
    """
    query = (
        select(
            Advertiser.name,
            Campaign.channel,
            func.sum(Campaign.total_est_spend).label("total_media_spend"),
            func.count(Campaign.id).label("data_points"),
        )
        .join(Advertiser, Advertiser.id == Campaign.advertiser_id)
        .where(Campaign.total_est_spend > 0)
        .group_by(Advertiser.name, Campaign.channel)
        .order_by(func.sum(Campaign.total_est_spend).desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = []
    for row in result.all():
        media_spend = round(row[2] or 0)
        channel = row[1]
        total_mult = get_total_spend_multiplier(channel)
        rows.append({
            "advertiser": row[0],
            "channel": channel,
            "media_spend": media_spend,
            "est_total_spend": round(media_spend * total_mult),
            "total_multiplier": total_mult,
            "avg_confidence": 0.5,
            "data_points": row[3],
        })
    return rows


@router.get("/google-ads-transparency")
async def google_ads_transparency(
    advertiser: str | None = None,
    domain: str | None = None,
    format: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    """SerpApi로 수집한 Google Ads Transparency Center 데이터."""
    import aiosqlite

    async with aiosqlite.connect("adscope.db") as db:
        db.row_factory = aiosqlite.Row
        where = []
        params = []

        if advertiser:
            where.append("advertiser_name LIKE ?")
            params.append(f"%{advertiser}%")
        if domain:
            where.append("target_domain LIKE ?")
            params.append(f"%{domain}%")
        if format:
            where.append("format = ?")
            params.append(format)

        where_clause = " AND ".join(where) if where else "1=1"

        cursor = await db.execute(f"""
            SELECT COUNT(*) FROM serpapi_ads WHERE {where_clause}
        """, params)
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(f"""
            SELECT * FROM serpapi_ads
            WHERE {where_clause}
            ORDER BY collected_at DESC
            LIMIT ? OFFSET ?
        """, params + [limit, offset])
        rows = await cursor.fetchall()

    return {
        "total": total,
        "items": [dict(r) for r in rows],
    }


@router.get("/market-coverage")
async def market_coverage():
    """ADIC 시장 데이터 vs AdScope 수집 커버리지 비교."""
    import aiosqlite

    async with aiosqlite.connect("adscope.db") as db:
        db.row_factory = aiosqlite.Row

        # ADIC top 100 total ad spend (4-media, 천원 단위)
        cursor = await db.execute("""
            SELECT SUM(amount) as total_4media,
                   COUNT(DISTINCT advertiser_name) as adic_advertisers
            FROM adic_ad_expenses
            WHERE medium = 'total' AND month IS NOT NULL
        """)
        adic = await cursor.fetchone()
        adic_total = (adic["total_4media"] or 0) * 1000  # 원 단위

        # Digital ratio: 1.73 (market avg)
        digital_ratio = 1.73
        est_digital = round(adic_total * digital_ratio)

        # AdScope spend estimates
        cursor = await db.execute("""
            SELECT SUM(est_daily_spend) as total, COUNT(*) as cnt
            FROM spend_estimates
        """)
        adscope = await cursor.fetchone()
        adscope_total = adscope["total"] or 0

        # SerpApi ads
        cursor = await db.execute("SELECT COUNT(*) FROM serpapi_ads")
        serpapi_count = (await cursor.fetchone())[0]

        # Keywords with Naver stats
        cursor = await db.execute("""
            SELECT COUNT(*) FROM keywords
            WHERE monthly_search_vol IS NOT NULL AND monthly_search_vol > 0
        """)
        kw_count = (await cursor.fetchone())[0]

    coverage = (adscope_total / est_digital * 100) if est_digital > 0 else 0

    return {
        "adic_top100_4media_spend": adic_total,
        "adic_advertisers": adic["adic_advertisers"],
        "estimated_digital_spend": est_digital,
        "digital_ratio": digital_ratio,
        "adscope_estimated_spend": round(adscope_total),
        "coverage_pct": round(coverage, 3),
        "serpapi_google_ads": serpapi_count,
        "naver_keywords_with_stats": kw_count,
    }


@router.get("/market-scale")
async def market_scale_summary(
    days: int = Query(default=30, le=90),
):
    """전체 디지털 광고 시장 규모 대비 보정 추정.

    카탈로그+서프 수집 → 매체이용량 보정 → 시장규모 보정 결과.
    검색/쇼핑 채널은 제외 (소형 광고주 다수).
    """
    from processor.market_scaler import get_market_summary
    return await get_market_summary(days=days)
