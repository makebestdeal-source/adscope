"""광고 스냅샷 조회 API."""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.deps import get_current_user, require_plan, require_paid
from database import get_db
from database.models import AdDetail, AdSnapshot, Keyword, User
from database.schemas import AdSnapshotOut, AdSnapshotWithDetails
from processor.channel_utils import SEARCH_CHANNELS, normalize_channel_for_display

router = APIRouter(prefix="/api/ads", tags=["ads"],
    dependencies=[Depends(get_current_user)])


@router.get("/snapshots", response_model=list[AdSnapshotOut])
async def list_snapshots(
    channel: str | None = None,
    keyword: str | None = None,
    persona_code: str | None = None,
    device: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """광고 스냅샷 목록 조회 (필터링 지원)."""
    query = select(AdSnapshot).order_by(AdSnapshot.captured_at.desc())

    if channel:
        query = query.where(AdSnapshot.channel == channel)
    if persona_code:
        from database.models import Persona
        sub = select(Persona.id).where(Persona.code == persona_code)
        query = query.where(AdSnapshot.persona_id.in_(sub))
    if device:
        query = query.where(AdSnapshot.device == device)
    if date_from:
        query = query.where(AdSnapshot.captured_at >= date_from)
    if date_to:
        query = query.where(AdSnapshot.captured_at <= date_to)
    if keyword:
        sub = select(Keyword.id).where(Keyword.keyword.ilike(f"%{keyword}%"))
        query = query.where(AdSnapshot.keyword_id.in_(sub))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/snapshots/{snapshot_id}", response_model=AdSnapshotWithDetails)
async def get_snapshot(
    snapshot_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """스냅샷 상세 조회 (광고 상세 포함)."""
    query = (
        select(AdSnapshot)
        .options(selectinload(AdSnapshot.details))
        .where(AdSnapshot.id == snapshot_id)
    )
    result = await db.execute(query)
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="스냅샷을 찾을 수 없습니다")
    return snapshot


@router.get("/stats/daily")
async def daily_stats(
    date: datetime | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """일일 수집 통계. KST 기준 오늘. 데이터 없으면 최근 날짜로 fallback."""
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    target = date or now_kst
    # KST 00:00~23:59 → UTC로 변환 (DB는 UTC naive)
    kst_start = target.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    day_start = kst_start - timedelta(hours=9)
    day_end = day_start + timedelta(hours=23, minutes=59, seconds=59)

    # 오늘 데이터 존재 여부 확인 — 없으면 최신 날짜로 fallback
    if date is None:
        today_check = await db.execute(
            select(func.count(AdSnapshot.id)).where(
                AdSnapshot.captured_at.between(day_start, day_end)
            )
        )
        if (today_check.scalar() or 0) == 0:
            latest = await db.execute(
                select(func.max(AdSnapshot.captured_at))
            )
            latest_dt = latest.scalar()
            if latest_dt:
                # latest_dt는 UTC → KST로 변환 후 해당 날짜의 UTC 범위
                latest_kst = latest_dt + timedelta(hours=9)
                kst_day = latest_kst.replace(hour=0, minute=0, second=0, microsecond=0)
                day_start = kst_day - timedelta(hours=9)
                day_end = day_start + timedelta(hours=23, minutes=59, seconds=59)

    # 스냅샷 수
    snap_count = await db.execute(
        select(func.count(AdSnapshot.id)).where(
            AdSnapshot.captured_at.between(day_start, day_end)
        )
    )
    # 광고 수 (전체)
    ad_count = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at.between(day_start, day_end))
    )
    # 접촉 광고 수 (is_contact=True)
    contact_count = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at.between(day_start, day_end))
        .where(AdDetail.is_contact == True)
    )
    # 카탈로그 광고 수 (is_contact=False)
    catalog_count = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at.between(day_start, day_end))
        .where(AdDetail.is_contact == False)
    )
    # 채널별 분포
    channel_dist = await db.execute(
        select(AdSnapshot.channel, func.count(AdSnapshot.id))
        .where(AdSnapshot.captured_at.between(day_start, day_end))
        .group_by(AdSnapshot.channel)
    )
    # 접촉 채널별 분포
    contact_channel_dist = await db.execute(
        select(AdSnapshot.channel, func.count(AdDetail.id))
        .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at.between(day_start, day_end))
        .where(AdDetail.is_contact == True)
        .group_by(AdSnapshot.channel)
    )

    # 최근 수집 시각 (KST)
    latest_crawl_q = await db.execute(select(func.max(AdSnapshot.captured_at)))
    latest_crawl_dt = latest_crawl_q.scalar()
    latest_crawl_at = None
    if latest_crawl_dt:
        latest_crawl_at = (latest_crawl_dt + timedelta(hours=9)).isoformat()

    # 오늘 전체 수집 건수 (KST 기준)
    today_kst_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today_utc_start = today_kst_start - timedelta(hours=9)
    today_ads_q = await db.execute(
        select(func.count(AdDetail.id))
        .join(AdSnapshot)
        .where(AdSnapshot.captured_at >= today_utc_start)
    )
    today_total_ads = today_ads_q.scalar() or 0

    # 응답 날짜는 KST 기준
    display_date = (day_start + timedelta(hours=9)).date().isoformat()
    return {
        "date": display_date,
        "total_snapshots": snap_count.scalar() or 0,
        "total_ads": ad_count.scalar() or 0,
        "total_contacts": contact_count.scalar() or 0,
        "total_catalog": catalog_count.scalar() or 0,
        "by_channel": {row[0]: row[1] for row in channel_dist.all()},
        "contact_channels": {row[0]: row[1] for row in contact_channel_dist.all()},
        "latest_crawl_at": latest_crawl_at,
        "today_total_ads": today_total_ads,
    }


@router.get("/stats/daily-trend")
async def daily_trend(
    days: int = Query(default=30, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """N일간 채널별 일일 수집 추이. KST 기준 날짜별 광고 수."""
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    cutoff_kst = now_kst - timedelta(days=days)
    cutoff_utc = cutoff_kst.replace(tzinfo=None) - timedelta(hours=9)

    # SQLite date() 함수로 KST 날짜 추출
    kst_date_expr = func.date(
        AdSnapshot.captured_at, "+9 hours"
    )

    result = await db.execute(
        select(
            kst_date_expr.label("date"),
            AdSnapshot.channel,
            func.count(AdDetail.id).label("ad_count"),
        )
        .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at >= cutoff_utc)
        .group_by(kst_date_expr, AdSnapshot.channel)
        .order_by(kst_date_expr)
    )

    rows = result.all()
    return [
        {"date": row[0], "channel": row[1], "ad_count": row[2]}
        for row in rows
    ]


@router.get("/gallery", dependencies=[Depends(require_plan("full"))])
async def ad_gallery(
    channel: str | None = None,
    advertiser: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    source: str | None = Query(default=None, description="ads | social | None(all)"),
    limit: int = Query(default=60, le=200),
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """creative_image_path가 있는 광고 목록 + 소셜 콘텐츠 (갤러리용)."""
    from database.models import BrandChannelContent, Advertiser as AdvModel

    ad_items = []
    social_items = []

    # ── 광고 소재 ──
    if source != "social":
        query = (
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
                AdDetail.extra_data,
            )
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .order_by(AdSnapshot.captured_at.desc())
        )
        # 검색소재는 이미지 없어도 포함 (문구+광고주 유지), 그 외는 이미지 필수
        if channel and channel in SEARCH_CHANNELS:
            pass  # No image filter for search ads
        elif not channel:
            # 전체 조회: 검색채널 OR 이미지 있는 광고
            query = query.where(
                or_(
                    AdSnapshot.channel.in_(SEARCH_CHANNELS),
                    AdDetail.creative_image_path.isnot(None),
                )
            )
        else:
            query = query.where(AdDetail.creative_image_path.isnot(None))
            query = query.where(AdDetail.creative_image_path != "")

        if channel:
            # Meta 통합: DB에 이미 meta로 저장됨 (facebook/instagram → meta)
            if channel == "meta":
                query = query.where(AdSnapshot.channel == "meta")
            else:
                query = query.where(AdSnapshot.channel == channel)
        if advertiser:
            query = query.where(
                AdDetail.advertiser_name_raw.ilike(f"%{advertiser}%")
            )
        if date_from:
            query = query.where(AdSnapshot.captured_at >= date_from)
        else:
            # 유튜브: 영상 광고만, 기본 최근 30일 한정
            yt_cutoff = datetime.now(timezone(timedelta(hours=9))).replace(tzinfo=None) - timedelta(days=30)
            query = query.where(
                or_(
                    ~AdSnapshot.channel.in_(["youtube_ads", "youtube_surf"]),
                    AdSnapshot.captured_at >= yt_cutoff,
                )
            )
        if date_to:
            query = query.where(AdSnapshot.captured_at <= date_to)

        result = await db.execute(query)
        for row in result.all():
            img_path = row[4]
            # 이미지 파일 존재 검증 -- 깨진 경로 방지
            if img_path and not os.path.exists(img_path):
                img_path = None
            extra = row[9] or {}
            landing = extra.get("landing_analysis") if isinstance(extra, dict) else None
            ch = row[7]
            # 검색소재는 썸네일 제거 (문구+광고주 정보만 유지)
            if ch in SEARCH_CHANNELS:
                img_path = None
            display_ch = normalize_channel_for_display(ch)
            ad_items.append({
                "id": row[0],
                "advertiser_name_raw": row[1],
                "ad_text": row[2],
                "ad_type": row[3],
                "creative_image_path": img_path,
                "url": row[5],
                "brand": row[6],
                "channel": display_ch,
                "channel_raw": ch,
                "captured_at": row[8].isoformat() if row[8] else None,
                "source": "ads",
                "landing_analysis": landing,
            })

    # ── 소셜 콘텐츠 ──
    if source != "ads":
        sq = (
            select(
                BrandChannelContent.id,
                BrandChannelContent.advertiser_id,
                BrandChannelContent.title,
                BrandChannelContent.content_type,
                BrandChannelContent.thumbnail_url,
                BrandChannelContent.extra_data,
                BrandChannelContent.platform,
                BrandChannelContent.discovered_at,
                BrandChannelContent.view_count,
                BrandChannelContent.like_count,
                AdvModel.name,
                AdvModel.brand_name,
                BrandChannelContent.upload_date,
                BrandChannelContent.content_id,
            )
            .join(AdvModel, BrandChannelContent.advertiser_id == AdvModel.id)
            .order_by(BrandChannelContent.discovered_at.desc())
        )

        if channel:
            if channel == "meta":
                sq = sq.where(BrandChannelContent.platform.in_(["meta", "instagram", "facebook"]))
            elif channel in ("youtube", "instagram", "facebook"):
                sq = sq.where(BrandChannelContent.platform == channel)
            else:
                # 소셜 콘텐츠에 해당 없는 채널이면 소셜 쿼리 스킵
                sq = sq.where(BrandChannelContent.platform == "___none___")
        if advertiser:
            sq = sq.where(AdvModel.name.ilike(f"%{advertiser}%"))
        if date_from:
            sq = sq.where(BrandChannelContent.discovered_at >= date_from)
        if date_to:
            sq = sq.where(BrandChannelContent.discovered_at <= date_to)

        result = await db.execute(sq)
        for row in result.all():
            extra = row[5] or {}
            local_path = extra.get("local_image_path")
            # 이미지 파일 존재 검증 -- 깨진 경로 방지
            if local_path and not os.path.exists(local_path):
                local_path = None
            upload_dt = row[12]  # BrandChannelContent.upload_date
            discovered_dt = row[7]  # BrandChannelContent.discovered_at
            # Use upload_date (original publish date) as captured_at; fall back to discovered_at
            display_date = upload_dt or discovered_dt
            platform_raw = row[6]   # BrandChannelContent.platform
            platform_val = normalize_channel_for_display(platform_raw) if platform_raw else platform_raw
            content_id = row[13]    # BrandChannelContent.content_id
            thumb_url = row[4]      # BrandChannelContent.thumbnail_url
            # Construct direct link to the original post
            if platform_raw == "youtube" and content_id:
                content_url = f"https://www.youtube.com/watch?v={content_id}"
            elif platform_raw == "instagram" and content_id:
                content_url = f"https://www.instagram.com/p/{content_id}/"
            else:
                content_url = None
            social_items.append({
                "id": f"social_{row[0]}",
                "advertiser_name_raw": row[10] or "",
                "ad_text": row[2] or "",
                "ad_type": row[3] or "social",
                "creative_image_path": local_path,
                "url": content_url,
                "brand": row[11],
                "channel": platform_val,
                "captured_at": display_date.isoformat() if display_date else None,
                "source": "social",
                "view_count": row[8],
                "like_count": row[9],
                "upload_date": upload_dt.isoformat() if upload_dt else None,
                "thumbnail_url": thumb_url,
            })

    # ── 합치기 ──
    all_items = ad_items + social_items
    all_items.sort(key=lambda x: x.get("captured_at") or "", reverse=True)
    total = len(all_items)
    paged = all_items[offset:offset + limit]

    return {"total": total, "items": paged}
