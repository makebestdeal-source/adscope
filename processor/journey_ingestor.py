"""Journey event ingestor -- mirror existing DB data into journey_events table.

Maps data from multiple source tables into a unified time-series:
  - SpendEstimate   -> EXPOSURE (spend)
  - AdDetail        -> EXPOSURE (impressions proxy)
  - TrafficSignal   -> INTEREST (search queries)
  - BrandChannelContent -> INTEREST (social engagements)
  - NewsMention     -> INTEREST (news mentions)
  - SmartStoreSnapshot  -> CONSIDERATION (reviews) / CONVERSION (orders, revenue)

Full-refresh per campaign: delete existing events then re-insert.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select

from database import async_session
from database.models import (
    AdDetail,
    AdSnapshot,
    Advertiser,
    BrandChannelContent,
    Campaign,
    JourneyEvent,
    NewsMention,
    SmartStoreSnapshot,
    SpendEstimate,
    TrafficSignal,
)

logger = logging.getLogger(__name__)

# How many days beyond the campaign window to look for signals
WINDOW_PAD_DAYS = 14


async def ingest_journey_events(
    campaign_ids: list[int] | None = None,
    days: int = 90,
) -> dict:
    """Mirror existing data into journey_events table.

    Args:
        campaign_ids: Specific campaigns to process. None = all with start_at.
        days: Only consider campaigns active within the last N days.

    Returns:
        {"processed": N, "inserted": N, "skipped": N}
    """
    async with async_session() as session:
        now = datetime.now(UTC).replace(tzinfo=None)
        cutoff = now - timedelta(days=days)

        # Fetch target campaigns
        camp_q = select(Campaign).where(Campaign.last_seen >= cutoff)
        if campaign_ids:
            camp_q = camp_q.where(Campaign.id.in_(campaign_ids))
        campaigns = (await session.execute(camp_q)).scalars().all()

        if not campaigns:
            logger.info("[journey_ingestor] no campaigns found")
            return {"processed": 0, "inserted": 0, "skipped": 0}

        total_inserted = 0
        skipped = 0

        for camp in campaigns:
            adv_id = camp.advertiser_id
            if adv_id is None:
                skipped += 1
                continue

            # Determine campaign time window
            window_start = (camp.start_at or camp.first_seen) - timedelta(days=WINDOW_PAD_DAYS)
            window_end = (camp.end_at or camp.last_seen or now) + timedelta(days=WINDOW_PAD_DAYS)

            # Full refresh: delete existing events for this campaign
            await session.execute(
                delete(JourneyEvent).where(JourneyEvent.campaign_id == camp.id)
            )

            events: list[JourneyEvent] = []

            # ── EXPOSURE: spend from SpendEstimate ──
            spend_rows = (
                await session.execute(
                    select(
                        SpendEstimate.date,
                        SpendEstimate.channel,
                        func.sum(SpendEstimate.est_daily_spend),
                    )
                    .where(
                        and_(
                            SpendEstimate.campaign_id == camp.id,
                            SpendEstimate.date >= window_start,
                            SpendEstimate.date <= window_end,
                        )
                    )
                    .group_by(SpendEstimate.date, SpendEstimate.channel)
                )
            ).fetchall()

            for row in spend_rows:
                dt, channel, total_spend = row
                if total_spend is None or total_spend <= 0:
                    continue
                events.append(
                    JourneyEvent(
                        campaign_id=camp.id,
                        advertiser_id=adv_id,
                        ts=dt,
                        stage="exposure",
                        source="ad_crawl",
                        metric="spend",
                        value=round(float(total_spend), 2),
                        dims={"channel": channel},
                    )
                )

            # ── EXPOSURE: impressions (AdDetail count per day) ──
            imp_rows = (
                await session.execute(
                    select(
                        func.date(AdSnapshot.captured_at).label("day"),
                        AdSnapshot.channel,
                        func.count(AdDetail.id),
                    )
                    .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                    .where(
                        and_(
                            AdDetail.advertiser_id == adv_id,
                            AdSnapshot.channel == camp.channel,
                            AdSnapshot.captured_at >= window_start,
                            AdSnapshot.captured_at <= window_end,
                        )
                    )
                    .group_by("day", AdSnapshot.channel)
                )
            ).fetchall()

            for row in imp_rows:
                day_str, channel, cnt = row
                if cnt is None or cnt <= 0:
                    continue
                # SQLite date() returns string 'YYYY-MM-DD'
                if isinstance(day_str, str):
                    ts = datetime.strptime(day_str, "%Y-%m-%d")
                else:
                    ts = day_str if isinstance(day_str, datetime) else datetime.combine(day_str, datetime.min.time())
                events.append(
                    JourneyEvent(
                        campaign_id=camp.id,
                        advertiser_id=adv_id,
                        ts=ts,
                        stage="exposure",
                        source="ad_crawl",
                        metric="impressions",
                        value=float(cnt),
                        dims={"channel": channel},
                    )
                )

            # ── INTEREST: search queries from TrafficSignal ──
            traffic_rows = (
                await session.execute(
                    select(
                        TrafficSignal.date,
                        TrafficSignal.composite_index,
                        TrafficSignal.brand_keyword,
                    ).where(
                        and_(
                            TrafficSignal.advertiser_id == adv_id,
                            TrafficSignal.date >= window_start,
                            TrafficSignal.date <= window_end,
                        )
                    )
                )
            ).fetchall()

            for row in traffic_rows:
                dt, composite_idx, keyword = row
                if composite_idx is None:
                    continue
                events.append(
                    JourneyEvent(
                        campaign_id=camp.id,
                        advertiser_id=adv_id,
                        ts=dt,
                        stage="interest",
                        source="search",
                        metric="queries",
                        value=float(composite_idx),
                        dims={"keyword": keyword} if keyword else {},
                    )
                )

            # ── INTEREST: social engagements from BrandChannelContent ──
            social_rows = (
                await session.execute(
                    select(
                        func.date(BrandChannelContent.upload_date).label("day"),
                        BrandChannelContent.platform,
                        func.sum(BrandChannelContent.like_count),
                    )
                    .where(
                        and_(
                            BrandChannelContent.advertiser_id == adv_id,
                            BrandChannelContent.upload_date >= window_start,
                            BrandChannelContent.upload_date <= window_end,
                            BrandChannelContent.like_count.is_not(None),
                        )
                    )
                    .group_by("day", BrandChannelContent.platform)
                )
            ).fetchall()

            for row in social_rows:
                day_str, platform, total_likes = row
                if total_likes is None or total_likes <= 0:
                    continue
                if isinstance(day_str, str):
                    ts = datetime.strptime(day_str, "%Y-%m-%d")
                else:
                    ts = day_str if isinstance(day_str, datetime) else datetime.combine(day_str, datetime.min.time())
                events.append(
                    JourneyEvent(
                        campaign_id=camp.id,
                        advertiser_id=adv_id,
                        ts=ts,
                        stage="interest",
                        source="social",
                        metric="engagements",
                        value=float(total_likes),
                        dims={"platform": platform},
                    )
                )

            # ── INTEREST: news mentions from NewsMention ──
            news_rows = (
                await session.execute(
                    select(
                        func.date(NewsMention.published_at).label("day"),
                        func.count(NewsMention.id),
                    )
                    .where(
                        and_(
                            NewsMention.advertiser_id == adv_id,
                            NewsMention.published_at >= window_start,
                            NewsMention.published_at <= window_end,
                        )
                    )
                    .group_by("day")
                )
            ).fetchall()

            for row in news_rows:
                day_str, cnt = row
                if cnt is None or cnt <= 0:
                    continue
                if isinstance(day_str, str):
                    ts = datetime.strptime(day_str, "%Y-%m-%d")
                else:
                    ts = day_str if isinstance(day_str, datetime) else datetime.combine(day_str, datetime.min.time())
                events.append(
                    JourneyEvent(
                        campaign_id=camp.id,
                        advertiser_id=adv_id,
                        ts=ts,
                        stage="interest",
                        source="news",
                        metric="mentions",
                        value=float(cnt),
                        dims={},
                    )
                )

            # ── CONSIDERATION: reviews from SmartStoreSnapshot ──
            review_rows = (
                await session.execute(
                    select(
                        func.date(SmartStoreSnapshot.captured_at).label("day"),
                        func.sum(SmartStoreSnapshot.review_delta),
                    )
                    .where(
                        and_(
                            SmartStoreSnapshot.advertiser_id == adv_id,
                            SmartStoreSnapshot.captured_at >= window_start,
                            SmartStoreSnapshot.captured_at <= window_end,
                            SmartStoreSnapshot.review_delta.is_not(None),
                        )
                    )
                    .group_by("day")
                )
            ).fetchall()

            for row in review_rows:
                day_str, total_reviews = row
                if total_reviews is None or total_reviews <= 0:
                    continue
                if isinstance(day_str, str):
                    ts = datetime.strptime(day_str, "%Y-%m-%d")
                else:
                    ts = day_str if isinstance(day_str, datetime) else datetime.combine(day_str, datetime.min.time())
                events.append(
                    JourneyEvent(
                        campaign_id=camp.id,
                        advertiser_id=adv_id,
                        ts=ts,
                        stage="consideration",
                        source="smartstore",
                        metric="reviews",
                        value=float(total_reviews),
                        dims={},
                    )
                )

            # ── CONVERSION: orders + revenue from SmartStoreSnapshot ──
            conv_rows = (
                await session.execute(
                    select(
                        func.date(SmartStoreSnapshot.captured_at).label("day"),
                        func.sum(SmartStoreSnapshot.purchase_cnt_delta),
                        func.sum(SmartStoreSnapshot.purchase_cnt_delta * SmartStoreSnapshot.price),
                    )
                    .where(
                        and_(
                            SmartStoreSnapshot.advertiser_id == adv_id,
                            SmartStoreSnapshot.captured_at >= window_start,
                            SmartStoreSnapshot.captured_at <= window_end,
                            SmartStoreSnapshot.purchase_cnt_delta.is_not(None),
                        )
                    )
                    .group_by("day")
                )
            ).fetchall()

            for row in conv_rows:
                day_str, total_orders, total_revenue = row
                if isinstance(day_str, str):
                    ts = datetime.strptime(day_str, "%Y-%m-%d")
                else:
                    ts = day_str if isinstance(day_str, datetime) else datetime.combine(day_str, datetime.min.time())

                if total_orders is not None and total_orders > 0:
                    events.append(
                        JourneyEvent(
                            campaign_id=camp.id,
                            advertiser_id=adv_id,
                            ts=ts,
                            stage="conversion",
                            source="smartstore",
                            metric="orders",
                            value=float(total_orders),
                            dims={},
                        )
                    )
                if total_revenue is not None and total_revenue > 0:
                    events.append(
                        JourneyEvent(
                            campaign_id=camp.id,
                            advertiser_id=adv_id,
                            ts=ts,
                            stage="conversion",
                            source="smartstore",
                            metric="revenue",
                            value=round(float(total_revenue), 0),
                            dims={},
                        )
                    )

            # Bulk insert
            if events:
                session.add_all(events)
                total_inserted += len(events)

        await session.commit()

        processed = len(campaigns)
        logger.info(
            "[journey_ingestor] processed=%d inserted=%d skipped=%d",
            processed, total_inserted, skipped,
        )
        return {"processed": processed, "inserted": total_inserted, "skipped": skipped}
