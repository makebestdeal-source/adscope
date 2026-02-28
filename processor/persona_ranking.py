"""Per-Persona Ad Ranking -- advertiser ranking per persona profile.

Analyzes which advertisers target each persona (age/gender) most heavily,
generates heatmap data for persona x advertiser matrix, and daily trends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select, distinct, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AdDetail, AdSnapshot, Persona


# ── Dataclasses ──


@dataclass
class PersonaAdvertiserRank:
    """Single row: one advertiser's ranking within one persona."""

    persona_code: str
    age_group: str | None
    gender: str | None
    advertiser_name: str
    advertiser_id: int | None
    impression_count: int
    session_count: int
    avg_per_session: float
    channels: list[str] = field(default_factory=list)
    rank: int = 0


@dataclass
class PersonaHeatmapCell:
    """Single cell in the persona x advertiser heatmap matrix."""

    persona_code: str
    age_group: str | None
    gender: str | None
    advertiser_name: str
    advertiser_id: int | None
    impression_count: int
    intensity: float  # 0.0 ~ 1.0


# ── Core Functions ──


async def calculate_persona_advertiser_ranking(
    db: AsyncSession,
    persona_code: str | None = None,
    days: int = 30,
    channel: str | None = None,
    limit: int = 20,
) -> list[PersonaAdvertiserRank]:
    """Rank advertisers per persona by impression count.

    JOIN: ad_details -> ad_snapshots -> personas
    GROUP BY: persona.code, age_group, gender, advertiser_name_raw, advertiser_id
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Main aggregation query
    q = (
        select(
            Persona.code.label("persona_code"),
            Persona.age_group,
            Persona.gender,
            AdDetail.advertiser_name_raw.label("advertiser_name"),
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("impression_count"),
            func.count(distinct(AdSnapshot.id)).label("session_count"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.advertiser_name_raw.isnot(None))
        .where(AdDetail.advertiser_name_raw != "")
    )

    if persona_code:
        q = q.where(Persona.code == persona_code)
    if channel:
        q = q.where(AdSnapshot.channel == channel)

    q = q.group_by(
        Persona.code,
        Persona.age_group,
        Persona.gender,
        AdDetail.advertiser_name_raw,
        AdDetail.advertiser_id,
    )

    result = await db.execute(q)
    rows = result.all()

    # Build per-persona ranking
    persona_groups: dict[str, list] = {}
    for row in rows:
        code = row.persona_code
        if code not in persona_groups:
            persona_groups[code] = []
        sessions = max(row.session_count, 1)
        persona_groups[code].append(
            PersonaAdvertiserRank(
                persona_code=code,
                age_group=row.age_group,
                gender=row.gender,
                advertiser_name=row.advertiser_name,
                advertiser_id=row.advertiser_id,
                impression_count=row.impression_count,
                session_count=row.session_count,
                avg_per_session=round(row.impression_count / sessions, 2),
                channels=[],
                rank=0,
            )
        )

    # Sort each persona group by impression_count DESC, assign rank, truncate
    results: list[PersonaAdvertiserRank] = []
    for code, items in persona_groups.items():
        items.sort(key=lambda x: x.impression_count, reverse=True)
        for i, item in enumerate(items[:limit]):
            item.rank = i + 1
            results.append(item)

    # Fetch channel info for each advertiser per persona
    chan_q = (
        select(
            Persona.code.label("persona_code"),
            AdDetail.advertiser_name_raw.label("advertiser_name"),
            AdSnapshot.channel,
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.advertiser_name_raw.isnot(None))
        .where(AdDetail.advertiser_name_raw != "")
    )
    if persona_code:
        chan_q = chan_q.where(Persona.code == persona_code)
    if channel:
        chan_q = chan_q.where(AdSnapshot.channel == channel)

    chan_q = chan_q.group_by(
        Persona.code, AdDetail.advertiser_name_raw, AdSnapshot.channel
    )

    chan_result = await db.execute(chan_q)
    chan_rows = chan_result.all()

    # Build channel lookup: (persona_code, advertiser_name) -> [channels]
    chan_map: dict[tuple[str, str], list[str]] = {}
    for cr in chan_rows:
        key = (cr.persona_code, cr.advertiser_name)
        if key not in chan_map:
            chan_map[key] = []
        if cr.channel not in chan_map[key]:
            chan_map[key].append(cr.channel)

    for item in results:
        key = (item.persona_code, item.advertiser_name)
        item.channels = chan_map.get(key, [])

    return results


async def calculate_persona_heatmap(
    db: AsyncSession,
    days: int = 30,
    channel: str | None = None,
    top_advertisers: int = 15,
) -> list[PersonaHeatmapCell]:
    """Build persona x advertiser heatmap matrix.

    1. Find top N advertisers by total impressions across ALL personas.
    2. For each persona x advertiser pair, count impressions.
    3. Normalize intensity: max impressions = 1.0, others proportional.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Step 1: Find top N advertisers globally + per-persona top to ensure all ages covered
    top_q = (
        select(
            AdDetail.advertiser_name_raw.label("advertiser_name"),
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("total_impressions"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.advertiser_name_raw.isnot(None))
        .where(AdDetail.advertiser_name_raw != "")
    )
    if channel:
        top_q = top_q.where(AdSnapshot.channel == channel)

    top_q = (
        top_q.group_by(AdDetail.advertiser_name_raw, AdDetail.advertiser_id)
        .order_by(func.count(AdDetail.id).desc())
        .limit(top_advertisers)
    )

    top_result = await db.execute(top_q)
    top_rows = top_result.all()

    if not top_rows:
        return []

    top_names = list(dict.fromkeys(r.advertiser_name for r in top_rows))
    adv_id_map = {r.advertiser_name: r.advertiser_id for r in top_rows}

    # Also include top 3 advertisers PER PERSONA to ensure all age groups appear
    per_persona_q = (
        select(
            Persona.code.label("persona_code"),
            AdDetail.advertiser_name_raw.label("advertiser_name"),
            AdDetail.advertiser_id,
            func.count(AdDetail.id).label("cnt"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.advertiser_name_raw.isnot(None))
        .where(AdDetail.advertiser_name_raw != "")
    )
    if channel:
        per_persona_q = per_persona_q.where(AdSnapshot.channel == channel)

    per_persona_q = per_persona_q.group_by(
        Persona.code, AdDetail.advertiser_name_raw, AdDetail.advertiser_id
    ).order_by(func.count(AdDetail.id).desc())

    pp_result = await db.execute(per_persona_q)
    pp_rows = pp_result.all()

    # Pick top 3 per persona that aren't already in global top
    from collections import defaultdict
    per_persona_counts: dict[str, int] = defaultdict(int)
    for row in pp_rows:
        if row.advertiser_name not in top_names and per_persona_counts[row.persona_code] < 3:
            top_names.append(row.advertiser_name)
            adv_id_map[row.advertiser_name] = row.advertiser_id
            per_persona_counts[row.persona_code] += 1

    # Step 2: For each persona x advertiser, count impressions
    matrix_q = (
        select(
            Persona.code.label("persona_code"),
            Persona.age_group,
            Persona.gender,
            AdDetail.advertiser_name_raw.label("advertiser_name"),
            func.count(AdDetail.id).label("impression_count"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(AdDetail.advertiser_name_raw.in_(top_names))
    )
    if channel:
        matrix_q = matrix_q.where(AdSnapshot.channel == channel)

    matrix_q = matrix_q.group_by(
        Persona.code,
        Persona.age_group,
        Persona.gender,
        AdDetail.advertiser_name_raw,
    )

    matrix_result = await db.execute(matrix_q)
    matrix_rows = matrix_result.all()

    # Step 3: Normalize to 0.0 - 1.0
    max_impressions = max((r.impression_count for r in matrix_rows), default=1)
    if max_impressions == 0:
        max_impressions = 1

    cells: list[PersonaHeatmapCell] = []
    for row in matrix_rows:
        cells.append(
            PersonaHeatmapCell(
                persona_code=row.persona_code,
                age_group=row.age_group,
                gender=row.gender,
                advertiser_name=row.advertiser_name,
                advertiser_id=adv_id_map.get(row.advertiser_name),
                impression_count=row.impression_count,
                intensity=round(row.impression_count / max_impressions, 4),
            )
        )

    return cells


async def calculate_persona_ranking_trend(
    db: AsyncSession,
    persona_code: str,
    days: int = 30,
    channel: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Daily impression trend for a specific persona's top advertisers.

    1. Find top N advertisers for this persona.
    2. For each advertiser, get daily impression counts.
    Returns list of {date, advertiser_name, impression_count}.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Step 1: Find top N advertisers for this persona
    top_q = (
        select(
            AdDetail.advertiser_name_raw.label("advertiser_name"),
            func.count(AdDetail.id).label("total"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(Persona.code == persona_code)
        .where(AdDetail.advertiser_name_raw.isnot(None))
        .where(AdDetail.advertiser_name_raw != "")
    )
    if channel:
        top_q = top_q.where(AdSnapshot.channel == channel)

    top_q = (
        top_q.group_by(AdDetail.advertiser_name_raw)
        .order_by(func.count(AdDetail.id).desc())
        .limit(limit)
    )

    top_result = await db.execute(top_q)
    top_names = [r.advertiser_name for r in top_result.all()]

    if not top_names:
        return []

    # Step 2: Daily impressions per advertiser
    trend_q = (
        select(
            func.date(AdSnapshot.captured_at).label("date"),
            AdDetail.advertiser_name_raw.label("advertiser_name"),
            func.count(AdDetail.id).label("impression_count"),
        )
        .select_from(AdDetail)
        .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
        .join(Persona, AdSnapshot.persona_id == Persona.id)
        .where(AdSnapshot.captured_at >= cutoff)
        .where(Persona.code == persona_code)
        .where(AdDetail.advertiser_name_raw.in_(top_names))
    )
    if channel:
        trend_q = trend_q.where(AdSnapshot.channel == channel)

    trend_q = trend_q.group_by(
        func.date(AdSnapshot.captured_at),
        AdDetail.advertiser_name_raw,
    ).order_by(func.date(AdSnapshot.captured_at))

    trend_result = await db.execute(trend_q)
    return [
        {
            "date": str(row.date),
            "advertiser_name": row.advertiser_name,
            "impression_count": row.impression_count,
        }
        for row in trend_result.all()
    ]
