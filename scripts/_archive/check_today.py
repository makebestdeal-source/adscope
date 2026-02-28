import sqlite3, sys

conn = sqlite3.connect('adscope.db')
c = conn.cursor()

# Today's ads by channel
c.execute("""
    SELECT s.channel, d.advertiser_name_raw, d.ad_text, d.url
    FROM ad_details d
    JOIN ad_snapshots s ON d.snapshot_id = s.id
    WHERE DATE(s.captured_at) = '2026-02-18'
    ORDER BY s.channel, d.id
""")
rows = c.fetchall()
prev = ''
for ch, adv, text, url in rows:
    ch = ch or '?'
    if ch != prev:
        prev = ch
        print(f'\n=== {ch} ===')
    adv = (adv or '?')[:30]
    text = (text or '')[:40]
    url = (url or '')[:40]
    print(f'  {adv} | {text} | {url}')

print(f'\nTotal today: {len(rows)}')

# Facebook/Instagram specifically
print('\n\n=== FB/IG advertiser countries ===')
c.execute("""
    SELECT s.channel, d.advertiser_name_raw, d.extra_data
    FROM ad_details d
    JOIN ad_snapshots s ON d.snapshot_id = s.id
    WHERE DATE(s.captured_at) = '2026-02-18'
    AND s.channel IN ('facebook', 'instagram')
    LIMIT 20
""")
for ch, adv, extra in c.fetchall():
    extra_short = (extra or '')[:100]
    print(f'  [{ch}] {adv} | {extra_short}')

# Campaign/spend rebuild check
c.execute("SELECT COUNT(*) FROM campaigns")
print(f'\nCampaigns: {c.fetchone()[0]}')
c.execute("SELECT COUNT(*) FROM spend_estimates")
print(f'Spend estimates: {c.fetchone()[0]}')
c.execute("SELECT DATE(created_at), COUNT(*) FROM spend_estimates GROUP BY DATE(created_at) ORDER BY DATE(created_at) DESC LIMIT 5")
print('Spend by date:')
for d, cnt in c.fetchall():
    print(f'  {d}: {cnt}')

conn.close()
