"""소셜 카테고리 랭킹 계산기.

산업(Industry) 카테고리별로 광고주의 소셜 활동을 점수화하여
일일 랭킹 스냅샷(SocialCategoryRanking)을 생성한다.

점수 공식 (0-100):
  구독자 규모 20% + 구독자 성장률 20% + 포스팅 빈도 20%
  + 인게이지먼트 25% + 조회수 15%
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import func, select, and_

from database import async_session
from database.models import (
    Advertiser,
    AdDetail,
    AdSnapshot,
    BrandChannelContent,
    ChannelStats,
    Industry,
    Keyword,
    SocialCategoryRanking,
)


# ── 점수 가중치 ──
W_SUBSCRIBERS = 0.20
W_GROWTH = 0.20
W_POSTING = 0.20
W_ENGAGEMENT = 0.25
W_VIEWS = 0.15


def _log_score(value: float, max_value: float) -> float:
    """로그 스케일 정규화 (0-100)."""
    if value <= 0 or max_value <= 0:
        return 0.0
    return min(100.0, (math.log1p(value) / math.log1p(max_value)) * 100)


def _linear_score(value: float, cap: float) -> float:
    """선형 정규화 (cap까지, 0-100)."""
    if value <= 0 or cap <= 0:
        return 0.0
    return min(100.0, (value / cap) * 100)


async def auto_assign_industries(session) -> int:
    """industry_id가 NULL인 광고주에게 키워드 기반 산업 자동배정.

    AdDetail → AdSnapshot → Keyword → industry_id 경로로
    가장 많은 광고가 발견된 산업을 배정한다.
    """
    # industry_id가 NULL이고 소셜 데이터가 있는 광고주
    null_advs = (await session.execute(
        select(Advertiser.id).where(
            Advertiser.industry_id.is_(None),
            Advertiser.official_channels.isnot(None),
        )
    )).scalars().all()

    if not null_advs:
        return 0

    assigned = 0
    for adv_id in null_advs:
        # 해당 광고주의 AdDetail → Keyword.industry_id 집계
        rows = (await session.execute(
            select(Keyword.industry_id, func.count(AdDetail.id).label("cnt"))
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
            .where(
                AdDetail.advertiser_id == adv_id,
                Keyword.industry_id.isnot(None),
            )
            .group_by(Keyword.industry_id)
            .order_by(func.count(AdDetail.id).desc())
            .limit(1)
        )).first()

        if rows:
            adv = await session.get(Advertiser, adv_id)
            if adv:
                adv.industry_id = rows[0]
                assigned += 1

    if assigned:
        await session.commit()
        logger.info(f"[social_ranking] auto-assigned industry to {assigned} advertisers")
    return assigned


async def calculate_social_rankings(target_date: datetime | None = None) -> dict:
    """소셜 카테고리 랭킹을 계산하고 DB에 저장.

    Returns: {"processed": N, "created": N, "industries": N}
    """
    if target_date is None:
        target_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    period_start = target_date - timedelta(days=7)
    prev_week = target_date - timedelta(days=7)

    stats = {"processed": 0, "created": 0, "industries": 0}

    async with async_session() as session:
        # Phase 1: industry 자동배정
        await auto_assign_industries(session)

        # 모든 산업 로드
        industries = (await session.execute(select(Industry))).scalars().all()

        for industry in industries:
            # 해당 산업의 광고주 중 소셜 데이터가 있는 광고주
            adv_ids_q = select(Advertiser.id).where(
                Advertiser.industry_id == industry.id
            )
            adv_ids = (await session.execute(adv_ids_q)).scalars().all()
            if not adv_ids:
                continue

            # 광고주별 메트릭 수집
            adv_metrics = []

            for adv_id in adv_ids:
                # ChannelStats (최신)
                cs_rows = (await session.execute(
                    select(ChannelStats).where(
                        ChannelStats.advertiser_id == adv_id,
                    ).order_by(ChannelStats.collected_at.desc()).limit(5)
                )).scalars().all()

                subs = 0
                followers = 0
                for cs in cs_rows:
                    if cs.subscribers and cs.subscribers > subs:
                        subs = cs.subscribers
                    if cs.followers and cs.followers > followers:
                        followers = cs.followers
                total_subscribers = subs + followers

                # 7일전 구독자 (성장률 계산용)
                old_cs = (await session.execute(
                    select(ChannelStats).where(
                        ChannelStats.advertiser_id == adv_id,
                        ChannelStats.collected_at <= period_start,
                    ).order_by(ChannelStats.collected_at.desc()).limit(5)
                )).scalars().all()

                old_subs = 0
                old_followers = 0
                for cs in old_cs:
                    if cs.subscribers and cs.subscribers > old_subs:
                        old_subs = cs.subscribers
                    if cs.followers and cs.followers > old_followers:
                        old_followers = cs.followers
                old_total = old_subs + old_followers

                growth_rate = 0.0
                if old_total > 0:
                    growth_rate = ((total_subscribers - old_total) / old_total) * 100

                # BrandChannelContent (7일간)
                content_agg = (await session.execute(
                    select(
                        func.count(BrandChannelContent.id),
                        func.coalesce(func.sum(BrandChannelContent.view_count), 0),
                        func.coalesce(func.sum(BrandChannelContent.like_count), 0),
                    ).where(
                        BrandChannelContent.advertiser_id == adv_id,
                        BrandChannelContent.upload_date >= period_start,
                    )
                )).first()

                posts = content_agg[0] or 0
                views = content_agg[1] or 0
                likes = content_agg[2] or 0

                # Fallback: ChannelStats에서 avg_likes/avg_views 사용
                if posts == 0 and total_subscribers == 0:
                    continue  # 소셜 데이터 없는 광고주 스킵

                # engagement_rate
                eng_rate = 0.0
                if total_subscribers > 0 and posts > 0:
                    avg_likes = likes / posts if posts > 0 else 0
                    eng_rate = (avg_likes / total_subscribers) * 100
                elif cs_rows and cs_rows[0].engagement_rate:
                    eng_rate = cs_rows[0].engagement_rate or 0.0

                posting_freq = float(posts)  # 7일간 포스팅 수 = 주간 빈도

                adv_metrics.append({
                    "adv_id": adv_id,
                    "total_subscribers": total_subscribers,
                    "posts": posts,
                    "views": views,
                    "likes": likes,
                    "engagement_rate": eng_rate,
                    "growth_rate": growth_rate,
                    "posting_freq": posting_freq,
                })

            if not adv_metrics:
                continue

            # 산업 내 최대값 (정규화용)
            max_subs = max((m["total_subscribers"] for m in adv_metrics), default=1)
            max_views = max((m["views"] for m in adv_metrics), default=1)

            # 점수 계산
            scored = []
            for m in adv_metrics:
                s_subs = _log_score(m["total_subscribers"], max_subs)
                s_growth = _linear_score(min(m["growth_rate"] + 50, 100), 100)  # -50%~+50% → 0~100
                s_posting = _linear_score(m["posting_freq"], 14)  # cap: 14 posts/week
                s_engage = _linear_score(m["engagement_rate"], 10)  # cap: 10%
                s_views = _log_score(m["views"], max_views)

                score = (
                    s_subs * W_SUBSCRIBERS
                    + s_growth * W_GROWTH
                    + s_posting * W_POSTING
                    + s_engage * W_ENGAGEMENT
                    + s_views * W_VIEWS
                )
                m["composite_score"] = round(score, 2)
                scored.append(m)

            # 순위 부여
            scored.sort(key=lambda x: x["composite_score"], reverse=True)
            avg_score = sum(m["composite_score"] for m in scored) / len(scored)
            total_advs = len(scored)

            # 지난주 랭킹 조회 (WoW 비교)
            prev_rankings = {}
            prev_rows = (await session.execute(
                select(SocialCategoryRanking).where(
                    SocialCategoryRanking.date == prev_week,
                    SocialCategoryRanking.industry_id == industry.id,
                )
            )).scalars().all()
            for pr in prev_rows:
                prev_rankings[pr.advertiser_id] = {
                    "score": pr.composite_score,
                    "rank": pr.rank_in_industry,
                }

            # Upsert
            for rank, m in enumerate(scored, 1):
                prev = prev_rankings.get(m["adv_id"])
                wow_score = round(m["composite_score"] - prev["score"], 2) if prev else None
                wow_rank = (prev["rank"] - rank) if prev else None  # positive = improved

                existing = (await session.execute(
                    select(SocialCategoryRanking).where(
                        SocialCategoryRanking.date == target_date,
                        SocialCategoryRanking.advertiser_id == m["adv_id"],
                    )
                )).scalar_one_or_none()

                if existing:
                    existing.industry_id = industry.id
                    existing.total_subscribers = m["total_subscribers"]
                    existing.total_posts_period = m["posts"]
                    existing.total_views_period = m["views"]
                    existing.total_likes_period = m["likes"]
                    existing.engagement_rate = round(m["engagement_rate"], 4)
                    existing.subscriber_growth_rate = round(m["growth_rate"], 2)
                    existing.posting_frequency = m["posting_freq"]
                    existing.composite_score = m["composite_score"]
                    existing.rank_in_industry = rank
                    existing.industry_avg_score = round(avg_score, 2)
                    existing.industry_total_advs = total_advs
                    existing.score_wow_change = wow_score
                    existing.rank_wow_change = wow_rank
                else:
                    session.add(SocialCategoryRanking(
                        date=target_date,
                        industry_id=industry.id,
                        advertiser_id=m["adv_id"],
                        total_subscribers=m["total_subscribers"],
                        total_posts_period=m["posts"],
                        total_views_period=m["views"],
                        total_likes_period=m["likes"],
                        engagement_rate=round(m["engagement_rate"], 4),
                        subscriber_growth_rate=round(m["growth_rate"], 2),
                        posting_frequency=m["posting_freq"],
                        composite_score=m["composite_score"],
                        rank_in_industry=rank,
                        industry_avg_score=round(avg_score, 2),
                        industry_total_advs=total_advs,
                        score_wow_change=wow_score,
                        rank_wow_change=wow_rank,
                    ))
                    stats["created"] += 1

                stats["processed"] += 1

            stats["industries"] += 1

        await session.commit()

    logger.info(f"[social_ranking] done: {stats}")
    return stats
