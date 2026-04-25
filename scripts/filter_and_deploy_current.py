"""Filter current local data and upload a clean DB snapshot to Railway."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import gzip
import os
from pathlib import Path
import shutil
import sqlite3
import sys

import requests
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processor.campaign_builder import rebuild_campaigns_and_spend
from processor.data_quality_gate import (
    QualityRule,
    collect_quality_stats,
    evaluate_quality_gate,
    parse_channel_rules,
    parse_channels,
)
from scripts.reject_invalid_labels import run_label_quality_repair
from scripts.reject_unusable_creatives import run_rejection

DB_PATH = ROOT / "adscope.db"


def _quality_rule() -> QualityRule:
    return QualityRule(
        min_total=int(os.getenv("DATA_QUALITY_GATE_MIN_TOTAL", "5")),
        max_missing_url_ratio=float(os.getenv("DATA_QUALITY_GATE_MAX_MISSING_URL", "0.0")),
        max_generic_advertiser_ratio=float(
            os.getenv("DATA_QUALITY_GATE_MAX_GENERIC_ADVERTISER", "0.02")
        ),
        max_invalid_label_ratio=float(os.getenv("DATA_QUALITY_GATE_MAX_INVALID_LABEL", "0.0")),
        max_missing_creative_ratio=float(
            os.getenv("DATA_QUALITY_GATE_MAX_MISSING_CREATIVE", "0.05")
        ),
        max_missing_asset_ratio=float(os.getenv("DATA_QUALITY_GATE_MAX_MISSING_ASSET", "0.05")),
    )


def _check_quality(db_path: Path, days: int) -> list[dict]:
    report = evaluate_quality_gate(
        stats_by_channel=collect_quality_stats(
            db_path=db_path,
            active_days=days,
            channels=parse_channels(os.getenv("DATA_QUALITY_GATE_CHANNELS", "")) or None,
        ),
        default_rule=_quality_rule(),
        channel_rules=parse_channel_rules(os.getenv("DATA_QUALITY_GATE_CHANNEL_RULES", "")),
    )
    failed = [row for row in report if not row["passed"]]
    for row in report:
        logger.info(
            "quality {} pass={} total={} invalid_label={} missing_creative={} generic={} url={}",
            row["channel"],
            row["passed"],
            row["total"],
            row["invalid_label"],
            row["missing_creative"],
            row["generic_advertiser"],
            row["missing_url"],
        )
    if failed:
        raise SystemExit(
            "quality gate failed: "
            + ", ".join(f"{row['channel']} ({'; '.join(row['reasons'])})" for row in failed)
        )
    return report


def _snapshot_db() -> tuple[Path, dict]:
    deploy_dir = ROOT / "cache" / "deploy"
    deploy_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot = deploy_dir / f"adscope_filtered_{stamp}.db"

    source = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=60)
    target = sqlite3.connect(str(snapshot))
    try:
        source.backup(target, pages=2000)
    finally:
        target.close()
        source.close()

    conn = sqlite3.connect(str(snapshot))
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise SystemExit(f"snapshot integrity_check failed: {integrity}")
    row = conn.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM ad_details
           WHERE verification_status IS NULL OR verification_status != 'rejected') AS active_ads,
          (SELECT COUNT(*) FROM advertisers) AS advertisers,
          (SELECT COUNT(*) FROM campaigns) AS campaigns,
          (SELECT COUNT(*) FROM spend_estimates) AS spend_estimates,
          (SELECT MAX(captured_at) FROM ad_snapshots) AS latest_snapshot
        """
    ).fetchone()
    conn.close()
    counts = {
        "active_ads": row[0],
        "advertisers": row[1],
        "campaigns": row[2],
        "spend_estimates": row[3],
        "latest_snapshot": row[4],
    }
    return snapshot, counts


def _gzip(path: Path) -> Path:
    gz_path = path.with_suffix(path.suffix + ".gz")
    with open(path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return gz_path


def _upload(gz_path: Path) -> requests.Response:
    secret = os.getenv("MIGRATION_SECRET", "")
    if not secret:
        raise SystemExit("MIGRATION_SECRET is not configured")
    url = os.getenv("MIGRATION_UPLOAD_URL", "https://api.adscope.kr/api/_upload_data")
    with open(gz_path, "rb") as f:
        response = requests.post(
            f"{url}?secret={secret}",
            files={"file": ("adscope.db.gz", f, "application/gzip")},
            timeout=300,
        )
    response.raise_for_status()
    return response


async def run(args: argparse.Namespace) -> None:
    load_dotenv(ROOT / ".env")
    logger.info("filtering db={} days={}", DB_PATH, args.days)

    label_stats = run_label_quality_repair(
        db_path=DB_PATH,
        days=args.days,
        apply=True,
        repair_campaign_names=True,
    )
    logger.info("label filter stats={}", label_stats)

    creative_stats = run_rejection(days=args.days, dry_run=False)
    logger.info("creative filter stats={}", creative_stats)

    _check_quality(DB_PATH, args.days)

    if not args.skip_rebuild:
        stats = await rebuild_campaigns_and_spend(active_days=args.active_days)
        logger.info("campaign rebuild stats={}", stats)

    _check_quality(DB_PATH, args.days)
    snapshot, counts = _snapshot_db()
    _check_quality(snapshot, args.days)

    gz_path = _gzip(snapshot)
    logger.info(
        "snapshot={} gzip={} size_mb={} counts={}",
        snapshot,
        gz_path,
        round(gz_path.stat().st_size / (1024 * 1024), 1),
        counts,
    )

    if args.no_upload:
        logger.info("upload skipped")
    else:
        response = _upload(gz_path)
        logger.info("upload ok status={} body={}", response.status_code, response.text[:300])

    if not args.keep_snapshot:
        for path in (snapshot, gz_path):
            try:
                path.unlink()
            except OSError:
                logger.warning("could not remove {}", path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--active-days", type=int, default=7)
    parser.add_argument("--skip-rebuild", action="store_true")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--keep-snapshot", action="store_true")
    return parser.parse_args()


def main() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:YYYY-MM-DD HH:mm:ss} | {level:<7} | {message}")
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
