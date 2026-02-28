from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.verification_quality import (
    ChannelVerificationStats,
    VerificationRule,
    evaluate_verification_gate,
    parse_channel_rules,
    parse_channels,
)


def test_parse_channels_empty_returns_empty_list():
    assert parse_channels(None) == []
    assert parse_channels("") == []


def test_parse_channels_trims_and_skips_empty_entries():
    assert parse_channels(" google_gdn , , kakao_da ") == ["google_gdn", "kakao_da"]


def test_parse_channel_rules_parses_and_clamps_values():
    rules = parse_channel_rules(
        "google_gdn:1.2:-0.3:5,kakao_da:0.4:0.2,broken_entry,facebook:bad:0.1:3"
    )

    assert rules["google_gdn"] == VerificationRule(
        min_total=5,
        min_coverage=1.0,
        min_verified=0.0,
    )
    assert rules["kakao_da"] == VerificationRule(
        min_total=1,
        min_coverage=0.4,
        min_verified=0.2,
    )
    assert "broken_entry" not in rules
    assert "facebook" not in rules


def test_evaluate_gate_fails_when_only_unknown_or_missing():
    stats = {
        "naver_search": ChannelVerificationStats(
            channel="naver_search",
            total=10,
            unknown=4,
            missing=6,
        )
    }
    report = evaluate_verification_gate(
        stats_by_channel=stats,
        default_rule=VerificationRule(min_total=5, min_coverage=0.5, min_verified=0.1),
    )

    row = report[0]
    assert row["channel"] == "naver_search"
    assert row["passed"] is False
    assert row["coverage_ratio"] == 0.0
    assert row["verified_ratio"] == 0.0
    assert row["reasons"] == ["coverage<0.50", "verified<0.10"]


def test_evaluate_gate_uses_channel_override_rule():
    stats = {
        "google_gdn": ChannelVerificationStats(
            channel="google_gdn",
            total=4,
            verified=1,
            likely_verified=1,
            unverified=0,
            unknown=2,
            missing=0,
        )
    }
    default_rule = VerificationRule(min_total=5, min_coverage=0.8, min_verified=0.5)
    channel_rules = {"google_gdn": VerificationRule(min_total=3, min_coverage=0.5, min_verified=0.2)}

    report = evaluate_verification_gate(
        stats_by_channel=stats,
        default_rule=default_rule,
        channel_rules=channel_rules,
    )
    row = report[0]

    assert row["passed"] is True
    assert row["rule"] == {"min_total": 3, "min_coverage": 0.5, "min_verified": 0.2}
