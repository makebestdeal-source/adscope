"""Unified channel constants, category mappings, and helper functions.

Single source of truth for all channel-related definitions across the project.
Every module should import from here instead of defining local mappings.

데이터 분기 원칙:
  - is_contact=True  → 소셜 소재 (실제 브라우징 접촉, /social-gallery)
  - is_contact=False → 광고 소재 (카탈로그/라이브러리, /gallery)

듀얼 수집 플랫폼 (같은 플랫폼에서 카탈로그+접촉 모두 수집):
  - YouTube: youtube_ads(카탈로그) + youtube_surf(접촉)
  - Google:  google_search_ads(카탈로그) + google_gdn(접촉)
  - Naver:   naver_search/naver_shopping(카탈로그) + naver_da(접촉)
"""

from __future__ import annotations

# ── Contact channels (real browsing exposure → 소셜 소재) ──
CONTACT_CHANNELS: set[str] = {
    "naver_da",
    "kakao_da",
    "google_gdn",
    "youtube_surf",
}

# ── Catalog channels (ad library / transparency center → 광고 소재) ──
CATALOG_CHANNELS: set[str] = {
    "youtube_ads",
    "google_search_ads",
    "meta",
    "tiktok_ads",
    "naver_shopping",
    "naver_search",
}

# ── All known channels ──
ALL_CHANNELS: set[str] = CONTACT_CHANNELS | CATALOG_CHANNELS

# ── Dual collection mapping (platform -> catalog + contact channels) ──
DUAL_PLATFORM_MAP: dict[str, dict[str, str | list[str]]] = {
    "youtube": {"catalog": "youtube_ads", "contact": "youtube_surf"},
    "google": {"catalog": "google_search_ads", "contact": "google_gdn"},
    "naver": {"catalog": ["naver_search", "naver_shopping"], "contact": "naver_da"},
}

# ── Media category mapping (channel -> category key) ──
MEDIA_CATEGORIES: dict[str, list[str]] = {
    "video": ["youtube_ads", "youtube_surf"],
    "social": ["meta"],
    "portal": ["naver_search", "naver_da"],
    "search": ["google_search_ads"],
    "network": ["google_gdn", "kakao_da"],
}

# ── Media category Korean display names ──
MEDIA_CATEGORY_KO: dict[str, str] = {
    "video": "동영상",
    "social": "소셜/SNS",
    "portal": "포털",
    "search": "검색광고",
    "network": "네트워크/디스플레이",
}

# ── Channel display names (Korean) ──
CHANNEL_DISPLAY_NAMES: dict[str, str] = {
    "naver_search": "네이버 검색광고",
    "naver_da": "네이버 DA",
    "kakao_da": "카카오 DA",
    "google_gdn": "구글 GDN",
    "youtube_ads": "유튜브 광고",
    "youtube_surf": "유튜브 광고",
    "meta": "Meta",
    "tiktok_ads": "틱톡 광고",
    "naver_shopping": "네이버 쇼핑",
    "google_search_ads": "구글 검색광고",
}

# ── Search channels (text-only, no thumbnail in gallery) ──
SEARCH_CHANNELS: set[str] = {"naver_search", "google_search_ads"}

# ── Channel -> benchmark key (for spend_reverse_estimator) ──
CHANNEL_TO_BENCHMARK_KEY: dict[str, str] = {
    "meta": "meta",
    "naver_search": "naver_sa",
    "naver_da": "naver_gfa",
    "kakao_da": "kakao",
    "google_gdn": "google",
    "youtube_ads": "google",
    "youtube_surf": "google",
    "google_search_ads": "google",
}

# Build reverse lookup: channel -> category key (cached at import time)
_CHANNEL_TO_CATEGORY: dict[str, str] = {}
for _cat, _channels in MEDIA_CATEGORIES.items():
    for _ch in _channels:
        _CHANNEL_TO_CATEGORY[_ch] = _cat


# ── Helper functions ──


def get_media_category(channel: str) -> str:
    """Return the media category key for a channel."""
    return _CHANNEL_TO_CATEGORY.get(channel, "network")


def get_media_category_ko(channel: str) -> str:
    """Return the Korean display name for a channel's media category."""
    cat = get_media_category(channel)
    return MEDIA_CATEGORY_KO.get(cat, cat)


def get_display_name(channel: str) -> str:
    """Return the Korean display name for a channel."""
    return CHANNEL_DISPLAY_NAMES.get(channel, channel)


def get_benchmark_key(channel: str) -> str:
    """Return the benchmark key used for spend estimation."""
    return CHANNEL_TO_BENCHMARK_KEY.get(channel, "meta")


def is_catalog_channel(channel: str) -> bool:
    """True if the channel is a catalog/library source (not real exposure)."""
    return channel in CATALOG_CHANNELS


def is_contact_channel(channel: str) -> bool:
    """True if the channel is a contact source (real browsing exposure)."""
    return channel in CONTACT_CHANNELS


def is_contact(channel_name: str, ad: dict | None = None) -> bool:
    """Determine if an ad is contact (소셜 소재) or catalog (광고 소재)."""
    if channel_name in CONTACT_CHANNELS:
        return True
    if channel_name in CATALOG_CHANNELS:
        return False
    return True


def get_dual_channels(platform: str) -> dict | None:
    """Return catalog + contact channels for a dual-collection platform."""
    return DUAL_PLATFORM_MAP.get(platform)


# ── Meta family channels (all → meta) ──
META_CHANNELS: set[str] = {
    "meta", "facebook", "instagram", "facebook_contact",
    "messenger", "audience_network",
}

# ── Display channel normalization ──
CHANNEL_DISPLAY_NORMALIZE: dict[str, str] = {
    "youtube_surf": "youtube_ads",
    "facebook": "meta",
    "instagram": "meta",
    "facebook_contact": "meta",
    "messenger": "meta",
    "audience_network": "meta",
}


def normalize_channel_for_display(channel: str) -> str:
    """Normalize channel name for frontend display (merge variants)."""
    return CHANNEL_DISPLAY_NORMALIZE.get(channel, channel)
