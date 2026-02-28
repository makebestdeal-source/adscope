"""Data washing layer -- staging -> validation -> promote to live DB.

Crawled ads go through staging_ads first, get washed (validated/filtered),
and only approved ads are promoted to the live ad_details table.
"""

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AdDetail, AdSnapshot, Advertiser, Industry, Keyword, Persona, StagingAd,
)
from processor.korean_filter import is_korean_ad
from processor.advertiser_name_cleaner import clean_name_for_pipeline
from processor.advertiser_verifier import NameQuality, verify_advertiser_name
from processor.advertiser_link_collector import extract_website_from_url
from processor.creative_hasher import compute_creative_hash, compute_text_hash
from processor.extra_data_normalizer import normalize_extra_data
from processor.channel_utils import is_contact as _is_contact
from processor.dedup import find_existing_ad, update_seen
from crawler.personas.profiles import PERSONAS


AUTO_PROMOTE = os.getenv("STAGING_AUTO_PROMOTE", "true").lower() in ("1", "true", "yes")


# ── Wash rules ──

def _validate_url(url: str | None) -> bool:
    """URL is required for ad recognition (광고주 식별 필수)."""
    if not url or not url.strip():
        return False
    return url.startswith(("http://", "https://")) and len(url) < 2000


def _validate_timestamp(captured_at: Any) -> bool:
    """Timestamp should be within 7 days of now."""
    if not captured_at:
        return True
    if isinstance(captured_at, str):
        try:
            captured_at = datetime.fromisoformat(captured_at)
        except (ValueError, TypeError):
            return False
    now = datetime.utcnow()
    return now - timedelta(days=7) <= captured_at <= now + timedelta(hours=1)


def wash_single_ad(ad: dict, channel: str) -> dict:
    """Wash a single ad dict. Returns {status, rejection_reason, wash_score, resolved_name}."""
    score = 1.0
    reasons = []

    ad_text = ad.get("ad_text")
    adv_name = ad.get("advertiser_name")
    brand = ad.get("brand")
    ad_desc = ad.get("ad_description")

    # 1. Korean filter (접촉형 채널은 면제 — 한국 사용자 기기에서 수집)
    if not is_korean_ad(ad_text, adv_name, brand, ad_desc, channel=channel):
        return {
            "status": "rejected",
            "rejection_reason": "korean_filter_fail",
            "wash_score": 0.0,
            "resolved_name": adv_name,
        }

    # 2. Advertiser name verification
    resolved_name = adv_name
    if adv_name:
        vr = verify_advertiser_name(adv_name)
        if vr.quality == NameQuality.REJECTED:
            reasons.append(f"name_rejected:{vr.rejection_reason}")
            score -= 0.3
            resolved_name = None
        elif vr.quality == NameQuality.CLEANED:
            resolved_name = vr.cleaned_name
            score -= 0.05

    # 3. URL validation (URL 필수 — 없으면 광고주 식별 불가)
    url = ad.get("url")
    if not _validate_url(url):
        reasons.append("missing_or_invalid_url")
        score -= 0.5

    # 4. Text length sanity
    if ad_text and len(ad_text) > 5000:
        reasons.append("text_too_long")
        score -= 0.1

    # 5. Extra data normalization (enrich, not reject)
    raw_extra = ad.get("extra_data") or {}
    ad["extra_data"] = normalize_extra_data(raw_extra, channel)

    # 6. Creative hash
    c_hash = compute_creative_hash(ad.get("creative_image_path"))
    if not c_hash:
        c_hash = compute_text_hash(adv_name, ad_text, url)
    ad["_creative_hash"] = c_hash

    # Decision
    score = max(0.0, min(1.0, score))
    if score < 0.3:
        status = "rejected"
    elif score < 0.6:
        status = "quarantine"
    else:
        status = "approved"

    return {
        "status": status,
        "rejection_reason": "; ".join(reasons) if reasons else None,
        "wash_score": round(score, 2),
        "resolved_name": resolved_name,
    }


# ── Batch operations ──

async def save_to_staging(
    session: AsyncSession,
    channel_name: str,
    result: dict,
    keyword_text: str,
    persona_code: str,
    device_type: str,
) -> tuple[str, int]:
    """Save crawl result to staging_ads. Returns (batch_id, count)."""
    batch_id = str(uuid.uuid4())
    ads = result.get("ads", [])
    count = 0

    # Parse captured_at to datetime object (SQLite requires it)
    raw_ts = result.get("captured_at")
    if isinstance(raw_ts, str):
        try:
            captured_at = datetime.fromisoformat(raw_ts)
        except (ValueError, TypeError):
            captured_at = datetime.utcnow()
    elif isinstance(raw_ts, datetime):
        captured_at = raw_ts
    else:
        captured_at = datetime.utcnow()

    for ad in ads:
        staging = StagingAd(
            batch_id=batch_id,
            channel=channel_name,
            persona_code=persona_code,
            keyword=keyword_text,
            device=device_type,
            page_url=result.get("page_url", ""),
            captured_at=captured_at,
            raw_payload=ad,
            status="pending",
        )
        session.add(staging)
        count += 1

    if count:
        await session.commit()

    return batch_id, count


async def wash_batch(session: AsyncSession, batch_id: str) -> dict:
    """Run washing rules on all pending ads in a batch.

    Returns {approved, rejected, quarantine, total}.
    """
    result = await session.execute(
        select(StagingAd).where(
            StagingAd.batch_id == batch_id,
            StagingAd.status == "pending",
        )
    )
    rows = result.scalars().all()

    stats = {"approved": 0, "rejected": 0, "quarantine": 0, "total": len(rows)}

    for row in rows:
        ad = row.raw_payload or {}
        wash = wash_single_ad(ad, row.channel)

        row.status = wash["status"]
        row.rejection_reason = wash.get("rejection_reason")
        row.wash_score = wash.get("wash_score")
        row.resolved_advertiser_name = wash.get("resolved_name")
        row.processed_at = datetime.utcnow()

        # Store washed extra_data and hash back
        if "_creative_hash" in ad:
            payload = dict(row.raw_payload)
            payload["_creative_hash"] = ad["_creative_hash"]
            payload["extra_data"] = ad.get("extra_data", {})
            row.raw_payload = payload

        stats[wash["status"]] += 1

    await session.commit()
    return stats


async def promote_approved(session: AsyncSession, batch_id: str) -> dict:
    """Promote approved staging ads to live ad_details.

    Returns {promoted, errors, snapshot_id}.
    """
    result = await session.execute(
        select(StagingAd).where(
            StagingAd.batch_id == batch_id,
            StagingAd.status == "approved",
            StagingAd.promoted_at.is_(None),
        )
    )
    rows = result.scalars().all()
    if not rows:
        return {"promoted": 0, "errors": 0, "snapshot_id": None}

    # Group by (channel, keyword, persona_code, device) for snapshot creation
    first = rows[0]

    # Ensure keyword exists
    kw_result = await session.execute(
        select(Keyword).where(Keyword.keyword == first.keyword)
    )
    kw = kw_result.scalar_one_or_none()
    if not kw:
        ind_result = await session.execute(
            select(Industry).where(Industry.name == "기타")
        )
        industry = ind_result.scalar_one_or_none()
        if not industry:
            industry = Industry(name="기타")
            session.add(industry)
            await session.flush()
        kw = Keyword(keyword=first.keyword or "unknown", industry_id=industry.id, is_active=True)
        session.add(kw)
        await session.flush()

    # Ensure persona exists (카탈로그 채널은 persona_code=None → M30 기본값)
    persona_row = None
    _pc = first.persona_code or "M30"
    if _pc:
        p_result = await session.execute(
            select(Persona).where(Persona.code == _pc)
        )
        persona_row = p_result.scalar_one_or_none()
        if not persona_row:
            _p = PERSONAS.get(_pc)
            _age = str(_p.age_group).replace("\ub300", "") if _p and _p.age_group else "30"  # "10\ub300" -> "10"
            _gender = "F" if (_p and _p.gender and "\uc5ec" in _p.gender) else ("M" if _pc[0:1] != "F" else "F")  # "\uc5ec\uc131" -> F
            persona_row = Persona(code=_pc, age_group=_age, gender=_gender, login_type="none")
            session.add(persona_row)
            await session.flush()

    # Create snapshot
    snap = AdSnapshot(
        keyword_id=kw.id,
        persona_id=persona_row.id if persona_row else None,
        device=first.device or "pc",
        channel=first.channel,
        captured_at=first.captured_at or datetime.utcnow(),
        page_url=first.page_url,
        ad_count=len(rows),
    )
    session.add(snap)
    await session.flush()

    promoted = 0
    deduped = 0
    errors = 0

    for row in rows:
        try:
            ad = row.raw_payload or {}
            adv_name = row.resolved_advertiser_name or ad.get("advertiser_name")
            # 광고카피/URL 제거
            if adv_name:
                adv_name = clean_name_for_pipeline(adv_name)

            c_hash = ad.get("_creative_hash")

            # Dedup check: if same ad already exists in this channel, just update seen_count
            existing_id = await find_existing_ad(
                session, row.channel, c_hash,
                adv_name, ad.get("ad_text"), ad.get("url"),
            )
            if existing_id:
                await update_seen(session, existing_id, row.captured_at)
                row.promoted_at = datetime.utcnow()
                row.promoted_ad_detail_id = existing_id
                row.status = "deduped"
                deduped += 1
                continue

            # Lookup/create advertiser
            advertiser_id = None
            if adv_name:
                adv_result = await session.execute(
                    select(Advertiser).where(Advertiser.name == adv_name)
                )
                adv = adv_result.scalar_one_or_none()
                if not adv:
                    website = extract_website_from_url(
                        ad.get("url"), ad.get("display_url")
                    )
                    adv = Advertiser(name=adv_name, website=website)
                    session.add(adv)
                    await session.flush()
                advertiser_id = adv.id

            extra = ad.get("extra_data") or {}
            now = datetime.utcnow()

            detail = AdDetail(
                snapshot_id=snap.id,
                persona_id=persona_row.id,
                advertiser_id=advertiser_id,
                advertiser_name_raw=adv_name,
                ad_text=ad.get("ad_text"),
                ad_description=ad.get("ad_description"),
                position=ad.get("position"),
                url=ad.get("url"),
                display_url=ad.get("display_url"),
                ad_type=ad.get("ad_type"),
                verification_status=ad.get("verification_status"),
                verification_source=ad.get("verification_source"),
                creative_image_path=ad.get("creative_image_path"),
                creative_hash=c_hash,
                extra_data=extra,
                is_contact=_is_contact(row.channel, ad),
                first_seen_at=row.captured_at or now,
                last_seen_at=row.captured_at or now,
                seen_count=1,
            )
            session.add(detail)
            await session.flush()

            row.promoted_at = now
            row.promoted_ad_detail_id = detail.id
            row.resolved_advertiser_id = advertiser_id
            promoted += 1

        except Exception as e:
            errors += 1
            logger.warning("promote error for staging_ad {}: {}", row.id, str(e)[:100])

    await session.commit()
    return {"promoted": promoted, "deduped": deduped, "errors": errors, "snapshot_id": snap.id}


async def wash_and_promote(
    session: AsyncSession,
    batch_id: str,
) -> dict:
    """Full pipeline: wash batch + auto-promote approved ads.

    Returns combined stats.
    """
    wash_stats = await wash_batch(session, batch_id)

    promote_stats = {"promoted": 0, "errors": 0, "snapshot_id": None}
    if AUTO_PROMOTE and wash_stats["approved"] > 0:
        promote_stats = await promote_approved(session, batch_id)

    return {
        "batch_id": batch_id,
        "wash": wash_stats,
        "promote": promote_stats,
    }
