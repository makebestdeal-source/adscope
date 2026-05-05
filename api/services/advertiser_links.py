"""Helpers for keeping advertiser labels and profile links consistent."""

from __future__ import annotations

from datetime import datetime, timedelta
import re

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.services.advertiser_names import (
    display_advertiser_name,
    is_low_confidence_campaign_source_name,
    is_person_or_handle_advertiser_name,
    is_placeholder_advertiser_name,
)
from database.models import AdDetail, AdSnapshot, Advertiser


def needs_context_advertiser_name(advertiser_name: object | None) -> bool:
    return (
        is_placeholder_advertiser_name(advertiser_name)
        or is_person_or_handle_advertiser_name(advertiser_name)
        or is_low_confidence_campaign_source_name(advertiser_name)
    )


def _norm_label(value: object | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def is_platform_profile_url(value: object | None) -> bool:
    text = str(value or "").lower()
    return any(
        marker in text
        for marker in (
            "adstransparency.google.com",
            "ader.naver.com",
            "facebook.com/ads/library",
            "tiktok.com/business/creativecenter",
        )
    )


async def resolve_profile_advertiser_id(
    db: AsyncSession,
    *,
    current_id: int | None,
    current_name: object | None,
    display_name: object | None,
) -> int | None:
    """Resolve a campaign's display label to the matching advertiser profile id."""
    if not current_id or not display_name:
        return current_id
    if not needs_context_advertiser_name(current_name):
        return current_id

    target = _norm_label(display_name)
    current = _norm_label(current_name)
    if not target or target == current:
        return current_id

    result = await db.execute(
        select(Advertiser).where(
            or_(
                func.lower(Advertiser.name) == target,
                func.lower(Advertiser.brand_name) == target,
            )
        )
    )
    candidates = [
        adv
        for adv in result.scalars().all()
        if adv.id != current_id
        and display_advertiser_name(adv.name, adv.brand_name, fallback=None)
        and not needs_context_advertiser_name(adv.name)
    ]
    if not candidates:
        return current_id

    candidate_ids = [adv.id for adv in candidates]
    cutoff = datetime.utcnow() - timedelta(days=365)
    count_result = await db.execute(
        select(AdDetail.advertiser_id, func.count(AdDetail.id).label("ad_count"))
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(
            AdDetail.advertiser_id.in_(candidate_ids),
            AdSnapshot.captured_at >= cutoff,
            or_(
                AdDetail.verification_status.is_(None),
                AdDetail.verification_status != "rejected",
            ),
        )
        .group_by(AdDetail.advertiser_id)
    )
    ad_counts = {row.advertiser_id: int(row.ad_count or 0) for row in count_result.all()}

    def score(adv: Advertiser) -> tuple[int, int, int, int]:
        exact_name = 1 if _norm_label(adv.name) == target else 0
        clean_site = 0 if is_platform_profile_url(adv.website) else 1
        official_type = 1 if adv.advertiser_type in ("company", "brand", "group") else 0
        return (exact_name, clean_site, official_type, ad_counts.get(adv.id, 0))

    return max(candidates, key=score).id
