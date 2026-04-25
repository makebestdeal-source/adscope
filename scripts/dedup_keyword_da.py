"""키워드(naver_search) 및 DA(kakao_da) 채널 중복 소재 제거.

동일 광고주 + 동일 소재의 중복 행을 제거한다.
- creative_hash가 있으면: (channel, creative_hash) 기준
- 없으면: (channel, advertiser_name_raw, url) 기준
  - url도 없으면: (channel, advertiser_name_raw, ad_text[:100]) 기준

중복 중 가장 오래된 행(MIN id)을 유지하고,
seen_count는 합산, last_seen_at은 MAX로 업데이트.

사용법:
    python scripts/dedup_keyword_da.py           # dry-run (삭제 안 함, 현황만 출력)
    python scripts/dedup_keyword_da.py --run     # 실제 삭제 실행
    python scripts/dedup_keyword_da.py --channels naver_search kakao_da  # 채널 지정
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "adscope.db"

TARGET_CHANNELS = ["naver_search", "kakao_da"]


def build_dedup_key_expr() -> str:
    """SQLite CASE 식: creative_hash 우선, 없으면 advertiser+url, 없으면 advertiser+text."""
    return """
        CASE
            WHEN d.creative_hash IS NOT NULL AND d.creative_hash <> ''
                THEN 'hash:' || d.creative_hash
            WHEN d.advertiser_name_raw IS NOT NULL AND d.url IS NOT NULL AND d.url <> ''
                THEN 'adv_url:' || LOWER(TRIM(d.advertiser_name_raw)) || '|||' || LOWER(TRIM(d.url))
            WHEN d.advertiser_name_raw IS NOT NULL AND d.ad_text IS NOT NULL AND d.ad_text <> ''
                THEN 'adv_txt:' || LOWER(TRIM(d.advertiser_name_raw)) || '|||' || SUBSTR(TRIM(d.ad_text), 1, 100)
            ELSE NULL
        END
    """


def get_duplicate_summary(conn: sqlite3.Connection, channels: list[str]) -> list[tuple]:
    """채널별 중복 현황 반환: (channel, total, unique, dup_count)"""
    key_expr = build_dedup_key_expr()
    ch_placeholders = ",".join("?" * len(channels))
    c = conn.cursor()
    c.execute(f"""
        SELECT
            s.channel,
            COUNT(*) as total,
            COUNT(DISTINCT CASE WHEN {key_expr} IS NOT NULL THEN {key_expr} END) as uniq
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE s.channel IN ({ch_placeholders})
        GROUP BY s.channel
        ORDER BY total DESC
    """, channels)
    rows = []
    for ch, total, uniq in c.fetchall():
        rows.append((ch, total, uniq, total - uniq))
    return rows


def get_delete_ids(conn: sqlite3.Connection, channels: list[str]) -> tuple[list[int], dict]:
    """삭제 대상 id 목록과 keeper별 집계 정보를 반환."""
    key_expr = build_dedup_key_expr()
    ch_placeholders = ",".join("?" * len(channels))
    c = conn.cursor()

    # 임시 테이블: id, channel, dedup_key
    c.execute("DROP TABLE IF EXISTS _dedup_tmp")
    c.execute(f"""
        CREATE TEMP TABLE _dedup_tmp AS
        SELECT
            d.id,
            s.channel,
            ({key_expr}) as dedup_key
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE s.channel IN ({ch_placeholders})
          AND ({key_expr}) IS NOT NULL
    """, channels)

    # keeper: 각 (channel, dedup_key) 그룹에서 MIN(id) 유지
    c.execute("""
        CREATE TEMP TABLE _dedup_keepers AS
        SELECT
            MIN(id) as keep_id,
            channel,
            dedup_key,
            COUNT(*) as cnt
        FROM _dedup_tmp
        GROUP BY channel, dedup_key
        HAVING cnt > 1
    """)

    # 삭제 대상: keeper가 아닌 나머지
    c.execute("""
        SELECT t.id
        FROM _dedup_tmp t
        JOIN _dedup_keepers k ON k.channel = t.channel AND k.dedup_key = t.dedup_key
        WHERE t.id <> k.keep_id
    """)
    delete_ids = [r[0] for r in c.fetchall()]

    # keeper별 집계 정보 (seen_count 합산, last_seen_at MAX)
    c.execute("""
        SELECT
            k.keep_id,
            SUM(COALESCE(d.seen_count, 1)) as total_seen,
            MAX(s.captured_at) as last_seen,
            MIN(s.captured_at) as first_seen
        FROM _dedup_keepers k
        JOIN _dedup_tmp t ON t.channel = k.channel AND t.dedup_key = k.dedup_key
        JOIN ad_details d ON d.id = t.id
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        GROUP BY k.keep_id
    """)
    keeper_updates = {r[0]: (r[1], r[2], r[3]) for r in c.fetchall()}

    c.execute("DROP TABLE IF EXISTS _dedup_tmp")
    c.execute("DROP TABLE IF EXISTS _dedup_keepers")

    return delete_ids, keeper_updates


def apply_dedup(conn: sqlite3.Connection, channels: list[str]) -> int:
    """실제 중복 제거 실행. 삭제 건수 반환."""
    delete_ids, keeper_updates = get_delete_ids(conn, channels)
    if not delete_ids:
        return 0

    c = conn.cursor()

    # keeper 행 업데이트: seen_count 합산, last_seen_at MAX
    for keep_id, (total_seen, last_seen, first_seen) in keeper_updates.items():
        c.execute("""
            UPDATE ad_details
            SET seen_count = ?,
                last_seen_at = CASE WHEN last_seen_at IS NULL OR ? > last_seen_at THEN ? ELSE last_seen_at END,
                first_seen_at = CASE WHEN first_seen_at IS NULL OR ? < first_seen_at THEN ? ELSE first_seen_at END
            WHERE id = ?
        """, (total_seen, last_seen, last_seen, first_seen, first_seen, keep_id))

    # 배치 삭제
    batch_size = 500
    total_deleted = 0
    for i in range(0, len(delete_ids), batch_size):
        batch = delete_ids[i:i + batch_size]
        ph = ",".join("?" * len(batch))
        c.execute(f"DELETE FROM ad_details WHERE id IN ({ph})", batch)
        total_deleted += c.rowcount

    # 고아 스냅샷 정리
    c.execute("""
        DELETE FROM ad_snapshots
        WHERE channel IN ({ph_ch})
          AND id NOT IN (SELECT DISTINCT snapshot_id FROM ad_details)
    """.replace("{ph_ch}", ",".join("?" * len(channels))), channels)
    orphan_deleted = c.rowcount

    conn.commit()

    if orphan_deleted:
        print(f"  고아 스냅샷 정리: {orphan_deleted}건")

    return total_deleted


def main():
    parser = argparse.ArgumentParser(description="키워드/DA 채널 중복 소재 제거")
    parser.add_argument("--run", action="store_true", help="실제 삭제 실행 (기본: dry-run)")
    parser.add_argument("--channels", nargs="+", default=TARGET_CHANNELS,
                        help=f"대상 채널 (기본: {TARGET_CHANNELS})")
    parser.add_argument("--db", default=str(DB_PATH), help="DB 경로")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERROR] DB 파일 없음: {db_path}", file=sys.stderr)
        sys.exit(1)

    print(f"DB: {db_path}")
    print(f"대상 채널: {args.channels}")
    print(f"모드: {'실제 실행' if args.run else 'DRY-RUN (미리보기)'}\n")

    conn = sqlite3.connect(str(db_path))

    # 현황 출력
    summary = get_duplicate_summary(conn, args.channels)
    print("=== 현재 중복 현황 ===")
    if not summary:
        print("  데이터 없음")
        conn.close()
        return

    total_dup = 0
    for ch, total, uniq, dup in summary:
        dup_pct = (dup / total * 100) if total > 0 else 0
        print(f"  {ch}: 전체 {total}건, 고유 {uniq}건, 중복 {dup}건 ({dup_pct:.1f}%)")
        total_dup += dup

    if total_dup == 0:
        print("\n중복 없음. 종료.")
        conn.close()
        return

    print(f"\n  → 삭제 예정: 총 {total_dup}건")

    if not args.run:
        print("\n[DRY-RUN] 실제 삭제하려면 --run 옵션을 추가하세요.")
        print(f"  예: python scripts/dedup_keyword_da.py --run")
        conn.close()
        return

    # 백업 확인
    print("\n실행 전 백업을 권장합니다.")
    confirm = input("계속 진행하시겠습니까? (yes/N): ").strip().lower()
    if confirm != "yes":
        print("취소됨.")
        conn.close()
        return

    print("\n--- 중복 제거 실행 중 ---")
    deleted = apply_dedup(conn, args.channels)

    # VACUUM
    print("--- VACUUM ---")
    conn.execute("VACUUM")

    # 결과 출력
    print("\n=== 완료 ===")
    summary_after = get_duplicate_summary(conn, args.channels)
    for ch, total, uniq, dup in summary_after:
        print(f"  {ch}: {total}건 (중복 {dup}건 남음)")
    print(f"\n  총 삭제: {deleted}건")

    conn.close()


if __name__ == "__main__":
    main()
