"""Backfill ad_product_name, ad_format_type, campaign_purpose for existing ad_details.

Uses the ad_product_classifier to fill in missing marketing plan fields
for all existing ad_details records.

Usage:
    python scripts/backfill_ad_products.py
    python scripts/backfill_ad_products.py --limit 500
"""

import asyncio
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db, async_session
from database.models import AdDetail, AdSnapshot
from processor.ad_product_classifier import classify_ad_product
from sqlalchemy import select, update


BATCH_SIZE = 100


async def main(limit: int = 0):
    await init_db()

    async with async_session() as s:
        # Count records needing backfill
        q = (
            select(AdDetail.id)
            .where(AdDetail.ad_product_name.is_(None))
        )
        result = await s.execute(q)
        total_missing = len(result.scalars().all())
        print(f"Records missing ad_product_name: {total_missing}")

        if total_missing == 0:
            print("Nothing to backfill.")
            return

        # Fetch records with snapshot info for channel
        q = (
            select(
                AdDetail.id,
                AdDetail.ad_type,
                AdDetail.url,
                AdDetail.ad_text,
                AdDetail.ad_placement,
                AdDetail.extra_data,
                AdDetail.is_retargeted,
                AdDetail.retargeting_network,
                AdSnapshot.channel,
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(AdDetail.ad_product_name.is_(None))
            .order_by(AdDetail.id)
        )
        if limit > 0:
            q = q.limit(limit)

        result = await s.execute(q)
        rows = result.all()
        print(f"Processing {len(rows)} records...")

        updated = 0
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]

            for row in batch:
                detail_id = row[0]
                ad_data = {
                    "ad_type": row[1],
                    "url": row[2],
                    "ad_text": row[3],
                    "ad_placement": row[4],
                    "extra_data": row[5] or {},
                }
                # Add retargeting info to extra_data for classifier
                if row[6]:  # is_retargeted
                    ad_data["extra_data"]["retargeting_network"] = row[7]

                channel = row[8]
                cls = classify_ad_product(channel, ad_data)

                await s.execute(
                    update(AdDetail)
                    .where(AdDetail.id == detail_id)
                    .values(
                        ad_product_name=cls["ad_product_name"],
                        ad_format_type=cls["ad_format_type"],
                        campaign_purpose=cls["campaign_purpose"],
                    )
                )
                updated += 1

            await s.commit()
            print(f"  Batch {i // BATCH_SIZE + 1}: updated {min(i + BATCH_SIZE, len(rows))}/{len(rows)}")

        print(f"Backfill complete: {updated} records updated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Limit records to process")
    args = parser.parse_args()
    asyncio.run(main(args.limit))
