"""DB 데이터 품질 수정 스크립트.

진단 결과 기반 8가지 수정:
1. 고아 레코드 정리 (삭제된 광고주/캠페인 참조)
2. spend_estimates 중복 제거
3. 중복 광고주 병합
4. 구 보정계수(7.4/6.3) spend_estimates 재계산
5. 캠페인 total_est_spend 실제 합계로 갱신
6. serpapi_ads advertiser_name 정규화
7. naver_shopping advertiser_name 백필
8. position_zone 백필 (position 기반)
"""

import sqlite3
import json
import re
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "adscope.db"

# 현재 코드 기준 보정계수
CURRENT_CALIBRATION = {
    "naver_search": 3.7,
    "naver_da": 3.2,
}
CURRENT_CPC = {
    "naver_search": 500,
    "naver_da": 800,
}
CURRENT_INV_WEIGHT = {
    "naver_search": 1.0,
    "naver_da": 1.3,
}
HITS_TO_CLICKS = {1: 40, 2: 100, 3: 200, 4: 400}
HITS_5PLUS = 750


def get_clicks(ad_hits: int) -> int:
    if ad_hits <= 0:
        return 0
    if ad_hits >= 5:
        return HITS_5PLUS
    return HITS_TO_CLICKS.get(ad_hits, 40)


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    print("=" * 70)
    print("AdScope DB 데이터 품질 수정")
    print("=" * 70)

    # ── 1. 고아 레코드 정리 ──
    print("\n[1/8] 고아 레코드 정리")

    # ad_details -> 삭제된 advertiser_id
    cur.execute("""
        UPDATE ad_details SET advertiser_id = NULL
        WHERE advertiser_id IS NOT NULL
          AND advertiser_id NOT IN (SELECT id FROM advertisers)
    """)
    n1a = cur.rowcount
    print(f"  ad_details advertiser_id 해제: {n1a}건")

    # spend_estimates -> 삭제된 campaign_id
    cur.execute("""
        DELETE FROM spend_estimates
        WHERE campaign_id NOT IN (SELECT id FROM campaigns)
    """)
    n1b = cur.rowcount
    print(f"  spend_estimates 고아 삭제: {n1b}건")

    # ── 2. spend_estimates 중복 제거 ──
    print("\n[2/8] spend_estimates 중복 제거")
    cur.execute("""
        DELETE FROM spend_estimates
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM spend_estimates
            GROUP BY campaign_id, date, channel
        )
    """)
    n2 = cur.rowcount
    print(f"  중복 삭제: {n2}건")

    # ── 3. 중복 광고주 병합 ──
    print("\n[3/8] 중복 광고주 병합")

    def normalize_name(name: str) -> str:
        s = name.replace(" ", "").replace("(주)", "").replace("주식회사", "")
        return s.strip()

    cur.execute("SELECT id, name FROM advertisers ORDER BY id")
    all_advs = cur.fetchall()
    norm_map: dict[str, list[tuple[int, str]]] = {}
    for aid, aname in all_advs:
        key = normalize_name(aname)
        norm_map.setdefault(key, []).append((aid, aname))

    merged_count = 0
    for key, group in norm_map.items():
        if len(group) <= 1:
            continue
        # 가장 오래된(가장 작은 ID) 광고주를 마스터로
        master_id = group[0][0]
        for dup_id, dup_name in group[1:]:
            # ad_details 이전
            cur.execute(
                "UPDATE ad_details SET advertiser_id = ? WHERE advertiser_id = ?",
                (master_id, dup_id),
            )
            moved_ads = cur.rowcount
            # campaigns 이전
            cur.execute(
                "UPDATE campaigns SET advertiser_id = ? WHERE advertiser_id = ?",
                (master_id, dup_id),
            )
            moved_camps = cur.rowcount
            # 중복 광고주 삭제
            cur.execute("DELETE FROM advertisers WHERE id = ?", (dup_id,))
            print(f"  #{dup_id} \"{dup_name}\" -> #{master_id} \"{group[0][1]}\" "
                  f"(ads={moved_ads}, camps={moved_camps})")
            merged_count += 1
    print(f"  총 병합: {merged_count}쌍")

    # ── 4. 구 보정계수 spend_estimates 재계산 ──
    print("\n[4/8] 구 보정계수(7.4/6.3) spend_estimates 재계산")
    cur.execute("""
        SELECT id, channel, est_daily_spend, factors
        FROM spend_estimates
        WHERE factors IS NOT NULL
          AND (json_extract(factors, '$.market_calibration') = 7.4
               OR json_extract(factors, '$.market_calibration') = 6.3)
    """)
    old_calib_rows = cur.fetchall()
    recalc_count = 0
    for se_id, ch, old_spend, factors_json in old_calib_rows:
        try:
            factors = json.loads(factors_json) if isinstance(factors_json, str) else factors_json
        except (json.JSONDecodeError, TypeError):
            continue

        old_calib = factors.get("market_calibration", 1.0)
        new_calib = CURRENT_CALIBRATION.get(ch, old_calib)
        if old_calib == new_calib:
            continue

        # 비율 보정: new_spend = old_spend * (new_calib / old_calib)
        ratio = new_calib / old_calib
        new_spend = round(old_spend * ratio, 2)

        factors["market_calibration"] = new_calib
        factors["recalculated_from"] = old_calib
        new_factors_json = json.dumps(factors, ensure_ascii=False)

        cur.execute(
            "UPDATE spend_estimates SET est_daily_spend = ?, factors = ? WHERE id = ?",
            (new_spend, new_factors_json, se_id),
        )
        recalc_count += 1
    print(f"  재계산: {recalc_count}건 (7.4->3.7, 6.3->3.2)")

    # ── 5. 캠페인 total_est_spend 실제 합계 기반 갱신 ──
    print("\n[5/8] 캠페인 total_est_spend 갱신 (실제 spend_estimates 합계 기반)")
    # 30일 투영 방식 유지: avg_daily * 30
    cur.execute("""
        SELECT c.id,
               c.total_est_spend,
               COALESCE(SUM(se.est_daily_spend), 0) as actual_sum,
               COUNT(DISTINCT DATE(se.date)) as observed_days
        FROM campaigns c
        LEFT JOIN spend_estimates se ON se.campaign_id = c.id
        GROUP BY c.id
    """)
    camp_rows = cur.fetchall()
    fixed_camps = 0
    for cid, stored, actual_sum, obs_days in camp_rows:
        obs_days = max(1, obs_days)
        avg_daily = actual_sum / obs_days
        correct_total = round(avg_daily * 30, 2)

        # 10% 이상 차이나면 갱신
        if stored is None or stored == 0:
            if actual_sum == 0:
                continue
        elif abs(stored - correct_total) / max(stored, 1) < 0.10:
            continue

        cur.execute(
            "UPDATE campaigns SET total_est_spend = ? WHERE id = ?",
            (correct_total, cid),
        )
        fixed_camps += 1
    print(f"  갱신: {fixed_camps}건")

    # ── 6. serpapi_ads advertiser_name 정규화 ──
    print("\n[6/8] serpapi_ads advertiser_name 정규화 (stealth_ 접두사 정리)")
    # stealth_gdn_chosun-sports -> network+source 구조화, advertiser_name 유지(NOT NULL)
    cur.execute("""
        SELECT id, advertiser_name, extra_data
        FROM serpapi_ads
        WHERE advertiser_name LIKE 'stealth_%'
    """)
    stealth_rows = cur.fetchall()
    stealth_fixed = 0
    for sid, aname, extra_json in stealth_rows:
        try:
            extra = json.loads(extra_json) if extra_json else {}
        except (json.JSONDecodeError, TypeError):
            extra = {}
        # 원본 source를 extra_data에 보존
        extra["stealth_source"] = aname
        # stealth_gdn_chosun-sports -> network=gdn, source_detail=chosun-sports
        parts = aname.replace("stealth_", "").split("_", 1)
        if len(parts) >= 2:
            extra["network"] = parts[0]
            extra["source_detail"] = parts[1]

        # advertiser_name을 "[미확인]소스명" 형태로 변경 (NOT NULL 제약)
        clean_name = f"[미확인]{parts[1] if len(parts) >= 2 else aname}"
        new_extra = json.dumps(extra, ensure_ascii=False)
        cur.execute(
            "UPDATE serpapi_ads SET advertiser_name = ?, extra_data = ? WHERE id = ?",
            (clean_name, new_extra, sid),
        )
        stealth_fixed += 1
    print(f"  stealth 소스명 정규화: {stealth_fixed}건")

    # ── 7. naver_shopping advertiser_name 백필 ──
    print("\n[7/8] naver_shopping advertiser_name 백필 (ad_text에서 추출)")
    cur.execute("""
        SELECT d.id, d.ad_text, d.extra_data
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE s.channel = 'naver_shopping'
          AND (d.advertiser_name_raw IS NULL OR d.advertiser_name_raw = '')
    """)
    shopping_rows = cur.fetchall()
    shopping_fixed = 0
    for did, ad_text, extra_json in shopping_rows:
        try:
            extra = json.loads(extra_json) if extra_json else {}
        except (json.JSONDecodeError, TypeError):
            extra = {}

        # extra_data에서 mall 정보 찾기
        mall = extra.get("mall") or extra.get("mallName") or extra.get("storeName") or ""
        if not mall and ad_text:
            # ad_text에서 브랜드/판매자 추출 시도 (첫 번째 단어)
            # 쇼핑 광고 텍스트는 보통 "상품명" 형태
            pass  # 상품명에서 브랜드 추출은 AI enricher에 위임

        if mall:
            cur.execute(
                "UPDATE ad_details SET advertiser_name_raw = ? WHERE id = ?",
                (mall, did),
            )
            shopping_fixed += 1
    print(f"  mall 이름 백필: {shopping_fixed}건 (나머지는 AI enricher 대기)")

    # ── 8. position_zone 백필 ──
    print("\n[8/8] position_zone 백필 (position 기반)")
    # 네이버/구글 검색: 1-3 = top, 4-7 = middle, 8+ = bottom
    # DA/GDN: 1-2 = top, 3-5 = middle, 6+ = bottom
    # 소셜/카탈로그: 위치 의미 없음 -> unknown

    zone_rules = {
        "naver_search":      {"top": 3, "middle": 7},
        "google_search_ads": {"top": 3, "middle": 7},
        "naver_shopping":    {"top": 3, "middle": 8},
        "naver_da":          {"top": 2, "middle": 5},
        "kakao_da":          {"top": 2, "middle": 5},
        "google_gdn":        {"top": 2, "middle": 5},
    }

    cur.execute("""
        SELECT d.id, d.position, s.channel
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
        WHERE d.position_zone IS NULL AND d.position IS NOT NULL
    """)
    pos_rows = cur.fetchall()
    zone_updates = []
    for did, pos, ch in pos_rows:
        rule = zone_rules.get(ch)
        if not rule:
            zone = "unknown"
        elif pos <= rule["top"]:
            zone = "top"
        elif pos <= rule["middle"]:
            zone = "middle"
        else:
            zone = "bottom"
        zone_updates.append((zone, did))

    cur.executemany("UPDATE ad_details SET position_zone = ? WHERE id = ?", zone_updates)
    # position이 NULL인 경우 unknown
    cur.execute("""
        UPDATE ad_details SET position_zone = 'unknown'
        WHERE position_zone IS NULL AND position IS NULL
    """)
    n8b = cur.rowcount
    print(f"  position 기반 zone 할당: {len(zone_updates)}건")
    print(f"  position NULL -> unknown: {n8b}건")

    # ── 커밋 ──
    conn.commit()

    # ── 결과 요약 ──
    print("\n" + "=" * 70)
    print("수정 완료 요약")
    print("=" * 70)
    cur.execute("SELECT COUNT(*) FROM ad_details")
    print(f"  ad_details: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM advertisers")
    print(f"  advertisers: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM campaigns")
    print(f"  campaigns: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM spend_estimates")
    print(f"  spend_estimates: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM serpapi_ads WHERE advertiser_name IS NOT NULL")
    n_serp = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM serpapi_ads")
    t_serp = cur.fetchone()[0]
    print(f"  serpapi_ads (name있는): {n_serp}/{t_serp}")

    # position_zone 분포
    print("\n  position_zone 분포:")
    cur.execute("SELECT position_zone, COUNT(*) FROM ad_details GROUP BY position_zone ORDER BY COUNT(*) DESC")
    for r in cur.fetchall():
        print(f"    {str(r[0]):10s}: {r[1]}건")

    # 보정계수 확인
    print("\n  market_calibration 분포 (spend_estimates):")
    cur.execute("""
        SELECT json_extract(factors, '$.market_calibration') as cal, COUNT(*)
        FROM spend_estimates
        WHERE factors IS NOT NULL
        GROUP BY cal
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    for r in cur.fetchall():
        print(f"    calib={r[0]}: {r[1]}건")

    conn.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
