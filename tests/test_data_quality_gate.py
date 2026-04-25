from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.data_quality_gate import ChannelQualityStats, QualityRule, evaluate_quality_gate


def test_quality_gate_fails_on_missing_url_and_generic_advertiser():
    stats = {
        "meta": ChannelQualityStats(
            channel="meta",
            total=10,
            missing_url=1,
            generic_advertiser=2,
            missing_creative=0,
            missing_asset=0,
        )
    }

    report = evaluate_quality_gate(
        stats_by_channel=stats,
        default_rule=QualityRule(
            min_total=5,
            max_missing_url_ratio=0.0,
            max_generic_advertiser_ratio=0.1,
            max_missing_creative_ratio=0.1,
            max_missing_asset_ratio=0.1,
        ),
    )

    row = report[0]
    assert row["passed"] is False
    assert row["reasons"] == ["missing_url>0.00", "generic_advertiser>0.10"]


def test_quality_gate_ignores_creative_ratio_for_search_channels():
    stats = {
        "naver_search": ChannelQualityStats(
            channel="naver_search",
            total=12,
            missing_url=0,
            generic_advertiser=0,
            missing_creative=12,
            missing_asset=0,
        )
    }

    report = evaluate_quality_gate(
        stats_by_channel=stats,
        default_rule=QualityRule(
            min_total=5,
            max_missing_url_ratio=0.0,
            max_generic_advertiser_ratio=0.05,
            max_missing_creative_ratio=0.0,
            max_missing_asset_ratio=0.0,
        ),
    )

    row = report[0]
    assert row["passed"] is True
    assert row["reasons"] == []


def test_quality_gate_fails_on_missing_asset_for_non_search_channel():
    stats = {
        "youtube_ads": ChannelQualityStats(
            channel="youtube_ads",
            total=20,
            missing_url=0,
            generic_advertiser=0,
            missing_creative=0,
            missing_asset=3,
        )
    }

    report = evaluate_quality_gate(
        stats_by_channel=stats,
        default_rule=QualityRule(
            min_total=5,
            max_missing_url_ratio=0.0,
            max_generic_advertiser_ratio=0.05,
            max_missing_creative_ratio=0.05,
            max_missing_asset_ratio=0.05,
        ),
    )

    row = report[0]
    assert row["passed"] is False
    assert row["reasons"] == ["missing_asset>0.05"]
