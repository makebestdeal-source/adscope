"""Social channel auto-discoverer -- scrape advertiser websites for social media links.

Visits advertiser.website and extracts YouTube, Instagram, Facebook, TikTok links
from HTML (footer, header, meta tags, og tags, schema.org markup).
No DOM-selector ad detection -- purely link extraction from HTML source.
"""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urljoin, urlparse

import httpx
from loguru import logger
from sqlalchemy import func, or_, select, update

from database import async_session
from database.models import Advertiser

# ── Social URL patterns ──

_SOCIAL_PATTERNS: dict[str, re.Pattern] = {
    "youtube": re.compile(
        r"(?:https?://)?(?:www\.)?youtube\.com/(?:@|channel/|c/|user/)([A-Za-z0-9_\-]+)",
        re.I,
    ),
    "instagram": re.compile(
        r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?",
        re.I,
    ),
    "facebook": re.compile(
        r"(?:https?://)?(?:www\.)?facebook\.com/(?:pages/)?([A-Za-z0-9_.]+)/?",
        re.I,
    ),
    "tiktok": re.compile(
        r"(?:https?://)?(?:www\.)?tiktok\.com/@([A-Za-z0-9_.]+)/?",
        re.I,
    ),
}

# Skip invalid handles
_INVALID_HANDLES = {
    "p", "reel", "reels", "stories", "watch", "ads", "pages", "channel",
    "c", "user", "explore", "about", "help", "privacy", "terms",
    "share", "hashtag", "sharer", "dialog", "login", "signup",
    "settings", "direct", "accounts", "intent", "search",
}

# Post-level URL indicators (skip these)
_POST_INDICATORS = {
    "/p/", "/reel/", "/reels/", "/stories/", "/status/", "/watch?v=",
    "/shorts/", "/video/", "/photo/", "/posts/",
}


def _extract_social_urls_from_html(html: str, base_url: str) -> dict[str, str]:
    """Extract social media profile URLs from HTML content.

    Looks for:
    1. <a href="..."> links containing social platform domains
    2. og:see_also meta tags
    3. Schema.org sameAs properties
    """
    results: dict[str, str] = {}

    # Find all href values
    href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.I)
    all_urls: list[str] = href_pattern.findall(html)

    # Also look for og:see_also and schema.org sameAs
    og_pattern = re.compile(
        r'<meta\s+[^>]*property=["\']og:see_also["\'][^>]*content=["\']([^"\']+)["\']',
        re.I,
    )
    all_urls.extend(og_pattern.findall(html))

    # Schema.org sameAs (JSON-LD)
    jsonld_pattern = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)
    for match in jsonld_pattern.findall(html):
        try:
            data = json.loads(match)
            if isinstance(data, dict):
                same_as = data.get("sameAs", [])
                if isinstance(same_as, str):
                    same_as = [same_as]
                if isinstance(same_as, list):
                    all_urls.extend(str(u) for u in same_as if isinstance(u, str))
        except (json.JSONDecodeError, TypeError):
            pass

    # Process each URL
    for url in all_urls:
        if not url or not isinstance(url, str):
            continue

        # Make absolute URL
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = urljoin(base_url, url)

        # Check if URL is a post-level link
        is_post = any(ind in url for ind in _POST_INDICATORS)
        if is_post:
            continue

        for platform, pattern in _SOCIAL_PATTERNS.items():
            if platform in results:
                continue
            m = pattern.search(url)
            if m:
                handle = m.group(1)
                if handle.lower() in _INVALID_HANDLES:
                    continue
                # Store full URL for YouTube, handle for others
                if platform == "youtube":
                    results[platform] = url if url.startswith("http") else f"https://www.youtube.com/@{handle}"
                elif platform == "instagram":
                    results[platform] = handle
                elif platform == "facebook":
                    results[platform] = handle
                elif platform == "tiktok":
                    results[platform] = f"@{handle}"

    return results


async def _fetch_website(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch website HTML with timeout and error handling."""
    if not url:
        return None
    if not url.startswith("http"):
        url = f"https://{url}"

    try:
        resp = await client.get(url, follow_redirects=True, timeout=15.0)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass

    # Try http if https failed
    if url.startswith("https://"):
        try:
            http_url = url.replace("https://", "http://", 1)
            resp = await client.get(http_url, follow_redirects=True, timeout=10.0)
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass

    return None


async def discover_social_channels(limit: int = 100) -> dict:
    """Discover social channels by scraping advertiser websites.

    Targets advertisers that have a website but missing official_channels.
    """
    stats = {"processed": 0, "discovered": 0, "channels_added": 0, "errors": 0}

    async with async_session() as session:
        # Find advertisers with website but no/empty official_channels
        stmt = (
            select(Advertiser.id, Advertiser.name, Advertiser.website, Advertiser.official_channels)
            .where(
                Advertiser.website.isnot(None),
                Advertiser.website != "",
                or_(
                    Advertiser.official_channels.is_(None),
                    Advertiser.official_channels == "{}",
                    Advertiser.official_channels == "null",
                    Advertiser.official_channels == "",
                ),
            )
            .order_by(func.random())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    if not rows:
        logger.info("[social_discovery] No advertisers to process (all have channels)")
        return stats

    logger.info("[social_discovery] Processing {} advertisers", len(rows))

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    }

    async with httpx.AsyncClient(headers=headers, verify=False) as client:
        # Process in batches of 10 (concurrent)
        batch_size = 10
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            tasks = []
            for adv_id, adv_name, website, current_channels in batch:
                tasks.append(_process_one_advertiser(client, adv_id, adv_name, website, current_channels))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    stats["errors"] += 1
                    continue
                stats["processed"] += 1
                if result and result.get("new_channels"):
                    stats["discovered"] += 1
                    stats["channels_added"] += len(result["new_channels"])

            # Small delay between batches
            if i + batch_size < len(rows):
                await asyncio.sleep(1)

    logger.info(
        "[social_discovery] Done: processed={}, discovered={}, channels_added={}, errors={}",
        stats["processed"], stats["discovered"], stats["channels_added"], stats["errors"],
    )
    return stats


async def _process_one_advertiser(
    client: httpx.AsyncClient,
    adv_id: int,
    adv_name: str,
    website: str,
    current_channels,
) -> dict | None:
    """Fetch website and extract social links for one advertiser."""
    html = await _fetch_website(client, website)
    if not html:
        return None

    social_links = _extract_social_urls_from_html(html, website)
    if not social_links:
        return None

    # Parse existing channels
    existing: dict = {}
    if current_channels:
        if isinstance(current_channels, str):
            try:
                existing = json.loads(current_channels)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        elif isinstance(current_channels, dict):
            existing = current_channels

    # Merge (non-destructive)
    new_channels: dict[str, str] = {}
    merged = {**existing}
    for platform, handle in social_links.items():
        if platform not in merged:
            merged[platform] = handle
            new_channels[platform] = handle

    if not new_channels:
        return None

    # Update DB
    async with async_session() as session:
        await session.execute(
            update(Advertiser)
            .where(Advertiser.id == adv_id)
            .values(official_channels=merged)
        )
        await session.commit()

    logger.debug("[social_discovery] {} -> {}", adv_name, new_channels)
    return {"advertiser_id": adv_id, "new_channels": new_channels}
