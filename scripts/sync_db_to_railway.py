"""Sync local adscope.db to Railway server.

Usage:
    python scripts/sync_db_to_railway.py          # manual sync (one-shot)
    python scripts/sync_db_to_railway.py --auto    # called by scheduler after crawl

Compresses local DB to gzip, uploads to Railway via _upload_data endpoint.
"""
import gzip
import os
import shutil
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processor.data_quality_gate import (
    QualityRule,
    collect_quality_stats,
    evaluate_quality_gate,
    parse_channel_rules,
    parse_channels,
)

DB_PATH = ROOT / "adscope.db"
GZ_PATH = ROOT / "adscope.db.gz"

load_dotenv(ROOT / ".env")

RAILWAY_URL = os.getenv("MIGRATION_UPLOAD_URL", "https://api.adscope.kr/api/_upload_data")
SECRET = os.getenv("MIGRATION_SECRET", "")


def _check_quality_gate() -> bool:
    if os.getenv("DEPLOY_SKIP_QUALITY_GATE", "").lower() in {"1", "true", "yes"}:
        return True

    report = evaluate_quality_gate(
        stats_by_channel=collect_quality_stats(
            db_path=DB_PATH,
            active_days=int(os.getenv("DATA_QUALITY_GATE_ACTIVE_DAYS", "30")),
            channels=parse_channels(os.getenv("DATA_QUALITY_GATE_CHANNELS", "")) or None,
        ),
        default_rule=QualityRule(
            min_total=int(os.getenv("DATA_QUALITY_GATE_MIN_TOTAL", "5")),
            max_missing_url_ratio=float(os.getenv("DATA_QUALITY_GATE_MAX_MISSING_URL", "0.0")),
            max_generic_advertiser_ratio=float(os.getenv("DATA_QUALITY_GATE_MAX_GENERIC_ADVERTISER", "0.02")),
            max_missing_creative_ratio=float(os.getenv("DATA_QUALITY_GATE_MAX_MISSING_CREATIVE", "0.05")),
            max_missing_asset_ratio=float(os.getenv("DATA_QUALITY_GATE_MAX_MISSING_ASSET", "0.05")),
        ),
        channel_rules=parse_channel_rules(os.getenv("DATA_QUALITY_GATE_CHANNEL_RULES", "")),
    )
    failed = [row for row in report if not row["passed"]]
    if not failed:
        return True

    logger.error(
        "Deploy blocked by data quality gate: {}",
        ", ".join(row["channel"] for row in failed),
    )
    for row in failed:
        logger.error("  {} reasons={}", row["channel"], "; ".join(row["reasons"]))
    return False


def compress_db() -> float:
    """Compress adscope.db to .gz, return size in MB."""
    with open(DB_PATH, "rb") as f_in:
        with gzip.open(GZ_PATH, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    size_mb = round(GZ_PATH.stat().st_size / (1024 * 1024), 1)
    return size_mb


def upload_to_railway() -> bool:
    """Upload compressed DB to Railway. Returns True on success."""
    if not SECRET:
        logger.error("MIGRATION_SECRET is not configured")
        return False
    try:
        with open(GZ_PATH, "rb") as f:
            resp = requests.post(
                f"{RAILWAY_URL}?secret={SECRET}",
                files={"file": ("adscope.db.gz", f, "application/gzip")},
                timeout=300,
            )
        if resp.status_code == 200:
            data = resp.json()
            logger.info("Railway sync OK: {}MB", data.get("size_mb", "?"))
            return True
        else:
            logger.error("Railway sync FAILED: {} {}", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        logger.error("Railway sync error: {}", e)
        return False


def sync() -> bool:
    """Compress + upload. Returns True on success."""
    if not DB_PATH.exists():
        logger.error("DB not found: {}", DB_PATH)
        return False
    if not _check_quality_gate():
        return False

    size_mb = compress_db()
    logger.info("Compressed DB: {}MB", size_mb)

    ok = upload_to_railway()

    if GZ_PATH.exists():
        os.remove(GZ_PATH)

    return ok


def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

    auto = "--auto" in sys.argv
    if auto:
        logger.info("Auto sync triggered by scheduler")

    ok = sync()
    if not ok:
        sys.exit(1)
    logger.info("Sync complete.")


if __name__ == "__main__":
    main()
