from processor.data_washer import wash_single_ad


def test_google_search_archive_without_landing_url_is_approved():
    ad = {
        "advertiser_name": "삼성전자",
        "ad_text": None,
        "ad_description": None,
        "url": None,
        "display_url": None,
        "ad_type": "google_search_text",
        "extra_data": {
            "detection_method": "ads_transparency_rpc",
            "creative_id": "CR0001",
            "format_type": 3,
            "start_ts": "1768862474",
            "end_ts": "1771253992",
        },
    }

    result = wash_single_ad(ad, "google_search_ads")

    assert result["status"] == "approved"
    assert "archive_missing_landing_url" in (result["rejection_reason"] or "")
    assert ad["_creative_hash"]


def test_archive_img_markup_is_promoted_to_original_image_url():
    ad = {
        "advertiser_name": "이루가",
        "ad_text": '<img src="https://tpc.googlesyndication.com/archive/simgad/12345">',
        "ad_description": None,
        "url": None,
        "display_url": None,
        "ad_type": "google_search_text",
        "extra_data": {
            "detection_method": "ads_transparency_rpc",
            "creative_id": "CR0002",
            "format_type": 2,
            "start_ts": "1768896000",
            "end_ts": "1771253972",
        },
    }

    result = wash_single_ad(ad, "google_search_ads")

    assert result["status"] == "approved"
    assert ad["ad_text"] is None
    assert ad["extra_data"]["original_image_url"].endswith("/12345")
    assert ad["_creative_hash"]


def test_google_gdn_archive_hint_counts_as_creative_asset():
    ad = {
        "advertiser_name": "현대자동차",
        "ad_text": "전기차 프로모션",
        "ad_description": None,
        "url": "https://adstransparency.google.com/advertiser/AR123?region=KR",
        "display_url": "adstransparency.google.com",
        "creative_image_path": None,
        "ad_type": "gdn_display",
        "extra_data": {
            "detection_method": "ads_transparency_rpc",
            "creative_id": "CR0003",
            "image_url": "https://tpc.googlesyndication.com/archive/simgad/67890",
            "start_ts": "1768896000",
            "end_ts": "1771253972",
        },
    }

    result = wash_single_ad(ad, "google_gdn")

    assert result["status"] == "approved"
    assert "missing_creative_asset" not in (result["rejection_reason"] or "")
    assert ad["_creative_hash"]
