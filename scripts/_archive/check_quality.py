"""최근 크롤링 결과 광고주명 품질 확인."""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://adscope:adscope@localhost:5433/adscope?ssl=disable",
)

from database import async_session, init_db
from sqlalchemy import text


async def check():
    await init_db()
    async with async_session() as s:
        # 최근 크롤링 결과의 광고주명 상태
        r = await s.execute(text("""
            SELECT s.channel, s.device,
                   COUNT(*) as total,
                   SUM(CASE WHEN d.advertiser_name_raw IS NOT NULL AND d.advertiser_name_raw <> '' THEN 1 ELSE 0 END) as has_name,
                   SUM(CASE WHEN d.advertiser_name_raw IS NULL OR d.advertiser_name_raw = '' THEN 1 ELSE 0 END) as no_name
            FROM ad_details d
            JOIN ad_snapshots s ON s.id = d.snapshot_id
            WHERE s.captured_at >= NOW() - INTERVAL '1 hour'
            GROUP BY s.channel, s.device
            ORDER BY s.channel
        """))
        rows = r.all()
        print("=" * 55)
        print("  최근 1시간 수집 결과 — 광고주명 품질")
        print("=" * 55)
        print(f"  {'채널':<18} {'디바이스':<8} {'총':>4} {'광고주O':>6} {'광고주X':>6}")
        print("-" * 55)
        for row in rows:
            print(f"  {row[0]:<18} {row[1]:<8} {row[2]:>4} {row[3]:>6} {row[4]:>6}")

        # 상세 내역 - 광고주명 샘플
        r2 = await s.execute(text("""
            SELECT s.channel, d.advertiser_name_raw, SUBSTRING(d.ad_text, 1, 50) as ad_text
            FROM ad_details d
            JOIN ad_snapshots s ON s.id = d.snapshot_id
            WHERE s.captured_at >= NOW() - INTERVAL '1 hour'
            ORDER BY s.channel, d.id
            LIMIT 40
        """))
        rows2 = r2.all()
        print()
        print("=" * 90)
        print("  광고주명 샘플 (최대 40건)")
        print("=" * 90)
        for row in rows2:
            name = row[1] or "(NULL)"
            text_val = row[2] or ""
            print(f"  [{row[0]:<14}] {name:<30} | {text_val}")


if __name__ == "__main__":
    asyncio.run(check())
