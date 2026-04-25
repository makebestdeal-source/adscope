import sqlite3
from collections import Counter

conn = sqlite3.connect("adscope.db")
c = conn.cursor()

# content_id가 여러 advertiser_id에 걸쳐 있는 경우 (다른 광고주로 같은 영상이 등록)
c.execute("""
SELECT content_id, platform, COUNT(DISTINCT advertiser_id) as adv_cnt, COUNT(*) as total
FROM brand_channel_contents
WHERE content_id IS NOT NULL AND content_id != ''
GROUP BY content_id, platform
HAVING adv_cnt > 1
ORDER BY total DESC
LIMIT 20
""")
rows = c.fetchall()
print(f"같은 content_id, 다른 광고주: {len(rows)}건")
for r in rows[:10]:
    print(f"  {r[1]} cid={r[0][:15]} adv_cnt={r[2]} total={r[3]}")

# 소셜 갤러리에서 어느 채널/광고주가 가장 많은지
c.execute("""
SELECT a.name, b.platform, COUNT(*) as cnt
FROM brand_channel_contents b
LEFT JOIN advertisers a ON b.advertiser_id = a.id
GROUP BY b.advertiser_id, b.platform
ORDER BY cnt DESC
LIMIT 15
""")
print("\n광고주별 소셜 콘텐츠 수 (상위 15):")
for r in c.fetchall():
    print(f"  {str(r[0])[:25]} / {r[1]} : {r[2]}건")

conn.close()
