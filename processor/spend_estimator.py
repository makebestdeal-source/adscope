"""Spend estimation engine -- Simplified base cost + frequency multiplier model.

단순화된 광고비 추정 로직:
  1. 채널별 캠페인당 일평균 베이스 비용 (고정값)
  2. 감지 횟수(ad_hits)에 따라 50%씩 가산:
     - 1회 = base × 1.0
     - 2회 = base × 1.5
     - 3회 = base × 2.0
     - 4회 = base × 2.5
     - 5회+ = base × 3.0

  공식: daily_spend = BASE_DAILY_COST[channel] × (1 + (min(hits, 5) - 1) × 0.5)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SpendEstimation:
    channel: str
    keyword: str
    advertiser_name: str | None
    est_daily_spend: float
    confidence: float  # 0.0 ~ 1.0
    calculation_method: str
    factors: dict


# ── 채널별 캠페인당 일평균 베이스 비용 (원) ──
# facebook/instagram은 "meta"로 통합 (1,000,000원)
BASE_DAILY_COST: dict[str, int] = {
    "naver_search":      300_000,
    "google_search_ads": 100_000,
    "google_gdn":        400_000,
    "naver_da":        1_000_000,
    "youtube_ads":     3_000_000,
    "youtube_surf":    3_000_000,
    "kakao_da":          800_000,
    "meta":            1_000_000,
    "naver_shopping":    800_000,
    "tiktok_ads":        500_000,
}

# DB에 facebook/instagram 채널명으로 저장된 것 → meta 베이스 적용
_CHANNEL_ALIAS: dict[str, str] = {
    "facebook": "meta",
    "instagram": "meta",
}


def _frequency_multiplier(ad_hits: int) -> float:
    """감지 횟수에 따른 배수: 1회=1.0, 2회=1.5, 3회=2.0, 4회=2.5, 5회+=3.0"""
    if ad_hits <= 0:
        return 0.0
    capped = min(ad_hits, 5)
    return 1.0 + (capped - 1) * 0.5


def _confidence_from_hits(ad_hits: int) -> float:
    """감지 횟수가 많을수록 신뢰도 높음."""
    if ad_hits <= 0:
        return 0.1
    if ad_hits == 1:
        return 0.3
    if ad_hits == 2:
        return 0.4
    if ad_hits == 3:
        return 0.5
    if ad_hits == 4:
        return 0.6
    return 0.7  # 5+


class SpendEstimatorV1:
    """Legacy V1 -- kept for import compatibility but now uses simplified model."""

    def estimate_naver_search(
        self,
        keyword: str = "",
        cpc: int = 0,
        monthly_search_vol: int = 0,
        position: int = 1,
        advertiser_name: str | None = None,
        trend_factor: float = 1.0,
        industry_id: int | None = None,
    ) -> SpendEstimation:
        base = BASE_DAILY_COST["naver_search"]
        return SpendEstimation(
            channel="naver_search",
            keyword=keyword,
            advertiser_name=advertiser_name,
            est_daily_spend=float(base),
            confidence=0.4,
            calculation_method="base_cost_simple",
            factors={"base_daily_cost": base, "ad_hits": 1, "multiplier": 1.0},
        )


class SpendEstimatorV2:
    """Simplified base cost + frequency multiplier engine.

    모든 채널 동일한 로직:
      daily_spend = BASE_DAILY_COST[channel] × frequency_multiplier(ad_hits)
    """

    _v1 = SpendEstimatorV1()

    def estimate(
        self,
        channel: str,
        ad_data: dict,
        frequency_data: dict | None = None,
    ) -> SpendEstimation:
        freq = frequency_data or {}

        # Inhouse ads: 0 won
        if ad_data.get("is_inhouse"):
            return SpendEstimation(
                channel=channel,
                keyword=ad_data.get("keyword", ""),
                advertiser_name=ad_data.get("advertiser_name"),
                est_daily_spend=0.0,
                confidence=0.95,
                calculation_method="inhouse_zero",
                factors={"reason": "inhouse_ad"},
            )

        ad_hits = freq.get("ad_hits", 1)
        resolved = _CHANNEL_ALIAS.get(channel, channel)
        base = BASE_DAILY_COST.get(resolved, 500_000)
        multiplier = _frequency_multiplier(ad_hits)
        est_spend = round(base * multiplier, 2)
        confidence = _confidence_from_hits(ad_hits)

        return SpendEstimation(
            channel=channel,
            keyword=ad_data.get("keyword", ""),
            advertiser_name=ad_data.get("advertiser_name"),
            est_daily_spend=est_spend,
            confidence=confidence,
            calculation_method="base_cost_frequency",
            factors={
                "base_daily_cost": base,
                "ad_hits": ad_hits,
                "frequency_multiplier": multiplier,
            },
        )
