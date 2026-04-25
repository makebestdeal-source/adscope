# -*- coding: utf-8 -*-
import sqlite3, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
conn = sqlite3.connect('adscope.db')
c = conn.cursor()

# 1. 인스타 핸들 패턴 (_로 시작, ._.포함 등)
c.execute("""
SELECT a.id, a.name, a.data_source, a.website
FROM advertisers a
WHERE a.name LIKE '_%_%' AND a.name NOT LIKE '% %'
  AND LENGTH(a.name) < 30
  AND (a.name LIKE '_%.__%' OR a.name LIKE '___%')
LIMIT 30
""")
print("=== 인스타 핸들 의심 ===")
for r in c.fetchall():
    print(f"  id={r[0]:5d} | {r[1]:30s} | src: {r[2] or '-'}")

# 2. __yeorm, _pitka, _yosiro_ 직접 검색
for name in ['yeorm', 'pitka', 'yosiro']:
    c.execute("""
    SELECT a.id, a.name, a.data_source, ad.url, s.channel
    FROM advertisers a
    JOIN ad_details ad ON a.id = ad.advertiser_id
    JOIN ad_snapshots s ON ad.snapshot_id = s.id
    WHERE a.name LIKE ?
    LIMIT 3
    """, (f"%{name}%",))
    rows = c.fetchall()
    print(f"\n--- {name} ---")
    for r in rows:
        print(f"  id={r[0]} | {r[1]} | src={r[2]} | ch={r[4]}")
        print(f"  url={r[3][:80]}")

# 3. 쓰레기 광고주 유형별 수
print("\n\n=== 쓰레기 데이터 유형별 수 ===")

# 하우스광고 (네이버페이, 네이버로그인, 구글플레이 등)
c.execute("""
SELECT name, COUNT(*) FROM advertisers
WHERE name LIKE '%네이버페이%' OR name LIKE '%네이버로그인%'
   OR name LIKE '%NAVER Direct%' OR name LIKE '%구글플레이%'
   OR name LIKE '%Learn More%' OR name LIKE '%카카오%페이지%'
GROUP BY name ORDER BY COUNT(*) DESC
""")
print("\n하우스광고/플랫폼 서비스:")
for r in c.fetchall():
    print(f"  {r[0][:40]:40s} x{r[1]}")

# 일본어 광고주
c.execute("SELECT COUNT(*) FROM advertisers WHERE name LIKE '%会社%' OR name LIKE '%株式%'")
print(f"\n일본 법인 (株式会社 등): {c.fetchone()[0]}건")

# 채널별 website 보유율
print("\n=== 채널별 광고주 website 보유율 ===")
c.execute("""
SELECT s.channel,
  COUNT(DISTINCT a.id) as total_adv,
  COUNT(DISTINCT CASE WHEN a.website IS NOT NULL AND a.website <> '' THEN a.id END) as with_site,
  ROUND(100.0 * COUNT(DISTINCT CASE WHEN a.website IS NOT NULL AND a.website <> '' THEN a.id END) / COUNT(DISTINCT a.id), 1) as pct
FROM ad_details ad
JOIN ad_snapshots s ON ad.snapshot_id = s.id
JOIN advertisers a ON ad.advertiser_id = a.id
GROUP BY s.channel
ORDER BY total_adv DESC
""")
for r in c.fetchall():
    print(f"  {r[0]:20s} | {r[2]:4d}/{r[1]:4d} ({r[3]}%)")

# display_url -> 실제 도메인 추출 가능 여부
print("\n=== display_url 샘플 (website 없는 광고주) ===")
c.execute("""
SELECT a.name, ad.display_url, s.channel
FROM ad_details ad
JOIN ad_snapshots s ON ad.snapshot_id = s.id
JOIN advertisers a ON ad.advertiser_id = a.id
WHERE (a.website IS NULL OR a.website = '')
  AND ad.display_url IS NOT NULL AND ad.display_url <> ''
  AND ad.display_url NOT LIKE '%naver%' AND ad.display_url NOT LIKE '%tivan%'
  AND ad.display_url NOT LIKE '%pstatic%'
LIMIT 20
""")
for r in c.fetchall():
    print(f"  {r[0][:25]:25s} | {r[1][:40]:40s} | {r[2]}")

conn.close()
