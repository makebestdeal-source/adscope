"""크롤러 -> 정규화 -> 분류 -> DB 적재 파이프라인."""

import asyncio
import sys
from pathlib import Path

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AdDetail, AdSnapshot, Keyword, Persona

# ── 세션 내 키워드/페르소나 캐시 (N+1 쿼리 방지) ──
_keyword_cache: dict[str, int] = {}  # keyword_text -> keyword_id
_persona_cache: dict[str, int] = {}  # persona_code -> persona_id


async def _get_keyword_id(session: AsyncSession, keyword_text: str) -> int | None:
    """키워드 ID 조회 (캐시 우선)."""
    if keyword_text in _keyword_cache:
        return _keyword_cache[keyword_text]
    result = await session.execute(
        select(Keyword.id).where(Keyword.keyword == keyword_text)
    )
    kw_id = result.scalar_one_or_none()
    if kw_id is not None:
        _keyword_cache[keyword_text] = kw_id
    return kw_id


async def _get_persona_id(session: AsyncSession, persona_code: str) -> int | None:
    """페르소나 ID 조회 (캐시 우선)."""
    if persona_code in _persona_cache:
        return _persona_cache[persona_code]
    result = await session.execute(
        select(Persona.id).where(Persona.code == persona_code)
    )
    p_id = result.scalar_one_or_none()
    if p_id is not None:
        _persona_cache[persona_code] = p_id
    return p_id
from processor.ad_classifier import classify_ad
from processor.advertiser_verifier import NameQuality, verify_advertiser_name
from processor.normalizer import NormalizedSnapshot, normalize_crawl_result
from processor.korean_filter import is_korean_ad, clean_advertiser_name
from processor.creative_hasher import compute_creative_hash, compute_text_hash
from processor.extra_data_normalizer import normalize_extra_data
from processor.ad_product_classifier import classify_ad_product
from processor.dedup import find_existing_ad, update_seen
from processor.landing_cache import get_cached_brand, cache_landing_result, _extract_domain

CHANNEL_VERIFICATION_DEFAULTS: dict[str, tuple[str, str]] = {
    "naver_search": ("unverified", "channel_default"),
    "kakao_da": ("unverified", "channel_default"),
}
GLOBAL_VERIFICATION_DEFAULT = ("unknown", "not_collected")


def _resolve_verification_fields(channel: str, ad) -> tuple[str, str, dict]:
    extra_data = dict(ad.extra_data or {})

    verification_status = ad.verification_status or extra_data.get("verification_status")
    verification_source = ad.verification_source or extra_data.get("verification_source")

    if isinstance(verification_status, str):
        verification_status = verification_status.strip() or None
    if isinstance(verification_source, str):
        verification_source = verification_source.strip() or None

    fallback_status, fallback_source = CHANNEL_VERIFICATION_DEFAULTS.get(
        channel,
        GLOBAL_VERIFICATION_DEFAULT,
    )
    if verification_status is None:
        verification_status = fallback_status
    if verification_source is None:
        verification_source = fallback_source

    extra_data.setdefault("verification_status", verification_status)
    extra_data.setdefault("verification_source", verification_source)
    return verification_status, verification_source, extra_data


async def _check_duplicate(session: AsyncSession, creative_hash: str | None, channel: str) -> bool:
    """같은 creative_hash가 이미 다른 채널에서 저장되었는지 확인.

    동일 채널 내 중복은 허용 (같은 광고가 여러 세션에 노출될 수 있음).
    다른 채널 간 중복만 차단 (YouTube Ads + YouTube Surf 등).
    """
    if not creative_hash:
        return False
    result = await session.execute(
        select(AdDetail.id).where(
            AdDetail.creative_hash == creative_hash,
            AdDetail.snapshot_id.in_(
                select(AdSnapshot.id).where(AdSnapshot.channel != channel)
            ),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def save_crawl_result(session: AsyncSession, raw: dict) -> AdSnapshot | None:
    """크롤링 원본 결과를 정규화 후 DB에 적재.

    Args:
        session: DB 세션
        raw: 크롤러가 반환한 원본 dict

    Returns:
        저장된 AdSnapshot 또는 None (에러 시)
    """
    try:
        normalized = normalize_crawl_result(raw)
    except Exception as e:
        logger.error(f"[pipeline] 정규화 실패: {e}")
        return None

    # keyword_id 조회 (캐시 사용 — N+1 쿼리 방지)
    keyword_id = await _get_keyword_id(session, normalized.keyword)
    if not keyword_id:
        logger.warning(f"[pipeline] 키워드 '{normalized.keyword}' DB에 없음, 스킵")
        return None

    # persona_id 조회 (캐시 사용)
    persona_id = await _get_persona_id(session, normalized.persona_code)
    if not persona_id:
        logger.warning(f"[pipeline] 페르소나 '{normalized.persona_code}' DB에 없음, 스킵")
        return None

    # AdSnapshot 생성 (채널명 정규화: facebook/instagram → meta)
    from processor.channel_utils import CHANNEL_DISPLAY_NORMALIZE
    save_channel = CHANNEL_DISPLAY_NORMALIZE.get(normalized.channel, normalized.channel)
    snapshot = AdSnapshot(
        keyword_id=keyword_id,
        persona_id=persona_id,
        device=normalized.device,
        channel=save_channel,
        captured_at=normalized.captured_at,
        page_url=normalized.page_url,
        screenshot_path=normalized.screenshot_path,
        ad_count=len(normalized.ads),
        crawl_duration_ms=normalized.crawl_duration_ms,
    )
    session.add(snapshot)
    await session.flush()

    # AdDetail 생성 + Phase 3 분류 + 광고주명 검증
    rejected_count = 0
    korean_filtered = 0
    no_url_filtered = 0
    inhouse_filtered = 0
    for ad in normalized.ads:
        # URL 필수: 광고주 URL 없으면 광고주 식별 불가 → 제외
        if not ad.url or not ad.url.strip():
            no_url_filtered += 1
            continue

        # 한글 필터: 한국 시장 광고만 저장 (접촉형 채널은 면제)
        if not is_korean_ad(ad.ad_text, ad.advertiser_name, ad.brand, ad.ad_description,
                            channel=normalized.channel):
            korean_filtered += 1
            continue

        # 광고주명 검증
        name_verification = verify_advertiser_name(ad.advertiser_name)
        original_name = ad.advertiser_name

        if name_verification.quality == NameQuality.REJECTED:
            # 가비지 이름 → 원본 보존하되 advertiser_name 제거
            rejected_count += 1
            ad.advertiser_name = None
            ad.extra_data = {
                **(ad.extra_data or {}),
                "original_advertiser_name": name_verification.original_name,
                "rejection_reason": name_verification.rejection_reason,
            }
        elif name_verification.cleaned_name:
            ad.advertiser_name = name_verification.cleaned_name

        verification_status, verification_source, extra_data = _resolve_verification_fields(
            normalized.channel,
            ad,
        )

        # 거부된 이름 → verification_status 오버라이드
        if name_verification.quality == NameQuality.REJECTED:
            verification_status = "rejected"
            verification_source = f"name_quality:{name_verification.rejection_reason}"

        # 광고 분류 (마커/인하우스/리타겟팅/위치)
        classification = classify_ad(
            channel=normalized.channel,
            url=ad.url,
            ad_text=ad.ad_text,
            advertiser_name=ad.advertiser_name,
            device=normalized.device,
            position=ad.position,
            ad_type=ad.ad_type,
            ad_placement=ad.ad_placement,
            extra_data=ad.extra_data,
        )

        # 인하우스(플랫폼 내부) 광고 제외 — 네이버페이, 해피빈 등은 광고주가 아님
        if classification.is_inhouse:
            inhouse_filtered += 1
            continue

        # extra_data 정규화
        extra_data = normalize_extra_data(extra_data, normalized.channel)

        # creative hash 계산 + 크롤러간 중복 체크
        c_hash = compute_creative_hash(ad.creative_image_path)
        if not c_hash:
            c_hash = compute_text_hash(ad.advertiser_name, ad.ad_text, ad.url)
        if c_hash and await _check_duplicate(session, c_hash, normalized.channel):
            continue  # 다른 채널에서 이미 수집된 광고 -> 스킵

        # 같은 채널 내 중복 -> seen_count만 업데이트
        existing_id = await find_existing_ad(
            session, normalized.channel, c_hash,
            ad.advertiser_name, ad.ad_text, ad.url,
        )
        if existing_id:
            await update_seen(session, existing_id, normalized.captured_at)
            continue

        # 광고상품 자동분류
        ad_raw = {
            "ad_type": ad.ad_type,
            "url": ad.url,
            "ad_text": ad.ad_text,
            "ad_placement": ad.ad_placement,
            "extra_data": ad.extra_data,
        }
        product_cls = classify_ad_product(normalized.channel, ad_raw)

        detail = AdDetail(
            snapshot_id=snapshot.id,
            persona_id=persona_id,
            advertiser_name_raw=original_name,
            brand=ad.brand,
            ad_text=ad.ad_text,
            ad_description=ad.ad_description,
            position=ad.position,
            url=ad.url,
            display_url=ad.display_url,
            ad_type=ad.ad_type,
            verification_status=verification_status,
            verification_source=verification_source,
            product_name=ad.product_name,
            product_category=ad.product_category,
            ad_placement=ad.ad_placement,
            promotion_type=ad.promotion_type,
            creative_image_path=ad.creative_image_path,
            creative_hash=c_hash,
            # Phase 3 분류 필드
            position_zone=classification.position_zone,
            is_inhouse=classification.is_inhouse,
            is_retargeted=classification.is_retargeted,
            retargeting_network=classification.retargeting_network,
            ad_marker_type=classification.ad_marker_type,
            # 마케팅 플랜 계층 필드
            campaign_purpose=getattr(ad, "campaign_purpose", None) or product_cls["campaign_purpose"],
            ad_format_type=getattr(ad, "ad_format_type", None) or product_cls["ad_format_type"],
            ad_product_name=getattr(ad, "ad_product_name", None) or product_cls["ad_product_name"],
            model_name=getattr(ad, "model_name", None),
            extra_data=extra_data,
            first_seen_at=normalized.captured_at,
            last_seen_at=normalized.captured_at,
            seen_count=1,
        )
        session.add(detail)

    await session.flush()

    # ── 랜딩 URL 도메인 추출 → 광고주 website 자동 업데이트 ──
    await _auto_update_advertiser_websites(session)

    log_msg = (
        f"[pipeline] DB 적재 완료: '{normalized.keyword}' "
        f"({normalized.channel}/{normalized.device}) "
        f"- 광고 {len(normalized.ads)}건"
    )
    if no_url_filtered:
        log_msg += f" (URL없음 {no_url_filtered}건)"
    if inhouse_filtered:
        log_msg += f" (하우스광고 {inhouse_filtered}건)"
    if korean_filtered:
        log_msg += f" (비한국 필터 {korean_filtered}건)"
    if rejected_count:
        log_msg += f" (광고주명 거부 {rejected_count}건)"
    logger.info(log_msg)
    return snapshot


# ── 트래킹 URL 패턴 (도메인 추출 시 제외) ──
_TRACKING_HOSTS = {
    "tivan.naver.com", "g.tivan.naver.com",
    "ader.naver.com", "adcr.naver.com",
    "searchad.naver.com", "ad.naver.com",
    "m.ad.search.naver.com", "siape.veta.naver.com",
    "ssl.pstatic.net",
    "ad.daum.net", "v.daum.net",
    "track.tiara.kakao.com",
    "adstransparency.google.com",
    "googleads.g.doubleclick.net", "pagead2.googlesyndication.com",
    "play.google.com", "apps.apple.com",
    "facebook.com", "business.facebook.com",
    "ads.tiktok.com",
}


def _extract_landing_domain(url: str) -> str | None:
    """광고 URL에서 실제 랜딩 도메인을 추출. 트래킹 URL이면 None."""
    if not url or not url.startswith("http"):
        return None
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        # 트래킹/인프라 도메인은 제외
        for tracking in _TRACKING_HOSTS:
            if tracking in host:
                return None
        if not host or len(host) < 4:
            return None
        return host
    except Exception:
        return None


async def _auto_update_advertiser_websites(session: AsyncSession):
    """방금 저장된 광고의 URL에서 도메인을 추출해 광고주 website 자동 업데이트.

    Rules:
    1. 광고 URL이 트래킹이 아닌 실제 도메인이면 추출
    2. extra_data에 original_landing_url이 있으면 그것도 시도
    3. 추출한 도메인을 landing_url_cache에 캐싱
    4. 광고주의 website가 비어있으면 자동 채움
    """
    from sqlalchemy import text as sa_text

    try:
        # 최근 적재된 광고 중 광고주에 website 없는 것 조회
        result = await session.execute(sa_text("""
            SELECT d.id, d.url, d.extra_data, d.advertiser_id, a.name
            FROM ad_details d
            JOIN advertisers a ON d.advertiser_id = a.id
            WHERE d.first_seen_at >= datetime('now', '-1 hour')
              AND (a.website IS NULL OR a.website = '')
              AND d.url IS NOT NULL AND d.url <> ''
            LIMIT 200
        """))
        rows = result.fetchall()

        for row in rows:
            ad_id, url, extra_data_str, adv_id, adv_name = row

            # 1. 메인 URL에서 도메인 추출 시도
            domain = _extract_landing_domain(url)

            # 2. extra_data의 original_landing_url에서도 시도
            if not domain and extra_data_str:
                try:
                    import json
                    ed = json.loads(extra_data_str) if isinstance(extra_data_str, str) else extra_data_str
                    landing_url = ed.get("original_landing_url") or ed.get("landing_url")
                    if landing_url:
                        domain = _extract_landing_domain(landing_url)
                except Exception:
                    pass

            if not domain:
                continue

            # 3. 캐시에 저장
            try:
                await cache_landing_result(
                    session, url=f"https://{domain}",
                    brand_name=adv_name, advertiser_id=adv_id,
                )
            except Exception:
                pass

            # 4. 광고주 website 업데이트
            await session.execute(sa_text(
                "UPDATE advertisers SET website = :website WHERE id = :id "
                "AND (website IS NULL OR website = '')"
            ), {"website": domain, "id": adv_id})

            logger.debug(f"[pipeline] 광고주 website 자동 업데이트: [{adv_id}] {adv_name} -> {domain}")

    except Exception as e:
        logger.debug(f"[pipeline] 광고주 website 자동 업데이트 에러 (무시): {e}")


async def _emit_event(event_type: str, data: dict):
    """이벤트 버스로 이벤트 발행 (import 실패 시 무시)."""
    try:
        from api.event_bus import event_bus
        await event_bus.publish(event_type, data)
    except Exception:
        pass  # 이벤트 발행 실패가 파이프라인을 중단시키지 않음


async def save_crawl_results(session: AsyncSession, results: list[dict]) -> int:
    """여러 크롤링 결과를 일괄 DB 적재.

    전체를 하나의 트랜잭션으로 래핑하여 부분 적재를 방지합니다.
    에러 발생 시 전체 롤백합니다.

    Returns:
        성공적으로 적재된 스냅샷 수
    """
    saved = 0
    channels_saved: dict[str, int] = {}
    try:
        async with session.begin():
            for raw in results:
                if raw.get("error"):
                    continue
                snapshot = await save_crawl_result(session, raw)
                if snapshot:
                    saved += 1
                    ch = snapshot.channel or "unknown"
                    channels_saved[ch] = channels_saved.get(ch, 0) + 1
    except Exception as e:
        logger.error(f"[pipeline] save_crawl_results 트랜잭션 실패, 롤백: {e}")
        raise

    # SSE 이벤트 발행 — 프론트엔드 자동 갱신 트리거
    if saved > 0:
        await _emit_event("crawl_complete", {
            "saved_snapshots": saved,
            "channels": channels_saved,
        })

    return saved
