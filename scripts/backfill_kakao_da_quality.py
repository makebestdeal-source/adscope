"""Backfill kakao_da landing/display quality from stored tracking URLs.

Usage:
    python scripts/backfill_kakao_da_quality.py --dry-run
    python scripts/backfill_kakao_da_quality.py --limit 200
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.constants import is_infra_domain
from crawler.url_utils import extract_domain, is_tracking_url, resolve_redirect_url, resolve_via_http


_GENERIC_KAKAO_NAMES = {"", "카카오", "kakao", "KEYWORDAD", "Daum", "daum"}


def _resolve_kakao_click_url(click_url: str | None) -> tuple[str | None, str | None]:
    candidate = str(click_url or "").strip()
    if not candidate:
        return None, None

    embedded = re.search(r"/click/(https?://.+)$", candidate)
    if embedded:
        embedded_url = embedded.group(1).strip()
        embedded_domain = extract_domain(embedded_url)
        if embedded_domain and not is_infra_domain(embedded_domain):
            return embedded_url, embedded_domain

    static_resolved = resolve_redirect_url(candidate) or candidate
    static_domain = extract_domain(static_resolved)
    if static_domain and not is_infra_domain(static_domain):
        return static_resolved, static_domain

    if is_tracking_url(candidate) or (static_domain and is_infra_domain(static_domain)):
        http_resolved = resolve_via_http(candidate, timeout=5) or static_resolved
        http_domain = extract_domain(http_resolved)
        if http_domain and not is_infra_domain(http_domain):
            return http_resolved, http_domain

    return None, None


def run_backfill(dry_run: bool = False, limit: int | None = None) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    query = """
        SELECT d.id, d.advertiser_name_raw, d.url, d.display_url, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE s.channel = 'kakao_da'
          AND (
            d.display_url IS NULL
            OR trim(d.display_url) = ''
            OR d.display_url = 'tr.ad.daum.net'
            OR d.display_url = 'ka.ad.daum.net'
            OR d.url LIKE 'https://tr.ad.daum.net/%'
            OR d.url LIKE 'https://ka.ad.daum.net/click/%'
            OR d.advertiser_name_raw IN ('카카오', 'kakao', 'KEYWORDAD', 'Daum', 'daum')
          )
        ORDER BY d.id
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    rows = conn.execute(query).fetchall()

    stats = {
        "rows_scanned": 0,
        "rows_resolved": 0,
        "rows_updated": 0,
        "url_updates": 0,
        "display_url_updates": 0,
        "advertiser_name_updates": 0,
        "unresolved": 0,
    }
    updates: list[tuple[str | None, str | None, str | None, int]] = []

    for row in rows:
        stats["rows_scanned"] += 1
        extra = json.loads(row["extra_data"]) if row["extra_data"] else {}
        click_url = extra.get("click_url") or row["url"]

        resolved_url, resolved_domain = _resolve_kakao_click_url(click_url)
        if not resolved_url or not resolved_domain:
            stats["unresolved"] += 1
            continue

        stats["rows_resolved"] += 1

        after_url = resolved_url
        after_display = resolved_domain
        before_name = row["advertiser_name_raw"] or ""
        before_name_clean = before_name.strip()
        if before_name_clean in _GENERIC_KAKAO_NAMES:
            after_name = resolved_domain.removeprefix("www.").removeprefix("m.")
        else:
            after_name = before_name or resolved_domain.removeprefix("www.").removeprefix("m.")

        changed = False
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

        if after_name and after_name != before_name:
            stats["advertiser_name_updates"] += 1
            changed = True
        else:
            after_name = row["advertiser_name_raw"]

        if not changed:
            continue

        stats["rows_updated"] += 1
        updates.append((after_name, after_url, after_display, row["id"]))

    if not dry_run and updates:
        conn.executemany(
            """
            UPDATE ad_details
            SET advertiser_name_raw = ?, url = ?, display_url = ?
            WHERE id = ?
            """,
            updates,
        )
        conn.commit()

    conn.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill kakao_da landing/display quality")
    parser.add_argument("--dry-run", action="store_true", help="Scan but do not write updates")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for sampling")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    stats = run_backfill(dry_run=args.dry_run, limit=args.limit)
    mode = "dry-run" if args.dry_run else "write"
    print(f"[kakao-da-backfill] mode={mode} db={DB_PATH}")
    for key, value in stats.items():
        print(f"[kakao-da-backfill] {key}={value}")


if __name__ == "__main__":
    main()
