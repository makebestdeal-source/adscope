"""쇼핑 카테고리 랭킹 계산기.

ShoppingKeyword.category 별로 스토어의 판매 활동을 점수화하여
일일 랭킹 스냅샷(ShoppingCategoryRanking)을 생성한다.

점수 공식 (0-100):
  예상 GMV 30% + 거래량 20% + 리뷰 속도 20%
  + 상품 다양성 15% + 가격 경쟁력 15%
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import func, select, and_, distinct

from database import async_session
from database.models import (
    ShoppingCategoryRanking,
    ShoppingKeyword,
    SmartStoreSnapshot,
)


# ── 점수 가중치 ──
W_GMV = 0.30
W_TRANSACTIONS = 0.20
W_REVIEWS = 0.20
W_PRODUCTS = 0.15
W_PRICE_COMP = 0.15


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


def _price_competitiveness(avg_price: float, category_avg: float) -> float:
    """가격 경쟁력 점수: 카테고리 평균에 가까울수록 높음 (0-100)."""
    if not avg_price or not category_avg or category_avg == 0:
        return 50.0  # 데이터 없으면 중간값
    deviation = abs(avg_price - category_avg) / category_avg
    return max(0.0, min(100.0, (1.0 - deviation) * 100))


async def calculate_shopping_rankings(target_date: datetime | None = None) -> dict:
    """쇼핑 카테고리 랭킹을 계산하고 DB에 저장.

    Returns: {"processed": N, "created": N, "categories": N}
    """
    if target_date is None:
        target_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    period_start = target_date - timedelta(days=7)
    prev_week = target_date - timedelta(days=7)

    stats = {"processed": 0, "created": 0, "categories": 0}

    async with async_session() as session:
        # 활성 카테고리 목록
        categories = (await session.execute(
            select(ShoppingKeyword.category).where(
                ShoppingKeyword.is_active == True,
                ShoppingKeyword.category.isnot(None),
            ).distinct()
        )).scalars().all()

        for category in categories:
            # 해당 카테고리의 키워드
            keywords = (await session.execute(
                select(ShoppingKeyword.keyword).where(
                    ShoppingKeyword.category == category,
                    ShoppingKeyword.is_active == True,
                )
            )).scalars().all()

            if not keywords:
                continue

            # 최근 7일 SmartStoreSnapshot에서 store_name별 집계
            # ranking_category가 해당 카테고리의 키워드인 스냅샷
            store_agg_q = (
                select(
                    SmartStoreSnapshot.store_name,
                    func.count(distinct(SmartStoreSnapshot.product_url)).label("product_count"),
                    func.avg(SmartStoreSnapshot.price).label("avg_price"),
                    func.sum(func.coalesce(SmartStoreSnapshot.estimated_daily_sales, 0)).label("daily_sales"),
                    func.sum(func.coalesce(SmartStoreSnapshot.review_count, 0)).label("review_count"),
                    func.sum(func.coalesce(SmartStoreSnapshot.review_delta, 0)).label("review_delta"),
                    func.sum(func.coalesce(SmartStoreSnapshot.purchase_cnt, 0)).label("purchase_cnt"),
                    func.sum(func.coalesce(SmartStoreSnapshot.purchase_cnt_delta, 0)).label("purchase_delta"),
                    func.max(SmartStoreSnapshot.advertiser_id).label("advertiser_id"),
                )
                .where(
                    SmartStoreSnapshot.ranking_category.in_(keywords),
                    SmartStoreSnapshot.captured_at >= period_start,
                    SmartStoreSnapshot.store_name.isnot(None),
                    SmartStoreSnapshot.store_name != "",
                )
                .group_by(SmartStoreSnapshot.store_name)
            )

            rows = (await session.execute(store_agg_q)).all()

            if not rows:
                continue

            # 메트릭 정리
            store_metrics = []
            for row in rows:
                avg_price = int(row.avg_price) if row.avg_price else 0
                daily_sales = int(row.daily_sales) if row.daily_sales else 0
                gmv = daily_sales * avg_price if avg_price > 0 else 0

                store_metrics.append({
                    "store_name": row.store_name,
                    "advertiser_id": row.advertiser_id,
                    "product_count": row.product_count or 0,
                    "avg_price": avg_price,
                    "daily_sales": daily_sales,
                    "gmv": gmv,
                    "review_count": int(row.review_count) if row.review_count else 0,
                    "review_delta": int(row.review_delta) if row.review_delta else 0,
                    "purchase_cnt": int(row.purchase_cnt) if row.purchase_cnt else 0,
                    "purchase_delta": int(row.purchase_delta) if row.purchase_delta else 0,
                })

            if not store_metrics:
                continue

            # 카테고리 최대/평균값
            max_gmv = max((m["gmv"] for m in store_metrics), default=1)
            max_purchase = max((m["purchase_delta"] for m in store_metrics), default=1)
            max_reviews = max((m["review_delta"] for m in store_metrics), default=1)
            max_products = max((m["product_count"] for m in store_metrics), default=1)
            cat_avg_price = sum(m["avg_price"] for m in store_metrics) / len(store_metrics) if store_metrics else 1

            # 점수 계산
            for m in store_metrics:
                s_gmv = _log_score(m["gmv"], max_gmv)
                s_trans = _log_score(m["purchase_delta"], max_purchase)
                s_reviews = _log_score(m["review_delta"], max_reviews)
                s_products = _linear_score(m["product_count"], max_products)
                s_price = _price_competitiveness(m["avg_price"], cat_avg_price)

                score = (
                    s_gmv * W_GMV
                    + s_trans * W_TRANSACTIONS
                    + s_reviews * W_REVIEWS
                    + s_products * W_PRODUCTS
                    + s_price * W_PRICE_COMP
                )
                m["composite_score"] = round(score, 2)

            # 순위
            store_metrics.sort(key=lambda x: x["composite_score"], reverse=True)
            avg_score = sum(m["composite_score"] for m in store_metrics) / len(store_metrics)
            total_stores = len(store_metrics)

            # 지난주 랭킹 (WoW)
            prev_rankings = {}
            prev_rows = (await session.execute(
                select(ShoppingCategoryRanking).where(
                    ShoppingCategoryRanking.date == prev_week,
                    ShoppingCategoryRanking.shopping_category == category,
                )
            )).scalars().all()
            for pr in prev_rows:
                prev_rankings[pr.store_name] = {
                    "score": pr.composite_score,
                    "rank": pr.rank_in_category,
                    "gmv": pr.total_estimated_gmv,
                }

            # Upsert
            for rank, m in enumerate(store_metrics, 1):
                prev = prev_rankings.get(m["store_name"])
                wow_score = round(m["composite_score"] - prev["score"], 2) if prev else None
                wow_rank = (prev["rank"] - rank) if prev else None
                wow_gmv = None
                if prev and prev["gmv"] and prev["gmv"] > 0:
                    wow_gmv = round(((m["gmv"] - prev["gmv"]) / prev["gmv"]) * 100, 2)

                existing = (await session.execute(
                    select(ShoppingCategoryRanking).where(
                        ShoppingCategoryRanking.date == target_date,
                        ShoppingCategoryRanking.shopping_category == category,
                        ShoppingCategoryRanking.store_name == m["store_name"],
                    )
                )).scalar_one_or_none()

                if existing:
                    existing.advertiser_id = m["advertiser_id"]
                    existing.product_count = m["product_count"]
                    existing.avg_price = m["avg_price"]
                    existing.total_estimated_daily_sales = m["daily_sales"]
                    existing.total_estimated_gmv = m["gmv"]
                    existing.total_review_count = m["review_count"]
                    existing.total_review_delta = m["review_delta"]
                    existing.total_purchase_cnt = m["purchase_cnt"]
                    existing.total_purchase_delta = m["purchase_delta"]
                    existing.composite_score = m["composite_score"]
                    existing.rank_in_category = rank
                    existing.category_avg_score = round(avg_score, 2)
                    existing.category_total_stores = total_stores
                    existing.score_wow_change = wow_score
                    existing.rank_wow_change = wow_rank
                    existing.gmv_wow_change_pct = wow_gmv
                else:
                    session.add(ShoppingCategoryRanking(
                        date=target_date,
                        shopping_category=category,
                        store_name=m["store_name"],
                        advertiser_id=m["advertiser_id"],
                        product_count=m["product_count"],
                        avg_price=m["avg_price"],
                        total_estimated_daily_sales=m["daily_sales"],
                        total_estimated_gmv=m["gmv"],
                        total_review_count=m["review_count"],
                        total_review_delta=m["review_delta"],
                        total_purchase_cnt=m["purchase_cnt"],
                        total_purchase_delta=m["purchase_delta"],
                        composite_score=m["composite_score"],
                        rank_in_category=rank,
                        category_avg_score=round(avg_score, 2),
                        category_total_stores=total_stores,
                        score_wow_change=wow_score,
                        rank_wow_change=wow_rank,
                        gmv_wow_change_pct=wow_gmv,
                    ))
                    stats["created"] += 1

                stats["processed"] += 1

            stats["categories"] += 1

        await session.commit()

    logger.info(f"[shopping_ranking] done: {stats}")
    return stats
