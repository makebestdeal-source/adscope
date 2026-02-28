"""Traffic estimator -- brand search volume signals from Naver DataLab + Google Trends.

Sources:
  1. Naver DataLab Search Trend API (official, free, requires client ID/secret)
  2. Google Trends via pytrends (unofficial but widely used)

Output: TrafficSignal row per advertiser per day.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import httpx

from sqlalchemy import and_, select

from database import async_session
from database.models import Advertiser, TrafficSignal

logger = logging.getLogger(__name__)

NAVER_DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"


_NAVER_DAILY_CALL_COUNT = 0
_NAVER_DAILY_CALL_LIMIT = 800  # 일일 한도 1000 중 여유분 확보


async def _fetch_naver_trend_batch(
    keywords: list[str],
    client_id: str,
    client_secret: str,
    days: int = 30,
) -> dict[str, float | None]:
    """Fetch Naver DataLab for up to 5 keywords in a single API call.

    Returns dict of {keyword: ratio} for each keyword.
    """
    global _NAVER_DAILY_CALL_COUNT
    if _NAVER_DAILY_CALL_COUNT >= _NAVER_DAILY_CALL_LIMIT:
        logger.warning("[traffic] Naver DataLab daily limit (%d) reached, skipping", _NAVER_DAILY_CALL_LIMIT)
        return {kw: None for kw in keywords}

    end_date = datetime.now(UTC).strftime("%Y-%m-%d")
    start_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

    keyword_groups = [
        {"groupName": kw, "keywords": [kw]} for kw in keywords[:5]
    ]

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }

    result_map: dict[str, float | None] = {kw: None for kw in keywords}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                NAVER_DATALAB_URL,
                json=body,
                headers={
                    "X-Naver-Client-Id": client_id,
                    "X-Naver-Client-Secret": client_secret,
                    "Content-Type": "application/json",
                },
            )
            _NAVER_DAILY_CALL_COUNT += 1

            if resp.status_code != 200:
                logger.warning("[traffic] Naver DataLab error %d", resp.status_code)
                return result_map

            data = resp.json()
            for group in data.get("results", []):
                name = group.get("title", "")
                points = group.get("data", [])
                if points:
                    result_map[name] = float(points[-1]["ratio"])

            return result_map
    except Exception as e:
        logger.warning("[traffic] Naver DataLab batch exception: %s", e)
        return result_map


async def _fetch_naver_trend(
    keyword: str,
    client_id: str,
    client_secret: str,
    days: int = 30,
) -> float | None:
    """Single keyword wrapper for backward compatibility."""
    result = await _fetch_naver_trend_batch([keyword], client_id, client_secret, days)
    return result.get(keyword)


async def _fetch_google_trend(keyword: str, days: int = 30) -> float | None:
    """Fetch Google Trends index (0-100) for a keyword using pytrends."""
    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="ko", tz=540)
        timeframe = f"today {max(1, days // 30)}-m" if days <= 90 else "today 3-m"
        pytrends.build_payload([keyword], cat=0, timeframe=timeframe, geo="KR")
        df = pytrends.interest_over_time()

        if df.empty or keyword not in df.columns:
            return None

        # Return latest value
        return float(df[keyword].iloc[-1])
    except ImportError:
        logger.debug("[traffic] pytrends not installed, skipping Google Trends")
        return None
    except Exception as e:
        logger.warning("[traffic] Google Trends exception for '%s': %s", keyword, e)
        return None


# ── Campaign channel → stealth network mapping ──
_CHANNEL_TO_NETWORK = {
    "facebook": "meta", "instagram": "meta",
    "naver_da": "naver", "naver_search": "naver",
    "naver_shopping": "naver", "mobile_naver_ssp": "naver",
    "kakao_da": "kakao",
    "google_search_ads": "gdn", "mobile_gdn": "gdn", "youtube_ads": "gdn",
}


async def _get_stealth_traffic_proxy(session, advertiser_id: int) -> float | None:
    """Derive traffic proxy from stealth surf data for an advertiser.

    Logic: advertiser's campaign channels → stealth network contact rates → traffic index.
    Higher contact rate = more ad impressions = more ad spend = higher traffic proxy.
    """
    from sqlalchemy import text as sa_text, func as sa_func

    # Get advertiser's active channels
    from database.models import Campaign
    ch_result = await session.execute(
        select(sa_func.distinct(Campaign.channel)).where(
            and_(Campaign.advertiser_id == advertiser_id, Campaign.is_active == True)
        )
    )
    channels = ch_result.scalars().all()
    if not channels:
        return None

    # Map to stealth networks
    networks = set()
    for ch in channels:
        net = _CHANNEL_TO_NETWORK.get(ch)
        if net:
            networks.add(net)
    if not networks:
        return None

    # Get stealth contact rates for these networks
    since = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).isoformat()
    q = sa_text("""
        SELECT json_extract(extra_data, '$.network') AS net, COUNT(*) AS cnt
        FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
          AND collected_at >= :since
          AND json_extract(extra_data, '$.network') IN ({})
        GROUP BY net
    """.format(",".join(f"'{n}'" for n in networks)))

    result = await session.execute(q, {"since": since})
    rows = result.fetchall()
    if not rows:
        return None

    ratios = {"gdn": 50, "naver": 6, "kakao": 6, "meta": 5}
    total_score = 0.0
    count = 0
    for net, cnt in rows:
        imp = cnt / ratios.get(net, 10)
        # Normalize to 0-100: 100+ impressions per network = score 100
        score = min(100.0, imp / 1.0)  # 100 impressions = 100
        total_score += score
        count += 1

    return round(total_score / count, 1) if count > 0 else None


def _compute_level(composite: float) -> str:
    if composite >= 60:
        return "high"
    if composite >= 30:
        return "mid"
    return "low"


async def estimate_traffic_signals(
    session=None,
    advertiser_ids: list[int] | None = None,
    days: int = 30,
) -> dict:
    """Estimate traffic signals for advertisers using search trend data.

    Sources (priority order):
    1. Naver DataLab API (if keys configured)
    2. Google Trends via pytrends
    3. Stealth surf contact rate fallback (always available)

    Returns: {"processed": N, "created": N, "updated": N, "skipped": N}
    """
    naver_id = os.getenv("NAVER_DATALAB_CLIENT_ID", "")
    naver_secret = os.getenv("NAVER_DATALAB_CLIENT_SECRET", "")

    own_session = session is None
    if own_session:
        session = async_session()

    try:
        now = datetime.now(UTC).replace(tzinfo=None)
        today = now.date()
        today_dt = datetime(today.year, today.month, today.day)
        week_ago_dt = today_dt - timedelta(days=7)

        # Get advertisers with brand names
        adv_query = select(Advertiser).where(Advertiser.brand_name.isnot(None))
        if advertiser_ids:
            adv_query = adv_query.where(Advertiser.id.in_(advertiser_ids))

        result = await session.execute(adv_query)
        advertisers = result.scalars().all()

        created = 0
        updated = 0
        skipped = 0

        # Pre-filter valid advertisers and batch Naver API calls (5 per request)
        valid_advs = []
        for adv in advertisers:
            keyword = adv.brand_name or adv.name
            if not keyword or len(keyword) < 2:
                skipped += 1
                continue
            valid_advs.append((adv, keyword))

        # Batch fetch Naver trends (5 keywords per API call = ~380 calls for 1,894 advertisers)
        naver_results: dict[str, float | None] = {}
        if naver_id and naver_secret:
            batch: list[str] = []
            for _, keyword in valid_advs:
                batch.append(keyword)
                if len(batch) >= 5:
                    result = await _fetch_naver_trend_batch(batch, naver_id, naver_secret, days)
                    naver_results.update(result)
                    batch = []
            if batch:
                result = await _fetch_naver_trend_batch(batch, naver_id, naver_secret, days)
                naver_results.update(result)

        for adv, keyword in valid_advs:
            naver_idx = naver_results.get(keyword)

            google_idx = None
            if naver_id:
                google_idx = await _fetch_google_trend(keyword, days)

            # Stealth fallback when official sources unavailable
            stealth_idx = None
            if naver_idx is None and google_idx is None:
                stealth_idx = await _get_stealth_traffic_proxy(session, adv.id)

            if naver_idx is None and google_idx is None and stealth_idx is None:
                skipped += 1
                continue

            # Composite: Naver 60% + Google 40% (Korean market weight)
            if naver_idx is not None and google_idx is not None:
                composite = naver_idx * 0.6 + google_idx * 0.4
            elif naver_idx is not None:
                composite = naver_idx
            elif google_idx is not None:
                composite = google_idx
            else:
                composite = stealth_idx * 0.7

            composite = round(composite, 1)

            # Week-over-week change
            prev_row = (
                await session.execute(
                    select(TrafficSignal.composite_index).where(
                        and_(
                            TrafficSignal.advertiser_id == adv.id,
                            TrafficSignal.date == week_ago_dt,
                        )
                    )
                )
            ).scalar_one_or_none()

            wow_change = None
            if prev_row and prev_row > 0:
                wow_change = round(((composite - prev_row) / prev_row) * 100, 1)

            level = _compute_level(composite)

            # Upsert
            existing = (
                await session.execute(
                    select(TrafficSignal).where(
                        and_(
                            TrafficSignal.advertiser_id == adv.id,
                            TrafficSignal.date == today_dt,
                        )
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.brand_keyword = keyword
                existing.naver_search_index = naver_idx
                existing.google_trend_index = google_idx
                existing.composite_index = composite
                existing.wow_change_pct = wow_change
                existing.traffic_level = level
                updated += 1
            else:
                session.add(
                    TrafficSignal(
                        advertiser_id=adv.id,
                        date=today_dt,
                        brand_keyword=keyword,
                        naver_search_index=naver_idx,
                        google_trend_index=google_idx,
                        composite_index=composite,
                        wow_change_pct=wow_change,
                        traffic_level=level,
                    )
                )
                created += 1

        await session.commit()
        total = len(advertisers)
        logger.info(
            "[traffic_estimator] processed=%d created=%d updated=%d skipped=%d",
            total, created, updated, skipped,
        )
        return {"processed": total, "created": created, "updated": updated, "skipped": skipped}

    finally:
        if own_session:
            await session.close()
