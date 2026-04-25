"""광고주명으로 공식 사이트를 검색하여 DB에 매칭.

네이버 검색 결과에서 공식 사이트 URL을 추출하여
website가 없는 광고주에게 자동으로 매칭합니다.

Usage:
    python scripts/find_websites.py [--limit 500] [--dry-run]
"""

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")

# url_resolver 모듈에서 공유 로직 import
from processor.url_resolver import (
    search_naver,
    _is_excluded_domain,
    _extract_clean_domain,
    MIN_SEARCH_LEN,
    MAX_SEARCH_LEN,
)


async def find_and_update_websites(limit: int = 500, dry_run: bool = False):
    """Find official websites for advertisers without one."""
    from database import init_db, async_session
    from database.models import Advertiser, AdDetail
    from sqlalchemy import select, func, update

    await init_db()

    # Load advertisers without websites, ordered by ad count (most important first)
    async with async_session() as session:
        query = (
            select(
                Advertiser.id,
                Advertiser.name,
                func.count(AdDetail.id).label("ad_count"),
            )
            .outerjoin(AdDetail, AdDetail.advertiser_id == Advertiser.id)
            .where(
                (Advertiser.website.is_(None)) | (Advertiser.website == "")
            )
            .group_by(Advertiser.id)
            .order_by(func.count(AdDetail.id).desc())
            .limit(limit)
        )
        rows = (await session.execute(query)).all()

    if not rows:
        logger.info("No advertisers without website found.")
        return

    logger.info(f"Found {len(rows)} advertisers without website (limit={limit})")

    # Search in batches with rate limiting
    BATCH_SIZE = 5  # concurrent requests
    DELAY_BETWEEN_BATCHES = 1.5  # seconds

    found = 0
    not_found = 0
    errors = 0
    results = []  # (adv_id, name, website)

    async with httpx.AsyncClient() as client:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]

            tasks = []
            for adv_id, name, ad_count in batch:
                # Skip names that are too short or too long for search
                if not name or len(name.strip()) < MIN_SEARCH_LEN or len(name.strip()) > MAX_SEARCH_LEN:
                    not_found += 1
                    continue
                tasks.append((adv_id, name, ad_count, search_naver(client, name.strip())))

            if not tasks:
                continue

            # Run batch concurrently
            search_results = await asyncio.gather(
                *[t[3] for t in tasks],
                return_exceptions=True,
            )

            for (adv_id, name, ad_count, _), website in zip(tasks, search_results):
                if isinstance(website, Exception):
                    errors += 1
                    continue
                if website:
                    found += 1
                    results.append((adv_id, name, website))
                    logger.info(f"  [+] {name} ({ad_count} ads) -> {website}")
                else:
                    not_found += 1
                    logger.debug(f"  [-] {name} ({ad_count} ads) -> not found")

            # Rate limiting
            if i + BATCH_SIZE < len(rows):
                await asyncio.sleep(DELAY_BETWEEN_BATCHES)

            # Progress
            done = min(i + BATCH_SIZE, len(rows))
            if done % 50 == 0 or done == len(rows):
                logger.info(f"Progress: {done}/{len(rows)} | Found: {found} | NotFound: {not_found}")

    # Update DB
    if results and not dry_run:
        logger.info(f"\nUpdating {len(results)} advertisers with found websites...")
        async with async_session() as session:
            for adv_id, name, website in results:
                await session.execute(
                    update(Advertiser)
                    .where(Advertiser.id == adv_id)
                    .values(website=website)
                )
            await session.commit()
        logger.info(f"DB updated: {len(results)} advertisers now have websites")
    elif dry_run:
        logger.info(f"\n[DRY RUN] Would update {len(results)} advertisers:")
        for adv_id, name, website in results[:20]:
            logger.info(f"  {name} -> {website}")
        if len(results) > 20:
            logger.info(f"  ... and {len(results) - 20} more")

    # Summary
    logger.info(f"\n{'=' * 50}")
    logger.info(f"SUMMARY")
    logger.info(f"  Searched: {len(rows)}")
    logger.info(f"  Found:    {found}")
    logger.info(f"  NotFound: {not_found}")
    logger.info(f"  Errors:   {errors}")
    logger.info(f"{'=' * 50}")

    return {"searched": len(rows), "found": found, "not_found": not_found, "errors": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find advertiser official websites via Naver search")
    parser.add_argument("--limit", type=int, default=500, help="Max advertisers to search")
    parser.add_argument("--dry-run", action="store_true", help="Don't update DB, just show results")
    args = parser.parse_args()

    asyncio.run(find_and_update_websites(limit=args.limit, dry_run=args.dry_run))
