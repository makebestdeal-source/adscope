"""Launch Impact Scorer -- compute MRS / RV / CS / LII daily scores.

Metrics:
  MRS (Media Reach Score): weighted mention count by media type (0-100)
  RV (Reaction Velocity): mention growth slope since launch (0-100)
  CS (Conversion Signal): search/wishlist/review conversion (0-100)
  LII (Launch Impact Index): geometric mean of MRS * RV * CS (0-100)

Category weight presets: game / commerce / product
"""

from __future__ import annotations

import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select

from database import async_session
from database.models import (
    Advertiser,
    LaunchImpactScore,
    LaunchMention,
    LaunchProduct,
    SmartStoreSnapshot,
    TrafficSignal,
)

logger = logging.getLogger(__name__)

# ── Category weight presets ──

CATEGORY_WEIGHTS = {
    "game": {
        "mrs": {"news": 0.15, "blog": 0.15, "community": 0.25, "youtube": 0.30, "sns": 0.10, "review": 0.05},
        "cs": {"search": 0.30, "wishlist": 0.20, "review": 0.50},
    },
    "commerce": {
        "mrs": {"news": 0.10, "blog": 0.15, "community": 0.05, "youtube": 0.10, "sns": 0.10, "review": 0.50},
        "cs": {"search": 0.40, "wishlist": 0.35, "review": 0.25},
    },
    "product": {
        "mrs": {"news": 0.35, "blog": 0.25, "community": 0.10, "youtube": 0.15, "sns": 0.10, "review": 0.05},
        "cs": {"search": 0.40, "wishlist": 0.30, "review": 0.30},
    },
}

# Normalization caps per source type
MRS_CAPS = {"news": 30, "blog": 50, "community": 100, "youtube": 20, "sns": 50, "review": 100}

# RV expected slopes per category (mentions/day)
RV_EXPECTED_SLOPE = {"game": 10, "commerce": 5, "product": 3}
RV_DAY0_CAP = {"game": 50, "commerce": 30, "product": 20}

# CS caps
CS_WISHLIST_CAP = {"game": 1000, "commerce": 500, "product": 200}
CS_REVIEW_CAP = {"game": 100, "commerce": 50, "product": 20}


def _normalize(value: float, cap: float) -> float:
    """Normalize value to 0-100 scale."""
    if cap <= 0:
        return 0.0
    return min(100.0, (value / cap) * 100.0)


def _calc_mrs(mention_counts: dict[str, int], category: str) -> float:
    """Calculate Media Reach Score."""
    weights = CATEGORY_WEIGHTS.get(category, CATEGORY_WEIGHTS["product"])["mrs"]
    total = 0.0
    for source_type, count in mention_counts.items():
        cap = MRS_CAPS.get(source_type, 50)
        normalized = _normalize(count, cap)
        weight = weights.get(source_type, 0.05)
        total += normalized * weight
    return round(min(100.0, total), 1)


def _calc_rv(
    daily_mention_counts: list[int],
    days_since_launch: int,
    category: str,
    search_delta_pct: float | None,
) -> float:
    """Calculate Reaction Velocity."""
    if days_since_launch < 0:
        # Pre-launch: score based on hype mentions
        total = sum(daily_mention_counts) if daily_mention_counts else 0
        return round(_normalize(total, RV_DAY0_CAP.get(category, 30) * 0.5), 1)

    if days_since_launch == 0:
        day0 = daily_mention_counts[-1] if daily_mention_counts else 0
        rv = _normalize(day0, RV_DAY0_CAP.get(category, 30))
    elif len(daily_mention_counts) >= 2:
        # Simple slope: (latest - first) / days
        slope = (daily_mention_counts[-1] - daily_mention_counts[0]) / max(1, len(daily_mention_counts) - 1)
        # If negative slope, still count absolute volume
        if slope < 0:
            avg_volume = sum(daily_mention_counts) / len(daily_mention_counts)
            rv = _normalize(avg_volume, RV_EXPECTED_SLOPE.get(category, 5) * 2)
        else:
            rv = _normalize(slope, RV_EXPECTED_SLOPE.get(category, 5))
    else:
        rv = 0.0

    # Search trend acceleration bonus
    if search_delta_pct is not None and search_delta_pct > 50:
        rv = min(100.0, rv + 10)

    return round(min(100.0, rv), 1)


def _calc_cs(
    search_index: float | None,
    search_baseline: float | None,
    wishlist_count: int | None,
    review_delta: int,
    category: str,
) -> float:
    """Calculate Conversion Signal."""
    weights = CATEGORY_WEIGHTS.get(category, CATEGORY_WEIGHTS["product"])["cs"]

    # Search signal
    if search_index and search_baseline and search_baseline > 0:
        search_signal = _normalize(search_index, search_baseline * 2)
    elif search_index:
        search_signal = min(100.0, search_index)
    else:
        search_signal = 0.0

    # Wishlist signal
    wishlist_cap = CS_WISHLIST_CAP.get(category, 500)
    wishlist_signal = _normalize(wishlist_count or 0, wishlist_cap)

    # Review signal
    review_cap = CS_REVIEW_CAP.get(category, 50)
    review_signal = _normalize(max(0, review_delta), review_cap)

    cs = (
        search_signal * weights["search"]
        + wishlist_signal * weights["wishlist"]
        + review_signal * weights["review"]
    )
    return round(min(100.0, cs), 1)


def _calc_lii(mrs: float, rv: float, cs: float) -> float:
    """Calculate Launch Impact Index as geometric mean with floor of 1."""
    return round(min(100.0, (max(1.0, mrs) * max(1.0, rv) * max(1.0, cs)) ** (1 / 3)), 1)


def _determine_phase(days_since_launch: int, lii: float, prev_lii: float | None) -> str:
    """Determine impact phase."""
    if days_since_launch < 0:
        return "pre_launch"
    if days_since_launch <= 7:
        return "launch_week"
    if prev_lii is not None and lii > prev_lii + 2:
        return "growth"
    if prev_lii is not None and abs(lii - prev_lii) <= 3:
        return "plateau"
    return "decline"


async def calculate_launch_impact_scores(
    session=None,
    product_ids: list[int] | None = None,
    days: int = 30,
) -> dict:
    """Calculate MRS/RV/CS/LII for all active launch products.

    Returns: {"processed": N, "created": N, "updated": N}
    """
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        today_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = now - timedelta(days=days)

        # Get active products
        query = select(LaunchProduct).where(LaunchProduct.is_active == True)  # noqa: E712
        if product_ids:
            query = query.where(LaunchProduct.id.in_(product_ids))
        result = await session.execute(query)
        products = result.scalars().all()

        if not products:
            return {"processed": 0, "created": 0, "updated": 0}

        created = 0
        updated = 0

        for product in products:
            launch_dt = product.launch_date
            if launch_dt.tzinfo:
                launch_dt = launch_dt.replace(tzinfo=None)
            days_since_launch = (today_dt - launch_dt).days

            # ── Mention counts by type ──
            mention_q = await session.execute(
                select(
                    LaunchMention.source_type,
                    func.count(LaunchMention.id),
                ).where(
                    and_(
                        LaunchMention.launch_product_id == product.id,
                        LaunchMention.collected_at >= cutoff,
                    )
                ).group_by(LaunchMention.source_type)
            )
            mention_counts = {row[0]: row[1] for row in mention_q.fetchall()}
            total_mentions = sum(mention_counts.values())

            # ── Daily mention series (for RV) ──
            daily_q = await session.execute(
                select(
                    func.date(LaunchMention.published_at),
                    func.count(LaunchMention.id),
                ).where(
                    and_(
                        LaunchMention.launch_product_id == product.id,
                        LaunchMention.published_at.isnot(None),
                        LaunchMention.published_at >= cutoff,
                    )
                ).group_by(func.date(LaunchMention.published_at))
                .order_by(func.date(LaunchMention.published_at).asc())
            )
            daily_counts = [row[1] for row in daily_q.fetchall()]

            # ── Search / traffic data ──
            search_index = None
            search_delta_pct = None
            search_baseline = None

            traffic_q = await session.execute(
                select(TrafficSignal).where(
                    and_(
                        TrafficSignal.advertiser_id == product.advertiser_id,
                        TrafficSignal.date >= cutoff,
                    )
                ).order_by(TrafficSignal.date.desc()).limit(1)
            )
            latest_traffic = traffic_q.scalar_one_or_none()
            if latest_traffic:
                search_index = latest_traffic.naver_search_index or latest_traffic.composite_index
                search_delta_pct = latest_traffic.wow_change_pct

                # Baseline: avg traffic before launch
                baseline_q = await session.execute(
                    select(func.avg(TrafficSignal.naver_search_index)).where(
                        and_(
                            TrafficSignal.advertiser_id == product.advertiser_id,
                            TrafficSignal.date < launch_dt,
                            TrafficSignal.date >= launch_dt - timedelta(days=7),
                        )
                    )
                )
                search_baseline = baseline_q.scalar_one()

            # ── Commerce signals (wishlist/review) ──
            wishlist_count = None
            review_count = None
            review_delta = 0

            if product.category == "commerce" and product.product_url:
                ss_q = await session.execute(
                    select(SmartStoreSnapshot).where(
                        and_(
                            SmartStoreSnapshot.product_url == product.product_url,
                            SmartStoreSnapshot.captured_at >= cutoff,
                        )
                    ).order_by(SmartStoreSnapshot.captured_at.desc()).limit(1)
                )
                latest_ss = ss_q.scalar_one_or_none()
                if latest_ss:
                    wishlist_count = latest_ss.wishlist_count
                    review_count = latest_ss.review_count
                    review_delta = latest_ss.review_delta or 0

            # ── Calculate scores ──
            mrs = _calc_mrs(mention_counts, product.category)
            rv = _calc_rv(daily_counts, days_since_launch, product.category, search_delta_pct)
            cs = _calc_cs(search_index, search_baseline, wishlist_count, review_delta, product.category)
            lii = _calc_lii(mrs, rv, cs)

            # Previous day's score for phase detection
            prev_q = await session.execute(
                select(LaunchImpactScore.lii_score).where(
                    and_(
                        LaunchImpactScore.launch_product_id == product.id,
                        LaunchImpactScore.date < today_dt,
                    )
                ).order_by(LaunchImpactScore.date.desc()).limit(1)
            )
            prev_lii = prev_q.scalar_one_or_none()
            phase = _determine_phase(days_since_launch, lii, prev_lii)

            factors = {
                "mention_counts": mention_counts,
                "daily_mention_counts": daily_counts,
                "search_index": search_index,
                "search_baseline": search_baseline,
                "search_delta_pct": search_delta_pct,
                "wishlist_count": wishlist_count,
                "review_count": review_count,
                "review_delta": review_delta,
                "sub_scores": {"mrs": mrs, "rv": rv, "cs": cs},
                "category_weights": product.category,
            }

            # ── Upsert ──
            existing = (
                await session.execute(
                    select(LaunchImpactScore).where(
                        and_(
                            LaunchImpactScore.launch_product_id == product.id,
                            LaunchImpactScore.date == today_dt,
                        )
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.mrs_score = mrs
                existing.rv_score = rv
                existing.cs_score = cs
                existing.lii_score = lii
                existing.total_mentions = total_mentions
                existing.mention_by_type = mention_counts
                existing.search_index = search_index
                existing.search_delta_pct = search_delta_pct
                existing.wishlist_count = wishlist_count
                existing.review_count = review_count
                existing.review_delta = review_delta
                existing.days_since_launch = days_since_launch
                existing.impact_phase = phase
                existing.factors = factors
                updated += 1
            else:
                session.add(LaunchImpactScore(
                    launch_product_id=product.id,
                    date=today_dt,
                    mrs_score=mrs,
                    rv_score=rv,
                    cs_score=cs,
                    lii_score=lii,
                    total_mentions=total_mentions,
                    mention_by_type=mention_counts,
                    search_index=search_index,
                    search_delta_pct=search_delta_pct,
                    wishlist_count=wishlist_count,
                    review_count=review_count,
                    review_delta=review_delta,
                    days_since_launch=days_since_launch,
                    impact_phase=phase,
                    factors=factors,
                ))
                created += 1

        await session.commit()
        logger.info(
            "[launch_impact] processed=%d created=%d updated=%d",
            len(products), created, updated,
        )
        return {"processed": len(products), "created": created, "updated": updated}

    except Exception:
        logger.exception("[launch_impact] calculate_launch_impact_scores failed")
        await session.rollback()
        raise
    finally:
        if own_session:
            await session.close()
