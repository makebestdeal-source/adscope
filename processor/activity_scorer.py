"""Digital activity scorer -- compute activity state from existing DB data.

Uses:
- Campaigns (active count, channel diversity)
- AdDetails (creative count, variants)
- BrandChannelContent (social posts)
- Stealth surf contact rates (market-level ad frequency signals)

Output: ActivityScore row per advertiser per day.
States: test / scale / push / peak / cooldown
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, and_, text

from database import async_session
from database.models import (
    ActivityScore,
    AdDetail,
    AdSnapshot,
    Advertiser,
    BrandChannelContent,
    Campaign,
)

logger = logging.getLogger(__name__)

# ── Score weights (stealth 추가로 재조정) ──
W_CAMPAIGNS = 0.20
W_CREATIVES = 0.20
W_SOCIAL = 0.15
W_CHANNELS = 0.15
W_FREQUENCY = 0.15
W_STEALTH = 0.15  # stealth surf market signal

# ── Normalization caps ──
MAX_CAMPAIGNS = 10
MAX_CREATIVES = 50
MAX_SOCIAL = 20
MAX_CHANNELS = 6

# ── Campaign channel → stealth network mapping ──
_CHANNEL_TO_NETWORK = {
    "facebook": "meta", "instagram": "meta",
    "naver_da": "naver", "naver_search": "naver",
    "naver_shopping": "naver", "mobile_naver_ssp": "naver",
    "kakao_da": "kakao",
    "google_search_ads": "gdn", "mobile_gdn": "gdn", "youtube_ads": "gdn",
}


async def _get_stealth_contact_rates(session, days: int = 30) -> dict[str, float]:
    """Get stealth surf contact rates per network (cached per call)."""
    since = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)).isoformat()
    q = text("""
        SELECT json_extract(extra_data, '$.network') AS net,
               COUNT(*) AS cnt
        FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
          AND collected_at >= :since
        GROUP BY net
    """)
    result = await session.execute(q, {"since": since})
    rows = result.fetchall()
    if not rows:
        return {}
    # Normalize: request counts → 0-100 score per network
    ratios = {"gdn": 50, "naver": 6, "kakao": 6, "meta": 5}
    total_pages = 26  # pages per session
    # Estimate sessions from persona count
    pq = text("""
        SELECT COUNT(DISTINCT json_extract(extra_data, '$.persona'))
        FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%' AND collected_at >= :since
    """)
    persona_count = (await session.execute(pq, {"since": since})).scalar() or 1
    scores = {}
    for net, cnt in rows:
        if not net:
            continue
        imp = cnt / ratios.get(net, 10)
        rate = imp / (total_pages * persona_count)
        # Scale: 0.5+ rate = 100 score
        scores[net] = min(100.0, rate * 200.0)
    return scores


def _normalize(value: float, cap: float) -> float:
    """Normalize value to 0-100 scale with soft cap."""
    if cap <= 0:
        return 0.0
    return min(100.0, (value / cap) * 100.0)


def _determine_state(
    score: float,
    prev_score: float | None,
) -> str:
    """Determine activity state from composite score and trend."""
    if prev_score is not None and score < prev_score - 10:
        return "cooldown"
    if score >= 70:
        return "peak"
    if score >= 45:
        return "push"
    if score >= 20:
        return "scale"
    return "test"


async def calculate_activity_scores(
    session=None,
    days: int = 7,
    advertiser_ids: list[int] | None = None,
) -> dict:
    """Calculate activity scores for all active advertisers.

    Returns: {"processed": N, "created": N, "updated": N}
    """
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        cutoff = now - timedelta(days=days)
        today = now.date()
        today_dt = datetime(today.year, today.month, today.day)

        # Pre-load stealth contact rates (market-level)
        stealth_rates = await _get_stealth_contact_rates(session, days=30)

        # Get active advertisers (have campaigns in period)
        adv_query = (
            select(Campaign.advertiser_id)
            .where(Campaign.last_seen >= cutoff)
            .group_by(Campaign.advertiser_id)
        )
        if advertiser_ids:
            adv_query = adv_query.where(Campaign.advertiser_id.in_(advertiser_ids))

        result = await session.execute(adv_query)
        active_adv_ids = [r[0] for r in result.fetchall()]

        if not active_adv_ids:
            return {"processed": 0, "created": 0, "updated": 0}

        created = 0
        updated = 0

        for adv_id in active_adv_ids:
            # 1. Active campaigns count
            camp_count = (
                await session.execute(
                    select(func.count(Campaign.id)).where(
                        and_(
                            Campaign.advertiser_id == adv_id,
                            Campaign.is_active == True,
                        )
                    )
                )
            ).scalar_one()

            # 2. Creative count & variants (unique ad_text in period)
            creative_q = (
                select(
                    func.count(AdDetail.id),
                    func.count(func.distinct(AdDetail.ad_text)),
                )
                .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                .where(
                    and_(
                        AdDetail.advertiser_id == adv_id,
                        AdSnapshot.captured_at >= cutoff,
                    )
                )
            )
            cr_result = (await session.execute(creative_q)).one()
            total_creatives = cr_result[0] or 0
            creative_variants = cr_result[1] or 0

            # 3. Social post count
            social_count = (
                await session.execute(
                    select(func.count(BrandChannelContent.id)).where(
                        and_(
                            BrandChannelContent.advertiser_id == adv_id,
                            BrandChannelContent.upload_date >= cutoff,
                        )
                    )
                )
            ).scalar_one() or 0

            # 4. Channel diversity
            chan_count = (
                await session.execute(
                    select(func.count(func.distinct(Campaign.channel))).where(
                        and_(
                            Campaign.advertiser_id == adv_id,
                            Campaign.is_active == True,
                        )
                    )
                )
            ).scalar_one() or 0

            # 5. Ad frequency (avg daily ad_hits)
            daily_ads = total_creatives / max(1, days)

            # 6. Stealth market signal — advertiser's channels matched to stealth contact rates
            adv_channels = (
                await session.execute(
                    select(func.distinct(Campaign.channel)).where(
                        and_(Campaign.advertiser_id == adv_id, Campaign.is_active == True)
                    )
                )
            ).scalars().all()
            stealth_score = 0.0
            if stealth_rates and adv_channels:
                matched_scores = []
                for ch in adv_channels:
                    net = _CHANNEL_TO_NETWORK.get(ch)
                    if net and net in stealth_rates:
                        matched_scores.append(stealth_rates[net])
                if matched_scores:
                    stealth_score = sum(matched_scores) / len(matched_scores)

            # Compute composite score
            s_campaigns = _normalize(camp_count, MAX_CAMPAIGNS)
            s_creatives = _normalize(creative_variants, MAX_CREATIVES)
            s_social = _normalize(social_count, MAX_SOCIAL)
            s_channels = _normalize(chan_count, MAX_CHANNELS)
            s_frequency = _normalize(daily_ads, 10)
            s_stealth = stealth_score  # already 0-100

            composite = (
                s_campaigns * W_CAMPAIGNS
                + s_creatives * W_CREATIVES
                + s_social * W_SOCIAL
                + s_channels * W_CHANNELS
                + s_frequency * W_FREQUENCY
                + s_stealth * W_STEALTH
            )
            composite = round(min(100.0, composite), 1)

            # Previous score for state determination
            prev_q = (
                select(ActivityScore.composite_score)
                .where(
                    and_(
                        ActivityScore.advertiser_id == adv_id,
                        ActivityScore.date < today_dt,
                    )
                )
                .order_by(ActivityScore.date.desc())
                .limit(1)
            )
            prev_row = (await session.execute(prev_q)).scalar_one_or_none()

            state = _determine_state(composite, prev_row)

            factors = {
                "campaigns": camp_count,
                "creatives": total_creatives,
                "creative_variants": creative_variants,
                "social_posts": social_count,
                "channels": chan_count,
                "daily_avg_ads": round(daily_ads, 1),
                "stealth_score": round(stealth_score, 1),
                "sub_scores": {
                    "campaigns": round(s_campaigns, 1),
                    "creatives": round(s_creatives, 1),
                    "social": round(s_social, 1),
                    "channels": round(s_channels, 1),
                    "frequency": round(s_frequency, 1),
                    "stealth": round(s_stealth, 1),
                },
            }

            # Upsert
            existing = (
                await session.execute(
                    select(ActivityScore).where(
                        and_(
                            ActivityScore.advertiser_id == adv_id,
                            ActivityScore.date == today_dt,
                        )
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.active_campaigns = camp_count
                existing.new_creatives = total_creatives
                existing.creative_variants = creative_variants
                existing.social_post_count = social_count
                existing.channel_count = chan_count
                existing.composite_score = composite
                existing.activity_state = state
                existing.factors = factors
                updated += 1
            else:
                session.add(
                    ActivityScore(
                        advertiser_id=adv_id,
                        date=today_dt,
                        active_campaigns=camp_count,
                        new_creatives=total_creatives,
                        creative_variants=creative_variants,
                        social_post_count=social_count,
                        channel_count=chan_count,
                        composite_score=composite,
                        activity_state=state,
                        factors=factors,
                    )
                )
                created += 1

        await session.commit()
        total = len(active_adv_ids)
        logger.info(
            "[activity_scorer] processed=%d created=%d updated=%d",
            total, created, updated,
        )
        return {"processed": total, "created": created, "updated": updated}

    finally:
        if own_session:
            await session.close()
