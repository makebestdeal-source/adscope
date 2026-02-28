"""전체 디지털 광고 시장 규모 보정 모듈.

수집 데이터(카탈로그+서프)를 기반으로 전체 시장 광고비를 추정.

보정 3단계:
1. 매체 이용량 보정 (채널별 MAU/DAU 기반 도달률 가중치)
2. 전체 시장 보정 (업계 공식 시장 규모 대비 스케일링)
3. 접촉률 보정 (stealth 서프 데이터, campaign_builder에서 이미 적용)

제외 대상 (소형 광고주 다수): naver_search, google_search_ads, naver_shopping
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC, timedelta

from sqlalchemy import func, select, text

from database import async_session
from database.models import Campaign, SpendEstimate


# ── 한국 디지털 광고 시장 규모 (2025-2026 기준, 연간 KRW) ──
# 출처: 방송통신위원회, KOBACO, 한국디지털광고협회, 메조미디어 보고서
# 총 디지털 광고비: ~8.5조원/년 (2025)
# 검색광고: ~3.0조원 (네이버SA 2.0 + 구글SA 0.8 + 카카오검색 0.2)
# 쇼핑광고: ~0.8조원 (네이버쇼핑 0.5 + 기타 0.3)
# → 검색+쇼핑 제외 시 ~4.7조원/년

_ANNUAL_MARKET_SIZE_KRW: dict[str, int] = {
    # 디스플레이 배너 (~1.6조)
    "naver_da":          500_000_000_000,   # 네이버 DA 5,000억
    "kakao_da":          400_000_000_000,   # 카카오 DA 4,000억 (비즈보드 포함)
    "google_gdn":        500_000_000_000,   # GDN 5,000억
    "mobile_gdn":        200_000_000_000,   # 모바일 GDN 2,000억

    # 동영상 광고 (~1.8조)
    "youtube_ads":     1_200_000_000_000,   # 유튜브 1.2조
    "youtube_surf":      100_000_000_000,   # (유튜브 서프 부분)
    "tiktok_ads":        200_000_000_000,   # 틱톡 2,000억
    "youtube_brand":     300_000_000_000,   # 유튜브 브랜드채널 3,000억

    # 소셜 광고 (~1.3조)
    "facebook":          400_000_000_000,   # 페이스북 4,000억
    "instagram":         700_000_000_000,   # 인스타그램 7,000억

    # 검색 (제외 대상이지만 참고용)
    # "naver_search":   2_000_000_000_000,
    # "google_search_ads": 800_000_000_000,
    # "naver_shopping":    500_000_000_000,
}

# 일간 시장 규모 = 연간 / 365
_DAILY_MARKET_SIZE_KRW = {ch: v // 365 for ch, v in _ANNUAL_MARKET_SIZE_KRW.items()}

# ── 매체 이용량 가중치 (MAU/DAU 기반 도달률) ──
# 각 채널의 실제 광고 도달 비율 대비 우리 수집의 편향 보정
# > 1.0: 우리 수집이 실제보다 과소 → 상향 보정 필요
# < 1.0: 우리 수집이 실제보다 과대 → 하향 보정
_MEDIA_USAGE_WEIGHT: dict[str, float] = {
    "youtube_ads":       1.8,   # 유튜브: MAU 4,600만, 광고 지면 매우 다양, 수집 커버리지 낮음
    "youtube_surf":      1.5,
    "instagram":         1.5,   # 인스타: MAU 2,200만, 스토리/릴스 미수집
    "facebook":          1.2,   # 페이스북: MAU 1,800만, Ad Library로 상당 부분 커버
    "google_gdn":        1.3,   # GDN: 매우 넓은 인벤토리, 언론사 기사면만 수집
    "mobile_gdn":        1.4,
    "naver_da":          1.0,   # 네이버DA: 수집 커버리지 높음 (웹 DA + stealth)
    "kakao_da":          1.2,   # 카카오: 비즈보드 미수집으로 과소
    "tiktok_ads":        1.6,   # 틱톡: Creative Center 20건/회만 수집
}

# 제외 채널 (소형 광고주 다수, 시장 보정 불필요)
EXCLUDED_FROM_MARKET_SCALING = {
    "naver_search", "google_search_ads", "naver_shopping",
}


@dataclass
class MarketScaleResult:
    """채널별 시장 보정 결과."""
    channel: str
    our_daily_spend: float          # 우리 추정 일일 광고비 (KRW)
    market_daily_spend: float       # 시장 일일 광고비 (KRW)
    media_usage_weight: float       # 매체 이용량 가중치
    coverage_ratio: float           # 우리 커버리지 비율
    market_scale_factor: float      # 시장 스케일 팩터 (market / our)
    scaled_daily_spend: float       # 보정 후 일일 추정 (KRW)


async def calculate_market_scale(days: int = 30) -> dict[str, MarketScaleResult]:
    """채널별 시장 보정 계수 산출.

    수집 데이터의 일간 광고비와 시장 규모를 비교하여
    스케일 팩터를 계산. 이를 통해 전체 시장 광고비를 추정.
    """
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    async with async_session() as session:
        # 채널별 우리 수집 일간 평균 광고비
        rows = await session.execute(
            select(
                SpendEstimate.channel,
                func.sum(SpendEstimate.est_daily_spend),
                func.count(func.distinct(SpendEstimate.date)),
            )
            .where(SpendEstimate.date >= since)
            .group_by(SpendEstimate.channel)
        )

        results: dict[str, MarketScaleResult] = {}
        for row in rows.all():
            channel = row[0]
            total_spend = float(row[1] or 0)
            date_count = max(int(row[2] or 1), 1)

            if channel in EXCLUDED_FROM_MARKET_SCALING:
                continue

            our_daily = total_spend / date_count
            market_daily = _DAILY_MARKET_SIZE_KRW.get(channel, 0)
            usage_weight = _MEDIA_USAGE_WEIGHT.get(channel, 1.0)

            if our_daily <= 0 or market_daily <= 0:
                continue

            # 실효 커버리지 = (우리 수집 / 시장 규모) × 매체이용량 보정
            # usage_weight > 1 이면 우리가 과소수집 → 실효 커버리지 낮아짐
            effective_coverage = (our_daily / market_daily) / usage_weight
            coverage = our_daily / market_daily

            # 시장 스케일 팩터 = 시장 규모 / 우리 수집
            # 이 팩터를 곱하면 우리 추정이 시장 규모와 동일
            scale_factor = market_daily / our_daily

            # 보정 후 일간 추정 = 시장 규모 (by construction)
            scaled_daily = market_daily

            results[channel] = MarketScaleResult(
                channel=channel,
                our_daily_spend=our_daily,
                market_daily_spend=market_daily,
                media_usage_weight=usage_weight,
                coverage_ratio=effective_coverage,
                market_scale_factor=scale_factor,
                scaled_daily_spend=scaled_daily,
            )

    return results


async def get_market_summary(days: int = 30) -> dict:
    """전체 시장 광고비 추정 요약.

    Returns:
        {
            "period_days": 30,
            "our_total_daily": 3,760만원/일,
            "market_total_daily": 128억원/일 (검색/쇼핑 제외),
            "coverage_ratio": 0.29%,
            "channels": { ... per-channel details ... },
            "excluded_channels": ["naver_search", ...],
        }
    """
    scale_results = await calculate_market_scale(days=days)

    our_total = sum(r.our_daily_spend for r in scale_results.values())
    market_total = sum(r.market_daily_spend for r in scale_results.values())
    scaled_total = sum(r.scaled_daily_spend for r in scale_results.values())

    channels = {}
    for ch, r in sorted(scale_results.items(), key=lambda x: -x[1].market_daily_spend):
        channels[ch] = {
            "our_daily_krw": round(r.our_daily_spend),
            "market_daily_krw": round(r.market_daily_spend),
            "coverage_pct": round(r.coverage_ratio * 100, 3),
            "media_usage_weight": r.media_usage_weight,
            "scale_factor": round(r.market_scale_factor, 1),
            "scaled_daily_krw": round(r.scaled_daily_spend),
        }

    return {
        "period_days": days,
        "our_total_daily_krw": round(our_total),
        "market_total_daily_krw": round(market_total),
        "scaled_total_daily_krw": round(scaled_total),
        "overall_coverage_pct": round((our_total / market_total * 100) if market_total else 0, 3),
        "channels": channels,
        "excluded_channels": sorted(EXCLUDED_FROM_MARKET_SCALING),
        "note": "검색/쇼핑 채널 제외 (소형 광고주 다수). 디스플레이+동영상+소셜 시장만 보정.",
    }
