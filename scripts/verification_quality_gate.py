"""Verification quality gate report for recent ad snapshots."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from processor.verification_quality import (
    VerificationRule,
    collect_verification_stats,
    evaluate_verification_gate,
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


def _parse_args():
    parser = argparse.ArgumentParser(description="Ad verification quality gate")
    parser.add_argument(
        "--days",
        type=int,
        default=_env_int("VERIFICATION_GATE_ACTIVE_DAYS", 7),
        help="Lookback window in days",
    )
    parser.add_argument(
        "--channels",
        default=os.getenv("VERIFICATION_GATE_CHANNELS", ""),
        help="Comma-separated channels to evaluate (default: all channels in window)",
    )
    parser.add_argument(
        "--min-total",
        type=int,
        default=_env_int("VERIFICATION_GATE_MIN_TOTAL", 5),
        help="Default minimum ad rows per channel",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=_env_float("VERIFICATION_GATE_DEFAULT_MIN_COVERAGE", 0.5),
        help="Default minimum coverage ratio (verified+likely_verified+unverified)/total",
    )
    parser.add_argument(
        "--min-verified",
        type=float,
        default=_env_float("VERIFICATION_GATE_DEFAULT_MIN_VERIFIED", 0.1),
        help="Default minimum verified ratio verified/total",
    )
    parser.add_argument(
        "--rules",
        default=os.getenv("VERIFICATION_GATE_CHANNEL_RULES", ""),
        help="Per-channel overrides 'channel:min_coverage:min_verified[:min_total]'",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always return success even when gate checks fail",
    )
    return parser.parse_args()


async def main():
    args = _parse_args()
    await init_db()

    channels = parse_channels(args.channels)
    channel_rules = parse_channel_rules(args.rules)
    default_rule = VerificationRule(
        min_total=max(0, args.min_total),
        min_coverage=max(0.0, min(1.0, args.min_coverage)),
        min_verified=max(0.0, min(1.0, args.min_verified)),
    )

    stats = await collect_verification_stats(
        active_days=max(0, args.days),
        channels=channels or None,
    )
    report = evaluate_verification_gate(
        stats_by_channel=stats,
        default_rule=default_rule,
        channel_rules=channel_rules,
    )

    if not report:
        logger.warning("[verification-gate] no ad_details found in the requested window")
        return

    logger.info("[verification-gate] days={} channels={}", args.days, ",".join(channels) or "all")
    failed: list[dict] = []
    for row in report:
        logger.info(
            "[verification-gate] {} pass={} total={} verified={} likely_verified={} unverified={} "
            "unknown={} missing={} coverage={:.2%} verified_ratio={:.2%} rule={}",
            row["channel"],
            row["passed"],
            row["total"],
            row["verified"],
            row["likely_verified"],
            row["unverified"],
            row["unknown"],
            row["missing"],
            row["coverage_ratio"],
            row["verified_ratio"],
            row["rule"],
        )
        if not row["passed"]:
            failed.append(row)

    if failed:
        logger.error("[verification-gate] failed channels: {}", ", ".join(r["channel"] for r in failed))
        for row in failed:
            logger.error("[verification-gate] {} reasons={}", row["channel"], "; ".join(row["reasons"]))
        if not args.no_fail:
            raise SystemExit(2)

    logger.info("[verification-gate] pass")


if __name__ == "__main__":
    asyncio.run(main())
