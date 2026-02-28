"""Consumer Insights API -- ad copy themes, promotion distribution, winning creatives, keyword landscape."""

import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import (
    AdDetail,
    AdSnapshot,
    Advertiser,
    Campaign,
    Industry,
    Keyword,
    ProductCategory,
)

router = APIRouter(prefix="/api/consumer-insights", tags=["consumer-insights"],
    dependencies=[Depends(get_current_user)])

KST = timezone(timedelta(hours=9))

# Korean ad stopwords
_STOPWORDS = {
    "이", "그", "저", "것", "를", "을", "에", "의", "가", "은", "는", "로", "으로",
    "와", "과", "도", "에서", "까지", "부터", "만", "보다", "처럼", "같이",
    "및", "등", "더", "좀", "잘", "못", "안", "수", "있는", "있다", "하는", "하다",
    "합니다", "입니다", "되는", "된", "위한", "통해", "대한", "한", "할", "위",
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are",
    "with", "your", "our", "this", "that", "from", "by", "be", "as", "it", "all",
    "http", "https", "www", "com", "kr", "co", "net",
}


def _extract_words(text: str, min_len: int = 2) -> list[str]:
    """Simple Korean/English word extraction from ad text."""
    if not text:
        return []
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Split on non-alphanumeric (keep Korean)
    tokens = re.findall(r"[가-힣a-zA-Z0-9]+", text)
    return [t for t in tokens if len(t) >= min_len and t.lower() not in _STOPWORDS]


@router.get("/ad-copy-themes")
async def ad_copy_themes(
    industry_id: int | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(30, ge=10, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Top words/phrases from ad copy text, grouped by frequency."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    q = (
        select(AdDetail.ad_text, AdDetail.ad_description)
        .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.ad_text.isnot(None))
    )
    if industry_id:
        q = q.join(Advertiser, Advertiser.id == AdDetail.advertiser_id).where(
            Advertiser.industry_id == industry_id
        )
    q = q.limit(5000)  # cap for performance

    rows = (await db.execute(q)).all()

    counter: Counter = Counter()
    for row in rows:
        combined = (row.ad_text or "") + " " + (row.ad_description or "")
        words = _extract_words(combined)
        counter.update(words)

    top_words = counter.most_common(limit)
    return [{"word": w, "count": c} for w, c in top_words]


@router.get("/promotion-distribution")
async def promotion_distribution(
    industry_id: int | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Distribution of promotion types and campaign objectives."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    # Promotion types from ad_details
    promo_q = (
        select(
            AdDetail.promotion_type,
            func.count(AdDetail.id).label("cnt"),
        )
        .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
        .where(and_(AdSnapshot.captured_at >= cutoff, AdDetail.promotion_type.isnot(None)))
    )
    if industry_id:
        promo_q = promo_q.join(Advertiser, Advertiser.id == AdDetail.advertiser_id).where(
            Advertiser.industry_id == industry_id
        )
    promo_q = promo_q.group_by(AdDetail.promotion_type).order_by(func.count(AdDetail.id).desc())
    promo_rows = (await db.execute(promo_q)).all()

    # Campaign objectives
    obj_q = (
        select(
            Campaign.objective,
            func.count(Campaign.id).label("cnt"),
        )
        .where(and_(Campaign.first_seen >= cutoff, Campaign.objective.isnot(None)))
    )
    if industry_id:
        obj_q = obj_q.join(Advertiser, Advertiser.id == Campaign.advertiser_id).where(
            Advertiser.industry_id == industry_id
        )
    obj_q = obj_q.group_by(Campaign.objective).order_by(func.count(Campaign.id).desc())
    obj_rows = (await db.execute(obj_q)).all()

    return {
        "promotion_types": [
            {"type": r.promotion_type, "count": r.cnt}
            for r in promo_rows
        ],
        "objectives": [
            {"objective": r.objective, "count": r.cnt}
            for r in obj_rows
        ],
    }


@router.get("/winning-creatives")
async def winning_creatives(
    industry_id: int | None = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(20, ge=5, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Most frequently seen ad creatives (high repetition = effective)."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    q = (
        select(
            AdDetail.id,
            AdDetail.ad_text,
            AdDetail.ad_description,
            AdDetail.seen_count,
            AdDetail.promotion_type,
            AdDetail.creative_image_path,
            AdDetail.product_name,
            Advertiser.id.label("advertiser_id"),
            Advertiser.name.label("advertiser_name"),
            AdSnapshot.channel,
        )
        .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
        .outerjoin(Advertiser, Advertiser.id == AdDetail.advertiser_id)
        .where(and_(AdSnapshot.captured_at >= cutoff, AdDetail.seen_count > 1))
    )
    if industry_id:
        q = q.where(Advertiser.industry_id == industry_id)

    q = q.order_by(AdDetail.seen_count.desc()).limit(limit)
    rows = (await db.execute(q)).all()

    return [
        {
            "id": r.id,
            "ad_text": (r.ad_text or "")[:200],
            "ad_description": (r.ad_description or "")[:200],
            "seen_count": r.seen_count,
            "promotion_type": r.promotion_type,
            "image_path": r.creative_image_path,
            "product_name": r.product_name,
            "advertiser_id": r.advertiser_id,
            "advertiser_name": r.advertiser_name,
            "channel": r.channel,
        }
        for r in rows
    ]


@router.get("/keyword-landscape")
async def keyword_landscape(
    industry_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Keywords: search volume vs CPC vs ad count (bubble chart data)."""
    q = select(
        Keyword.id,
        Keyword.keyword,
        Keyword.monthly_search_vol,
        Keyword.naver_cpc,
        Keyword.industry_id,
    ).where(
        and_(
            Keyword.is_active == True,
            Keyword.monthly_search_vol.isnot(None),
            Keyword.monthly_search_vol > 0,
        )
    )
    if industry_id:
        q = q.where(Keyword.industry_id == industry_id)

    keywords = (await db.execute(q)).all()

    # Count ads per keyword
    kw_ids = [k.id for k in keywords]
    ad_counts: dict[int, int] = {}
    if kw_ids:
        count_rows = (
            await db.execute(
                select(
                    AdSnapshot.keyword_id,
                    func.count(AdDetail.id).label("cnt"),
                )
                .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
                .where(AdSnapshot.keyword_id.in_(kw_ids))
                .group_by(AdSnapshot.keyword_id)
            )
        ).all()
        ad_counts = {r.keyword_id: r.cnt for r in count_rows}

    return [
        {
            "keyword": k.keyword,
            "search_vol": k.monthly_search_vol,
            "cpc": k.naver_cpc or 0,
            "ad_count": ad_counts.get(k.id, 0),
        }
        for k in keywords
    ]


@router.get("/category-heatmap")
async def category_heatmap(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Industry x Product Category ad concentration grid."""
    cutoff = datetime.now(KST).replace(tzinfo=None) - timedelta(days=days)

    rows = (
        await db.execute(
            select(
                Industry.name.label("industry"),
                ProductCategory.name.label("category"),
                func.count(AdDetail.id).label("ad_count"),
                func.count(func.distinct(AdDetail.advertiser_id)).label("advertiser_count"),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .join(Advertiser, Advertiser.id == AdDetail.advertiser_id)
            .join(Industry, Industry.id == Advertiser.industry_id)
            .join(ProductCategory, ProductCategory.id == AdDetail.product_category_id)
            .where(AdSnapshot.captured_at >= cutoff)
            .group_by(Industry.name, ProductCategory.name)
            .order_by(func.count(AdDetail.id).desc())
            .limit(100)
        )
    ).all()

    return [
        {
            "industry": r.industry,
            "category": r.category,
            "ad_count": r.ad_count,
            "advertiser_count": r.advertiser_count,
        }
        for r in rows
    ]
