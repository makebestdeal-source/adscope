"""Phase 3E: 미검증 광고 일괄 크로스체킹.

Meta Ad Library + Google Ads Transparency Center를 조회하여
ad_details.verification_status를 업데이트한다.

사용법:
    from processor.cross_verifier import batch_verify_unverified
    stats = await batch_verify_unverified(days=7, limit=50)
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from loguru import logger
from playwright.async_api import async_playwright
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session, init_db
from database.models import AdDetail, AdSnapshot, Advertiser

# 검증 소스 URL 템플릿
META_LIBRARY_URL = "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=KR&q={query}"
GOOGLE_TRANSPARENCY_URL = "https://adstransparency.google.com/?region=KR&query={query}"

# 설정
_MAX_CONCURRENT = int(os.getenv("CROSS_VERIFY_CONCURRENT", "3"))
_PAGE_TIMEOUT = int(os.getenv("CROSS_VERIFY_TIMEOUT_MS", "15000"))


@dataclass
class VerificationResult:
    """단일 광고주의 크로스체킹 결과."""

    advertiser_name: str
    meta_status: str  # verified, likely_verified, unverified, unknown, error
    google_status: str
    final_status: str  # cross_verified, verified, unverified, unknown
    source: str  # "meta+google", "meta", "google", "none"


def _classify_meta_result(body_text: str, hint: str | None = None) -> str:
    """Meta Ad Library 결과 분류."""
    lower = body_text.lower()
    no_result_phrases = [
        "no results", "결과가 없습니다", "광고를 찾을 수 없습니다",
        "no ads found", "이 검색과 일치하는",
    ]
    for phrase in no_result_phrases:
        if phrase in lower:
            return "unverified"

    if hint and hint.lower() in lower:
        return "verified"
    if len(body_text.strip()) > 200:
        return "likely_verified"
    return "unknown"


def _classify_google_result(body_text: str, hint: str | None = None) -> str:
    """Google Ads Transparency 결과 분류."""
    lower = body_text.lower()
    no_result_phrases = [
        "no results", "결과 없음", "일치하는 광고주가 없습니다",
        "no matching", "we couldn't find",
    ]
    for phrase in no_result_phrases:
        if phrase in lower:
            return "unverified"

    if hint and hint.lower() in lower:
        return "verified"
    if len(body_text.strip()) > 200:
        return "likely_verified"
    return "unknown"


def _determine_final_status(meta: str, google: str) -> tuple[str, str]:
    """두 소스 결과를 종합하여 최종 검증 상태 결정.

    Returns:
        (final_status, source_label)
    """
    if meta == "verified" and google == "verified":
        return "cross_verified", "meta+google"
    if meta == "verified" or google == "verified":
        source = "meta" if meta == "verified" else "google"
        return "verified", source
    if meta == "likely_verified" or google == "likely_verified":
        source = "meta" if meta == "likely_verified" else "google"
        return "likely_verified", source
    if meta == "unverified" and google == "unverified":
        return "unverified", "meta+google"
    return "unknown", "none"


async def _check_meta(page, advertiser_name: str) -> str:
    """Meta Ad Library에서 광고주 검색 후 결과 분류."""
    try:
        url = META_LIBRARY_URL.format(query=advertiser_name)
        await page.goto(url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT)
        await page.wait_for_timeout(3000)
        body = await page.inner_text("body")
        return _classify_meta_result(body, advertiser_name)
    except Exception as e:
        logger.debug(f"[cross_verify] Meta 조회 실패 ({advertiser_name}): {e}")
        return "error"


async def _check_google(page, advertiser_name: str) -> str:
    """Google Ads Transparency에서 광고주 검색 후 결과 분류."""
    try:
        url = GOOGLE_TRANSPARENCY_URL.format(query=advertiser_name)
        await page.goto(url, wait_until="domcontentloaded", timeout=_PAGE_TIMEOUT)
        await page.wait_for_timeout(3000)
        body = await page.inner_text("body")
        return _classify_google_result(body, advertiser_name)
    except Exception as e:
        logger.debug(f"[cross_verify] Google 조회 실패 ({advertiser_name}): {e}")
        return "error"


async def verify_advertiser(browser, advertiser_name: str) -> VerificationResult:
    """단일 광고주에 대해 Meta + Google 크로스체킹 실행."""
    context = await browser.new_context()
    try:
        meta_page = await context.new_page()
        google_page = await context.new_page()

        meta_status, google_status = await asyncio.gather(
            _check_meta(meta_page, advertiser_name),
            _check_google(google_page, advertiser_name),
        )

        final_status, source = _determine_final_status(meta_status, google_status)

        return VerificationResult(
            advertiser_name=advertiser_name,
            meta_status=meta_status,
            google_status=google_status,
            final_status=final_status,
            source=source,
        )
    finally:
        await context.close()


async def batch_verify_unverified(
    days: int = 7,
    limit: int = 50,
) -> dict:
    """DB에서 미검증 광고를 조회하여 일괄 크로스체킹.

    Args:
        days: 최근 N일 이내 광고만 대상
        limit: 최대 검증할 광고주 수

    Returns:
        {"total_checked": int, "verified": int, "unverified": int, "errors": int}
    """
    from datetime import datetime, timedelta

    await init_db()

    cutoff = datetime.utcnow() - timedelta(days=days)

    # 미검증 광고주명 수집
    async with async_session() as session:
        q = (
            select(AdDetail.advertiser_name_raw)
            .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
            .where(AdSnapshot.captured_at >= cutoff)
            .where(
                AdDetail.verification_status.in_(["unverified", "unknown", None])
            )
            .where(AdDetail.advertiser_name_raw.isnot(None))
            .group_by(AdDetail.advertiser_name_raw)
            .limit(limit)
        )
        result = await session.execute(q)
        advertiser_names = [r[0] for r in result.all()]

    if not advertiser_names:
        logger.info("[cross_verify] 미검증 광고주 없음")
        return {"total_checked": 0, "verified": 0, "unverified": 0, "errors": 0}

    logger.info(f"[cross_verify] {len(advertiser_names)}명 광고주 검증 시작")

    # 브라우저로 일괄 검증
    stats = {"total_checked": 0, "verified": 0, "unverified": 0, "errors": 0}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        sem = asyncio.Semaphore(_MAX_CONCURRENT)

        async def limited_verify(name: str) -> VerificationResult:
            async with sem:
                return await verify_advertiser(browser, name)

        results = await asyncio.gather(
            *[limited_verify(name) for name in advertiser_names],
            return_exceptions=True,
        )

        await browser.close()

    # DB 업데이트
    async with async_session() as session:
        for r in results:
            if isinstance(r, Exception):
                stats["errors"] += 1
                continue

            stats["total_checked"] += 1

            if r.final_status in ("cross_verified", "verified", "likely_verified"):
                stats["verified"] += 1
            elif r.final_status == "unverified":
                stats["unverified"] += 1

            # 해당 광고주의 모든 미검증 광고 업데이트
            await session.execute(
                update(AdDetail)
                .where(AdDetail.advertiser_name_raw == r.advertiser_name)
                .where(
                    AdDetail.verification_status.in_(["unverified", "unknown", None])
                )
                .values(
                    verification_status=r.final_status,
                    verification_source=f"cross_check:{r.source}",
                )
            )

            logger.debug(
                f"[cross_verify] {r.advertiser_name}: "
                f"meta={r.meta_status}, google={r.google_status} → {r.final_status}"
            )

        await session.commit()

    logger.info(
        f"[cross_verify] 완료: {stats['total_checked']}명 검증, "
        f"{stats['verified']}명 확인, {stats['unverified']}명 미확인, "
        f"{stats['errors']}건 오류"
    )
    return stats
