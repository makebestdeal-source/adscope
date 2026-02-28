# -*- coding: utf-8 -*-
"""Fix mismatched advertiser names: ad copy as name, naver prefix pollution, etc."""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "adscope.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    merged = 0
    renamed = 0

    # =============================================
    # 1. Ad copy used as advertiser name + same website -> merge
    # =============================================
    merges = [
        # (from_id, to_id, description)
        (4743, 3393, '"엄마, 나 결혼하기 무서워." -> 월드비전'),
        (3391, 3350, '"3·1절 그 후, 아직도 침묵 속에" -> 대한적십자사'),
        (4171, 2506, '"3/12(목) 양주 김미경" -> 쎈엄마'),
    ]
    for from_id, to_id, desc in merges:
        c.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (from_id,))
        cnt = c.fetchone()[0]
        c.execute("SELECT name FROM advertisers WHERE id=?", (from_id,))
        row = c.fetchone()
        if not row:
            continue
        print(f"[병합] {desc} ({cnt}건)")
        c.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (to_id, from_id))
        c.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (to_id, from_id))
        c.execute("DELETE FROM advertisers WHERE id=?", (from_id,))
        merged += 1

    # =============================================
    # 2. Naver login/pay prefix pollution
    # =============================================
    PREFIXES = [
        "네이버 로그인 네이버 아이디로 로그인이 가능합니다. 서비스 자세히 보기",
        "네이버페이 네이버 아이디 하나로 간편구매 Naver Pay 서비스 보기",
        "네이버페이 네이버 아이디 하나로 간편구매 Naver Pay",
        "네이버 톡톡 네이버",
        "네이버로그인",
        "네이버페이",
    ]

    c.execute("""
        SELECT id, name, website FROM advertisers
        WHERE name LIKE '%네이버로그인%' OR name LIKE '%네이버페이%'
           OR name LIKE '%네이버 로그인%' OR name LIKE '%Naver Pay%'
           OR name LIKE '%네이버 톡톡%'
        ORDER BY id
    """)
    naver_rows = c.fetchall()

    for adv_id, name, website in naver_rows:
        clean = name
        for prefix in PREFIXES:
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()
                break

        # Strip commas and special separators
        clean = clean.strip(",. ")

        if not clean:
            if website:
                domain = (website.replace("https://", "").replace("http://", "")
                          .replace("www.", "").replace("m.", "").split("/")[0].split(".")[0])
                clean = domain
            else:
                continue

        # Check for existing advertiser with same name
        c.execute("SELECT id FROM advertisers WHERE name=? AND id!=?", (clean, adv_id))
        existing = c.fetchone()

        if existing:
            c.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (adv_id,))
            cnt = c.fetchone()[0]
            print(f'[병합] "{name}" (id={adv_id}, {cnt}건) -> "{clean}" (id={existing[0]})')
            c.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (existing[0], adv_id))
            c.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (existing[0], adv_id))
            c.execute("DELETE FROM advertisers WHERE id=?", (adv_id,))
            merged += 1
        else:
            print(f'[이름수정] "{name}" -> "{clean}" (id={adv_id})')
            c.execute("UPDATE advertisers SET name=? WHERE id=?", (clean, adv_id))
            renamed += 1

    # =============================================
    # 3. Other ad-copy-as-name cases
    # =============================================
    simple_renames = [
        (5170, "일미리성형외과"),
        (2959, "인스파이어리조트"),
        (5237, "피시팡"),
        (2604, "담가화로구이"),
        (2557, "삼쩜삼캠퍼스"),
        (2874, "메가스터디러셀"),
        (3079, "정철어학원"),
        (4402, "고려여행사"),
        (4337, "페이쏨땀"),
    ]

    for adv_id, clean_name in simple_renames:
        c.execute("SELECT id, name FROM advertisers WHERE id=?", (adv_id,))
        row = c.fetchone()
        if not row:
            continue
        old_name = row[1]
        if old_name == clean_name:
            continue

        # Check for existing advertiser to merge into
        c.execute("SELECT id FROM advertisers WHERE name=? AND id!=?", (clean_name, adv_id))
        existing = c.fetchone()

        if existing:
            c.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (adv_id,))
            cnt = c.fetchone()[0]
            print(f'[병합] "{old_name}" ({cnt}건) -> "{clean_name}" (id={existing[0]})')
            c.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (existing[0], adv_id))
            c.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (existing[0], adv_id))
            c.execute("DELETE FROM advertisers WHERE id=?", (adv_id,))
            merged += 1
        else:
            print(f'[이름수정] "{old_name}" -> "{clean_name}" (id={adv_id})')
            c.execute("UPDATE advertisers SET name=? WHERE id=?", (clean_name, adv_id))
            renamed += 1

    # =============================================
    # 4. Broader check: any remaining long names that look like ad copy
    # =============================================
    c.execute("""
        SELECT id, name, website FROM advertisers
        WHERE LENGTH(name) >= 20
          AND (name LIKE '%더 알아보기%' OR name LIKE '%서비스 보기%'
               OR name LIKE '%지금 바로%' OR name LIKE '%무료%상담%'
               OR name LIKE '%할인%판매%' OR name LIKE '%월%억%매출%')
        ORDER BY id
    """)
    remaining_long = c.fetchall()
    if remaining_long:
        print(f"\n=== 추가 의심 광고주 ({len(remaining_long)}건) ===")
        for r in remaining_long:
            print(f"  id={r[0]} name={r[1]} web={r[2]}")

    conn.commit()
    print(f"\n=== 완료: 병합 {merged}건, 이름수정 {renamed}건 ===")

    c.execute("SELECT COUNT(*) FROM advertisers")
    print(f"광고주 총: {c.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
