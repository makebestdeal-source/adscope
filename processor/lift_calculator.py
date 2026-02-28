"""Campaign lift calculator -- compute Pre/Post lift from journey_events.

For each campaign with a start_at date, computes:
  - Query Lift:  search signal change (interest/search)
  - Social Lift: social engagement change (interest/social)
  - Sales Lift:  conversion signal change (conversion/smartstore)

Confidence = proportion of signals that have data in both pre and post windows.
Results are upserted into the campaign_lifts table (unique per campaign_id).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select

from database import async_session
from database.models import Campaign, CampaignLift, JourneyEvent

logger = logging.getLogger(__name__)


async def _avg_value_in_window(
    session,
    campaign_id: int,
    stage: str,
    source: str,
    window_start: datetime,
    window_end: datetime,
    *,
    advertiser_id: int | None = None,
) -> tuple[float | None, int]:
    """Return (average value, row count) for a journey_events slice.

    If advertiser_id is provided, also searches events linked to
    the same advertiser (interest/social events are advertiser-level).
    Returns (None, 0) when no matching rows exist.
    """
    # Try campaign-level first
    result = (
        await session.execute(
            select(
                func.avg(JourneyEvent.value),
                func.count(JourneyEvent.id),
            ).where(
                and_(
                    JourneyEvent.campaign_id == campaign_id,
                    JourneyEvent.stage == stage,
                    JourneyEvent.source == source,
                    JourneyEvent.ts >= window_start,
                    JourneyEvent.ts < window_end,
                )
            )
        )
    ).one()
    avg_val, cnt = result
    if avg_val is not None and cnt > 0:
        return float(avg_val), int(cnt)

    # Fallback: search by advertiser_id (interest/social are shared)
    if advertiser_id and stage in ("interest", "consideration", "conversion"):
        result2 = (
            await session.execute(
                select(
                    func.avg(JourneyEvent.value),
                    func.count(JourneyEvent.id),
                ).where(
                    and_(
                        JourneyEvent.advertiser_id == advertiser_id,
                        JourneyEvent.stage == stage,
                        JourneyEvent.source == source,
                        JourneyEvent.ts >= window_start,
                        JourneyEvent.ts < window_end,
                    )
                )
            )
        ).one()
        avg_val2, cnt2 = result2
        if avg_val2 is not None and cnt2 > 0:
            return float(avg_val2), int(cnt2)

    return None, 0


def _compute_lift(
    pre_avg: float | None,
    post_avg: float | None,
    epsilon: float,
) -> float | None:
    """Percentage lift: (post - pre) / max(pre, epsilon).

    Returns None if either side has no data.
    """
    if pre_avg is None or post_avg is None:
        return None
    denominator = max(pre_avg, epsilon)
    return round((post_avg - pre_avg) / denominator * 100, 2)


async def calculate_campaign_lifts(
    campaign_ids: list[int] | None = None,
    pre_days: int = 7,
    post_days: int = 7,
    epsilon: float = 0.01,
) -> dict:
    """Calculate Query/Social/Sales lift per campaign.

    Args:
        campaign_ids: Specific campaigns. None = all with start_at set.
        pre_days: Days before campaign start for the pre-window.
        post_days: Days after campaign start (or end) for the post-window.
        epsilon: Floor divisor to avoid division by zero.

    Returns:
        {"processed": N, "created": N, "updated": N, "skipped": N}
    """
    async with async_session() as session:
        # Fetch campaigns with start_at
        camp_q = select(Campaign).where(Campaign.start_at.is_not(None))
        if campaign_ids:
            camp_q = camp_q.where(Campaign.id.in_(campaign_ids))
        campaigns = (await session.execute(camp_q)).scalars().all()

        if not campaigns:
            logger.info("[lift_calculator] no campaigns with start_at found")
            return {"processed": 0, "created": 0, "updated": 0, "skipped": 0}

        created = 0
        updated = 0
        skipped = 0

        for camp in campaigns:
            adv_id = camp.advertiser_id
            if adv_id is None:
                skipped += 1
                continue

            start_at = camp.start_at

            # Pre-window: [start_at - pre_days, start_at)
            pre_start = start_at - timedelta(days=pre_days)
            pre_end = start_at

            # Post-window depends on campaign status
            if camp.status == "completed" and camp.end_at is not None:
                # Completed: measure after the campaign ended
                post_start = camp.end_at
                post_end = camp.end_at + timedelta(days=post_days)
            else:
                # Active or no end_at: measure from start
                post_start = start_at
                post_end = start_at + timedelta(days=post_days)

            # ── Query Lift (interest / search) ──
            pre_query_avg, pre_query_cnt = await _avg_value_in_window(
                session, camp.id, "interest", "search", pre_start, pre_end,
                advertiser_id=adv_id,
            )
            post_query_avg, post_query_cnt = await _avg_value_in_window(
                session, camp.id, "interest", "search", post_start, post_end,
                advertiser_id=adv_id,
            )
            query_lift = _compute_lift(pre_query_avg, post_query_avg, epsilon)

            # ── Social Lift (interest / social) ──
            pre_social_avg, pre_social_cnt = await _avg_value_in_window(
                session, camp.id, "interest", "social", pre_start, pre_end,
                advertiser_id=adv_id,
            )
            post_social_avg, post_social_cnt = await _avg_value_in_window(
                session, camp.id, "interest", "social", post_start, post_end,
                advertiser_id=adv_id,
            )
            social_lift = _compute_lift(pre_social_avg, post_social_avg, epsilon)

            # ── Sales Lift (conversion / smartstore) ──
            pre_sales_avg, pre_sales_cnt = await _avg_value_in_window(
                session, camp.id, "conversion", "smartstore", pre_start, pre_end,
                advertiser_id=adv_id,
            )
            post_sales_avg, post_sales_cnt = await _avg_value_in_window(
                session, camp.id, "conversion", "smartstore", post_start, post_end,
                advertiser_id=adv_id,
            )
            sales_lift = _compute_lift(pre_sales_avg, post_sales_avg, epsilon)

            # ── Confidence ──
            signals_with_data = 0
            total_signals = 3
            if pre_query_cnt > 0 and post_query_cnt > 0:
                signals_with_data += 1
            if pre_social_cnt > 0 and post_social_cnt > 0:
                signals_with_data += 1
            if pre_sales_cnt > 0 and post_sales_cnt > 0:
                signals_with_data += 1
            confidence = round(signals_with_data / total_signals, 2)

            # Skip if absolutely no data at all
            if signals_with_data == 0 and query_lift is None and social_lift is None and sales_lift is None:
                skipped += 1
                continue

            now = datetime.now(UTC).replace(tzinfo=None)
            factors = {
                "pre_days": pre_days,
                "post_days": post_days,
                "pre_window": [pre_start.isoformat(), pre_end.isoformat()],
                "post_window": [post_start.isoformat(), post_end.isoformat()],
                "data_points": {
                    "query": {"pre": pre_query_cnt, "post": post_query_cnt},
                    "social": {"pre": pre_social_cnt, "post": post_social_cnt},
                    "sales": {"pre": pre_sales_cnt, "post": post_sales_cnt},
                },
            }

            # Upsert: delete existing then insert (unique per campaign_id)
            existing = (
                await session.execute(
                    select(CampaignLift).where(CampaignLift.campaign_id == camp.id)
                )
            ).scalar_one_or_none()

            if existing:
                existing.advertiser_id = adv_id
                existing.calculated_at = now
                existing.query_lift_pct = query_lift
                existing.pre_query_avg = pre_query_avg
                existing.post_query_avg = post_query_avg
                existing.social_lift_pct = social_lift
                existing.pre_social_avg = pre_social_avg
                existing.post_social_avg = post_social_avg
                existing.sales_lift_pct = sales_lift
                existing.pre_sales_avg = pre_sales_avg
                existing.post_sales_avg = post_sales_avg
                existing.confidence = confidence
                existing.factors = factors
                updated += 1
            else:
                session.add(
                    CampaignLift(
                        campaign_id=camp.id,
                        advertiser_id=adv_id,
                        calculated_at=now,
                        query_lift_pct=query_lift,
                        pre_query_avg=pre_query_avg,
                        post_query_avg=post_query_avg,
                        social_lift_pct=social_lift,
                        pre_social_avg=pre_social_avg,
                        post_social_avg=post_social_avg,
                        sales_lift_pct=sales_lift,
                        pre_sales_avg=pre_sales_avg,
                        post_sales_avg=post_sales_avg,
                        confidence=confidence,
                        factors=factors,
                    )
                )
                created += 1

        await session.commit()

        processed = len(campaigns)
        logger.info(
            "[lift_calculator] processed=%d created=%d updated=%d skipped=%d",
            processed, created, updated, skipped,
        )
        return {
            "processed": processed,
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }
