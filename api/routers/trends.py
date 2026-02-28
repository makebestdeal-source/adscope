"""트렌드 데이터 API."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import Keyword, TrendData
from database.schemas import TrendDataOut

router = APIRouter(prefix="/api/trends", tags=["trends"], redirect_slashes=False,
    dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[TrendDataOut])
async def list_trends(
    keyword_id: int | None = None,
    keyword: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """트렌드 데이터 목록 조회."""
    query = select(TrendData).order_by(TrendData.date.desc())

    if keyword_id:
        query = query.where(TrendData.keyword_id == keyword_id)
    elif keyword:
        sub = select(Keyword.id).where(Keyword.keyword.ilike(f"%{keyword}%"))
        query = query.where(TrendData.keyword_id.in_(sub))

    if date_from:
        query = query.where(TrendData.date >= date_from)
    if date_to:
        query = query.where(TrendData.date <= date_to)

    result = await db.execute(query.offset(offset).limit(limit))
    return result.scalars().all()


@router.get("/keywords/top")
async def top_trending_keywords(
    days: int = Query(default=30, le=90),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """최근 N일 네이버 트렌드 평균 기준 상위 키워드."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    avg_naver = func.avg(TrendData.naver_trend)
    avg_google = func.avg(TrendData.google_trend)

    result = await db.execute(
        select(
            Keyword.id,
            Keyword.keyword,
            avg_naver.label("avg_naver_trend"),
            avg_google.label("avg_google_trend"),
            func.max(TrendData.date).label("latest_at"),
        )
        .join(Keyword, Keyword.id == TrendData.keyword_id)
        .where(TrendData.date >= cutoff)
        .group_by(Keyword.id, Keyword.keyword)
        .order_by(func.coalesce(avg_naver, 0).desc())
        .limit(limit)
    )

    return [
        {
            "keyword_id": row[0],
            "keyword": row[1],
            "avg_naver_trend": round(row[2], 2) if row[2] is not None else None,
            "avg_google_trend": round(row[3], 2) if row[3] is not None else None,
            "latest_at": row[4],
        }
        for row in result.all()
    ]


@router.get("/keywords/{keyword_id}", response_model=list[TrendDataOut])
async def trend_by_keyword(
    keyword_id: int,
    days: int = Query(default=30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """특정 키워드의 최근 N일 트렌드 시계열."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(TrendData)
        .where(TrendData.keyword_id == keyword_id)
        .where(TrendData.date >= cutoff)
        .order_by(TrendData.date.asc())
    )
    return result.scalars().all()
