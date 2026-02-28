"""Spend calibrator -- uses case study benchmarks to calibrate spend estimation.

Flow:
  1. Admin enters known actual ad spend for reference advertisers (large/medium/small)
  2. System compares actual vs estimated spend -> calibration_factor
  3. For similar advertisers (same industry/size/channel), apply averaged calibration
  4. Integrated into campaign_builder as benchmark_calibration layer

Example:
  - Samsung (large, IT): actual=500M/month, estimated=300M -> factor=1.67
  - LG (large, IT): actual=400M/month, estimated=280M -> factor=1.43
  - Average factor for large+IT = 1.55
  - Applied to all large IT advertisers' estimates
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, UTC
from collections import defaultdict

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from database.models import (
    Advertiser, SpendBenchmark, SpendEstimate, Campaign,
    MetaSignalComposite, Industry,
)

logger = logging.getLogger(__name__)

# Size classification thresholds (monthly spend in KRW)
SIZE_THRESHOLDS = {
    "large": 100_000_000,    # 1억+
    "medium": 10_000_000,    # 1천만+
    "small": 0,              # 나머지
}


def classify_advertiser_size(monthly_spend: float) -> str:
    """Classify advertiser by monthly spend level."""
    if monthly_spend >= SIZE_THRESHOLDS["large"]:
        return "large"
    if monthly_spend >= SIZE_THRESHOLDS["medium"]:
        return "medium"
    return "small"


async def compute_calibration_factors(
    session: AsyncSession | None = None,
) -> dict:
    """Compute calibration factors from benchmarks and update them.

    Groups benchmarks by (industry_id, advertiser_size, channel) and
    calculates average calibration_factor for each group.

    Returns: {"updated": N, "groups": N, "factors": {group_key: factor}}
    """
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        # Get all benchmarks
        result = await session.execute(
            select(SpendBenchmark).order_by(SpendBenchmark.created_at.desc())
        )
        benchmarks = result.scalars().all()

        if not benchmarks:
            return {"updated": 0, "groups": 0, "factors": {}}

        # For each benchmark, compute estimated_monthly_spend from SpendEstimate
        updated = 0
        for bm in benchmarks:
            if bm.estimated_monthly_spend is not None and bm.calibration_factor is not None:
                continue

            # Sum estimates for this advertiser in the benchmark period
            est_q = (
                select(func.sum(SpendEstimate.est_daily_spend))
                .join(Campaign, SpendEstimate.campaign_id == Campaign.id)
                .where(
                    and_(
                        Campaign.advertiser_id == bm.advertiser_id,
                        SpendEstimate.date >= bm.period_start,
                        SpendEstimate.date <= bm.period_end,
                    )
                )
            )
            if bm.channel:
                est_q = est_q.where(SpendEstimate.channel == bm.channel)

            total_est = (await session.execute(est_q)).scalar() or 0

            # Convert daily sum to monthly equivalent
            days = max(1, (bm.period_end - bm.period_start).days)
            est_monthly = (total_est / days) * 30

            bm.estimated_monthly_spend = round(est_monthly, 2)
            if est_monthly > 0:
                bm.calibration_factor = round(bm.actual_monthly_spend / est_monthly, 4)
            else:
                bm.calibration_factor = 1.0
            updated += 1

        await session.commit()

        # Group by (industry_id, size, channel) and average
        groups: dict[str, list[float]] = defaultdict(list)
        for bm in benchmarks:
            if bm.calibration_factor is None:
                continue
            key = f"{bm.industry_id or 'all'}:{bm.advertiser_size}:{bm.channel or 'all'}"
            groups[key].append(bm.calibration_factor)

        averaged_factors = {}
        for key, factors in groups.items():
            avg = sum(factors) / len(factors)
            # Clamp to reasonable range
            avg = max(0.3, min(3.0, avg))
            averaged_factors[key] = round(avg, 4)

        logger.info(
            "[calibrator] computed %d groups from %d benchmarks, updated %d",
            len(averaged_factors), len(benchmarks), updated,
        )

        return {
            "updated": updated,
            "groups": len(averaged_factors),
            "factors": averaged_factors,
        }

    finally:
        if own_session:
            await session.close()


async def get_benchmark_calibration(
    session: AsyncSession,
    advertiser_id: int,
    channel: str | None = None,
) -> float:
    """Get the best-matching benchmark calibration factor for an advertiser.

    Lookup priority:
      1. Exact match: same advertiser_id + channel
      2. Industry + size + channel match
      3. Industry + size match (any channel)
      4. Size match only
      5. Default 1.0

    Returns: calibration factor (0.3 ~ 3.0)
    """
    # 1. Direct benchmark for this advertiser
    direct_q = select(SpendBenchmark.calibration_factor).where(
        SpendBenchmark.advertiser_id == advertiser_id,
        SpendBenchmark.calibration_factor.isnot(None),
    )
    if channel:
        direct_q = direct_q.where(SpendBenchmark.channel == channel)
    direct_q = direct_q.order_by(SpendBenchmark.created_at.desc()).limit(1)
    direct = (await session.execute(direct_q)).scalar()
    if direct is not None:
        return max(0.3, min(3.0, direct))

    # 2. Get advertiser info for group matching
    adv = (await session.execute(
        select(Advertiser.industry_id).where(Advertiser.id == advertiser_id)
    )).scalar()

    # Estimate advertiser size from current total spend
    total_spend_q = select(func.sum(SpendEstimate.est_daily_spend)).join(
        Campaign, SpendEstimate.campaign_id == Campaign.id
    ).where(
        Campaign.advertiser_id == advertiser_id,
        SpendEstimate.date >= datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30),
    )
    total_30d = (await session.execute(total_spend_q)).scalar() or 0
    est_monthly = total_30d
    adv_size = classify_advertiser_size(est_monthly)

    # 3. Find matching group benchmarks
    group_q = select(
        func.avg(SpendBenchmark.calibration_factor)
    ).where(
        SpendBenchmark.calibration_factor.isnot(None),
        SpendBenchmark.advertiser_size == adv_size,
    )

    # Try industry + size + channel
    if adv and channel:
        result = (await session.execute(
            group_q.where(
                SpendBenchmark.industry_id == adv,
                SpendBenchmark.channel == channel,
            )
        )).scalar()
        if result is not None:
            return max(0.3, min(3.0, round(result, 4)))

    # Try industry + size
    if adv:
        result = (await session.execute(
            group_q.where(SpendBenchmark.industry_id == adv)
        )).scalar()
        if result is not None:
            return max(0.3, min(3.0, round(result, 4)))

    # Try size only
    result = (await session.execute(group_q)).scalar()
    if result is not None:
        return max(0.3, min(3.0, round(result, 4)))

    return 1.0


async def list_benchmarks(session: AsyncSession | None = None) -> list[dict]:
    """List all benchmarks with advertiser info."""
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        result = await session.execute(
            select(SpendBenchmark, Advertiser.name)
            .join(Advertiser, SpendBenchmark.advertiser_id == Advertiser.id)
            .order_by(SpendBenchmark.created_at.desc())
        )
        rows = result.all()
        return [
            {
                "id": bm.id,
                "advertiser_id": bm.advertiser_id,
                "advertiser_name": name,
                "channel": bm.channel,
                "period_start": bm.period_start.isoformat() if bm.period_start else None,
                "period_end": bm.period_end.isoformat() if bm.period_end else None,
                "actual_monthly_spend": bm.actual_monthly_spend,
                "estimated_monthly_spend": bm.estimated_monthly_spend,
                "calibration_factor": bm.calibration_factor,
                "advertiser_size": bm.advertiser_size,
                "source": bm.source,
                "notes": bm.notes,
            }
            for bm, name in rows
        ]
    finally:
        if own_session:
            await session.close()
