"""Instagram catalog crawler via Meta Ad Library (Instagram platform filter).

Thin subclass of MetaLibraryCrawler that:
- Sets channel = "instagram"
- Appends &publisher_platforms[0]=instagram to the search URL
- Forces ad_type = "social_library" and is_contact = False (catalog)

No login required -- uses public Meta Ad Library.
"""

from __future__ import annotations

from loguru import logger

from crawler.meta_library import (
    META_AD_LIBRARY_SEARCH_URL,
    MetaLibraryCrawler,
)

# Instagram-filtered Meta Ad Library search URL
_INSTAGRAM_LIBRARY_SEARCH_URL = (
    META_AD_LIBRARY_SEARCH_URL + "&publisher_platforms[0]=instagram"
)


class InstagramCatalogCrawler(MetaLibraryCrawler):
    """Meta Ad Library crawler filtered to Instagram platform only."""

    channel = "instagram"

    async def _search_ad_library(
        self, context, keyword: str, persona_code: str,
    ) -> list[dict]:
        """Override to inject Instagram platform filter into the search URL."""
        # Temporarily patch the module-level URL for parent's _search_ad_library
        import crawler.meta_library as _ml

        original_url = _ml.META_AD_LIBRARY_SEARCH_URL
        _ml.META_AD_LIBRARY_SEARCH_URL = _INSTAGRAM_LIBRARY_SEARCH_URL
        try:
            ads = await super()._search_ad_library(context, keyword, persona_code)
        finally:
            _ml.META_AD_LIBRARY_SEARCH_URL = original_url

        # Tag each ad with instagram channel metadata
        for ad in ads:
            ad["ad_type"] = "social_library"
            ad["ad_placement"] = "meta_ads_library_instagram"
            extra = ad.get("extra_data", {})
            extra["source_channel"] = "instagram"
            extra["publisher_platforms"] = ["instagram"]
            ad["extra_data"] = extra

            # ── IG 전용 마케팅 플랜 계층 필드 ──
            # Parent sets ad_product_name; prefix with "IG " for Instagram
            parent_product = ad.get("ad_product_name", "피드 이미지")
            ad["ad_product_name"] = f"IG {parent_product}"
            ad["ad_format_type"] = "social"
            # campaign_purpose is inherited from parent as-is

        logger.info(
            "[instagram] Meta Ad Library (Instagram filter) '{}' -> {} ads",
            keyword, len(ads),
        )
        return ads
