"""ad_classifier position_zone 분류 테스트 — youtube_ads + instagram."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from processor.ad_classifier import classify_position_zone


# ── youtube_ads ──

def test_youtube_surf_preroll():
    assert classify_position_zone("youtube_ads", ad_type="video_preroll_surf") == "top"


def test_youtube_surf_feed():
    assert classify_position_zone("youtube_ads", ad_type="youtube_feed") == "middle"


def test_youtube_surf_default():
    assert classify_position_zone("youtube_ads") == "middle"


# ── instagram ──

def test_instagram_stories():
    assert classify_position_zone("instagram", ad_type="stories_ad") == "top"


def test_instagram_reels():
    assert classify_position_zone("instagram", ad_type="reels_ad") == "middle"


def test_instagram_feed():
    assert classify_position_zone("instagram", ad_type="feed_sponsored") == "middle"


def test_instagram_default():
    assert classify_position_zone("instagram") == "middle"


# ── 기존 채널 regression ──

def test_naver_search_powerlink_top():
    assert classify_position_zone("naver_search", ad_type="powerlink", position=1) == "top"


def test_naver_search_bizsite_bottom():
    assert classify_position_zone("naver_search", ad_type="bizsite") == "bottom"


def test_google_gdn_default():
    assert classify_position_zone("google_gdn") == "middle"


def test_youtube_ads_preroll():
    assert classify_position_zone("youtube_ads", ad_type="video_preroll") == "top"


def test_unknown_channel():
    assert classify_position_zone("unknown_channel") == "unknown"
