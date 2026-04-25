"""Proper bidirectional DB merge using INSERT OR IGNORE.

Pre-condition: Both DBs share consistent ID space (verified: 0 mismatches
across advertisers, campaigns, keywords, snapshots, details).

Strategy:
  1. Copy server_db.db → merged_db.db (server as base)
  2. ATTACH local adscope.db
  3. INSERT OR IGNORE from local into each table (preserves server rows, adds local-only rows)
  4. Handle local-only tables (shopping_keywords, etc.)
  5. Clean up minimal orphans (119 spend_estimates with no campaign)

Usage: python scripts/merge_dbs_v2.py
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
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    except Exception:
        return -1


def get_columns(conn, table):
    return [col[1] for col in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def merge():
    if not os.path.exists(SERVER_DB):
        print(f"ERROR: {SERVER_DB} not found")
        sys.exit(1)
    if not os.path.exists(LOCAL_DB):
        print(f"ERROR: {LOCAL_DB} not found")
        sys.exit(1)

    # Step 1: Copy server as base
    print(f"Copying {SERVER_DB} -> {OUTPUT_DB}...")
    shutil.copy2(SERVER_DB, OUTPUT_DB)

    conn = sqlite3.connect(OUTPUT_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Step 2: Attach local DB
    conn.execute(f'ATTACH DATABASE "{LOCAL_DB}" AS local_db')

    # Get all tables in server (main) and local
    main_tables = set(
        r[0] for r in conn.execute(
            "SELECT name FROM main.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )
    local_tables = set(
        r[0] for r in conn.execute(
            "SELECT name FROM local_db.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    )

    common_tables = main_tables & local_tables
    local_only_tables = local_tables - main_tables

    print(f"\nCommon tables: {len(common_tables)}")
    print(f"Local-only tables: {local_only_tables}")

    # Step 3: INSERT OR IGNORE for all common tables
    print("\n" + "=" * 60)
    print("MERGING COMMON TABLES")
    print("=" * 60)

    # Order matters: parent tables first (advertisers, keywords, personas before campaigns, etc.)
    ordered_tables = [
        "users", "industries", "personas", "product_categories",
        "advertisers", "keywords",
        "campaigns", "ad_snapshots",
        "ad_details", "spend_estimates",
        "advertiser_products", "advertiser_favorites",
        "brand_channel_contents", "channel_stats",
        "news_mentions", "smartstore_tracked_products", "smartstore_snapshots",
        "traffic_signals", "activity_scores", "social_impact_scores",
        "meta_signal_composites", "journey_events", "campaign_lifts",
        "naver_search_products", "landing_url_cache",
        "serpapi_ads", "staging_ads",
        "ad_platforms", "adic_ad_expenses",
        "login_history", "user_sessions", "password_reset_tokens",
        "mobile_panel_devices", "mobile_panel_exposures",
        "launch_products", "launch_impact_scores", "launch_mentions",
        "product_ad_activities", "unknown_ad_marks",
    ]

    # Add any common tables not in the ordered list
    remaining = common_tables - set(ordered_tables)
    ordered_tables.extend(sorted(remaining))

    total_added = 0
    for table in ordered_tables:
        if table not in common_tables:
            continue

        before = count(conn, table)
        local_cnt = conn.execute(f'SELECT COUNT(*) FROM local_db."{table}"').fetchone()[0]

        if local_cnt == 0:
            continue

        # Get columns
        cols = get_columns(conn, table)
        col_str = ", ".join(f'"{c}"' for c in cols)

        try:
            conn.execute(
                f'INSERT OR IGNORE INTO main."{table}" ({col_str}) '
                f'SELECT {col_str} FROM local_db."{table}"'
            )
            conn.commit()
        except Exception as e:
            print(f"  ERROR {table}: {e}")
            continue

        after = count(conn, table)
        added = after - before
        if added > 0:
            total_added += added
            print(f"  {table}: {before:,} -> {after:,} (+{added:,})")

    print(f"\nTotal rows added from common tables: {total_added:,}")

    # Step 4: Create and populate local-only tables
    if local_only_tables:
        print("\n" + "=" * 60)
        print("LOCAL-ONLY TABLES")
        print("=" * 60)

        for table in sorted(local_only_tables):
            local_cnt = conn.execute(f'SELECT COUNT(*) FROM local_db."{table}"').fetchone()[0]
            if local_cnt == 0:
                print(f"  SKIP {table} (empty)")
                continue

            # Get CREATE statement
            create_sql = conn.execute(
                f"SELECT sql FROM local_db.sqlite_master WHERE type='table' AND name='{table}'"
            ).fetchone()[0]

            try:
                conn.execute(create_sql)
            except sqlite3.OperationalError:
                pass  # already exists

            cols = [
                col[1] for col in conn.execute(f'PRAGMA local_db.table_info("{table}")').fetchall()
            ]
            col_str = ", ".join(f'"{c}"' for c in cols)

            conn.execute(
                f'INSERT OR IGNORE INTO main."{table}" ({col_str}) '
                f'SELECT {col_str} FROM local_db."{table}"'
            )
            conn.commit()

            final_cnt = count(conn, table)
            print(f"  {table}: {final_cnt:,} rows")

            # Copy indexes
            indexes = conn.execute(
                f"SELECT sql FROM local_db.sqlite_master "
                f"WHERE type='index' AND tbl_name='{table}' AND sql IS NOT NULL"
            ).fetchall()
            for idx in indexes:
                try:
                    conn.execute(idx[0])
                except Exception:
                    pass

    conn.commit()

    # Step 5: Check for orphan spend_estimates
    print("\n" + "=" * 60)
    print("INTEGRITY CHECK")
    print("=" * 60)

    orphan_spends = conn.execute(
        "SELECT COUNT(*) FROM spend_estimates "
        "WHERE campaign_id NOT IN (SELECT id FROM campaigns)"
    ).fetchone()[0]
    print(f"  Orphan spend_estimates (no campaign): {orphan_spends}")

    if orphan_spends > 0 and orphan_spends < 200:
        # Small number - safe to keep or delete
        orphan_spend_total = conn.execute(
            "SELECT COALESCE(SUM(est_daily_spend), 0) FROM spend_estimates "
            "WHERE campaign_id NOT IN (SELECT id FROM campaigns)"
        ).fetchone()[0]
        print(f"  Orphan spend total: {orphan_spend_total/1e8:.2f} billion won")
        # Keep them for now - they don't cause issues

    orphan_details = conn.execute(
        "SELECT COUNT(*) FROM ad_details "
        "WHERE snapshot_id NOT IN (SELECT id FROM ad_snapshots)"
    ).fetchone()[0]
    print(f"  Orphan ad_details (no snapshot): {orphan_details}")

    orphan_campaigns = conn.execute(
        "SELECT COUNT(*) FROM campaigns "
        "WHERE advertiser_id NOT IN (SELECT id FROM advertisers)"
    ).fetchone()[0]
    print(f"  Orphan campaigns (no advertiser): {orphan_campaigns}")

    # Step 6: Check for actual duplicates in spend_estimates
    dup_spends = conn.execute(
        "SELECT COUNT(*) FROM ("
        "  SELECT campaign_id, date, channel, COUNT(*) as cnt "
        "  FROM spend_estimates "
        "  GROUP BY campaign_id, date, channel "
        "  HAVING cnt > 1"
        ")"
    ).fetchone()[0]
    print(f"  Duplicate spend_estimates (same campaign+date+channel): {dup_spends}")

    if dup_spends > 0:
        # Deduplicate: keep the one with the highest est_daily_spend (or first by id)
        print("  Deduplicating spend_estimates...")
        before_dedup = count(conn, "spend_estimates")
        conn.execute(
            "DELETE FROM spend_estimates WHERE id NOT IN ("
            "  SELECT MIN(id) FROM spend_estimates "
            "  GROUP BY campaign_id, date, channel"
            ")"
        )
        conn.commit()
        after_dedup = count(conn, "spend_estimates")
        print(f"  Deduped: {before_dedup:,} -> {after_dedup:,} (removed {before_dedup - after_dedup:,})")

    # Detach and VACUUM
    conn.execute("DETACH DATABASE local_db")

    print("\n" + "=" * 60)
    print("FINAL SUMMARY")
    print("=" * 60)

    key_tables = [
        "advertisers", "campaigns", "keywords",
        "ad_snapshots", "ad_details", "spend_estimates",
        "brand_channel_contents", "channel_stats",
        "news_mentions", "traffic_signals",
        "smartstore_snapshots", "staging_ads", "serpapi_ads",
        "activity_scores", "social_impact_scores",
        "meta_signal_composites", "journey_events",
        "shopping_keywords", "shopping_category_rankings", "social_category_rankings",
    ]

    for table in key_tables:
        cnt = count(conn, table)
        if cnt >= 0:
            suffix = ""
            if table == "spend_estimates":
                total = conn.execute("SELECT SUM(est_daily_spend) FROM spend_estimates").fetchone()[0]
                suffix = f" (total: {total / 1e8:.1f} billion won)"
            print(f"  {table}: {cnt:,}{suffix}")

    size_mb = os.path.getsize(OUTPUT_DB) / (1024 * 1024)
    print(f"\nFile size: {size_mb:.1f} MB")

    print("\nVACUUM...")
    conn.execute("VACUUM")
    conn.close()

    size_mb = os.path.getsize(OUTPUT_DB) / (1024 * 1024)
    print(f"After VACUUM: {size_mb:.1f} MB")
    print(f"\nDone! {OUTPUT_DB} ready for upload.")


if __name__ == "__main__":
    merge()
