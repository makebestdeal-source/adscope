# -*- coding: utf-8 -*-
"""Run smartstore collector for advertisers with smartstore_url set."""
import asyncio
import logging
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, '.')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
logging.getLogger('processor.smartstore_collector').setLevel(logging.DEBUG)

async def main():
    from database import init_db
    await init_db()

    from processor.smartstore_collector import collect_smartstore_signals

    # Get advertiser IDs with smartstore_url set
    import sqlite3
    conn = sqlite3.connect('adscope.db')
    cur = conn.cursor()
    cur.execute("SELECT id, name, smartstore_url FROM advertisers WHERE smartstore_url IS NOT NULL AND smartstore_url <> ''")
    rows = cur.fetchall()
    conn.close()

    ids = [r[0] for r in rows]
    print(f"Running for {len(ids)} advertisers with smartstore URLs:")
    for r in rows:
        print(f"  {r[0]} | {r[1]} | {r[2]}")

    result = await collect_smartstore_signals(advertiser_ids=ids)
    print(f"\nResult: {result}")

    # Show what was saved
    conn = sqlite3.connect('adscope.db')
    cur = conn.cursor()
    cur.execute("SELECT id, advertiser_id, store_name, product_name, review_count, price, seller_grade, captured_at FROM smartstore_snapshots ORDER BY id DESC LIMIT 20")
    snaps = cur.fetchall()
    conn.close()

    if snaps:
        print(f"\nLatest snapshots ({len(snaps)}):")
        for s in snaps:
            print(f"  id={s[0]} adv={s[1]} store={s[2]} product={s[3][:30] if s[3] else '?'} reviews={s[4]} price={s[5]} grade={s[6]} at={s[7]}")
    else:
        print("\nNo snapshots saved yet.")


if __name__ == "__main__":
    asyncio.run(main())
