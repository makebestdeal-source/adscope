"""Temporary script to check URL collection status."""
import sqlite3
import sys
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")
conn = sqlite3.connect("adscope.db")
c = conn.cursor()

# 1. website 없는 광고주인데 ad URL은 있는 경우
c.execute("""
    SELECT a.id, a.name, COUNT(DISTINCT ad.url) as ucnt
    FROM advertisers a
    JOIN ad_details ad ON ad.advertiser_id = a.id
    WHERE (a.website IS NULL OR a.website = '')
      AND ad.url IS NOT NULL AND ad.url <> ''
    GROUP BY a.id
    ORDER BY ucnt DESC
    LIMIT 20
""")
print("=== website X but ad URL O - TOP 20 ===")
for r in c.fetchall():
    print(f"  id={r[0]} [{r[1]}] unique_urls={r[2]}")

c.execute("""
    SELECT COUNT(DISTINCT a.id)
    FROM advertisers a
    JOIN ad_details ad ON ad.advertiser_id = a.id
    WHERE (a.website IS NULL OR a.website = '')
      AND ad.url IS NOT NULL AND ad.url <> ''
""")
print(f"\ntotal: {c.fetchone()[0]}")

# 2. Sample URLs for website-less advertisers
c.execute("""
    SELECT a.id, a.name, ad.url
    FROM advertisers a
    JOIN ad_details ad ON ad.advertiser_id = a.id
    WHERE (a.website IS NULL OR a.website = '')
      AND ad.url IS NOT NULL AND ad.url <> ''
    GROUP BY a.id
    LIMIT 15
""")
print("\n=== Samples ===")
for r in c.fetchall():
    try:
        domain = urlparse(r[2]).netloc.replace("www.", "")
    except Exception:
        domain = "?"
    print(f"  [{r[1]}] -> {domain} ({r[2][:70]})")

# 3. Auto-fix: set website from most common ad URL domain
print("\n=== Auto-fixable advertisers ===")
c.execute("""
    SELECT a.id, a.name, ad.url, COUNT(*) as cnt
    FROM advertisers a
    JOIN ad_details ad ON ad.advertiser_id = a.id
    WHERE (a.website IS NULL OR a.website = '')
      AND ad.url IS NOT NULL AND ad.url <> ''
    GROUP BY a.id, SUBSTR(ad.url, 1, INSTR(ad.url || '/', '/') + INSTR(SUBSTR(ad.url, INSTR(ad.url, '//') + 2), '/'))
    ORDER BY a.id, cnt DESC
""")
fix_map = {}
for r in c.fetchall():
    if r[0] not in fix_map:
        try:
            domain = urlparse(r[2]).netloc.replace("www.", "")
            if domain:
                fix_map[r[0]] = (r[1], domain)
        except Exception:
            pass

print(f"  Can auto-fix: {len(fix_map)} advertisers")
for aid, (name, domain) in list(fix_map.items())[:10]:
    print(f"    [{name}] -> {domain}")

# 4. Apply fix
updated = 0
for aid, (name, domain) in fix_map.items():
    c.execute("UPDATE advertisers SET website = ? WHERE id = ? AND (website IS NULL OR website = '')", (domain, aid))
    updated += c.rowcount

conn.commit()
print(f"\n>> Updated {updated} advertisers with website from ad URLs")

# Final stats
c.execute("SELECT COUNT(*) FROM advertisers WHERE website IS NOT NULL AND website <> ''")
print(f">> Advertisers with website: {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM advertisers WHERE website IS NULL OR website = ''")
print(f">> Advertisers without website: {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM advertisers")
print(f">> Total: {c.fetchone()[0]}")

conn.close()
