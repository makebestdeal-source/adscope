"""Build the next archive prefix batch from checkpoints + historical yield.

This lets us keep running dated archive backfills in manageable slices
without manually choosing prefixes every time.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"
CHECKPOINT_DIR = ROOT / ".archive_checkpoints_dated"
REPORT_JSON = ROOT / "cache" / "reports" / "archive_prefix_queue_latest.json"
REPORT_MD = ROOT / "cache" / "reports" / "archive_prefix_queue_latest.md"

if hasattr(sys.stdout, "buffer"):
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, closefd=False)

CHANNEL_ALIASES = {
    "search": "google_search_ads",
    "gdn": "google_gdn",
    "yt": "youtube_ads",
}

CHANNEL_ARGS = {
    "google_search_ads": "search",
    "google_gdn": "gdn",
    "youtube_ads": "yt",
}


def generate_prefixes() -> list[str]:
    prefixes: list[str] = []
    for cho in range(19):
        for jung in range(21):
            code = 0xAC00 + (cho * 21 + jung) * 28
            prefixes.append(chr(code))
    prefixes.extend([chr(c) for c in range(ord("a"), ord("z") + 1)])
    prefixes.extend([str(i) for i in range(10)])
    return prefixes


def load_done_prefixes(channel: str, month: str) -> set[str]:
    key = month.replace("-", "_")
    path = CHECKPOINT_DIR / f"{channel}_{key}.done"
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def fetch_historical_scores(conn: sqlite3.Connection, channel: str) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        """
        SELECT keyword,
               SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
               SUM(CASE WHEN status = 'deduped' THEN 1 ELSE 0 END) AS deduped_count,
               COUNT(*) AS total_count
        FROM staging_ads
        WHERE channel = ?
          AND keyword IS NOT NULL
          AND TRIM(keyword) != ''
        GROUP BY keyword
        """,
        (channel,),
    ).fetchall()

    scores: dict[str, dict[str, int]] = {}
    for keyword, approved_count, deduped_count, total_count in rows:
        scores[str(keyword)] = {
            "approved_count": int(approved_count or 0),
            "deduped_count": int(deduped_count or 0),
            "total_count": int(total_count or 0),
        }
    return scores


def fetch_monthly_scores(conn: sqlite3.Connection, channel: str) -> dict[tuple[str, str], dict[str, int]]:
    rows = conn.execute(
        """
        SELECT
            substr(d.ad_delivery_start, 1, 7) AS ym,
            sa.keyword,
            SUM(CASE WHEN sa.status = 'approved' THEN 1 ELSE 0 END) AS approved_count,
            SUM(CASE WHEN sa.status = 'deduped' THEN 1 ELSE 0 END) AS deduped_count,
            COUNT(*) AS total_count
        FROM staging_ads sa
        JOIN ad_details d ON d.id = sa.promoted_ad_detail_id
        JOIN ad_snapshots s ON s.id = d.snapshot_id
        WHERE sa.channel = ?
          AND s.channel = ?
          AND COALESCE(d.is_retroactive, 0) = 1
          AND d.ad_delivery_start IS NOT NULL
          AND sa.keyword IS NOT NULL
          AND TRIM(sa.keyword) != ''
        GROUP BY ym, sa.keyword
        """,
        (channel, channel),
    ).fetchall()

    scores: dict[tuple[str, str], dict[str, int]] = {}
    for ym, keyword, approved_count, deduped_count, total_count in rows:
        scores[(str(ym), str(keyword))] = {
            "approved_count": int(approved_count or 0),
            "deduped_count": int(deduped_count or 0),
            "total_count": int(total_count or 0),
        }
    return scores


def build_queue(
    channel: str,
    months: list[str],
    batch_size: int,
    include_all_prefixes: bool,
) -> dict:
    prefixes = generate_prefixes()
    with sqlite3.connect(DB_PATH) as conn:
        historical_scores = fetch_historical_scores(conn, channel)
        monthly_scores = fetch_monthly_scores(conn, channel)

    candidates = []
    for index, prefix in enumerate(prefixes):
        pending_months = [month for month in months if prefix not in load_done_prefixes(channel, month)]
        if not pending_months:
            continue

        hist = historical_scores.get(prefix, {})
        approved = int(hist.get("approved_count", 0))
        deduped = int(hist.get("deduped_count", 0))
        total = int(hist.get("total_count", 0))

        month_stats = [
            monthly_scores.get((month, prefix), {"approved_count": 0, "deduped_count": 0, "total_count": 0})
            for month in pending_months
        ]
        month_approved = sum(item["approved_count"] for item in month_stats)
        month_deduped = sum(item["deduped_count"] for item in month_stats)
        month_total = sum(item["total_count"] for item in month_stats)
        has_monthly_history = month_total > 0

        if not include_all_prefixes and approved + deduped + month_approved + month_deduped == 0:
            continue

        candidates.append(
            {
                "prefix": prefix,
                "pending_months": pending_months,
                "approved_count": approved,
                "deduped_count": deduped,
                "total_count": total,
                "month_approved_count": month_approved,
                "month_deduped_count": month_deduped,
                "month_total_count": month_total,
                "has_monthly_history": has_monthly_history,
                "priority_score": (
                    (month_approved * 5)
                    + (month_deduped * 3)
                    + approved
                    + deduped
                ) * max(1, len(pending_months)),
                "prefix_order": index,
            }
        )

    candidates.sort(
        key=lambda item: (
            -int(item["has_monthly_history"]),
            -item["month_approved_count"],
            -item["month_deduped_count"],
            -item["month_total_count"],
            -item["priority_score"],
            -item["approved_count"],
            -item["deduped_count"],
            -item["total_count"],
            item["prefix_order"],
        )
    )

    batch = candidates[:batch_size]
    return {
        "channel": channel,
        "months": months,
        "batch_size": batch_size,
        "candidate_count": len(candidates),
        "selected_prefixes": [item["prefix"] for item in batch],
        "batch": batch,
    }


def write_reports(report: dict):
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Archive Prefix Queue",
        "",
        f"- channel: `{report['channel']}`",
        f"- months: `{', '.join(report['months'])}`",
        f"- batch_size: {report['batch_size']}",
        f"- candidate_count: {report['candidate_count']}",
        f"- selected_prefixes: `{', '.join(report['selected_prefixes'])}`",
        "",
        "## Batch",
        "",
        "| Prefix | Pending Months | Month Approved | Month Deduped | Approved | Deduped | Total Seen | Priority |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]

    for item in report["batch"]:
        lines.append(
            f"| {item['prefix']} | {', '.join(item['pending_months'])} | "
            f"{item['month_approved_count']} | {item['month_deduped_count']} | "
            f"{item['approved_count']} | {item['deduped_count']} | {item['total_count']} | "
            f"{item['priority_score']} |"
        )

    lines.extend(
        [
            "",
            "## Suggested Command",
            "",
            "```powershell",
            "python scripts/archive_crawl_dated.py "
            f"--months {','.join(report['months'])} "
            f"--channels {CHANNEL_ARGS.get(report['channel'], report['channel'])} "
            f"--prefixes {','.join(report['selected_prefixes'])} --timeout 3600",
            "```",
        ]
    )
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Build the next archive prefix batch queue")
    parser.add_argument("--channel", default="search", help="search|gdn|yt or full channel name")
    parser.add_argument("--months", default="2025-10,2025-11,2025-12", help="Comma-separated YYYY-MM values")
    parser.add_argument("--batch-size", type=int, default=3, help="How many prefixes to select")
    parser.add_argument(
        "--include-all-prefixes",
        action="store_true",
        help="Include prefixes with no historical yield yet",
    )
    args = parser.parse_args()

    channel = CHANNEL_ALIASES.get(args.channel, args.channel)
    months = [month.strip() for month in args.months.split(",") if month.strip()]
    report = build_queue(
        channel=channel,
        months=months,
        batch_size=args.batch_size,
        include_all_prefixes=args.include_all_prefixes,
    )
    write_reports(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
