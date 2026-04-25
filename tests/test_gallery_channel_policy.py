from processor.channel_utils import (
    get_gallery_ad_channels,
    get_gallery_social_platforms,
    normalize_channel_for_display,
)
from api.routers.ads import _keyword_material_fields


def test_gallery_hides_naver_shopping_creatives():
    assert get_gallery_ad_channels("naver_shopping") == set()
    assert get_gallery_social_platforms("naver_shopping") == set()


def test_gallery_groups_youtube_ads_and_surf():
    assert get_gallery_ad_channels("youtube_ads") == {"youtube_ads", "youtube_surf"}
    assert get_gallery_ad_channels("youtube_surf") == {"youtube_ads", "youtube_surf"}
    assert get_gallery_social_platforms("youtube_ads") == {"youtube"}
    assert normalize_channel_for_display("youtube_surf") == "youtube_ads"
    assert normalize_channel_for_display("youtube") == "youtube_ads"


def test_gallery_groups_meta_library_and_feed():
    expected_ad_channels = {"meta", "meta_feed", "facebook", "instagram"}
    expected_platforms = {"meta", "instagram", "facebook"}

    assert get_gallery_ad_channels("meta") == expected_ad_channels
    assert get_gallery_ad_channels("meta_feed") == expected_ad_channels
    assert get_gallery_social_platforms("meta") == expected_platforms
    assert get_gallery_social_platforms("meta_feed") == expected_platforms
    assert normalize_channel_for_display("meta_feed") == "meta"


def test_gallery_search_material_fields_are_text_first():
    fields = _keyword_material_fields(
        "naver_search",
        keyword="credit loan",
        extra_data={"search_keyword": "loan"},
    )

    assert fields == {
        "material_type": "keyword_text",
        "keyword": "credit loan",
        "search_keyword": "loan",
    }


def test_gallery_search_material_fields_fall_back_to_extra_keyword():
    fields = _keyword_material_fields(
        "google_search_ads",
        keyword=None,
        extra_data={"search_keyword": "insurance"},
    )

    assert fields["material_type"] == "keyword_text"
    assert fields["keyword"] == "insurance"
    assert fields["search_keyword"] == "insurance"


def test_gallery_image_material_fields_remain_creative_first():
    fields = _keyword_material_fields(
        "google_gdn",
        keyword="display seed",
        extra_data={"search_keyword": "display crawl"},
    )

    assert fields["material_type"] == "creative_image"
