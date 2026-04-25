from pathlib import Path
import sys
from datetime import UTC, datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.campaign_builder import (
    CampaignAggregate,
    _creative_view_key,
    _is_youtube_ad_ended,
    _youtube_ad_period,
    _youtube_ended_total_spend,
    _yt_compute_daily_views,
)
from processor.spend_estimator import SpendEstimatorV2


def test_youtube_uses_observed_view_count_without_low_sample_discount():
    estimator = SpendEstimatorV2()

    estimate = estimator.estimate(
        "youtube_ads",
        {
            "daily_view_count": 20_000,
            "ad_hits_total": 1,
        },
        {"ad_hits": 1},
    )

    assert estimate.est_daily_spend == 1_000_000
    assert estimate.calculation_method == "video_cpv"
    assert estimate.factors["cpv"] == 50
    assert estimate.factors["daily_views"] == 20_000
    assert estimate.factors["view_count_based"] is True
    assert estimate.factors["conservative"] is False


def test_youtube_fallback_keeps_existing_conservative_floor():
    estimator = SpendEstimatorV2()

    estimate = estimator.estimate(
        "youtube_ads",
        {"ad_hits_total": 1},
        {"ad_hits": 1},
    )

    assert estimate.est_daily_spend == 25_000
    assert estimate.factors["daily_views"] == 1_000
    assert estimate.factors["has_view_data"] is False
    assert estimate.factors["conservative"] is True


def test_search_spend_is_clicks_from_average_ctr_times_cpc():
    estimator = SpendEstimatorV2()

    estimate = estimator.estimate(
        "naver_search",
        {
            "avg_position": 2,
            "keyword_search_volume": 10_000,
            "ad_hits_total": 3,
        },
        {"ad_hits": 3},
    )

    assert estimate.est_daily_spend == 200_000
    assert estimate.factors["ctr"] == 0.020
    assert estimate.factors["daily_clicks"] == 200
    assert estimate.factors["cpc"] == 1_000


def test_naver_da_uses_ctr_cpc_and_traffic_multiplier():
    estimator = SpendEstimatorV2()

    estimate = estimator.estimate(
        "naver_da",
        {
            "ad_hits_total": 3,
            "placement_traffic_multiplier": 1.5,
        },
        {"ad_hits": 2},
    )

    assert estimate.est_daily_spend == 120_000
    assert estimate.factors["cpc"] == 1_000
    assert estimate.factors["ctr"] == 0.001
    assert estimate.factors["daily_impressions"] == 120_000
    assert estimate.factors["daily_clicks"] == 120
    assert estimate.factors["placement_traffic_multiplier"] == 1.5


def test_youtube_daily_views_distribute_total_view_count_over_observed_days():
    agg = CampaignAggregate(total_view_count=90_000)

    assert _yt_compute_daily_views(agg, observed_days=3) == 30_000


def test_creative_view_key_prefers_stable_material_id():
    assert (
        _creative_view_key({"creative_id": "abc", "matched_video_id": "vid123"}, 1_000)
        == "matched_video_id:vid123"
    )
    assert _creative_view_key({"creative_id": "abc", "view_count": 1_000}, 1_000) == "creative_id:abc"
    assert _creative_view_key({"view_count": 1_000}, 1_000) == "view_count:1000"


def test_youtube_ended_ad_period_uses_end_timestamp():
    start = int(datetime(2026, 3, 1, tzinfo=UTC).timestamp())
    end = int(datetime(2026, 3, 10, tzinfo=UTC).timestamp())

    start_at, end_at = _youtube_ad_period(
        {"start_timestamp": str(start), "end_timestamp": str(end)}
    )

    assert start_at == datetime(2026, 3, 1)
    assert end_at == datetime(2026, 3, 10)
    assert _is_youtube_ad_ended(
        {"end_timestamp": str(end)},
        now=datetime(2026, 4, 25),
    )


def test_youtube_ended_total_spend_uses_cumulative_views_without_daily_cap():
    agg = CampaignAggregate(ended_total_view_count=10_000_000)

    assert _youtube_ended_total_spend(agg, "youtube_ads") == 500_000_000
