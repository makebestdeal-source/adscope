"""연령별 페르소나 광고 수집 — 경량 모드.

12개 인구통계 페르소나로 네이버 검색광고를 수집.
Docker 불필요, SQLite 직접 적재. 스크린샷 없음.

사용법:
    python scripts/quick_collect.py
    python scripts/quick_collect.py --personas M20,F20,M30,F30
    python scripts/quick_collect.py --keywords "대출,보험,성형외과"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///adscope.db")

from loguru import logger
from sqlalchemy import select

from crawler.config import crawler_settings
from crawler.naver_search import NaverSearchCrawler
from crawler.personas.profiles import PERSONAS
from database import async_session, init_db
from database.models import Keyword, Persona
from processor.pipeline import save_crawl_results

TOP_KEYWORDS = [
    "대출", "보험", "성형외과", "다이어트", "영어회화",
    "아파트 분양", "변호사", "패션", "항공권", "중고차",
]

DEMOGRAPHIC_PERSONAS = [
    "M10", "F10", "M20", "F20", "M30", "F30",
    "M40", "F40", "M50", "F50", "M60", "F60",
]


def parse_args():
    p = argparse.ArgumentParser(description="연령별 페르소나 광고 수집")
    p.add_argument("--personas", default=",".join(DEMOGRAPHIC_PERSONAS))
    p.add_argument("--keywords", default=",".join(TOP_KEYWORDS))
    p.add_argument("--device", default="pc", choices=["pc", "mobile"])
    return p.parse_args()


def apply_fast_mode():
    """체류시간 최소화 + 스크린샷 비활성화."""
    crawler_settings.dwell_min_ms = 2_000
    crawler_settings.dwell_max_ms = 4_000
    crawler_settings.dwell_scroll_count_min = 1
    crawler_settings.dwell_scroll_count_max = 2
    crawler_settings.warmup_site_count = 0
    crawler_settings.scroll_read_pause_min_ms = 300
    crawler_settings.scroll_read_pause_max_ms = 1_000
    crawler_settings.inter_page_min_ms = 500
    crawler_settings.inter_page_max_ms = 2_000
    crawler_settings.mouse_enabled = False


def patch_no_screenshot():
    """스크린샷/이미지 저장 완전 비활성화 — 디스크 절약."""
    from crawler.base_crawler import BaseCrawler

    async def _noop_screenshot(self, page, keyword, persona_code):
        return None

    async def _noop_capture(self, page, sel, kw, pc, pn="ad"):
        return None

    BaseCrawler._take_screenshot = _noop_screenshot
    BaseCrawler._capture_ad_element = _noop_capture


async def ensure_data(session, personas, keywords):
    """DB에 페르소나/키워드가 없으면 생성."""
    for code in personas:
        r = await session.execute(select(Persona).where(Persona.code == code))
        if not r.scalar_one_or_none():
            profile = PERSONAS.get(code)
            if profile:
                session.add(Persona(
                    code=code, age_group=profile.age_group,
                    gender=profile.gender, login_type=profile.login_type,
                    description=profile.description,
                    targeting_category=profile.targeting_category,
                    is_clean=profile.is_clean, primary_device=profile.primary_device,
                ))
    for kw in keywords:
        r = await session.execute(select(Keyword).where(Keyword.keyword == kw))
        if not r.scalar_one_or_none():
            session.add(Keyword(industry_id=1, keyword=kw, is_active=True))
    await session.commit()


async def main():
    args = parse_args()
    t0 = time.time()

    apply_fast_mode()
    patch_no_screenshot()

    await init_db()

    personas = [p.strip() for p in args.personas.split(",") if p.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    async with async_session() as session:
        await ensure_data(session, personas, keywords)

    n = len(personas)
    logger.info(f"수집: {n}명 × {len(keywords)}키워드 ({args.device})")

    total_saved = 0
    total_ads = 0
    total_errors = 0

    for i, code in enumerate(personas, 1):
        profile = PERSONAS.get(code)
        label = f"{profile.age_group} {profile.gender}" if profile and profile.age_group else code
        logger.info(f"[{i}/{n}] {code} ({label})")

        try:
            async with NaverSearchCrawler() as crawler:
                results = await crawler.crawl_keywords(
                    keywords=keywords, persona_code=code, device_type=args.device,
                )
                ads = sum(len(r.get("ads", [])) for r in results if not r.get("error"))
                errs = sum(1 for r in results if r.get("error"))

                # 즉시 DB 저장 (페르소나별)
                async with async_session() as session:
                    saved = await save_crawl_results(session, results)

                total_saved += saved
                total_ads += ads
                total_errors += errs
                logger.info(f"  → 광고 {ads}건, DB {saved}건 저장")

        except Exception as e:
            logger.error(f"  → 실패: {e}")

    elapsed = time.time() - t0

    print(f"\n{'='*55}")
    print(f"  수집 완료")
    print(f"{'='*55}")
    print(f"  페르소나  : {n}명")
    print(f"  키워드    : {len(keywords)}개")
    print(f"  총 광고   : {total_ads}건")
    print(f"  DB 저장   : {total_saved}건 스냅샷")
    print(f"  에러      : {total_errors}건")
    print(f"  소요시간  : {elapsed:.0f}초 ({elapsed/60:.1f}분)")
    print(f"{'='*55}")


if __name__ == "__main__":
    asyncio.run(main())
