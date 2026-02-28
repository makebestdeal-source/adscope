"""네이버 검색광고 키워드도구 API 연동.

보유 계정(dingojm / customer_id: 1903273)으로
키워드별 월간검색수, 평균CPC, 경쟁도를 수집하여
광고비 추정 정확도를 개선한다.

API 문서: https://naver.github.io/searchad-apidoc/
인증: HMAC-SHA256 (X-API-KEY, X-CUSTOMER, X-Timestamp, X-Signature)

.env 필요:
  NAVER_AD_API_KEY=<Access License>
  NAVER_AD_SECRET_KEY=<Secret Key>
  NAVER_AD_CUSTOMER_ID=1903273
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import datetime, timezone

import httpx
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from database.models import Keyword


# ── 설정 ──

API_BASE = "https://api.searchad.naver.com"
CUSTOMER_ID = os.getenv("NAVER_AD_CUSTOMER_ID", "1903273")
API_KEY = os.getenv("NAVER_AD_API_KEY", "")
SECRET_KEY = os.getenv("NAVER_AD_SECRET_KEY", "")


def _generate_signature(timestamp: str, method: str, path: str) -> str:
    """HMAC-SHA256 서명 생성 (Base64 인코딩)."""
    import base64
    message = f"{timestamp}.{method}.{path}"
    sign = hmac.new(
        SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(sign).decode("utf-8")


def _auth_headers(method: str, path: str) -> dict:
    """API 인증 헤더 생성."""
    timestamp = str(int(time.time() * 1000))
    signature = _generate_signature(timestamp, method, path)
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": API_KEY,
        "X-Customer": CUSTOMER_ID,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }


async def fetch_keyword_stats(keywords: list[str]) -> list[dict]:
    """키워드도구 API로 키워드별 통계 조회.

    Args:
        keywords: 검색할 키워드 목록 (최대 5개씩 배치)

    Returns:
        [{"keyword": str, "monthlyPcQcCnt": int, "monthlyMobileQcCnt": int,
          "monthlyAvePcClkCost": int, "monthlyAveMobileClkCost": int,
          "compIdx": str, "plAvgDepth": int}]
    """
    if not API_KEY or not SECRET_KEY:
        logger.warning("[naver_kw] API keys not configured. Set NAVER_AD_API_KEY and NAVER_AD_SECRET_KEY in .env")
        return []

    path = "/keywordstool"
    all_results: list[dict] = []

    # 5개씩 배치 처리
    batch_size = 5
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]
        params = {
            "hintKeywords": ",".join(batch),
            "showDetail": "1",
        }

        headers = _auth_headers("GET", path)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{API_BASE}{path}",
                    params=params,
                    headers=headers,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    keyword_list = data.get("keywordList", [])
                    all_results.extend(keyword_list)
                    logger.debug(
                        "[naver_kw] batch {}/{}: {} keywords returned",
                        i // batch_size + 1,
                        (len(keywords) + batch_size - 1) // batch_size,
                        len(keyword_list),
                    )
                elif resp.status_code == 401:
                    logger.error("[naver_kw] Authentication failed. Check API keys.")
                    return all_results
                else:
                    logger.warning(
                        "[naver_kw] API returned {}: {}",
                        resp.status_code, resp.text[:200],
                    )
        except Exception as e:
            logger.error("[naver_kw] API call failed: {}", str(e)[:100])

        # Rate limit: 0.5초 간격
        import asyncio
        await asyncio.sleep(0.5)

    return all_results


async def update_keyword_stats() -> dict:
    """DB의 모든 활성 키워드에 대해 CPC/검색량 업데이트.

    Returns:
        {"total": N, "updated": M, "errors": E}
    """
    if not API_KEY or not SECRET_KEY:
        logger.warning("[naver_kw] Skipping: API keys not set")
        return {"total": 0, "updated": 0, "errors": 0, "skipped": "no_api_keys"}

    # DB에서 활성 키워드 조회
    async with async_session() as session:
        result = await session.execute(
            select(Keyword.id, Keyword.keyword).where(Keyword.is_active == True)
        )
        db_keywords = result.fetchall()

    if not db_keywords:
        return {"total": 0, "updated": 0, "errors": 0}

    kw_list = [row.keyword for row in db_keywords]
    kw_id_map = {row.keyword.lower(): row.id for row in db_keywords}

    logger.info("[naver_kw] Fetching stats for {} keywords", len(kw_list))

    # API 호출
    api_results = await fetch_keyword_stats(kw_list)

    # DB 업데이트
    updated = 0
    errors = 0
    async with async_session() as session:
        for item in api_results:
            rel_keyword = item.get("relKeyword", "").lower()
            kw_id = kw_id_map.get(rel_keyword)
            if not kw_id:
                continue

            pc_search = _parse_search_count(item.get("monthlyPcQcCnt"))
            mobile_search = _parse_search_count(item.get("monthlyMobileQcCnt"))
            total_search = (pc_search or 0) + (mobile_search or 0) or None

            pc_cpc = _parse_cpc(item.get("monthlyAvePcClkCost"))
            mobile_cpc = _parse_cpc(item.get("monthlyAveMobileClkCost"))
            # 모바일 CPC 우선 (모바일 트래픽이 더 많음)
            best_cpc = mobile_cpc or pc_cpc

            try:
                await session.execute(
                    update(Keyword)
                    .where(Keyword.id == kw_id)
                    .values(
                        naver_cpc=best_cpc,
                        monthly_search_vol=total_search,
                    )
                )
                updated += 1
            except Exception as e:
                errors += 1
                logger.debug("[naver_kw] Update failed for '{}': {}", rel_keyword, e)

        await session.commit()

    logger.info(
        "[naver_kw] Updated {}/{} keywords (errors: {})",
        updated, len(db_keywords), errors,
    )
    return {"total": len(db_keywords), "updated": updated, "errors": errors}


def _parse_search_count(val) -> int | None:
    """API 검색량 값 파싱 (문자열 '< 10' 등 처리)."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if s == "< 10":
        return 5
    try:
        return int(s.replace(",", ""))
    except ValueError:
        return None


def _parse_cpc(val) -> int | None:
    """API CPC 값 파싱."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val) if val > 0 else None
    try:
        return int(str(val).replace(",", ""))
    except ValueError:
        return None


async def get_related_keywords(seed_keyword: str, limit: int = 20) -> list[dict]:
    """시드 키워드의 연관 키워드 조회.

    새로운 수집 키워드 발굴에 활용.
    """
    if not API_KEY or not SECRET_KEY:
        return []

    results = await fetch_keyword_stats([seed_keyword])

    # 검색량 순 정렬
    sorted_results = sorted(
        results,
        key=lambda x: (
            _parse_search_count(x.get("monthlyMobileQcCnt")) or 0
        ) + (
            _parse_search_count(x.get("monthlyPcQcCnt")) or 0
        ),
        reverse=True,
    )

    return [
        {
            "keyword": item.get("relKeyword", ""),
            "monthly_search": (
                (_parse_search_count(item.get("monthlyPcQcCnt")) or 0)
                + (_parse_search_count(item.get("monthlyMobileQcCnt")) or 0)
            ),
            "cpc": _parse_cpc(item.get("monthlyAveMobileClkCost"))
                   or _parse_cpc(item.get("monthlyAvePcClkCost")),
            "competition": item.get("compIdx", ""),
        }
        for item in sorted_results[:limit]
    ]
