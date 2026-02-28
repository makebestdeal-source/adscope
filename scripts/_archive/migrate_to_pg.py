"""SQLite → PostgreSQL 데이터 마이그레이션 스크립트."""

import sqlite3
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# DATABASE_URL을 database 모듈 import 전에 설정해야 engine이 올바르게 생성됨
os.environ["DATABASE_URL"] = "postgresql+asyncpg://adscope:adscope@localhost:5433/adscope"

import psycopg
from psycopg.types.json import Jsonb
import asyncio
from database import init_db

PG_DSN = "postgresql://adscope:adscope@localhost:5433/adscope"
SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "adscope.db")

TABLES = [
    "industries", "personas", "keywords", "crawl_schedules",
    "advertisers", "ad_snapshots", "ad_details",
    "campaigns", "trend_data", "spend_estimates",
]

# SQLite 0/1 → Python bool 변환 대상
BOOLEAN_COLUMNS = {
    "keywords": ["is_active"],
    "campaigns": ["is_active"],
}

# SQLite TEXT → PG JSON 변환 대상
JSON_COLUMNS = {
    "advertisers": ["aliases"],
    "ad_details": ["extra_data"],
    "campaigns": ["channels", "extra_data"],
    "spend_estimates": ["factors"],
}


def _fix_row(table: str, cols: list[str], row_dict: dict) -> dict:
    """SQLite → PG 호환 변환."""
    # boolean
    for col in BOOLEAN_COLUMNS.get(table, []):
        if col in row_dict and row_dict[col] is not None:
            row_dict[col] = bool(row_dict[col])

    # JSON: SQLite 텍스트 → Python dict/list → Jsonb 래퍼
    for col in JSON_COLUMNS.get(table, []):
        if col in row_dict and row_dict[col] is not None:
            val = row_dict[col]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            row_dict[col] = Jsonb(val) if val is not None else None

    return row_dict


def main():
    # 1. PG 테이블 생성
    asyncio.run(init_db())
    print("PG tables created")

    # 2. 기존 데이터 클린업 (재실행 대응)
    with psycopg.connect(PG_DSN) as dst:
        for table in reversed(TABLES):
            try:
                dst.execute(f"DELETE FROM {table}")
            except Exception:
                dst.rollback()
        dst.commit()
    print("Existing PG data cleared")

    # 3. SQLite 읽기
    src = sqlite3.connect(SQLITE_PATH)

    # 4. PG 쓰기
    with psycopg.connect(PG_DSN) as dst:
        for table in TABLES:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(f"  {table}: 0 rows (skip)")
                continue

            cols = [d[0] for d in src.execute(f"SELECT * FROM {table}").description]
            col_names = ", ".join(cols)
            placeholders = ", ".join([f"%({c})s" for c in cols])
            sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

            count = 0
            for row in rows:
                row_dict = _fix_row(table, cols, dict(zip(cols, row)))
                try:
                    dst.execute(sql, row_dict)
                    count += 1
                except Exception as e:
                    dst.rollback()
                    print(f"  Error in {table} row {count}: {e}")
                    break
            else:
                dst.commit()
            print(f"  {table}: {count} rows")

        # 5. 시퀀스 리셋
        for table in TABLES:
            try:
                dst.execute(f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE(MAX(id), 1)
                    ) FROM {table}
                """)
                dst.commit()
            except Exception:
                dst.rollback()

    src.close()
    print("Migration complete!")


if __name__ == "__main__":
    main()
