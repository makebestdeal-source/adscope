"""경쟁사 대비 윈도우 점유율(SOV) 분석.

SOV (Share of Voice) = (특정 광고주 광고 노출 수) / (전체 광고 노출 수)
관측 윈도우(시간 구간) 내에서 광고주별 점유율 계산.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AdDetail, AdSnapshot, Advertiser, Campaign, Keyword, Persona


@dataclass
class SOVResult:
    """광고주별 윈도우 점유율."""

    advertiser_name: str
    advertiser_id: int
    channel: str
    total_impressions: int
    total_market_impressions: int
    sov_percentage: float
    position_sov: dict[str, float] = field(default_factory=dict)


@dataclass
class SOVTrendPoint:
    """SOV 일별 추이 데이터 포인트."""

    date: str
    advertiser_name: str
    advertiser_id: int
    sov_percentage: float


async def calculate_sov(
    db: AsyncSession,
    keyword: str | None = None,
    industry_id: int | None = None,
    channel: str | None = None,
    days: int = 30,
    limit: int = 20,
) -> list[SOVResult]:
    """키워드/업종에서 광고주별 점유율 계산.

    로직:
    1. ad_snapshots에서 해당 키워드/업종의 전체 광고 수집
    2. advertiser별 그룹핑
    3. 전체 대비 비율 계산
    4. 위치별(top/middle/bottom) 세부 SOV도 함께 계산
    """
    since = datetime.utcnow() - timedelta(days=days)

    # 전체 시장 노출 수
    total_q = (
        select(func.count(AdDetail.id).label("total"))
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at >= since)
        .where(AdDetail.is_inhouse == False)  # noqa: E712
    )
    if channel:
        total_q = total_q.where(AdSnapshot.channel == channel)
    if keyword:
        total_q = total_q.join(Keyword, AdSnapshot.keyword_id == Keyword.id).where(
            Keyword.keyword == keyword
        )
    if industry_id:
        total_q = total_q.join(Keyword, AdSnapshot.keyword_id == Keyword.id).where(
            Keyword.industry_id == industry_id
        )

    total_result = await db.execute(total_q)
    total_market = total_result.scalar() or 0

    if total_market == 0:
        return []

    # 광고주별 노출 수
    adv_q = (
        select(
            Advertiser.name,
            Advertiser.id.label("advertiser_id"),
            AdSnapshot.channel,
            func.count(AdDetail.id).label("impressions"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Advertiser, AdDetail.advertiser_id == Advertiser.id)
        .where(AdSnapshot.captured_at >= since)
        .where(AdDetail.is_inhouse == False)  # noqa: E712
    )
    if channel:
        adv_q = adv_q.where(AdSnapshot.channel == channel)
    if keyword:
        adv_q = adv_q.join(Keyword, AdSnapshot.keyword_id == Keyword.id).where(
            Keyword.keyword == keyword
        )
    if industry_id:
        adv_q = adv_q.join(Keyword, AdSnapshot.keyword_id == Keyword.id).where(
            Keyword.industry_id == industry_id
        )

    adv_q = (
        adv_q.group_by(Advertiser.name, Advertiser.id, AdSnapshot.channel)
        .order_by(func.count(AdDetail.id).desc())
        .limit(limit)
    )

    adv_result = await db.execute(adv_q)
    rows = adv_result.all()

    results: list[SOVResult] = []
    for row in rows:
        # 위치별 SOV
        pos_q = (
            select(
                AdDetail.position_zone,
                func.count(AdDetail.id).label("cnt"),
            )
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdSnapshot.captured_at >= since)
            .where(AdDetail.advertiser_id == row.advertiser_id)
            .where(AdDetail.position_zone.isnot(None))
        )
        if channel:
            pos_q = pos_q.where(AdSnapshot.channel == channel)

        pos_q = pos_q.group_by(AdDetail.position_zone)
        pos_result = await db.execute(pos_q)

        # 위치별 점유율: 해당 광고주의 위치별 노출 / 전체 시장 노출
        position_sov = {}
        for pr in pos_result.all():
            if pr.position_zone:
                position_sov[pr.position_zone] = round(
                    pr.cnt / total_market * 100, 2
                )

        results.append(
            SOVResult(
                advertiser_name=row.name,
                advertiser_id=row.advertiser_id,
                channel=row.channel,
                total_impressions=row.impressions,
                total_market_impressions=total_market,
                sov_percentage=round(row.impressions / total_market * 100, 2),
                position_sov=position_sov,
            )
        )

    return results


async def calculate_competitive_sov(
    db: AsyncSession,
    advertiser_id: int,
    days: int = 30,
) -> dict:
    """특정 광고주의 경쟁사 대비 점유율.

    같은 업종 내 경쟁사 자동 매칭 → 채널별·연령대별 점유율 비교.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # 대상 광고주 정보
    adv = await db.get(Advertiser, advertiser_id)
    if not adv:
        return {"error": "Advertiser not found"}

    # 같은 업종 광고주 목록
    if adv.industry_id:
        competitors_q = select(Advertiser.id).where(
            Advertiser.industry_id == adv.industry_id,
            Advertiser.id != advertiser_id,
        )
        comp_result = await db.execute(competitors_q)
        competitor_ids = [r[0] for r in comp_result.all()]
    else:
        # 업종 없으면 같은 키워드에서 경쟁하는 광고주
        kw_q = (
            select(func.distinct(AdSnapshot.keyword_id))
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdDetail.advertiser_id == advertiser_id)
            .where(AdSnapshot.captured_at >= since)
        )
        kw_result = await db.execute(kw_q)
        keyword_ids = [r[0] for r in kw_result.all()]

        if keyword_ids:
            comp_q = (
                select(func.distinct(AdDetail.advertiser_id))
                .select_from(AdDetail)
                .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                .where(AdSnapshot.keyword_id.in_(keyword_ids))
                .where(AdDetail.advertiser_id != advertiser_id)
                .where(AdDetail.advertiser_id.isnot(None))
                .where(AdSnapshot.captured_at >= since)
            )
            comp_result = await db.execute(comp_q)
            competitor_ids = [r[0] for r in comp_result.all()]
        else:
            competitor_ids = []

    all_ids = [advertiser_id] + competitor_ids[:19]  # 최대 20개

    # 전체 노출 수 (대상 + 경쟁사)
    total_q = (
        select(func.count(AdDetail.id))
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdDetail.advertiser_id.in_(all_ids))
        .where(AdSnapshot.captured_at >= since)
    )
    total_market = (await db.execute(total_q)).scalar() or 1

    # 광고주별 채널별 노출
    by_channel_q = (
        select(
            AdDetail.advertiser_id,
            Advertiser.name,
            AdSnapshot.channel,
            func.count(AdDetail.id).label("impressions"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Advertiser, AdDetail.advertiser_id == Advertiser.id)
        .where(AdDetail.advertiser_id.in_(all_ids))
        .where(AdSnapshot.captured_at >= since)
        .group_by(AdDetail.advertiser_id, Advertiser.name, AdSnapshot.channel)
    )
    ch_result = await db.execute(by_channel_q)
    ch_rows = ch_result.all()

    # 채널별 구조화
    by_channel: dict[str, dict] = {}
    adv_totals: dict[int, int] = {}
    adv_names: dict[int, str] = {}

    for row in ch_rows:
        adv_names[row.advertiser_id] = row.name
        adv_totals[row.advertiser_id] = (
            adv_totals.get(row.advertiser_id, 0) + row.impressions
        )

        ch = row.channel
        if ch not in by_channel:
            by_channel[ch] = {}
        by_channel[ch][row.advertiser_id] = {
            "name": row.name,
            "impressions": row.impressions,
        }

    # 채널별 SOV 계산
    by_channel_sov: dict[str, dict] = {}
    for ch, advertisers in by_channel.items():
        ch_total = sum(a["impressions"] for a in advertisers.values())
        ch_sov = {}
        for aid, data in advertisers.items():
            ch_sov[data["name"]] = round(data["impressions"] / max(ch_total, 1) * 100, 2)
        by_channel_sov[ch] = ch_sov

    # 연령대별 SOV
    by_age_q = (
        select(
            AdDetail.advertiser_id,
            Persona.age_group,
            func.count(AdDetail.id).label("impressions"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdDetail.advertiser_id.in_(all_ids))
        .where(AdSnapshot.captured_at >= since)
        .where(Persona.age_group.isnot(None))
        .group_by(AdDetail.advertiser_id, Persona.age_group)
    )
    age_result = await db.execute(by_age_q)
    age_rows = age_result.all()

    by_age: dict[str, dict] = {}
    for row in age_rows:
        ag = row.age_group
        if ag not in by_age:
            by_age[ag] = {}
        by_age[ag][row.advertiser_id] = row.impressions

    by_age_sov: dict[str, dict] = {}
    for ag, advertisers in by_age.items():
        ag_total = sum(advertisers.values())
        ag_sov = {}
        for aid, imp in advertisers.items():
            name = adv_names.get(aid, str(aid))
            ag_sov[name] = round(imp / max(ag_total, 1) * 100, 2)
        by_age_sov[ag] = ag_sov

    # 결과 구성
    target_total = adv_totals.get(advertiser_id, 0)
    target_sov = round(target_total / total_market * 100, 2)

    competitors_list = []
    for cid in competitor_ids[:19]:
        if cid in adv_totals:
            competitors_list.append(
                {
                    "advertiser_id": cid,
                    "name": adv_names.get(cid, ""),
                    "sov_percentage": round(
                        adv_totals[cid] / total_market * 100, 2
                    ),
                    "total_impressions": adv_totals[cid],
                }
            )
    competitors_list.sort(key=lambda x: x["sov_percentage"], reverse=True)

    return {
        "target": {
            "advertiser_id": advertiser_id,
            "name": adv.name,
            "sov_percentage": target_sov,
            "total_impressions": target_total,
        },
        "competitors": competitors_list,
        "by_channel": by_channel_sov,
        "by_age_group": by_age_sov,
    }


async def calculate_sov_trend(
    db: AsyncSession,
    advertiser_id: int,
    competitor_ids: list[int] | None = None,
    days: int = 30,
) -> list[SOVTrendPoint]:
    """SOV 일별 추이 — 광고주 vs 경쟁사."""
    since = datetime.utcnow() - timedelta(days=days)

    all_ids = [advertiser_id]
    if competitor_ids:
        all_ids.extend(competitor_ids)

    q = (
        select(
            func.date(AdSnapshot.captured_at).label("date"),
            AdDetail.advertiser_id,
            Advertiser.name,
            func.count(AdDetail.id).label("impressions"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Advertiser, AdDetail.advertiser_id == Advertiser.id)
        .where(AdDetail.advertiser_id.in_(all_ids))
        .where(AdSnapshot.captured_at >= since)
        .group_by(
            func.date(AdSnapshot.captured_at),
            AdDetail.advertiser_id,
            Advertiser.name,
        )
        .order_by(func.date(AdSnapshot.captured_at))
    )

    result = await db.execute(q)
    rows = result.all()

    # 일별 전체 노출 계산
    daily_totals: dict[str, int] = {}
    for row in rows:
        d = str(row.date)
        daily_totals[d] = daily_totals.get(d, 0) + row.impressions

    return [
        SOVTrendPoint(
            date=str(row.date),
            advertiser_name=row.name,
            advertiser_id=row.advertiser_id,
            sov_percentage=round(
                row.impressions / max(daily_totals.get(str(row.date), 1), 1) * 100, 2
            ),
        )
        for row in rows
    ]
