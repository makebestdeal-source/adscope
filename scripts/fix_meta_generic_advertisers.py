"""Repair Meta rows where CTA text was stored as the advertiser name."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.constants import is_infra_domain
from crawler.url_utils import extract_domain
from processor.data_quality_gate import _GENERIC_ADVERTISER_NAMES


DB_PATH = ROOT / "adscope.db"


def _fallback_name(url: str | None, display_url: str | None) -> str | None:
    domain = extract_domain(url) or (display_url or "").strip().lower()
    if not domain or is_infra_domain(domain):
        return None
    return domain.removeprefix("www.").removeprefix("m.")


def _load_extra(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def run_fix(days: int = 30, dry_run: bool = False) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT d.id, d.advertiser_name_raw, d.url, d.display_url, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE s.channel = 'meta'
          AND s.captured_at >= datetime('now', ?)
          AND (d.verification_status IS NULL OR d.verification_status != 'rejected')
        """,
        (f"-{max(0, days)} day",),
    ).fetchall()

    updates: list[tuple[str | None, str, str, int]] = []
    stats = {
        "rows_scanned": len(rows),
        "generic_rows": 0,
        "renamed": 0,
        "rejected": 0,
    }

    for row in rows:
        raw_name = (row["advertiser_name_raw"] or "").strip()
        if raw_name.lower() not in _GENERIC_ADVERTISER_NAMES:
            continue

        stats["generic_rows"] += 1
        extra = _load_extra(row["extra_data"])
        extra["generic_advertiser_original"] = raw_name

        fallback = _fallback_name(row["url"], row["display_url"])
        if fallback:
            extra["advertiser_name_source"] = "landing_domain_fallback"
            updates.append((fallback, "verified", json.dumps(extra, ensure_ascii=False), int(row["id"])))
            stats["renamed"] += 1
        else:
            extra["quality_rejection_reason"] = "generic_meta_advertiser"
            updates.append((raw_name, "rejected", json.dumps(extra, ensure_ascii=False), int(row["id"])))
            stats["rejected"] += 1

    if updates and not dry_run:
        conn.executemany(
            """
            UPDATE ad_details
            SET advertiser_name_raw = ?, verification_status = ?, extra_data = ?
            WHERE id = ?
            """,
            updates,
        )
        conn.commit()

    conn.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix Meta CTA/generic advertiser names")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--dry-run", action="store_true", help="Scan only")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    stats = run_fix(days=args.days, dry_run=args.dry_run)
    mode = "dry-run" if args.dry_run else "write"
    print(f"[fix-meta-generic] mode={mode} db={DB_PATH}")
    for key, value in stats.items():
        print(f"[fix-meta-generic] {key}={value}")


if __name__ == "__main__":
    main()
