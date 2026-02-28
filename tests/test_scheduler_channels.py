from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler.scheduler import (
    _limit_keywords_for_channel,
    _parse_channel_int_map,
    _parse_channels,
    _resolve_min_interval_for_channel,
    should_skip_keyword_independent_channel,
)


class _KeywordCrawler:
    keyword_dependent = True


class _NoKeywordCrawler:
    keyword_dependent = False


def test_parse_channels_defaults_to_naver_search():
    assert _parse_channels("") == ["naver_search"]


def test_parse_channels_filters_unknown_and_deduplicates():
    raw = "naver_search,facebook,unknown,youtube_ads,google_gdn,kakao_da,facebook"
    assert _parse_channels(raw) == [
        "naver_search",
        "facebook",
        "youtube_ads",
        "google_gdn",
        "kakao_da",
    ]


def test_should_skip_keyword_independent_channel():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC).replace(tzinfo=None)
    recent = now - timedelta(minutes=30)
    old = now - timedelta(minutes=240)

    assert should_skip_keyword_independent_channel(recent, now, 180) is True
    assert should_skip_keyword_independent_channel(old, now, 180) is False
    assert should_skip_keyword_independent_channel(None, now, 180) is False


def test_parse_channel_int_map_filters_invalid_entries():
    raw = "google_gdn:240, bad_entry ,unknown:10,kakao_da:abc,facebook:60"
    assert _parse_channel_int_map(raw) == {
        "google_gdn": 240,
        "facebook": 60,
    }


def test_limit_keywords_for_channel_prefers_explicit_limit():
    keywords = ["k1", "k2", "k3"]
    limited = _limit_keywords_for_channel(
        job_keywords=keywords,
        channel="naver_search",
        crawler_cls=_KeywordCrawler,
        channel_keyword_limits={"naver_search": 2},
    )
    assert limited == ["k1", "k2"]


def test_limit_keywords_for_channel_fallback_for_non_keyword():
    keywords = ["k1", "k2", "k3"]
    limited = _limit_keywords_for_channel(
        job_keywords=keywords,
        channel="google_gdn",
        crawler_cls=_NoKeywordCrawler,
        channel_keyword_limits={},
    )
    assert limited == ["k1"]


def test_resolve_min_interval_for_channel():
    assert _resolve_min_interval_for_channel(
        channel="google_gdn",
        is_keyword_dependent=False,
        default_non_keyword_interval=240,
        channel_min_intervals={},
    ) == 240
    assert _resolve_min_interval_for_channel(
        channel="naver_search",
        is_keyword_dependent=True,
        default_non_keyword_interval=240,
        channel_min_intervals={},
    ) == 0
    assert _resolve_min_interval_for_channel(
        channel="naver_search",
        is_keyword_dependent=True,
        default_non_keyword_interval=240,
        channel_min_intervals={"naver_search": 30},
    ) == 30
