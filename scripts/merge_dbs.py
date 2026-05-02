"""Merge local DB data into server DB without duplicates.

Strategy: Server DB is the base. Add local-only data to it.
- For tables where server has more: keep server data as-is
- For tables where local has more: add local rows not in server (by natural key)
- For tables only in local: create table and copy all data

Usage: python scripts/merge_dbs.py
Output: merged_db.db (ready for upload)
"""
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SERVER_DB = "server_db.db"
LOCAL_DB = "adscope.db"
OUTPUT_DB = "merged_db.db"


def count(conn, table):
    return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def merge():
    if not os.path.exists(SERVER_DB):
        print(f"ERROR: {SERVER_DB} not found")
        sys.exit(1)
    if not os.path.exists(LOCAL_DB):
        print(f"ERROR: {LOCAL_DB} not found")
        sys.exit(1)

    # Copy server DB as base
    print(f"Copying {SERVER_DB} -> {OUTPUT_DB} as base...")
    shutil.copy2(SERVER_DB, OUTPUT_DB)

    merged = sqlite3.connect(OUTPUT_DB)
    local = sqlite3.connect(LOCAL_DB)
    mc = merged.cursor()
    lc = local.cursor()

    # ── 1) Tables only in local: create and copy ──
    print("\n=== Tables only in local ===")
    local_only_tables = ["shopping_category_rankings", "shopping_keywords", "social_category_rankings"]
    for table in local_only_tables:
        try:
            lc.execute(f'SELECT COUNT(*) FROM "{table}"')
        except:
            print(f"  SKIP {table} (not in local)")
            continue

        cnt = count(local, table)
        if cnt == 0:
            print(f"  SKIP {table} (empty)")
            continue

        # Get CREATE TABLE statement from local
        create_sql = lc.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
        ).fetchone()[0]

        try:
            mc.execute(create_sql)
            print(f"  Created table {table}")
        except sqlite3.OperationalError:
            print(f"  Table {table} already exists")

        # Copy all rows
        cols = [col[1] for col in lc.execute(f'PRAGMA table_info("{table}")').fetchall()]
        col_str = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["?"] * len(cols))

        rows = lc.execute(f'SELECT {col_str} FROM "{table}"').fetchall()
        mc.executemany(f'INSERT OR IGNORE INTO "{table}" ({col_str}) VALUES ({placeholders})', rows)
        print(f"  {table}: inserted {mc.rowcount} / {len(rows)} rows")

    # Also copy indexes for local-only tables
    for table in local_only_tables:
        indexes = lc.execute(
            f"SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='{table}' AND sql IS NOT NULL"
        ).fetchall()
        for idx_sql in indexes:
            try:
                mc.execute(idx_sql[0])
            except:
                pass

    merged.commit()

    # ── 1-1) advertisers: natural key = website (fallback: name) ──
    print("\n=== advertisers ===")
    before = count(merged, "advertisers")

    adv_cols = [col[1] for col in lc.execute('PRAGMA table_info("advertisers")').fetchall()]
    adv_non_id = [c for c in adv_cols if c != "id"]
    adv_col_str = ", ".join(f'"{c}"' for c in adv_non_id)
    adv_placeholders = ", ".join(["?"] * len(adv_non_id))

    existing_adv_website = dict(mc.execute(
        "SELECT website, id FROM advertisers WHERE website IS NOT NULL AND website != ''"
    ).fetchall())
    existing_adv_name = dict(mc.execute(
        "SELECT name, id FROM advertisers WHERE (website IS NULL OR website = '')"
    ).fetchall())

    local_advs = lc.execute(f"SELECT id, {adv_col_str} FROM advertisers").fetchall()
    adv_name_idx = adv_non_id.index("name")
    adv_website_idx = adv_non_id.index("website") if "website" in adv_non_id else None

    local_to_merged_adv = {}  # local_adv_id -> merged_adv_id
    for row in local_advs:
        local_id = row[0]
        data = list(row[1:])
        website = data[adv_website_idx] if adv_website_idx is not None else None
        name = data[adv_name_idx]

        if website:
            if website in existing_adv_website:
                local_to_merged_adv[local_id] = existing_adv_website[website]
                continue
        else:
            if name in existing_adv_name:
                local_to_merged_adv[local_id] = existing_adv_name[name]
                continue

        mc.execute(f"INSERT INTO advertisers ({adv_col_str}) VALUES ({adv_placeholders})", data)
        new_id = mc.lastrowid
        local_to_merged_adv[local_id] = new_id
        if website:
            existing_adv_website[website] = new_id
        else:
            existing_adv_name[name] = new_id

    merged.commit()
    after = count(merged, "advertisers")
    print(f"  Added {after - before} new advertisers ({before} -> {after})")

    # ── 1-2) campaigns: natural key = advertiser_id + first_seen_month + product_service ──
    print("\n=== campaigns ===")
    before = count(merged, "campaigns")

    camp_cols = [col[1] for col in lc.execute('PRAGMA table_info("campaigns")').fetchall()]
    camp_non_id = [c for c in camp_cols if c != "id"]
    camp_col_str = ", ".join(f'"{c}"' for c in camp_non_id)
    camp_placeholders = ", ".join(["?"] * len(camp_non_id))

    existing_camps = {}
    for row in mc.execute("SELECT advertiser_id, strftime('%Y-%m', first_seen), COALESCE(product_service,''), id FROM campaigns"):
        existing_camps[(row[0], row[1], row[2])] = row[3]

    local_camps = lc.execute(f"SELECT id, {camp_col_str} FROM campaigns").fetchall()
    camp_adv_idx = camp_non_id.index("advertiser_id")
    camp_fs_idx = camp_non_id.index("first_seen") if "first_seen" in camp_non_id else None
    camp_ps_idx = camp_non_id.index("product_service") if "product_service" in camp_non_id else None

    local_to_merged_camp = {}  # local_camp_id -> merged_camp_id
    for row in local_camps:
        local_id = row[0]
        data = list(row[1:])

        # remap advertiser_id
        local_adv_id = data[camp_adv_idx]
        merged_adv_id = local_to_merged_adv.get(local_adv_id, local_adv_id)
        data[camp_adv_idx] = merged_adv_id

        fs = data[camp_fs_idx][:7] if camp_fs_idx is not None and data[camp_fs_idx] else None
        ps = data[camp_ps_idx] if camp_ps_idx is not None else None
        key = (merged_adv_id, fs, ps or "")

        if key in existing_camps:
            local_to_merged_camp[local_id] = existing_camps[key]
            continue

        mc.execute(f"INSERT INTO campaigns ({camp_col_str}) VALUES ({camp_placeholders})", data)
        new_id = mc.lastrowid
        local_to_merged_camp[local_id] = new_id
        existing_camps[key] = new_id

    merged.commit()
    after = count(merged, "campaigns")
    print(f"  Added {after - before} new campaigns ({before} -> {after})")

    # ── 2) ad_snapshots: natural key = keyword_id + channel + captured_at ──
    print("\n=== ad_snapshots ===")
    before = count(merged, "ad_snapshots")

    # Get existing natural keys from server
    existing_keys = set(mc.execute(
        "SELECT keyword_id, channel, captured_at FROM ad_snapshots"
    ).fetchall())
    print(f"  Server has {len(existing_keys)} snapshots")

    # Get local rows
    local_rows = lc.execute(
        "SELECT keyword_id, persona_id, device, channel, captured_at, "
        "page_url, screenshot_path, raw_html_path, ad_count, crawl_duration_ms "
        "FROM ad_snapshots"
    ).fetchall()

    # Build ID mapping for ad_snapshots (local_id -> merged_id) for ad_details later
    local_snapshot_map = {}  # local snapshot natural key -> local id
    for row in lc.execute("SELECT id, keyword_id, channel, captured_at FROM ad_snapshots"):
        local_snapshot_map[(row[1], row[2], row[3])] = row[0]

    new_rows = []
    for row in local_rows:
        key = (row[0], row[3], row[4])  # keyword_id, channel, captured_at
        if key not in existing_keys:
            new_rows.append(row)

    if new_rows:
        mc.executemany(
            "INSERT INTO ad_snapshots "
            "(keyword_id, persona_id, device, channel, captured_at, "
            "page_url, screenshot_path, raw_html_path, ad_count, crawl_duration_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            new_rows
        )
    merged.commit()
    after = count(merged, "ad_snapshots")
    print(f"  Added {after - before} new snapshots ({before} -> {after})")

    # Build local_snapshot_id -> merged_snapshot_id mapping
    merged_snapshot_map = {}  # (keyword_id, channel, captured_at) -> merged_id
    for row in mc.execute("SELECT id, keyword_id, channel, captured_at FROM ad_snapshots"):
        merged_snapshot_map[(row[1], row[2], row[3])] = row[0]

    local_to_merged_snapshot = {}  # local_snapshot_id -> merged_snapshot_id
    for (kw_id, ch, cat), local_id in local_snapshot_map.items():
        merged_id = merged_snapshot_map.get((kw_id, ch, cat))
        if merged_id:
            local_to_merged_snapshot[local_id] = merged_id

    # ── 2-1) ad_details: natural key = creative_hash (fallback: url + ad_text) ──
    print("\n=== ad_details ===")
    before = count(merged, "ad_details")

    ad_cols = [col[1] for col in lc.execute('PRAGMA table_info("ad_details")').fetchall()]
    non_id_cols = [c for c in ad_cols if c != "id"]
    col_str = ", ".join(f'"{c}"' for c in non_id_cols)
    placeholders = ", ".join(["?"] * len(non_id_cols))

    # existing dedup keys
    existing_hashes = set(r[0] for r in mc.execute(
        "SELECT creative_hash FROM ad_details WHERE creative_hash IS NOT NULL"
    ).fetchall())
    existing_url_text = set(mc.execute(
        "SELECT url, ad_text FROM ad_details WHERE creative_hash IS NULL"
    ).fetchall())

    local_ads = lc.execute(f"SELECT id, {col_str} FROM ad_details").fetchall()
    snap_idx = non_id_cols.index("snapshot_id") if "snapshot_id" in non_id_cols else None
    hash_idx = non_id_cols.index("creative_hash") if "creative_hash" in non_id_cols else None
    url_idx = non_id_cols.index("url") if "url" in non_id_cols else None
    text_idx = non_id_cols.index("ad_text") if "ad_text" in non_id_cols else None
    ad_adv_idx = non_id_cols.index("advertiser_id") if "advertiser_id" in non_id_cols else None

    new_ads = []
    for row in local_ads:
        local_id = row[0]
        data = list(row[1:])  # non-id columns

        # remap snapshot_id
        if snap_idx is not None and data[snap_idx] is not None:
            data[snap_idx] = local_to_merged_snapshot.get(data[snap_idx], data[snap_idx])

        # remap advertiser_id
        if ad_adv_idx is not None and data[ad_adv_idx] is not None:
            data[ad_adv_idx] = local_to_merged_adv.get(data[ad_adv_idx], data[ad_adv_idx])

        ch = data[hash_idx] if hash_idx is not None else None
        if ch:
            if ch in existing_hashes:
                continue
            existing_hashes.add(ch)
        else:
            url = data[url_idx] if url_idx is not None else None
            txt = data[text_idx] if text_idx is not None else None
            key = (url, txt)
            if key in existing_url_text:
                continue
            existing_url_text.add(key)

        new_ads.append(data)

    if new_ads:
        mc.executemany(
            f"INSERT INTO ad_details ({col_str}) VALUES ({placeholders})",
            new_ads
        )
    merged.commit()
    after = count(merged, "ad_details")
    print(f"  Added {after - before} new ad_details ({before} -> {after})")

    # ── 3) keywords: natural key = keyword ──
    print("\n=== keywords ===")
    before = count(merged, "keywords")

    existing_kw = set(r[0] for r in mc.execute("SELECT keyword FROM keywords").fetchall())
    local_kws = lc.execute(
        "SELECT industry_id, keyword, naver_cpc, monthly_search_vol, is_active, created_at "
        "FROM keywords"
    ).fetchall()

    new_kws = [r for r in local_kws if r[1] not in existing_kw]
    if new_kws:
        mc.executemany(
            "INSERT INTO keywords (industry_id, keyword, naver_cpc, monthly_search_vol, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            new_kws
        )
    merged.commit()
    after = count(merged, "keywords")
    print(f"  Added {after - before} new keywords ({before} -> {after})")

    # ── 4) spend_estimates: natural key = campaign_id + date + channel ──
    print("\n=== spend_estimates ===")
    before = count(merged, "spend_estimates")

    existing_spend = set(mc.execute(
        "SELECT campaign_id, date, channel FROM spend_estimates"
    ).fetchall())

    local_spends = lc.execute(
        "SELECT campaign_id, date, channel, est_daily_spend, confidence, calculation_method, factors "
        "FROM spend_estimates"
    ).fetchall()

    new_spends = []
    for row in local_spends:
        local_camp_id = row[0]
        merged_camp_id = local_to_merged_camp.get(local_camp_id, local_camp_id)
        key = (merged_camp_id, row[1], row[2])
        if key not in existing_spend:
            existing_spend.add(key)
            new_spends.append((merged_camp_id, row[1], row[2], row[3], row[4], row[5], row[6]))

    if new_spends:
        mc.executemany(
            "INSERT INTO spend_estimates "
            "(campaign_id, date, channel, est_daily_spend, confidence, calculation_method, factors) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            new_spends
        )
    merged.commit()
    after = count(merged, "spend_estimates")
    print(f"  Added {after - before} new spend estimates ({before} -> {after})")

    # ── 5) channel_stats: natural key = brand_channel_id + collected_at ──
    print("\n=== channel_stats ===")
    before = count(merged, "channel_stats")

    # Check schema
    cols = [col[1] for col in lc.execute('PRAGMA table_info("channel_stats")').fetchall()]

    if "brand_channel_id" in cols and "collected_at" in cols:
        existing_cs = set(mc.execute(
            "SELECT brand_channel_id, collected_at FROM channel_stats"
        ).fetchall())

        non_id_cols = [c for c in cols if c != "id"]
        col_str = ", ".join(f'"{c}"' for c in non_id_cols)

        local_cs = lc.execute(f"SELECT {col_str} FROM channel_stats").fetchall()

        bci_idx = non_id_cols.index("brand_channel_id")
        ca_idx = non_id_cols.index("collected_at")

        new_cs = [r for r in local_cs if (r[bci_idx], r[ca_idx]) not in existing_cs]
        if new_cs:
            placeholders = ", ".join(["?"] * len(non_id_cols))
            mc.executemany(
                f"INSERT INTO channel_stats ({col_str}) VALUES ({placeholders})",
                new_cs
            )
        merged.commit()
        after = count(merged, "channel_stats")
        print(f"  Added {after - before} new stats ({before} -> {after})")

    # ── 6) news_mentions: natural key = article_title + article_url ──
    print("\n=== news_mentions ===")
    before = count(merged, "news_mentions")

    cols = [col[1] for col in lc.execute('PRAGMA table_info("news_mentions")').fetchall()]

    if "article_title" in cols and "article_url" in cols:
        try:
            existing_news = set(mc.execute("SELECT article_title, article_url FROM news_mentions").fetchall())
        except:
            existing_news = set()

        non_id_cols = [c for c in cols if c != "id"]
        col_str = ", ".join(f'"{c}"' for c in non_id_cols)

        local_news = lc.execute(f"SELECT {col_str} FROM news_mentions").fetchall()

        ti_idx = non_id_cols.index("article_title")
        url_idx = non_id_cols.index("article_url")

        new_news = [r for r in local_news if (r[ti_idx], r[url_idx]) not in existing_news]
        if new_news:
            placeholders = ", ".join(["?"] * len(non_id_cols))
            mc.executemany(
                f"INSERT INTO news_mentions ({col_str}) VALUES ({placeholders})",
                new_news
            )
        merged.commit()
        after = count(merged, "news_mentions")
        print(f"  Added {after - before} new mentions ({before} -> {after})")

    # ── 7) smartstore_snapshots: natural key = product_url + captured_at ──
    print("\n=== smartstore_snapshots ===")
    before = count(merged, "smartstore_snapshots")

    cols = [col[1] for col in lc.execute('PRAGMA table_info("smartstore_snapshots")').fetchall()]

    if "product_url" in cols and "captured_at" in cols:
        try:
            existing_ss = set(mc.execute("SELECT product_url, captured_at FROM smartstore_snapshots").fetchall())
        except:
            existing_ss = set()

        non_id_cols = [c for c in cols if c != "id"]
        col_str = ", ".join(f'"{c}"' for c in non_id_cols)

        local_ss = lc.execute(f"SELECT {col_str} FROM smartstore_snapshots").fetchall()

        pu_idx = non_id_cols.index("product_url")
        ca_idx = non_id_cols.index("captured_at")

        new_ss = [r for r in local_ss if (r[pu_idx], r[ca_idx]) not in existing_ss]
        if new_ss:
            placeholders = ", ".join(["?"] * len(non_id_cols))
            mc.executemany(
                f"INSERT INTO smartstore_snapshots ({col_str}) VALUES ({placeholders})",
                new_ss
            )
        merged.commit()
        after = count(merged, "smartstore_snapshots")
        print(f"  Added {after - before} new snapshots ({before} -> {after})")

    # ── 8) traffic_signals: has unique(advertiser_id, date) ──
    print("\n=== traffic_signals ===")
    before = count(merged, "traffic_signals")

    cols = [col[1] for col in lc.execute('PRAGMA table_info("traffic_signals")').fetchall()]
    non_id_cols = [c for c in cols if c != "id"]
    col_str = ", ".join(f'"{c}"' for c in non_id_cols)
    placeholders = ", ".join(["?"] * len(non_id_cols))

    existing_ts = set(mc.execute("SELECT advertiser_id, date FROM traffic_signals").fetchall())
    local_ts = lc.execute(f"SELECT {col_str} FROM traffic_signals").fetchall()

    ai_idx = non_id_cols.index("advertiser_id")
    d_idx = non_id_cols.index("date")

    new_ts = [r for r in local_ts if (r[ai_idx], r[d_idx]) not in existing_ts]
    if new_ts:
        mc.executemany(
            f"INSERT OR IGNORE INTO traffic_signals ({col_str}) VALUES ({placeholders})",
            new_ts
        )
    merged.commit()
    after = count(merged, "traffic_signals")
    print(f"  Added {after - before} new signals ({before} -> {after})")

    # ── 9) social_impact_scores: natural key = advertiser_id + date ──
    print("\n=== social_impact_scores ===")
    try:
        before = count(merged, "social_impact_scores")
    except:
        before = 0

    try:
        lc.execute('SELECT COUNT(*) FROM social_impact_scores')
        cols = [col[1] for col in lc.execute('PRAGMA table_info("social_impact_scores")').fetchall()]
        non_id_cols = [c for c in cols if c != "id"]
        col_str = ", ".join(f'"{c}"' for c in non_id_cols)
        placeholders = ", ".join(["?"] * len(non_id_cols))

        # Ensure table exists in merged
        create_sql = lc.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='social_impact_scores'"
        ).fetchone()[0]
        try:
            mc.execute(create_sql)
            print("  Created table social_impact_scores")
        except sqlite3.OperationalError:
            pass

        try:
            existing_sis = set(mc.execute("SELECT advertiser_id, date FROM social_impact_scores").fetchall())
        except:
            existing_sis = set()

        local_sis = lc.execute(f"SELECT {col_str} FROM social_impact_scores").fetchall()
        ai_idx = non_id_cols.index("advertiser_id")
        d_idx = non_id_cols.index("date")

        new_sis = [r for r in local_sis if (r[ai_idx], r[d_idx]) not in existing_sis]
        if new_sis:
            mc.executemany(
                f"INSERT OR IGNORE INTO social_impact_scores ({col_str}) VALUES ({placeholders})",
                new_sis
            )
        merged.commit()
        after = count(merged, "social_impact_scores")
        print(f"  Added {after - before} new scores ({before} -> {after})")
    except Exception as e:
        print(f"  SKIP social_impact_scores ({e})")

    # ── 10) brand_channel_contents: natural key = platform + content_id ──
    print("\n=== brand_channel_contents ===")
    try:
        before = count(merged, "brand_channel_contents")
    except:
        before = 0

    try:
        lc.execute('SELECT COUNT(*) FROM brand_channel_contents')
        cols = [col[1] for col in lc.execute('PRAGMA table_info("brand_channel_contents")').fetchall()]
        non_id_cols = [c for c in cols if c != "id"]
        col_str = ", ".join(f'"{c}"' for c in non_id_cols)
        placeholders = ", ".join(["?"] * len(non_id_cols))

        # Ensure table exists in merged
        create_sql = lc.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='brand_channel_contents'"
        ).fetchone()[0]
        try:
            mc.execute(create_sql)
            print("  Created table brand_channel_contents")
        except sqlite3.OperationalError:
            pass

        try:
            existing_bcc = set(mc.execute("SELECT platform, content_id FROM brand_channel_contents").fetchall())
        except:
            existing_bcc = set()

        local_bcc = lc.execute(f"SELECT {col_str} FROM brand_channel_contents").fetchall()
        p_idx = non_id_cols.index("platform")
        ci_idx = non_id_cols.index("content_id")

        new_bcc = [r for r in local_bcc if (r[p_idx], r[ci_idx]) not in existing_bcc]
        if new_bcc:
            mc.executemany(
                f"INSERT OR IGNORE INTO brand_channel_contents ({col_str}) VALUES ({placeholders})",
                new_bcc
            )
        merged.commit()
        after = count(merged, "brand_channel_contents")
        print(f"  Added {after - before} new contents ({before} -> {after})")
    except Exception as e:
        print(f"  SKIP brand_channel_contents ({e})")

    # ── 11) product_categories: natural key = (name, parent_id IS NULL / parent_name) ──
    print("\n=== product_categories ===")
    try:
        before = count(merged, "product_categories")

        # 부모 카테고리 먼저 (name 기준 중복 체크)
        local_parents = lc.execute(
            "SELECT name FROM product_categories WHERE parent_id IS NULL"
        ).fetchall()
        for (name,) in local_parents:
            mc.execute(
                "INSERT INTO product_categories (name) "
                "SELECT ? WHERE NOT EXISTS ("
                "  SELECT 1 FROM product_categories WHERE name = ? AND parent_id IS NULL"
                ")",
                (name, name)
            )

        # 자식 카테고리: 로컬의 부모명으로 머지 DB의 부모 ID 찾아 삽입
        local_children = lc.execute(
            "SELECT pc.name, p.name as parent_name "
            "FROM product_categories pc "
            "JOIN product_categories p ON pc.parent_id = p.id "
            "WHERE pc.parent_id IS NOT NULL"
        ).fetchall()
        for (child_name, parent_name) in local_children:
            parent_row = mc.execute(
                "SELECT id FROM product_categories WHERE name = ? AND parent_id IS NULL",
                (parent_name,)
            ).fetchone()
            if parent_row:
                mc.execute(
                    "INSERT OR IGNORE INTO product_categories (name, parent_id) "
                    "SELECT ?, ? WHERE NOT EXISTS ("
                    "  SELECT 1 FROM product_categories WHERE name = ? AND parent_id = ?"
                    ")",
                    (child_name, parent_row[0], child_name, parent_row[0])
                )
        merged.commit()
        after = count(merged, "product_categories")
        print(f"  Added {after - before} new categories ({before} -> {after})")
    except Exception as e:
        print(f"  SKIP product_categories ({e})")

    # ── Final summary ──
    print(f"\n{'='*50}")
    print(f"Merged DB: {OUTPUT_DB}")
    size_mb = os.path.getsize(OUTPUT_DB) / (1024 * 1024)
    print(f"Size: {size_mb:.1f} MB")

    print("\nFinal counts:")
    for table in sorted(["ad_details", "advertisers", "ad_snapshots", "campaigns",
                          "keywords", "spend_estimates", "news_mentions",
                          "smartstore_snapshots", "traffic_signals", "channel_stats",
                          "shopping_keywords", "shopping_category_rankings",
                          "social_category_rankings", "social_impact_scores",
                          "brand_channel_contents"]):
        try:
            cnt = count(merged, table)
            print(f"  {table}: {cnt:,}")
        except:
            pass

    merged.close()
    local.close()

    # ── 머지 후 정리: 쓰레기 광고주 + 절대경로 이미지 + 중복 소재 ──
    _post_merge_cleanup(OUTPUT_DB)

    print(f"\nDone! Upload {OUTPUT_DB} to server.")


def _post_merge_cleanup(db_path: str):
    """머지 완료 후 DB 품질 정리.

    1. 쓰레기 광고주 삭제 (라이브러리 ID:, 광고카피, 랜덤코드 등)
    2. 절대 로컬 경로 이미지 → NULL (서버에서 접근 불가)
    3. 텍스트 광고 당일 중복 소재 제거
    """
    import re
    GARBAGE_PATTERNS = [
        r"^라이브러리 ID:",
        r"^Library ID:",
        r"^Learn More$",
        r"^Shop Now$",
        r"^자세히 알아보기$",
        r"^지금 쇼핑하기$",
        r"^더 보기$",
        r"^See More$",
        r"^Get Started$",
        r"^Sign Up$",
        r"^Download$",
        r"^[A-Za-z0-9]{8,}[0-9]{6,}$",
        r"^[A-Za-z0-9\-_]{5,}\d{4,}$",
        r"^\d{7,}$",
        r"^\d+-\d+$",
    ]

    def is_garbage(name):
        if not name:
            return True
        if len(name) > 80:
            return True
        for pat in GARBAGE_PATTERNS:
            if re.match(pat, name, re.IGNORECASE):
                return True
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # 1. 쓰레기 광고주
    rows = cur.execute("SELECT id, name FROM advertisers").fetchall()
    garbage_ids = [r[0] for r in rows if is_garbage(r[1])]
    if garbage_ids:
        ph = ",".join("?" * len(garbage_ids))
        cur.execute(f"UPDATE ad_details SET advertiser_id = NULL WHERE advertiser_id IN ({ph})", garbage_ids)
        cur.execute(f"DELETE FROM campaigns WHERE advertiser_id IN ({ph})", garbage_ids)
        cur.execute(f"DELETE FROM advertisers WHERE id IN ({ph})", garbage_ids)
        print(f"\n[cleanup] 쓰레기 광고주 {len(garbage_ids)}개 삭제")

    # 2. 절대 로컬 경로 이미지 → NULL
    cur.execute("""
        UPDATE ad_details SET creative_image_path = NULL
        WHERE creative_image_path IS NOT NULL
          AND creative_image_path NOT LIKE 'stored_images%'
          AND creative_image_path NOT LIKE 'http%'
    """)
    if cur.rowcount:
        print(f"[cleanup] 절대경로 이미지 {cur.rowcount}개 NULL 처리")

    # 3. 텍스트 광고 당일 중복 제거
    cur.execute("""
        DELETE FROM ad_details
        WHERE creative_image_path IS NULL
          AND ad_text IS NOT NULL
          AND advertiser_name_raw IS NOT NULL
          AND id NOT IN (
            SELECT MIN(d2.id)
            FROM ad_details d2
            JOIN ad_snapshots s2 ON d2.snapshot_id = s2.id
            WHERE d2.creative_image_path IS NULL
              AND d2.ad_text IS NOT NULL
              AND d2.advertiser_name_raw IS NOT NULL
            GROUP BY d2.advertiser_name_raw, d2.ad_text, s2.channel, DATE(s2.captured_at)
          )
    """)
    if cur.rowcount:
        print(f"[cleanup] 텍스트 광고 중복 {cur.rowcount}개 삭제")

    # 4. 불량 소재 삭제: URL 없거나 텍스트+이미지 둘 다 없는 껍데기
    cur.execute("""
        DELETE FROM ad_details
        WHERE (url IS NULL OR url = '')
           OR ((ad_text IS NULL OR ad_text = '') AND creative_image_path IS NULL)
    """)
    if cur.rowcount:
        print(f"[cleanup] 불량 소재 (URL없음/내용없음) {cur.rowcount}개 삭제")

    # 5. 품질 체크 리포트 — WARNING 있으면 배포 전 확인 필요
    total = cur.execute("SELECT COUNT(*) FROM ad_details").fetchone()[0]
    no_url = cur.execute("SELECT COUNT(*) FROM ad_details WHERE url IS NULL OR url=''").fetchone()[0]
    no_content = cur.execute("""
        SELECT COUNT(*) FROM ad_details
        WHERE (ad_text IS NULL OR ad_text='') AND creative_image_path IS NULL
    """).fetchone()[0]
    no_adv = cur.execute("""
        SELECT COUNT(*) FROM ad_details
        WHERE advertiser_id IS NULL AND (advertiser_name_raw IS NULL OR advertiser_name_raw='')
    """).fetchone()[0]
    print(f"\n{'='*50}")
    print(f"[품질 검사] 최종 ad_details: {total:,}건")
    print(f"  URL 없음: {no_url}건 | 소재 없음: {no_content}건 | 광고주 없음: {no_adv}건")
    if no_url > 0 or no_content > 0:
        print("  [WARNING] 불량 데이터 잔존 - 배포 전 확인 필요!")
        sys.exit(1)
    else:
        print("  [OK] 품질 검사 통과 - 배포 가능")
    print('='*50)

    conn.commit()
    conn.execute("VACUUM")
    conn.close()


if __name__ == "__main__":
    merge()
