"""Backfill campaign metadata: start_at, end_at, status, creative_ids, product_service, promotion_copy, target_keywords."""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, UTC
from collections import Counter

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from sqlalchemy import select, func
from database import async_session
from database.models import Campaign, AdDetail, AdSnapshot, Advertiser


async def backfill():
    async with async_session() as session:
        campaigns = (await session.execute(select(Campaign))).scalars().all()
        updated = 0
        for c in campaigns:
            # start_at, end_at from first_seen/last_seen
            if not c.start_at:
                c.start_at = c.first_seen
            if not c.end_at:
                c.end_at = c.last_seen

            # status from is_active
            if not c.status or c.status == 'active':
                c.status = 'active' if c.is_active else 'completed'

            # creative_ids: find matching AdDetail IDs
            # Match by advertiser_id + channel (from snapshot)
            detail_q = (
                select(AdDetail.id)
                .join(AdSnapshot, AdDetail.snapshot_id == AdSnapshot.id)
                .where(AdDetail.advertiser_id == c.advertiser_id)
                .where(AdSnapshot.channel == c.channel)
            )
            detail_ids = [r[0] for r in (await session.execute(detail_q)).all()]
            c.creative_ids = detail_ids if detail_ids else None

            # product_service: most common product_name from linked details
            if not c.product_service and detail_ids:
                prod_q = (
                    select(AdDetail.product_name)
                    .where(AdDetail.id.in_(detail_ids[:100]))
                    .where(AdDetail.product_name.isnot(None))
                )
                prods = [r[0] for r in (await session.execute(prod_q)).all()]
                if prods:
                    c.product_service = Counter(prods).most_common(1)[0][0]

            # promotion_copy: most common ad_text
            if not c.promotion_copy and detail_ids:
                text_q = (
                    select(AdDetail.ad_text)
                    .where(AdDetail.id.in_(detail_ids[:100]))
                    .where(AdDetail.ad_text.isnot(None))
                )
                texts = [r[0] for r in (await session.execute(text_q)).all()]
                if texts:
                    c.promotion_copy = Counter(texts).most_common(1)[0][0]

            # target_keywords from advertiser
            if not c.target_keywords:
                adv = (await session.execute(
                    select(Advertiser).where(Advertiser.id == c.advertiser_id)
                )).scalar_one_or_none()
                if adv:
                    kw = {"brand": [adv.name]}
                    if adv.brand_name and adv.brand_name != adv.name:
                        kw["brand"].append(adv.brand_name)
                    if adv.aliases:
                        aliases = adv.aliases if isinstance(adv.aliases, list) else []
                        kw["brand"].extend(aliases)
                    if c.product_service:
                        kw["product"] = [c.product_service]
                    c.target_keywords = kw

            c.enrichment_status = 'pending'
            updated += 1

        await session.commit()
        print(f"Backfilled {updated} campaigns")


if __name__ == "__main__":
    from database import init_db

    async def main():
        await init_db()
        await backfill()

    asyncio.run(main())
