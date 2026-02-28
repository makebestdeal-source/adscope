"""랜딩페이지 일괄 분석 스크립트.

수집된 광고의 랜딩 URL을 방문하여 사업자 정보(상호명, 사업자등록번호)를 추출하고
광고주명이 없는 레코드를 보충한다.

사용법:
    python scripts/analyze_landings.py --days 1 --limit 50
    python scripts/analyze_landings.py --days 7 --limit 200 --screenshot
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from processor.landing_analyzer import batch_analyze_landings


def _parse_args():
    parser = argparse.ArgumentParser(description="Batch landing page analysis")
    parser.add_argument(
        "--days", type=int, default=1,
        help="Analyze ads captured within the last N days (default: 1)",
    )
    parser.add_argument(
        "--limit", type=int, default=100,
        help="Max number of ad_details to analyze (default: 100)",
    )
    parser.add_argument(
        "--screenshot", action="store_true",
        help="Capture landing page screenshots",
    )
    return parser.parse_args()


async def main():
    args = _parse_args()

    logger.info(
        f"[analyze_landings] 시작: days={args.days}, limit={args.limit}, "
        f"screenshot={args.screenshot}"
    )

    stats = await batch_analyze_landings(
        days=args.days,
        limit=args.limit,
        capture_screenshot=args.screenshot,
    )

    logger.info(f"[analyze_landings] 결과: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
