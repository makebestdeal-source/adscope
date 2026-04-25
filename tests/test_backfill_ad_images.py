from scripts.backfill_ad_images import (
    _extract_first_image_url,
    _first_direct_image_url,
    _needs_backfill,
)


def test_first_direct_image_url_prefers_known_keys():
    extra = {
        "preview_url": "https://example.com/preview.js",
        "image_url": "https://cdn.example.com/ad.jpg",
        "banner_image": "https://cdn.example.com/banner.jpg",
    }
    assert _first_direct_image_url(extra) == "https://cdn.example.com/ad.jpg"


def test_extract_first_image_url_from_payload():
    payload = 'var img="https://cdn.example.com/assets/sample.webp?x=1";'
    assert _extract_first_image_url(payload) == "https://cdn.example.com/assets/sample.webp?x=1"


def test_needs_backfill_for_missing_and_existing_paths():
    existing = __file__.replace("test_backfill_ad_images.py", "_tmp_backfill_asset.jpg")
    with open(existing, "wb") as handle:
        handle.write(b"fake")

    try:
        assert _needs_backfill("") is True
        assert _needs_backfill(None) is True
        assert _needs_backfill(existing) is False
        assert _needs_backfill(existing + ".missing") is True
    finally:
        import os

        if os.path.exists(existing):
            os.remove(existing)
