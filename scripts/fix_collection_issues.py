"""수집(크롤링) 문제 일괄 DB 수정.

수집 파이프라인에서 발생한 비정상 데이터를 정리:
1. 가비지 데이터 삭제 (플레이스홀더, 슬롯 마커, 안내문구)
2. naver_shopping 안내문구 → 실광고 아님, 삭제
3. kakao_da 광고문구가 advertiser_name에 들어간 건 → 정리
4. naver_da 이미지만 있고 광고주 식별 불가 → verification 마킹
5. advertiser_id 미매칭 건 자동 매칭 시도
6. 캠페인 재연결 (advertiser_id 복구 후)
"""

import sqlite3
import json
import re
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "adscope.db"


def normalize_for_match(name: str) -> str:
    """광고주명 정규화 (매칭용)."""
    if not name:
        return ""
    s = name.strip()
    # (주), 주식회사, 공백 제거
    s = re.sub(r"\(주\)|주식회사|\s+", "", s)
    # blog.naver, m.place.naver 등 URL 부분 제거
    s = re.sub(r"\s*(blog\.naver|m\.place\.naver|map\.naver|m\.smartstore\.naver).*$", "", s)
    # 특수문자 제거
    s = re.sub(r"[^\w가-힣a-zA-Z0-9]", "", s)
    return s.lower()


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    print("=" * 70)
    print("수집 문제 일괄 DB 수정")
    print("=" * 70)

    # ── 1. 가비지 데이터 삭제 ──
    print("\n[1/6] 가비지 데이터 삭제 (플레이스홀더, 슬롯 마커)")

    # URL 없는 가비지 (kakao placeholder, youtube slot marker, 비디오 타이머)
    cur.execute("""
        DELETE FROM ad_details
        WHERE (url IS NULL OR url = '')
          AND id IN (
            SELECT d.id FROM ad_details d
            JOIN ad_snapshots s ON d.snapshot_id = s.id
            WHERE s.channel IN ('kakao_da', 'youtube_surf')
               OR (s.channel = 'facebook' AND d.ad_text LIKE '0:0%')
          )
    """)
    n1 = cur.rowcount
    print(f"  URL 없는 가비지 삭제: {n1}건")

    # ── 2. naver_shopping 안내문구 삭제 ──
    print("\n[2/6] naver_shopping 안내문구 데이터 삭제")
    # "~관련 정보 및 ...스마트검색광고(파워링크)" 패턴 = 실제 광고 아닌 안내문구
    cur.execute("""
        DELETE FROM ad_details
        WHERE id IN (
            SELECT d.id FROM ad_details d
            JOIN ad_snapshots s ON d.snapshot_id = s.id
            WHERE s.channel = 'naver_shopping'
              AND (d.advertiser_name_raw IS NULL OR d.advertiser_name_raw = '')
              AND d.ad_text LIKE '%스마트검색광고%'
        )
    """)
    n2a = cur.rowcount

    # naver_shopping에서 여전히 광고주명 없는 나머지도 확인
    cur.execute("""
        SELECT COUNT(*) FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE s.channel = 'naver_shopping'
          AND (d.advertiser_name_raw IS NULL OR d.advertiser_name_raw = '')
    """)
    remaining_shop = cur.fetchone()[0]
    print(f"  안내문구 삭제: {n2a}건, 잔여 미식별: {remaining_shop}건")

    # ── 3. kakao_da 광고문구 → advertiser_name 정리 ──
    print("\n[3/6] kakao_da 광고문구 광고주명 정리")
    # advertiser_name_raw가 30자 이상 → 광고 카피가 잘못 들어간 것
    cur.execute("""
        SELECT d.id, d.advertiser_name_raw, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE s.channel = 'kakao_da'
          AND d.advertiser_name_raw IS NOT NULL
          AND LENGTH(d.advertiser_name_raw) > 30
    """)
    kakao_rows = cur.fetchall()
    kakao_fixed = 0
    for did, raw_name, extra_json in kakao_rows:
        try:
            extra = json.loads(extra_json) if extra_json else {}
        except (json.JSONDecodeError, TypeError):
            extra = {}
        extra["original_advertiser_name"] = raw_name
        extra["collection_issue"] = "ad_copy_as_advertiser_name"
        new_extra = json.dumps(extra, ensure_ascii=False)
        cur.execute(
            """UPDATE ad_details
               SET advertiser_name_raw = NULL,
                   verification_status = 'unverified',
                   verification_source = 'collection_issue:ad_copy_name',
                   extra_data = ?
               WHERE id = ?""",
            (new_extra, did),
        )
        kakao_fixed += 1

    # kakao_da에서 URL 도메인이 m.smartstore.naver.com, mkt.shopping.naver.com 인 건
    # → advertiser_name에 도메인이 들어간 것. 정리
    cur.execute("""
        SELECT d.id, d.advertiser_name_raw
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE s.channel = 'kakao_da'
          AND d.advertiser_name_raw IS NOT NULL
          AND (d.advertiser_name_raw LIKE '%.naver.com%'
               OR d.advertiser_name_raw LIKE '%.co.kr%'
               OR d.advertiser_name_raw LIKE '%http%')
    """)
    domain_rows = cur.fetchall()
    for did, raw_name in domain_rows:
        cur.execute(
            """UPDATE ad_details
               SET advertiser_name_raw = NULL,
                   verification_status = 'unverified',
                   verification_source = 'collection_issue:domain_as_name'
               WHERE id = ?""",
            (did,),
        )
        kakao_fixed += 1
    print(f"  kakao_da 광고문구/도메인 정리: {kakao_fixed}건")

    # ── 4. naver_da 미식별 데이터 마킹 ──
    print("\n[4/6] naver_da/kakao_da 미식별 데이터 마킹")
    # advertiser_name_raw NULL + 이미지만 있는 건 → unverified 마킹
    cur.execute("""
        UPDATE ad_details
        SET verification_status = 'unverified',
            verification_source = 'collection_issue:no_advertiser_data'
        WHERE id IN (
            SELECT d.id FROM ad_details d
            JOIN ad_snapshots s ON d.snapshot_id = s.id
            WHERE s.channel IN ('naver_da', 'kakao_da')
              AND (d.advertiser_name_raw IS NULL OR d.advertiser_name_raw = '')
              AND d.advertiser_id IS NULL
              AND d.verification_status != 'rejected'
        )
    """)
    n4 = cur.rowcount
    print(f"  미식별 마킹: {n4}건")

    # ── 5. advertiser_id 자동 매칭 ──
    print("\n[5/6] advertiser_id 자동 매칭 (이름 기반)")

    # 기존 광고주 이름 맵 구축
    cur.execute("SELECT id, name FROM advertisers")
    adv_map: dict[str, int] = {}
    for aid, aname in cur.fetchall():
        key = normalize_for_match(aname)
        if key and key not in adv_map:
            adv_map[key] = aid

    # advertiser_name_raw가 있지만 advertiser_id 없는 건 매칭 시도
    cur.execute("""
        SELECT d.id, d.advertiser_name_raw
        FROM ad_details d
        WHERE d.advertiser_id IS NULL
          AND d.advertiser_name_raw IS NOT NULL
          AND d.advertiser_name_raw != ''
    """)
    unmatched = cur.fetchall()
    matched_count = 0
    for did, raw_name in unmatched:
        key = normalize_for_match(raw_name)
        if key in adv_map:
            cur.execute(
                "UPDATE ad_details SET advertiser_id = ? WHERE id = ?",
                (adv_map[key], did),
            )
            matched_count += 1
    print(f"  매칭 시도: {len(unmatched)}건 → 성공: {matched_count}건")

    # ── 6. ad_snapshots ad_count 갱신 ──
    print("\n[6/6] ad_snapshots ad_count 갱신 (삭제 반영)")
    cur.execute("""
        UPDATE ad_snapshots
        SET ad_count = (
            SELECT COUNT(*) FROM ad_details WHERE snapshot_id = ad_snapshots.id
        )
        WHERE ad_count != (
            SELECT COUNT(*) FROM ad_details WHERE snapshot_id = ad_snapshots.id
        )
    """)
    n6 = cur.rowcount
    print(f"  ad_count 갱신: {n6}건")

    conn.commit()

    # ── 결과 요약 ──
    print("\n" + "=" * 70)
    print("수정 완료 요약")
    print("=" * 70)

    cur.execute("SELECT COUNT(*) FROM ad_details")
    print(f"  ad_details: {cur.fetchone()[0]:,d}")

    cur.execute("""
        SELECT s.channel, COUNT(*) as total,
               SUM(CASE WHEN d.advertiser_id IS NULL THEN 1 ELSE 0 END) as no_adv
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        GROUP BY s.channel ORDER BY no_adv DESC
    """)
    print(f"\n  {'채널':25s} {'총':>6s} {'미매칭':>7s}")
    for r in cur.fetchall():
        print(f"  {str(r[0]):25s} {r[1]:6d} {r[2]:7d}")

    cur.execute("SELECT COUNT(*) FROM ad_details WHERE url IS NULL OR url = ''")
    print(f"\n  URL 누락 잔여: {cur.fetchone()[0]}")

    cur.execute("SELECT verification_status, COUNT(*) FROM ad_details GROUP BY verification_status ORDER BY COUNT(*) DESC")
    print(f"\n  verification_status 분포:")
    for r in cur.fetchall():
        print(f"    {str(r[0]):30s}: {r[1]:,d}")

    conn.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
