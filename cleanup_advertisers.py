# -*- coding: utf-8 -*-
"""광고주 DB 3차 클린업 — 잘못된 canonical 이름 수정 + 나머지 불량 URL 정리"""
import sqlite3, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

conn = sqlite3.connect('adscope.db')
conn.execute("PRAGMA journal_mode=WAL")
c = conn.cursor()

# ─── 1. 불량 website (map.naver.com, blog.naver.com, 프로토콜 없는 것 포함) ───
print("=== 1. 남은 불량 URL 정리 ===")
BAD_REMAINING = [
    "map.naver.com", "blog.naver.com", "post.naver.com",
    "band.us", "cafe.naver.com",
]

# 불량 website를 가진 광고주 삭제
ids_to_delete = []
for domain in BAD_REMAINING:
    c.execute("SELECT id FROM advertisers WHERE website LIKE ?", (f"%{domain}%",))
    ids_to_delete += [r[0] for r in c.fetchall()]

if ids_to_delete:
    ids_to_delete = list(set(ids_to_delete))
    ph = ",".join("?"*len(ids_to_delete))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", ids_to_delete)
    for tbl, col in [("campaigns","advertiser_id"), ("brand_channel_contents","advertiser_id"),
                      ("channel_stats","advertiser_id"), ("news_mentions","advertiser_id"),
                      ("advertiser_favorites","advertiser_id")]:
        try: c.execute(f"DELETE FROM {tbl} WHERE {col} IN ({ph})", ids_to_delete)
        except: pass
    c.execute(f"DELETE FROM spend_estimates WHERE campaign_id IN (SELECT id FROM campaigns WHERE advertiser_id IN ({ph}))", ids_to_delete)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", ids_to_delete)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", ids_to_delete)
    print(f"  불량 URL 광고주 삭제: {c.rowcount}개")

# ─── 2. 병합 canonical 이름 수정 ───
# ad_details가 가장 많은 것이 domain 키워드와 매칭되면 그게 canonical
# 현재 잘못된 canonical을 브랜드명으로 바꿔줌
print("\n=== 2. 잘못된 canonical 이름 수정 ===")

# 도메인 → 올바른 브랜드명 매핑 (수동 보정)
CANONICAL_FIXES = {
    "https://themedicube.co.kr": "메디큐브",
    "https://food-ology.co.kr": "푸드올로지",
    "https://pethroom.com": "PETHROOM",
    "https://mommy-care.co.kr": "마미케어",
    "https://classu.co.kr": "클래스유",
    "https://3waau.com": "3WAAU",
    "https://spa-r.com": "스파알",
    "https://ollocdam.com": "올록담",
    "https://carmim.co.kr": "내차관리",
    "https://ergobody.co.kr": "Ergobody",
    "https://branden.shop": "브랜든 - Branden",
}

fixed = 0
for website, brand_name in CANONICAL_FIXES.items():
    # 해당 URL의 광고주 중 brand_name과 일치하는 것 찾기
    c.execute("SELECT id FROM advertisers WHERE website = ? AND name = ?", (website, brand_name))
    r = c.fetchone()
    if r:
        # 이미 올바른 이름으로 존재 → 현재 canonical과 swap
        correct_id = r[0]
        c.execute("SELECT id FROM advertisers WHERE website = ? AND id <> ? LIMIT 1",
                  (website, correct_id))
        wrong = c.fetchone()
        # 현재 canonical의 ad_details를 correct_id로 재배정
        if wrong:
            c.execute("UPDATE ad_details SET advertiser_id = ? WHERE advertiser_id = ?",
                      (correct_id, wrong[0]))
            c.execute("UPDATE campaigns SET advertiser_id = ? WHERE advertiser_id = ?",
                      (correct_id, wrong[0]))
            try:
                c.execute("DELETE FROM advertisers WHERE id = ?", (wrong[0],))
            except: pass
            fixed += 1
            print(f"  {website}: canonical → '{brand_name}' (id={correct_id})")
    else:
        # brand_name이 아직 없으면 현재 canonical 이름을 수정
        c.execute("SELECT id FROM advertisers WHERE website = ? LIMIT 1", (website,))
        r2 = c.fetchone()
        if r2:
            c.execute("UPDATE advertisers SET name = ? WHERE id = ?", (brand_name, r2[0]))
            fixed += 1
            print(f"  {website}: 이름 → '{brand_name}' (id={r2[0]})")
print(f"  수정 완료: {fixed}개")

# ─── 3. 이름에 URL 포함된 광고주 정리 ───
print("\n=== 3. 이름에 URL 포함 → 정리 ===")
c.execute("""
SELECT id, name FROM advertisers
WHERE name LIKE '%.com%' OR name LIKE '%.kr%' OR name LIKE '%.net%'
   OR name LIKE 'http%' OR name LIKE 'www.%'
""")
rows = c.fetchall()
fixed_url = 0
for adv_id, name in rows:
    # URL 부분 제거
    cleaned = re.sub(r'\s+(?:https?://)?(?:www\.)?[\w.-]+\.(?:com|kr|net|co\.kr|io|ai)(?:/\S*)?$', '', name).strip()
    # 이름 자체가 도메인인 경우 (예: "웨딩스타.com")
    cleaned = re.sub(r'\.(?:com|kr|net|co\.kr)$', '', cleaned).strip()
    if cleaned and cleaned != name and len(cleaned) >= 2:
        c.execute("UPDATE advertisers SET name = ? WHERE id = ?", (cleaned, adv_id))
        fixed_url += 1
        print(f"  '{name}' → '{cleaned}'")
print(f"  이름 URL 제거: {fixed_url}개")

# ─── 4. 일본어 광고주 (히라가나/가타카나) ───
print("\n=== 4. 일본어 광고주 삭제 ===")
import unicodedata
jp_re = re.compile(r'[\u3040-\u309F\u30A0-\u30FF]')
c.execute("SELECT id, name FROM advertisers")
all_advs = c.fetchall()
jp_ids = [r[0] for r in all_advs if r[1] and jp_re.search(r[1])]
if jp_ids:
    ph = ",".join("?"*len(jp_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", jp_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", jp_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", jp_ids)
    print(f"  일본어 광고주 삭제: {len(jp_ids)}개")
    for jid in jp_ids:
        matched = next((r[1] for r in all_advs if r[0] == jid), '')
        print(f"    {jid}: '{matched}'")
else:
    print("  없음")

# ─── 5. 의문문 광고주 (?, ？로 끝나는 것) ───
print("\n=== 5. 의문문 광고주 삭제 ===")
q_re = re.compile(r'[?？]\s*$')
q_ids = [r[0] for r in all_advs if r[1] and q_re.search(r[1])]
if q_ids:
    ph = ",".join("?"*len(q_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", q_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", q_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", q_ids)
    print(f"  의문문 광고주 삭제: {len(q_ids)}개")
    for qid in q_ids:
        matched = next((r[1] for r in all_advs if r[0] == qid), '')
        print(f"    {qid}: '{matched}'")
else:
    print("  없음")

# ─── 6. 순수 알파벳 2글자 이하 (gf, gg, gt, zb 등) ───
print("\n=== 6. 알파벳 2글자 이하 광고주 삭제 ===")
alpha_re = re.compile(r'^[a-zA-Z]{1,2}$')
al_ids = [r[0] for r in all_advs if r[1] and alpha_re.match(r[1].strip())]
if al_ids:
    ph = ",".join("?"*len(al_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", al_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", al_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", al_ids)
    print(f"  삭제: {len(al_ids)}개")
    for aid in al_ids:
        matched = next((r[1] for r in all_advs if r[0] == aid), '')
        print(f"    {aid}: '{matched}'")
else:
    print("  없음")

# ─── 7. 소문자알파벳+숫자 아이디형 (hjm2154 등) ───
print("\n=== 7. 알파벳+숫자 아이디형 광고주 삭제 ===")
uid_re = re.compile(r'^[a-z]{2,8}[0-9]{2,}$')
uid_ids = [r[0] for r in all_advs if r[1] and uid_re.match(r[1].strip())]
if uid_ids:
    ph = ",".join("?"*len(uid_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", uid_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", uid_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", uid_ids)
    print(f"  삭제: {len(uid_ids)}개")
    for uid in uid_ids:
        matched = next((r[1] for r in all_advs if r[0] == uid), '')
        print(f"    {uid}: '{matched}'")
else:
    print("  없음")

# ─── 8. place.naver.com / m.site.naver.com 등 네이버 내부 URL ───
print("\n=== 8. 네이버 내부 URL website 광고주 삭제 ===")
naver_internal = ["place.naver.com", "m.place.naver.com", "m.site.naver.com",
                  "blog.naver.com", "cafe.naver.com", "post.naver.com"]
nav_ids = []
for domain in naver_internal:
    c.execute("SELECT id FROM advertisers WHERE website LIKE ?", (f"%{domain}%",))
    nav_ids += [r[0] for r in c.fetchall()]
nav_ids = list(set(nav_ids))
if nav_ids:
    ph = ",".join("?"*len(nav_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", nav_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", nav_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", nav_ids)
    print(f"  삭제: {len(nav_ids)}개")
else:
    print("  없음")

# ─── 9. cafe24 사용자 숍 서브도메인 ───
print("\n=== 9. cafe24 서브도메인 광고주 삭제 ===")
c.execute("SELECT id, name, website FROM advertisers WHERE website LIKE '%.cafe24.com%'")
cafe24_rows = c.fetchall()
cafe24_ids = []
for r in cafe24_rows:
    w = r[2] or ''
    clean_w = w.replace('https://','').replace('http://','').replace('www.','').rstrip('/')
    if clean_w != 'cafe24.com':
        cafe24_ids.append(r[0])
        print(f"  {r[0]}: '{r[1]}' → {r[2]}")
if cafe24_ids:
    ph = ",".join("?"*len(cafe24_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", cafe24_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", cafe24_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", cafe24_ids)
    print(f"  삭제: {len(cafe24_ids)}개")
else:
    print("  없음")

# ─── 10. 광고 카피형 — 구어체 관형형/조사 패턴 ───
print("\n=== 10. 광고 카피형 광고주 삭제 ===")
ad_copy_re = re.compile(r'(?:들의|없는|있는|없어|있어|해주는|해드리는|알려주는)\s+|^광고없는\s+|^찐\s+')
c.execute("SELECT id, name, website FROM advertisers")
all_advs2 = c.fetchall()
copy_ids = []
for r in all_advs2:
    n = r[1] or ''
    if len(n) >= 7 and ' ' in n and ad_copy_re.search(n):
        copy_ids.append(r[0])
        print(f"  {r[0]}: '{r[1]}' → {r[2]}")
if copy_ids:
    ph = ",".join("?"*len(copy_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", copy_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", copy_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", copy_ids)
    print(f"  삭제: {len(copy_ids)}개")
else:
    print("  없음")

# ─── 11. 단독 플랫폼명 (네이버, 카카오 등) ───
print("\n=== 11. 단독 플랫폼명 광고주 삭제 ===")
PLATFORM_NAMES = {"네이버", "카카오", "유튜브", "인스타그램", "페이스북", "틱톡", "메타", "구글"}
plat_ids = [r[0] for r in all_advs2 if r[1] and r[1].strip() in PLATFORM_NAMES]
if plat_ids:
    ph = ",".join("?"*len(plat_ids))
    c.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", plat_ids)
    c.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", plat_ids)
    c.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", plat_ids)
    print(f"  삭제: {len(plat_ids)}개")
    for pid in plat_ids:
        matched = next((r[1] for r in all_advs2 if r[0] == pid), '')
        print(f"    {pid}: '{matched}'")
else:
    print("  없음")

conn.commit()

print()
print("=== 최종 현황 ===")
# all_advs 재조회 필요
c.execute("SELECT id, name FROM advertisers")
all_advs = c.fetchall()
for tbl in ["advertisers", "campaigns", "ad_details"]:
    c.execute(f"SELECT COUNT(*) FROM {tbl}")
    print(f"  {tbl}: {c.fetchone()[0]:,}")

# 중복 URL 잔존 확인
c.execute("""
SELECT website, COUNT(*) as cnt
FROM advertisers
WHERE website IS NOT NULL AND website <> ''
GROUP BY website HAVING cnt >= 3
ORDER BY cnt DESC LIMIT 10
""")
dups = c.fetchall()
if dups:
    print("\n  [아직 남은 URL 중복 3개 이상]")
    for r in dups:
        print(f"    {r[1]}개 → {r[0]}")
else:
    print("\n  URL 중복(3개 이상) 없음.")

conn.close()
