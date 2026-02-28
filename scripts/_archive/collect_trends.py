"""트렌드 데이터 수집 실행 스크립트."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# PG 사용 시 환경변수 설정
if not os.getenv("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://adscope:adscope@localhost:5433/adscope"

from database import async_session, init_db
from crawler.trend_collector import TrendCollector


async def main():
    await init_db()

    collector = TrendCollector()
    async with async_session() as session:
        saved = await collector.collect_and_save(session)
        print(f"트렌드 {saved}건 수집/적재 완료")


if __name__ == "__main__":
    asyncio.run(main())
