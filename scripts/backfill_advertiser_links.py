"""Backfill website and official_channels for existing advertisers.

Extracts URLs from ad_details rows -- no external web requests.

Usage:
    python scripts/backfill_advertiser_links.py
    python scripts/backfill_advertiser_links.py --limit 200
    python scripts/backfill_advertiser_links.py --force  # overwrite existing
"""

import argparse
import asyncio
import io
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from database import async_session, init_db  # noqa: E402
from processor.advertiser_link_collector import collect_advertiser_links  # noqa: E402


async def main():
    parser = argparse.ArgumentParser(description="Backfill advertiser website/social links")
    parser.add_argument("--limit", type=int, default=500, help="Max advertisers to process")
    parser.add_argument("--force", action="store_true", help="Overwrite existing website values")
    args = parser.parse_args()

    await init_db()
    print(f"Starting advertiser link backfill (limit={args.limit})")

    if args.force:
        # For force mode, we need a custom implementation that also processes
        # advertisers with existing websites
        from sqlalchemy import func, select, update
        from database.models import AdDetail, Advertiser
        from processor.advertiser_link_collector import extract_website_from_ads
        import json

        stats = {"processed": 0, "website_set": 0, "channels_set": 0}

        async with async_session() as session:
            adv_query = (
                select(
                    Advertiser.id,
                    Advertiser.name,
                    Advertiser.website,
                    Advertiser.official_channels,
                    func.count(AdDetail.id).label("ad_count"),
                )
                .outerjoin(AdDetail, AdDetail.advertiser_id == Advertiser.id)
                .group_by(Advertiser.id)
                .having(func.count(AdDetail.id) > 0)
                .order_by(func.count(AdDetail.id).desc())
                .limit(args.limit)
            )
            adv_rows = (await session.execute(adv_query)).all()

            for adv_id, adv_name, current_website, current_channels, ad_count in adv_rows:
                detail_query = (
                    select(
                        AdDetail.url,
                        AdDetail.display_url,
                        AdDetail.extra_data,
                    )
                    .where(AdDetail.advertiser_id == adv_id)
                    .limit(100)
                )
                details = (await session.execute(detail_query)).all()
                ad_rows_data = [
                    {"url": r[0], "display_url": r[1], "extra_data": r[2]}
                    for r in details
                ]

                website, social_handles = extract_website_from_ads(ad_rows_data)

                update_values = {}
                if website:
                    update_values["website"] = website
                    if not current_website:
                        stats["website_set"] += 1

                existing_channels = {}
                if current_channels:
                    if isinstance(current_channels, str):
                        try:
                            existing_channels = json.loads(current_channels)
                        except (json.JSONDecodeError, TypeError):
                            existing_channels = {}
                    elif isinstance(current_channels, dict):
                        existing_channels = current_channels

                if social_handles:
                    merged = {**existing_channels}
                    for platform, handle in social_handles.items():
                        if platform not in merged:
                            merged[platform] = handle
                    if merged != existing_channels:
                        update_values["official_channels"] = merged
                        stats["channels_set"] += 1

                if update_values:
                    await session.execute(
                        update(Advertiser)
                        .where(Advertiser.id == adv_id)
                        .values(**update_values)
                    )

                stats["processed"] += 1
                if stats["processed"] % 50 == 0:
                    print(f"  ... processed {stats['processed']}/{len(adv_rows)}")

            await session.commit()

        print(f"Done (force mode): {stats}")
    else:
        stats = await collect_advertiser_links(limit=args.limit)
        print(f"Done: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
