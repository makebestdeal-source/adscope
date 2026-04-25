"""Repair missing or missing-on-disk creative assets from stored raw metadata.

This script is aimed at channels that already have usable `extra_data`
(`image_url`, `banner_image`, `preview_url`, etc.) but failed to persist
creative assets reliably.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.image_utils import detect_image_ext, is_valid_image
from crawler.youtube_ads import YouTubeAdsCrawler
from processor.data_quality_gate import _normalize_image_path
from processor.image_store import get_image_store


DB_PATH = ROOT / "adscope.db"
DEFAULT_CHANNELS = ("meta", "kakao_da", "google_gdn", "youtube_ads")
DIRECT_IMAGE_KEYS = (
    "image_url",
    "banner_image",
    "cover_url",
    "full_picture",
    "picture",
    "product_image",
    "thumbnail_url",
    "video_thumbnail",
    "creative_url",
    "media_url",
)
_IMAGE_URL_RE = re.compile(
    r"https?://[^\s\"'<>]+?\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)


def _load_extra(extra_raw: str | None) -> dict:
    if not extra_raw:
        return {}
    try:
        value = json.loads(extra_raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _first_direct_image_url(extra: dict) -> str | None:
    for key in DIRECT_IMAGE_KEYS:
        value = extra.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
    return None


def _extract_first_image_url(payload: str | None) -> str | None:
    if not payload:
        return None
    match = _IMAGE_URL_RE.search(payload)
    return match.group(0) if match else None


def _needs_backfill(creative_path: str | None) -> bool:
    raw_path = (creative_path or "").strip()
    if not raw_path:
        return True
    return _normalize_image_path(raw_path, "stored_images") is None


async def _resolve_download_target(
    client: httpx.AsyncClient,
    channel: str,
    extra: dict,
) -> tuple[str | None, bytes | None, dict]:
    direct_url = _first_direct_image_url(extra)
    if direct_url:
        return direct_url, None, {}

    preview_url = extra.get("preview_url")
    if not isinstance(preview_url, str) or not preview_url.startswith(("http://", "https://")):
        return None, None, {}

    try:
        response = await client.get(preview_url)
    except Exception:
        return None, None, {}

    if response.status_code != 200:
        return None, None, {}

    content = response.content
    if len(content) >= 500 and is_valid_image(content):
        return preview_url, content, {}

    payload = response.text or ""

    if channel == "youtube_ads":
        video_id = YouTubeAdsCrawler._extract_video_id_from_js(payload)
        if video_id:
            thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            return thumb_url, None, {"video_id": video_id, "image_url": thumb_url}

    inferred_url = _extract_first_image_url(payload)
    if inferred_url:
        return inferred_url, None, {"image_url": inferred_url}

    return None, None, {}


def _write_working_file(row_id: int, channel: str, content: bytes) -> Path:
    date_dir = datetime.now().strftime("%Y%m%d")
    work_dir = ROOT / "stored_images" / channel / date_dir / "creative_tmp"
    work_dir.mkdir(parents=True, exist_ok=True)
    ext = detect_image_ext(content)
    filename = f"backfill_{row_id}_{datetime.now().strftime('%H%M%S%f')}{ext}"
    path = work_dir / filename
    path.write_bytes(content)
    return path


async def _download_content(
    client: httpx.AsyncClient,
    url: str,
    prepared_bytes: bytes | None = None,
) -> bytes | None:
    if prepared_bytes is not None:
        return prepared_bytes if len(prepared_bytes) >= 500 and is_valid_image(prepared_bytes) else None

    try:
        response = await client.get(url)
    except Exception:
        return None

    if response.status_code != 200:
        return None

    content = response.content
    if len(content) < 500 or not is_valid_image(content):
        return None
    return content


async def run_backfill(
    channels: tuple[str, ...] = DEFAULT_CHANNELS,
    days: int = 30,
    limit: int | None = None,
    dry_run: bool = False,
    reject_unrecoverable: bool = False,
) -> dict:
    store = get_image_store()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    placeholders = ",".join("?" for _ in channels)
    query = f"""
        SELECT d.id, s.channel, d.creative_image_path, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE s.channel IN ({placeholders})
          AND s.captured_at >= datetime('now', ?)
          AND d.extra_data IS NOT NULL
          AND d.extra_data != ''
          AND (d.verification_status IS NULL OR d.verification_status != 'rejected')
        ORDER BY d.id DESC
    """
    params: list[object] = [*channels, f"-{max(0, days)} day"]
    if limit:
        query += f" LIMIT {int(limit)}"

    rows = conn.execute(query, params).fetchall()

    stats: dict[str, int | dict[str, int]] = {
        "rows_scanned": len(rows),
        "rows_needing_backfill": 0,
        "rows_updated": 0,
        "downloaded": 0,
        "resolved_from_preview": 0,
        "skipped_no_source": 0,
        "failed_download": 0,
        "rows_rejected": 0,
        "per_channel": defaultdict(int),
    }

    updates: list[tuple[str, str, int]] = []
    reject_updates: list[tuple[str, str, int]] = []

    def flush_updates() -> None:
        nonlocal updates, reject_updates
        if dry_run or not updates:
            pass
        else:
            conn.executemany(
                """
                UPDATE ad_details
                SET creative_image_path = ?, extra_data = ?
                WHERE id = ?
                """,
                updates,
            )
            conn.commit()
            updates = []

        if dry_run or not reject_updates:
            return

        conn.executemany(
            """
            UPDATE ad_details
            SET verification_status = ?, extra_data = ?
            WHERE id = ?
            """,
            reject_updates,
        )
        conn.commit()
        reject_updates = []

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for row in rows:
            if not _needs_backfill(row["creative_image_path"]):
                continue

            stats["rows_needing_backfill"] += 1
            channel = str(row["channel"])
            extra = _load_extra(row["extra_data"])

            download_url, prepared_bytes, extra_updates = await _resolve_download_target(client, channel, extra)
            if not download_url:
                stats["skipped_no_source"] += 1
                if reject_unrecoverable:
                    merged_extra = dict(extra)
                    merged_extra["quality_rejection_reason"] = "missing_image_source"
                    reject_updates.append(("rejected", json.dumps(merged_extra, ensure_ascii=False), int(row["id"])))
                    stats["rows_rejected"] += 1
                    stats["per_channel"][channel] += 1
                    if len(reject_updates) >= 100:
                        flush_updates()
                continue
            if extra_updates:
                stats["resolved_from_preview"] += 1

            content = await _download_content(client, download_url, prepared_bytes=prepared_bytes)
            if content is None:
                stats["failed_download"] += 1
                if reject_unrecoverable:
                    merged_extra = dict(extra)
                    merged_extra.update(extra_updates)
                    merged_extra["quality_rejection_reason"] = "creative_download_failed"
                    reject_updates.append(("rejected", json.dumps(merged_extra, ensure_ascii=False), int(row["id"])))
                    stats["rows_rejected"] += 1
                    stats["per_channel"][channel] += 1
                    if len(reject_updates) >= 100:
                        flush_updates()
                continue

            working_path = _write_working_file(int(row["id"]), channel, content)
            try:
                stored_path = await store.save(str(working_path), channel, "creative")
            except Exception:
                stored_path = str(working_path)

            merged_extra = dict(extra)
            merged_extra.update(extra_updates)
            if _first_direct_image_url(merged_extra) is None and download_url.startswith(("http://", "https://")):
                merged_extra["image_url"] = download_url

            updates.append((stored_path, json.dumps(merged_extra, ensure_ascii=False), int(row["id"])))
            stats["downloaded"] += 1
            stats["rows_updated"] += 1
            stats["per_channel"][channel] += 1
            if len(updates) >= 100:
                flush_updates()

    flush_updates()

    conn.close()
    stats["per_channel"] = dict(stats["per_channel"])
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill creative assets from stored raw metadata")
    parser.add_argument(
        "--channels",
        default=",".join(DEFAULT_CHANNELS),
        help="Comma-separated channel list",
    )
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit")
    parser.add_argument("--dry-run", action="store_true", help="Do not write updates")
    parser.add_argument(
        "--reject-unrecoverable",
        action="store_true",
        help="Mark rows as rejected when creative recovery is not possible",
    )
    args = parser.parse_args()

    channels = tuple(part.strip() for part in args.channels.split(",") if part.strip())
    if not channels:
        raise SystemExit("No channels provided")
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    stats = asyncio.run(
        run_backfill(
            channels=channels,
            days=args.days,
            limit=args.limit,
            dry_run=args.dry_run,
            reject_unrecoverable=args.reject_unrecoverable,
        )
    )
    mode = "dry-run" if args.dry_run else "write"
    print(f"[backfill-ad-images] mode={mode} db={DB_PATH}")
    for key, value in stats.items():
        print(f"[backfill-ad-images] {key}={value}")


if __name__ == "__main__":
    main()
