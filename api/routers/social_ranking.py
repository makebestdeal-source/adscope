"""소셜 카테고리 랭킹 API.

산업(Industry)별 광고주 소셜 활동 랭킹 조회.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select, desc

from database import async_session
from database.models import (
    Advertiser,
    Industry,
    SocialCategoryRanking,
)

router = APIRouter(
    prefix="/api/social-ranking",
    tags=["social-ranking"],
)


@router.get("/industries")
async def list_industries():
    """산업 목록 + 최신 랭킹 요약."""
    async with async_session() as session:
        # 가장 최근 날짜
        latest_date = (await session.execute(
            select(func.max(SocialCategoryRanking.date))
        )).scalar()

        if not latest_date:
            return {"industries": [], "latest_date": None}

        # 산업별 요약
        rows = (await session.execute(
            select(
                SocialCategoryRanking.industry_id,
                Industry.name,
                func.count(SocialCategoryRanking.id).label("advertiser_count"),
                func.avg(SocialCategoryRanking.composite_score).label("avg_score"),
                func.max(SocialCategoryRanking.composite_score).label("top_score"),
            )
            .join(Industry, SocialCategoryRanking.industry_id == Industry.id)
            .where(SocialCategoryRanking.date == latest_date)
            .group_by(SocialCategoryRanking.industry_id, Industry.name)
            .order_by(func.count(SocialCategoryRanking.id).desc())
        )).all()

        industries = []
        for row in rows:
            # 1위 광고주
            top_adv = (await session.execute(
                select(Advertiser.name).join(
                    SocialCategoryRanking,
                    SocialCategoryRanking.advertiser_id == Advertiser.id,
                ).where(
                    SocialCategoryRanking.date == latest_date,
                    SocialCategoryRanking.industry_id == row.industry_id,
                    SocialCategoryRanking.rank_in_industry == 1,
                )
            )).scalar()

            industries.append({
                "industry_id": row.industry_id,
                "industry_name": row.name,
                "advertiser_count": row.advertiser_count,
                "avg_score": round(row.avg_score, 1) if row.avg_score else 0,
                "top_score": round(row.top_score, 1) if row.top_score else 0,
                "top_advertiser": top_adv,
            })

    return {"industries": industries, "latest_date": str(latest_date)[:10]}


@router.get("/{industry_id}")
async def get_industry_ranking(
    industry_id: int,
    sort_by: str = Query("score", regex="^(score|subscribers|engagement|posting|growth)$"),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """산업 내 광고주 랭킹."""
    async with async_session() as session:
        latest_date = (await session.execute(
            select(func.max(SocialCategoryRanking.date)).where(
                SocialCategoryRanking.industry_id == industry_id,
            )
        )).scalar()

        if not latest_date:
            return {"rankings": [], "total": 0, "industry": None}

        industry = (await session.execute(
            select(Industry).where(Industry.id == industry_id)
        )).scalar_one_or_none()

        # 정렬 매핑
        sort_map = {
            "score": SocialCategoryRanking.composite_score,
            "subscribers": SocialCategoryRanking.total_subscribers,
            "engagement": SocialCategoryRanking.engagement_rate,
            "posting": SocialCategoryRanking.posting_frequency,
            "growth": SocialCategoryRanking.subscriber_growth_rate,
        }
        sort_col = sort_map.get(sort_by, SocialCategoryRanking.composite_score)

        q = (
            select(SocialCategoryRanking, Advertiser.name.label("advertiser_name"))
            .join(Advertiser, SocialCategoryRanking.advertiser_id == Advertiser.id)
            .where(
                SocialCategoryRanking.date == latest_date,
                SocialCategoryRanking.industry_id == industry_id,
            )
            .order_by(desc(sort_col))
        )

        total = (await session.execute(
            select(func.count(SocialCategoryRanking.id)).where(
                SocialCategoryRanking.date == latest_date,
                SocialCategoryRanking.industry_id == industry_id,
            )
        )).scalar() or 0

        rows = (await session.execute(q.offset(offset).limit(limit))).all()

        rankings = []
        for r, adv_name in rows:
            rankings.append({
                "rank": r.rank_in_industry,
                "advertiser_id": r.advertiser_id,
                "advertiser_name": adv_name,
                "composite_score": r.composite_score,
                "total_subscribers": r.total_subscribers,
                "total_posts": r.total_posts_period,
                "total_views": r.total_views_period,
                "total_likes": r.total_likes_period,
                "engagement_rate": r.engagement_rate,
                "subscriber_growth_rate": r.subscriber_growth_rate,
                "posting_frequency": r.posting_frequency,
                "score_wow_change": r.score_wow_change,
                "rank_wow_change": r.rank_wow_change,
            })

    return {
        "industry": {"id": industry.id, "name": industry.name} if industry else None,
        "date": str(latest_date)[:10],
        "total": total,
        "rankings": rankings,
    }


@router.get("/{industry_id}/trend")
async def get_industry_trend(
    industry_id: int,
    days: int = Query(30, ge=7, le=90),
    top_n: int = Query(5, ge=1, le=20),
):
    """산업 트렌드: 일별 평균 점수 + 상위 N개 광고주 시계열."""
    since = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        # 일별 평균
        daily_avg = (await session.execute(
            select(
                SocialCategoryRanking.date,
                func.avg(SocialCategoryRanking.composite_score).label("avg_score"),
                func.count(SocialCategoryRanking.id).label("count"),
            )
            .where(
                SocialCategoryRanking.industry_id == industry_id,
                SocialCategoryRanking.date >= since,
            )
            .group_by(SocialCategoryRanking.date)
            .order_by(SocialCategoryRanking.date)
        )).all()

        # 현재 top N 광고주
        latest_date = (await session.execute(
            select(func.max(SocialCategoryRanking.date)).where(
                SocialCategoryRanking.industry_id == industry_id,
            )
        )).scalar()

        top_advs = []
        if latest_date:
            top_rows = (await session.execute(
                select(SocialCategoryRanking.advertiser_id, Advertiser.name)
                .join(Advertiser, SocialCategoryRanking.advertiser_id == Advertiser.id)
                .where(
                    SocialCategoryRanking.date == latest_date,
                    SocialCategoryRanking.industry_id == industry_id,
                )
                .order_by(SocialCategoryRanking.rank_in_industry)
                .limit(top_n)
            )).all()

            for adv_id, adv_name in top_rows:
                adv_trend = (await session.execute(
                    select(SocialCategoryRanking.date, SocialCategoryRanking.composite_score)
                    .where(
                        SocialCategoryRanking.advertiser_id == adv_id,
                        SocialCategoryRanking.industry_id == industry_id,
                        SocialCategoryRanking.date >= since,
                    )
                    .order_by(SocialCategoryRanking.date)
                )).all()

                top_advs.append({
                    "advertiser_id": adv_id,
                    "advertiser_name": adv_name,
                    "data": [{"date": str(d)[:10], "score": s} for d, s in adv_trend],
                })

    return {
        "industry_avg": [
            {"date": str(r.date)[:10], "avg_score": round(r.avg_score, 1), "count": r.count}
            for r in daily_avg
        ],
        "top_advertisers": top_advs,
    }


@router.get("/top-movers")
async def get_top_movers(
    limit: int = Query(20, ge=1, le=50),
):
    """WoW 상승/하락 Top 광고주."""
    async with async_session() as session:
        latest_date = (await session.execute(
            select(func.max(SocialCategoryRanking.date))
        )).scalar()

        if not latest_date:
            return {"risers": [], "fallers": []}

        base_q = (
            select(
                SocialCategoryRanking,
                Advertiser.name.label("advertiser_name"),
                Industry.name.label("industry_name"),
            )
            .join(Advertiser, SocialCategoryRanking.advertiser_id == Advertiser.id)
            .join(Industry, SocialCategoryRanking.industry_id == Industry.id)
            .where(
                SocialCategoryRanking.date == latest_date,
                SocialCategoryRanking.score_wow_change.isnot(None),
            )
        )

        # 상승
        risers = (await session.execute(
            base_q.order_by(desc(SocialCategoryRanking.score_wow_change)).limit(limit)
        )).all()

        # 하락
        fallers = (await session.execute(
            base_q.order_by(SocialCategoryRanking.score_wow_change).limit(limit)
        )).all()

        def _fmt(rows):
            return [{
                "advertiser_id": r.advertiser_id,
                "advertiser_name": adv_name,
                "industry_name": ind_name,
                "composite_score": r.composite_score,
                "score_wow_change": r.score_wow_change,
                "rank_in_industry": r.rank_in_industry,
                "rank_wow_change": r.rank_wow_change,
            } for r, adv_name, ind_name in rows]

    return {
        "date": str(latest_date)[:10],
        "risers": _fmt(risers),
        "fallers": _fmt(fallers),
    }
