"""Show recent crawl results from DB."""
import sqlite3
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

conn = sqlite3.connect("adscope.db")
cur = conn.cursor()

# 1. 채널/디바이스별 요약
cur.execute("""
    SELECT s.channel, s.device, COUNT(d.id) as ad_count
    FROM ad_details d
    JOIN ad_snapshots s ON s.id = d.snapshot_id
    WHERE s.captured_at >= datetime('now', '-1 day')
    GROUP BY s.channel, s.device
    ORDER BY ad_count DESC
""")
print("=" * 45)
print("  Channel/Device Summary (last 24h)")
print("=" * 45)
total = 0
for row in cur.fetchall():
    ch, dev, cnt = row
    print(f"  {ch:<18} {dev:<8} {cnt:>4}")
    total += cnt
print("-" * 45)
print(f"  {'TOTAL':<26} {total:>4}")
print()

# 2. 상세 데이터
cur.execute("""
    SELECT s.channel, s.device,
           d.advertiser_name_raw,
           SUBSTR(d.ad_text, 1, 50) as ad_text,
           d.ad_type, d.position,
           d.display_url
    FROM ad_details d
    JOIN ad_snapshots s ON s.id = d.snapshot_id
    WHERE s.captured_at >= datetime('now', '-1 day')
    ORDER BY s.channel, s.device, d.position
    LIMIT 80
""")

print("=" * 100)
print("  Recent Ads Detail (max 80)")
print("=" * 100)

rows = cur.fetchall()
prev_ch = None
for row in rows:
    ch_key = f"{row[0]}({row[1]})"
    if ch_key != prev_ch:
        print(f"\n--- {ch_key} ---")
        prev_ch = ch_key
    adv = (row[2] or "(unknown)")[:22]
    txt = (row[3] or "")[:45]
    pos = row[5] or 0
    atype = (row[4] or "")[:16]
    durl = (row[6] or "")[:25]
    print(f"  #{pos:<2} [{atype:<16}] {adv:<22} {durl:<25} | {txt}")

# 3. 광고주 미확인 비율
cur.execute("""
    SELECT
        COUNT(*) as total,
        SUM(CASE WHEN d.advertiser_name_raw IS NULL OR d.advertiser_name_raw = '' THEN 1 ELSE 0 END) as unknown
    FROM ad_details d
    JOIN ad_snapshots s ON s.id = d.snapshot_id
    WHERE s.captured_at >= datetime('now', '-1 day')
""")
total_row = cur.fetchone()
if total_row and total_row[0] > 0:
    pct = round(total_row[1] / total_row[0] * 100, 1)
    print(f"\n--- Advertiser Detection ---")
    print(f"  Total: {total_row[0]}, Unknown: {total_row[1]} ({pct}%)")

conn.close()
