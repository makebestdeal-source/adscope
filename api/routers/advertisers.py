"""광고주 분석 API -- 검색, 트리 조회, 광고비 리포트, 매체 분석."""

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from api.deps import get_current_user, require_admin, require_paid
from sqlalchemy import cast, func, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    AdDetail, AdSnapshot, Advertiser, AdvertiserFavorite,
    Campaign, Industry, Keyword, SpendEstimate, User,
)
from database.schemas import (
    AdvertiserOut,
    AdvertiserProfileOut,
    AdvertiserProfileUpdate,
    AdvertiserSearchResult,
    AdvertiserSpendReport,
    AdvertiserTreeOut,
    BrandTreeChild,
    BrandTreeGroup,
    BrandTreeResponse,
    CampaignOut,
    ChannelSpendSummary,
    DailySpendPoint,
    UnifiedSearchResult,
)
from processor.channel_utils import (
    MEDIA_CATEGORIES,
    MEDIA_CATEGORY_KO,
    get_media_category as _channel_to_category,
)

router = APIRouter(
    prefix="/api/advertisers",
    tags=["advertisers"],
    redirect_slashes=False,
    dependencies=[Depends(get_current_user)],
)

KST = timezone(timedelta(hours=9))


# ── 기존 API ──


@router.get("", response_model=list[AdvertiserOut])
async def list_advertisers(
    industry_id: int | None = None,
    search: str | None = None,
    limit: int = Query(default=5000, le=10000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """광고주 목록 조회."""
    query = select(Advertiser).order_by(Advertiser.name)

    if industry_id:
        query = query.where(Advertiser.industry_id == industry_id)
    if search:
        query = query.where(Advertiser.name.ilike(f"%{search}%"))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/ranking/top")
async def top_advertisers(
    channel: str | None = None,
    days: int = Query(default=30, le=90),
    limit: int = Query(default=50, le=500),
    contact_only: bool = Query(default=False, description="True=접촉 데이터만, False=전체"),
    db: AsyncSession = Depends(get_db),
):
    """광고 노출 빈도 기준 상위 광고주."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    query = (
        select(
            AdDetail.advertiser_name_raw,
            func.count(AdDetail.id).label("ad_count"),
        )
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.advertiser_name_raw.isnot(None))
        .where(AdDetail.advertiser_name_raw != "")
        .group_by(AdDetail.advertiser_name_raw)
        .order_by(func.count(AdDetail.id).desc())
        .limit(limit)
    )

    if channel:
        query = query.where(AdSnapshot.channel == channel)
    if contact_only:
        query = query.where(AdDetail.is_contact == True)

    result = await db.execute(query)
    return [
        {"advertiser": row[0], "ad_count": row[1]}
        for row in result.all()
    ]


# ── 광고주 검증 통계 ──


@router.get("/verification-stats")
async def verification_stats(
    days: int = Query(default=30, le=90),
    db: AsyncSession = Depends(get_db),
):
    """광고주명 검증 상태 분포 요약."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # verification_status 분포
    status_result = await db.execute(
        select(
            AdDetail.verification_status,
            func.count(AdDetail.id),
        )
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at >= cutoff)
        .group_by(AdDetail.verification_status)
    )
    status_dist = {(row[0] or "null"): row[1] for row in status_result.all()}

    # NULL 광고주명 수
    null_names = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.advertiser_name_raw.is_(None))
    )

    # 전체 광고주 수
    total_advertisers = await db.execute(select(func.count(Advertiser.id)))

    # 광고 연결 없는 고아 광고주
    orphan_count = await db.execute(
        select(func.count(Advertiser.id)).where(
            ~Advertiser.id.in_(
                select(AdDetail.advertiser_id)
                .where(AdDetail.advertiser_id.is_not(None))
                .distinct()
            )
        )
    )

    return {
        "period_days": days,
        "verification_status_distribution": status_dist,
        "null_advertiser_names": null_names.scalar_one(),
        "total_advertisers": total_advertisers.scalar_one(),
        "orphan_advertisers": orphan_count.scalar_one(),
    }


# ── 광고주 검색 (R12 핵심) ──


@router.get("/search", response_model=list[AdvertiserSearchResult])
async def search_advertiser(
    q: str = Query(..., min_length=1, description="검색어 (이름, 브랜드, 제품, 별칭)"),
    include_children: bool = Query(default=True, description="하위 계열사/브랜드 포함"),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """광고주 검색 — 이름, 브랜드, 제품명, 별칭으로 통합 검색.

    트리 구조의 하위 항목도 포함하여 반환.
    """
    search_term = f"%{q}%"
    results: list[dict] = []
    seen_ids: set[int] = set()

    # 1) 이름/브랜드 직접 매칭
    name_query = (
        select(Advertiser)
        .where(
            or_(
                Advertiser.name.ilike(search_term),
                Advertiser.brand_name.ilike(search_term),
            )
        )
        .limit(limit)
    )
    rows = (await db.execute(name_query)).scalars().all()
    for adv in rows:
        if adv.id not in seen_ids:
            seen_ids.add(adv.id)
            results.append({**_adv_to_dict(adv), "match_type": "exact"})

    # 2) 별칭(aliases) 매칭 — JSON 배열 검색
    if len(results) < limit:
        # PostgreSQL: aliases::text ILIKE '%q%'
        alias_query = (
            select(Advertiser)
            .where(cast(Advertiser.aliases, String).ilike(search_term))
            .limit(limit - len(results))
        )
        alias_rows = (await db.execute(alias_query)).scalars().all()
        for adv in alias_rows:
            if adv.id not in seen_ids:
                seen_ids.add(adv.id)
                results.append({**_adv_to_dict(adv), "match_type": "alias"})

    # 3) 하위 계열사/브랜드 포함
    if include_children and results:
        parent_ids = [r["id"] for r in results]
        children_query = (
            select(Advertiser)
            .where(Advertiser.parent_id.in_(parent_ids))
        )
        children = (await db.execute(children_query)).scalars().all()
        for child in children:
            if child.id not in seen_ids:
                seen_ids.add(child.id)
                results.append({**_adv_to_dict(child), "match_type": "child"})

    return results[:limit]


# ── 통합 검색 (Phase 3F) ──


@router.get("/unified-search", response_model=UnifiedSearchResult)
async def unified_search(
    q: str = Query(..., min_length=1, description="통합 검색어"),
    search_type: str = Query(
        default="all",
        description="검색 범위: all | advertiser | industry | competitor",
    ),
    days: int = Query(default=30, le=365),
    limit: int = Query(default=30, le=100),
    db: AsyncSession = Depends(get_db),
):
    """통합 검색 — 광고주/업종/경쟁사/광고텍스트/랜딩 사업자명 교차 검색.

    5단계 검색:
    1. 광고주명 직접 매칭 (이름/브랜드/별칭)
    2. 업종 매칭 (같은 업종 광고주)
    3. 경쟁사 매칭 (같은 키워드에 노출된 다른 광고주)
    4. 광고 텍스트 매칭 (소재에서 검색어 포함)
    5. 랜딩 분석 매칭 (사업자명에서 검색어 포함)
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    search_term = f"%{q}%"
    result = UnifiedSearchResult()

    # 1) 광고주명 직접 매칭
    if search_type in ("all", "advertiser"):
        adv_query = (
            select(Advertiser)
            .where(
                or_(
                    Advertiser.name.ilike(search_term),
                    Advertiser.brand_name.ilike(search_term),
                    cast(Advertiser.aliases, String).ilike(search_term),
                )
            )
            .limit(limit)
        )
        adv_rows = (await db.execute(adv_query)).scalars().all()
        result.advertisers = [
            AdvertiserSearchResult(**_adv_to_dict(a), match_type="exact")
            for a in adv_rows
        ]

    # 2) 업종 매칭 — 1에서 매칭된 광고주의 업종에 속한 다른 광고주
    if search_type in ("all", "industry") and result.advertisers:
        industry_ids = {
            a.industry_id for a in result.advertisers if a.industry_id
        }
        matched_ids = {a.id for a in result.advertisers}

        if industry_ids:
            ind_query = (
                select(Advertiser)
                .where(
                    Advertiser.industry_id.in_(list(industry_ids)),
                    ~Advertiser.id.in_(list(matched_ids)),
                )
                .limit(limit)
            )
            ind_rows = (await db.execute(ind_query)).scalars().all()
            result.industry_matches = [
                AdvertiserSearchResult(**_adv_to_dict(a), match_type="industry")
                for a in ind_rows
            ]

    # 3) 경쟁사 매칭 — 같은 키워드에 노출된 다른 광고주
    if search_type in ("all", "competitor"):
        # 검색어를 키워드로 사용하는 스냅샷의 다른 광고주
        comp_query = (
            select(
                AdDetail.advertiser_name_raw,
                func.count(AdDetail.id).label("ad_count"),
            )
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
            .where(
                Keyword.keyword.ilike(search_term),
                AdSnapshot.captured_at >= cutoff,
                AdDetail.advertiser_name_raw.isnot(None),
                AdDetail.advertiser_name_raw != "",
            )
            .group_by(AdDetail.advertiser_name_raw)
            .order_by(func.count(AdDetail.id).desc())
            .limit(limit)
        )
        comp_rows = (await db.execute(comp_query)).all()
        result.competitor_ads = [
            {"advertiser": row[0], "ad_count": row[1]}
            for row in comp_rows
        ]

    # 4) 광고 텍스트 매칭
    if search_type in ("all",):
        text_query = (
            select(
                AdDetail.advertiser_name_raw,
                AdDetail.ad_text,
                AdDetail.url,
                AdSnapshot.channel,
            )
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(
                AdDetail.ad_text.ilike(search_term),
                AdSnapshot.captured_at >= cutoff,
            )
            .order_by(AdSnapshot.captured_at.desc())
            .limit(min(limit, 20))
        )
        text_rows = (await db.execute(text_query)).all()
        result.ad_text_matches = [
            {
                "advertiser": row[0],
                "ad_text": (row[1] or "")[:100],
                "url": row[2],
                "channel": row[3],
            }
            for row in text_rows
        ]

    # 5) 랜딩 분석 매칭 (extra_data JSON 검색)
    if search_type in ("all",):
        try:
            landing_query = (
                select(
                    AdDetail.id,
                    AdDetail.advertiser_name_raw,
                    AdDetail.url,
                    AdDetail.extra_data,
                )
                .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                .where(
                    AdSnapshot.captured_at >= cutoff,
                    cast(AdDetail.extra_data, String).ilike(search_term),
                )
                .limit(min(limit, 20))
            )
            landing_rows = (await db.execute(landing_query)).all()
            result.landing_matches = [
                {
                    "ad_detail_id": row[0],
                    "advertiser": row[1],
                    "url": row[2],
                    "landing_analysis": (row[3] or {}).get("landing_analysis"),
                }
                for row in landing_rows
            ]
        except Exception:
            # extra_data JSON 검색이 지원되지 않는 경우 무시
            pass

    return result


# ── 매체 카테고리별 광고 비중 (media-breakdown) ──


@router.get("/media-breakdown/{advertiser_id}")
async def media_breakdown(
    advertiser_id: int,
    days: int = Query(default=30, le=365, description="period (days)"),
    include_children: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """advertiser media category breakdown -- ad count & est spend by media category."""
    # KST cutoff
    now_kst = datetime.now(KST)
    cutoff_kst = now_kst - timedelta(days=days)
    cutoff_utc = cutoff_kst.astimezone(timezone.utc).replace(tzinfo=None)

    # advertiser lookup
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = adv_result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    # target IDs (include children)
    target_ids = {advertiser_id}
    if include_children:
        children_result = await db.execute(
            select(Advertiser.id).where(Advertiser.parent_id == advertiser_id)
        )
        for row in children_result.all():
            target_ids.add(row[0])

    # industry name
    industry_name = None
    if advertiser.industry_id:
        ind_result = await db.execute(
            select(Industry.name).where(Industry.id == advertiser.industry_id)
        )
        industry_name = ind_result.scalar_one_or_none()

    # 1) channel-level ad count (from ad_details + ad_snapshots)
    channel_count_result = await db.execute(
        select(
            AdSnapshot.channel,
            func.count(AdDetail.id).label("ad_count"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.advertiser_id.in_(list(target_ids)),
            AdSnapshot.captured_at >= cutoff_utc,
        )
        .group_by(AdSnapshot.channel)
    )
    channel_ad_counts: dict[str, int] = {}
    for ch, cnt in channel_count_result.all():
        channel_ad_counts[ch] = cnt

    # 2) channel-level est_spend (from spend_estimates via campaigns)
    campaign_result = await db.execute(
        select(Campaign.id, Campaign.channel)
        .where(
            Campaign.advertiser_id.in_(list(target_ids)),
            Campaign.last_seen >= cutoff_utc,
        )
    )
    campaign_rows = campaign_result.all()
    campaign_ids = [r[0] for r in campaign_rows]
    campaign_channel_map: dict[int, str] = {r[0]: r[1] for r in campaign_rows}

    channel_spend: dict[str, float] = {}
    if campaign_ids:
        spend_result = await db.execute(
            select(
                SpendEstimate.campaign_id,
                func.sum(SpendEstimate.est_daily_spend).label("total_spend"),
            )
            .where(
                SpendEstimate.campaign_id.in_(campaign_ids),
                SpendEstimate.date >= cutoff_utc,
            )
            .group_by(SpendEstimate.campaign_id)
        )
        for cid, total in spend_result.all():
            ch = campaign_channel_map.get(cid, "unknown")
            channel_spend[ch] = channel_spend.get(ch, 0.0) + (total or 0.0)

    # all channels
    all_channels = set(channel_ad_counts.keys()) | set(channel_spend.keys())

    # by_channel list
    by_channel = []
    for ch in sorted(all_channels):
        by_channel.append({
            "channel": ch,
            "category": MEDIA_CATEGORY_KO.get(_channel_to_category(ch), _channel_to_category(ch)),
            "ad_count": channel_ad_counts.get(ch, 0),
            "est_spend": round(channel_spend.get(ch, 0.0), 2),
        })

    # aggregate by category
    cat_data: dict[str, dict] = {}
    for ch_item in by_channel:
        cat_key = _channel_to_category(ch_item["channel"])
        if cat_key not in cat_data:
            cat_data[cat_key] = {"channels": [], "ad_count": 0, "est_spend": 0.0}
        cat_data[cat_key]["channels"].append(ch_item["channel"])
        cat_data[cat_key]["ad_count"] += ch_item["ad_count"]
        cat_data[cat_key]["est_spend"] += ch_item["est_spend"]

    total_ads = sum(c["ad_count"] for c in cat_data.values())
    total_spend = sum(c["est_spend"] for c in cat_data.values())

    categories = []
    for cat_key in ["video", "social", "portal", "network"]:
        if cat_key not in cat_data:
            continue
        d = cat_data[cat_key]
        ratio = d["est_spend"] / total_spend if total_spend > 0 else (
            d["ad_count"] / total_ads if total_ads > 0 else 0.0
        )
        categories.append({
            "category": MEDIA_CATEGORY_KO[cat_key],
            "category_key": cat_key,
            "channels": sorted(set(d["channels"])),
            "ad_count": d["ad_count"],
            "est_spend": round(d["est_spend"], 2),
            "ratio": round(ratio, 4),
        })

    # recent ads with images (for gallery)
    gallery_result = await db.execute(
        select(
            AdDetail.id,
            AdDetail.advertiser_name_raw,
            AdDetail.ad_text,
            AdDetail.ad_type,
            AdDetail.creative_image_path,
            AdDetail.url,
            AdDetail.brand,
            AdSnapshot.channel,
            AdSnapshot.captured_at,
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.advertiser_id.in_(list(target_ids)),
            AdSnapshot.captured_at >= cutoff_utc,
            AdDetail.creative_image_path.isnot(None),
            AdDetail.creative_image_path != "",
        )
        .order_by(AdSnapshot.captured_at.desc())
        .limit(20)
    )
    recent_ads = []
    for row in gallery_result.all():
        img_path = row[4]
        if img_path and not os.path.exists(img_path):
            img_path = None
        recent_ads.append({
            "id": row[0],
            "advertiser_name_raw": row[1],
            "ad_text": row[2],
            "ad_type": row[3],
            "creative_image_path": img_path,
            "url": row[5],
            "brand": row[6],
            "channel": row[7],
            "captured_at": row[8].isoformat() if row[8] else None,
        })

    return {
        "advertiser_id": advertiser.id,
        "advertiser_name": advertiser.name,
        "brand_name": advertiser.brand_name,
        "website": advertiser.website,
        "official_channels": advertiser.official_channels,
        "advertiser_type": advertiser.advertiser_type,
        "industry_name": industry_name,
        "total_ads": total_ads,
        "total_est_spend": round(total_spend, 2),
        "period_days": days,
        "categories": categories,
        "by_channel": by_channel,
        "recent_ads": recent_ads,
    }


# ── 브랜드 트리 전체 조회 ──


@router.get("/brand-tree", response_model=BrandTreeResponse)
async def get_brand_tree(db: AsyncSession = Depends(get_db)):
    """전체 그룹/광고주 브랜드 트리 반환 (duplicate 제외)."""
    # 모든 광고주 조회 (duplicate 제외)
    all_result = await db.execute(
        select(Advertiser)
        .where(or_(Advertiser.advertiser_type != "duplicate", Advertiser.advertiser_type.is_(None)))
        .order_by(Advertiser.name)
    )
    all_advertisers = all_result.scalars().all()

    # 광고주별 광고 수 집계 (최근 90일)
    cutoff = datetime.utcnow() - timedelta(days=90)
    count_result = await db.execute(
        select(
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("cnt"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdSnapshot.captured_at >= cutoff,
            AdDetail.advertiser_id.isnot(None),
        )
        .group_by(AdDetail.advertiser_id)
    )
    ad_counts: dict[int, int] = {row[0]: row[1] for row in count_result.all()}

    # ID -> Advertiser 매핑
    adv_map: dict[int, Advertiser] = {a.id: a for a in all_advertisers}
    # parent_id -> children 매핑
    children_map: dict[int, list[Advertiser]] = {}
    for a in all_advertisers:
        if a.parent_id and a.parent_id in adv_map:
            children_map.setdefault(a.parent_id, []).append(a)

    def _build_children(parent_id: int, depth: int = 0) -> list[BrandTreeChild]:
        if depth >= 4:
            return []
        kids = children_map.get(parent_id, [])
        result = []
        for child in kids:
            result.append(BrandTreeChild(
                id=child.id,
                name=child.name,
                advertiser_type=child.advertiser_type,
                website=child.website,
                brand_name=child.brand_name,
                ad_count=ad_counts.get(child.id, 0),
                children=_build_children(child.id, depth + 1),
            ))
        return result

    groups: list[BrandTreeGroup] = []
    independents: list[BrandTreeChild] = []
    has_parent = {a.id for a in all_advertisers if a.parent_id and a.parent_id in adv_map}

    for adv in all_advertisers:
        if adv.id in has_parent:
            # 하위 노드이므로 최상위에 표시하지 않음
            continue
        if adv.advertiser_type == "group":
            groups.append(BrandTreeGroup(
                id=adv.id,
                name=adv.name,
                advertiser_type=adv.advertiser_type,
                website=adv.website,
                children=_build_children(adv.id),
            ))
        else:
            independents.append(BrandTreeChild(
                id=adv.id,
                name=adv.name,
                advertiser_type=adv.advertiser_type,
                website=adv.website,
                brand_name=adv.brand_name,
                ad_count=ad_counts.get(adv.id, 0),
                children=_build_children(adv.id),
            ))

    return BrandTreeResponse(groups=groups, independents=independents)


# ── 즐겨찾기 Pydantic 스키마 ──


class FavoriteCreateIn(BaseModel):
    category: str | None = "monitoring"
    notes: str | None = None


class FavoriteUpdateIn(BaseModel):
    category: str | None = None
    notes: str | None = None
    is_pinned: bool | None = None
    sort_order: int | None = None


class FavoriteOut(BaseModel):
    id: int
    user_id: int
    advertiser_id: int
    category: str | None = "monitoring"
    notes: str | None = None
    is_pinned: bool = False
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # advertiser info
    advertiser_name: str | None = None
    brand_name: str | None = None
    industry_name: str | None = None
    website: str | None = None
    logo_url: str | None = None
    # stats
    recent_ad_count: int = 0
    total_est_spend: float = 0.0


class FavoriteStatusOut(BaseModel):
    is_favorite: bool
    category: str | None = None


# ── 즐겨찾기 API ──


@router.get("/favorites", response_model=list[FavoriteOut])
async def list_favorites(
    category: str | None = Query(default=None, description="카테고리 필터 (monitoring, competing, interested, other)"),
    search: str | None = Query(default=None, description="광고주 이름 검색"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 즐겨찾기 광고주 목록 조회."""
    cutoff = datetime.utcnow() - timedelta(days=30)

    # Base query: favorites + advertiser join
    query = (
        select(
            AdvertiserFavorite,
            Advertiser.name.label("advertiser_name"),
            Advertiser.brand_name.label("brand_name"),
            Advertiser.website.label("website"),
            Advertiser.logo_url.label("logo_url"),
            Industry.name.label("industry_name"),
        )
        .join(Advertiser, AdvertiserFavorite.advertiser_id == Advertiser.id)
        .outerjoin(Industry, Advertiser.industry_id == Industry.id)
        .where(AdvertiserFavorite.user_id == current_user.id)
    )

    if category:
        query = query.where(AdvertiserFavorite.category == category)
    if search:
        query = query.where(Advertiser.name.ilike(f"%{search}%"))

    query = query.order_by(
        AdvertiserFavorite.is_pinned.desc(),
        AdvertiserFavorite.sort_order.asc(),
        AdvertiserFavorite.created_at.desc(),
    )

    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return []

    # Collect advertiser IDs for stats subqueries
    adv_ids = [row[0].advertiser_id for row in rows]

    # Subquery: recent 30-day ad count per advertiser
    ad_count_result = await db.execute(
        select(
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("cnt"),
        )
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.advertiser_id.in_(adv_ids),
            AdSnapshot.captured_at >= cutoff,
        )
        .group_by(AdDetail.advertiser_id)
    )
    ad_counts: dict[int, int] = {row[0]: row[1] for row in ad_count_result.all()}

    # Subquery: total est_spend per advertiser (last 30 days)
    spend_result = await db.execute(
        select(
            Campaign.advertiser_id,
            func.sum(SpendEstimate.est_daily_spend).label("total_spend"),
        )
        .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
        .where(
            Campaign.advertiser_id.in_(adv_ids),
            SpendEstimate.date >= cutoff,
        )
        .group_by(Campaign.advertiser_id)
    )
    spend_map: dict[int, float] = {row[0]: row[1] or 0.0 for row in spend_result.all()}

    # Build response
    favorites = []
    for row in rows:
        fav: AdvertiserFavorite = row[0]
        favorites.append(FavoriteOut(
            id=fav.id,
            user_id=fav.user_id,
            advertiser_id=fav.advertiser_id,
            category=fav.category,
            notes=fav.notes,
            is_pinned=fav.is_pinned,
            sort_order=fav.sort_order,
            created_at=fav.created_at,
            updated_at=fav.updated_at,
            advertiser_name=row[1],
            brand_name=row[2],
            website=row[3],
            logo_url=row[4],
            industry_name=row[5],
            recent_ad_count=ad_counts.get(fav.advertiser_id, 0),
            total_est_spend=round(spend_map.get(fav.advertiser_id, 0.0), 2),
        ))

    return favorites


@router.post("/{advertiser_id}/favorite", response_model=FavoriteOut, status_code=201)
async def add_favorite(
    advertiser_id: int,
    body: FavoriteCreateIn = FavoriteCreateIn(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """광고주를 즐겨찾기에 추가."""
    # Check advertiser exists
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = adv_result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    # Check duplicate
    dup_result = await db.execute(
        select(AdvertiserFavorite).where(
            AdvertiserFavorite.user_id == current_user.id,
            AdvertiserFavorite.advertiser_id == advertiser_id,
        )
    )
    if dup_result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already in favorites")

    fav = AdvertiserFavorite(
        user_id=current_user.id,
        advertiser_id=advertiser_id,
        category=body.category or "monitoring",
        notes=body.notes,
    )
    db.add(fav)
    await db.commit()
    await db.refresh(fav)

    # Get industry name for response
    industry_name = None
    if advertiser.industry_id:
        ind_result = await db.execute(
            select(Industry.name).where(Industry.id == advertiser.industry_id)
        )
        industry_name = ind_result.scalar_one_or_none()

    return FavoriteOut(
        id=fav.id,
        user_id=fav.user_id,
        advertiser_id=fav.advertiser_id,
        category=fav.category,
        notes=fav.notes,
        is_pinned=fav.is_pinned,
        sort_order=fav.sort_order,
        created_at=fav.created_at,
        updated_at=fav.updated_at,
        advertiser_name=advertiser.name,
        brand_name=advertiser.brand_name,
        website=advertiser.website,
        logo_url=advertiser.logo_url,
        industry_name=industry_name,
    )


@router.delete("/{advertiser_id}/favorite", status_code=200)
async def remove_favorite(
    advertiser_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """광고주 즐겨찾기 해제."""
    result = await db.execute(
        select(AdvertiserFavorite).where(
            AdvertiserFavorite.user_id == current_user.id,
            AdvertiserFavorite.advertiser_id == advertiser_id,
        )
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")

    await db.delete(fav)
    await db.commit()
    return {"ok": True, "message": "Favorite removed"}


@router.put("/{advertiser_id}/favorite", response_model=FavoriteOut)
async def update_favorite(
    advertiser_id: int,
    body: FavoriteUpdateIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """즐겨찾기 정보 수정 (카테고리, 메모, 핀, 정렬순서)."""
    result = await db.execute(
        select(AdvertiserFavorite).where(
            AdvertiserFavorite.user_id == current_user.id,
            AdvertiserFavorite.advertiser_id == advertiser_id,
        )
    )
    fav = result.scalar_one_or_none()
    if not fav:
        raise HTTPException(status_code=404, detail="Favorite not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(fav, field, value)
    fav.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(fav)

    # Get advertiser info for response
    adv_result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = adv_result.scalar_one_or_none()

    industry_name = None
    if advertiser and advertiser.industry_id:
        ind_result = await db.execute(
            select(Industry.name).where(Industry.id == advertiser.industry_id)
        )
        industry_name = ind_result.scalar_one_or_none()

    return FavoriteOut(
        id=fav.id,
        user_id=fav.user_id,
        advertiser_id=fav.advertiser_id,
        category=fav.category,
        notes=fav.notes,
        is_pinned=fav.is_pinned,
        sort_order=fav.sort_order,
        created_at=fav.created_at,
        updated_at=fav.updated_at,
        advertiser_name=advertiser.name if advertiser else None,
        brand_name=advertiser.brand_name if advertiser else None,
        website=advertiser.website if advertiser else None,
        logo_url=advertiser.logo_url if advertiser else None,
        industry_name=industry_name,
    )


@router.get("/{advertiser_id}/favorite/status", response_model=FavoriteStatusOut)
async def favorite_status(
    advertiser_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자가 이 광고주를 즐겨찾기했는지 여부 확인."""
    result = await db.execute(
        select(AdvertiserFavorite).where(
            AdvertiserFavorite.user_id == current_user.id,
            AdvertiserFavorite.advertiser_id == advertiser_id,
        )
    )
    fav = result.scalar_one_or_none()
    if fav:
        return FavoriteStatusOut(is_favorite=True, category=fav.category)
    return FavoriteStatusOut(is_favorite=False)


def _adv_to_dict(adv: Advertiser) -> dict:
    return {
        "id": adv.id,
        "name": adv.name,
        "industry_id": adv.industry_id,
        "brand_name": adv.brand_name,
        "website": adv.website,
        "official_channels": adv.official_channels,
        "advertiser_type": adv.advertiser_type,
        "parent_id": adv.parent_id,
    }


# ── 광고주 트리 조회 (R13) ──


@router.get("/{advertiser_id}/tree", response_model=AdvertiserTreeOut)
async def get_advertiser_tree(
    advertiser_id: int,
    db: AsyncSession = Depends(get_db),
):
    """광고주의 트리 구조 조회 (그룹사→계열사→브랜드→제품)."""
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="광고주를 찾을 수 없습니다")

    # 최상위 부모 찾기
    root = advertiser
    visited = {root.id}
    while root.parent_id and root.parent_id not in visited:
        parent_result = await db.execute(
            select(Advertiser).where(Advertiser.id == root.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            break
        visited.add(parent.id)
        root = parent

    # 트리 구성
    tree = await _build_tree(db, root)
    return tree


async def _build_tree(db: AsyncSession, adv: Advertiser, depth: int = 0) -> dict:
    """재귀적으로 광고주 트리 구성 (최대 4단계)."""
    node = {
        "id": adv.id,
        "name": adv.name,
        "industry_id": adv.industry_id,
        "brand_name": adv.brand_name,
        "website": adv.website,
        "parent_id": adv.parent_id,
        "advertiser_type": adv.advertiser_type,
        "aliases": adv.aliases or [],
        "children": [],
    }

    if depth >= 4:
        return node

    children_result = await db.execute(
        select(Advertiser).where(Advertiser.parent_id == adv.id).order_by(Advertiser.name)
    )
    children = children_result.scalars().all()
    for child in children:
        child_node = await _build_tree(db, child, depth + 1)
        node["children"].append(child_node)

    return node


# ── 광고비 리포트 (R12 1순위 기능) ──


@router.get("/{advertiser_id}/spend-report", response_model=AdvertiserSpendReport)
async def advertiser_spend_report(
    advertiser_id: int,
    days: int = Query(default=30, le=365, description="조회 기간 (일)"),
    include_children: bool = Query(default=True, description="하위 계열사 광고비 합산"),
    db: AsyncSession = Depends(get_db),
):
    """핵심 지표: 광고주의 매체별 광고비 + 기간 리포트.

    특정 광고주가 어떤 매체에 얼마의 광고비를 어느 기간 동안 쓰고 있는지 반환.
    """
    # 광고주 조회
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="광고주를 찾을 수 없습니다")

    # 대상 광고주 ID 수집 (하위 포함)
    target_ids = {advertiser_id}
    if include_children:
        children_result = await db.execute(
            select(Advertiser.id).where(Advertiser.parent_id == advertiser_id)
        )
        for row in children_result.all():
            target_ids.add(row[0])

    cutoff = datetime.utcnow() - timedelta(days=days)
    end_date = datetime.utcnow()

    # 캠페인 조회
    campaigns_result = await db.execute(
        select(Campaign)
        .where(
            Campaign.advertiser_id.in_(list(target_ids)),
            Campaign.last_seen >= cutoff,
        )
        .order_by(Campaign.last_seen.desc())
    )
    campaigns = campaigns_result.scalars().all()
    campaign_ids = [c.id for c in campaigns]

    # 광고비 추정 데이터
    if campaign_ids:
        spend_result = await db.execute(
            select(SpendEstimate)
            .where(
                SpendEstimate.campaign_id.in_(campaign_ids),
                SpendEstimate.date >= cutoff,
            )
            .order_by(SpendEstimate.date)
        )
        estimates = spend_result.scalars().all()
    else:
        estimates = []

    # 채널별 집계
    channel_data: dict[str, dict] = {}
    daily_data: dict[str, float] = {}

    for est in estimates:
        ch = est.channel
        if ch not in channel_data:
            channel_data[ch] = {"est_spend": 0.0, "ad_count": 0, "keywords": set(), "is_active": False}
        channel_data[ch]["est_spend"] += est.est_daily_spend
        channel_data[ch]["ad_count"] += 1

        day_str = est.date.strftime("%Y-%m-%d")
        daily_data[day_str] = daily_data.get(day_str, 0.0) + est.est_daily_spend

    # 캠페인에서 키워드/활성 상태 보강
    for campaign in campaigns:
        ch = campaign.channel
        if ch in channel_data:
            if campaign.is_active:
                channel_data[ch]["is_active"] = True

    # 위치 분포 (ad_details에서)
    if campaign_ids:
        position_result = await db.execute(
            select(
                AdSnapshot.channel,
                AdDetail.position_zone,
                func.count(AdDetail.id),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(
                AdDetail.advertiser_id.in_(list(target_ids)),
                AdSnapshot.captured_at >= cutoff,
            )
            .group_by(AdSnapshot.channel, AdDetail.position_zone)
        )
        for ch, zone, cnt in position_result.all():
            if ch in channel_data and zone:
                if "position_distribution" not in channel_data[ch]:
                    channel_data[ch]["position_distribution"] = {}
                channel_data[ch]["position_distribution"][zone] = cnt

    # 응답 구성
    total_spend = sum(cd["est_spend"] for cd in channel_data.values())

    by_channel = []
    for ch, data in sorted(channel_data.items(), key=lambda kv: -kv[1]["est_spend"]):
        by_channel.append(ChannelSpendSummary(
            channel=ch,
            est_spend=round(data["est_spend"], 2),
            ad_count=data["ad_count"],
            position_distribution=data.get("position_distribution", {}),
            is_active=data["is_active"],
        ))

    daily_trend = [
        DailySpendPoint(date=d, spend=round(s, 2))
        for d, s in sorted(daily_data.items())
    ]

    return AdvertiserSpendReport(
        advertiser=advertiser,
        total_est_spend=round(total_spend, 2),
        period={
            "start": cutoff.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        by_channel=by_channel,
        daily_trend=daily_trend,
        active_campaigns=campaigns[:20],
    )


# ── 기존 상세/캠페인 API ──


@router.get("/{advertiser_id}", response_model=AdvertiserTreeOut)
async def get_advertiser(advertiser_id: int, db: AsyncSession = Depends(get_db)):
    """광고주 상세 조회 (트리 정보 포함)."""
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="광고주를 찾을 수 없습니다")
    return advertiser


@router.get("/{advertiser_id}/campaigns", response_model=list[CampaignOut])
async def get_advertiser_campaigns(
    advertiser_id: int, db: AsyncSession = Depends(get_db)
):
    """광고주의 캠페인 목록."""
    result = await db.execute(
        select(Campaign)
        .where(Campaign.advertiser_id == advertiser_id)
        .order_by(Campaign.last_seen.desc())
    )
    return result.scalars().all()


# ── 광고주 프로필 API ──


@router.get("/{advertiser_id}/profile", response_model=AdvertiserProfileOut)
async def get_advertiser_profile(
    advertiser_id: int, db: AsyncSession = Depends(get_db)
):
    """광고주 프로필(백데이터 포함) 상세 조회."""
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")
    return advertiser


@router.put("/{advertiser_id}/profile", response_model=AdvertiserProfileOut)
async def update_advertiser_profile(
    advertiser_id: int,
    profile: AdvertiserProfileUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """광고주 프로필(백데이터) 수동 업데이트. Admin only."""
    result = await db.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = result.scalar_one_or_none()
    if not advertiser:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    update_data = profile.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(advertiser, field, value)

    advertiser.data_source = "manual"
    advertiser.profile_updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(advertiser)
    return advertiser
