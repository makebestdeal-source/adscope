"""Sync new industries + keywords from seed JSON into the database (additive only)."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from database import async_session, init_db
from database.models import Keyword, Industry


async def sync_keywords():
    await init_db()

    seed_dir = Path(__file__).resolve().parent.parent / "database" / "seed_data"

    # -- Sync industries first (FK dependency) --
    industries_path = seed_dir / "industries.json"
    if industries_path.exists():
        with open(industries_path, encoding="utf-8") as f:
            industries_data = json.load(f)

        async with async_session() as session:
            ind_added = 0
            for item in industries_data:
                result = await session.execute(
                    select(Industry).where(Industry.id == item["id"])
                )
                if not result.scalar_one_or_none():
                    session.add(Industry(
                        id=item["id"],
                        name=item["name"],
                        avg_cpc_min=item.get("avg_cpc_min"),
                        avg_cpc_max=item.get("avg_cpc_max"),
                    ))
                    ind_added += 1
            if ind_added > 0:
                await session.commit()
                print(f"Added {ind_added} new industries")

    # -- Sync keywords --
    seed_path = seed_dir / "keywords.json"
    with open(seed_path, encoding="utf-8") as f:
        seed_data = json.load(f)

    async with async_session() as session:
        existing = await session.execute(select(Keyword.keyword))
        existing_set = {row[0] for row in existing.all()}
        print(f"DB existing keywords: {len(existing_set)}")

        added = 0
        for item in seed_data:
            kw = item["keyword"].strip()
            if kw not in existing_set:
                session.add(Keyword(
                    industry_id=item["industry_id"],
                    keyword=kw,
                    naver_cpc=item.get("naver_cpc"),
                    monthly_search_vol=item.get("monthly_search_vol"),
                ))
                added += 1
                print(f"  + {kw} (industry={item['industry_id']})")

        if added > 0:
            await session.commit()

        total = await session.execute(select(Keyword))
        total_count = len(total.all())
        print(f"\nAdded: {added}")
        print(f"DB total keywords: {total_count}")


if __name__ == "__main__":
    asyncio.run(sync_keywords())
