"""Backfill naver_shopping advertiser/display quality using crawler heuristics.

Usage:
    python scripts/backfill_naver_shopping_quality.py --dry-run
    python scripts/backfill_naver_shopping_quality.py
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

from crawler.naver_shopping import _derive_shopping_advertiser, _derive_shopping_display_url


def run_backfill(dry_run: bool = False, limit: int | None = None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT d.id, d.advertiser_name_raw, d.ad_text, d.url, d.display_url
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE s.channel = 'naver_shopping'
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

        after_name = _derive_shopping_advertiser(
            row["advertiser_name_raw"],
            row["url"],
            ad_text=row["ad_text"],
        ) or row["advertiser_name_raw"]
        after_display = _derive_shopping_display_url(
            row["url"],
            ad_text=row["ad_text"],
        ) or row["display_url"]

        changed = False
        if after_name and after_name != before_name:
            stats["advertiser_name_updates"] += 1
            changed = True

        if after_display and after_display != before_display:
            stats["display_url_updates"] += 1
            changed = True

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
    parser = argparse.ArgumentParser(description="Backfill naver_shopping advertiser/display quality")
    parser.add_argument("--dry-run", action="store_true", help="Scan but do not write updates")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for sampling")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    stats = run_backfill(dry_run=args.dry_run, limit=args.limit)
    mode = "dry-run" if args.dry_run else "write"
    print(f"[naver-shopping-backfill] mode={mode} db={DB_PATH}")
    for key, value in stats.items():
        print(f"[naver-shopping-backfill] {key}={value}")


if __name__ == "__main__":
    main()
