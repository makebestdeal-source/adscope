"""Incremental update of marketing schedule data.

Called by scheduler daily at 05:30 KST. Updates:
1. advertiser_products: new products, updated dates/counts
2. product_ad_activities: new daily activity rows
3. Detection of pattern changes

Usage (standalone):
    python -m processor.marketing_schedule_builder
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_

from database import init_db, async_session
from database.models import (
    AdDetail, AdSnapshot, AdvertiserProduct, ProductAdActivity,
)

logger = logging.getLogger("adscope.marketing_schedule")


async def update_marketing_schedule(days_back: int = 2) -> dict:
    """Process recent ad data into marketing schedule tables.

    Args:
        days_back: How many days back to process (default 2 for incremental)

    Returns:
        Summary dict with counts
    """
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    async with async_session() as s:
        # Step 1: Query recent ads grouped by (advertiser_id, product_name, channel)
        q = (
            select(
                AdDetail.advertiser_id,
                func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown").label("prod_name"),
                AdDetail.product_category_id,
                AdSnapshot.channel,
                func.min(AdSnapshot.captured_at).label("first_seen"),
                func.max(AdSnapshot.captured_at).label("last_seen"),
                func.count(AdDetail.id).label("ad_count"),
            )
            .join(AdSnapshot, AdSnapshot.id == AdDetail.snapshot_id)
            .where(
                AdDetail.advertiser_id.is_not(None),
                AdSnapshot.captured_at >= cutoff,
            )
            .group_by(
                AdDetail.advertiser_id,
                func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown"),
                AdDetail.product_category_id,
                AdSnapshot.channel,
            )
        )
        rows = (await s.execute(q)).all()
        logger.info(f"Marketing schedule: {len(rows)} groups to process (last {days_back} days)")

        if not rows:
            return {"products_updated": 0, "activities_created": 0}

        # Step 2: Aggregate by (advertiser_id, product_name)
        portfolio = defaultdict(lambda: {
            "channels": set(), "first_seen": None, "last_seen": None,
            "ad_count": 0, "cat_id": None,
        })
        for row in rows:
            adv_id, prod_name, cat_id, channel, first_seen, last_seen, ad_count = row
            key = (adv_id, prod_name)
            p = portfolio[key]
            p["channels"].add(channel)
            p["ad_count"] += ad_count
            p["cat_id"] = cat_id or p["cat_id"]
            if first_seen and (p["first_seen"] is None or first_seen < p["first_seen"]):
                p["first_seen"] = first_seen
            if last_seen and (p["last_seen"] is None or last_seen > p["last_seen"]):
                p["last_seen"] = last_seen

        # Step 3: UPSERT into advertiser_products
        products_updated = 0
        for (adv_id, prod_name), data in portfolio.items():
            existing = (await s.execute(
                select(AdvertiserProduct).where(
                    AdvertiserProduct.advertiser_id == adv_id,
                    AdvertiserProduct.product_name == prod_name,
                )
            )).scalar_one_or_none()

            if existing:
                existing.ad_count = (existing.ad_count or 0) + data["ad_count"]
                old_channels = set(existing.channels or [])
                existing.channels = sorted(old_channels | data["channels"])
                if data["last_seen"] and (not existing.last_ad_seen or data["last_seen"] > existing.last_ad_seen):
                    existing.last_ad_seen = data["last_seen"]
                if data["first_seen"] and (not existing.first_ad_seen or data["first_seen"] < existing.first_ad_seen):
                    existing.first_ad_seen = data["first_seen"]
                existing.updated_at = datetime.utcnow()
            else:
                product = AdvertiserProduct(
                    advertiser_id=adv_id,
                    product_name=prod_name,
                    product_category_id=data["cat_id"],
                    source="ad_observed",
                    channels=sorted(data["channels"]),
                    ad_count=data["ad_count"],
                    first_ad_seen=data["first_seen"],
                    last_ad_seen=data["last_seen"],
                )
                s.add(product)
            products_updated += 1

        await s.commit()

        # Step 4: Build daily activity
        # Refresh product lookup
        all_products = (await s.execute(select(AdvertiserProduct))).scalars().all()
        product_lookup = {(p.advertiser_id, p.product_name): p.id for p in all_products}

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
            .where(
                AdDetail.advertiser_id.is_not(None),
                AdSnapshot.captured_at >= cutoff,
            )
            .group_by(
                AdDetail.advertiser_id,
                func.coalesce(AdDetail.product_name, AdDetail.product_category, "Unknown"),
                func.date(AdSnapshot.captured_at),
                AdSnapshot.channel,
                AdDetail.ad_product_name,
            )
        )
        daily_rows = (await s.execute(daily_q)).all()

        activities_created = 0
        for row in daily_rows:
            adv_id, prod_name, dt, channel, ad_prod_name, ad_count, unique_cr = row
            prod_id = product_lookup.get((adv_id, prod_name))
            if not prod_id:
                continue

            if isinstance(dt, str):
                dt = datetime.strptime(dt, "%Y-%m-%d")

            # Check existing
            existing = (await s.execute(
                select(ProductAdActivity.id).where(
                    ProductAdActivity.advertiser_product_id == prod_id,
                    func.date(ProductAdActivity.date) == dt,
                    ProductAdActivity.channel == channel,
                )
            )).scalar_one_or_none()

            if not existing:
                activity = ProductAdActivity(
                    advertiser_product_id=prod_id,
                    date=dt,
                    channel=channel,
                    ad_product_name=ad_prod_name,
                    ad_count=ad_count,
                    unique_creatives=unique_cr,
                )
                s.add(activity)
                activities_created += 1

        await s.commit()

        result = {
            "products_updated": products_updated,
            "activities_created": activities_created,
        }
        logger.info(f"Marketing schedule update complete: {result}")
        return result


if __name__ == "__main__":
    async def _run():
        await init_db()
        result = await update_marketing_schedule(days_back=365)
        print(f"Result: {result}")
    asyncio.run(_run())
