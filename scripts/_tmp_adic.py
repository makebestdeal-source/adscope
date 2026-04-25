import sqlite3, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
conn = sqlite3.connect('adscope.db')

# 1. ADIC 업종별 광고비
print('=== ADIC: Top industries by ad spend ===')
rows = conn.execute("""
    SELECT industry, SUM(amount) as total
    FROM adic_ad_expenses
    WHERE medium = 'total' AND amount > 0
    GROUP BY industry
    ORDER BY total DESC
    LIMIT 30
""").fetchall()
for r in rows:
    name = r[0] if r[0] else '(none)'
    print(f'  {name:30s} | {r[1]/100000000:.1f} B')

# 2. ADIC 상위 광고주
print()
print('=== ADIC: Top 50 advertisers ===')
rows = conn.execute("""
    SELECT advertiser_name, industry, SUM(amount) as total
    FROM adic_ad_expenses
    WHERE medium = 'total' AND amount > 0
    GROUP BY advertiser_name
    ORDER BY total DESC
    LIMIT 50
""").fetchall()
for r in rows:
    name = r[0] if r[0] else '?'
    ind = r[1] if r[1] else '-'
    print(f'  {name:25s} | {ind:20s} | {r[2]/100000000:.1f} B')

# 3. ad_details 채널별 업종 분포 (product_category 기준)
print()
print('=== AdScope: product_category distribution ===')
rows = conn.execute("""
    SELECT d.product_category, COUNT(*) as cnt
    FROM ad_details d
    WHERE d.product_category IS NOT NULL AND d.product_category != ''
    GROUP BY d.product_category
    ORDER BY cnt DESC
    LIMIT 30
""").fetchall()
for r in rows:
    print(f'  {r[0]:30s} | {r[1]:5d}')

# 4. 네이버 검색 키워드별 수집량
print()
print('=== Naver search: keyword hit counts (from keywords table) ===')
rows = conn.execute("""
    SELECT k.keyword, COUNT(d.id) as cnt
    FROM ad_details d
    JOIN ad_snapshots s ON d.snapshot_id = s.id
    JOIN keywords k ON s.keyword_id = k.id
    WHERE s.channel = 'naver_search'
    GROUP BY k.keyword
    ORDER BY cnt DESC
    LIMIT 40
""").fetchall()
for r in rows:
    print(f'  {r[0]:25s} | {r[1]:5d}')

conn.close()
