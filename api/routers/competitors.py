"""Competitor auto-mapping API router.

Provides:
  GET /api/competitors/{advertiser_id}          - affinity scores
  GET /api/competitors/{advertiser_id}/keywords - keyword reverse lookup
"""

import re
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_current_user, require_paid
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.models import AdDetail, AdSnapshot, Advertiser, Industry, Keyword
from database.schemas import (
    CompetitorListOut,
    CompetitorScoreOut,
)
from processor.competitor_mapper import calculate_competitor_affinity

router = APIRouter(prefix="/api/competitors", tags=["competitors"])


_CHANNEL_LABELS = {
    "naver_search": "네이버 검색",
    "naver_da": "네이버 DA",
    "naver_shopping": "네이버 쇼핑",
    "kakao_da": "카카오 DA",
    "google_gdn": "구글 GDN",
    "google_search": "구글 검색",
    "youtube_ads": "유튜브",
    "meta_library": "메타",
    "tiktok_ads": "틱톡",
}

_MESSAGE_MARKERS = (
    "할인",
    "특가",
    "쿠폰",
    "무료배송",
    "이벤트",
    "혜택",
    "최대",
    "단독",
    "공식",
    "신규",
    "런칭",
    "출시",
    "사전예약",
    "렌탈",
    "정기배송",
    "추천",
    "오늘",
    "선착순",
)

_MESSAGE_STOPWORDS = {
    "광고",
    "검색",
    "상품",
    "구매",
    "자세히",
    "더보기",
    "바로가기",
    "naver",
    "http",
    "https",
    "www",
    "com",
}


async def _target_advertiser_ids(
    db: AsyncSession,
    advertiser_id: int,
    include_children: bool,
) -> set[int]:
    target_ids = {advertiser_id}
    if include_children:
        children_result = await db.execute(
            select(Advertiser.id).where(Advertiser.parent_id == advertiser_id)
        )
        target_ids.update(row[0] for row in children_result.all())
    return target_ids


def _live_ad_filter():
    return or_(
        AdDetail.verification_status.is_(None),
        AdDetail.verification_status != "rejected",
    )


def _channel_label(channel: str | None) -> str:
    if not channel:
        return "-"
    return _CHANNEL_LABELS.get(channel, channel)


def _message_terms(rows) -> list[dict]:
    marker_counts: Counter[str] = Counter()
    fallback_counts: Counter[str] = Counter()

    for row in rows:
        text = " ".join(str(part or "") for part in row).strip()
        if not text:
            continue
        lower_text = text.lower()
        for marker in _MESSAGE_MARKERS:
            if marker in text:
                marker_counts[marker] += 1
        for token in re.findall(r"[가-힣A-Za-z0-9]{2,12}", lower_text):
            if token in _MESSAGE_STOPWORDS or token.isdigit():
                continue
            fallback_counts[token] += 1

    if marker_counts:
        return [
            {"term": term, "count": count}
            for term, count in marker_counts.most_common(12)
        ]

    terms = []
    for term, count in fallback_counts.most_common(20):
        if len(terms) >= 12:
            break
        if any(item["term"] == term for item in terms):
            continue
        terms.append({"term": term, "count": count})

    return terms


@router.get("/{advertiser_id}", response_model=CompetitorListOut)
async def get_competitors(
    advertiser_id: int,
    days: int = Query(default=30, le=365),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Return competitor affinity scores for a given advertiser.

    Ranks candidates by composite affinity across keyword overlap,
    channel overlap, position zone similarity, spend similarity,
    and co-occurrence count.
    """
    target = await db.get(Advertiser, advertiser_id)
    if not target:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    scores = await calculate_competitor_affinity(
        db, advertiser_id=advertiser_id, days=days, limit=limit
    )

    industry_name: str | None = None
    if target.industry_id:
        industry = await db.get(Industry, target.industry_id)
        industry_name = industry.name if industry else None

    return CompetitorListOut(
        target_id=target.id,
        target_name=target.name,
        industry_id=target.industry_id,
        industry_name=industry_name,
        competitors=[
            CompetitorScoreOut(
                competitor_id=s.competitor_id,
                competitor_name=s.competitor_name,
                industry_id=s.industry_id,
                affinity_score=s.affinity_score,
                keyword_overlap=s.keyword_overlap,
                channel_overlap=s.channel_overlap,
                position_zone_overlap=s.position_zone_overlap,
                spend_similarity=s.spend_similarity,
                co_occurrence_count=s.co_occurrence_count,
            )
            for s in scores
        ],
    )


@router.get("/{advertiser_id}/simple-summary")
async def get_simple_competitive_summary(
    advertiser_id: int,
    days: int = Query(default=30, le=365),
    include_children: bool = Query(default=True),
    limit: int = Query(default=8, le=20),
    db: AsyncSession = Depends(get_db),
):
    """수집된 광고 데이터만으로 광고주 경쟁 상황을 짧게 요약."""
    target = await db.get(Advertiser, advertiser_id)
    if not target:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    target_ids = await _target_advertiser_ids(db, advertiser_id, include_children)
    target_id_list = list(target_ids)
    cutoff = datetime.utcnow() - timedelta(days=days)

    target_keyword_subq = (
        select(AdSnapshot.keyword_id)
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(target_id_list))
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdSnapshot.keyword_id.isnot(None))
        .where(_live_ad_filter())
        .distinct()
        .subquery()
    )

    keyword_rows = (
        await db.execute(
            select(
                Keyword.id.label("keyword_id"),
                Keyword.keyword,
                AdSnapshot.channel,
                func.count(AdDetail.id).label("ad_count"),
                func.min(AdSnapshot.captured_at).label("first_seen"),
                func.max(AdSnapshot.captured_at).label("last_seen"),
            )
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
            .where(AdDetail.advertiser_id.in_(target_id_list))
            .where(AdSnapshot.captured_at >= cutoff)
            .where(Keyword.keyword.isnot(None))
            .where(Keyword.keyword != "")
            .where(_live_ad_filter())
            .group_by(Keyword.id, Keyword.keyword, AdSnapshot.channel)
            .order_by(func.count(AdDetail.id).desc(), func.max(AdSnapshot.captured_at).desc())
            .limit(500)
        )
    ).all()

    keyword_map: dict[int, dict] = {}
    for row in keyword_rows:
        item = keyword_map.setdefault(
            row.keyword_id,
            {
                "keyword_id": row.keyword_id,
                "keyword": row.keyword,
                "channels": [],
                "ad_count": 0,
                "first_seen": row.first_seen.strftime("%Y-%m-%d") if row.first_seen else None,
                "last_seen": row.last_seen.strftime("%Y-%m-%d") if row.last_seen else None,
            },
        )
        if row.channel and row.channel not in item["channels"]:
            item["channels"].append(row.channel)
        item["ad_count"] += int(row.ad_count or 0)
        if row.first_seen:
            first_seen = row.first_seen.strftime("%Y-%m-%d")
            if not item["first_seen"] or first_seen < item["first_seen"]:
                item["first_seen"] = first_seen
        if row.last_seen:
            last_seen = row.last_seen.strftime("%Y-%m-%d")
            if not item["last_seen"] or last_seen > item["last_seen"]:
                item["last_seen"] = last_seen

    top_keywords = sorted(
        keyword_map.values(),
        key=lambda item: (item["ad_count"], item["last_seen"] or ""),
        reverse=True,
    )[:12]

    channel_rows = (
        await db.execute(
            select(
                AdSnapshot.channel,
                func.count(AdDetail.id).label("ad_count"),
                func.max(AdSnapshot.captured_at).label("last_seen"),
            )
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdDetail.advertiser_id.in_(target_id_list))
            .where(AdSnapshot.captured_at >= cutoff)
            .where(_live_ad_filter())
            .group_by(AdSnapshot.channel)
            .order_by(func.count(AdDetail.id).desc())
        )
    ).all()
    total_ads = sum(int(row.ad_count or 0) for row in channel_rows)
    channel_mix = [
        {
            "channel": row.channel,
            "channel_label": _channel_label(row.channel),
            "ad_count": int(row.ad_count or 0),
            "share": round((int(row.ad_count or 0) / total_ads) * 100, 1) if total_ads else 0.0,
            "last_seen": row.last_seen.strftime("%Y-%m-%d") if row.last_seen else None,
        }
        for row in channel_rows
    ]

    competitor_rows = (
        await db.execute(
            select(
                Advertiser.id.label("competitor_id"),
                Advertiser.name.label("competitor_name"),
                func.count(AdDetail.id).label("ad_count"),
                func.count(func.distinct(AdSnapshot.keyword_id)).label("shared_keyword_count"),
                func.max(AdSnapshot.captured_at).label("last_seen"),
            )
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .join(Advertiser, AdDetail.advertiser_id == Advertiser.id)
            .where(AdSnapshot.keyword_id.in_(select(target_keyword_subq.c.keyword_id)))
            .where(AdDetail.advertiser_id.isnot(None))
            .where(AdDetail.advertiser_id.notin_(target_id_list))
            .where(AdSnapshot.captured_at >= cutoff)
            .where(_live_ad_filter())
            .group_by(Advertiser.id, Advertiser.name)
            .order_by(func.count(AdDetail.id).desc(), func.count(func.distinct(AdSnapshot.keyword_id)).desc())
            .limit(limit)
        )
    ).all()

    competitor_ids = [row.competitor_id for row in competitor_rows]
    shared_keyword_map: dict[int, list[str]] = {cid: [] for cid in competitor_ids}
    if competitor_ids:
        shared_keyword_rows = (
            await db.execute(
                select(
                    AdDetail.advertiser_id.label("competitor_id"),
                    Keyword.keyword,
                    func.count(AdDetail.id).label("ad_count"),
                )
                .select_from(AdDetail)
                .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
                .where(AdDetail.advertiser_id.in_(competitor_ids))
                .where(AdSnapshot.keyword_id.in_(select(target_keyword_subq.c.keyword_id)))
                .where(AdSnapshot.captured_at >= cutoff)
                .where(Keyword.keyword.isnot(None))
                .where(Keyword.keyword != "")
                .where(_live_ad_filter())
                .group_by(AdDetail.advertiser_id, Keyword.keyword)
                .order_by(AdDetail.advertiser_id, func.count(AdDetail.id).desc())
            )
        ).all()
        for row in shared_keyword_rows:
            terms = shared_keyword_map.setdefault(row.competitor_id, [])
            if len(terms) < 3 and row.keyword not in terms:
                terms.append(row.keyword)

    top_competitors = [
        {
            "advertiser_id": row.competitor_id,
            "advertiser_name": row.competitor_name,
            "ad_count": int(row.ad_count or 0),
            "shared_keyword_count": int(row.shared_keyword_count or 0),
            "shared_keywords": shared_keyword_map.get(row.competitor_id, []),
            "last_seen": row.last_seen.strftime("%Y-%m-%d") if row.last_seen else None,
            "note": (
                f"{', '.join(shared_keyword_map.get(row.competitor_id, [])[:2])}에서 같이 보임"
                if shared_keyword_map.get(row.competitor_id)
                else f"{int(row.shared_keyword_count or 0)}개 키워드에서 겹침"
            ),
        }
        for row in competitor_rows
    ]

    message_rows = (
        await db.execute(
            select(
                AdDetail.ad_text,
                AdDetail.ad_description,
                AdDetail.product_name,
                AdDetail.promotion_type,
            )
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdDetail.advertiser_id.in_(target_id_list))
            .where(AdSnapshot.captured_at >= cutoff)
            .where(_live_ad_filter())
            .order_by(AdSnapshot.captured_at.desc())
            .limit(500)
        )
    ).all()
    message_terms = _message_terms(message_rows)

    quick_reads: list[str] = []
    if top_keywords:
        names = ", ".join(item["keyword"] for item in top_keywords[:3])
        quick_reads.append(f"키워드는 {names} 쪽에 많이 걸려 있습니다.")
    if top_competitors:
        names = ", ".join(item["advertiser_name"] for item in top_competitors[:3])
        quick_reads.append(f"같은 키워드에서 {names}가 자주 같이 보입니다.")
    if channel_mix:
        top_channel = channel_mix[0]
        quick_reads.append(
            f"채널은 {top_channel['channel_label']} 비중이 가장 큽니다."
        )
    if message_terms:
        terms = ", ".join(item["term"] for item in message_terms[:3])
        quick_reads.append(f"소재 문구는 {terms} 톤이 자주 보입니다.")
    if not quick_reads:
        quick_reads.append(f"최근 {days}일 수집 데이터가 아직 부족합니다.")

    headline_bits = []
    if top_keywords:
        headline_bits.append(f"{top_keywords[0]['keyword']} 중심")
    if channel_mix:
        headline_bits.append(f"{channel_mix[0]['channel_label']} 강세")
    if top_competitors:
        headline_bits.append(f"{top_competitors[0]['advertiser_name']}와 자주 겹침")
    headline = " · ".join(headline_bits) if headline_bits else "아직 읽을 데이터가 적습니다"

    return {
        "advertiser_id": advertiser_id,
        "advertiser_name": target.name,
        "included_advertiser_ids": sorted(target_ids),
        "period_days": days,
        "data_basis": "수집 광고 기준",
        "headline": headline,
        "quick_reads": quick_reads,
        "top_keywords": top_keywords,
        "top_competitors": top_competitors,
        "channel_mix": channel_mix,
        "message_terms": message_terms,
    }


@router.get("/{advertiser_id}/keywords")
async def get_advertiser_keywords(
    advertiser_id: int,
    days: int = Query(default=30, le=365),
    channel: str | None = None,
    include_children: bool = Query(default=True),
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """광고주의 키워드 역추적 — 어떤 키워드에 광고가 노출되었는지 반환."""
    target = await db.get(Advertiser, advertiser_id)
    if not target:
        raise HTTPException(status_code=404, detail="Advertiser not found")

    target_ids = await _target_advertiser_ids(db, advertiser_id, include_children)

    cutoff = datetime.utcnow() - timedelta(days=days)

    q = (
        select(
            Keyword.id.label("keyword_id"),
            Keyword.keyword,
            Keyword.monthly_search_vol,
            Keyword.naver_cpc,
            AdSnapshot.channel,
            func.count(AdDetail.id).label("impression_count"),
            func.min(AdSnapshot.captured_at).label("first_seen"),
            func.max(AdSnapshot.captured_at).label("last_seen"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Keyword, AdSnapshot.keyword_id == Keyword.id)
        .where(AdDetail.advertiser_id.in_(list(target_ids)))
        .where(AdSnapshot.captured_at >= cutoff)
        .where(Keyword.keyword.isnot(None))
        .where(Keyword.keyword != "")
        .where(
            (AdDetail.verification_status.is_(None))
            | (AdDetail.verification_status != "rejected")
        )
    )
    if channel:
        q = q.where(AdSnapshot.channel == channel)

    q = (
        q.group_by(
            Keyword.id,
            Keyword.keyword,
            Keyword.monthly_search_vol,
            Keyword.naver_cpc,
            AdSnapshot.channel,
        )
        .order_by(
            func.count(AdDetail.id).desc(),
            func.max(AdSnapshot.captured_at).desc(),
        )
        .limit(limit if channel else min(limit * 8, 1000))
    )

    rows = (await db.execute(q)).all()

    # 키워드별로 채널 합치기
    kw_map: dict[int, dict] = {}
    for r in rows:
        kid = r.keyword_id
        if kid not in kw_map:
            kw_map[kid] = {
                "keyword_id": kid,
                "keyword": r.keyword,
                "monthly_search_vol": r.monthly_search_vol,
                "naver_cpc": r.naver_cpc,
                "channels": [],
                "impression_count": 0,
                "first_seen": r.first_seen.strftime("%Y-%m-%d") if r.first_seen else None,
                "last_seen": r.last_seen.strftime("%Y-%m-%d") if r.last_seen else None,
            }
        kw_map[kid]["channels"].append(r.channel)
        kw_map[kid]["impression_count"] += r.impression_count
        # 날짜 갱신
        if r.first_seen:
            fs = r.first_seen.strftime("%Y-%m-%d")
            if not kw_map[kid]["first_seen"] or fs < kw_map[kid]["first_seen"]:
                kw_map[kid]["first_seen"] = fs
        if r.last_seen:
            ls = r.last_seen.strftime("%Y-%m-%d")
            if not kw_map[kid]["last_seen"] or ls > kw_map[kid]["last_seen"]:
                kw_map[kid]["last_seen"] = ls

    keywords = sorted(
        kw_map.values(),
        key=lambda x: (x["impression_count"], x["last_seen"] or ""),
        reverse=True,
    )[:limit]

    return {
        "advertiser_id": advertiser_id,
        "advertiser_name": target.name,
        "included_advertiser_ids": sorted(target_ids),
        "keywords": keywords,
    }
