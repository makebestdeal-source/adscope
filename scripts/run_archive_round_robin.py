"""Run archive backfill in a round-robin sequence across channels.

This avoids getting stuck on one media/channel for too long by rotating
channel-month tasks in a fixed order.

Usage:
    python scripts/run_archive_round_robin.py --months 2025-04,2025-05 --channels gdn,yt,meta,search
    python scripts/run_archive_round_robin.py --months 2025-04 --channels gdn,yt --cycles 2 --batch-size 5
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

DATED_CHANNELS = {"search", "gdn", "yt"}
FULL_ARCHIVE_CHANNELS = {"meta", "tiktok"}
VALID_CHANNELS = DATED_CHANNELS | FULL_ARCHIVE_CHANNELS
DB_PATH = ROOT / "adscope.db"

CHANNEL_DB_NAMES = {
    "search": "google_search_ads",
    "gdn": "google_gdn",
    "yt": "youtube_ads",
    "meta": "meta",
    "tiktok": "tiktok_ads",
}

TARGET_MONTHLY_ROWS = {
    "search": 80,
    "gdn": 120,
    "yt": 80,
    "meta": 100,
    "tiktok": 40,
}

ALL_PREFIXES_COUNT = 435


def generate_prefixes() -> list[str]:
    prefixes: list[str] = []
    for cho in range(19):
        for jung in range(21):
            code = 0xAC00 + (cho * 21 + jung) * 28
            prefixes.append(chr(code))
    prefixes.extend([chr(c) for c in range(ord("a"), ord("z") + 1)])
    prefixes.extend([str(i) for i in range(10)])
    return prefixes


def month_range(start_month: str, end_month: str) -> list[str]:
    start = datetime.strptime(start_month, "%Y-%m")
    end = datetime.strptime(end_month, "%Y-%m")
    if start > end:
        raise SystemExit("--start-month must be <= --end-month")

    months: list[str] = []
    current = start
    while current <= end:
        months.append(current.strftime("%Y-%m"))
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)
    return months


def checkpoint_count(channel: str, month: str) -> int:
    path = ROOT / ".archive_checkpoints_dated" / f"{CHANNEL_DB_NAMES[channel]}_{month.replace('-', '_')}.done"
    if not path.exists():
        return 0
    return len({line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()})


def done_prefixes(channel: str, month: str) -> set[str]:
    path = ROOT / ".archive_checkpoints_dated" / f"{CHANNEL_DB_NAMES[channel]}_{month.replace('-', '_')}.done"
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def next_pending_prefixes(channel: str, month: str, limit: int) -> list[str]:
    done = done_prefixes(channel, month)
    pending = [prefix for prefix in generate_prefixes() if prefix not in done]
    if limit > 0:
        return pending[:limit]
    return pending


def monthly_row_count(channel: str, month: str) -> int:
    db_channel = CHANNEL_DB_NAMES[channel]
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT COUNT(*)
            FROM ad_details d
            JOIN ad_snapshots s ON s.id = d.snapshot_id
            WHERE s.channel = ?
              AND substr(COALESCE(d.ad_delivery_start, d.first_seen_at, d.last_seen_at, s.captured_at), 1, 7) = ?
            """,
            (db_channel, month),
        ).fetchone()
    return int(row[0] or 0)


def completion_state(channel: str, month: str) -> tuple[bool, str]:
    row_count = monthly_row_count(channel, month)
    cp_count = checkpoint_count(channel, month)
    target = TARGET_MONTHLY_ROWS[channel]

    if row_count >= target:
        return True, f"rows {row_count}/{target}"
    if cp_count >= ALL_PREFIXES_COUNT:
        return True, f"prefixes {cp_count}/{ALL_PREFIXES_COUNT}"
    return False, f"rows {row_count}/{target}, prefixes {cp_count}/{ALL_PREFIXES_COUNT}"


def run_command(cmd: list[str]) -> int:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    started = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    elapsed = time.time() - started
    print(f"<<< exit={proc.returncode} elapsed={elapsed:.1f}s", flush=True)
    return proc.returncode


def run_dated_channel(channel: str, month: str, batch_size: int, timeout: int, include_all_prefixes: bool) -> int:
    queue_cmd = [
        sys.executable,
        "scripts/archive_prefix_queue.py",
        "--channel",
        channel,
        "--months",
        month,
        "--batch-size",
        str(batch_size),
    ]
    if include_all_prefixes:
        queue_cmd.append("--include-all-prefixes")

    code = run_command(queue_cmd)
    if code != 0:
        return code

    return run_command(
        [
            sys.executable,
            "scripts/run_archive_prefix_queue.py",
            "--timeout",
            str(timeout),
        ]
    )


def run_full_archive_channel(channel: str, month: str, max_prefixes: int, timeout: int) -> int:
    prefixes = next_pending_prefixes(channel, month, max_prefixes)
    if not prefixes:
        print(f"\n>>> {channel} {month}: no pending prefixes", flush=True)
        return 0

    return run_command(
        [
            sys.executable,
            "scripts/archive_crawl.py",
            "--months",
            month,
            "--channels",
            channel,
            "--prefixes",
            ",".join(prefixes),
            "--timeout",
            str(timeout),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run archive tasks in round-robin order across channels")
    parser.add_argument("--months", default="", help="Comma-separated YYYY-MM values")
    parser.add_argument("--start-month", default="", help="Range start month YYYY-MM")
    parser.add_argument("--end-month", default="", help="Range end month YYYY-MM")
    parser.add_argument(
        "--channels",
        default="gdn,yt,meta,search",
        help="Comma-separated channel keys: gdn,yt,meta,search,tiktok",
    )
    parser.add_argument("--cycles", type=int, default=1, help="How many full round-robin passes to run")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Prefix batch size for dated channels (search/gdn/yt)",
    )
    parser.add_argument(
        "--max-prefixes",
        type=int,
        default=5,
        help="Prefix cap for archive_crawl.py channels (meta/tiktok)",
    )
    parser.add_argument("--timeout", type=int, default=3600, help="Per-task timeout in seconds")
    parser.add_argument(
        "--include-all-prefixes",
        action="store_true",
        help="Allow dated queue builder to include prefixes with no historical hits yet",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately if any task exits non-zero",
    )
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        help="Skip channel-months already considered complete by row target or full checkpoints",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned tasks without running crawls",
    )
    args = parser.parse_args()

    if args.months:
        months = [part.strip() for part in args.months.split(",") if part.strip()]
    elif args.start_month and args.end_month:
        months = month_range(args.start_month, args.end_month)
    else:
        raise SystemExit("Provide either --months or both --start-month and --end-month")

    channels = [part.strip() for part in args.channels.split(",") if part.strip()]
    invalid = [channel for channel in channels if channel not in VALID_CHANNELS]
    if invalid:
        raise SystemExit(f"Invalid channels: {invalid}. Valid: {sorted(VALID_CHANNELS)}")
    if not months:
        raise SystemExit("No months provided")
    if not channels:
        raise SystemExit("No channels provided")
    if args.cycles < 1:
        raise SystemExit("--cycles must be >= 1")

    print("=" * 60, flush=True)
    print("  ARCHIVE ROUND ROBIN", flush=True)
    print(f"  Months: {months}", flush=True)
    print(f"  Channels: {channels}", flush=True)
    print(f"  Cycles: {args.cycles}", flush=True)
    print(f"  Timeout per task: {args.timeout}s", flush=True)
    print("=" * 60, flush=True)

    failures: list[dict[str, str | int]] = []
    completed = 0
    skipped = 0

    for cycle_index in range(args.cycles):
        print(f"\n## Cycle {cycle_index + 1}/{args.cycles}", flush=True)
        for month in months:
            print(f"\n### Month {month}", flush=True)
            for channel in channels:
                if args.skip_completed:
                    done, reason = completion_state(channel, month)
                    if done:
                        skipped += 1
                        print(f"\n-- {channel} / {month} [skip: {reason}]", flush=True)
                        continue
                    print(f"\n-- {channel} / {month} [pending: {reason}]", flush=True)
                else:
                    print(f"\n-- {channel} / {month}", flush=True)

                if args.dry_run:
                    completed += 1
                    continue
                if channel in DATED_CHANNELS:
                    code = run_dated_channel(
                        channel=channel,
                        month=month,
                        batch_size=args.batch_size,
                        timeout=args.timeout,
                        include_all_prefixes=args.include_all_prefixes,
                    )
                else:
                    code = run_full_archive_channel(
                        channel=channel,
                        month=month,
                        max_prefixes=args.max_prefixes,
                        timeout=args.timeout,
                    )

                completed += 1
                if code != 0:
                    failures.append({"cycle": cycle_index + 1, "month": month, "channel": channel, "exit_code": code})
                    if args.stop_on_error:
                        print("\nStopped on first error.", flush=True)
                        print(f"Completed tasks: {completed}", flush=True)
                        print(f"Failures: {failures}", flush=True)
                        raise SystemExit(code)

    print("\n" + "=" * 60, flush=True)
    print("  ROUND ROBIN COMPLETE", flush=True)
    print(f"  Completed tasks: {completed}", flush=True)
    print(f"  Skipped tasks: {skipped}", flush=True)
    print(f"  Failures: {len(failures)}", flush=True)
    if failures:
        for item in failures:
            print(f"  - cycle={item['cycle']} month={item['month']} channel={item['channel']} exit={item['exit_code']}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
