"""업종(industry) → 제품카테고리(product_category) 전파 스크립트.

Step 1: product_categories.industry_id 설정 (industry 이름 기반 매핑)
Step 2: ad_details.product_category_id를 advertiser.industry_id 기반으로 일괄 설정

실행 순서:
    1. python scripts/quick_classify_advertisers.py   # 전체 광고주 키워드 분류
    2. python scripts/classify_industries.py           # 기타 광고주 AI 분류
    3. python scripts/propagate_industry_to_category.py  # 업종→카테고리 전파

Usage:
    python scripts/propagate_industry_to_category.py
    python scripts/propagate_industry_to_category.py --db server_db.db
    python scripts/propagate_industry_to_category.py --dry-run
    python scripts/propagate_industry_to_category.py --overwrite  # 기존값도 덮어씀
"""

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 업종명 → 제품카테고리 대분류명 매핑 (이름 기반 — ID 무관)
# key: industries.name / value: product_categories.name (parent_id IS NULL)
INDUSTRY_TO_PRODUCT_CATEGORY: dict[str, str] = {
    "IT/통신": "소프트웨어/SaaS",
    "가구/인테리어": "생활서비스",
    "가전/전자": "가전/전자",
    "건설/부동산": "부동산",
    "게임": "게임",
    "공공기관": "생활서비스",
    "교육": "교육",
    "금융/보험": "금융서비스",
    "럭셔리/명품": "패션",
    "반려동물": "생활서비스",
    "뷰티/화장품": "뷰티/화장품",
    "생활용품": "생활서비스",
    "스포츠/아웃도어": "패션",
    "식품/음료": "식품/음료",
    "엔터테인먼트": "엔터테인먼트",
    "여행/항공": "여행/레저",
    "유통/이커머스": "유통/쇼핑",
    "자동차": "자동차",
    "제약/헬스케어": "건강/의료",
    "주류": "식품/음료",
    "패션/의류": "패션",
    "플랫폼/O2O": "앱서비스",
    "핀테크/금융서비스": "금융서비스",
    # "기타" → 매핑 없음 (skip)
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "adscope.db"), help="DB 경로")
    parser.add_argument("--dry-run", action="store_true", help="DB 변경 없이 통계만 출력")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="이미 product_category_id가 설정된 광고도 덮어씀",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.text_factory = lambda b: b.decode("utf-8", errors="replace")
    cur = conn.cursor()

    # ── 1. industry id/name 로드 ──────────────────────────────────────────────
    cur.execute("SELECT id, name FROM industries")
    industry_id_to_name: dict[int, str] = {row[0]: row[1] for row in cur.fetchall()}
    industry_name_to_id: dict[str, int] = {v: k for k, v in industry_id_to_name.items()}

    # ── 2. product_category (대분류) id/name 로드 ─────────────────────────────
    cur.execute("SELECT id, name FROM product_categories WHERE parent_id IS NULL")
    cat_id_to_name: dict[int, str] = {row[0]: row[1] for row in cur.fetchall()}
    cat_name_to_id: dict[str, int] = {v: k for k, v in cat_id_to_name.items()}

    # ── 3. industry_id → product_category_id 매핑 빌드 ───────────────────────
    industry_id_to_cat_id: dict[int, int] = {}
    missing_cats: list[str] = []

    for ind_name, cat_name in INDUSTRY_TO_PRODUCT_CATEGORY.items():
        ind_id = industry_name_to_id.get(ind_name)
        cat_id = cat_name_to_id.get(cat_name)
        if ind_id is None:
            continue  # 이 DB에 없는 업종 → skip
        if cat_id is None:
            missing_cats.append(f"{ind_name} → {cat_name}(없음)")
            continue
        industry_id_to_cat_id[ind_id] = cat_id

    print(f"업종→카테고리 매핑 완성: {len(industry_id_to_cat_id)}개")
    for ind_id, cat_id in sorted(industry_id_to_cat_id.items()):
        print(
            f"  [{ind_id}]{industry_id_to_name[ind_id]}"
            f" → [{cat_id}]{cat_id_to_name[cat_id]}"
        )
    if missing_cats:
        print(f"\n[WARN] 카테고리 없음 (DB에 없는 product_category name):")
        for m in missing_cats:
            print(f"  {m}")

    # ── 4. product_categories.industry_id 업데이트 ────────────────────────────
    # 각 대분류 카테고리에 해당 industry_id를 역매핑으로 설정
    cat_to_ind: dict[int, int] = {v: k for k, v in industry_id_to_cat_id.items()}
    cat_ind_updated = 0
    for cat_id, ind_id in cat_to_ind.items():
        cur.execute(
            "SELECT industry_id FROM product_categories WHERE id = ?", (cat_id,)
        )
        row = cur.fetchone()
        if row and (row[0] is None or args.overwrite):
            if not args.dry_run:
                cur.execute(
                    "UPDATE product_categories SET industry_id = ? WHERE id = ?",
                    (ind_id, cat_id),
                )
            cat_ind_updated += 1

    print(f"\nproduct_categories.industry_id 업데이트: {cat_ind_updated}개")

    # ── 5. ad_details.product_category_id 전파 ───────────────────────────────
    print("\n[광고주별 ad_details 전파]")
    total_ads_updated = 0
    total_advertisers = 0
    skipped_no_cat = 0

    cur.execute(
        """
        SELECT a.id, a.name, a.industry_id, COUNT(d.id) AS ad_cnt
        FROM advertisers a
        LEFT JOIN ad_details d ON d.advertiser_id = a.id
        WHERE a.industry_id IS NOT NULL AND a.industry_id != 1
        GROUP BY a.id
        ORDER BY ad_cnt DESC
        """
    )
    advertisers = cur.fetchall()

    for adv_id, adv_name, ind_id, ad_cnt in advertisers:
        cat_id = industry_id_to_cat_id.get(ind_id)
        if cat_id is None:
            skipped_no_cat += 1
            continue

        if args.overwrite:
            cur.execute(
                "SELECT COUNT(*) FROM ad_details WHERE advertiser_id = ?", (adv_id,)
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM ad_details WHERE advertiser_id = ? AND product_category_id IS NULL",
                (adv_id,),
            )
        to_update = cur.fetchone()[0]
        if to_update == 0:
            continue

        if not args.dry_run:
            if args.overwrite:
                cur.execute(
                    "UPDATE ad_details SET product_category_id = ? WHERE advertiser_id = ?",
                    (cat_id, adv_id),
                )
            else:
                cur.execute(
                    "UPDATE ad_details SET product_category_id = ? WHERE advertiser_id = ? AND product_category_id IS NULL",
                    (cat_id, adv_id),
                )

        total_ads_updated += to_update
        total_advertisers += 1

    if not args.dry_run:
        conn.commit()
    conn.close()

    mode = "[DRY-RUN] " if args.dry_run else ""
    print(
        f"\n{mode}완료: {total_advertisers}개 광고주 / {total_ads_updated}개 광고 "
        f"product_category_id 설정"
    )
    if skipped_no_cat:
        print(f"  (카테고리 매핑 없음으로 건너뜀: {skipped_no_cat}개 광고주)")


if __name__ == "__main__":
    main()
