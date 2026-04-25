"""Backfill google_gdn landing/text quality from stored preview URLs.

Usage:
    python scripts/backfill_google_gdn_quality.py --dry-run
    python scripts/backfill_google_gdn_quality.py --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.youtube_ads import _display_domain_for_url, _extract_preview_landing_url, _extract_preview_text


CONCURRENCY = 8


async def _fetch_preview_payloads(rows: list[sqlite3.Row]) -> list[tuple[int, str | None, str | None, str | None]]:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    updates: list[tuple[int, str | None, str | None, str | None]] = []

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        async def _worker(row: sqlite3.Row) -> None:
            extra = json.loads(row["extra_data"]) if row["extra_data"] else {}
            preview_url = extra.get("preview_url")
            if not preview_url:
                return

            async with semaphore:
                try:
                    response = await client.get(str(preview_url))
                    if response.status_code != 200 or not response.text:
                        return
                    payload = response.text
                except Exception:
                    return

            resolved_url = _extract_preview_landing_url(payload)
            resolved_text = _extract_preview_text(payload)
            resolved_display = _display_domain_for_url(resolved_url)
            if not resolved_url or not resolved_text or not resolved_display:
                return
            updates.append((row["id"], resolved_url, resolved_display, resolved_text))

        await asyncio.gather(*(_worker(row) for row in rows))

    return updates


def run_backfill(dry_run: bool = False, limit: int | None = None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT d.id, d.url, d.display_url, d.ad_text, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE s.channel = 'google_gdn'
          AND (
            d.display_url = 'adstransparency.google.com'
            OR d.ad_text LIKE 'gdn_transparency_%'
          )
          AND json_extract(d.extra_data, '$.preview_url') IS NOT NULL
          AND json_extract(d.extra_data, '$.preview_url') != ''
        ORDER BY d.id
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    rows = conn.execute(query).fetchall()
    fetched_updates = asyncio.run(_fetch_preview_payloads(rows))

    stats = {
        "rows_scanned": len(rows),
        "rows_resolved": len(fetched_updates),
        "rows_updated": 0,
        "url_updates": 0,
        "display_url_updates": 0,
        "ad_text_updates": 0,
    }

    by_id = {row["id"]: row for row in rows}
    updates: list[tuple[str | None, str | None, str | None, int]] = []

    for row_id, resolved_url, resolved_display, resolved_text in fetched_updates:
        row = by_id[row_id]
        changed = False

        after_url = resolved_url
        after_display = resolved_display
        after_text = resolved_text

        if after_url and after_url != (row["url"] or ""):
            stats["url_updates"] += 1
            changed = True
        else:
            after_url = row["url"]

        if after_display and after_display != (row["display_url"] or ""):
            stats["display_url_updates"] += 1
            changed = True
        else:
            after_display = row["display_url"]

        if after_text and after_text != (row["ad_text"] or ""):
            stats["ad_text_updates"] += 1
            changed = True
        else:
            after_text = row["ad_text"]

        if not changed:
            continue

        stats["rows_updated"] += 1
        updates.append((after_url, after_display, after_text, row_id))

    if not dry_run and updates:
        conn.executemany(
            """
            UPDATE ad_details
            SET url = ?, display_url = ?, ad_text = ?
            WHERE id = ?
            """,
            updates,
        )
        conn.commit()

    conn.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill google_gdn preview landing/text quality")
    parser.add_argument("--dry-run", action="store_true", help="Scan but do not write updates")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for sampling")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    stats = run_backfill(dry_run=args.dry_run, limit=args.limit)
    mode = "dry-run" if args.dry_run else "write"
    print(f"[google-gdn-backfill] mode={mode} db={DB_PATH}")
    for key, value in stats.items():
        print(f"[google-gdn-backfill] {key}={value}")


if __name__ == "__main__":
    main()
