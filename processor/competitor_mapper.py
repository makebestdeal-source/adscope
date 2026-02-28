"""Competitor auto-mapping: affinity scoring engine + industry landscape.

Computes multi-dimensional similarity between advertisers based on:
  1. Keyword overlap (Jaccard)
  2. Channel overlap (Jaccard)
  3. Position zone similarity (cosine-like)
  4. Spend similarity (1 - normalised difference)
  5. Co-occurrence count (same snapshot appearances)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import func, select, and_, distinct, case, Float, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AdDetail,
    AdSnapshot,
    Advertiser,
    Campaign,
    Industry,
    Keyword,
    SpendEstimate,
)


# ── Data classes ──


@dataclass
class CompetitorScore:
    competitor_id: int
    competitor_name: str
    industry_id: int | None
    affinity_score: float
    keyword_overlap: float
    channel_overlap: float
    position_zone_overlap: float
    spend_similarity: float
    co_occurrence_count: int


@dataclass
class IndustryAdvertiserInfo:
    id: int
    name: str
    brand_name: str | None
    annual_revenue: float | None
    employee_count: int | None
    is_public: bool
    est_ad_spend: float
    sov_percentage: float
    channel_count: int
    channel_mix: list[str] = field(default_factory=list)
    ad_count: int = 0


@dataclass
class IndustryLandscape:
    industry_id: int
    industry_name: str
    total_market_size: float | None
    advertiser_count: int
    advertisers: list[IndustryAdvertiserInfo] = field(default_factory=list)
    revenue_ranking: list[IndustryAdvertiserInfo] = field(default_factory=list)
    spend_ranking: list[IndustryAdvertiserInfo] = field(default_factory=list)


# ── Helper functions ──


def _jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two sets, returned as 0-100 scale."""
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union) * 100.0


def _spend_similarity(spend_a: float, spend_b: float) -> float:
    """Spend similarity: 100 * (1 - |a-b| / max(a,b)).  Returns 0-100."""
    if spend_a <= 0 and spend_b <= 0:
        return 100.0
    max_val = max(spend_a, spend_b)
    if max_val == 0:
        return 100.0
    return max(0.0, (1.0 - abs(spend_a - spend_b) / max_val) * 100.0)


def _position_similarity(dist_a: dict[str, int], dist_b: dict[str, int]) -> float:
    """Cosine-like similarity on position zone distributions (0-100)."""
    all_zones = set(dist_a.keys()) | set(dist_b.keys())
    if not all_zones:
        return 0.0
    dot = sum(dist_a.get(z, 0) * dist_b.get(z, 0) for z in all_zones)
    mag_a = sum(v ** 2 for v in dist_a.values()) ** 0.5
    mag_b = sum(v ** 2 for v in dist_b.values()) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return (dot / (mag_a * mag_b)) * 100.0


# ── Main scoring function ──


async def calculate_competitor_affinity(
    db: AsyncSession,
    advertiser_id: int,
    days: int = 30,
    limit: int = 20,
) -> list[CompetitorScore]:
    """Calculate competitor affinity scores for a given advertiser.

    Steps:
      1. Find target advertiser and industry_id
      2. Gather candidates: same industry + keyword co-occurrence
      3. Batch-query 5 dimensions per candidate
      4. Composite score = keyword*0.30 + channel*0.20 + position*0.15
                         + spend*0.20 + co_occurrence*0.15
      5. Sort descending, return top N
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Step 1: Target advertiser
    target = await db.get(Advertiser, advertiser_id)
    if not target:
        return []

    # -- Target's keywords --
    target_kw_q = (
        select(distinct(AdSnapshot.keyword_id))
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id == advertiser_id)
        .where(AdSnapshot.captured_at >= since)
    )
    target_kw_result = await db.execute(target_kw_q)
    target_keyword_ids: set[int] = {r[0] for r in target_kw_result.all() if r[0] is not None}

    # -- Target's channels --
    target_ch_q = (
        select(distinct(AdSnapshot.channel))
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id == advertiser_id)
        .where(AdSnapshot.captured_at >= since)
    )
    target_ch_result = await db.execute(target_ch_q)
    target_channels: set[str] = {r[0] for r in target_ch_result.all() if r[0]}

    # -- Target's position zone distribution --
    target_pos_q = (
        select(
            AdDetail.position_zone,
            func.count(AdDetail.id).label("cnt"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id == advertiser_id)
        .where(AdSnapshot.captured_at >= since)
        .where(AdDetail.position_zone.isnot(None))
        .group_by(AdDetail.position_zone)
    )
    target_pos_result = await db.execute(target_pos_q)
    target_position_dist: dict[str, int] = {
        r.position_zone: r.cnt for r in target_pos_result.all() if r.position_zone
    }

    # -- Target's total spend --
    target_spend_q = (
        select(func.coalesce(func.sum(SpendEstimate.est_daily_spend), 0.0))
        .select_from(SpendEstimate)
        .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
        .where(Campaign.advertiser_id == advertiser_id)
        .where(SpendEstimate.date >= since)
    )
    target_spend_result = await db.execute(target_spend_q)
    target_spend: float = float(target_spend_result.scalar() or 0.0)

    # Step 2: Gather candidate competitors
    candidate_ids: set[int] = set()

    # 2a: Same industry
    if target.industry_id:
        industry_q = (
            select(Advertiser.id)
            .where(Advertiser.industry_id == target.industry_id)
            .where(Advertiser.id != advertiser_id)
        )
        industry_result = await db.execute(industry_q)
        candidate_ids.update(r[0] for r in industry_result.all())

    # 2b: Keyword co-occurrence (advertisers appearing on same keywords)
    if target_keyword_ids:
        cooccur_q = (
            select(distinct(AdDetail.advertiser_id))
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdSnapshot.keyword_id.in_(target_keyword_ids))
            .where(AdDetail.advertiser_id.isnot(None))
            .where(AdDetail.advertiser_id != advertiser_id)
            .where(AdSnapshot.captured_at >= since)
        )
        cooccur_result = await db.execute(cooccur_q)
        candidate_ids.update(r[0] for r in cooccur_result.all())

    if not candidate_ids:
        return []

    # Step 3: For each candidate, compute 5 dimensions
    scores: list[CompetitorScore] = []

    # Batch query: candidate keywords
    cand_kw_q = (
        select(
            AdDetail.advertiser_id,
            AdSnapshot.keyword_id,
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(candidate_ids))
        .where(AdSnapshot.captured_at >= since)
        .where(AdSnapshot.keyword_id.isnot(None))
    )
    cand_kw_result = await db.execute(cand_kw_q)
    cand_keywords: dict[int, set[int]] = {}
    for r in cand_kw_result.all():
        cand_keywords.setdefault(r[0], set()).add(r[1])

    # Batch query: candidate channels
    cand_ch_q = (
        select(
            AdDetail.advertiser_id,
            AdSnapshot.channel,
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(candidate_ids))
        .where(AdSnapshot.captured_at >= since)
    )
    cand_ch_result = await db.execute(cand_ch_q)
    cand_channels: dict[int, set[str]] = {}
    for r in cand_ch_result.all():
        if r[1]:
            cand_channels.setdefault(r[0], set()).add(r[1])

    # Batch query: candidate position zones
    cand_pos_q = (
        select(
            AdDetail.advertiser_id,
            AdDetail.position_zone,
            func.count(AdDetail.id).label("cnt"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(candidate_ids))
        .where(AdSnapshot.captured_at >= since)
        .where(AdDetail.position_zone.isnot(None))
        .group_by(AdDetail.advertiser_id, AdDetail.position_zone)
    )
    cand_pos_result = await db.execute(cand_pos_q)
    cand_position_dist: dict[int, dict[str, int]] = {}
    for r in cand_pos_result.all():
        if r.position_zone:
            cand_position_dist.setdefault(r.advertiser_id, {})[r.position_zone] = r.cnt

    # Batch query: candidate spend
    cand_spend_q = (
        select(
            Campaign.advertiser_id,
            func.coalesce(func.sum(SpendEstimate.est_daily_spend), 0.0).label("total"),
        )
        .select_from(SpendEstimate)
        .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
        .where(Campaign.advertiser_id.in_(candidate_ids))
        .where(SpendEstimate.date >= since)
        .group_by(Campaign.advertiser_id)
    )
    cand_spend_result = await db.execute(cand_spend_q)
    cand_spend: dict[int, float] = {r.advertiser_id: float(r.total) for r in cand_spend_result.all()}

    # Batch query: co-occurrence count (same snapshot_id appearances)
    if target_keyword_ids:
        # Count snapshots where both target and candidate have ads
        target_snapshot_q = (
            select(distinct(AdDetail.snapshot_id))
            .where(AdDetail.advertiser_id == advertiser_id)
        )
        cooccur_count_q = (
            select(
                AdDetail.advertiser_id,
                func.count(distinct(AdDetail.snapshot_id)).label("cnt"),
            )
            .where(AdDetail.advertiser_id.in_(candidate_ids))
            .where(AdDetail.snapshot_id.in_(target_snapshot_q))
            .group_by(AdDetail.advertiser_id)
        )
        cooccur_count_result = await db.execute(cooccur_count_q)
        cooccur_counts: dict[int, int] = {r.advertiser_id: r.cnt for r in cooccur_count_result.all()}
    else:
        cooccur_counts = {}

    # Find max co-occurrence for normalisation
    max_cooccur = max(cooccur_counts.values()) if cooccur_counts else 1

    # Load candidate advertiser info
    cand_adv_q = (
        select(Advertiser)
        .where(Advertiser.id.in_(candidate_ids))
    )
    cand_adv_result = await db.execute(cand_adv_q)
    cand_advertisers: dict[int, Advertiser] = {
        a.id: a for a in cand_adv_result.scalars().all()
    }

    # Step 4: Compute composite score per candidate
    for cid in candidate_ids:
        adv_obj = cand_advertisers.get(cid)
        if not adv_obj:
            continue

        kw_sim = _jaccard(target_keyword_ids, cand_keywords.get(cid, set()))
        ch_sim = _jaccard(target_channels, cand_channels.get(cid, set()))
        pos_sim = _position_similarity(target_position_dist, cand_position_dist.get(cid, {}))
        sp_sim = _spend_similarity(target_spend, cand_spend.get(cid, 0.0))
        cooccur_raw = cooccur_counts.get(cid, 0)
        cooccur_norm = (cooccur_raw / max(max_cooccur, 1)) * 100.0

        affinity = (
            kw_sim * 0.30
            + ch_sim * 0.20
            + pos_sim * 0.15
            + sp_sim * 0.20
            + cooccur_norm * 0.15
        )

        scores.append(
            CompetitorScore(
                competitor_id=cid,
                competitor_name=adv_obj.name,
                industry_id=adv_obj.industry_id,
                affinity_score=round(affinity, 2),
                keyword_overlap=round(kw_sim, 2),
                channel_overlap=round(ch_sim, 2),
                position_zone_overlap=round(pos_sim, 2),
                spend_similarity=round(sp_sim, 2),
                co_occurrence_count=cooccur_raw,
            )
        )

    # Step 5: Sort and limit
    scores.sort(key=lambda s: s.affinity_score, reverse=True)
    return scores[:limit]


# ── Industry landscape ──


async def calculate_industry_landscape(
    db: AsyncSession,
    industry_id: int,
    days: int = 30,
) -> IndustryLandscape | None:
    """Build an industry landscape view.

    For each advertiser in the industry:
      - SOV (share of voice)
      - Total estimated spend
      - Active channels
      - Ad count
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Get industry info
    industry = await db.get(Industry, industry_id)
    if not industry:
        return None

    # Get all advertisers in industry
    adv_q = select(Advertiser).where(Advertiser.industry_id == industry_id)
    adv_result = await db.execute(adv_q)
    advertisers_list: Sequence[Advertiser] = adv_result.scalars().all()

    if not advertisers_list:
        return IndustryLandscape(
            industry_id=industry_id,
            industry_name=industry.name,
            total_market_size=None,
            advertiser_count=0,
        )

    adv_ids = [a.id for a in advertisers_list]

    # Total market ad count for SOV
    total_market_q = (
        select(func.count(AdDetail.id))
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(adv_ids))
        .where(AdSnapshot.captured_at >= since)
    )
    total_market_result = await db.execute(total_market_q)
    total_market: int = total_market_result.scalar() or 0

    # Per-advertiser ad count
    per_adv_q = (
        select(
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("ad_count"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(adv_ids))
        .where(AdSnapshot.captured_at >= since)
        .group_by(AdDetail.advertiser_id)
    )
    per_adv_result = await db.execute(per_adv_q)
    ad_counts: dict[int, int] = {r.advertiser_id: r.ad_count for r in per_adv_result.all()}

    # Per-advertiser channels
    per_ch_q = (
        select(
            AdDetail.advertiser_id,
            AdSnapshot.channel,
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(adv_ids))
        .where(AdSnapshot.captured_at >= since)
        .distinct()
    )
    per_ch_result = await db.execute(per_ch_q)
    adv_channels: dict[int, list[str]] = {}
    for r in per_ch_result.all():
        if r[1]:
            adv_channels.setdefault(r[0], [])
            if r[1] not in adv_channels[r[0]]:
                adv_channels[r[0]].append(r[1])

    # Per-advertiser spend
    per_spend_q = (
        select(
            Campaign.advertiser_id,
            func.coalesce(func.sum(SpendEstimate.est_daily_spend), 0.0).label("total"),
        )
        .select_from(SpendEstimate)
        .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
        .where(Campaign.advertiser_id.in_(adv_ids))
        .where(SpendEstimate.date >= since)
        .group_by(Campaign.advertiser_id)
    )
    per_spend_result = await db.execute(per_spend_q)
    adv_spend: dict[int, float] = {r.advertiser_id: float(r.total) for r in per_spend_result.all()}

    total_market_spend = sum(adv_spend.values()) if adv_spend else None

    # Build advertiser info list
    infos: list[IndustryAdvertiserInfo] = []
    for adv in advertisers_list:
        count = ad_counts.get(adv.id, 0)
        sov = round(count / max(total_market, 1) * 100, 2) if total_market > 0 else 0.0
        channels = adv_channels.get(adv.id, [])
        spend = adv_spend.get(adv.id, 0.0)

        infos.append(
            IndustryAdvertiserInfo(
                id=adv.id,
                name=adv.name,
                brand_name=adv.brand_name,
                annual_revenue=adv.annual_revenue,
                employee_count=adv.employee_count,
                is_public=adv.is_public or False,
                est_ad_spend=round(spend, 2),
                sov_percentage=sov,
                channel_count=len(channels),
                channel_mix=channels,
                ad_count=count,
            )
        )

    # Sort by SOV descending (primary view)
    infos.sort(key=lambda x: x.sov_percentage, reverse=True)

    # Revenue ranking
    revenue_ranked = sorted(
        [i for i in infos if i.annual_revenue],
        key=lambda x: x.annual_revenue or 0,
        reverse=True,
    )

    # Spend ranking
    spend_ranked = sorted(
        infos,
        key=lambda x: x.est_ad_spend,
        reverse=True,
    )

    return IndustryLandscape(
        industry_id=industry_id,
        industry_name=industry.name,
        total_market_size=total_market_spend,
        advertiser_count=len(infos),
        advertisers=infos,
        revenue_ranking=revenue_ranked,
        spend_ranking=spend_ranked,
    )
