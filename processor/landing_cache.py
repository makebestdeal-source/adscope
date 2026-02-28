"""Landing URL 캐시 — 도메인→브랜드 매핑 DB 캐시 레이어.

크롤러의 landing URL 해석 병목(5URL x 8초 = 40초)을 해소.
한번 해석된 도메인은 DB 캐시에서 즉시 반환.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


async def get_cached_brand(session: AsyncSession, url: str) -> dict | None:
    """캐시에서 URL의 브랜드 정보 조회.

    Args:
        session: DB 세션
        url: 랜딩 URL

    Returns:
        {"brand_name": str, "advertiser_id": int|None, "business_name": str|None}
        또는 None (캐시 미스)
    """
    from database.models import LandingUrlCache

    domain = _extract_domain(url)
    if not domain:
        return None

    result = await session.execute(
        select(LandingUrlCache).where(LandingUrlCache.domain == domain)
    )
    cache_entry = result.scalar_one_or_none()

    if cache_entry is None:
        return None

    # 히트 카운트 업데이트
    await session.execute(
        update(LandingUrlCache)
        .where(LandingUrlCache.id == cache_entry.id)
        .values(hit_count=LandingUrlCache.hit_count + 1)
    )

    return {
        "brand_name": cache_entry.brand_name,
        "advertiser_id": cache_entry.advertiser_id,
        "business_name": cache_entry.business_name,
    }


async def cache_landing_result(
    session: AsyncSession,
    url: str,
    brand_name: str | None = None,
    advertiser_id: int | None = None,
    business_name: str | None = None,
    page_title: str | None = None,
) -> None:
    """랜딩 URL 해석 결과를 캐시에 저장.

    Args:
        session: DB 세션
        url: 원본 랜딩 URL
        brand_name: 해석된 브랜드명
        advertiser_id: 매칭된 광고주 ID
        business_name: 사업자명
        page_title: 페이지 타이틀
    """
    from database.models import LandingUrlCache

    domain = _extract_domain(url)
    if not domain:
        return

    # 기존 캐시 확인
    result = await session.execute(
        select(LandingUrlCache).where(LandingUrlCache.domain == domain)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # 업데이트 (더 좋은 정보가 있으면)
        if brand_name and not existing.brand_name:
            existing.brand_name = brand_name
        if advertiser_id and not existing.advertiser_id:
            existing.advertiser_id = advertiser_id
        if business_name and not existing.business_name:
            existing.business_name = business_name
        if page_title and not existing.page_title:
            existing.page_title = page_title
        existing.resolved_at = datetime.utcnow()
    else:
        cache_entry = LandingUrlCache(
            domain=domain,
            brand_name=brand_name,
            advertiser_id=advertiser_id,
            business_name=business_name,
            page_title=page_title,
        )
        session.add(cache_entry)

    try:
        await session.flush()
    except Exception as e:
        logger.debug(f"[landing_cache] 캐시 저장 실패 ({domain}): {e}")


def _extract_domain(url: str) -> str | None:
    """URL에서 도메인 추출 (www 제거)."""
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        domain = domain.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain if domain else None
    except Exception:
        return None
