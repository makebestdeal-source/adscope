"""
AdScope DB Data Quality Cleanup Script
Runs all 6 cleanup tasks with before/after counts.
"""
import sqlite3
import hashlib
import sys

DB = 'c:/Users/user/Desktop/adscopre/adscope.db'

def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn

def table_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ============================================================
# STEP 0: Initial state
# ============================================================
def step0_initial_state():
    print_section("STEP 0: INITIAL STATE")
    conn = get_conn()
    tables = ['advertisers', 'ad_details', 'campaigns', 'spend_estimates', 'ad_snapshots', 'industries']
    for t in tables:
        try:
            print(f"  {t}: {table_count(conn, t)}")
        except Exception as e:
            print(f"  {t}: ERROR - {e}")

    # Samsung fire entries
    print("\n  --- Samsung Fire related advertisers ---")
    rows = conn.execute(
        "SELECT id, name FROM advertisers WHERE name LIKE '%삼성화재%'"
    ).fetchall()
    for r in rows:
        ad_cnt = conn.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (r['id'],)).fetchone()[0]
        print(f"    id={r['id']}, name={r['name']}, ad_details={ad_cnt}")

    # Industry '기타' count
    gita = conn.execute("SELECT id FROM industries WHERE name='기타'").fetchone()
    if gita:
        gita_id = gita['id']
        gita_cnt = conn.execute("SELECT COUNT(*) FROM advertisers WHERE industry_id=?", (gita_id,)).fetchone()[0]
        total = table_count(conn, 'advertisers')
        print(f"\n  --- Industry '기타' ---")
        print(f"    industry_id={gita_id}, advertisers={gita_cnt}/{total} ({100*gita_cnt/total:.1f}%)")
    else:
        print("\n  --- Industry '기타' NOT FOUND ---")

    # Zero-spend count
    try:
        zs = conn.execute(
            "SELECT COUNT(*) FROM spend_estimates WHERE calculation_method='catalog_no_estimate' AND est_daily_spend=0"
        ).fetchone()[0]
        print(f"\n  --- Zero-spend placeholders ---")
        print(f"    catalog_no_estimate & spend=0: {zs}")
    except Exception as e:
        print(f"\n  --- Zero-spend check error: {e} ---")

    # Creative hash NULL count
    try:
        ch_null = conn.execute(
            "SELECT COUNT(*) FROM ad_details WHERE creative_hash IS NULL AND ad_text IS NOT NULL AND ad_text != ''"
        ).fetchone()[0]
        ch_total_null = conn.execute(
            "SELECT COUNT(*) FROM ad_details WHERE creative_hash IS NULL"
        ).fetchone()[0]
        print(f"\n  --- Creative hash ---")
        print(f"    NULL total: {ch_total_null}")
        print(f"    NULL but has ad_text: {ch_null}")
    except Exception as e:
        print(f"\n  --- Creative hash check error: {e} ---")

    conn.close()

# ============================================================
# STEP 1: Merge 6 duplicate advertiser pairs
# ============================================================
def step1_merge_duplicates():
    print_section("STEP 1: MERGE 6 DUPLICATE ADVERTISER PAIRS")
    conn = get_conn()

    pairs = [
        (616, 462, "기업은행"),
        (606, 2,   "네이버"),
        (617, 316, "아모레퍼시픽"),
        (605, 264, "카카오"),
        (620, 308, "풀무원"),
        (621, 402, "하이트진로"),
    ]

    for remove_id, keep_id, label in pairs:
        # Check if both exist
        r_remove = conn.execute("SELECT id, name FROM advertisers WHERE id=?", (remove_id,)).fetchone()
        r_keep = conn.execute("SELECT id, name FROM advertisers WHERE id=?", (keep_id,)).fetchone()

        if not r_remove:
            print(f"  [{label}] SKIP: remove_id={remove_id} not found")
            continue
        if not r_keep:
            print(f"  [{label}] SKIP: keep_id={keep_id} not found")
            continue

        # Before counts
        ad_before = conn.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (remove_id,)).fetchone()[0]
        camp_before = conn.execute("SELECT COUNT(*) FROM campaigns WHERE advertiser_id=?", (remove_id,)).fetchone()[0]

        print(f"\n  [{label}] Merging id={remove_id} ({r_remove['name']}) -> id={keep_id} ({r_keep['name']})")
        print(f"    Before: ad_details={ad_before}, campaigns={camp_before} on remove_id")

        # Move ad_details
        conn.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))

        # Move campaigns
        conn.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))

        # Move spend_estimates via campaign ids (already moved, but check direct FK too)
        # spend_estimates links to campaigns, not directly to advertisers usually
        # But the user's SQL pattern suggests there might be a direct advertiser_id
        try:
            conn.execute("UPDATE spend_estimates SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))
        except Exception:
            pass  # column might not exist

        # Also update any other tables that reference advertiser_id
        for extra_table in ['official_channels', 'brand_channel_content', 'channel_stats',
                            'smartstore_snapshots', 'activity_scores', 'meta_signal_composites',
                            'panel_observations', 'traffic_signals']:
            try:
                conn.execute(f"UPDATE {extra_table} SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))
            except Exception:
                pass

        # Delete the duplicate
        conn.execute("DELETE FROM advertisers WHERE id=?", (remove_id,))

        # After counts on keep_id
        ad_after = conn.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (keep_id,)).fetchone()[0]
        camp_after = conn.execute("SELECT COUNT(*) FROM campaigns WHERE advertiser_id=?", (keep_id,)).fetchone()[0]
        print(f"    After: ad_details={ad_after}, campaigns={camp_after} on keep_id={keep_id}")

    conn.commit()
    print(f"\n  Advertisers total after merge: {table_count(conn, 'advertisers')}")
    conn.close()

# ============================================================
# STEP 2: Samsung Fire consolidation (3 -> 1)
# ============================================================
def step2_samsung_fire():
    print_section("STEP 2: SAMSUNG FIRE CONSOLIDATION")
    conn = get_conn()

    rows = conn.execute(
        "SELECT id, name FROM advertisers WHERE name LIKE '%삼성화재%' ORDER BY id"
    ).fetchall()

    print(f"  Found {len(rows)} Samsung Fire entries:")
    for r in rows:
        ad_cnt = conn.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (r['id'],)).fetchone()[0]
        camp_cnt = conn.execute("SELECT COUNT(*) FROM campaigns WHERE advertiser_id=?", (r['id'],)).fetchone()[0]
        print(f"    id={r['id']}, name='{r['name']}', ad_details={ad_cnt}, campaigns={camp_cnt}")

    if len(rows) < 2:
        print("  Only 0-1 entries found, nothing to merge.")
        conn.close()
        return

    # Find the canonical one (without space before parenthesis)
    keep_row = None
    remove_rows = []
    for r in rows:
        name = r['name']
        # Prefer "삼성화재해상보험(주)" (no space before parenthesis, not "N잡크루")
        if 'N잡' not in name and '해상보험(주)' in name and ' (주)' not in name:
            keep_row = r
        elif keep_row is None and 'N잡' not in name:
            keep_row = r  # fallback

    if keep_row is None:
        keep_row = rows[0]

    for r in rows:
        if r['id'] != keep_row['id']:
            remove_rows.append(r)

    print(f"\n  Keep: id={keep_row['id']}, name='{keep_row['name']}'")
    for r in remove_rows:
        print(f"  Remove: id={r['id']}, name='{r['name']}'")

    for r in remove_rows:
        remove_id = r['id']
        keep_id = keep_row['id']

        conn.execute("UPDATE ad_details SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))
        conn.execute("UPDATE campaigns SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))
        try:
            conn.execute("UPDATE spend_estimates SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))
        except Exception:
            pass
        for extra_table in ['official_channels', 'brand_channel_content', 'channel_stats',
                            'smartstore_snapshots', 'activity_scores', 'meta_signal_composites',
                            'panel_observations', 'traffic_signals']:
            try:
                conn.execute(f"UPDATE {extra_table} SET advertiser_id=? WHERE advertiser_id=?", (keep_id, remove_id))
            except Exception:
                pass
        conn.execute("DELETE FROM advertisers WHERE id=?", (remove_id,))
        print(f"    Merged id={remove_id} -> id={keep_id}")

    conn.commit()

    # Verify
    final = conn.execute("SELECT COUNT(*) FROM ad_details WHERE advertiser_id=?", (keep_row['id'],)).fetchone()[0]
    print(f"\n  After merge: keep_id={keep_row['id']} has {final} ad_details")
    remaining = conn.execute("SELECT COUNT(*) FROM advertisers WHERE name LIKE '%삼성화재%'").fetchone()[0]
    print(f"  Remaining Samsung Fire advertisers: {remaining}")
    conn.close()

# ============================================================
# STEP 3: Reclassify industry '기타'
# ============================================================
def step3_reclassify_gita():
    print_section("STEP 3: RECLASSIFY INDUSTRY '기타'")
    conn = get_conn()

    # Get industry IDs
    industries = {}
    for row in conn.execute("SELECT id, name FROM industries").fetchall():
        industries[row['name']] = row['id']

    print(f"  Available industries: {len(industries)}")
    for name, iid in sorted(industries.items(), key=lambda x: x[1]):
        cnt = conn.execute("SELECT COUNT(*) FROM advertisers WHERE industry_id=?", (iid,)).fetchone()[0]
        print(f"    [{iid}] {name}: {cnt}")

    gita_id = industries.get('기타')
    if gita_id is None:
        print("  '기타' industry not found!")
        conn.close()
        return

    # Get all '기타' advertisers
    gita_advertisers = conn.execute(
        "SELECT id, name FROM advertisers WHERE industry_id=?", (gita_id,)
    ).fetchall()
    print(f"\n  '기타' advertisers to reclassify: {len(gita_advertisers)}")

    # Classification rules: (pattern, industry_name, exceptions)
    # Order matters - more specific patterns first
    rules = [
        # Samsung sub-brands
        ("삼성생명", "금융/보험"),
        ("삼성화재", "금융/보험"),
        ("삼성카드", "금융/보험"),
        ("삼성증권", "금융/보험"),
        ("삼성물산", "건설/부동산"),
        ("삼성전자", "IT/통신"),
        ("삼성SDS", "IT/통신"),
        ("삼성SDI", "IT/통신"),
        ("삼성바이오", "제약/건강"),
        ("삼성", "IT/통신"),  # default Samsung -> IT

        # Hyundai
        ("현대자동차", "자동차"),
        ("현대차", "자동차"),
        ("현대모비스", "자동차"),
        ("기아", "자동차"),
        ("제네시스", "자동차"),
        ("현대건설", "건설/부동산"),
        ("현대백화점", "유통/이커머스"),
        ("현대카드", "금융/보험"),
        ("현대해상", "금융/보험"),
        ("현대", "자동차"),  # default Hyundai -> auto

        # LG
        ("LG전자", "가전/전자"),
        ("LG생활건강", "뷰티/화장품"),
        ("LG유플러스", "IT/통신"),
        ("LG U+", "IT/통신"),
        ("LG이노텍", "IT/통신"),
        ("LG디스플레이", "IT/통신"),
        ("LG에너지", "IT/통신"),
        ("LG", "가전/전자"),  # default LG -> electronics

        # SK
        ("SK텔레콤", "IT/통신"),
        ("SKT", "IT/통신"),
        ("SK하이닉스", "IT/통신"),
        ("SK이노베이션", "에너지/화학"),
        ("SK에너지", "에너지/화학"),
        ("SK케미칼", "제약/건강"),
        ("SK바이오", "제약/건강"),
        ("SK", "IT/통신"),

        # CJ
        ("CJ제일제당", "식품/음료"),
        ("CJ ENM", "엔터테인먼트"),
        ("CJ올리브영", "뷰티/화장품"),
        ("CJ대한통운", "물류/운송"),
        ("CJ", "식품/음료"),

        # Lotte
        ("롯데쇼핑", "유통/이커머스"),
        ("롯데백화점", "유통/이커머스"),
        ("롯데마트", "유통/이커머스"),
        ("롯데온", "유통/이커머스"),
        ("롯데제과", "식품/음료"),
        ("롯데칠성", "식품/음료"),
        ("롯데푸드", "식품/음료"),
        ("롯데건설", "건설/부동산"),
        ("롯데손해보험", "금융/보험"),
        ("롯데카드", "금융/보험"),
        ("롯데렌탈", "자동차"),
        ("롯데", "유통/이커머스"),

        # Beauty/Cosmetics
        ("아모레", "뷰티/화장품"),
        ("이니스프리", "뷰티/화장품"),
        ("설화수", "뷰티/화장품"),
        ("라네즈", "뷰티/화장품"),
        ("에뛰드", "뷰티/화장품"),
        ("마몽드", "뷰티/화장품"),
        ("헤라", "뷰티/화장품"),

        # IT/Portal
        ("네이버", "IT/통신"),
        ("카카오", "IT/통신"),
        ("라인", "IT/통신"),
        ("쿠팡", "유통/이커머스"),
        ("배달의민족", "유통/이커머스"),
        ("우아한형제들", "유통/이커머스"),
        ("토스", "금융/보험"),
        ("비바리퍼블리카", "금융/보험"),
        ("야놀자", "여행/레저"),
        ("여기어때", "여행/레저"),
        ("직방", "건설/부동산"),
        ("당근", "IT/통신"),
        ("마켓컬리", "유통/이커머스"),
        ("컬리", "유통/이커머스"),
        ("무신사", "패션/의류"),
        ("지그재그", "패션/의류"),
        ("에이블리", "패션/의류"),
        ("29CM", "패션/의류"),

        # Finance
        ("국민은행", "금융/보험"),
        ("KB", "금융/보험"),
        ("신한", "금융/보험"),
        ("하나", "금융/보험"),
        ("우리은행", "금융/보험"),
        ("우리카드", "금융/보험"),
        ("IBK", "금융/보험"),
        ("기업은행", "금융/보험"),
        ("NH", "금융/보험"),
        ("농협", "금융/보험"),
        ("미래에셋", "금융/보험"),
        ("한화생명", "금융/보험"),
        ("한화투자", "금융/보험"),
        ("삼성자산운용", "금융/보험"),
        ("교보", "금융/보험"),
        ("DB손해보험", "금융/보험"),
        ("메리츠", "금융/보험"),
        ("카카오뱅크", "금융/보험"),
        ("케이뱅크", "금융/보험"),
        ("카카오페이", "금융/보험"),
        ("네이버페이", "금융/보험"),
        ("페이코", "금융/보험"),
        ("BC카드", "금융/보험"),
        ("비씨카드", "금융/보험"),
        ("롯데손보", "금융/보험"),

        # Telecom
        ("KT", "IT/통신"),
        ("LGU+", "IT/통신"),

        # Food/Beverage
        ("풀무원", "식품/음료"),
        ("오뚜기", "식품/음료"),
        ("농심", "식품/음료"),
        ("삼양", "식품/음료"),
        ("하이트진로", "식품/음료"),
        ("오비맥주", "식품/음료"),
        ("코카콜라", "식품/음료"),
        ("펩시", "식품/음료"),
        ("스타벅스", "식품/음료"),
        ("맥도날드", "식품/음료"),
        ("버거킹", "식품/음료"),
        ("BBQ", "식품/음료"),
        ("교촌", "식품/음료"),
        ("bhc", "식품/음료"),
        ("파리바게뜨", "식품/음료"),
        ("뚜레쥬르", "식품/음료"),
        ("매일유업", "식품/음료"),
        ("빙그레", "식품/음료"),
        ("동원", "식품/음료"),
        ("대상", "식품/음료"),
        ("정관장", "제약/건강"),

        # Pharma/Health
        ("유한양행", "제약/건강"),
        ("종근당", "제약/건강"),
        ("대웅", "제약/건강"),
        ("한미약품", "제약/건강"),
        ("녹십자", "제약/건강"),
        ("JW", "제약/건강"),
        ("일동", "제약/건강"),
        ("광동", "제약/건강"),

        # Fashion
        ("나이키", "패션/의류"),
        ("아디다스", "패션/의류"),
        ("뉴발란스", "패션/의류"),
        ("유니클로", "패션/의류"),
        ("자라", "패션/의류"),
        ("H&M", "패션/의류"),
        ("폴로", "패션/의류"),
        ("빈폴", "패션/의류"),
        ("코오롱", "패션/의류"),
        ("한섬", "패션/의류"),
        ("LF", "패션/의류"),

        # Auto
        ("BMW", "자동차"),
        ("벤츠", "자동차"),
        ("아우디", "자동차"),
        ("토요타", "자동차"),
        ("볼보", "자동차"),
        ("포르쉐", "자동차"),
        ("쌍용", "자동차"),
        ("르노", "자동차"),

        # Travel
        ("하나투어", "여행/레저"),
        ("모두투어", "여행/레저"),
        ("인터파크", "여행/레저"),
        ("대한항공", "여행/레저"),
        ("아시아나", "여행/레저"),
        ("제주항공", "여행/레저"),
        ("진에어", "여행/레저"),
        ("티웨이", "여행/레저"),
        ("에어부산", "여행/레저"),

        # Education
        ("메가스터디", "교육"),
        ("대성", "교육"),
        ("이투스", "교육"),
        ("에듀윌", "교육"),
        ("해커스", "교육"),
        ("YBM", "교육"),
        ("윤선생", "교육"),
        ("캐논", "가전/전자"),
        ("다이슨", "가전/전자"),
        ("쿠쿠", "가전/전자"),
        ("코웨이", "가전/전자"),

        # Entertainment
        ("SM엔터", "엔터테인먼트"),
        ("JYP", "엔터테인먼트"),
        ("YG", "엔터테인먼트"),
        ("하이브", "엔터테인먼트"),
        ("넷플릭스", "엔터테인먼트"),
        ("왓챠", "엔터테인먼트"),
        ("웨이브", "엔터테인먼트"),
        ("티빙", "엔터테인먼트"),
        ("넥슨", "게임"),
        ("엔씨소프트", "게임"),
        ("넷마블", "게임"),
        ("크래프톤", "게임"),
        ("카카오게임즈", "게임"),
        ("컴투스", "게임"),
        ("펄어비스", "게임"),

        # Construction/Real Estate
        ("GS건설", "건설/부동산"),
        ("대림", "건설/부동산"),
        ("포스코건설", "건설/부동산"),
        ("호반건설", "건설/부동산"),
        ("중흥건설", "건설/부동산"),

        # Retail/E-commerce
        ("신세계", "유통/이커머스"),
        ("이마트", "유통/이커머스"),
        ("SSG", "유통/이커머스"),
        ("GS25", "유통/이커머스"),
        ("GS리테일", "유통/이커머스"),
        ("CU", "유통/이커머스"),
        ("올리브영", "뷰티/화장품"),
        ("11번가", "유통/이커머스"),
        ("G마켓", "유통/이커머스"),
        ("옥션", "유통/이커머스"),
        ("위메프", "유통/이커머스"),
        ("티몬", "유통/이커머스"),
    ]

    reclassified = 0
    not_matched = []

    for adv in gita_advertisers:
        adv_name = adv['name']
        matched = False
        for pattern, industry_name in rules:
            if pattern in adv_name:
                target_id = industries.get(industry_name)
                if target_id is None:
                    # Create the industry if it doesn't exist
                    conn.execute("INSERT INTO industries (name) VALUES (?)", (industry_name,))
                    target_id = conn.execute("SELECT id FROM industries WHERE name=?", (industry_name,)).fetchone()['id']
                    industries[industry_name] = target_id
                    print(f"    Created new industry: {industry_name} (id={target_id})")

                conn.execute("UPDATE advertisers SET industry_id=? WHERE id=?", (target_id, adv['id']))
                reclassified += 1
                matched = True
                break
        if not matched:
            not_matched.append(adv_name)

    conn.commit()

    print(f"\n  Reclassified: {reclassified} advertisers")
    print(f"  Still '기타': {len(not_matched)} advertisers")
    if not_matched:
        print(f"  Unmatched names (first 30):")
        for nm in not_matched[:30]:
            print(f"    - {nm}")

    # Updated industry distribution
    print(f"\n  --- Updated Industry Distribution ---")
    for row in conn.execute(
        "SELECT i.name, COUNT(a.id) as cnt FROM industries i LEFT JOIN advertisers a ON a.industry_id=i.id GROUP BY i.id ORDER BY cnt DESC"
    ).fetchall():
        print(f"    {row['name']}: {row['cnt']}")

    conn.close()

# ============================================================
# STEP 4: Zero-spend placeholder cleanup
# ============================================================
def step4_zero_spend():
    print_section("STEP 4: ZERO-SPEND PLACEHOLDER CLEANUP")
    conn = get_conn()

    before = table_count(conn, 'spend_estimates')
    zero_cnt = conn.execute(
        "SELECT COUNT(*) FROM spend_estimates WHERE calculation_method='catalog_no_estimate' AND est_daily_spend=0"
    ).fetchone()[0]
    print(f"  Before: spend_estimates={before}, zero-spend={zero_cnt}")

    if zero_cnt > 0:
        conn.execute(
            "DELETE FROM spend_estimates WHERE calculation_method='catalog_no_estimate' AND est_daily_spend=0"
        )
        conn.commit()

    after = table_count(conn, 'spend_estimates')
    print(f"  After: spend_estimates={after} (deleted {before - after})")
    conn.close()

# ============================================================
# STEP 5: creative_hash text-based backfill
# ============================================================
def step5_creative_hash():
    print_section("STEP 5: CREATIVE_HASH TEXT-BASED BACKFILL")
    conn = sqlite3.connect(DB)

    null_total = conn.execute("SELECT COUNT(*) FROM ad_details WHERE creative_hash IS NULL").fetchone()[0]
    null_with_text = conn.execute(
        "SELECT COUNT(*) FROM ad_details WHERE creative_hash IS NULL AND ad_text IS NOT NULL AND ad_text != ''"
    ).fetchone()[0]
    print(f"  Before: creative_hash NULL={null_total}, NULL with ad_text={null_with_text}")

    cursor = conn.execute(
        "SELECT id, ad_text FROM ad_details WHERE creative_hash IS NULL AND ad_text IS NOT NULL AND ad_text != ''"
    )
    rows = cursor.fetchall()
    updated = 0
    for row in rows:
        h = hashlib.sha256(row[1].encode('utf-8')).hexdigest()
        conn.execute("UPDATE ad_details SET creative_hash = ? WHERE id = ?", (h, row[0]))
        updated += 1

    conn.commit()

    null_after = conn.execute("SELECT COUNT(*) FROM ad_details WHERE creative_hash IS NULL").fetchone()[0]
    print(f"  Updated: {updated} rows")
    print(f"  After: creative_hash NULL={null_after}")
    conn.close()

# ============================================================
# STEP 6: Final statistics
# ============================================================
def step6_final_stats():
    print_section("STEP 6: FINAL STATISTICS")
    conn = get_conn()

    print("  --- Table Row Counts ---")
    tables = ['advertisers', 'ad_details', 'campaigns', 'spend_estimates', 'ad_snapshots', 'industries']
    for t in tables:
        try:
            print(f"    {t}: {table_count(conn, t)}")
        except Exception as e:
            print(f"    {t}: ERROR - {e}")

    # Duplicate advertiser check
    print("\n  --- Duplicate Advertiser Check ---")
    pairs = [(616, "기업은행"), (606, "네이버"), (617, "아모레퍼시픽"), (605, "카카오"), (620, "풀무원"), (621, "하이트진로")]
    for rid, label in pairs:
        exists = conn.execute("SELECT COUNT(*) FROM advertisers WHERE id=?", (rid,)).fetchone()[0]
        print(f"    id={rid} ({label}): {'STILL EXISTS!' if exists else 'DELETED OK'}")

    samsung = conn.execute("SELECT COUNT(*) FROM advertisers WHERE name LIKE '%삼성화재%'").fetchone()[0]
    print(f"    Samsung Fire entries: {samsung} (should be 1)")

    # Industry '기타'
    gita = conn.execute("SELECT id FROM industries WHERE name='기타'").fetchone()
    if gita:
        gita_cnt = conn.execute("SELECT COUNT(*) FROM advertisers WHERE industry_id=?", (gita['id'],)).fetchone()[0]
        total = table_count(conn, 'advertisers')
        print(f"\n  --- Industry '기타' ---")
        print(f"    {gita_cnt}/{total} ({100*gita_cnt/total:.1f}%)")

    # Zero-spend
    try:
        zs = conn.execute(
            "SELECT COUNT(*) FROM spend_estimates WHERE calculation_method='catalog_no_estimate' AND est_daily_spend=0"
        ).fetchone()[0]
        print(f"\n  --- Zero-spend placeholders ---")
        print(f"    catalog_no_estimate & spend=0: {zs}")
    except:
        pass

    # Creative hash
    ch_null = conn.execute("SELECT COUNT(*) FROM ad_details WHERE creative_hash IS NULL").fetchone()[0]
    ch_total = table_count(conn, 'ad_details')
    print(f"\n  --- Creative Hash ---")
    print(f"    NULL: {ch_null}/{ch_total} ({100*ch_null/ch_total:.1f}%)")

    conn.close()

# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    print("AdScope DB Data Quality Cleanup")
    print(f"DB: {DB}")

    step0_initial_state()
    step1_merge_duplicates()
    step2_samsung_fire()
    step3_reclassify_gita()
    step4_zero_spend()
    step5_creative_hash()
    step6_final_stats()

    print("\n" + "="*60)
    print("  ALL DONE!")
    print("="*60)
