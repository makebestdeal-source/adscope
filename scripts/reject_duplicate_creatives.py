"""Find and reject duplicate ad creatives without deleting source rows.

The script keeps the earliest row in each duplicate group as the representative
and marks later rows as verification_status='rejected'.  It also annotates
extra_data so the action is reversible/auditable.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"

METHODS = ("hash", "path", "basename", "text_combo")


@dataclass(frozen=True)
class CreativeRow:
    id: int
    channel: str
    captured_at: str
    snapshot_id: int
    keyword_id: int | None
    advertiser_id: int | None
    creative_hash: str | None
    creative_image_path: str | None
    ad_text: str | None
    ad_description: str | None
    url: str | None
    display_url: str | None
    verification_status: str | None
    verification_source: str | None
    extra_data: object
    seen_count: int | None
    first_seen_at: str | None
    last_seen_at: str | None


@dataclass
class DuplicatePick:
    row_id: int
    representative_id: int
    channel: str
    method: str
    key: str
    group_size: int


def _clean(value: object) -> str:
    return str(value or "").strip()


def _norm_text(value: object) -> str:
    return " ".join(_clean(value).lower().split())


def _norm_path(value: object) -> str:
    return _clean(value).replace("\\", "/").lower()


def _path_basename(value: object) -> str:
    path = _norm_path(value)
    return path.rsplit("/", 1)[-1] if path else ""


def _json_obj(raw: object) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _row_sort_key(row: CreativeRow) -> tuple[str, int]:
    return (_clean(row.first_seen_at) or _clean(row.captured_at), row.id)


def _duplicate_key(row: CreativeRow, method: str) -> str | None:
    if method == "hash":
        return _clean(row.creative_hash).lower() or None
    if method == "path":
        return _norm_path(row.creative_image_path) or None
    if method == "basename":
        return _path_basename(row.creative_image_path) or None
    if method == "text_combo":
        parts = (
            _norm_text(row.ad_text),
            _norm_text(row.ad_description),
            _norm_text(row.url).split("?", 1)[0],
            _norm_text(row.display_url),
            str(row.advertiser_id or ""),
            str(row.keyword_id or ""),
        )
        if not any(parts[:4]):
            return None
        return "|".join(parts)
    raise ValueError(f"Unknown duplicate method: {method}")


def _parse_channels(raw: str | None) -> tuple[str, ...] | None:
    channels = tuple(part.strip() for part in (raw or "").split(",") if part.strip())
    return channels or None


def _parse_methods(raw: str | None) -> tuple[str, ...]:
    methods = tuple(part.strip() for part in (raw or "").split(",") if part.strip())
    if not methods:
        return METHODS
    unknown = sorted(set(methods) - set(METHODS))
    if unknown:
        raise SystemExit(f"Unknown --methods: {', '.join(unknown)}")
    return methods


def load_rows(conn: sqlite3.Connection, days: int, channels: tuple[str, ...] | None) -> list[CreativeRow]:
    query = """
        SELECT
            d.id,
            s.channel,
            s.captured_at,
            d.snapshot_id,
            s.keyword_id,
            d.advertiser_id,
            d.creative_hash,
            d.creative_image_path,
            d.ad_text,
            d.ad_description,
            d.url,
            d.display_url,
            d.verification_status,
            d.verification_source,
            d.extra_data,
            d.seen_count,
            d.first_seen_at,
            d.last_seen_at
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
    query += " ORDER BY s.captured_at ASC, d.id ASC"

    return [CreativeRow(**dict(row)) for row in conn.execute(query, params).fetchall()]


def find_duplicates(rows: Iterable[CreativeRow], methods: tuple[str, ...], limit: int | None) -> list[DuplicatePick]:
    row_by_id = {row.id: row for row in rows}
    picks: list[DuplicatePick] = []
    picked_ids: set[int] = set()
    representative_ids: set[int] = set()

    for method in methods:
        groups: dict[tuple[str, str], list[CreativeRow]] = defaultdict(list)
        for row in row_by_id.values():
            if row.id in picked_ids:
                continue
            key = _duplicate_key(row, method)
            if key:
                groups[(row.channel, key)].append(row)

        for (channel, key), group in sorted(groups.items(), key=lambda item: (item[0][0], len(item[1])), reverse=True):
            if len(group) < 2:
                continue
            group = sorted(group, key=_row_sort_key)
            representative = group[0]
            representative_ids.add(representative.id)
            for duplicate in group[1:]:
                if duplicate.id in picked_ids or duplicate.id in representative_ids:
                    continue
                picks.append(
                    DuplicatePick(
                        row_id=duplicate.id,
                        representative_id=representative.id,
                        channel=channel,
                        method=method,
                        key=key,
                        group_size=len(group),
                    )
                )
                picked_ids.add(duplicate.id)
                if limit is not None and len(picks) >= limit:
                    return picks
    return picks


def apply_rejections(conn: sqlite3.Connection, rows: list[CreativeRow], picks: list[DuplicatePick]) -> None:
    row_by_id = {row.id: row for row in rows}
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    detail_updates: list[tuple[str, str, str, int]] = []
    representative_seen: Counter[int] = Counter()
    representative_last_seen: dict[int, str] = {}

    for pick in picks:
        row = row_by_id[pick.row_id]
        extra = _json_obj(row.extra_data)
        extra.update(
            {
                "quality_rejection_reason": "duplicate_creative",
                "duplicate_creative": True,
                "duplicate_method": pick.method,
                "duplicate_key": pick.key,
                "duplicate_representative_id": pick.representative_id,
                "duplicate_group_size": pick.group_size,
                "duplicate_rejected_at": now,
            }
        )
        detail_updates.append(
            (
                "rejected",
                f"duplicate_creative:{pick.method}",
                json.dumps(extra, ensure_ascii=False, sort_keys=True),
                pick.row_id,
            )
        )
        representative_seen[pick.representative_id] += max(1, row.seen_count or 1)
        last_seen = _clean(row.last_seen_at) or _clean(row.captured_at)
        if last_seen and last_seen > representative_last_seen.get(pick.representative_id, ""):
            representative_last_seen[pick.representative_id] = last_seen

    conn.executemany(
        """
        UPDATE ad_details
        SET verification_status = ?,
            verification_source = ?,
            extra_data = ?
        WHERE id = ?
        """,
        detail_updates,
    )

    for representative_id, seen_delta in representative_seen.items():
        last_seen = representative_last_seen.get(representative_id)
        if last_seen:
            conn.execute(
                """
                UPDATE ad_details
                SET seen_count = COALESCE(seen_count, 1) + ?,
                    last_seen_at = CASE
                        WHEN last_seen_at IS NULL OR last_seen_at < ? THEN ?
                        ELSE last_seen_at
                    END
                WHERE id = ?
                """,
                (seen_delta, last_seen, last_seen, representative_id),
            )
        else:
            conn.execute(
                """
                UPDATE ad_details
                SET seen_count = COALESCE(seen_count, 1) + ?
                WHERE id = ?
                """,
                (seen_delta, representative_id),
            )

    conn.commit()


def summarize(rows: list[CreativeRow], picks: list[DuplicatePick]) -> dict:
    scanned_by_channel = Counter(row.channel for row in rows)
    reject_by_channel = Counter(pick.channel for pick in picks)
    reject_by_method = Counter(pick.method for pick in picks)
    groups = {(pick.channel, pick.method, pick.key) for pick in picks}
    return {
        "rows_scanned": len(rows),
        "rows_scanned_by_channel": dict(sorted(scanned_by_channel.items())),
        "duplicate_groups": len(groups),
        "rejectable_rows": len(picks),
        "rejectable_by_channel": dict(sorted(reject_by_channel.items())),
        "rejectable_by_method": dict(sorted(reject_by_method.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Reject duplicate creatives while preserving representative rows")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--channels", default="", help="Optional comma-separated channel list")
    parser.add_argument("--methods", default=",".join(METHODS), help=f"Comma-separated methods: {', '.join(METHODS)}")
    parser.add_argument("--limit", type=int, default=0, help="Max duplicate rows to reject; 0 means no limit")
    parser.add_argument("--apply", action="store_true", help="Write rejected status; omit for dry-run")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = load_rows(conn, args.days, _parse_channels(args.channels))
        picks = find_duplicates(rows, _parse_methods(args.methods), args.limit or None)
        stats = summarize(rows, picks)

        if args.apply and picks:
            apply_rejections(conn, rows, picks)
            mode = "apply"
        else:
            mode = "dry-run"

        print(f"[reject-duplicate-creatives] mode={mode} db={db_path}")
        for key, value in stats.items():
            print(f"[reject-duplicate-creatives] {key}={value}")

        for pick in picks[:10]:
            print(
                "[reject-duplicate-creatives] sample "
                f"row_id={pick.row_id} representative_id={pick.representative_id} "
                f"channel={pick.channel} method={pick.method} group_size={pick.group_size}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
