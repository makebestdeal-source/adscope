"""Competitor auto-mapping API router.

Provides:
  GET /api/competitors/{advertiser_id}          - affinity scores
  GET /api/competitors/{advertiser_id}/keywords - keyword reverse lookup
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import AdDetail, AdSnapshot, Advertiser, Industry, Keyword
from database.schemas import (
    CompetitorListOut,
    CompetitorScoreOut,
)
from processor.competitor_mapper import calculate_competitor_affinity

router = APIRouter(prefix="/api/competitors", tags=["competitors"],
    dependencies=[Depends(get_current_user)])


@router.get("/{advertiser_id}", response_model=CompetitorListOut)
async def get_competitors(
    advertiser_id: int,
    days: int = Query(default=30, le=365),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return competitor affinity scores for a given advertiser.

    Ranks candidates by composite affinity across keyword overlap,
    channel overlap, position zone similarity, spend similarity,
    and co-occurrence count.
    """
    target = await db.get(Advertiser, advertiser_id)
    if not target:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    scores = await calculate_competitor_affinity(
        db, advertiser_id=advertiser_id, days=days, limit=limit
    )

    industry_name: str | None = None
    if target.industry_id:
        industry = await db.get(Industry, target.industry_id)
        industry_name = industry.name if industry else None

    return CompetitorListOut(
        target_id=target.id,
        target_name=target.name,
        industry_id=target.industry_id,
        industry_name=industry_name,
        competitors=[
            CompetitorScoreOut(
                competitor_id=s.competitor_id,
                competitor_name=s.competitor_name,
                industry_id=s.industry_id,
                affinity_score=s.affinity_score,
                keyword_overlap=s.keyword_overlap,
                channel_overlap=s.channel_overlap,
                position_zone_overlap=s.position_zone_overlap,
                spend_similarity=s.spend_similarity,
                co_occurrence_count=s.co_occurrence_count,
            )
            for s in scores
        ],
    )


@router.get("/{advertiser_id}/keywords")
async def get_advertiser_keywords(
    advertiser_id: int,
    days: int = Query(default=30, le=365),
    channel: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """광고주의 키워드 역추적 — 어떤 키워드에 광고가 노출되었는지 반환."""
    target = await db.get(Advertiser, advertiser_id)
    if not target:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    cutoff = datetime.utcnow() - timedelta(days=days)

    q = (
        select(
            Keyword.id.label("keyword_id"),
            Keyword.keyword,
            Keyword.monthly_search_vol,
            Keyword.naver_cpc,
            AdSnapshot.channel,
            func.count(AdDetail.id).label("impression_count"),
            func.min(AdSnapshot.captured_at).label("first_seen"),
            func.max(AdSnapshot.captured_at).label("last_seen"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
        .where(AdDetail.advertiser_id == advertiser_id)
        .where(AdSnapshot.captured_at >= cutoff)
    )
    if channel:
        q = q.where(AdSnapshot.channel == channel)

    q = (
        q.group_by(Keyword.id, Keyword.keyword, AdSnapshot.channel)
        .order_by(func.count(AdDetail.id).desc())
        .limit(limit)
    )

    rows = (await db.execute(q)).all()

    # 키워드별로 채널 합치기
    kw_map: dict[int, dict] = {}
    for r in rows:
        kid = r.keyword_id
        if kid not in kw_map:
            kw_map[kid] = {
                "keyword_id": kid,
                "keyword": r.keyword,
                "monthly_search_vol": r.monthly_search_vol,
                "naver_cpc": r.naver_cpc,
                "channels": [],
                "impression_count": 0,
                "first_seen": r.first_seen.strftime("%Y-%m-%d") if r.first_seen else None,
                "last_seen": r.last_seen.strftime("%Y-%m-%d") if r.last_seen else None,
            }
        kw_map[kid]["channels"].append(r.channel)
        kw_map[kid]["impression_count"] += r.impression_count
        # 날짜 갱신
        if r.first_seen:
            fs = r.first_seen.strftime("%Y-%m-%d")
            if not kw_map[kid]["first_seen"] or fs < kw_map[kid]["first_seen"]:
                kw_map[kid]["first_seen"] = fs
        if r.last_seen:
            ls = r.last_seen.strftime("%Y-%m-%d")
            if not kw_map[kid]["last_seen"] or ls > kw_map[kid]["last_seen"]:
                kw_map[kid]["last_seen"] = ls

    keywords = sorted(kw_map.values(), key=lambda x: -x["impression_count"])

    return {
        "advertiser_id": advertiser_id,
        "advertiser_name": target.name,
        "keywords": keywords,
    }
