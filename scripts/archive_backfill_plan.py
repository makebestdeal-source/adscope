"""Build a practical 2025 archive backfill plan and worker task list.

Outputs:
- cache/reports/archive_backfill_plan_latest.json
- cache/reports/archive_backfill_plan_latest.md

Usage:
    python scripts/archive_backfill_plan.py
    python scripts/archive_backfill_plan.py --year 2025 --workers 4
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
OUT_DIR = ROOT / "cache" / "reports"
NOW = datetime.now()


ARCHIVE_CHANNELS = {
    "google_search_ads": {
        "label": "Google Search",
        "script": "scripts/archive_crawl_dated.py",
        "channel_arg": "search",
        "timeout_sec": 14400,
        "target_monthly_rows": 80,
    },
    "meta": {
        "label": "Meta Ad Library",
        "script": "scripts/archive_crawl.py",
        "channel_arg": "meta",
        "timeout_sec": 14400,
        "target_monthly_rows": 100,
    },
    "youtube_ads": {
        "label": "YouTube Ads",
        "script": "scripts/archive_crawl_dated.py",
        "channel_arg": "yt",
        "timeout_sec": 14400,
        "target_monthly_rows": 80,
    },
    "google_gdn": {
        "label": "Google GDN",
        "script": "scripts/archive_crawl_dated.py",
        "channel_arg": "gdn",
        "timeout_sec": 14400,
        "target_monthly_rows": 120,
    },
    "tiktok_ads": {
        "label": "TikTok Creative",
        "script": "scripts/archive_crawl.py",
        "channel_arg": "tiktok",
        "timeout_sec": 10800,
        "target_monthly_rows": 40,
    },
}

POSTPROCESS_COMMANDS = [
    "python scripts/backfill_advertiser_links.py --limit 800",
    "python scripts/build_campaigns_and_spend.py",
]


def _month_list(year: int) -> list[str]:
    return [f"{year}-{month:02d}" for month in range(1, 13)]


def _load_channel_priority_weights() -> dict[str, float]:
    path = OUT_DIR / "channel_priority_latest.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    weights = {}
    for row in data.get("channel_summary", []):
        weights[row["channel"]] = float(row.get("weighted_gap_amount") or 0)
    return weights


def _load_archive_stats(year: int) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    monthly_rows = conn.execute(
        """
        SELECT
            s.channel AS channel,
            substr(COALESCE(d.ad_delivery_start, d.first_seen_at, d.last_seen_at, s.captured_at), 1, 7) AS ym,
            COUNT(*) AS row_count,
            COUNT(DISTINCT d.advertiser_id) AS advertiser_count
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE d.is_retroactive = 1
          AND substr(COALESCE(d.ad_delivery_start, d.first_seen_at, d.last_seen_at, s.captured_at), 1, 4) = ?
          AND s.channel IN ({channels})
        GROUP BY s.channel, ym
        ORDER BY s.channel, ym
        """.format(channels=",".join("?" for _ in ARCHIVE_CHANNELS)),
        (str(year), *ARCHIVE_CHANNELS.keys()),
    ).fetchall()

    totals = conn.execute(
        """
        SELECT
            s.channel AS channel,
            COUNT(*) AS total_rows,
            COUNT(DISTINCT d.advertiser_id) AS total_advertisers,
            SUM(CASE WHEN d.ad_delivery_start IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_delivery_start,
            SUM(CASE WHEN d.ad_delivery_end IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_delivery_end
        FROM ad_details d
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE d.is_retroactive = 1
          AND s.channel IN ({channels})
        GROUP BY s.channel
        ORDER BY s.channel
        """.format(channels=",".join("?" for _ in ARCHIVE_CHANNELS)),
        tuple(ARCHIVE_CHANNELS.keys()),
    ).fetchall()

    conn.close()

    monthly = {(row["channel"], row["ym"]): dict(row) for row in monthly_rows}
    by_channel = {row["channel"]: dict(row) for row in totals}
    return {"monthly": monthly, "by_channel": by_channel}


def _status_for_month(channel: str, row_count: int) -> str:
    target = ARCHIVE_CHANNELS[channel]["target_monthly_rows"]
    if row_count <= 0:
        return "missing"
    if row_count < target:
        return "thin"
    return "covered"


def _task_priority(weight: float, month_index: int, status: str) -> float:
    status_mult = {"missing": 1.0, "thin": 0.7, "covered": 0.2}.get(status, 0.5)
    recency_boost = 1.0 + (month_index / 24.0)
    base = max(weight, 1.0)
    return round(base * status_mult * recency_boost, 2)


def _estimated_minutes(channel: str, status: str) -> int:
    base = {
        "google_search_ads": 90,
        "meta": 120,
        "youtube_ads": 120,
        "google_gdn": 120,
        "tiktok_ads": 75,
    }[channel]
    if status == "thin":
        return int(base * 0.7)
    if status == "covered":
        return int(base * 0.4)
    return base


def _build_command(channel: str, ym: str, max_prefixes: int | None = None) -> str:
    config = ARCHIVE_CHANNELS[channel]
    cmd = [
        "python",
        config["script"],
        "--months",
        ym,
        "--channels",
        config["channel_arg"],
        "--timeout",
        str(config["timeout_sec"]),
    ]
    if max_prefixes:
        cmd.extend(["--max-prefixes", str(max_prefixes)])
    return " ".join(cmd)


def _channel_notes(channel: str, stats: dict) -> list[str]:
    notes: list[str] = []
    if channel == "meta" and (stats.get("rows_with_delivery_start") or 0) == 0:
        notes.append("META_ACCESS_TOKEN 기반 API 우선 모드 권장: 기존 meta archive rows에 delivery date가 없음")
    if channel == "tiktok_ads":
        notes.append("현행 볼륨이 매우 낮아서 pilot 후 계속 여부 결정")
    return notes


def build_report(year: int, workers: int) -> dict:
    weights = _load_channel_priority_weights()
    stats = _load_archive_stats(year)
    months = _month_list(year)

    channel_summary = []
    tasks = []

    for channel, config in ARCHIVE_CHANNELS.items():
        channel_stats = stats["by_channel"].get(channel, {})
        months_missing = 0
        months_thin = 0
        months_covered = 0

        for index, ym in enumerate(months, start=1):
            month_row = stats["monthly"].get((channel, ym), {})
            row_count = int(month_row.get("row_count") or 0)
            advertiser_count = int(month_row.get("advertiser_count") or 0)
            status = _status_for_month(channel, row_count)
            if status == "missing":
                months_missing += 1
            elif status == "thin":
                months_thin += 1
            else:
                months_covered += 1

            priority = _task_priority(weights.get(channel, 0.0), index, status)
            tasks.append(
                {
                    "channel": channel,
                    "channel_label": config["label"],
                    "month": ym,
                    "status": status,
                    "existing_rows": row_count,
                    "existing_advertisers": advertiser_count,
                    "weighted_gap_amount": round(weights.get(channel, 0.0), 0),
                    "priority": priority,
                    "estimated_minutes": _estimated_minutes(channel, status),
                    "command": _build_command(channel, ym),
                    "pilot_command": _build_command(channel, ym, max_prefixes=5),
                    "notes": _channel_notes(channel, channel_stats),
                }
            )

        channel_summary.append(
            {
                "channel": channel,
                "channel_label": config["label"],
                "weighted_gap_amount": round(weights.get(channel, 0.0), 0),
                "total_retroactive_rows": int(channel_stats.get("total_rows") or 0),
                "total_retroactive_advertisers": int(channel_stats.get("total_advertisers") or 0),
                "rows_with_delivery_start": int(channel_stats.get("rows_with_delivery_start") or 0),
                "months_missing": months_missing,
                "months_thin": months_thin,
                "months_covered": months_covered,
                "target_monthly_rows": config["target_monthly_rows"],
                "notes": _channel_notes(channel, channel_stats),
            }
        )

    tasks.sort(key=lambda item: (-item["priority"], item["channel"], item["month"]))
    channel_summary.sort(key=lambda item: (-item["weighted_gap_amount"], item["channel"]))

    worker_slots = [{"worker_id": i + 1, "task_count": 0, "estimated_minutes": 0, "tasks": []} for i in range(workers)]
    for task in tasks:
        worker = min(worker_slots, key=lambda item: (item["estimated_minutes"], item["worker_id"]))
        worker["tasks"].append(task)
        worker["task_count"] += 1
        worker["estimated_minutes"] += task["estimated_minutes"]

    return {
        "generated_at": NOW.strftime("%Y-%m-%d %H:%M:%S"),
        "db_path": str(DB_PATH),
        "year": year,
        "workers": workers,
        "summary": {
            "task_count": len(tasks),
            "channels": len(ARCHIVE_CHANNELS),
            "postprocess_commands": POSTPROCESS_COMMANDS,
        },
        "channel_summary": channel_summary,
        "tasks": tasks,
        "worker_plan": worker_slots,
    }


def _channel_table_md(rows: list[dict]) -> str:
    lines = [
        "| Channel | Weighted Gap | Retro Rows | Missing Months | Thin Months | Covered Months | Notes |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        notes = "; ".join(row["notes"]) if row["notes"] else "-"
        lines.append(
            "| {label} | {gap:,.0f} | {rows} | {missing} | {thin} | {covered} | {notes} |".format(
                label=row["channel_label"],
                gap=row["weighted_gap_amount"],
                rows=row["total_retroactive_rows"],
                missing=row["months_missing"],
                thin=row["months_thin"],
                covered=row["months_covered"],
                notes=notes,
            )
        )
    return "\n".join(lines)


def _top_tasks_md(rows: list[dict], limit: int = 20) -> str:
    lines = [
        "| Month | Channel | Status | Existing Rows | Priority | Command |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in rows[:limit]:
        lines.append(
            "| {month} | {label} | {status} | {rows} | {priority} | `{command}` |".format(
                month=row["month"],
                label=row["channel_label"],
                status=row["status"],
                rows=row["existing_rows"],
                priority=row["priority"],
                command=row["command"],
            )
        )
    return "\n".join(lines)


def _worker_plan_md(rows: list[dict], limit_tasks: int = 6) -> str:
    blocks = []
    for worker in rows:
        blocks.append(
            "### Worker {worker_id}\n"
            "- tasks: {task_count}\n"
            "- estimated_minutes: {minutes}\n"
            "- first_tasks:\n{tasks}".format(
                worker_id=worker["worker_id"],
                task_count=worker["task_count"],
                minutes=worker["estimated_minutes"],
                tasks="\n".join(
                    f"  - {task['month']} {task['channel_label']} ({task['status']})"
                    for task in worker["tasks"][:limit_tasks]
                ) or "  - none",
            )
        )
    return "\n\n".join(blocks)


def build_markdown(report: dict) -> str:
    summary = report["summary"]
    return f"""# 2025 Archive Backfill Plan

- generated_at: {report['generated_at']}
- db_path: `{report['db_path']}`
- year: {report['year']}
- workers: {report['workers']}

## Summary

- archive task count: {summary['task_count']}
- archive channels: {summary['channels']}
- postprocess:
  - `{summary['postprocess_commands'][0]}`
  - `{summary['postprocess_commands'][1]}`

## Channel Priorities

{_channel_table_md(report['channel_summary'])}

## First Tasks

{_top_tasks_md(report['tasks'])}

## Worker Plan

{_worker_plan_md(report['worker_plan'])}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 2025 archive backfill plan")
    parser.add_argument("--year", type=int, default=2025, help="Target year for backfill planning")
    parser.add_argument("--workers", type=int, default=4, help="Number of PC workers")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(year=args.year, workers=max(args.workers, 1))
    md_text = build_markdown(report)

    json_path = OUT_DIR / "archive_backfill_plan_latest.json"
    md_path = OUT_DIR / "archive_backfill_plan_latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")

    print(f"[archive-plan] wrote {json_path}")
    print(f"[archive-plan] wrote {md_path}")
    if report["tasks"]:
        first = report["tasks"][0]
        print(
            "[archive-plan] top task: {month} {channel} status={status} priority={priority}".format(
                month=first["month"],
                channel=first["channel"],
                status=first["status"],
                priority=first["priority"],
            )
        )


if __name__ == "__main__":
    main()
