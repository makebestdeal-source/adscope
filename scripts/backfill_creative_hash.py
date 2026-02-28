"""Backfill creative_hash for existing AdDetail rows that have NULL creative_hash."""
import asyncio
import io
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from database import async_session, init_db
from database.models import AdDetail
from processor.creative_hasher import compute_creative_hash, compute_text_hash
from sqlalchemy import select, func

BATCH_SIZE = 500


async def main():
    await init_db()

    async with async_session() as session:
        # Count total rows with NULL creative_hash
        count_result = await session.execute(
            select(func.count(AdDetail.id)).where(AdDetail.creative_hash == None)
        )
        total = count_result.scalar_one()

    print(f"Total rows with NULL creative_hash: {total}")

    processed = 0
    hashed = 0
    offset = 0

    while True:
        async with async_session() as session:
            result = await session.execute(
                select(AdDetail)
                .where(AdDetail.creative_hash == None)
                .order_by(AdDetail.id)
                .limit(BATCH_SIZE)
                .offset(offset)
            )
            rows = result.scalars().all()

        if not rows:
            break

        batch_hashed = 0
        async with async_session() as session:
            for row in rows:
                # Re-attach the row to this session by querying it
                db_row = await session.get(AdDetail, row.id)
                if db_row is None:
                    continue

                h = compute_creative_hash(db_row.creative_image_path)
                if h is None:
                    h = compute_text_hash(db_row.advertiser_name_raw, db_row.ad_text, db_row.url)

                if h is not None:
                    db_row.creative_hash = h
                    batch_hashed += 1

            await session.commit()

        processed += len(rows)
        hashed += batch_hashed
        offset += BATCH_SIZE
        print(
            f"Progress: {processed}/{total} processed, {hashed} hashed"
            f" (batch: {batch_hashed}/{len(rows)})"
        )

    print(f"Done. Total processed: {processed}, total hashed: {hashed}, skipped: {processed - hashed}")


if __name__ == "__main__":
    asyncio.run(main())
