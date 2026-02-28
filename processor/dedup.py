"""Dedup logic for ad_details -- prevents duplicate INSERT, updates seen tracking.

Used by data_washer.promote_approved() and fast_crawl.save_to_db().
"""

from datetime import datetime

from sqlalchemy import select, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AdDetail, AdSnapshot


async def find_existing_ad(
    session: AsyncSession,
    channel: str,
    creative_hash: str | None,
    advertiser_name: str | None,
    ad_text: str | None,
    url: str | None,
) -> int | None:
    """Find existing ad_detail ID matching the same ad in the same channel.

    Match priority:
    1. creative_hash (if available) within same channel
    2. (advertiser_name_raw + ad_text + url) within same channel

    Returns ad_detail.id if found, None otherwise.
    """
    # Try creative_hash first (most reliable)
    if creative_hash:
        stmt = (
            select(AdDetail.id)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(
                AdDetail.creative_hash == creative_hash,
                AdSnapshot.channel == channel,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        existing_id = result.scalar_one_or_none()
        if existing_id:
            return existing_id

    # Fallback: text-based match (need at least one non-null field to avoid false matches)
    has_any = bool(advertiser_name or ad_text or url)
    if not has_any:
        return None  # All key fields are NULL → cannot determine uniqueness

    conditions = [AdSnapshot.channel == channel]
    if advertiser_name:
        conditions.append(AdDetail.advertiser_name_raw == advertiser_name)
    else:
        conditions.append(AdDetail.advertiser_name_raw.is_(None))
    if ad_text:
        conditions.append(AdDetail.ad_text == ad_text)
    else:
        conditions.append(AdDetail.ad_text.is_(None))
    if url:
        conditions.append(AdDetail.url == url)
    else:
        conditions.append(AdDetail.url.is_(None))

    stmt = (
        select(AdDetail.id)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(and_(*conditions))
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_seen(session: AsyncSession, ad_detail_id: int, captured_at: datetime | None = None):
    """Increment seen_count and update last_seen_at for an existing ad."""
    now = captured_at or datetime.utcnow()
    stmt = (
        update(AdDetail)
        .where(AdDetail.id == ad_detail_id)
        .values(
            seen_count=AdDetail.seen_count + 1,
            last_seen_at=now,
        )
    )
    await session.execute(stmt)
