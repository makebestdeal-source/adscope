"""Run archive_crawl_dated.py using the latest queue JSON.

Avoids shell encoding issues with Korean prefixes by passing arguments
through subprocess lists instead of manual command-line copy/paste.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE_PATH = ROOT / "cache" / "reports" / "archive_prefix_queue_latest.json"

CHANNEL_TO_ALIAS = {
    "google_search_ads": "search",
    "google_gdn": "gdn",
    "youtube_ads": "yt",
}


def main():
    parser = argparse.ArgumentParser(description="Run archive batch from queue JSON")
    parser.add_argument("--queue-json", default=str(DEFAULT_QUEUE_PATH))
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    queue_path = Path(args.queue_json)
    data = json.loads(queue_path.read_text(encoding="utf-8"))

    channel = data["channel"]
    channel_alias = CHANNEL_TO_ALIAS.get(channel, channel)
    months = ",".join(data["months"])
    prefixes = ",".join(data["selected_prefixes"])

    cmd = [
        sys.executable,
        "scripts/archive_crawl_dated.py",
        "--months",
        months,
        "--channels",
        channel_alias,
        "--prefixes",
        prefixes,
        "--timeout",
        str(args.timeout),
    ]

    print("Running:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(ROOT), check=True)


if __name__ == "__main__":
    main()
