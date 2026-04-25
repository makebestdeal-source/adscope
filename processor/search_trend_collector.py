"""Naver DataLab Search Trend API 기반 검색 트렌드 수집기.

advertisers 테이블의 브랜드명으로 네이버 검색 트렌드(일별 검색 지수)를
조회하여 traffic_signals 테이블에 저장합니다.

- API: https://openapi.naver.com/v1/datalab/search (POST)
- Headers: X-Naver-Client-Id, X-Naver-Client-Secret (DataLab 전용 키)
- Max 5 keyword groups per request
- Rate limit: 1,000 calls/day
- 일별 검색 지수: 0-100 (상대값)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, and_

from database import async_session
from database.models import Advertiser, TrafficSignal

logger = logging.getLogger(__name__)

NAVER_DATALAB_API = "https://openapi.naver.com/v1/datalab/search"
BATCH_SIZE = 5  # DataLab API max 5 keyword groups per request


# ──────────────────────────────────────────────
# WoW 변화율 및 트래픽 레벨 계산
# ──────────────────────────────────────────────

def _calc_wow_change(daily_data: list[dict]) -> float | None:
    """이번 주 평균 vs 지난 주 평균 비교하여 WoW 변화율 계산.

    daily_data: [{"period": "2026-03-16", "ratio": 45.2}, ...]
    Returns: wow_change_pct or None if insufficient data
    """
    if not daily_data or len(daily_data) < 8:
        return None

    # 최신 7일 = 이번 주, 그 이전 7일 = 지난 주
    sorted_data = sorted(daily_data, key=lambda x: x["period"])
    recent_7 = sorted_data[-7:]
    prev_7 = sorted_data[-14:-7] if len(sorted_data) >= 14 else []

    if not prev_7:
        return None

    avg_recent = sum(d["ratio"] for d in recent_7) / len(recent_7)
    avg_prev = sum(d["ratio"] for d in prev_7) / len(prev_7)

    if avg_prev == 0:
        return 100.0 if avg_recent > 0 else 0.0

    return round((avg_recent - avg_prev) / avg_prev * 100, 2)


def _determine_traffic_level(index: float) -> str:
    """검색 지수에 따른 트래픽 레벨 결정."""
    if index >= 70:
        return "high"
    elif index >= 30:
        return "mid"
    return "low"


# ──────────────────────────────────────────────
# API 호출
# ──────────────────────────────────────────────

async def _fetch_datalab_trends(
    client: httpx.AsyncClient,
    keyword_groups: list[dict],
    headers: dict,
    start_date: str,
    end_date: str,
) -> dict | None:
    """네이버 DataLab 검색 트렌드 API 호출.

    Args:
        keyword_groups: [{"groupName": "브랜드", "keywords": ["키워드1"]}, ...]
                        (max 5 groups)
        start_date: "2026-03-01"
        end_date: "2026-03-23"

    Returns:
        API response dict or None on error
    """
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }

    try:
        resp = await client.post(
            NAVER_DATALAB_API,
            json=body,
            headers=headers,
        )
        if resp.status_code != 200:
            logger.warning(
                "[search_trend] DataLab API error %d: %s",
                resp.status_code, resp.text[:300],
            )
            return None

        return resp.json()

    except Exception as e:
        logger.warning("[search_trend] DataLab API exception: %s", e)
        return None


# ──────────────────────────────────────────────
# 메인 수집 함수
# ──────────────────────────────────────────────

async def collect_search_trends(
    max_advertisers: int = 100,
    days: int = 30,
) -> dict:
    """Collect search trends from Naver DataLab for top advertisers.

    Args:
        max_advertisers: 처리할 최대 광고주 수
        days: 조회 기간 (일)

    Returns:
        {"processed": N, "saved": N, "errors": N}
    """
    client_id = os.getenv("NAVER_DATALAB_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_DATALAB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        logger.error("[search_trend] NAVER_DATALAB_CLIENT_ID/SECRET not set")
        return {"processed": 0, "saved": 0, "errors": 0}

    api_headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
        "Content-Type": "application/json",
    }

    now = datetime.now(UTC).replace(tzinfo=None)
    end_date = now.strftime("%Y-%m-%d")
    start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")

    total_processed = 0
    total_saved = 0
    total_errors = 0

    async with async_session() as session:
        # brand_name이 있는 광고주 목록
        adv_query = (
            select(Advertiser)
            .where(Advertiser.brand_name.isnot(None))
            .where(Advertiser.brand_name != "")
            .order_by(Advertiser.id.asc())
            .limit(max_advertisers)
        )
        advertisers = (await session.execute(adv_query)).scalars().all()

        if not advertisers:
            logger.warning("[search_trend] No advertisers with brand_name found")
            return {"processed": 0, "saved": 0, "errors": 0}

        logger.info(
            "[search_trend] Starting: %d advertisers, period %s ~ %s",
            len(advertisers), start_date, end_date,
        )

        # 기존 데이터 캐시 (중복 방지: advertiser_id + date)
        existing_q = select(TrafficSignal.advertiser_id, TrafficSignal.date)
        existing_rows = (await session.execute(existing_q)).all()
        existing_set: set[tuple[int, str]] = {
            (row[0], row[1].strftime("%Y-%m-%d") if row[1] else "")
            for row in existing_rows
        }

        # 5개씩 배치 처리
        batches: list[list] = []
        for i in range(0, len(advertisers), BATCH_SIZE):
            batches.append(advertisers[i:i + BATCH_SIZE])

        async with httpx.AsyncClient(timeout=15.0) as http_client:
            for batch_idx, batch in enumerate(batches):
                try:
                    # 키워드 그룹 구성 (advertiser_id -> keyword 매핑 유지)
                    keyword_groups = []
                    adv_map: dict[str, int] = {}  # groupName -> advertiser_id

                    for adv in batch:
                        keyword = (adv.brand_name or "").strip()
                        if not keyword or len(keyword) < 2:
                            continue

                        group_name = f"{keyword}_{adv.id}"
                        keyword_groups.append({
                            "groupName": group_name,
                            "keywords": [keyword],
                        })
                        adv_map[group_name] = adv.id

                    if not keyword_groups:
                        continue

                    # DataLab API 호출
                    result = await _fetch_datalab_trends(
                        http_client, keyword_groups, api_headers, start_date, end_date,
                    )

                    if not result or "results" not in result:
                        total_errors += len(keyword_groups)
                        continue

                    # 결과 파싱 및 저장
                    for group_result in result["results"]:
                        group_name = group_result.get("title", "")
                        adv_id = adv_map.get(group_name)
                        if adv_id is None:
                            continue

                        daily_data = group_result.get("data", [])
                        if not daily_data:
                            continue

                        # brand_keyword 추출 (groupName에서 _id 제거)
                        brand_keyword = group_result.get("keywords", [""])[0]

                        # WoW 변화율 계산 (전체 일별 데이터 기반)
                        wow_change = _calc_wow_change(daily_data)

                        for point in daily_data:
                            date_str = point.get("period", "")
                            ratio = point.get("ratio", 0.0)

                            if not date_str:
                                continue

                            # 중복 체크
                            if (adv_id, date_str) in existing_set:
                                continue

                            try:
                                date_val = datetime.strptime(date_str, "%Y-%m-%d")
                            except ValueError:
                                continue

                            traffic_level = _determine_traffic_level(ratio)

                            signal = TrafficSignal(
                                advertiser_id=adv_id,
                                date=date_val,
                                brand_keyword=brand_keyword,
                                naver_search_index=round(ratio, 2),
                                composite_index=round(ratio, 2),  # 네이버만 사용하므로 동일
                                wow_change_pct=wow_change,
                                traffic_level=traffic_level,
                            )
                            session.add(signal)
                            existing_set.add((adv_id, date_str))
                            total_saved += 1

                        total_processed += 1

                    # 배치 커밋
                    await session.commit()

                    if (batch_idx + 1) % 5 == 0:
                        logger.info(
                            "[search_trend] Progress: batch %d/%d, %d processed, %d saved",
                            batch_idx + 1, len(batches), total_processed, total_saved,
                        )

                    # API rate limit 방지 (1,000 calls/day -> 1초 간격)
                    await asyncio.sleep(1.0)

                except Exception as e:
                    logger.warning(
                        "[search_trend] Batch %d error: %s", batch_idx, e,
                    )
                    total_errors += len(batch)

        # 최종 커밋
        await session.commit()

    logger.info(
        "[search_trend] Done: %d processed, %d saved, %d errors",
        total_processed, total_saved, total_errors,
    )
    return {
        "processed": total_processed,
        "saved": total_saved,
        "errors": total_errors,
    }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    max_adv = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    d = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    result = asyncio.run(
        collect_search_trends(max_advertisers=max_adv, days=d)
    )
    logger.info("Result: %s", result)
