"""DART 광고비 보강 마이그레이션
신규 테이블: dart_financials, spend_allocations
기존 컬럼 추가: ad_details(4개), spend_estimates(2개), advertisers(2개)
"""
import sys
from pathlib import Path
_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)

import sqlite3
import asyncio
from database import init_db  # 신규 테이블 CREATE TABLE IF NOT EXISTS

DB_PATH = Path(_root) / "adscope.db"

def run_sqlite_alters():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    alters = [
        # ad_details
        "ALTER TABLE ad_details ADD COLUMN archive_source VARCHAR(50)",
        "ALTER TABLE ad_details ADD COLUMN ad_delivery_start DATETIME",
        "ALTER TABLE ad_details ADD COLUMN ad_delivery_end DATETIME",
        "ALTER TABLE ad_details ADD COLUMN is_retroactive BOOLEAN DEFAULT 0",
        # spend_estimates
        "ALTER TABLE spend_estimates ADD COLUMN data_source VARCHAR(30)",
        "ALTER TABLE spend_estimates ADD COLUMN confidence_tier VARCHAR(10)",
        # advertisers
        "ALTER TABLE advertisers ADD COLUMN corp_code VARCHAR(20)",
        "ALTER TABLE advertisers ADD COLUMN dart_matched_at DATETIME",
    ]

    for sql in alters:
        try:
            cur.execute(sql)
            print(f"OK: {sql[:60]}")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"SKIP (already exists): {sql[:60]}")
            else:
                raise

    conn.commit()
    conn.close()

async def main():
    run_sqlite_alters()       # ALTER TABLE (기존 컬럼)
    await init_db()            # CREATE TABLE IF NOT EXISTS (신규 테이블)
    print("Migration complete.")

if __name__ == "__main__":
    asyncio.run(main())
