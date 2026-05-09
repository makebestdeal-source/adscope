"""Apply conservative taxonomy overrides for advertisers with clear evidence.

This script is deliberately small and deterministic. It only touches cases where
the advertiser identity or landing domain is strong enough that a generic
classifier should not be allowed to override it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "adscope.db"

BESTSHOP = "\ubca0\uc2a4\ud2b8\uc0f5"
LG_BESTSHOP = "LG\uc804\uc790\ubca0\uc2a4\ud2b8\uc0f5"
ELECTRONICS = "\uac00\uc804/\uc804\uc790"
GAME = "\uac8c\uc784"


def _lookup_id(conn: sqlite3.Connection, table: str, name: str) -> int:
    row = conn.execute(f"SELECT id FROM {table} WHERE name = ? ORDER BY id LIMIT 1", (name,)).fetchone()
    if not row:
        raise RuntimeError(f"{table} missing required row: {name}")
    return int(row[0])


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def _advertiser_ref_tables(conn: sqlite3.Connection) -> list[str]:
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    return [
        table
        for table in tables
        if table != "advertisers" and _table_has_column(conn, table, "advertiser_id")
    ]


def _merge_advertisers(conn: sqlite3.Connection, target_id: int, source_ids: list[int]) -> int:
    source_ids = sorted({int(i) for i in source_ids if i and int(i) != int(target_id)})
    if not source_ids:
        return 0
    placeholders = ",".join("?" for _ in source_ids)
    for table in _advertiser_ref_tables(conn):
        try:
            conn.execute(
                f"UPDATE {table} SET advertiser_id = ? WHERE advertiser_id IN ({placeholders})",
                (target_id, *source_ids),
            )
        except sqlite3.IntegrityError:
            for source_id in source_ids:
                try:
                    conn.execute(
                        f"UPDATE {table} SET advertiser_id = ? WHERE advertiser_id = ?",
                        (target_id, source_id),
                    )
                except sqlite3.IntegrityError:
                    conn.execute(f"DELETE FROM {table} WHERE advertiser_id = ?", (source_id,))
    conn.execute(f"DELETE FROM advertisers WHERE id IN ({placeholders})", source_ids)
    return len(source_ids)


def run(db_path: str | Path = DB_PATH, dry_run: bool = False) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    stats: dict[str, int] = {}
    industry_id = _lookup_id(conn, "industries", ELECTRONICS)
    category_id = _lookup_id(conn, "product_categories", ELECTRONICS)

    bestshop_scope = """
        lower(coalesce(website, '')) LIKE '%bestshop.lge.co.kr%'
        OR name LIKE ?
    """
    bestshop_params = (f"%{BESTSHOP}%",)

    advertiser_ids = [
        int(row["id"])
        for row in conn.execute(f"SELECT id FROM advertisers WHERE {bestshop_scope}", bestshop_params)
    ]

    if advertiser_ids:
        target_row = conn.execute(
            """
            SELECT id
            FROM advertisers
            WHERE id IN ({})
            ORDER BY
                CASE WHEN lower(coalesce(website, '')) LIKE '%bestshop.lge.co.kr%' THEN 0 ELSE 1 END,
                id
            LIMIT 1
            """.format(",".join("?" for _ in advertiser_ids)),
            advertiser_ids,
        ).fetchone()
        target_id = int(target_row["id"])
        source_ids = [adv_id for adv_id in advertiser_ids if adv_id != target_id]

        stats["advertisers_merged"] = _merge_advertisers(conn, target_id, source_ids)
        advertiser_ids = [target_id]
        placeholders = "?"
        cur = conn.execute(
            f"""
            UPDATE advertisers
            SET
                name = ?,
                brand_name = ?,
                industry_id = ?,
                website = 'https://bestshop.lge.co.kr'
            WHERE id IN ({placeholders})
            """,
            (LG_BESTSHOP, LG_BESTSHOP, industry_id, target_id),
        )
        stats["advertisers_updated"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

        cur = conn.execute(
            f"""
            UPDATE ad_details
            SET product_category_id = ?, product_category = ?
            WHERE advertiser_id IN ({placeholders})
              AND (
                  product_category_id IS NULL
                  OR product_category_id IN (
                      SELECT id FROM product_categories
                      WHERE coalesce(industry_id, -1) != ?
                         OR name LIKE ?
                  )
              )
            """,
            (category_id, ELECTRONICS, *advertiser_ids, industry_id, f"%{GAME}%"),
        )
        stats["ad_details_updated_by_advertiser"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

        cur = conn.execute(
            f"""
            UPDATE campaigns
            SET product_service = ?
            WHERE advertiser_id IN ({placeholders})
              AND (
                  product_service IS NULL
                  OR trim(product_service) = ''
                  OR product_service LIKE ?
              )
            """,
            (ELECTRONICS, *advertiser_ids, f"%{GAME}%"),
        )
        stats["campaigns_updated"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    cur = conn.execute(
        """
        UPDATE ad_details
        SET product_category_id = ?, product_category = ?
        WHERE (
            lower(coalesce(display_url, '')) LIKE '%bestshop.lge.co.kr%'
            OR lower(coalesce(url, '')) LIKE '%bestshop.lge.co.kr%'
            OR coalesce(advertiser_name_raw, '') LIKE ?
            OR coalesce(ad_text, '') LIKE ?
        )
          AND (
              product_category_id IS NULL
              OR product_category_id IN (
                  SELECT id FROM product_categories
                  WHERE coalesce(industry_id, -1) != ?
                     OR name LIKE ?
              )
          )
        """,
        (category_id, ELECTRONICS, f"%{BESTSHOP}%", f"%{BESTSHOP}%", industry_id, f"%{GAME}%"),
    )
    stats["ad_details_updated_by_evidence"] = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    conn.close()
    stats["mode"] = 0 if dry_run else 1
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = run(args.db, dry_run=args.dry_run)
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
