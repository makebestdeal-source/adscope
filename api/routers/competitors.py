"""Competitor auto-mapping API router.

Provides:
  GET /api/competitors/{advertiser_id}          - affinity scores
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import Advertiser, Industry
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
