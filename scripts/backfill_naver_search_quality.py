"""Backfill naver_search advertiser/display quality using crawler normalization rules.

Usage:
    python scripts/backfill_naver_search_quality.py --dry-run
    python scripts/backfill_naver_search_quality.py
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.naver_search import _normalize_extracted_search_ad


def run_backfill(dry_run: bool = False, limit: int | None = None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT d.id, d.advertiser_name_raw, d.ad_text, d.url, d.display_url
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE s.channel = 'naver_search'
        ORDER BY d.id
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    rows = conn.execute(query).fetchall()

    stats = {
        "rows_scanned": 0,
        "rows_updated": 0,
        "advertiser_name_updates": 0,
        "display_url_updates": 0,
    }
    updates: list[tuple[str | None, str | None, int]] = []

    for row in rows:
        stats["rows_scanned"] += 1
        before_name = row["advertiser_name_raw"] or ""
        before_display = row["display_url"] or ""

        normalized = _normalize_extracted_search_ad(
            {
                "advertiser_name": before_name,
                "ad_text": row["ad_text"],
                "url": row["url"],
                "display_url": row["display_url"],
            }
        )

        after_name = normalized.get("advertiser_name") or None
        after_display = normalized.get("display_url") or None

        changed = False
        if after_name and after_name != before_name:
            stats["advertiser_name_updates"] += 1
            changed = True
        else:
            after_name = row["advertiser_name_raw"]

        if after_display and after_display != before_display:
            stats["display_url_updates"] += 1
            changed = True
        else:
            after_display = row["display_url"]

        if not changed:
            continue

        stats["rows_updated"] += 1
        updates.append((after_name, after_display, row["id"]))

    if not dry_run and updates:
        conn.executemany(
            """
            UPDATE ad_details
            SET advertiser_name_raw = ?, display_url = ?
            WHERE id = ?
            """,
            updates,
        )
        conn.commit()

    conn.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill naver_search advertiser/display quality")
    parser.add_argument("--dry-run", action="store_true", help="Scan but do not write updates")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for sampling")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    stats = run_backfill(dry_run=args.dry_run, limit=args.limit)
    mode = "dry-run" if args.dry_run else "write"
    print(f"[naver-search-backfill] mode={mode} db={DB_PATH}")
    for key, value in stats.items():
        print(f"[naver-search-backfill] {key}={value}")


if __name__ == "__main__":
    main()
