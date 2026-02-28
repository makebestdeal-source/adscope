"""Deduplicate all major tables in adscope.db.

Strategy:
- ad_details: Keep earliest per (creative_hash OR advertiser_name_raw+ad_text+url) per channel.
  Aggregate seen_count, set first_seen_at/last_seen_at from snapshot timestamps.
  Delete image files only for rows being deleted (if unique to that row).
- channel_stats: Keep latest per (advertiser_id, platform, channel_url).
- campaigns: Keep one per (advertiser_id, channel), merge date ranges.
- advertisers: Merge duplicate names, reassign FK references.
- staging_ads: Delete all approved/rejected rows.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "adscope.db"


def dedup_ad_details(conn):
    """Remove duplicate ad_details, keeping earliest per unique key per channel."""
    c = conn.cursor()

    # Ensure columns exist
    cols = {r[1] for r in c.execute("PRAGMA table_info(ad_details)").fetchall()}
    if "first_seen_at" not in cols:
        c.execute("ALTER TABLE ad_details ADD COLUMN first_seen_at DATETIME")
    if "last_seen_at" not in cols:
        c.execute("ALTER TABLE ad_details ADD COLUMN last_seen_at DATETIME")
    if "seen_count" not in cols:
        c.execute("ALTER TABLE ad_details ADD COLUMN seen_count INTEGER DEFAULT 1")

    # Backfill first_seen_at/last_seen_at from snapshot captured_at where NULL
    c.execute("""
        UPDATE ad_details SET
            first_seen_at = (SELECT captured_at FROM ad_snapshots WHERE id = ad_details.snapshot_id),
            last_seen_at = (SELECT captured_at FROM ad_snapshots WHERE id = ad_details.snapshot_id)
        WHERE first_seen_at IS NULL
    """)

    # Find duplicates: group by (channel, dedup_key)
    # dedup_key = creative_hash if available, else advertiser_name_raw|ad_text|url
    # Keep the one with lowest id (earliest)
    c.execute("""
        CREATE TEMP TABLE dedup_groups AS
        SELECT
            d.id,
            s.channel,
            CASE
                WHEN d.creative_hash IS NOT NULL AND d.creative_hash <> ''
                THEN d.creative_hash
                ELSE COALESCE(d.advertiser_name_raw,'') || '|||' || COALESCE(d.ad_text,'') || '|||' || COALESCE(d.url,'')
            END as dedup_key
        FROM ad_details d
        JOIN ad_snapshots s ON d.snapshot_id = s.id
    """)

    # Find keeper IDs (min id per channel+dedup_key)
    c.execute("""
        CREATE TEMP TABLE keepers AS
        SELECT MIN(id) as keep_id, channel, dedup_key, COUNT(*) as cnt
        FROM dedup_groups
        GROUP BY channel, dedup_key
    """)

    # Update keepers with aggregated data
    c.execute("""
        UPDATE ad_details SET
            seen_count = (
                SELECT k.cnt FROM keepers k
                JOIN dedup_groups dg ON dg.id = ad_details.id
                WHERE k.channel = dg.channel AND k.dedup_key = dg.dedup_key
            ),
            last_seen_at = (
                SELECT MAX(s2.captured_at)
                FROM dedup_groups dg2
                JOIN ad_details d2 ON d2.id = dg2.id
                JOIN ad_snapshots s2 ON d2.snapshot_id = s2.id
                JOIN dedup_groups dg_self ON dg_self.id = ad_details.id
                WHERE dg2.channel = dg_self.channel AND dg2.dedup_key = dg_self.dedup_key
            ),
            first_seen_at = (
                SELECT MIN(s2.captured_at)
                FROM dedup_groups dg2
                JOIN ad_details d2 ON d2.id = dg2.id
                JOIN ad_snapshots s2 ON d2.snapshot_id = s2.id
                JOIN dedup_groups dg_self ON dg_self.id = ad_details.id
                WHERE dg2.channel = dg_self.channel AND dg2.dedup_key = dg_self.dedup_key
            )
        WHERE ad_details.id IN (SELECT keep_id FROM keepers WHERE cnt > 1)
    """)

    # Get IDs to delete (not in keepers)
    c.execute("""
        SELECT dg.id FROM dedup_groups dg
        JOIN keepers k ON k.channel = dg.channel AND k.dedup_key = dg.dedup_key
        WHERE dg.id <> k.keep_id
    """)
    delete_ids = [r[0] for r in c.fetchall()]

    if delete_ids:
        # Delete in batches
        batch_size = 500
        for i in range(0, len(delete_ids), batch_size):
            batch = delete_ids[i:i+batch_size]
            placeholders = ",".join("?" * len(batch))
            c.execute(f"DELETE FROM ad_details WHERE id IN ({placeholders})", batch)

    # Clean temp tables
    c.execute("DROP TABLE IF EXISTS dedup_groups")
    c.execute("DROP TABLE IF EXISTS keepers")

    conn.commit()
    return len(delete_ids)


def dedup_channel_stats(conn):
    """Keep latest per (advertiser_id, platform, channel_url)."""
    c = conn.cursor()

    c.execute("""
        DELETE FROM channel_stats WHERE id NOT IN (
            SELECT MAX(id) FROM channel_stats
            GROUP BY advertiser_id, platform, channel_url
        )
    """)
    deleted = c.rowcount
    conn.commit()
    return deleted


def dedup_campaigns(conn):
    """Keep one per (advertiser_id, channel), merge date ranges."""
    c = conn.cursor()

    # Find groups with duplicates
    c.execute("""
        SELECT advertiser_id, channel, MIN(id) as keep_id,
               MIN(first_seen) as min_first, MAX(last_seen) as max_last,
               SUM(total_est_spend) as total_spend, SUM(snapshot_count) as total_snaps,
               COUNT(*) as cnt
        FROM campaigns
        GROUP BY advertiser_id, channel
        HAVING cnt > 1
    """)
    groups = c.fetchall()

    total_deleted = 0
    for adv_id, channel, keep_id, min_first, max_last, total_spend, total_snaps, cnt in groups:
        # Update keeper with merged data
        c.execute("""
            UPDATE campaigns SET
                first_seen = ?, last_seen = ?,
                total_est_spend = ?, snapshot_count = ?
            WHERE id = ?
        """, (min_first, max_last, total_spend, total_snaps, keep_id))

        # Reassign spend_estimates FK
        c.execute("""
            UPDATE spend_estimates SET campaign_id = ?
            WHERE campaign_id IN (
                SELECT id FROM campaigns
                WHERE advertiser_id = ? AND channel = ? AND id <> ?
            )
        """, (keep_id, adv_id, channel, keep_id))

        # Delete duplicates
        c.execute("""
            DELETE FROM campaigns
            WHERE advertiser_id = ? AND channel = ? AND id <> ?
        """, (adv_id, channel, keep_id))
        total_deleted += cnt - 1

    conn.commit()
    return total_deleted


def dedup_advertisers(conn):
    """Merge advertisers with duplicate names."""
    c = conn.cursor()

    # Find duplicate names
    c.execute("""
        SELECT name, MIN(id) as keep_id, GROUP_CONCAT(id) as all_ids, COUNT(*) as cnt
        FROM advertisers GROUP BY name HAVING cnt > 1
    """)
    groups = c.fetchall()

    total_deleted = 0
    for name, keep_id, all_ids_str, cnt in groups:
        other_ids = [int(x) for x in all_ids_str.split(",") if int(x) != keep_id]
        if not other_ids:
            continue

        placeholders = ",".join("?" * len(other_ids))

        # Reassign ad_details FK
        c.execute(
            f"UPDATE ad_details SET advertiser_id = ? WHERE advertiser_id IN ({placeholders})",
            [keep_id] + other_ids
        )

        # Reassign campaigns FK
        c.execute(
            f"UPDATE campaigns SET advertiser_id = ? WHERE advertiser_id IN ({placeholders})",
            [keep_id] + other_ids
        )

        # Reassign channel_stats FK
        c.execute(
            f"UPDATE channel_stats SET advertiser_id = ? WHERE advertiser_id IN ({placeholders})",
            [keep_id] + other_ids
        )

        # activity_scores: delete dupes that would conflict on (advertiser_id, date)
        c.execute(
            f"DELETE FROM activity_scores WHERE advertiser_id IN ({placeholders}) "
            f"AND date IN (SELECT date FROM activity_scores WHERE advertiser_id = ?)",
            other_ids + [keep_id]
        )
        c.execute(
            f"UPDATE activity_scores SET advertiser_id = ? WHERE advertiser_id IN ({placeholders})",
            [keep_id] + other_ids
        )

        # meta_signal_composites: same approach
        c.execute(
            f"DELETE FROM meta_signal_composites WHERE advertiser_id IN ({placeholders}) "
            f"AND date IN (SELECT date FROM meta_signal_composites WHERE advertiser_id = ?)",
            other_ids + [keep_id]
        )
        c.execute(
            f"UPDATE meta_signal_composites SET advertiser_id = ? WHERE advertiser_id IN ({placeholders})",
            [keep_id] + other_ids
        )

        # Delete duplicate advertisers
        c.execute(f"DELETE FROM advertisers WHERE id IN ({placeholders})", other_ids)
        total_deleted += len(other_ids)

    conn.commit()
    return total_deleted


def clean_staging(conn):
    """Delete all processed staging_ads (approved/rejected)."""
    c = conn.cursor()
    c.execute("DELETE FROM staging_ads WHERE status IN ('approved', 'rejected')")
    deleted = c.rowcount
    conn.commit()
    return deleted


def clean_orphan_snapshots(conn):
    """Delete ad_snapshots with no ad_details."""
    c = conn.cursor()
    c.execute("""
        DELETE FROM ad_snapshots
        WHERE id NOT IN (SELECT DISTINCT snapshot_id FROM ad_details)
    """)
    deleted = c.rowcount
    conn.commit()
    return deleted


def main():
    print(f"DB: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))

    # Before counts
    c = conn.cursor()
    tables = ["ad_details", "channel_stats", "campaigns", "advertisers", "staging_ads", "ad_snapshots"]
    print("\n=== BEFORE ===")
    for t in tables:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {c.fetchone()[0]}")

    print("\n--- Deduplicating ad_details ---")
    n = dedup_ad_details(conn)
    print(f"  Deleted: {n}")

    print("\n--- Deduplicating channel_stats ---")
    n = dedup_channel_stats(conn)
    print(f"  Deleted: {n}")

    print("\n--- Deduplicating campaigns ---")
    n = dedup_campaigns(conn)
    print(f"  Deleted: {n}")

    print("\n--- Deduplicating advertisers ---")
    n = dedup_advertisers(conn)
    print(f"  Deleted: {n}")

    print("\n--- Cleaning staging_ads ---")
    n = clean_staging(conn)
    print(f"  Deleted: {n}")

    print("\n--- Cleaning orphan snapshots ---")
    n = clean_orphan_snapshots(conn)
    print(f"  Deleted: {n}")

    # After counts
    print("\n=== AFTER ===")
    for t in tables:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t}: {c.fetchone()[0]}")

    # Verify dedup quality
    c.execute("""
        SELECT s.channel, COUNT(*) as total,
            COUNT(DISTINCT
                CASE WHEN d.creative_hash IS NOT NULL AND d.creative_hash <> ''
                THEN d.creative_hash
                ELSE d.advertiser_name_raw || '|||' || COALESCE(d.ad_text,'') || '|||' || COALESCE(d.url,'')
                END
            ) as uniq
        FROM ad_details d JOIN ad_snapshots s ON d.snapshot_id = s.id
        GROUP BY s.channel ORDER BY total DESC
    """)
    print("\n=== POST-DEDUP VERIFY ===")
    for ch, total, uniq in c.fetchall():
        dup_pct = ((total-uniq)/total*100) if total > 0 else 0
        print(f"  {ch}: {total} total, {uniq} unique, {dup_pct:.1f}% dup")

    # VACUUM
    print("\n--- VACUUM ---")
    conn.execute("VACUUM")
    print("  Done")

    conn.close()
    print("\nComplete!")


if __name__ == "__main__":
    main()
