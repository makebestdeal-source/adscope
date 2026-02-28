"""Rebuild campaigns and spend_estimates from current DB snapshot data."""

import asyncio
import os
from pathlib import Path
import sys

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from processor.campaign_builder import rebuild_campaigns_and_spend


async def main():
    await init_db()
    logger.info(
        "Campaign rebuild excluded channels: {}",
        os.getenv("CAMPAIGN_EXCLUDED_CHANNELS", "youtube_ads"),
    )
    stats = await rebuild_campaigns_and_spend(active_days=7)
    logger.info(
        "Done: linked_details={} created_advertisers={} industry_backfilled={} "
        "updated_campaigns={} inserted_estimates={} totals(campaigns={}, spend_estimates={})",
        stats["linked_details"],
        stats["created_advertisers"],
        stats["industry_backfilled"],
        stats["updated_campaigns"],
        stats["inserted_estimates"],
        stats["campaigns_total"],
        stats["spend_estimates_total"],
    )


if __name__ == "__main__":
    asyncio.run(main())
