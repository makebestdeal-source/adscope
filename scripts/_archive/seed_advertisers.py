"""Advertiser seed v2 -- JSON-based bulk import.

Loads data/advertiser_seed.json and upserts industries + advertisers.

Usage:
  python scripts/seed_advertisers.py [--dry-run]
"""

import asyncio
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from database import async_session, init_db
from database.models import Advertiser, Industry
from sqlalchemy import select, func


SEED_PATH = Path(_root) / "data" / "advertiser_seed.json"


def load_seed() -> dict:
    """Load JSON seed file."""
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def upsert_industries(session, industries: list[dict]) -> dict[str, int]:
    """Create or update industries. Returns name -> id map."""
    result = await session.execute(select(Industry))
    existing = {ind.name: ind for ind in result.scalars().all()}

    for item in industries:
        name = item["name"]
        if name in existing:
            ind = existing[name]
            ind.avg_cpc_min = item.get("avg_cpc_min", ind.avg_cpc_min)
            ind.avg_cpc_max = item.get("avg_cpc_max", ind.avg_cpc_max)
        else:
            ind = Industry(
                name=name,
                avg_cpc_min=item.get("avg_cpc_min"),
                avg_cpc_max=item.get("avg_cpc_max"),
            )
            session.add(ind)
            existing[name] = ind

    await session.flush()

    # Reload to get all IDs
    result = await session.execute(select(Industry))
    return {ind.name: ind.id for ind in result.scalars().all()}


async def upsert_advertisers(
    session,
    advertisers: list[dict],
    industry_map: dict[str, int],
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Create new or update existing advertisers.

    Returns (created, updated, skipped) counts.
    """
    result = await session.execute(select(Advertiser))
    existing = {}
    for adv in result.scalars().all():
        existing[adv.name.lower()] = adv

    now = datetime.now(timezone.utc)
    created = 0
    updated = 0
    skipped = 0

    for item in advertisers:
        name = item["name"]
        key = name.lower()
        industry_id = industry_map.get(item.get("industry"))

        channels = item.get("channels", {})
        aliases = item.get("aliases", [])

        if key in existing:
            adv = existing[key]
            changed = False

            if industry_id and adv.industry_id != industry_id:
                adv.industry_id = industry_id
                changed = True
            if item.get("type") and adv.advertiser_type != item["type"]:
                adv.advertiser_type = item["type"]
                changed = True
            if item.get("brand") and adv.brand_name != item["brand"]:
                adv.brand_name = item["brand"]
                changed = True
            if item.get("website") and adv.website != item["website"]:
                adv.website = item["website"]
                changed = True
            if aliases and adv.aliases != aliases:
                adv.aliases = aliases
                changed = True
            if channels and adv.official_channels != channels:
                adv.official_channels = channels
                changed = True

            if changed:
                adv.data_source = "seed_v2"
                adv.profile_updated_at = now
                updated += 1
            else:
                skipped += 1
        else:
            adv = Advertiser(
                name=name,
                industry_id=industry_id,
                advertiser_type=item.get("type"),
                brand_name=item.get("brand"),
                website=item.get("website"),
                aliases=aliases,
                official_channels=channels,
                data_source="seed_v2",
                profile_updated_at=now,
            )
            session.add(adv)
            existing[key] = adv
            created += 1

    return created, updated, skipped


async def print_summary(session):
    """Print advertiser count by industry."""
    stmt = (
        select(Industry.name, func.count(Advertiser.id))
        .outerjoin(Advertiser, Advertiser.industry_id == Industry.id)
        .group_by(Industry.name)
        .order_by(func.count(Advertiser.id).desc())
    )
    result = await session.execute(stmt)
    rows = result.fetchall()

    total_stmt = select(func.count(Advertiser.id))
    total_result = await session.execute(total_stmt)
    total = total_result.scalar() or 0

    print(f"\n[Summary] Total advertisers in DB: {total}")
    print(f"{'Industry':<20} {'Count':>6}")
    print("-" * 28)
    for name, cnt in rows:
        print(f"{name:<20} {cnt:>6}")


async def main(dry_run: bool = False):
    """Main entry point."""
    await init_db()

    seed = load_seed()
    industries = seed.get("industries", [])
    advertisers = seed.get("advertisers", [])

    print(f"Loaded seed: {len(industries)} industries, {len(advertisers)} advertisers")

    async with async_session() as session:
        # 1. Industries
        industry_map = await upsert_industries(session, industries)
        print(f"Industries synced: {len(industry_map)} total")

        # 2. Advertisers
        created, updated, skipped = await upsert_advertisers(
            session, advertisers, industry_map, dry_run=dry_run
        )
        print(
            f"Advertisers: {created} created, {updated} updated, {skipped} unchanged"
        )

        if dry_run:
            print("(DRY-RUN) Rolling back changes.")
            await session.rollback()
        else:
            await session.commit()
            print("Committed to DB.")

        # 3. Summary
        await print_summary(session)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed advertisers from JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to DB",
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
