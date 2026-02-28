"""트렌드 데이터 수집기 — Google Trends + DB 기반 내부 트렌드."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger
from pytrends.request import TrendReq
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import AdSnapshot, Keyword, TrendData


class TrendCollector:
    """Google Trends로 키워드별 트렌드 지수를 수집하고 DB에 적재."""

    def __init__(self, hl: str = "ko", tz: int = -540, geo: str = "KR"):
        self.hl = hl
        self.tz = tz
        self.geo = geo
        self._pytrends: TrendReq | None = None

    def _get_pytrends(self) -> TrendReq:
        if self._pytrends is None:
            self._pytrends = TrendReq(hl=self.hl, tz=self.tz)
        return self._pytrends

    def fetch_google_trends(
        self,
        keywords: list[str],
        timeframe: str = "today 3-m",
    ) -> dict[str, float]:
        """Google Trends에서 키워드별 최근 평균 관심도 수집.

        Returns:
            {"키워드": 0~100 평균값, ...}
        """
        results: dict[str, float] = {}

        # Google Trends는 한 번에 5개까지만 비교 가능
        for i in range(0, len(keywords), 5):
            batch = keywords[i : i + 5]
            try:
                pt = self._get_pytrends()
                pt.build_payload(batch, cat=0, timeframe=timeframe, geo=self.geo)
                df = pt.interest_over_time()

                if df.empty:
                    for kw in batch:
                        results[kw] = 0.0
                    continue

                for kw in batch:
                    if kw in df.columns:
                        # 최근 7일 평균
                        recent = df[kw].tail(7).mean()
                        results[kw] = round(float(recent), 2)
                    else:
                        results[kw] = 0.0

            except Exception as e:
                logger.warning(f"[trend] Google Trends batch 실패: {e}")
                for kw in batch:
                    results[kw] = 0.0

        return results

    async def compute_naver_trend(
        self,
        session: AsyncSession,
        keyword_id: int,
        days: int = 7,
    ) -> float:
        """DB의 크롤링 데이터로 네이버 내부 트렌드 지수 계산.

        최근 days일간 해당 키워드의 광고 수 변화를 기반으로 0~100 정규화.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await session.execute(
            select(func.avg(AdSnapshot.ad_count))
            .where(AdSnapshot.keyword_id == keyword_id)
            .where(AdSnapshot.captured_at >= cutoff)
        )
        recent_avg = float(result.scalar() or 0)

        # 전체 평균 대비 비율
        all_result = await session.execute(
            select(func.avg(AdSnapshot.ad_count))
            .where(AdSnapshot.keyword_id == keyword_id)
        )
        overall_avg = float(all_result.scalar() or 1)

        if overall_avg == 0:
            return 50.0

        ratio = recent_avg / overall_avg
        # 0.5~1.5 범위를 0~100으로 매핑
        normalized = max(0.0, min(100.0, (ratio - 0.5) * 100.0))
        return round(normalized, 2)

    async def collect_and_save(
        self,
        session: AsyncSession,
        keyword_ids: list[int] | None = None,
    ) -> int:
        """활성 키워드의 트렌드를 수집하여 DB에 적재.

        Returns:
            적재된 트렌드 레코드 수
        """
        # 활성 키워드 조회
        query = select(Keyword).where(Keyword.is_active.is_(True))
        if keyword_ids:
            query = query.where(Keyword.id.in_(keyword_ids))
        result = await session.execute(query)
        keywords = result.scalars().all()

        if not keywords:
            logger.warning("[trend] 수집 대상 키워드 없음")
            return 0

        keyword_map = {kw.keyword: kw for kw in keywords}
        keyword_names = list(keyword_map.keys())

        # Google Trends 수집 (동기 호출이므로 executor에서 실행)
        logger.info(f"[trend] Google Trends 수집 시작 ({len(keyword_names)}개 키워드)")
        loop = asyncio.get_event_loop()
        google_trends = await loop.run_in_executor(
            None, self.fetch_google_trends, keyword_names
        )

        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        saved = 0

        for kw_name, kw_obj in keyword_map.items():
            # 오늘 날짜 중복 체크
            existing = await session.execute(
                select(TrendData)
                .where(TrendData.keyword_id == kw_obj.id)
                .where(TrendData.date == today)
            )
            if existing.scalar_one_or_none():
                continue

            # 네이버 내부 트렌드 계산
            naver_trend = await self.compute_naver_trend(session, kw_obj.id)
            google_trend = google_trends.get(kw_name, 0.0)

            trend = TrendData(
                keyword_id=kw_obj.id,
                date=today,
                naver_trend=naver_trend,
                google_trend=google_trend,
                naver_search_vol=kw_obj.monthly_search_vol,
            )
            session.add(trend)
            saved += 1

        await session.commit()
        logger.info(f"[trend] 트렌드 {saved}건 적재 완료 (날짜: {today.date()})")
        return saved
