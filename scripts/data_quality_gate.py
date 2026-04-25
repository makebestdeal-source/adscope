"""Operational data quality gate report for recent ads."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processor.data_quality_gate import (
    QualityRule,
    collect_quality_stats,
    evaluate_quality_gate,
    parse_channel_rules,
    parse_channels,
)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except Exception:
        return default


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operational data quality gate")
    parser.add_argument("--days", type=int, default=_env_int("DATA_QUALITY_GATE_ACTIVE_DAYS", 30))
    parser.add_argument("--channels", default=os.getenv("DATA_QUALITY_GATE_CHANNELS", ""))
    parser.add_argument("--min-total", type=int, default=_env_int("DATA_QUALITY_GATE_MIN_TOTAL", 5))
    parser.add_argument(
        "--max-missing-url",
        type=float,
        default=_env_float("DATA_QUALITY_GATE_MAX_MISSING_URL", 0.0),
    )
    parser.add_argument(
        "--max-generic-advertiser",
        type=float,
        default=_env_float("DATA_QUALITY_GATE_MAX_GENERIC_ADVERTISER", 0.02),
    )
    parser.add_argument(
        "--max-invalid-label",
        type=float,
        default=_env_float("DATA_QUALITY_GATE_MAX_INVALID_LABEL", 0.0),
    )
    parser.add_argument(
        "--max-missing-creative",
        type=float,
        default=_env_float("DATA_QUALITY_GATE_MAX_MISSING_CREATIVE", 0.05),
    )
    parser.add_argument(
        "--max-missing-asset",
        type=float,
        default=_env_float("DATA_QUALITY_GATE_MAX_MISSING_ASSET", 0.05),
    )
    parser.add_argument(
        "--rules",
        default=os.getenv("DATA_QUALITY_GATE_CHANNEL_RULES", ""),
        help=(
            "Per-channel overrides "
            "channel:max_missing_url:max_generic:max_missing_creative:max_missing_asset[:min_total[:max_invalid_label]]"
        ),
    )
    parser.add_argument("--no-fail", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    channels = parse_channels(args.channels)
    default_rule = QualityRule(
        min_total=max(0, args.min_total),
        max_missing_url_ratio=max(0.0, min(1.0, args.max_missing_url)),
        max_generic_advertiser_ratio=max(0.0, min(1.0, args.max_generic_advertiser)),
        max_invalid_label_ratio=max(0.0, min(1.0, args.max_invalid_label)),
        max_missing_creative_ratio=max(0.0, min(1.0, args.max_missing_creative)),
        max_missing_asset_ratio=max(0.0, min(1.0, args.max_missing_asset)),
    )
    channel_rules = parse_channel_rules(args.rules)

    stats = collect_quality_stats(
        db_path=DB_PATH,
        active_days=max(0, args.days),
        channels=channels or None,
    )
    report = evaluate_quality_gate(
        stats_by_channel=stats,
        default_rule=default_rule,
        channel_rules=channel_rules,
    )

    if not report:
        logger.warning("[data-quality-gate] no ad_details found in the requested window")
        return

    logger.info("[data-quality-gate] days={} channels={}", args.days, ",".join(channels) or "all")
    failed: list[dict] = []
    for row in report:
        logger.info(
            "[data-quality-gate] {} pass={} total={} missing_url={} generic_adv={} missing_creative={} "
            "invalid_label={} missing_asset={} ratios(url={:.2%}, generic={:.2%}, invalid_label={:.2%}, "
            "creative={:.2%}, asset={:.2%}) rule={}",
            row["channel"],
            row["passed"],
            row["total"],
            row["missing_url"],
            row["generic_advertiser"],
            row["missing_creative"],
            row["invalid_label"],
            row["missing_asset"],
            row["missing_url_ratio"],
            row["generic_advertiser_ratio"],
            row["invalid_label_ratio"],
            row["missing_creative_ratio"],
            row["missing_asset_ratio"],
            row["rule"],
        )
        if not row["passed"]:
            failed.append(row)

    if failed:
        logger.error("[data-quality-gate] failed channels: {}", ", ".join(row["channel"] for row in failed))
        for row in failed:
            logger.error("[data-quality-gate] {} reasons={}", row["channel"], "; ".join(row["reasons"]))
        if not args.no_fail:
            raise SystemExit(2)

    logger.info("[data-quality-gate] pass")


if __name__ == "__main__":
    main()
