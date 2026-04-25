"""업종 3단계 계층 업데이트 스크립트.

현재 21개 업종에 industry_large(대), industry_medium(중) 컬럼을 추가하고
AdScope 기준 분류 체계로 매핑한다.

기존 name = 업종(소) 역할 유지.
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"

# id: (name, industry_large(대), industry_medium(중))
# 현재 name이 업종(소)이지만 현재 단계에서는 중=소로 동일하게 유지
# 추후 더 세분화된 소분류 필요 시 name을 별도로 세분화
INDUSTRY_MAP = {
    1:  ("기타",            "기타",          "기타"),
    2:  ("IT/통신",         "IT/미디어",     "IT/통신"),
    3:  ("자동차",          "자동차/교통",   "자동차"),
    4:  ("금융/보험",       "금융/서비스",   "금융/보험"),
    5:  ("식품/음료",       "식품/생활",     "식품/음료"),
    6:  ("뷰티/화장품",     "뷰티/패션",     "뷰티/화장품"),
    7:  ("패션/의류",       "뷰티/패션",     "패션/의류"),
    8:  ("유통/이커머스",   "유통/서비스",   "유통/이커머스"),
    9:  ("제약/헬스케어",   "건강/의료",     "제약/헬스케어"),
    10: ("가전/전자",       "IT/미디어",     "가전/전자"),
    11: ("건설/부동산",     "건설/부동산",   "건설/부동산"),
    12: ("게임",            "IT/미디어",     "게임"),
    13: ("엔터테인먼트",    "IT/미디어",     "엔터테인먼트"),
    14: ("여행/항공",       "유통/서비스",   "여행/항공"),
    15: ("교육",            "유통/서비스",   "교육"),
    16: ("스포츠/아웃도어", "뷰티/패션",     "스포츠/아웃도어"),
    17: ("가구/인테리어",   "건설/부동산",   "가구/인테리어"),
    18: ("주류",            "식품/생활",     "주류"),
    19: ("공공기관",        "공공/기관",     "공공기관"),
    20: ("반려동물",        "식품/생활",     "반려동물"),
    21: ("생활용품",        "식품/생활",     "생활용품"),
}

def main():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 컬럼 존재 확인 및 추가
    cur.execute("PRAGMA table_info(industries)")
    existing_cols = {row[1] for row in cur.fetchall()}

    for col in ("industry_medium", "industry_large"):
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE industries ADD COLUMN {col} TEXT")
            print(f"  컬럼 추가: {col}")
        else:
            print(f"  컬럼 이미 존재: {col}")

    # 현재 업종 목록 확인
    cur.execute("SELECT id, name FROM industries ORDER BY id")
    db_rows = cur.fetchall()
    db_map = {r[0]: r[1] for r in db_rows}

    # 매핑 적용
    updated = 0
    skipped = 0
    for industry_id, (name, large, medium) in INDUSTRY_MAP.items():
        if industry_id not in db_map:
            print(f"  [SKIP] ID {industry_id} ({name}) - DB에 없음")
            skipped += 1
            continue
        cur.execute(
            "UPDATE industries SET industry_large = ?, industry_medium = ? WHERE id = ?",
            (large, medium, industry_id)
        )
        updated += 1

    conn.commit()
    conn.close()

    print(f"\n업종 3단계 분류 완료: {updated}개 업데이트, {skipped}개 스킵")
    print("\n[업종 대분류 체계]")
    large_groups = {}
    for _, (name, large, medium) in INDUSTRY_MAP.items():
        large_groups.setdefault(large, []).append(name)
    for large, names in sorted(large_groups.items()):
        print(f"  {large:<15} → {', '.join(names)}")


if __name__ == "__main__":
    print(f"DB: {DB_PATH}")
    main()
