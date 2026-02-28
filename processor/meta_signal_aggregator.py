"""Meta-signal aggregator -- combines all signals into composite score + spend multiplier.

Reads from:
  - smartstore_snapshots  (매출 신호)
  - traffic_signals       (트래픽 신호)
  - activity_scores       (활동 점수)
  - panel_observations    (패널 보정)
  - serpapi_ads stealth_* (서프 접촉률 시그널)

Writes to:
  - meta_signal_composites (통합 메타신호 + spend_multiplier)

The spend_multiplier is used by campaign_builder to adjust SpendEstimate.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select, text

from database import async_session
from database.models import (
    ActivityScore,
    Advertiser,
    Campaign,
    MetaSignalComposite,
    PanelObservation,
    SmartStoreSnapshot,
    TrafficSignal,
)

logger = logging.getLogger(__name__)

# ── Weights for composite score (stealth 추가로 재조정) ──
W_SMARTSTORE = 0.25
W_TRAFFIC = 0.25
W_ACTIVITY = 0.25
W_STEALTH = 0.15   # stealth surf market vibrancy
W_PANEL = 0.10

# ── Campaign channel → stealth network ──
_CHANNEL_TO_NET = {
    "facebook": "meta", "instagram": "meta",
    "naver_da": "naver", "naver_search": "naver",
    "naver_shopping": "naver", "mobile_naver_ssp": "naver",
    "kakao_da": "kakao",
    "google_search_ads": "gdn", "mobile_gdn": "gdn", "youtube_ads": "gdn",
}

# ── Spend multiplier range ──
MULTIPLIER_MIN = 0.7
MULTIPLIER_MAX = 1.5


def _score_to_multiplier(composite: float) -> float:
    """Convert composite score (0-100) to spend multiplier (0.7-1.5).

    50 = neutral (1.0), 0 = 0.7, 100 = 1.5
    """
    # Linear mapping: 0->0.7, 50->1.0, 100->1.5
    if composite <= 50:
        mult = MULTIPLIER_MIN + (composite / 50) * (1.0 - MULTIPLIER_MIN)
    else:
        mult = 1.0 + ((composite - 50) / 50) * (MULTIPLIER_MAX - 1.0)
    return round(max(MULTIPLIER_MIN, min(MULTIPLIER_MAX, mult)), 3)


async def _calc_panel_calibration(
    session,
    advertiser_id: int,
    days: int = 7,
) -> float:
    """Compare AI panel vs human panel observation frequency.

    Returns calibration factor (0.8 ~ 1.2). Default 1.0 if no human panel data.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    ai_count = (
        await session.execute(
            select(func.count(PanelObservation.id)).where(
                and_(
                    PanelObservation.advertiser_id == advertiser_id,
                    PanelObservation.panel_type == "ai",
                    PanelObservation.observed_at >= cutoff,
                )
            )
        )
    ).scalar_one() or 0

    human_count = (
        await session.execute(
            select(func.count(PanelObservation.id)).where(
                and_(
                    PanelObservation.advertiser_id == advertiser_id,
                    PanelObservation.panel_type == "human",
                    PanelObservation.observed_at >= cutoff,
                )
            )
        )
    ).scalar_one() or 0

    if human_count == 0:
        return 1.0  # No human data, no calibration

    if ai_count == 0:
        return 1.1  # Human sees ads but AI doesn't -> slight upward adjustment

    ratio = human_count / ai_count
    # Clamp to 0.8 ~ 1.2
    calibration = max(0.8, min(1.2, ratio))
    return round(calibration, 3)


async def _load_stealth_network_scores(session) -> dict[str, float]:
    """Load stealth surf contact rates per network → 0-100 score."""
    since = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).isoformat()
    q = text("""
        SELECT json_extract(extra_data, '$.network') AS net, COUNT(*) AS cnt
        FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%' AND collected_at >= :since
        GROUP BY net
    """)
    result = await session.execute(q, {"since": since})
    rows = result.fetchall()
    ratios = {"gdn": 50, "naver": 6, "kakao": 6, "meta": 5}
    scores = {}
    for net, cnt in rows:
        if not net:
            continue
        imp = cnt / ratios.get(net, 10)
        # Scale: 100+ impressions = 100 score
        scores[net] = min(100.0, imp)
    return scores


async def _get_advertiser_stealth_score(
    session, adv_id: int, stealth_scores: dict[str, float]
) -> float:
    """Get stealth score for an advertiser based on their campaign channels."""
    if not stealth_scores:
        return 0.0
    ch_result = await session.execute(
        select(func.distinct(Campaign.channel)).where(
            and_(Campaign.advertiser_id == adv_id, Campaign.is_active == True)
        )
    )
    channels = ch_result.scalars().all()
    if not channels:
        return 0.0
    matched = []
    for ch in channels:
        net = _CHANNEL_TO_NET.get(ch)
        if net and net in stealth_scores:
            matched.append(stealth_scores[net])
    return sum(matched) / len(matched) if matched else 0.0


async def aggregate_meta_signals(
    session=None,
    advertiser_ids: list[int] | None = None,
) -> dict:
    """Aggregate all meta signals into composite score and spend multiplier.

    Returns: {"processed": N, "created": N, "updated": N}
    """
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        today = now.date()
        today_dt = datetime(today.year, today.month, today.day)
        yesterday_dt = today_dt - timedelta(days=1)

        # Pre-load stealth network scores
        stealth_net_scores = await _load_stealth_network_scores(session)

        # Get advertisers with any active campaign
        adv_query = (
            select(Campaign.advertiser_id)
            .where(Campaign.is_active == True)
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
            # 1. SmartStore score (latest snapshot's review_delta normalized)
            ss_snap = (
                await session.execute(
                    select(SmartStoreSnapshot)
                    .where(
                        and_(
                            SmartStoreSnapshot.advertiser_id == adv_id,
                            SmartStoreSnapshot.captured_at >= yesterday_dt,
                        )
                    )
                    .order_by(SmartStoreSnapshot.captured_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if ss_snap:
                # Normalize: 0 delta=0, 5+=50, 20+=100
                delta = ss_snap.review_delta or 0
                ss_score = min(100.0, delta * 5.0)
            else:
                ss_score = 0.0

            # 2. Traffic score (today's composite_index)
            traffic = (
                await session.execute(
                    select(TrafficSignal.composite_index).where(
                        and_(
                            TrafficSignal.advertiser_id == adv_id,
                            TrafficSignal.date == today_dt,
                        )
                    )
                )
            ).scalar_one_or_none()
            traffic_score = float(traffic) if traffic else 0.0

            # 3. Activity score (today's composite_score)
            activity = (
                await session.execute(
                    select(ActivityScore.composite_score).where(
                        and_(
                            ActivityScore.advertiser_id == adv_id,
                            ActivityScore.date == today_dt,
                        )
                    )
                )
            ).scalar_one_or_none()
            activity_score_val = float(activity) if activity else 0.0

            # 4. Stealth contact score
            stealth_val = await _get_advertiser_stealth_score(
                session, adv_id, stealth_net_scores
            )

            # 5. Panel calibration
            panel_cal = await _calc_panel_calibration(session, adv_id)

            # Composite score (weighted, stealth included)
            raw_composite = (
                ss_score * W_SMARTSTORE
                + traffic_score * W_TRAFFIC
                + activity_score_val * W_ACTIVITY
                + stealth_val * W_STEALTH
            )
            # Apply panel calibration to the composite
            composite = round(min(100.0, raw_composite * panel_cal), 1)

            # Spend multiplier
            spend_mult = _score_to_multiplier(composite)

            raw_factors = {
                "smartstore_raw": round(ss_score, 1),
                "traffic_raw": round(traffic_score, 1),
                "activity_raw": round(activity_score_val, 1),
                "stealth_raw": round(stealth_val, 1),
                "panel_calibration": panel_cal,
                "has_smartstore": ss_snap is not None,
                "has_traffic": traffic is not None,
                "has_activity": activity is not None,
                "has_stealth": stealth_val > 0,
            }

            # Upsert
            existing = (
                await session.execute(
                    select(MetaSignalComposite).where(
                        and_(
                            MetaSignalComposite.advertiser_id == adv_id,
                            MetaSignalComposite.date == today_dt,
                        )
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.smartstore_score = round(ss_score, 1)
                existing.traffic_score = round(traffic_score, 1)
                existing.activity_score = round(activity_score_val, 1)
                existing.panel_calibration = panel_cal
                existing.composite_score = composite
                existing.spend_multiplier = spend_mult
                existing.raw_factors = raw_factors
                updated += 1
            else:
                session.add(
                    MetaSignalComposite(
                        advertiser_id=adv_id,
                        date=today_dt,
                        smartstore_score=round(ss_score, 1),
                        traffic_score=round(traffic_score, 1),
                        activity_score=round(activity_score_val, 1),
                        panel_calibration=panel_cal,
                        composite_score=composite,
                        spend_multiplier=spend_mult,
                        raw_factors=raw_factors,
                    )
                )
                created += 1

        await session.commit()
        total = len(active_adv_ids)
        logger.info(
            "[meta_aggregator] processed=%d created=%d updated=%d",
            total, created, updated,
        )
        return {"processed": total, "created": created, "updated": updated}

    finally:
        if own_session:
            await session.close()


async def get_spend_multiplier(session, advertiser_id: int) -> float:
    """Get today's spend multiplier for an advertiser. Returns 1.0 if none."""
    today = datetime.now(UTC).replace(tzinfo=None).date()
    today_dt = datetime(today.year, today.month, today.day)

    result = (
        await session.execute(
            select(MetaSignalComposite.spend_multiplier).where(
                and_(
                    MetaSignalComposite.advertiser_id == advertiser_id,
                    MetaSignalComposite.date == today_dt,
                )
            )
        )
    ).scalar_one_or_none()

    return float(result) if result else 1.0
