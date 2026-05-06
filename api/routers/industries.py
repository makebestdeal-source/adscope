"""Industry landscape analysis API router."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from api.services.advertiser_names import display_market_advertiser_name
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    AdDetail,
    AdSnapshot,
    Advertiser,
    Campaign,
    Industry,
    SpendEstimate,
)
from database.schemas import (
    IndustryAdvertiserOut,
    IndustryLandscapeOut,
    IndustryMarketMapOut,
    IndustryOut,
    MarketMapPoint,
    SubcategoryBreakdown,
)
from database.models import ProductCategory

router = APIRouter(
    prefix="/api/industries",
    tags=["industries"],
    redirect_slashes=False,
)


@router.get("", response_model=list[IndustryOut])
async def list_industries(db: AsyncSession = Depends(get_db)):
    """List all industries with advertiser counts (last 30 days)."""
    cutoff = datetime.utcnow() - timedelta(days=30)

    result = await db.execute(select(Industry).order_by(Industry.name))
    industries = result.scalars().all()

    if not industries:
        return []

    industry_ids = [i.id for i in industries]

    # 최근 30일 광고 집행 광고주 수 (ad_details JOIN)
    count_result = await db.execute(
        select(
            Advertiser.industry_id,
            func.count(func.distinct(AdDetail.advertiser_id)).label("cnt"),
        )
        .join(AdDetail, AdDetail.advertiser_id == Advertiser.id)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            Advertiser.industry_id.in_(industry_ids),
            AdSnapshot.captured_at >= cutoff,
            or_(AdDetail.verification_status.is_(None), AdDetail.verification_status != "rejected"),
        )
        .group_by(Advertiser.industry_id)
    )
    count_map: dict[int, int] = {row[0]: row[1] for row in count_result.all()}

    # Fallback: 전체 광고주 수 (ad JOIN 없이) — ad 연결이 누락된 경우 보완
    total_adv_result = await db.execute(
        select(
            Advertiser.industry_id,
            func.count(Advertiser.id).label("cnt"),
        )
        .where(Advertiser.industry_id.in_(industry_ids))
        .group_by(Advertiser.industry_id)
    )
    total_adv_map: dict[int, int] = {row[0]: row[1] for row in total_adv_result.all()}

    items = []
    for ind in industries:
        # 최근 광고 집행 수 우선, 없으면 전체 등록 광고주 수
        ad_count = count_map.get(ind.id, 0)
        fallback = total_adv_map.get(ind.id, 0)
        items.append(
            IndustryOut(
                id=ind.id,
                name=ind.name,
                avg_cpc_min=ind.avg_cpc_min,
                avg_cpc_max=ind.avg_cpc_max,
                advertiser_count=ad_count if ad_count > 0 else fallback,
            )
        )
    return items


async def _build_landscape_advertisers(
    db: AsyncSession, industry_id: int, days: int, category_id: int | None = -999
) -> list[IndustryAdvertiserOut]:
    """Build advertiser landscape data for an industry within a time window.
    category_id=-999(default)=전체, category_id=None=미분류, category_id=N=해당 카테고리."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Fetch all advertisers in the industry
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.industry_id == industry_id)
    )
    advertisers = adv_result.scalars().all()

    if not advertisers:
        return []

    adv_ids = [a.id for a in advertisers]

    # Ad count and channels per advertiser (via ad_details -> ad_snapshots)
    cat_filters = [
        AdDetail.advertiser_id.in_(adv_ids),
        AdSnapshot.captured_at >= cutoff,
        or_(AdDetail.verification_status.is_(None), AdDetail.verification_status != "rejected"),
    ]
    if category_id == -999:
        pass  # 전체: 필터 없음
    elif category_id is None:
        cat_filters.append(AdDetail.product_category_id.is_(None))
    else:
        cat_filters.append(AdDetail.product_category_id == category_id)

    ad_stats = await db.execute(
        select(
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("ad_count"),
            func.group_concat(AdSnapshot.channel.distinct()).label("channels"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(*cat_filters)
        .group_by(AdDetail.advertiser_id)
    )
    ad_stats_map: dict[int, dict] = {}
    for row in ad_stats.all():
        channels_str = row.channels or ""
        channel_list = [c.strip() for c in channels_str.split(",") if c.strip()]
        ad_stats_map[row.advertiser_id] = {
            "ad_count": row.ad_count,
            "channels": channel_list,
        }

    # Total ads across all advertisers in the industry (for SOV calculation)
    total_ads_result = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(*cat_filters)
    )
    total_ads = total_ads_result.scalar() or 0

    # Estimated spend per advertiser (via campaigns -> spend_estimates)
    spend_result = await db.execute(
        select(
            Campaign.advertiser_id,
            func.sum(SpendEstimate.est_daily_spend).label("total_spend"),
        )
        .join(SpendEstimate, SpendEstimate.campaign_id == Campaign.id)
        .where(
            Campaign.advertiser_id.in_(adv_ids),
            SpendEstimate.date >= cutoff,
        )
        .group_by(Campaign.advertiser_id)
    )
    spend_map: dict[int, float] = {}
    for row in spend_result.all():
        spend_map[row.advertiser_id] = row.total_spend or 0.0

    # Build output list
    items: list[IndustryAdvertiserOut] = []
    for adv in advertisers:
        stats = ad_stats_map.get(adv.id, {"ad_count": 0, "channels": []})
        ad_count = stats["ad_count"]
        if ad_count <= 0:
            continue
        display_name = display_market_advertiser_name(adv.name, adv.brand_name)
        if not display_name:
            continue
        sov = (ad_count / total_ads * 100) if total_ads > 0 else 0.0
        est_spend = spend_map.get(adv.id, 0.0)

        items.append(
            IndustryAdvertiserOut(
                id=adv.id,
                name=display_name,
                brand_name=adv.brand_name,
                annual_revenue=adv.annual_revenue,
                employee_count=adv.employee_count,
                is_public=adv.is_public or False,
                est_ad_spend=round(est_spend, 2),
                sov_percentage=round(sov, 2),
                channel_count=len(stats["channels"]),
                channel_mix=stats["channels"],
                ad_count=ad_count,
            )
        )

    # Sort by SOV descending
    items.sort(key=lambda x: x.sov_percentage, reverse=True)
    return items


@router.get("/{industry_id}/subcategories", response_model=list[SubcategoryBreakdown])
async def get_industry_subcategories(
    industry_id: int,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """소분류별 광고주/광고 수 집계."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # 해당 업종의 product_categories
    cat_result = await db.execute(
        select(ProductCategory).where(ProductCategory.industry_id == industry_id)
    )
    categories = cat_result.scalars().all()

    # 해당 업종 광고주 IDs
    adv_result = await db.execute(
        select(Advertiser.id).where(Advertiser.industry_id == industry_id)
    )
    adv_ids = [r[0] for r in adv_result.all()]

    if not adv_ids:
        return []

    # 카테고리별 광고주/광고 수 (product_category_id 기준)
    stats_result = await db.execute(
        select(
            AdDetail.product_category_id,
            func.count(func.distinct(AdDetail.advertiser_id)).label("adv_cnt"),
            func.count(AdDetail.id).label("ad_cnt"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.advertiser_id.in_(adv_ids),
            AdSnapshot.captured_at >= cutoff,
            or_(AdDetail.verification_status.is_(None), AdDetail.verification_status != "rejected"),
        )
        .group_by(AdDetail.product_category_id)
    )

    cat_id_map = {c.id: c.name for c in categories}
    classified: dict[int | None, dict] = {}
    for row in stats_result.all():
        classified[row.product_category_id] = {
            "adv_cnt": row.adv_cnt,
            "ad_cnt": row.ad_cnt,
        }

    items: list[SubcategoryBreakdown] = []
    unclassified_adv = 0
    unclassified_ad = 0

    for cat in sorted(categories, key=lambda c: c.name):
        stats = classified.get(cat.id, {"adv_cnt": 0, "ad_cnt": 0})
        items.append(SubcategoryBreakdown(
            id=cat.id,
            name=cat.name,
            advertiser_count=stats["adv_cnt"],
            ad_count=stats["ad_cnt"],
        ))

    # 미분류: product_category_id가 None이거나 이 업종 외 카테고리인 경우
    for cat_id, stats in classified.items():
        if cat_id is None or cat_id not in cat_id_map:
            unclassified_adv += stats["adv_cnt"]
            unclassified_ad += stats["ad_cnt"]

    if unclassified_adv > 0 or unclassified_ad > 0:
        items.append(SubcategoryBreakdown(
            id=None,
            name="미분류",
            advertiser_count=unclassified_adv,
            ad_count=unclassified_ad,
        ))

    return items


@router.get("/{industry_id}/landscape", response_model=IndustryLandscapeOut)
async def get_industry_landscape(
    industry_id: int,
    days: int = Query(default=30, le=365),
    category_id: int | None = Query(default=None, alias="category_id"),
    unclassified: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Industry landscape analysis: advertisers ranked by share-of-voice.
    category_id: 특정 소분류 필터. unclassified=true: 미분류만."""
    # Fetch industry
    ind_result = await db.execute(
        select(Industry).where(Industry.id == industry_id)
    )
    industry = ind_result.scalar_one_or_none()
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")

    # category_id 파라미터 해석: 미전달=-999(전체), unclassified=None, 값=해당 카테고리
    if unclassified:
        eff_cat_id: int | None = None  # 미분류
    elif category_id is not None:
        eff_cat_id = category_id
    else:
        eff_cat_id = -999  # 전체

    advertisers = await _build_landscape_advertisers(db, industry_id, days, eff_cat_id)

    # Revenue ranking (only those with annual_revenue)
    revenue_ranking = sorted(
        [a for a in advertisers if a.annual_revenue],
        key=lambda x: x.annual_revenue or 0,
        reverse=True,
    )

    # Spend ranking
    spend_ranking = sorted(
        advertisers, key=lambda x: x.est_ad_spend, reverse=True
    )

    # Total market size estimate (sum of all estimated spends)
    total_market = sum(a.est_ad_spend for a in advertisers)

    return IndustryLandscapeOut(
        industry=IndustryOut.model_validate(industry),
        total_market_size=round(total_market, 2) if total_market > 0 else None,
        advertiser_count=len(advertisers),
        advertisers=advertisers,
        revenue_ranking=revenue_ranking[:20],
        spend_ranking=spend_ranking[:20],
    )


@router.get("/{industry_id}/market-map", response_model=IndustryMarketMapOut)
async def get_industry_market_map(
    industry_id: int,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Market map scatter plot: X=revenue, Y=ad_spend, size=SOV."""
    # Fetch industry
    ind_result = await db.execute(
        select(Industry).where(Industry.id == industry_id)
    )
    industry = ind_result.scalar_one_or_none()
    if not industry:
        raise HTTPException(status_code=404, detail="Industry not found")

    advertisers = await _build_landscape_advertisers(db, industry_id, days)

    points: list[MarketMapPoint] = []
    for adv in advertisers:
        # Only include advertisers that have revenue data for meaningful scatter plot
        revenue = adv.annual_revenue or 0
        points.append(
            MarketMapPoint(
                id=adv.id,
                name=adv.name,
                x=revenue,
                y=adv.est_ad_spend,
                size=max(adv.sov_percentage, 1.0),  # Minimum bubble size
                is_public=adv.is_public,
            )
        )

    return IndustryMarketMapOut(
        industry=IndustryOut.model_validate(industry),
        points=points,
        axis_labels={
            "x": "Annual Revenue (KRW)",
            "y": "Estimated Ad Spend (KRW)",
            "size": "Share of Voice (%)",
        },
    )
