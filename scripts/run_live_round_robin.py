"""Run live domestic crawlers in a low-load round-robin loop.

This is intentionally separate from archive backfills. It rotates only the
domestic observation channels that need fresh daily coverage and delegates each
channel to sequential_crawl.py so only one browser-heavy task runs at a time.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
REPORT_JSON = ROOT / "cache" / "reports" / "live_round_robin_latest.json"
REPORT_MD = ROOT / "cache" / "reports" / "live_round_robin_latest.md"

VALID_CHANNELS = {
    "naver_search",
    "naver_da",
    "naver_shopping",
    "kakao_da",
}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:26], fmt)
        except ValueError:
            continue
    return None


def latest_capture(channel: str) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT MAX(s.captured_at)
            FROM ad_snapshots s
            WHERE s.channel = ?
            """,
            (channel,),
        ).fetchone()
    return str(row[0]) if row and row[0] else None


def channel_counts(channel: str) -> dict[str, int]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT d.advertiser_id) AS advertisers
            FROM ad_details d
            JOIN ad_snapshots s ON s.id = d.snapshot_id
            WHERE s.channel = ?
            """,
            (channel,),
        ).fetchone()
    return {"rows": int(row[0] or 0), "advertisers": int(row[1] or 0)}


def freshness_hours(channel: str) -> float | None:
    captured = parse_time(latest_capture(channel))
    if not captured:
        return None
    return (datetime.now() - captured).total_seconds() / 3600


def run_command(cmd: list[str], timeout: int) -> int:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"\n>>> {' '.join(cmd)}", flush=True)
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), env=env, timeout=timeout + 120)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = 124
    elapsed = time.time() - started
    print(f"<<< exit={code} elapsed={elapsed:.1f}s", flush=True)
    return code


def write_report(report: dict) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Live Round Robin",
        "",
        f"- generated_at: {report['finished_at']}",
        f"- channels: `{', '.join(report['channels'])}`",
        f"- cycles: {report['cycles']}",
        f"- completed_tasks: {report['completed_tasks']}",
        f"- skipped_tasks: {report['skipped_tasks']}",
        f"- failures: {len(report['failures'])}",
        "",
        "## Tasks",
        "",
        "| Cycle | Channel | Status | Before Rows | After Rows | Delta | Latest Before | Latest After |",
        "|---:|---|---|---:|---:|---:|---|---|",
    ]
    for item in report["tasks"]:
        before = item.get("before", {})
        after = item.get("after", {})
        lines.append(
            f"| {item['cycle']} | {item['channel']} | {item['status']} | "
            f"{before.get('rows', 0)} | {after.get('rows', before.get('rows', 0))} | "
            f"{item.get('delta_rows', 0)} | {item.get('latest_before') or '-'} | "
            f"{item.get('latest_after') or item.get('latest_before') or '-'} |"
        )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run domestic live crawlers round-robin")
    parser.add_argument(
        "--channels",
        default="naver_search,naver_da,naver_shopping,kakao_da",
        help="Comma-separated live channels",
    )
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--task-timeout", type=int, default=1800)
    parser.add_argument("--sleep-between", type=int, default=30)
    parser.add_argument("--skip-fresh-hours", type=float, default=6.0)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    channels = [part.strip() for part in args.channels.split(",") if part.strip()]
    invalid = [channel for channel in channels if channel not in VALID_CHANNELS]
    if invalid:
        raise SystemExit(f"Invalid channels: {invalid}. Valid: {sorted(VALID_CHANNELS)}")
    if args.cycles < 1:
        raise SystemExit("--cycles must be >= 1")

    print("=" * 60, flush=True)
    print("  LIVE ROUND ROBIN", flush=True)
    print(f"  Channels: {channels}", flush=True)
    print(f"  Cycles: {args.cycles}", flush=True)
    print(f"  Task timeout: {args.task_timeout}s", flush=True)
    print(f"  Skip fresh: {args.skip_fresh_hours}h", flush=True)
    print("=" * 60, flush=True)

    tasks: list[dict] = []
    failures: list[dict] = []
    completed = 0
    skipped = 0

    for cycle in range(1, args.cycles + 1):
        print(f"\n## Cycle {cycle}/{args.cycles}", flush=True)
        for channel in channels:
            latest_before = latest_capture(channel)
            before = channel_counts(channel)
            age = freshness_hours(channel)
            task = {
                "cycle": cycle,
                "channel": channel,
                "before": before,
                "latest_before": latest_before,
            }

            if age is not None and age <= args.skip_fresh_hours:
                skipped += 1
                task.update({"status": "skipped_fresh", "freshness_hours": round(age, 2)})
                tasks.append(task)
                print(f"\n-- {channel} [skip: fresh {age:.2f}h]", flush=True)
                continue

            print(f"\n-- {channel} [run: rows={before['rows']}, latest={latest_before or '-'}]", flush=True)
            if args.dry_run:
                completed += 1
                task.update({"status": "dry_run", "after": before, "delta_rows": 0})
                tasks.append(task)
                continue

            code = run_command(
                [
                    sys.executable,
                    "scripts/sequential_crawl.py",
                    "--channels",
                    channel,
                    "--skip-postprocess",
                    "--timeout",
                    str(args.task_timeout),
                ],
                timeout=args.task_timeout,
            )
            completed += 1
            after = channel_counts(channel)
            latest_after = latest_capture(channel)
            task.update(
                {
                    "status": "ok" if code == 0 else f"exit_{code}",
                    "exit_code": code,
                    "after": after,
                    "latest_after": latest_after,
                    "delta_rows": after["rows"] - before["rows"],
                }
            )
            tasks.append(task)

            if code != 0:
                failures.append({"cycle": cycle, "channel": channel, "exit_code": code})
                if args.stop_on_error:
                    break
            if args.sleep_between > 0:
                time.sleep(args.sleep_between)
        if failures and args.stop_on_error:
            break

    report = {
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "channels": channels,
        "cycles": args.cycles,
        "task_timeout": args.task_timeout,
        "completed_tasks": completed,
        "skipped_tasks": skipped,
        "failures": failures,
        "tasks": tasks,
    }
    write_report(report)

    print("\n" + "=" * 60, flush=True)
    print("  LIVE ROUND ROBIN COMPLETE", flush=True)
    print(f"  Completed tasks: {completed}", flush=True)
    print(f"  Skipped tasks: {skipped}", flush=True)
    print(f"  Failures: {len(failures)}", flush=True)
    print(f"  Report: {REPORT_MD}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
