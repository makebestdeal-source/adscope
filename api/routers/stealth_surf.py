"""Stealth persona surf API -- 접촉률 기반 광고 분석."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from database.models import User

router = APIRouter(prefix="/api/stealth-surf", tags=["stealth-surf"])


@router.get("/summary")
async def get_stealth_summary(
    days: int = Query(default=30, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stealth 수집 전체 요약: 네트워크별/페르소나별 접촉률."""
    since = datetime.utcnow() - timedelta(days=days)

    rows = await db.execute(text("""
        SELECT extra_data FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
        AND collected_at >= :since
        AND extra_data IS NOT NULL
    """), {"since": since.isoformat()})

    by_network = {}
    by_persona = {}
    by_source = {}
    total = 0

    for (extra_data_str,) in rows:
        try:
            d = json.loads(extra_data_str)
        except Exception:
            continue
        total += 1
        net = d.get("network", "other")
        persona = d.get("persona", "unknown")
        source = d.get("source", "unknown")

        by_network[net] = by_network.get(net, 0) + 1
        by_persona[persona] = by_persona.get(persona, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1

    # 접촉률 계산 (세션당 = 26페이지 기준)
    pages_per_session = 26
    persona_count = len(by_persona) or 1
    total_pages = pages_per_session * persona_count

    contact_rates = {}
    for net, cnt in by_network.items():
        # request-to-impression ratio
        ratios = {"gdn": 50, "naver": 6, "kakao": 6, "meta": 5}
        r = ratios.get(net, 10)
        impressions = cnt / r
        contact_rates[net] = round(impressions / total_pages, 3)

    return {
        "total_ads": total,
        "period_days": days,
        "by_network": dict(sorted(by_network.items(), key=lambda x: -x[1])),
        "by_persona": dict(sorted(by_persona.items(), key=lambda x: -x[1])),
        "by_source": dict(sorted(by_source.items(), key=lambda x: -x[1])[:10]),
        "contact_rates": contact_rates,
        "sessions": persona_count,
    }


@router.get("/persona-breakdown")
async def get_persona_breakdown(
    days: int = Query(default=30, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """페르소나별 네트워크 분포 (히트맵 데이터)."""
    since = datetime.utcnow() - timedelta(days=days)

    rows = await db.execute(text("""
        SELECT extra_data FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
        AND collected_at >= :since
        AND extra_data IS NOT NULL
    """), {"since": since.isoformat()})

    matrix = {}  # {persona: {network: count}}
    for (extra_data_str,) in rows:
        try:
            d = json.loads(extra_data_str)
        except Exception:
            continue
        persona = d.get("persona", "unknown")
        net = d.get("network", "other")
        if persona not in matrix:
            matrix[persona] = {}
        matrix[persona][net] = matrix[persona].get(net, 0) + 1

    # 히트맵 셀 데이터
    cells = []
    for persona, nets in sorted(matrix.items()):
        for net, cnt in sorted(nets.items()):
            cells.append({
                "persona": persona,
                "network": net,
                "count": cnt,
            })

    return {"cells": cells, "personas": sorted(matrix.keys())}


@router.get("/spend-estimate")
async def get_stealth_spend_estimate(
    days: int = Query(default=30, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """접촉률 기반 광고비 추정."""
    try:
        from processor.stealth_spend_bridge import generate_stealth_spend_report
        report = await generate_stealth_spend_report(db, days=days)
        return report
    except Exception as e:
        return {"error": str(e)[:200], "estimates": []}


@router.get("/source-detail")
async def get_source_detail(
    source: str = Query(...),
    days: int = Query(default=30, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 소스(언론사/카테고리)별 상세."""
    since = datetime.utcnow() - timedelta(days=days)

    # Escape LIKE wildcards in user input to prevent injection
    safe_source = source.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    source_pattern = f'%"{safe_source}"%'

    rows = await db.execute(text("""
        SELECT extra_data, target_domain FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
        AND collected_at >= :since
        AND extra_data LIKE :source_pattern ESCAPE '\\'
    """), {"since": since.isoformat(), "source_pattern": source_pattern})

    by_network = {}
    by_persona = {}
    sample_urls = []

    for extra_data_str, target_domain in rows:
        try:
            d = json.loads(extra_data_str)
        except Exception:
            continue
        if d.get("source") != source and d.get("channel") != source:
            continue
        net = d.get("network", "other")
        persona = d.get("persona", "unknown")
        by_network[net] = by_network.get(net, 0) + 1
        by_persona[persona] = by_persona.get(persona, 0) + 1
        if len(sample_urls) < 5 and target_domain:
            sample_urls.append(target_domain[:100])

    return {
        "source": source,
        "total": sum(by_network.values()),
        "by_network": by_network,
        "by_persona": by_persona,
        "sample_urls": sample_urls,
    }
