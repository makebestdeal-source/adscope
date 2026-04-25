import sqlite3, os, json

os.chdir(r"c:\Users\user\Desktop\adscopre")
conn = sqlite3.connect("adscope.db")
cur = conn.cursor()

print("=== 최신 GDN 이미지 경로 실존 확인 ===")
cur.execute("""
SELECT d.creative_image_path
FROM ad_details d
JOIN ad_snapshots s ON s.id = d.snapshot_id
WHERE s.channel = 'google_gdn'
  AND d.creative_image_path IS NOT NULL AND d.creative_image_path != ''
ORDER BY s.captured_at DESC
LIMIT 10
""")
for r in cur.fetchall():
    p = r[0].replace("\\", "/")
    exists = os.path.exists(p)
    print(f"  {'OK' if exists else 'MISS'} | {p[:90]}")
conn.close()
import sys; sys.exit(0)

print("=== 날짜별 이미지 저장 현황 (3/26 이후) ===")
cur.execute("""
SELECT
  date(s.captured_at) as dt,
  s.channel,
  COUNT(*) as total,
  SUM(CASE WHEN d.creative_image_path IS NOT NULL AND d.creative_image_path != '' THEN 1 ELSE 0 END) as has_img
FROM ad_details d
JOIN ad_snapshots s ON s.id = d.snapshot_id
WHERE s.captured_at >= '2026-03-26'
  AND s.channel NOT IN ('naver_search', 'google_search_ads')
GROUP BY dt, s.channel ORDER BY dt, s.channel
""")
for r in cur.fetchall():
    pct = round(r[3]/r[2]*100) if r[2] else 0
    print(f"  {r[0]} {r[1]:15s} {r[3]}/{r[2]} ({pct}%)")

print("\n=== 3/26 이후 이미지 있는 광고 경로 샘플 ===")
cur.execute("""
SELECT s.channel, d.creative_image_path
FROM ad_details d
JOIN ad_snapshots s ON s.id = d.snapshot_id
WHERE s.captured_at >= '2026-03-26'
  AND d.creative_image_path IS NOT NULL AND d.creative_image_path != ''
LIMIT 10
""")
for r in cur.fetchall():
    p = r[1]
    print(f"  {r[0]} | EXISTS={os.path.exists(p)} | {p[:90]}")

print("\n=== extra_data에 image URL 포함 여부 (이미지 없는 GDN 샘플) ===")
cur.execute("""
SELECT d.extra_data
FROM ad_details d
JOIN ad_snapshots s ON s.id = d.snapshot_id
WHERE s.channel = 'google_gdn'
  AND s.captured_at >= '2026-03-26'
  AND (d.creative_image_path IS NULL OR d.creative_image_path = '')
LIMIT 5
""")
for r in cur.fetchall():
    if r[0]:
        try:
            ed = json.loads(r[0])
            keys = list(ed.keys())[:8]
            print(f"  keys: {keys}")
            if 'image_url' in ed: print(f"  image_url: {ed['image_url'][:80]}")
            if 'creative_url' in ed: print(f"  creative_url: {ed['creative_url'][:80]}")
        except:
            print(f"  raw: {str(r[0])[:100]}")

conn.close()
