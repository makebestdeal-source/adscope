"""Advertiser eligibility rules for high-signal analytics surfaces."""

from __future__ import annotations

from api.services.advertiser_names import (
    display_advertiser_name,
    is_low_confidence_campaign_source_name,
    is_person_or_handle_advertiser_name,
    is_placeholder_advertiser_name,
)


OFFICIAL_ADVERTISER_TYPES = {"group", "company", "brand", "product"}


def is_platform_profile_url(value: object | None) -> bool:
    text = str(value or "").lower()
    return any(
        marker in text
        for marker in (
            "adstransparency.google.com",
            "ader.naver.com",
            "facebook.com/ads/library",
            "tiktok.com/business/creativecenter",
            "youtube.com/channel/",
        )
    )


def is_meta_signal_eligible_advertiser(
    *,
    name: object | None,
    brand_name: object | None = None,
    advertiser_type: object | None = None,
    website: object | None = None,
    official_channels: object | None = None,
    smartstore_url: object | None = None,
) -> bool:
    """Return True only for advertiser profiles suitable for meta-signal rankings."""
    display = display_advertiser_name(name, brand_name, fallback=None)
    if not display:
        return False

    adv_type = str(advertiser_type or "").strip().lower()
    if adv_type == "duplicate":
        return False
    if adv_type in OFFICIAL_ADVERTISER_TYPES:
        return True
    if display_advertiser_name(brand_name, fallback=None):
        return True
    if official_channels or smartstore_url:
        return True

    if is_placeholder_advertiser_name(name) or is_person_or_handle_advertiser_name(name):
        return False
    if is_low_confidence_campaign_source_name(name):
        return False
    if is_platform_profile_url(website):
        return False

    return True
