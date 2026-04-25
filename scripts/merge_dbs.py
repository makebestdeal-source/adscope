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

    # Only add if campaign_id exists in merged DB
    existing_campaigns = set(r[0] for r in mc.execute("SELECT id FROM campaigns").fetchall())

    new_spends = []
    skipped_campaign = 0
    for row in local_spends:
        key = (row[0], row[1], row[2])
        if key not in existing_spend:
            if row[0] in existing_campaigns:
                new_spends.append(row)
            else:
                skipped_campaign += 1

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
    if skipped_campaign:
        print(f"  Skipped {skipped_campaign} (campaign_id not in server)")

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
    print(f"\nDone! Upload {OUTPUT_DB} to server.")


if __name__ == "__main__":
    merge()
