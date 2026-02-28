"""Brand channel content pipeline -- save/update brand channel content to DB."""

from __future__ import annotations

import asyncio
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from loguru import logger
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from database.models import BrandChannelContent

_STORE_DIR = Path("stored_images") / "instagram"


async def _download_ig_thumbnail(content_id: str) -> str | None:
    """Download IG thumbnail via /p/{shortcode}/media/?size=l and save as WebP.

    Returns local file path on success, None on failure.
    """
    date_str = datetime.now().strftime("%Y%m%d")
    dest = _STORE_DIR / date_str / "thumbnail" / f"{content_id}.webp"
    if dest.exists():
        return str(dest)

    url = f"https://www.instagram.com/p/{content_id}/media/?size=l"
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with aiohttp.ClientSession(headers=headers) as sess:
            async with sess.get(url, timeout=timeout) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                if len(data) < 500:
                    return None

        loop = asyncio.get_event_loop()
        webp_bytes = await loop.run_in_executor(None, _convert_thumb, data)
        if not webp_bytes:
            return None

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(webp_bytes)
        return str(dest)
    except Exception as e:
        logger.debug(f"[brand_pipeline] IG thumbnail download failed {content_id}: {e}")
        return None


def _convert_thumb(data: bytes) -> bytes | None:
    """Convert raw image bytes to WebP thumbnail."""
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        max_dim = 600
        if img.width > max_dim or img.height > max_dim:
            ratio = min(max_dim / img.width, max_dim / img.height)
            img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WebP", quality=75, method=4)
        return buf.getvalue()
    except Exception:
        return None


async def save_brand_content(
    session: AsyncSession,
    advertiser_id: int,
    platform: str,
    channel_url: str,
    contents: list[dict],
) -> int:
    """Save brand channel content items to the database.

    For each content item:
    - Check if (platform, content_id) already exists.
    - If not: INSERT new BrandChannelContent row.
    - If yes: UPDATE view_count, like_count, updated_at.

    For Instagram content, downloads thumbnails locally to avoid CDN URL expiry.

    Returns count of newly inserted items.
    """
    new_count = 0

    for item in contents:
        content_id = _get_content_id(platform, item)
        if not content_id:
            logger.debug(f"Skipping item with no content_id: {item}")
            continue

        # Check for existing record
        result = await session.execute(
            select(BrandChannelContent).where(
                BrandChannelContent.platform == platform,
                BrandChannelContent.content_id == content_id,
            )
        )
        existing = result.scalar_one_or_none()

        # Download IG thumbnails locally (CDN URLs expire)
        local_path = None
        if platform == "instagram" and content_id:
            local_path = await _download_ig_thumbnail(content_id)

        if existing:
            # Update mutable fields
            view_count = item.get("view_count")
            like_count = item.get("like_count")
            if view_count is not None:
                existing.view_count = view_count
            if like_count is not None:
                existing.like_count = like_count
            # Refresh thumbnail_url with fresh CDN URL
            thumb = item.get("thumbnail_url")
            if thumb:
                existing.thumbnail_url = thumb[:500]
            # Update local image path
            if local_path:
                ed = existing.extra_data or {}
                if isinstance(ed, str):
                    try:
                        ed = json.loads(ed)
                    except (json.JSONDecodeError, TypeError):
                        ed = {}
                ed["local_image_path"] = local_path
                existing.extra_data = ed
                flag_modified(existing, "extra_data")
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # Detect ad content indicators
            from crawler.brand_monitor import BrandChannelMonitor

            ad_info = BrandChannelMonitor.detect_ad_content(item)

            # Parse upload date
            upload_date = _parse_upload_date(item)

            extra = {}
            if local_path:
                extra["local_image_path"] = local_path

            row = BrandChannelContent(
                advertiser_id=advertiser_id,
                platform=platform,
                channel_url=channel_url,
                content_id=content_id,
                content_type=item.get("content_type"),
                title=item.get("title") or item.get("caption", "")[:500] if item.get("caption") else item.get("title"),
                description=item.get("caption"),
                thumbnail_url=item.get("thumbnail_url", "")[:500] if item.get("thumbnail_url") else None,
                upload_date=upload_date,
                view_count=item.get("view_count"),
                like_count=item.get("like_count"),
                duration_seconds=item.get("duration_seconds"),
                is_ad_content=ad_info.get("has_sponsored_tag", False),
                ad_indicators=ad_info if ad_info.get("ad_keywords_found") else None,
                extra_data=extra if extra else None,
                discovered_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(row)
            new_count += 1

    await session.flush()
    return new_count


def _get_content_id(platform: str, item: dict) -> str | None:
    """Extract the content ID based on platform."""
    if platform == "youtube":
        return item.get("video_id")
    elif platform == "instagram":
        return item.get("shortcode")
    return item.get("content_id")


def _parse_upload_date(item: dict) -> datetime | None:
    """Try to parse upload date from various fields."""
    # Direct upload_date field (ISO format)
    ud = item.get("upload_date")
    if isinstance(ud, datetime):
        return ud
    if isinstance(ud, str) and ud:
        try:
            return datetime.fromisoformat(ud.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    # From timestamp
    ts = item.get("timestamp")
    if ts and isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError):
            pass

    return None
