"""네이버 쇼핑 크롤러 -> fast_crawl save_to_db -> DB 저장 테스트."""

import asyncio
import io
import os
import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _root)
os.chdir(_root)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

os.environ["CRAWLER_WARMUP_SITE_COUNT"] = "0"

from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

from database import init_db, async_session
from database.models import AdDetail, AdSnapshot
from sqlalchemy import select, func
from crawler.naver_shopping import NaverShoppingCrawler
from crawler.personas.profiles import PERSONAS
from crawler.personas.device_config import PC_DEVICE


async def main():
    await init_db()

    # 수집 전 카운트
    async with async_session() as session:
        before_details = (await session.execute(
            select(func.count(AdDetail.id)).where(AdDetail.ad_type == "naver_shopping_ad")
        )).scalar() or 0
        before_snaps = (await session.execute(
            select(func.count(AdSnapshot.id)).where(AdSnapshot.channel == "naver_shopping")
        )).scalar() or 0
    print(f"Before: {before_details} details, {before_snaps} snapshots")

    # 크롤링
    keyword = "노트북"
    print(f"Crawling Naver Shopping '{keyword}'...")
    async with NaverShoppingCrawler() as crawler:
        result = await crawler.crawl_keyword(keyword, PERSONAS["M30"], PC_DEVICE)

    ads = result.get("ads", [])
    print(f"Crawled: {len(ads)} ads")

    if not ads:
        print("No ads!")
        return

    # fast_crawl의 save_to_db 사용
    from scripts.fast_crawl import save_to_db
    await save_to_db("naver_shopping", result, keyword, "M30", "pc")

    # 수집 후 카운트
    async with async_session() as session:
        after_details = (await session.execute(
            select(func.count(AdDetail.id)).where(AdDetail.ad_type == "naver_shopping_ad")
        )).scalar() or 0
        after_snaps = (await session.execute(
            select(func.count(AdSnapshot.id)).where(AdSnapshot.channel == "naver_shopping")
        )).scalar() or 0
    print(f"After: {after_details} details (+{after_details - before_details}), "
          f"{after_snaps} snapshots (+{after_snaps - before_snaps})")


if __name__ == "__main__":
    asyncio.run(main())
