"""Build advertiser product portfolio from existing ad data.

Scans ad_details to extract unique (advertiser, product) combinations
and populates the advertiser_products + product_ad_activities tables.

Usage:
    python scripts/build_product_portfolio.py
    python scripts/build_product_portfolio.py --limit 50  # top N advertisers
"""

import asyncio
import sys
import os
import argparse
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db, async_session
from database.models import (
    AdDetail, AdSnapshot, Advertiser, AdvertiserProduct,
    ProductAdActivity, ProductCategory,
)
from sqlalchemy import select, func, and_


async def main(limit: int = 0):
    await init_db()

    async with async_session() as s:
        # Step 1: Query grouped product data from ad_details
        print("Step 1: Querying ad_details for product data...")

        q = (
            select(
                AdDetail.advertiser_id,
                func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown").label("prod_name"),
                AdDetail.product_category_id,
                AdSnapshot.channel,
                func.min(AdSnapshot.captured_at).label("first_seen"),
                func.max(AdSnapshot.captured_at).label("last_seen"),
                func.count(AdDetail.id).label("ad_count"),
                func.sum(AdDetail.estimated_budget).label("total_budget"),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(AdDetail.advertiser_id.is_not(None))
            .group_by(
                AdDetail.advertiser_id,
                func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown"),
                AdDetail.product_category_id,
                AdSnapshot.channel,
            )
        )
        result = await s.execute(q)
        rows = result.all()
        print(f"  Found {len(rows)} (advertiser, product, channel) groups")

        if not rows:
            print("No data to process.")
            return

        # Step 2: Aggregate across channels to create AdvertiserProduct entries
        print("Step 2: Aggregating into AdvertiserProduct entries...")

        # Key: (advertiser_id, product_name, product_category_id)
        portfolio = defaultdict(lambda: {
            "channels": set(),
            "first_seen": None,
            "last_seen": None,
            "ad_count": 0,
            "total_spend": 0.0,
        })

        for row in rows:
            adv_id, prod_name, cat_id, channel, first_seen, last_seen, ad_count, budget = row
            key = (adv_id, prod_name, cat_id)
            p = portfolio[key]
            p["channels"].add(channel)
            p["ad_count"] += ad_count
            p["total_spend"] += float(budget or 0)
            if first_seen:
                if p["first_seen"] is None or first_seen < p["first_seen"]:
                    p["first_seen"] = first_seen
            if last_seen:
                if p["last_seen"] is None or last_seen > p["last_seen"]:
                    p["last_seen"] = last_seen

        print(f"  {len(portfolio)} unique (advertiser, product) combinations")

        # Optionally limit to top N advertisers by ad count
        if limit > 0:
            adv_counts = defaultdict(int)
            for (adv_id, _, _), data in portfolio.items():
                adv_counts[adv_id] += data["ad_count"]
            top_advs = set(
                sorted(adv_counts, key=adv_counts.get, reverse=True)[:limit]
            )
            portfolio = {
                k: v for k, v in portfolio.items() if k[0] in top_advs
            }
            print(f"  Limited to {limit} top advertisers ({len(portfolio)} products)")

        # Step 3: UPSERT into advertiser_products
        print("Step 3: Upserting AdvertiserProduct records...")

        inserted = 0
        updated = 0
        for (adv_id, prod_name, cat_id), data in portfolio.items():
            # Check existing
            existing = (await s.execute(
                select(AdvertiserProduct).where(
                    AdvertiserProduct.advertiser_id == adv_id,
                    AdvertiserProduct.product_name == prod_name,
                )
            )).scalar_one_or_none()

            if existing:
                existing.product_category_id = cat_id or existing.product_category_id
                existing.channels = sorted(data["channels"])
                existing.ad_count = data["ad_count"]
                existing.total_spend_est = data["total_spend"]
                if data["first_seen"]:
                    existing.first_ad_seen = data["first_seen"]
                if data["last_seen"]:
                    existing.last_ad_seen = data["last_seen"]
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                product = AdvertiserProduct(
                    advertiser_id=adv_id,
                    product_name=prod_name,
                    product_category_id=cat_id,
                    source="ad_observed",
                    channels=sorted(data["channels"]),
                    ad_count=data["ad_count"],
                    total_spend_est=data["total_spend"],
                    first_ad_seen=data["first_seen"],
                    last_ad_seen=data["last_seen"],
                )
                s.add(product)
                inserted += 1

        await s.commit()
        print(f"  Inserted: {inserted}, Updated: {updated}")

        # Step 4: Build daily activity data
        print("Step 4: Building ProductAdActivity daily rollup...")

        # Refresh advertiser_products for FK lookup
        all_products = (await s.execute(
            select(AdvertiserProduct)
        )).scalars().all()

        product_lookup = {}
        for p in all_products:
            product_lookup[(p.advertiser_id, p.product_name)] = p.id

        # Query daily data
        daily_q = (
            select(
                AdDetail.advertiser_id,
                func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown").label("prod_name"),
                func.date(AdSnapshot.captured_at).label("dt"),
                AdSnapshot.channel,
                AdDetail.ad_product_name,
                func.count(AdDetail.id).label("ad_count"),
                func.count(func.distinct(AdDetail.creative_hash)).label("unique_creatives"),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(AdDetail.advertiser_id.is_not(None))
            .group_by(
                AdDetail.advertiser_id,
                func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown"),
                func.date(AdSnapshot.captured_at),
                AdSnapshot.channel,
                AdDetail.ad_product_name,
            )
        )
        daily_result = await s.execute(daily_q)
        daily_rows = daily_result.all()
        print(f"  {len(daily_rows)} daily activity records")

        activity_inserted = 0
        for row in daily_rows:
            adv_id, prod_name, dt, channel, ad_prod_name, ad_count, unique_cr = row
            prod_id = product_lookup.get((adv_id, prod_name))
            if not prod_id:
                continue

            # Parse date
            if isinstance(dt, str):
                dt = datetime.strptime(dt, "%Y-%m-%d")

            # Check existing
            existing = (await s.execute(
                select(ProductAdActivity.id).where(
                    ProductAdActivity.advertiser_product_id == prod_id,
                    func.date(ProductAdActivity.date) == (dt if isinstance(dt, str) else dt),
                    ProductAdActivity.channel == channel,
                )
            )).scalar_one_or_none()

            if existing:
                continue

            activity = ProductAdActivity(
                advertiser_product_id=prod_id,
                date=dt,
                channel=channel,
                ad_product_name=ad_prod_name,
                ad_count=ad_count,
                unique_creatives=unique_cr,
            )
            s.add(activity)
            activity_inserted += 1

        await s.commit()
        print(f"  Activities inserted: {activity_inserted}")
        print("Done!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Top N advertisers only")
    args = parser.parse_args()
    asyncio.run(main(args.limit))
