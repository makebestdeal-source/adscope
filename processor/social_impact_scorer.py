"""Social impact scorer -- measure brand impact from ads/PR.

Combines three signals:
  1. News impact: article volume + sentiment from news_mentions
  2. Social posting impact: posting frequency + engagement changes from BrandChannelContent
  3. Search lift: search volume changes from TrafficSignal correlated with campaigns

Output: SocialImpactScore row per advertiser per day.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, select

from database import async_session
from database.models import (
    Advertiser,
    BrandChannelContent,
    Campaign,
    ChannelStats,
    NewsMention,
    SocialImpactScore,
    TrafficSignal,
)

logger = logging.getLogger(__name__)

# ── Score weights ──
W_NEWS = 0.30
W_SOCIAL = 0.35
W_SEARCH = 0.35

# ── Normalization caps ──
MAX_NEWS_ARTICLES = 20
SENTIMENT_BONUS_WEIGHT = 0.2


def _normalize(value: float, cap: float) -> float:
    if cap <= 0:
        return 0.0
    return min(100.0, (value / cap) * 100.0)


def _calc_news_impact(article_count: int, avg_sentiment: float) -> float:
    """News impact score (0-100).
    Base: article volume (max 80), Bonus: positive sentiment (max 20).
    """
    base = min(80.0, (article_count / MAX_NEWS_ARTICLES) * 80.0)
    sentiment_bonus = max(0, avg_sentiment * SENTIMENT_BONUS_WEIGHT * 100)
    return round(min(100.0, base + sentiment_bonus), 1)


def _calc_social_posting_impact(
    current_posts: int,
    baseline_posts: int,
    current_engagement: float,
    baseline_engagement: float,
    has_active_campaign: bool,
) -> tuple[float, float, float]:
    """Social posting impact (0-100).
    Returns: (score, posting_delta_pct, engagement_delta_pct)
    """
    # Posting frequency lift (40% of score)
    if baseline_posts > 0:
        posting_delta = ((current_posts - baseline_posts) / baseline_posts) * 100
    else:
        posting_delta = 100.0 if current_posts > 0 else 0.0

    posting_norm = min(40.0, max(0, (posting_delta + 100) / 300 * 40))

    # Engagement lift (60% of score)
    if baseline_engagement > 0.01:
        eng_delta = ((current_engagement - baseline_engagement) / baseline_engagement) * 100
    else:
        eng_delta = 100.0 if current_engagement > 0.01 else 0.0

    eng_norm = min(60.0, max(0, (eng_delta + 100) / 300 * 60))

    score = posting_norm + eng_norm

    # Discount organic growth (no campaign = less ad impact)
    if not has_active_campaign:
        score *= 0.7

    return round(min(100.0, score), 1), round(posting_delta, 1), round(eng_delta, 1)


def _calc_search_lift(
    current_index: float | None,
    baseline_index: float | None,
    wow_change: float | None,
    has_active_campaign: bool,
    campaign_days: int,
) -> tuple[float, float | None]:
    """Search lift score (0-100).
    Returns: (score, search_volume_delta_pct)
    """
    if current_index is None:
        return 0.0, None

    if has_active_campaign and baseline_index and baseline_index > 0:
        delta_pct = ((current_index - baseline_index) / baseline_index) * 100
        base = min(70.0, max(0, delta_pct / 200 * 70))
        recency = max(0, min(30, 30 - campaign_days))
        score = base + recency
        return round(min(100.0, score), 1), round(delta_pct, 1)

    # No campaign -- use WoW change as proxy
    if wow_change is not None:
        score = max(0, min(100, wow_change)) * 0.4
        return round(score, 1), round(wow_change, 1)

    return 0.0, None


def _calc_composite(news: float, social: float, search: float) -> float:
    return round(min(100.0, news * W_NEWS + social * W_SOCIAL + search * W_SEARCH), 1)


def _determine_phase(
    has_active: bool,
    days_since_end: int | None,
) -> str:
    if has_active:
        return "during"
    if days_since_end is not None and days_since_end <= 30:
        return "post"
    if days_since_end is not None:
        return "pre"
    return "none"


async def calculate_social_impact_scores(
    session=None,
    advertiser_ids: list[int] | None = None,
    days: int = 7,
) -> dict:
    """Calculate social impact scores for all active advertisers.

    Returns: {"processed": N, "created": N, "updated": N}
    """
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        cutoff = now - timedelta(days=days)
        baseline_start = cutoff - timedelta(days=days)
        today = now.date()
        today_dt = datetime(today.year, today.month, today.day)

        # Get advertisers: those with campaigns OR news mentions in period
        camp_adv = (
            select(Campaign.advertiser_id)
            .where(Campaign.last_seen >= baseline_start)
            .group_by(Campaign.advertiser_id)
        )
        news_adv = (
            select(NewsMention.advertiser_id)
            .where(NewsMention.collected_at >= cutoff)
            .group_by(NewsMention.advertiser_id)
        )

        combined = select(Advertiser.id).where(
            Advertiser.id.in_(camp_adv) | Advertiser.id.in_(news_adv)
        )
        if advertiser_ids:
            combined = combined.where(Advertiser.id.in_(advertiser_ids))

        result = await session.execute(combined)
        adv_ids = [r[0] for r in result.fetchall()]

        if not adv_ids:
            return {"processed": 0, "created": 0, "updated": 0}

        created = 0
        updated = 0

        for adv_id in adv_ids:
            # ── 1. News impact ──
            news_q = select(
                func.count(NewsMention.id),
                func.avg(NewsMention.sentiment_score),
            ).where(
                and_(
                    NewsMention.advertiser_id == adv_id,
                    NewsMention.collected_at >= cutoff,
                )
            )
            news_row = (await session.execute(news_q)).one()
            article_count = news_row[0] or 0
            avg_sentiment = news_row[1] or 0.0
            news_score = _calc_news_impact(article_count, avg_sentiment)

            # ── 2. Social posting impact ──
            # Current period posts
            curr_social = (
                await session.execute(
                    select(func.count(BrandChannelContent.id)).where(
                        and_(
                            BrandChannelContent.advertiser_id == adv_id,
                            BrandChannelContent.upload_date >= cutoff,
                        )
                    )
                )
            ).scalar_one() or 0

            # Baseline period posts
            base_social = (
                await session.execute(
                    select(func.count(BrandChannelContent.id)).where(
                        and_(
                            BrandChannelContent.advertiser_id == adv_id,
                            BrandChannelContent.upload_date >= baseline_start,
                            BrandChannelContent.upload_date < cutoff,
                        )
                    )
                )
            ).scalar_one() or 0

            # Current engagement rate (latest ChannelStats)
            curr_eng = (
                await session.execute(
                    select(func.avg(ChannelStats.engagement_rate)).where(
                        and_(
                            ChannelStats.advertiser_id == adv_id,
                            ChannelStats.collected_at >= cutoff,
                        )
                    )
                )
            ).scalar_one() or 0.0

            base_eng = (
                await session.execute(
                    select(func.avg(ChannelStats.engagement_rate)).where(
                        and_(
                            ChannelStats.advertiser_id == adv_id,
                            ChannelStats.collected_at >= baseline_start,
                            ChannelStats.collected_at < cutoff,
                        )
                    )
                )
            ).scalar_one() or 0.0

            # ── 3. Campaign info ──
            active_camp = (
                await session.execute(
                    select(func.count(Campaign.id)).where(
                        and_(
                            Campaign.advertiser_id == adv_id,
                            Campaign.is_active == True,
                        )
                    )
                )
            ).scalar_one() or 0
            has_active = active_camp > 0

            # Campaign days active (from earliest active campaign)
            camp_first = (
                await session.execute(
                    select(func.min(Campaign.first_seen)).where(
                        and_(
                            Campaign.advertiser_id == adv_id,
                            Campaign.is_active == True,
                        )
                    )
                )
            ).scalar_one()
            campaign_days = (now - camp_first).days if camp_first else 0

            # Days since last campaign ended (for phase)
            last_end = (
                await session.execute(
                    select(func.max(Campaign.last_seen)).where(
                        and_(
                            Campaign.advertiser_id == adv_id,
                            Campaign.is_active == False,
                        )
                    )
                )
            ).scalar_one()
            days_since_end = (now - last_end).days if last_end else None

            social_score, posting_delta, eng_delta = _calc_social_posting_impact(
                curr_social, base_social, curr_eng, base_eng, has_active,
            )

            # ── 4. Search lift ──
            traffic_q = (
                select(TrafficSignal.composite_index, TrafficSignal.wow_change_pct)
                .where(TrafficSignal.advertiser_id == adv_id)
                .order_by(TrafficSignal.date.desc())
                .limit(1)
            )
            traffic_row = (await session.execute(traffic_q)).one_or_none()
            current_index = traffic_row[0] if traffic_row else None
            wow_change = traffic_row[1] if traffic_row else None

            # Baseline search index (before campaign or 14 days ago)
            baseline_cutoff = camp_first if camp_first else (now - timedelta(days=14))
            baseline_traffic = (
                await session.execute(
                    select(func.avg(TrafficSignal.composite_index)).where(
                        and_(
                            TrafficSignal.advertiser_id == adv_id,
                            TrafficSignal.date <= baseline_cutoff,
                        )
                    )
                )
            ).scalar_one()

            search_score, search_delta = _calc_search_lift(
                current_index, baseline_traffic, wow_change, has_active, campaign_days,
            )

            # ── 5. Composite ──
            composite = _calc_composite(news_score, social_score, search_score)
            phase = _determine_phase(has_active, days_since_end)

            factors = {
                "news": {
                    "article_count": article_count,
                    "avg_sentiment": round(avg_sentiment, 2),
                    "score": news_score,
                },
                "social": {
                    "current_posts": curr_social,
                    "baseline_posts": base_social,
                    "current_engagement": round(curr_eng, 2),
                    "baseline_engagement": round(base_eng, 2),
                    "score": social_score,
                },
                "search": {
                    "current_index": round(current_index, 1) if current_index else None,
                    "baseline_index": round(baseline_traffic, 1) if baseline_traffic else None,
                    "wow_change": round(wow_change, 1) if wow_change else None,
                    "score": search_score,
                },
                "campaign": {
                    "active_count": active_camp,
                    "days_active": campaign_days,
                    "phase": phase,
                },
            }

            # ── 6. Upsert ──
            existing = (
                await session.execute(
                    select(SocialImpactScore).where(
                        and_(
                            SocialImpactScore.advertiser_id == adv_id,
                            SocialImpactScore.date == today_dt,
                        )
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.news_impact_score = news_score
                existing.social_posting_score = social_score
                existing.search_lift_score = search_score
                existing.composite_score = composite
                existing.news_article_count = article_count
                existing.news_sentiment_avg = round(avg_sentiment, 2) if avg_sentiment else None
                existing.social_engagement_delta_pct = eng_delta
                existing.social_posting_delta_pct = posting_delta
                existing.search_volume_delta_pct = search_delta
                existing.has_active_campaign = has_active
                existing.campaign_days_active = campaign_days
                existing.impact_phase = phase
                existing.factors = factors
                updated += 1
            else:
                session.add(SocialImpactScore(
                    advertiser_id=adv_id,
                    date=today_dt,
                    news_impact_score=news_score,
                    social_posting_score=social_score,
                    search_lift_score=search_score,
                    composite_score=composite,
                    news_article_count=article_count,
                    news_sentiment_avg=round(avg_sentiment, 2) if avg_sentiment else None,
                    social_engagement_delta_pct=eng_delta,
                    social_posting_delta_pct=posting_delta,
                    search_volume_delta_pct=search_delta,
                    has_active_campaign=has_active,
                    campaign_days_active=campaign_days,
                    impact_phase=phase,
                    factors=factors,
                ))
                created += 1

        await session.commit()
        total = len(adv_ids)
        logger.info(
            "[social_impact] processed=%d created=%d updated=%d",
            total, created, updated,
        )
        return {"processed": total, "created": created, "updated": updated}

    except Exception:
        logger.exception("[social_impact] calculate_social_impact_scores failed")
        await session.rollback()
        raise
    finally:
        if own_session:
            await session.close()
