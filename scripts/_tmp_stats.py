import sqlite3
conn = sqlite3.connect('adscope.db')

print('=== Creative images by channel (last 7 days) ===')
rows = conn.execute("""
    SELECT s.channel,
           COUNT(d.id) as total,
           SUM(CASE WHEN d.creative_image_path IS NOT NULL AND length(d.creative_image_path) > 0 THEN 1 ELSE 0 END) as with_image
    FROM ad_details d
    JOIN ad_snapshots s ON d.snapshot_id = s.id
    WHERE s.captured_at >= datetime('now', '-7 days')
    GROUP BY s.channel
    ORDER BY total DESC
""").fetchall()
for r in rows:
    pct = (r[2]/r[1]*100) if r[1] > 0 else 0
    print(f'  {r[0]:20s} | total: {r[1]:5d} | with_image: {r[2]:5d} ({pct:.0f}%)')

print()
print('=== Daily creative summary (last 7 days) ===')
rows = conn.execute("""
    SELECT DATE(s.captured_at) as dt, COUNT(d.id) as cnt,
           SUM(CASE WHEN d.creative_image_path IS NOT NULL AND length(d.creative_image_path) > 0 THEN 1 ELSE 0 END) as with_img
    FROM ad_details d
    JOIN ad_snapshots s ON d.snapshot_id = s.id
    WHERE s.captured_at >= datetime('now', '-7 days')
    GROUP BY dt ORDER BY dt DESC
""").fetchall()
for r in rows:
    pct = (r[2]/r[1]*100) if r[1] > 0 else 0
    print(f'  {r[0]} | {r[1]:5d} ads | {r[2]:5d} with_image ({pct:.0f}%)')

print()
print('=== URL collection rate by channel (last 3 days) ===')
rows = conn.execute("""
    SELECT s.channel,
           COUNT(d.id) as total,
           SUM(CASE WHEN d.url IS NOT NULL AND length(d.url) > 0 THEN 1 ELSE 0 END) as with_url
    FROM ad_details d
    JOIN ad_snapshots s ON d.snapshot_id = s.id
    WHERE s.captured_at >= datetime('now', '-3 days')
    GROUP BY s.channel
    ORDER BY total DESC
""").fetchall()
for r in rows:
    pct = (r[2]/r[1]*100) if r[1] > 0 else 0
    print(f'  {r[0]:20s} | total: {r[1]:5d} | with_url: {r[2]:5d} ({pct:.0f}%)')

print()
print('=== YouTube surf (last 7 days) ===')
rows = conn.execute("""
    SELECT DATE(s.captured_at) as dt, COUNT(d.id) as cnt
    FROM ad_details d
    JOIN ad_snapshots s ON d.snapshot_id = s.id
    WHERE s.channel = 'youtube_surf'
    AND s.captured_at >= datetime('now', '-7 days')
    GROUP BY dt ORDER BY dt DESC
""").fetchall()
for r in rows:
    print(f'  {r[0]} | {r[1]:5d}')
if not rows:
    print('  (no youtube_surf data in last 7 days)')

conn.close()
