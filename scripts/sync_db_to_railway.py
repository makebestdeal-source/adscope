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
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
GZ_PATH = ROOT / "adscope.db.gz"

RAILWAY_URL = "https://adscope.kr/api/_upload_data"
SECRET = "adscope-migrate-2026"


def compress_db() -> float:
    """Compress adscope.db to .gz, return size in MB."""
    with open(DB_PATH, "rb") as f_in:
        with gzip.open(GZ_PATH, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    size_mb = round(GZ_PATH.stat().st_size / (1024 * 1024), 1)
    return size_mb


def upload_to_railway() -> bool:
    """Upload compressed DB to Railway. Returns True on success."""
    try:
        with open(GZ_PATH, "rb") as f:
            resp = requests.post(
                RAILWAY_URL,
                files={"file": ("adscope.db.gz", f, "application/gzip")},
                data={"secret": SECRET},
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
