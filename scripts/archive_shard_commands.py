"""Generate shard commands for parallel archive backfill workers.

This does not launch workers. It prints ready-to-run commands so the user can:
1. run them in separate terminals on one PC, or
2. distribute them across multiple PCs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT_JSON = ROOT / "cache" / "reports" / "archive_shard_commands_latest.json"
OUT_MD = ROOT / "cache" / "reports" / "archive_shard_commands_latest.md"

CHANNEL_CONFIG = {
    "search": {
        "channel": "google_search_ads",
        "script": "scripts/archive_crawl_dated.py",
        "channel_arg": "search",
    },
    "gdn": {
        "channel": "google_gdn",
        "script": "scripts/archive_crawl_dated.py",
        "channel_arg": "gdn",
    },
    "yt": {
        "channel": "youtube_ads",
        "script": "scripts/archive_crawl_dated.py",
        "channel_arg": "yt",
    },
    "meta": {
        "channel": "meta",
        "script": "scripts/archive_crawl.py",
        "channel_arg": "meta",
    },
    "tiktok": {
        "channel": "tiktok_ads",
        "script": "scripts/archive_crawl.py",
        "channel_arg": "tiktok",
    },
}


def build_commands(
    channel_key: str,
    months: list[str],
    workers: int,
    timeout: int,
    max_prefixes: int | None,
) -> dict:
    cfg = CHANNEL_CONFIG[channel_key]
    months_arg = ",".join(months)
    commands = []

    for worker_index in range(workers):
        cmd = [
            "python",
            cfg["script"],
            "--months",
            months_arg,
            "--channels",
            cfg["channel_arg"],
            "--timeout",
            str(timeout),
            "--worker-index",
            str(worker_index),
            "--worker-count",
            str(workers),
        ]
        if max_prefixes:
            cmd.extend(["--max-prefixes", str(max_prefixes)])
        commands.append(
            {
                "worker_index": worker_index,
                "worker_count": workers,
                "command": " ".join(cmd),
            }
        )

    return {
        "channel_key": channel_key,
        "channel": cfg["channel"],
        "script": cfg["script"],
        "months": months,
        "workers": workers,
        "timeout": timeout,
        "max_prefixes": max_prefixes,
        "commands": commands,
    }


def write_reports(report: dict) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Archive Shard Commands",
        "",
        f"- channel: `{report['channel']}`",
        f"- script: `{report['script']}`",
        f"- months: `{', '.join(report['months'])}`",
        f"- workers: {report['workers']}",
        f"- timeout: {report['timeout']}",
        f"- max_prefixes: {report['max_prefixes'] or 'full'}",
        "",
        "## Commands",
        "",
    ]
    for item in report["commands"]:
        lines.append(f"### Worker {item['worker_index']}/{item['worker_count']}")
        lines.append("")
        lines.append("```powershell")
        lines.append(item["command"])
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- 같은 PC에서는 `2 workers` 정도부터 시작하는 편이 안전합니다.",
            "- 여러 PC에서 독립 DB로 수집하면 병합은 `scripts/merge_dbs.py`가 더 안전합니다.",
            "- 동일 DB에 너무 많은 worker를 붙이면 SQLite write lock이 병목이 될 수 있습니다.",
        ]
    )
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate archive shard commands")
    parser.add_argument("--channel", choices=sorted(CHANNEL_CONFIG.keys()), required=True)
    parser.add_argument("--months", required=True, help="Comma-separated YYYY-MM values")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=5400)
    parser.add_argument("--max-prefixes", type=int, default=0)
    args = parser.parse_args()

    months = [month.strip() for month in args.months.split(",") if month.strip()]
    report = build_commands(
        channel_key=args.channel,
        months=months,
        workers=args.workers,
        timeout=args.timeout,
        max_prefixes=args.max_prefixes or None,
    )
    write_reports(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
