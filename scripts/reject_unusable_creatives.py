"""Reject recent non-search rows that still lack a usable creative asset."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from processor.channel_utils import requires_creative_asset
from processor.data_quality_gate import _normalize_image_path


DB_PATH = ROOT / "adscope.db"


def run_rejection(days: int = 30, channels: tuple[str, ...] | None = None, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT d.id, s.channel, d.creative_image_path, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE s.captured_at >= datetime('now', ?)
          AND (d.verification_status IS NULL OR d.verification_status != 'rejected')
    """
    params: list[object] = [f"-{max(0, days)} day"]
    if channels:
        placeholders = ",".join("?" for _ in channels)
        query += f" AND s.channel IN ({placeholders})"
        params.extend(channels)

    rows = conn.execute(query, params).fetchall()

    stats = {
        "rows_scanned": len(rows),
        "rows_rejected": 0,
        "per_channel": {},
    }
    per_channel: dict[str, int] = {}
    updates: list[tuple[str, str, int]] = []

    for row in rows:
        channel = str(row["channel"])
        if not requires_creative_asset(channel):
            continue

        creative_path = (row["creative_image_path"] or "").strip()
        if creative_path and _normalize_image_path(creative_path, "stored_images") is not None:
            continue

        extra = {}
        if row["extra_data"]:
            try:
                extra = json.loads(row["extra_data"])
            except Exception:
                extra = {}
        extra["quality_rejection_reason"] = (
            "missing_creative_path" if not creative_path else "missing_creative_asset"
        )
        updates.append(("rejected", json.dumps(extra, ensure_ascii=False), int(row["id"])))
        stats["rows_rejected"] += 1
        per_channel[channel] = per_channel.get(channel, 0) + 1

    if updates and not dry_run:
        conn.executemany(
            """
            UPDATE ad_details
            SET verification_status = ?, extra_data = ?
            WHERE id = ?
            """,
            updates,
        )
        conn.commit()

    conn.close()
    stats["per_channel"] = per_channel
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Reject unusable creative rows from recent non-search channels")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--channels", default="", help="Optional comma-separated channel list")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, do not write")
    args = parser.parse_args()

    channels = tuple(part.strip() for part in args.channels.split(",") if part.strip()) or None
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    stats = run_rejection(days=args.days, channels=channels, dry_run=args.dry_run)
    mode = "dry-run" if args.dry_run else "write"
    print(f"[reject-unusable-creatives] mode={mode} db={DB_PATH}")
    for key, value in stats.items():
        print(f"[reject-unusable-creatives] {key}={value}")


if __name__ == "__main__":
    main()
