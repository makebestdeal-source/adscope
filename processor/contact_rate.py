"""광고 접촉율 분석 — 연령대별·채널별·광고주별 광고 노출 빈도 측정.

접촉율 = (광고 노출 건수) / (수집 세션 수)
→ 세션당 평균 몇 건의 광고에 노출되는지 분석.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AdDetail, AdSnapshot, Persona


@dataclass
class ContactRateResult:
    """연령대별 광고 접촉율 분석 결과."""

    age_group: str
    gender: str
    channel: str
    total_sessions: int
    total_ad_impressions: int
    contact_rate: float  # 세션당 평균 광고 수
    unique_advertisers: int
    avg_ads_per_session: float
    top_ad_types: dict[str, int] = field(default_factory=dict)
    position_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class ContactRateTrendPoint:
    """접촉율 시계열 데이터 포인트."""

    date: str
    age_group: str
    gender: str
    contact_rate: float


async def calculate_contact_rates(
    db: AsyncSession,
    days: int = 30,
    channel: str | None = None,
    age_group: str | None = None,
) -> list[ContactRateResult]:
    """연령대×성별 × 채널 광고 접촉율 계산.

    로직:
    1. personas 테이블에서 age_group, gender 조회
    2. ad_snapshots에서 해당 persona의 세션 수 집계
    3. ad_details에서 광고 노출 건수 집계
    4. contact_rate = ad_impressions / sessions
    """
    since = datetime.utcnow() - timedelta(days=days)

    # 기본 조인: snapshots ↔ personas ↔ details (접촉 데이터만)
    base_q = (
        select(
            Persona.age_group,
            Persona.gender,
            AdSnapshot.channel,
            func.count(func.distinct(AdSnapshot.id)).label("total_sessions"),
            func.count(AdDetail.id).label("total_ad_impressions"),
            func.count(func.distinct(AdDetail.advertiser_id)).label(
                "unique_advertisers"
            ),
        )
        .select_from(AdSnapshot)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at >= since)
        .where(Persona.age_group.isnot(None))
        .where(AdDetail.is_contact == True)
    )

    if channel:
        base_q = base_q.where(AdSnapshot.channel == channel)
    if age_group:
        base_q = base_q.where(Persona.age_group == age_group)

    base_q = base_q.group_by(Persona.age_group, Persona.gender, AdSnapshot.channel)

    result = await db.execute(base_q)
    rows = result.all()

    results: list[ContactRateResult] = []
    for row in rows:
        sessions = row.total_sessions or 1
        impressions = row.total_ad_impressions or 0

        # 위치 분포 조회
        position_q = (
            select(
                AdDetail.position_zone,
                func.count(AdDetail.id).label("cnt"),
            )
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .join(Persona, AdSnapshot.persona_id == Persona.id)
            .where(AdSnapshot.captured_at >= since)
            .where(Persona.age_group == row.age_group)
            .where(Persona.gender == row.gender)
            .where(AdSnapshot.channel == row.channel)
            .where(AdDetail.position_zone.isnot(None))
            .where(AdDetail.is_contact == True)
            .group_by(AdDetail.position_zone)
        )
        pos_result = await db.execute(position_q)
        position_dist = {r.position_zone: r.cnt for r in pos_result.all()}

        # 광고 유형 분포 조회
        type_q = (
            select(
                AdDetail.ad_type,
                func.count(AdDetail.id).label("cnt"),
            )
            .select_from(AdDetail)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .join(Persona, AdSnapshot.persona_id == Persona.id)
            .where(AdSnapshot.captured_at >= since)
            .where(Persona.age_group == row.age_group)
            .where(Persona.gender == row.gender)
            .where(AdSnapshot.channel == row.channel)
            .where(AdDetail.ad_type.isnot(None))
            .where(AdDetail.is_contact == True)
            .group_by(AdDetail.ad_type)
        )
        type_result = await db.execute(type_q)
        ad_types = {r.ad_type: r.cnt for r in type_result.all()}

        results.append(
            ContactRateResult(
                age_group=row.age_group,
                gender=row.gender,
                channel=row.channel,
                total_sessions=sessions,
                total_ad_impressions=impressions,
                contact_rate=round(impressions / sessions, 2),
                unique_advertisers=row.unique_advertisers or 0,
                avg_ads_per_session=round(impressions / sessions, 2),
                top_ad_types=ad_types,
                position_distribution=position_dist,
            )
        )

    return results


async def calculate_contact_rate_trend(
    db: AsyncSession,
    days: int = 30,
    channel: str | None = None,
    age_group: str | None = None,
) -> list[ContactRateTrendPoint]:
    """광고 접촉율 일별 추이."""
    since = datetime.utcnow() - timedelta(days=days)

    q = (
        select(
            func.date(AdSnapshot.captured_at).label("date"),
            Persona.age_group,
            Persona.gender,
            func.count(func.distinct(AdSnapshot.id)).label("sessions"),
            func.count(AdDetail.id).label("impressions"),
        )
        .select_from(AdSnapshot)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .join(AdDetail, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at >= since)
        .where(Persona.age_group.isnot(None))
        .where(AdDetail.is_contact == True)
    )

    if channel:
        q = q.where(AdSnapshot.channel == channel)
    if age_group:
        q = q.where(Persona.age_group == age_group)

    q = q.group_by(
        func.date(AdSnapshot.captured_at), Persona.age_group, Persona.gender
    ).order_by(func.date(AdSnapshot.captured_at))

    result = await db.execute(q)
    return [
        ContactRateTrendPoint(
            date=str(row.date),
            age_group=row.age_group,
            gender=row.gender,
            contact_rate=round((row.impressions or 0) / max(row.sessions, 1), 2),
        )
        for row in result.all()
    ]


async def compare_advertiser_contact_rates(
    db: AsyncSession,
    advertiser_id: int,
    days: int = 30,
) -> list[dict]:
    """특정 광고주의 연령대별 접촉율 비교.

    → 해당 광고주가 어느 연령대에 가장 많이 노출되는지 분석.
    """
    since = datetime.utcnow() - timedelta(days=days)

    q = (
        select(
            Persona.age_group,
            Persona.gender,
            AdSnapshot.channel,
            func.count(func.distinct(AdSnapshot.id)).label("sessions"),
            func.count(AdDetail.id).label("impressions"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdDetail.advertiser_id == advertiser_id)
        .where(AdSnapshot.captured_at >= since)
        .where(Persona.age_group.isnot(None))
        .group_by(Persona.age_group, Persona.gender, AdSnapshot.channel)
    )

    result = await db.execute(q)
    return [
        {
            "age_group": row.age_group,
            "gender": row.gender,
            "channel": row.channel,
            "sessions_with_ad": row.sessions,
            "ad_impressions": row.impressions,
            "avg_per_session": round(
                (row.impressions or 0) / max(row.sessions, 1), 2
            ),
        }
        for row in result.all()
    ]
