# -*- coding: utf-8 -*-
"""Fix remaining advertiser name issues: website duplicates, domain-as-name, ad-copy-as-name."""

import sqlite3
import sys
import re

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = "adscope.db"

# Manual name corrections for domain-only names
DOMAIN_TO_NAME = {
    "andar": ("안다르", "andar.co.kr"),
    "skullpig": ("스컬피그", "skullpig.com"),
    "ohou": ("오늘의집", "ohou.se"),
    "isoohyun": ("이수현 한의원", "isoohyun.co.kr"),
}


def is_ad_copy(name: str) -> bool:
    """Check if name looks like ad copy rather than a brand name."""
    # Patterns that indicate ad copy
    patterns = [
        r"^\d+/\d+",  # Date format like 3/12
        r"더 알아보기",
        r"서비스 보기",
        r"지금 바로",
        r"선착순",
        r"무료토크",
        r"월\d+억",
        r"\d+,\d+원",
        r"할인판매",
        r"못하시는 분",
        r"못하는 ",
        r"진짜 하실",
        r"싸다고\?",
        r"하루 두 알",
        r"초소형 정제",
        r"선명한데",
        r"까딱하기",
        r"빠르고 간편한",
        r"합격자격증",
    ]
    for p in patterns:
        if re.search(p, name):
            return True
    return len(name) >= 25 and any(kw in name for kw in ["!", "?", "...", "~"])


def pick_best_name(names_ids: list[tuple[int, str]]) -> tuple[int, str]:
    """Among multiple advertiser records, pick the best (shortest clean) name."""
    # Filter out ad-copy names
    clean = [(aid, n) for aid, n in names_ids if not is_ad_copy(n)]
    if not clean:
        clean = names_ids  # fallback

    # Pick shortest name (usually the cleanest)
    clean.sort(key=lambda x: len(x[1]))
    return clean[0]


def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    merged = 0
    renamed = 0

    # =============================================
    # 1. Fix domain-only advertiser names
    # =============================================
    for domain_name, (real_name, website) in DOMAIN_TO_NAME.items():
        c.execute("SELECT id FROM advertisers WHERE name=?", (domain_name,))
        row = c.fetchone()
        if not row:
            continue
        adv_id = row[0]
        # Check if real_name already exists
        c.execute("SELECT id FROM advertisers WHERE name=? AND id!=?", (real_name, adv_id))
        existing = c.fetchone()
        if existing:
            c.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (adv_id,))
            cnt = c.fetchone()[0]
            print(f'[병합] "{domain_name}" ({cnt}건) -> "{real_name}" (id={existing[0]})')
            c.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (existing[0], adv_id))
            c.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (existing[0], adv_id))
            c.execute("DELETE FROM advertisers WHERE id=?", (adv_id,))
            merged += 1
        else:
            print(f'[이름수정] "{domain_name}" -> "{real_name}" (id={adv_id})')
            c.execute("UPDATE advertisers SET name=? WHERE id=?", (real_name, adv_id))
            renamed += 1

    # =============================================
    # 2. Merge website duplicates (same domain, multiple names)
    # =============================================
    # Skip facebook.com, youtube.com (multiple legitimate advertisers share these)
    SKIP_WEBSITES = {"facebook.com", "youtube.com", "instagram.com", ""}

    c.execute("""
        SELECT website, COUNT(*) as cnt FROM advertisers
        WHERE website IS NOT NULL AND website != ''
        GROUP BY website HAVING COUNT(*) > 1
        ORDER BY cnt DESC
    """)
    dup_websites = c.fetchall()

    for website, cnt in dup_websites:
        if website in SKIP_WEBSITES:
            continue

        c.execute("SELECT id, name FROM advertisers WHERE website=? ORDER BY id", (website,))
        entries = c.fetchall()

        # Pick best name
        best_id, best_name = pick_best_name(entries)

        for adv_id, name in entries:
            if adv_id == best_id:
                continue
            c.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (adv_id,))
            ad_cnt = c.fetchone()[0]
            print(f'[website병합] "{name}" ({ad_cnt}건) -> "{best_name}" (id={best_id}) [{website}]')
            c.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (best_id, adv_id))
            c.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (best_id, adv_id))
            c.execute("DELETE FROM advertisers WHERE id=?", (adv_id,))
            merged += 1

    # =============================================
    # 3. samsung.com special case - keep as separate brands
    # =============================================
    # samsung.com has 삼성전자, 삼성닷컴, 삼성, 삼성전자판매 - merge into 삼성전자
    c.execute("SELECT id FROM advertisers WHERE name='삼성전자'")
    samsung_main = c.fetchone()
    if samsung_main:
        samsung_id = samsung_main[0]
        for merge_name in ["삼성닷컴", "삼성전자판매"]:
            c.execute("SELECT id FROM advertisers WHERE name=?", (merge_name,))
            row = c.fetchone()
            if row and row[0] != samsung_id:
                c.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (row[0],))
                ad_cnt = c.fetchone()[0]
                print(f'[삼성병합] "{merge_name}" ({ad_cnt}건) -> "삼성전자" (id={samsung_id})')
                c.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (samsung_id, row[0]))
                c.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (samsung_id, row[0]))
                c.execute("DELETE FROM advertisers WHERE id=?", (row[0],))
                merged += 1

    conn.commit()
    print(f"\n=== 완료: 병합 {merged}건, 이름수정 {renamed}건 ===")

    c.execute("SELECT COUNT(*) FROM advertisers")
    print(f"광고주 총: {c.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
