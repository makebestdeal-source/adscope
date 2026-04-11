"""쇼핑 카테고리 랭킹 API v2.

카테고리별 스토어 판매 활동 랭킹 조회.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, desc

from api.deps import get_current_user
from database import async_session
from database.models import ShoppingCategoryRanking

router = APIRouter(
    prefix="/api/shopping-ranking-v2",
    tags=["shopping-ranking-v2"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/categories")
async def list_categories():
    """쇼핑 카테고리 목록 + 최신 랭킹 요약."""
    async with async_session() as session:
        latest_date = (await session.execute(
            select(func.max(ShoppingCategoryRanking.date))
        )).scalar()

        if not latest_date:
            return {"categories": [], "latest_date": None}

        rows = (await session.execute(
            select(
                ShoppingCategoryRanking.shopping_category,
                func.count(ShoppingCategoryRanking.id).label("store_count"),
                func.avg(ShoppingCategoryRanking.composite_score).label("avg_score"),
                func.sum(ShoppingCategoryRanking.total_estimated_gmv).label("total_gmv"),
                func.max(ShoppingCategoryRanking.composite_score).label("top_score"),
            )
            .where(ShoppingCategoryRanking.date == latest_date)
            .group_by(ShoppingCategoryRanking.shopping_category)
            .order_by(func.sum(ShoppingCategoryRanking.total_estimated_gmv).desc())
        )).all()

        categories = []
        for row in rows:
            # 1위 스토어
            top_store = (await session.execute(
                select(ShoppingCategoryRanking.store_name).where(
                    ShoppingCategoryRanking.date == latest_date,
                    ShoppingCategoryRanking.shopping_category == row.shopping_category,
                    ShoppingCategoryRanking.rank_in_category == 1,
                )
            )).scalar()

            categories.append({
                "category": row.shopping_category,
                "store_count": row.store_count,
                "avg_score": round(row.avg_score, 1) if row.avg_score else 0,
                "total_gmv": int(row.total_gmv) if row.total_gmv else 0,
                "top_score": round(row.top_score, 1) if row.top_score else 0,
                "top_store": top_store,
            })

    return {"categories": categories, "latest_date": str(latest_date)[:10]}


@router.get("/{category}")
async def get_category_ranking(
    category: str,
    sort_by: str = Query("score", regex="^(score|gmv|reviews|products|growth)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """카테고리 내 스토어 랭킹."""
    async with async_session() as session:
        latest_date = (await session.execute(
            select(func.max(ShoppingCategoryRanking.date)).where(
                ShoppingCategoryRanking.shopping_category == category,
            )
        )).scalar()

        if not latest_date:
            return {"rankings": [], "total": 0, "category": category}

        sort_map = {
            "score": ShoppingCategoryRanking.composite_score,
            "gmv": ShoppingCategoryRanking.total_estimated_gmv,
            "reviews": ShoppingCategoryRanking.total_review_delta,
            "products": ShoppingCategoryRanking.product_count,
            "growth": ShoppingCategoryRanking.gmv_wow_change_pct,
        }
        sort_col = sort_map.get(sort_by, ShoppingCategoryRanking.composite_score)

        base_where = [
            ShoppingCategoryRanking.date == latest_date,
            ShoppingCategoryRanking.shopping_category == category,
        ]

        total = (await session.execute(
            select(func.count(ShoppingCategoryRanking.id)).where(*base_where)
        )).scalar() or 0

        rows = (await session.execute(
            select(ShoppingCategoryRanking)
            .where(*base_where)
            .order_by(desc(sort_col))
            .offset(offset).limit(limit)
        )).scalars().all()

        rankings = []
        for r in rows:
            rankings.append({
                "rank": r.rank_in_category,
                "store_name": r.store_name,
                "advertiser_id": r.advertiser_id,
                "composite_score": r.composite_score,
                "product_count": r.product_count,
                "avg_price": r.avg_price,
                "estimated_daily_sales": r.total_estimated_daily_sales,
                "estimated_gmv": r.total_estimated_gmv,
                "review_count": r.total_review_count,
                "review_delta": r.total_review_delta,
                "purchase_cnt": r.total_purchase_cnt,
                "purchase_delta": r.total_purchase_delta,
                "score_wow_change": r.score_wow_change,
                "rank_wow_change": r.rank_wow_change,
                "gmv_wow_change_pct": r.gmv_wow_change_pct,
            })

    return {
        "category": category,
        "date": str(latest_date)[:10],
        "total": total,
        "rankings": rankings,
    }


@router.get("/{category}/trend")
async def get_category_trend(
    category: str,
    days: int = Query(30, ge=7, le=90),
    top_n: int = Query(5, ge=1, le=20),
):
    """카테고리 트렌드: 일별 총 GMV + 상위 N개 스토어 시계열."""
    since = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        daily_agg = (await session.execute(
            select(
                ShoppingCategoryRanking.date,
                func.sum(ShoppingCategoryRanking.total_estimated_gmv).label("total_gmv"),
                func.count(ShoppingCategoryRanking.id).label("store_count"),
            )
            .where(
                ShoppingCategoryRanking.shopping_category == category,
                ShoppingCategoryRanking.date >= since,
            )
            .group_by(ShoppingCategoryRanking.date)
            .order_by(ShoppingCategoryRanking.date)
        )).all()

        # Top N 스토어
        latest_date = (await session.execute(
            select(func.max(ShoppingCategoryRanking.date)).where(
                ShoppingCategoryRanking.shopping_category == category,
            )
        )).scalar()

        top_stores = []
        if latest_date:
            top_rows = (await session.execute(
                select(ShoppingCategoryRanking.store_name)
                .where(
                    ShoppingCategoryRanking.date == latest_date,
                    ShoppingCategoryRanking.shopping_category == category,
                )
                .order_by(ShoppingCategoryRanking.rank_in_category)
                .limit(top_n)
            )).scalars().all()

            for store in top_rows:
                store_trend = (await session.execute(
                    select(
                        ShoppingCategoryRanking.date,
                        ShoppingCategoryRanking.total_estimated_gmv,
                        ShoppingCategoryRanking.composite_score,
                    )
                    .where(
                        ShoppingCategoryRanking.store_name == store,
                        ShoppingCategoryRanking.shopping_category == category,
                        ShoppingCategoryRanking.date >= since,
                    )
                    .order_by(ShoppingCategoryRanking.date)
                )).all()

                top_stores.append({
                    "store_name": store,
                    "data": [
                        {"date": str(d)[:10], "gmv": g, "score": s}
                        for d, g, s in store_trend
                    ],
                })

    return {
        "category_trend": [
            {"date": str(r.date)[:10], "total_gmv": int(r.total_gmv or 0), "store_count": r.store_count}
            for r in daily_agg
        ],
        "top_stores": top_stores,
    }


@router.get("/top-movers")
async def get_top_movers(
    limit: int = Query(20, ge=1, le=50),
):
    """WoW GMV 변화 Top 스토어."""
    async with async_session() as session:
        latest_date = (await session.execute(
            select(func.max(ShoppingCategoryRanking.date))
        )).scalar()

        if not latest_date:
            return {"risers": [], "fallers": []}

        base_q = (
            select(ShoppingCategoryRanking)
            .where(
                ShoppingCategoryRanking.date == latest_date,
                ShoppingCategoryRanking.gmv_wow_change_pct.isnot(None),
            )
        )

        risers = (await session.execute(
            base_q.order_by(desc(ShoppingCategoryRanking.gmv_wow_change_pct)).limit(limit)
        )).scalars().all()

        fallers = (await session.execute(
            base_q.order_by(ShoppingCategoryRanking.gmv_wow_change_pct).limit(limit)
        )).scalars().all()

        def _fmt(rows):
            return [{
                "store_name": r.store_name,
                "category": r.shopping_category,
                "composite_score": r.composite_score,
                "estimated_gmv": r.total_estimated_gmv,
                "gmv_wow_change_pct": r.gmv_wow_change_pct,
                "rank_in_category": r.rank_in_category,
                "rank_wow_change": r.rank_wow_change,
            } for r in rows]

    return {
        "date": str(latest_date)[:10],
        "risers": _fmt(risers),
        "fallers": _fmt(fallers),
    }
