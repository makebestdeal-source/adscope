import sqlite3

conn = sqlite3.connect('adscope.db')
c = conn.cursor()

# Get actual table names
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables:", tables)

# Find snapshot-like table
snapshot_table = None
for t in tables:
    if 'snapshot' in t.lower() or 'crawl' in t.lower():
        snapshot_table = t
        print(f"Snapshot table: {t}")
        c.execute(f"PRAGMA table_info({t})")
        for col in c.fetchall():
            print(f"  {col}")

# ad_details - check channel column
print()
c.execute("SELECT DISTINCT ad_placement FROM ad_details LIMIT 20")
print("ad_placements:", [r[0] for r in c.fetchall()])

# Check if ad_details has channel info via extra_data or other
c.execute("SELECT url FROM ad_details LIMIT 5")
print()
print("Sample URLs:")
for row in c.fetchall():
    print(f"  {row[0]}")

# advertiser website vs ad url
print()
print("=== Advertisers WITHOUT website (3312) ===")
print("But do their ads have URLs?")
c.execute("""
SELECT a.name, a.website, a.smartstore_url,
       COUNT(ad.id) as ad_cnt,
       COUNT(CASE WHEN ad.url IS NOT NULL AND ad.url <> '' THEN 1 END) as url_cnt
FROM advertisers a
LEFT JOIN ad_details ad ON a.id = ad.advertiser_id
WHERE a.website IS NULL OR a.website = ''
GROUP BY a.id
ORDER BY ad_cnt DESC
LIMIT 20
""")
for row in c.fetchall():
    name = (row[0] or "?")[:25]
    smart = (row[2] or "")[:35]
    print(f"  {name:25s} | smart: {smart:35s} | ads: {row[3]:4d} | with_url: {row[4]:4d}")

# Check: can we derive website from ad URLs?
print()
print("=== Can we derive website from ad_details.url? ===")
c.execute("""
SELECT a.name, ad.url
FROM advertisers a
JOIN ad_details ad ON a.id = ad.advertiser_id
WHERE (a.website IS NULL OR a.website = '')
LIMIT 20
""")
for row in c.fetchall():
    name = (row[0] or "?")[:25]
    url = (row[1] or "")[:80]
    print(f"  {name:25s} | {url}")

conn.close()
