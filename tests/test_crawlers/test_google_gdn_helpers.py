from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crawler.google_gdn import GoogleGDNCrawler


def test_normalize_creatives_basic():
    creatives = [
        {
            "advertiser_name": "Samsung",
            "creative_id": "abc123",
            "format_type": "IMAGE",
            "start_ts": 1700000000,
            "end_ts": None,
            "preview_url": None,
            "image_url": None,
            "view_count": 1000,
        },
    ]
    ads = GoogleGDNCrawler._normalize_creatives(creatives, "test_keyword")
    assert len(ads) == 1
    assert ads[0]["advertiser_name"] == "Samsung"
    assert ads[0]["ad_type"] == "gdn_display"
    assert ads[0]["ad_format_type"] == "display"
    assert ads[0]["extra_data"]["platform"] == "google_display"


def test_normalize_creatives_dedup():
    creatives = [
        {"advertiser_name": "A", "creative_id": "id1", "format_type": "IMAGE",
         "start_ts": None, "end_ts": None, "preview_url": None, "image_url": None, "view_count": None},
        {"advertiser_name": "A", "creative_id": "id1", "format_type": "IMAGE",
         "start_ts": None, "end_ts": None, "preview_url": None, "image_url": None, "view_count": None},
    ]
    ads = GoogleGDNCrawler._normalize_creatives(creatives, "kw")
    assert len(ads) == 1


def test_is_valid_image():
    assert GoogleGDNCrawler._is_valid_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100) is True
    assert GoogleGDNCrawler._is_valid_image(b"\xff\xd8\xff" + b"\x00" * 100) is True
    assert GoogleGDNCrawler._is_valid_image(b"not an image") is False
    assert GoogleGDNCrawler._is_valid_image(b"") is False
