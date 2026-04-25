"""Backfill missing advertiser websites from existing ad detail URLs.

This script does not make external requests. It uses ad_details.display_url,
ad_details.url, and extra_data already stored in the DB.

Policy:
  1. Prefer advertiser-owned domains from display_url/url/extra_data.
  2. If no owned domain exists, allow advertiser-operated storefronts such as
     smartstore.naver.com and brand.naver.com as a practical fallback.
  3. Never promote ad/search/social/video infrastructure such as
     ader.naver.com, adstransparency.google.com, youtube.com, or naver.com.

Usage:
    python scripts/backfill_advertiser_websites.py --limit 500 --dry-run
    python scripts/backfill_advertiser_websites.py --limit 500 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from loguru import logger
from sqlalchemy import case, desc, func, select, update

from database import async_session
from database.models import AdDetail, Advertiser
from processor.advertiser_link_collector import extract_website_from_ads


logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")


async def _load_target_advertisers(limit: int) -> list[tuple[int, str, int, int]]:
    recent_count = func.sum(
        case((AdDetail.first_seen_at >= func.datetime("now", "-30 days"), 1), else_=0)
    ).label("recent_count")
    total_count = func.count(AdDetail.id).label("total_count")

    async with async_session() as session:
        rows = (
            await session.execute(
                select(Advertiser.id, Advertiser.name, recent_count, total_count)
                .join(AdDetail, AdDetail.advertiser_id == Advertiser.id)
                .where((Advertiser.website.is_(None)) | (Advertiser.website == ""))
                .group_by(Advertiser.id)
                .order_by(desc(recent_count), desc(total_count))
                .limit(limit)
            )
        ).all()

    return [(row[0], row[1], int(row[2] or 0), int(row[3] or 0)) for row in rows]


async def _load_ad_rows(advertiser_id: int, sample_size: int) -> list[dict]:
    async with async_session() as session:
        rows = (
            await session.execute(
                select(AdDetail.url, AdDetail.display_url, AdDetail.extra_data)
                .where(AdDetail.advertiser_id == advertiser_id)
                .order_by(desc(AdDetail.first_seen_at), desc(AdDetail.id))
                .limit(sample_size)
            )
        ).all()

    return [
        {"url": row[0], "display_url": row[1], "extra_data": row[2]}
        for row in rows
    ]


async def backfill_advertiser_websites(
    limit: int,
    sample_size: int,
    apply: bool,
) -> dict:
    targets = await _load_target_advertisers(limit)
    logger.info(
        f"Loaded {len(targets)} advertisers missing website "
        f"(limit={limit}, sample_size={sample_size}, mode={'apply' if apply else 'dry-run'})"
    )

    candidates: list[tuple[int, str, str, int, int]] = []
    checked = 0
    no_candidate = 0

    for advertiser_id, name, recent_count, total_count in targets:
        ad_rows = await _load_ad_rows(advertiser_id, sample_size)
        checked += 1
        website, _ = extract_website_from_ads(ad_rows)
        if not website:
            no_candidate += 1
            continue
        candidates.append((advertiser_id, name, website, recent_count, total_count))

    if candidates and apply:
        async with async_session() as session:
            for advertiser_id, _name, website, _recent_count, _total_count in candidates:
                await session.execute(
                    update(Advertiser)
                    .where(
                        Advertiser.id == advertiser_id,
                        (Advertiser.website.is_(None)) | (Advertiser.website == ""),
                    )
                    .values(website=website)
                )
            await session.commit()

    preview_limit = 30
    for advertiser_id, name, website, recent_count, total_count in candidates[:preview_limit]:
        logger.info(
            f"{'[APPLY]' if apply else '[DRY]'} "
            f"#{advertiser_id} {name} -> {website} "
            f"(recent30={recent_count}, total={total_count})"
        )
    if len(candidates) > preview_limit:
        logger.info(f"... and {len(candidates) - preview_limit} more candidates")

    stats = {
        "checked": checked,
        "candidates": len(candidates),
        "updated": len(candidates) if apply else 0,
        "no_candidate": no_candidate,
    }
    logger.info(
        "SUMMARY "
        f"checked={stats['checked']} candidates={stats['candidates']} "
        f"updated={stats['updated']} no_candidate={stats['no_candidate']}"
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill advertisers.website from ad_details URL signals"
    )
    parser.add_argument("--limit", type=int, default=500, help="Max advertisers to inspect")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Max ad_details rows to inspect per advertiser",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview changes only")
    mode.add_argument("--apply", action="store_true", help="Update advertisers.website")
    args = parser.parse_args()

    apply_changes = bool(args.apply)
    asyncio.run(
        backfill_advertiser_websites(
            limit=max(args.limit, 0),
            sample_size=max(args.sample_size, 1),
            apply=apply_changes,
        )
    )


if __name__ == "__main__":
    main()
