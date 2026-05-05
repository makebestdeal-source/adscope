"""캠페인 추적 API.

금액 필드 규칙:
  - total_est_spend: Campaign 테이블 컬럼. 캠페인 누적 추정 매체비 (KRW).
  - total_spend (CampaignEffectOut): SUM(spend_estimates.est_daily_spend).
    캠페인 전체 기간 추정 매체비 합계 (KRW). 대행수수료 미포함 순수 매체비.
  - est_daily_spend: 일별 추정 매체비 (KRW).
"""

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, require_paid
from api.services.advertiser_links import (
    needs_context_advertiser_name,
    resolve_profile_advertiser_id,
)
from api.services.advertiser_names import (
    campaign_display_fields,
    clean_raw_advertiser_name,
)
from database import get_db
from database.models import (
    AdDetail, AdSnapshot, Advertiser, Campaign, CampaignLift, JourneyEvent, SpendEstimate,
)
from database.schemas import (
    CampaignCreativeItem, CampaignDetailOut, CampaignEffectOut, CampaignLiftOut,
    CampaignOut, CampaignUpdateIn, JourneyEventOut, SpendEstimateOut,
)

router = APIRouter(
    prefix="/api/campaigns",
    tags=["campaigns"],
    redirect_slashes=False,
)


def _as_id_list(value) -> list[int]:
    if not value:
        return []
    if isinstance(value, list):
        return [int(v) for v in value if str(v).isdigit()]
    if isinstance(value, str):
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [int(v) for v in parsed if str(v).isdigit()]
        except Exception:
            return [int(v) for v in value.split(",") if v.strip().isdigit()]
    return []


def _has_cjk_without_hangul(text: str) -> bool:
    """한자/일본어가 있고 한국어(한글)가 없으면 True."""
    has_cjk = bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff]", text))
    has_hangul = bool(re.search(r"[\uac00-\ud7a3\u1100-\u11ff]", text))
    return has_cjk and not has_hangul


def _is_foreign_advertiser(
    country: str | None,
    name: str | None,
    website: str | None,
    *extra_texts: str | None,
) -> bool:
    """국내 광고주(KR) 여부를 판별. 해외이면 True.
    extra_texts: 캠페인명·표시 광고주명 등 추가 텍스트 필드.
    """
    if country and country.upper() != "KR":
        return True
    # DB 광고주명 검사
    if _has_cjk_without_hangul(name or ""):
        return True
    # 추가 텍스트 필드 검사 (캠페인명, 표시 광고주명 등)
    for t in extra_texts:
        if t and _has_cjk_without_hangul(t):
            return True
    # 해외 도메인 TLD
    site = (website or "").lower()
    if re.search(r"\.(cn|com\.cn|jp|tw|hk|sg|vn|th)(/|$)", site):
        return True
    return False


async def _first_ad_context(db: AsyncSession, creative_ids) -> dict:
    ids = _as_id_list(creative_ids)[:5]
    if not ids:
        return {}
    row = (
        await db.execute(
            select(
                AdDetail.advertiser_name_raw,
                AdDetail.ad_text,
                AdDetail.url,
                AdDetail.brand,
                AdDetail.extra_data,
            ).where(AdDetail.id.in_(ids)).limit(1)
        )
    ).first()
    if not row:
        return {}
    return {
        "advertiser_name_raw": row.advertiser_name_raw,
        "ad_text": row.ad_text,
        "url": row.url,
        "brand": row.brand,
        "extra_data": row.extra_data,
    }


def _needs_subject(advertiser_name) -> bool:
    return needs_context_advertiser_name(advertiser_name)


def _context_brand_name(brand_name, advertiser_name, ad_ctx: dict):
    if brand_name:
        return brand_name
    if _needs_subject(advertiser_name):
        return ad_ctx.get("brand") or ad_ctx.get("advertiser_name_raw")
    return None


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
    """캠페인 목록 (광고주+월+제품 기준 그룹핑). 프론트 캠페인 리스트 페이지용.

    동일 광고주 + 동일 월 + 동일 제품(product_service)이면 채널을 합산해 1개 캠페인으로 표시.
    product_service가 NULL/빈값이면 같은 제품으로 간주.
    """
    from sqlalchemy import Integer, cast as sa_cast

    month_expr = func.strftime("%Y-%m", Campaign.first_seen)
    product_expr = func.coalesce(Campaign.product_service, "")

    query = (
        select(
            func.min(Campaign.id).label("id"),
            Campaign.advertiser_id,
            Advertiser.name.label("advertiser_name"),
            func.max(Advertiser.brand_name).label("brand_name"),
            func.max(Advertiser.website).label("website"),
            month_expr.label("month"),
            product_expr.label("product_service"),
            func.group_concat(Campaign.channel).label("channels_raw"),
            func.group_concat(Campaign.id).label("campaign_ids_raw"),
            func.max(Campaign.creative_ids).label("creative_ids"),
            func.sum(Campaign.total_est_spend).label("total_est_spend"),
            func.min(Campaign.first_seen).label("first_seen"),
            func.max(Campaign.last_seen).label("last_seen"),
            func.sum(Campaign.snapshot_count).label("snapshot_count"),
            func.max(Campaign.campaign_name).label("campaign_name"),
            func.max(Campaign.objective).label("objective"),
            func.max(Campaign.model_info).label("model_info"),
            func.max(Campaign.promotion_copy).label("promotion_copy"),
            func.max(Campaign.status).label("status"),
            func.max(sa_cast(Campaign.is_active, Integer)).label("is_active"),
            func.max(Advertiser.country).label("advertiser_country"),
        )
        .outerjoin(Advertiser, Campaign.advertiser_id == Advertiser.id)
        .group_by(Campaign.advertiser_id, month_expr, product_expr)
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

    # 정렬 (집계 함수 기반)
    sort_col = {
        "last_seen": func.max(Campaign.last_seen),
        "first_seen": func.min(Campaign.first_seen),
        "total_est_spend": func.sum(Campaign.total_est_spend),
        "advertiser_name": Advertiser.name,
        "snapshot_count": func.sum(Campaign.snapshot_count),
    }.get(sort_by, func.max(Campaign.last_seen))

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

    raw_items = []
    for r in rows:
        # GROUP_CONCAT 결과에서 채널 중복 제거
        channels = list(dict.fromkeys((r.channels_raw or "").split(",")))
        channels = [c for c in channels if c]
        campaign_ids = [int(x) for x in (r.campaign_ids_raw or "").split(",") if x.strip()]
        ad_ctx = await _first_ad_context(db, r.creative_ids)
        display = campaign_display_fields(
            campaign_name=r.campaign_name,
            advertiser_name=r.advertiser_name,
            brand_name=_context_brand_name(r.brand_name, r.advertiser_name, ad_ctx),
            website=r.website,
            url=ad_ctx.get("url"),
            ad_text=ad_ctx.get("ad_text"),
            product_service=r.product_service,
            model_info=r.model_info,
            promotion_copy=r.promotion_copy,
            extra_data=ad_ctx.get("extra_data"),
            campaign_id=r.id,
        )
        if _needs_subject(r.advertiser_name) and not display["subject"]:
            continue

        profile_advertiser_id = await resolve_profile_advertiser_id(
            db,
            current_id=r.advertiser_id,
            current_name=r.advertiser_name,
            display_name=display["advertiser_name"],
        )
        link_resolved = bool(profile_advertiser_id and profile_advertiser_id != r.advertiser_id)
        resolved_adv_id = profile_advertiser_id or r.advertiser_id

        raw_items.append({
            "id": r.id,
            "campaign_ids": campaign_ids,
            "advertiser_id": resolved_adv_id,
            "source_advertiser_id": r.advertiser_id,
            "profile_link_resolved": link_resolved,
            "advertiser_name": display["advertiser_name"],
            "channel": channels[0] if len(channels) == 1 else "multi",
            "channels": channels,
            "month": r.month,
            "campaign_name": display["campaign_name"],
            "advertised_subject": display["subject"],
            "objective": r.objective,
            "product_service": r.product_service or None,
            "model_info": r.model_info,
            "promotion_copy": r.promotion_copy,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            "is_active": bool(r.is_active),
            "total_est_spend": round(r.total_est_spend or 0),
            "snapshot_count": r.snapshot_count or 0,
            "status": r.status,
            "is_foreign": _is_foreign_advertiser(
                r.advertiser_country,
                r.advertiser_name,
                r.website,
                display["advertiser_name"],
                display["campaign_name"],
            ),
        })

    # advertiser_name + month + product_service 기준 재병합
    # (동일 브랜드가 복수 advertiser_id로 등록된 케이스 통합)
    merged: dict[tuple, dict] = {}
    for item in raw_items:
        name_key = (item["advertiser_name"] or "").strip().lower()
        # 이름이 없으면 advertiser_id로 대체 (잘못된 병합 방지)
        if not name_key:
            name_key = f"_id_{item['advertiser_id']}"
        key = (name_key, item["month"], item.get("product_service") or "")
        if key not in merged:
            merged[key] = item
        else:
            ex = merged[key]
            ex["campaign_ids"] = list(dict.fromkeys(ex["campaign_ids"] + item["campaign_ids"]))
            new_ch = ex["channels"] + [c for c in item["channels"] if c not in ex["channels"]]
            ex["channels"] = new_ch
            ex["channel"] = new_ch[0] if len(new_ch) == 1 else "multi"
            ex["total_est_spend"] += item["total_est_spend"]
            ex["snapshot_count"] += item["snapshot_count"]
            ex["is_active"] = ex["is_active"] or item["is_active"]
            ex["is_foreign"] = ex["is_foreign"] or item["is_foreign"]
            if item["last_seen"] and (not ex["last_seen"] or item["last_seen"] > ex["last_seen"]):
                ex["last_seen"] = item["last_seen"]
            if item["first_seen"] and (not ex["first_seen"] or item["first_seen"] < ex["first_seen"]):
                ex["first_seen"] = item["first_seen"]

    items = list(merged.values())

    return {
        "total": total,
        "total_spend_sum": total_spend_sum,
        "items": items,
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
    result = await db.execute(
        select(Campaign, Advertiser)
        .outerjoin(Advertiser, Campaign.advertiser_id == Advertiser.id)
        .where(Campaign.id == campaign_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign, advertiser = row
    advertiser_name = advertiser.name if advertiser else None

    # 연결 소재 조회 (최대 20건)
    creatives: list[CampaignCreativeItem] = []
    if campaign.creative_ids:
        ids = campaign.creative_ids[:20]
        cr_result = await db.execute(
            select(
                AdDetail.id,
                AdDetail.advertiser_name_raw,
                AdDetail.ad_text,
                AdDetail.ad_type,
                AdDetail.creative_image_path,
                AdDetail.url,
                AdDetail.extra_data,
                AdSnapshot.channel,
                AdSnapshot.captured_at,
            )
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdDetail.id.in_(ids))
        )
        import json
        for row2 in cr_result.all():
            extra = row2.extra_data
            if isinstance(extra, str):
                try:
                    extra = json.loads(extra)
                except Exception:
                    extra = None
            creatives.append(CampaignCreativeItem(
                id=row2.id,
                advertiser_name_raw=clean_raw_advertiser_name(row2.advertiser_name_raw),
                ad_text=row2.ad_text,
                ad_type=row2.ad_type,
                creative_image_path=row2.creative_image_path,
                url=row2.url,
                extra_data=extra,
                channel=row2.channel,
                captured_at=row2.captured_at,
            ))

    # advertiser JOIN 실패 시 → ad_details에서 advertiser_name_raw 폴백
    advertiser_exists = advertiser_name is not None
    if not advertiser_name and campaign.creative_ids:
        fb = await db.execute(
            select(AdDetail.advertiser_name_raw)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdDetail.id.in_(campaign.creative_ids[:5]))
            .limit(1)
        )
        fb_row = fb.first()
        if fb_row:
            advertiser_name = clean_raw_advertiser_name(fb_row[0])

    ad_ctx = {}
    if creatives:
        first = creatives[0]
        ad_ctx = {
            "advertiser_name_raw": first.advertiser_name_raw,
            "ad_text": first.ad_text,
            "url": first.url,
            "extra_data": first.extra_data,
        }
    display = campaign_display_fields(
        campaign_name=campaign.campaign_name,
        advertiser_name=advertiser_name,
        brand_name=_context_brand_name(advertiser.brand_name if advertiser else None, advertiser_name, ad_ctx),
        website=advertiser.website if advertiser else None,
        url=ad_ctx.get("url"),
        ad_text=ad_ctx.get("ad_text"),
        product_service=campaign.product_service,
        model_info=campaign.model_info,
        promotion_copy=campaign.promotion_copy,
        extra_data=ad_ctx.get("extra_data"),
        campaign_id=campaign.id,
    )

    out = CampaignDetailOut.model_validate(campaign)
    profile_advertiser_id = await resolve_profile_advertiser_id(
        db,
        current_id=campaign.advertiser_id,
        current_name=advertiser_name,
        display_name=display["advertiser_name"],
    )
    out.advertiser_id = profile_advertiser_id or campaign.advertiser_id
    out.advertiser_name = display["advertiser_name"]
    out.campaign_name = display["campaign_name"]
    out.advertiser_exists = advertiser_exists
    out.creatives = creatives
    return out


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
    advertiser = None
    if campaign.advertiser_id:
        adv_result = await db.execute(
            select(Advertiser).where(Advertiser.id == campaign.advertiser_id)
        )
        advertiser = adv_result.scalar_one_or_none()
    ad_ctx = await _first_ad_context(db, campaign.creative_ids)
    display = campaign_display_fields(
        campaign_name=campaign.campaign_name,
        advertiser_name=advertiser.name if advertiser else None,
        brand_name=_context_brand_name(advertiser.brand_name if advertiser else None, advertiser.name if advertiser else None, ad_ctx),
        website=advertiser.website if advertiser else None,
        url=ad_ctx.get("url"),
        ad_text=ad_ctx.get("ad_text"),
        product_service=campaign.product_service,
        model_info=campaign.model_info,
        promotion_copy=campaign.promotion_copy,
        extra_data=ad_ctx.get("extra_data"),
        campaign_id=campaign.id,
    )

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
        campaign_name=display["campaign_name"],
        advertiser_name=display["advertiser_name"],
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
    _current_user = Depends(get_current_user),
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
