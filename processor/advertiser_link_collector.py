"""Advertiser link auto-collector -- extract website & social links from ad_details.

ad_details.url / display_url / extra_data  ->  advertiser.website + official_channels.
No external web requests. All data comes from already-crawled ad_details rows.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from database.models import AdDetail, AdSnapshot, Advertiser

# ── Ad-infra domains to exclude (not real advertiser websites) ──

_AD_INFRA_DOMAINS: set[str] = {
    # Google / GDN
    "adstransparency.google.com",
    "googleads.g.doubleclick.net",
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "google.com",
    "google.co.kr",
    "gstatic.com",
    "googleapis.com",
    "youtube.com",  # YouTube itself is infra, not a website
    "youtu.be",
    # Naver
    "ader.naver.com",
    "g.tivan.naver.com",
    "siape.veta.naver.com",
    "ssl.pstatic.net",
    "pstatic.net",
    "naver.com",
    "naver.me",
    "navercorp.com",
    # Kakao / Daum
    "tr.ad.daum.net",
    "ad.daum.net",
    "daum.net",
    "kakao.com",
    "kakaocorp.com",
    # Meta
    "facebook.com",
    "instagram.com",
    "fb.com",
    "fbcdn.net",
    "meta.com",
    # TikTok
    "ads.tiktok.com",
    "tiktok.com",
    # General ad trackers
    "criteo.com",
    "criteo.net",
    "adroll.com",
    "rtbhouse.com",
    "mobon.net",
    "openx.net",
    "appsflyer.com",
    "adjust.com",
    "branch.io",
    "app.link",
    # CDN / tracking
    "cloudfront.net",
    "akamaized.net",
    "akamai.net",
    "amazonaws.com",
}

# Social platform patterns -> official_channels key
_SOCIAL_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    # Instagram handle from URL
    ("instagram", "instagram.com", re.compile(
        r"instagram\.com/(?:p/|reel/|stories/)?([A-Za-z0-9_.]+)", re.I
    )),
    # YouTube channel from URL
    ("youtube", "youtube.com", re.compile(
        r"youtube\.com/(?:@|channel/|c/|user/)?([A-Za-z0-9_\-]+)", re.I
    )),
    # Facebook page from URL
    ("facebook", "facebook.com", re.compile(
        r"facebook\.com/(?:pages/)?([A-Za-z0-9_.]+)", re.I
    )),
    # TikTok handle
    ("tiktok", "tiktok.com", re.compile(
        r"tiktok\.com/@([A-Za-z0-9_.]+)", re.I
    )),
]

# URL parts that indicate social page (not individual posts)
_SOCIAL_POST_INDICATORS = {
    "/p/", "/reel/", "/stories/", "/status/", "/watch?v=",
    "/shorts/", "/video/", "/photo/",
}


def _extract_domain(url: str) -> str | None:
    """Extract clean domain from URL, stripping www. prefix."""
    if not url:
        return None
    try:
        if "://" not in url:
            url = f"https://{url}"
        parsed = urlparse(url)
        domain = (parsed.netloc or "").lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain if domain else None
    except Exception:
        return None


def _is_ad_infra(domain: str) -> bool:
    """Check if a domain belongs to ad infrastructure (not a real website)."""
    if not domain:
        return True
    # Exact match
    if domain in _AD_INFRA_DOMAINS:
        return True
    # Subdomain match: check if any infra domain is a suffix
    for infra in _AD_INFRA_DOMAINS:
        if domain.endswith(f".{infra}"):
            return True
    return False


def _extract_root_domain(url: str) -> str | None:
    """Extract root domain (e.g., 'shop.samsung.com' -> 'samsung.com')."""
    domain = _extract_domain(url)
    if not domain:
        return None
    parts = domain.split(".")
    if len(parts) >= 2:
        # Handle .co.kr, .go.kr etc.
        if len(parts) >= 3 and parts[-2] in ("co", "go", "or", "ac", "ne", "re"):
            return ".".join(parts[-3:])
        return ".".join(parts[-2:])
    return domain


def _clean_url_for_website(url: str) -> str | None:
    """Clean a URL to produce a website root (https://domain.com)."""
    domain = _extract_domain(url)
    if not domain or _is_ad_infra(domain):
        return None
    # Build clean website URL
    return f"https://{domain}"


def _extract_social_handles(urls: list[str]) -> dict[str, str]:
    """Extract social media handles from a list of URLs.

    Returns:
        {"instagram": "handle", "youtube": "@channel", ...}
    """
    handles: dict[str, str] = {}
    for url in urls:
        if not url:
            continue
        # Skip post-level URLs (we want profile/page URLs)
        is_post = any(indicator in url for indicator in _SOCIAL_POST_INDICATORS)
        for platform, domain_hint, pattern in _SOCIAL_PATTERNS:
            if platform in handles:
                continue  # Already found
            if domain_hint not in url.lower():
                continue
            m = pattern.search(url)
            if m:
                handle = m.group(1)
                # Filter out generic/invalid handles
                if handle.lower() in ("p", "reel", "stories", "watch", "ads",
                                       "pages", "channel", "c", "user",
                                       "explore", "about", "help"):
                    continue
                if is_post and platform in ("instagram", "facebook"):
                    continue  # Don't extract handle from individual posts
                handles[platform] = handle
    return handles


def extract_website_from_ads(
    ad_rows: list[dict],
) -> tuple[str | None, dict[str, str]]:
    """Extract the best website URL and social handles from ad detail rows.

    Args:
        ad_rows: list of dicts with keys: url, display_url, extra_data

    Returns:
        (website_url, official_channels_dict)
    """
    candidate_urls: list[str] = []
    all_urls: list[str] = []

    for row in ad_rows:
        url = row.get("url") or ""
        display_url = row.get("display_url") or ""
        extra_data = row.get("extra_data")

        # Parse extra_data if string
        if isinstance(extra_data, str):
            try:
                extra_data = json.loads(extra_data)
            except (json.JSONDecodeError, TypeError):
                extra_data = {}
        if not isinstance(extra_data, dict):
            extra_data = {}

        # Collect all URLs for social handle extraction
        if url:
            all_urls.append(url)
        if display_url:
            all_urls.append(display_url if "://" in display_url else f"https://{display_url}")

        # Redirect URLs from extra_data
        redirect_urls = extra_data.get("redirect_urls", [])
        if isinstance(redirect_urls, list):
            for r in redirect_urls:
                if isinstance(r, str) and r:
                    all_urls.append(r)

        # click_url from naver_da
        click_url = extra_data.get("click_url", "")
        if click_url:
            all_urls.append(click_url)

        # landing_analysis.url
        landing = extra_data.get("landing_analysis", {})
        if isinstance(landing, dict):
            landing_url = landing.get("url", "")
            if landing_url:
                all_urls.append(landing_url)

        # display_url is the most reliable for naver_search
        if display_url and not _is_ad_infra(_extract_domain(
                display_url if "://" in display_url else f"https://{display_url}")):
            candidate_urls.append(
                display_url if "://" in display_url else f"https://{display_url}"
            )

        # Main URL if not ad infra
        if url and not _is_ad_infra(_extract_domain(url)):
            candidate_urls.append(url)

    # ── Determine website ──
    website: str | None = None

    # Score candidates by frequency (most common domain wins)
    domain_counts: dict[str, tuple[str, int]] = {}
    for u in candidate_urls:
        d = _extract_domain(u)
        if d and not _is_ad_infra(d):
            if d not in domain_counts:
                domain_counts[d] = (u, 0)
            domain_counts[d] = (domain_counts[d][0], domain_counts[d][1] + 1)

    if domain_counts:
        # Pick the domain with the highest count
        best_domain = max(domain_counts, key=lambda d: domain_counts[d][1])
        website = f"https://{best_domain}"

    # ── Extract social handles ──
    social_handles = _extract_social_handles(all_urls)

    return website, social_handles


async def collect_advertiser_links(limit: int = 50) -> dict:
    """Collect website/official_channels for advertisers that have none.

    Extracts URLs from existing ad_details rows -- no external web requests.

    Args:
        limit: max number of advertisers to process per run

    Returns:
        {"processed": int, "website_set": int, "channels_set": int}
    """
    stats = {"processed": 0, "website_set": 0, "channels_set": 0}

    async with async_session() as session:
        # Find advertisers with NULL website, ordered by ad_detail count (most ads first)
        adv_query = (
            select(
                Advertiser.id,
                Advertiser.name,
                Advertiser.website,
                Advertiser.official_channels,
                func.count(AdDetail.id).label("ad_count"),
            )
            .outerjoin(AdDetail, AdDetail.advertiser_id == Advertiser.id)
            .where(
                (Advertiser.website.is_(None)) | (Advertiser.website == "")
            )
            .group_by(Advertiser.id)
            .order_by(func.count(AdDetail.id).desc())
            .limit(limit)
        )
        adv_rows = (await session.execute(adv_query)).all()

        for adv_id, adv_name, current_website, current_channels, ad_count in adv_rows:
            if ad_count == 0:
                continue

            # Fetch ad_details for this advertiser
            detail_query = (
                select(
                    AdDetail.url,
                    AdDetail.display_url,
                    AdDetail.extra_data,
                )
                .where(AdDetail.advertiser_id == adv_id)
                .limit(100)  # Sample up to 100 ads
            )
            details = (await session.execute(detail_query)).all()

            ad_rows_data = [
                {"url": r[0], "display_url": r[1], "extra_data": r[2]}
                for r in details
            ]

            website, social_handles = extract_website_from_ads(ad_rows_data)

            # Update advertiser
            update_values: dict = {}

            if website and not current_website:
                update_values["website"] = website
                stats["website_set"] += 1

            # Merge social handles into existing official_channels
            existing_channels: dict = {}
            if current_channels:
                if isinstance(current_channels, str):
                    try:
                        existing_channels = json.loads(current_channels)
                    except (json.JSONDecodeError, TypeError):
                        existing_channels = {}
                elif isinstance(current_channels, dict):
                    existing_channels = current_channels

            if social_handles:
                merged = {**existing_channels}
                new_added = False
                for platform, handle in social_handles.items():
                    if platform not in merged:
                        merged[platform] = handle
                        new_added = True
                if new_added:
                    update_values["official_channels"] = merged
                    stats["channels_set"] += 1

            if update_values:
                await session.execute(
                    update(Advertiser)
                    .where(Advertiser.id == adv_id)
                    .values(**update_values)
                )

            stats["processed"] += 1

        await session.commit()

    logger.info(
        f"[link_collector] Processed {stats['processed']} advertisers: "
        f"website set={stats['website_set']}, channels set={stats['channels_set']}"
    )
    return stats


async def collect_links_for_advertiser(
    session: AsyncSession,
    advertiser_id: int,
    force: bool = False,
) -> tuple[str | None, dict[str, str]]:
    """Collect links for a single advertiser within an existing session.

    Used by pipeline/campaign_builder when creating new advertisers.

    Args:
        session: Active DB session (caller manages transaction)
        advertiser_id: Target advertiser ID
        force: If True, overwrite existing website

    Returns:
        (website, social_handles) that were set
    """
    adv_result = await session.execute(
        select(Advertiser).where(Advertiser.id == advertiser_id)
    )
    advertiser = adv_result.scalar_one_or_none()
    if not advertiser:
        return None, {}

    # Skip if already has website (unless force)
    if advertiser.website and not force:
        return advertiser.website, {}

    # Fetch ad_details
    detail_query = (
        select(
            AdDetail.url,
            AdDetail.display_url,
            AdDetail.extra_data,
        )
        .where(AdDetail.advertiser_id == advertiser_id)
        .limit(100)
    )
    details = (await session.execute(detail_query)).all()

    if not details:
        return None, {}

    ad_rows_data = [
        {"url": r[0], "display_url": r[1], "extra_data": r[2]}
        for r in details
    ]

    website, social_handles = extract_website_from_ads(ad_rows_data)

    # Update
    update_values: dict = {}
    if website and (not advertiser.website or force):
        update_values["website"] = website

    existing_channels: dict = {}
    if advertiser.official_channels:
        if isinstance(advertiser.official_channels, str):
            try:
                existing_channels = json.loads(advertiser.official_channels)
            except (json.JSONDecodeError, TypeError):
                existing_channels = {}
        elif isinstance(advertiser.official_channels, dict):
            existing_channels = advertiser.official_channels

    if social_handles:
        merged = {**existing_channels}
        for platform, handle in social_handles.items():
            if platform not in merged:
                merged[platform] = handle
        if merged != existing_channels:
            update_values["official_channels"] = merged

    if update_values:
        for key, val in update_values.items():
            setattr(advertiser, key, val)

    return website, social_handles


def extract_website_from_url(url: str | None, display_url: str | None = None) -> str | None:
    """Quick extraction of website from a single ad's url/display_url.

    Used inline in pipeline.py when creating a new advertiser.
    Returns clean website URL or None.
    """
    # Try display_url first (most reliable for naver_search)
    for candidate in [display_url, url]:
        if not candidate:
            continue
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        domain = _extract_domain(candidate)
        if domain and not _is_ad_infra(domain):
            return f"https://{domain}"
    return None
