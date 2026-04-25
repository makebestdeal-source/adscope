# -*- coding: utf-8 -*-
import sqlite3, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('adscope.db')
c = conn.cursor()

# 동일 도메인에 광고주 3개 이상인 URL 중복 확인
print("=== 동일 URL → 복수 광고주 (3개 이상) ===")
c.execute("""
SELECT website, COUNT(*) as cnt, GROUP_CONCAT(name, ' | ') as names
FROM advertisers
WHERE website IS NOT NULL AND website <> ''
GROUP BY website
HAVING cnt >= 3
ORDER BY cnt DESC
LIMIT 30
""")
for r in c.fetchall():
    names_preview = r[2][:100] if r[2] else ''
    print(f"  [{r[1]}개] {r[0]}")
    print(f"    → {names_preview}")

# 이상한 기호/혼합 스크립트 광고주
print()
print("=== 이상한 이름 패턴 (비한글·영문 기호 혼합) ===")
c.execute("SELECT id, name, website FROM advertisers")
rows = c.fetchall()
garbage = []
for adv_id, name, website in rows:
    # 유니코드 특수문자 블록 (이집트 상형문자, 수학기호 등)
    has_exotic = bool(re.search(r'[\U00010000-\U0001FFFF\u2200-\u22FF\u27C0-\u27EF\u2A00-\u2AFF]', name))
    # 그리스/키릴/히브리 + 한글 혼합 (homoglyph attack 패턴)
    has_mixed = (bool(re.search(r'[\u0370-\u03FF\u0400-\u04FF]', name)) and
                 bool(re.search(r'[\uAC00-\uD7A3]', name)))
    # Instagram 협찬 텍스트
    is_sponsored = '페이지는' in name and '함께합니다' in name
    # 광고문구 통째로 이름에
    is_ad_copy = len(name) > 40 and ('무료' in name or '할인' in name or '지금' in name or '주문' in name)

    if has_exotic or has_mixed or is_sponsored or is_ad_copy:
        garbage.append((adv_id, name, website,
                        'exotic' if has_exotic else 'mixed_script' if has_mixed else
                        'instagram_sponsored' if is_sponsored else 'ad_copy'))

print(f"  이상 광고주: {len(garbage)}개")
for adv_id, name, website, reason in garbage[:30]:
    print(f"  [{reason}] id={adv_id} '{name[:60]}' / {website or '(no url)'}")

# DramaBox 등 글로벌 쇼트드라마 앱 잔존 현황
print()
print("=== 글로벌 쇼트드라마 앱 잔존 (DramaBox/Vigloo/Dramawave 등) ===")
c.execute("""
SELECT website, COUNT(*) as cnt
FROM advertisers
WHERE (
  name LIKE '%DramaBox%' OR name LIKE '%Dramawave%' OR
  name LIKE '%Vigloo%' OR name LIKE '%ReelShort%' OR
  name LIKE '%Shortmax%' OR name LIKE '%drama%'
)
GROUP BY website
ORDER BY cnt DESC
LIMIT 20
""")
for r in c.fetchall():
    print(f"  {r[1]}개 → {r[0]}")

print()
c.execute("""
SELECT COUNT(*) FROM advertisers
WHERE (
  name LIKE '%DramaBox%' OR name LIKE '%Dramawave%' OR
  name LIKE '%Vigloo%' OR name LIKE '%ReelShort%' OR
  name LIKE '%drama%' OR name LIKE '%Drama%'
)
""")
print(f"Drama 관련 광고주 총: {c.fetchone()[0]}개")

conn.close()
