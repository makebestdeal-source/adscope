"""Initialize shopping_keywords table from seed data.

Usage: python scripts/init_shopping_keywords.py
"""

import asyncio
import json
from pathlib import Path

from loguru import logger

from database import async_session
from database.models import Base, ShoppingKeyword


async def init_shopping_keywords():
    """Create shopping_keywords table and populate from seed data."""
    # 1. Create table if not exists
    from database import engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    logger.info("shopping_keywords table ensured")

    # 2. Load seed data
    seed_path = Path("database/seed_data/shopping_keywords.json")
    if not seed_path.exists():
        logger.error(f"Seed file not found: {seed_path}")
        return

    with open(seed_path, encoding="utf-8") as f:
        data = json.load(f)

    # 3. Insert keywords (skip duplicates)
    inserted = 0
    skipped = 0
    async with async_session() as session:
        for group in data:
            category = group.get("category", "")
            subcategory = group.get("subcategory", "")
            keywords = group.get("keywords", [])

            for i, kw in enumerate(keywords):
                kw = kw.strip()
                if not kw:
                    continue

                # Check if already exists
                from sqlalchemy import select
                exists = await session.execute(
                    select(ShoppingKeyword.id).where(ShoppingKeyword.keyword == kw)
                )
                if exists.scalar_one_or_none():
                    skipped += 1
                    continue

                session.add(ShoppingKeyword(
                    keyword=kw,
                    category=category,
                    subcategory=subcategory,
                    priority=5,  # default priority
                    is_active=True,
                ))
                inserted += 1

        await session.commit()

    logger.info(f"Shopping keywords: inserted={inserted}, skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(init_shopping_keywords())
