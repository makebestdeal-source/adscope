"""Spend reverse estimator -- derives ad spend from meta signals and real execution benchmarks.

Two independent estimation methods:

1. **Meta Signal Reverse Estimation** (from xlsx coefficients):
   Observed search queries / channel views / social engagement -> reverse to spend.
   Coefficients per 1 KRW of ad spend:
     - Naver: search_query=0.07, channel_views=0.03, social_engagement=0.04
   Reverse: spend = observed_signal_delta / coefficient

2. **Real Execution Data Calibration** (from media agency CSV):
   Actual media cost ratios (% of total ad spend that goes to the platform):
     - META (FB/IG): 80.1% -> total_multiplier = 1.248
     - Naver SA:     86.6% -> total_multiplier = 1.155
     - Naver GFA:    86.0% -> total_multiplier = 1.163
     - Kakao:        84.6% -> total_multiplier = 1.182
     - Google:       84.5% -> total_multiplier = 1.183

   Agency fee rates (avg):
     - META: 14.7%, Naver SA: 9.1%, Naver GFA: 8.8%
     - Kakao: 10.4%, Google: 18.1%

3. **Catalog Channel Estimation** (for FB/IG/YT where no contact frequency):
   Uses ad library data (creative count, active days, format) to infer a spend range.
"""

from __future__ import annotations

from dataclasses import dataclass

from processor.channel_utils import (
    CHANNEL_TO_BENCHMARK_KEY as _CHANNEL_TO_BENCHMARK,
    get_benchmark_key,
)


# ── Meta Signal Coefficients (per 1 KRW ad spend) ──
# Source: 광고비역추산.xlsx - these represent the incremental signal
# generated per 1 won of ad spend on each platform
META_SIGNAL_COEFFICIENTS = {
    "naver": {
        "search_query": 0.07,       # 1원 -> 0.07 search queries
        "channel_views": 0.03,      # 1원 -> 0.03 organic channel views
        "social_engagement": 0.04,  # 1원 -> 0.04 social engagements
    },
    "youtube": {
        "cpc": 100,     # CPC 100원
        "cpv": 50,      # CPV 50원
        "vtr": 0.25,    # View-through rate 25%
    },
    "meta": {
        "cpc": 700,     # CPC 700원
        "ctr": 0.004,   # CTR 0.4%
    },
}

# ── Real Execution Benchmarks (from media agency CSV) ──
# media_cost_ratio: what % of total ad spend goes to the platform
# agency_fee_rate: average agency commission rate
# total_multiplier: 1 / media_cost_ratio (to convert platform cost to total spend)
REAL_EXECUTION_BENCHMARKS = {
    "meta": {
        "media_cost_ratio": 0.801,
        "agency_fee_rate": 0.147,
        "total_multiplier": 1.248,
        "avg_campaign_spend": 10_633_550,  # per campaign line avg
        "sample_count": 31,
    },
    "naver_sa": {
        "media_cost_ratio": 0.866,
        "agency_fee_rate": 0.091,
        "total_multiplier": 1.155,
        "avg_campaign_spend": 5_141_327,
        "sample_count": 23,
    },
    "naver_gfa": {
        "media_cost_ratio": 0.860,
        "agency_fee_rate": 0.088,
        "total_multiplier": 1.163,
        "avg_campaign_spend": 6_984_543,
        "sample_count": 20,
    },
    "naver_nosp": {
        "media_cost_ratio": 0.850,
        "agency_fee_rate": 0.098,
        "total_multiplier": 1.176,
        "avg_campaign_spend": 3_058_293,
        "sample_count": 18,
    },
    "kakao": {
        "media_cost_ratio": 0.846,
        "agency_fee_rate": 0.104,
        "total_multiplier": 1.182,
        "avg_campaign_spend": 8_765_233,
        "sample_count": 13,
    },
    "google": {
        "media_cost_ratio": 0.845,
        "agency_fee_rate": 0.181,
        "total_multiplier": 1.183,
        "avg_campaign_spend": 3_930_921,
        "sample_count": 18,
    },
}

# ── Catalog Channel Spend Estimation Coefficients ──
# For FB/IG/YT catalog (ad library scraping, no contact frequency)
# Base daily spend estimates by creative format and active status
CATALOG_BASE_DAILY = {
    "facebook": {
        "image": 150_000,     # 이미지 소재 하루 15만원
        "video": 300_000,     # 동영상 소재 하루 30만원
        "carousel": 200_000,  # 캐러셀 하루 20만원
        "default": 100_000,   # 기본 하루 10만원
    },
    "instagram": {
        "image": 120_000,
        "video": 250_000,
        "carousel": 180_000,
        "default": 80_000,
    },
    "youtube_ads": {
        "video": 500_000,     # 유튜브 동영상 하루 50만원
        "default": 200_000,
    },
}

# Creative count multipliers (more creatives = higher spend)
CREATIVE_COUNT_MULTIPLIERS = {
    1: 0.5,    # 소재 1개: 소규모 캠페인
    2: 0.7,
    3: 1.0,    # 소재 3개: 표준 캠페인
    5: 1.3,
    10: 1.8,   # 소재 10개 이상: 대형 캠페인
    20: 2.5,
}


@dataclass
class ReverseEstimation:
    """Result of reverse spend estimation."""
    channel: str
    method: str                    # "meta_signal_reverse" | "catalog_creative" | "hybrid"
    est_monthly_spend: float       # estimated monthly total spend (수주액)
    est_monthly_media_cost: float  # estimated monthly media cost (매체비)
    confidence: float              # 0.0 ~ 1.0
    factors: dict


def _creative_count_multiplier(count: int) -> float:
    """Interpolate creative count to spend multiplier."""
    if count <= 0:
        return 0.3
    sorted_thresholds = sorted(CREATIVE_COUNT_MULTIPLIERS.items())
    for i, (threshold, mult) in enumerate(sorted_thresholds):
        if count <= threshold:
            if i == 0:
                return mult
            prev_t, prev_m = sorted_thresholds[i - 1]
            ratio = (count - prev_t) / (threshold - prev_t)
            return prev_m + ratio * (mult - prev_m)
    return sorted_thresholds[-1][1]  # max


def estimate_from_meta_signals(
    advertiser_name: str,
    search_query_delta: float = 0,
    channel_views_delta: float = 0,
    social_engagement_delta: float = 0,
    period_days: int = 30,
) -> ReverseEstimation | None:
    """Reverse-estimate Naver ad spend from observed meta signal deltas.

    The coefficients represent signal-per-won:
      - search_query_delta / 0.07 = estimated spend
      - channel_views_delta / 0.03 = estimated spend
      - social_engagement_delta / 0.04 = estimated spend

    Takes weighted average of available signals.
    """
    coeffs = META_SIGNAL_COEFFICIENTS["naver"]
    estimates = []
    weights = []

    if search_query_delta > 0:
        est = search_query_delta / coeffs["search_query"]
        estimates.append(est)
        weights.append(0.5)  # search queries are most reliable

    if channel_views_delta > 0:
        est = channel_views_delta / coeffs["channel_views"]
        estimates.append(est)
        weights.append(0.3)

    if social_engagement_delta > 0:
        est = social_engagement_delta / coeffs["social_engagement"]
        estimates.append(est)
        weights.append(0.2)

    if not estimates:
        return None

    # Weighted average
    total_weight = sum(weights)
    weighted_spend = sum(e * w for e, w in zip(estimates, weights)) / total_weight

    # Scale to monthly if period differs
    monthly_spend = weighted_spend * (30 / period_days)

    # Media cost (Naver SA/GFA average ~86%)
    media_cost = monthly_spend * 0.86

    # Confidence based on number of signals available
    signal_count = len(estimates)
    confidence = min(0.7, 0.3 + signal_count * 0.15)

    return ReverseEstimation(
        channel="naver_combined",
        method="meta_signal_reverse",
        est_monthly_spend=round(monthly_spend, 0),
        est_monthly_media_cost=round(media_cost, 0),
        confidence=confidence,
        factors={
            "search_query_delta": search_query_delta,
            "channel_views_delta": channel_views_delta,
            "social_engagement_delta": social_engagement_delta,
            "coefficients": coeffs,
            "signal_count": signal_count,
            "period_days": period_days,
            "individual_estimates": [round(e) for e in estimates],
        },
    )


def estimate_catalog_daily_spend(
    channel: str,
    creative_count: int = 1,
    creative_format: str = "default",
    active_days: int = 30,
    has_multiple_formats: bool = False,
) -> ReverseEstimation:
    """Estimate daily spend for catalog channels (FB/IG/YT) from ad library data.

    Uses creative count, format, and active duration as proxy signals.
    """
    channel_pricing = CATALOG_BASE_DAILY.get(channel, CATALOG_BASE_DAILY.get("facebook", {}))
    base_daily = channel_pricing.get(creative_format, channel_pricing.get("default", 100_000))

    # Creative count multiplier
    cc_mult = _creative_count_multiplier(creative_count)

    # Duration discount (longer campaigns tend to have lower daily spend)
    if active_days > 60:
        duration_mult = 0.8
    elif active_days > 30:
        duration_mult = 0.9
    else:
        duration_mult = 1.0

    # Multiple format bonus
    format_mult = 1.2 if has_multiple_formats else 1.0

    est_daily = round(base_daily * cc_mult * duration_mult * format_mult)

    # Monthly estimate
    est_monthly_media = est_daily * 30

    # Total spend using real execution benchmark
    benchmark_key = get_benchmark_key(channel)
    benchmark = REAL_EXECUTION_BENCHMARKS.get(benchmark_key, {})
    total_mult = benchmark.get("total_multiplier", 1.25)
    est_monthly_total = round(est_monthly_media * total_mult)

    # Confidence: low because catalog estimation is inherently imprecise
    confidence = 0.25
    if creative_count >= 3:
        confidence += 0.05
    if active_days >= 14:
        confidence += 0.05

    return ReverseEstimation(
        channel=channel,
        method="catalog_creative",
        est_monthly_spend=est_monthly_total,
        est_monthly_media_cost=est_monthly_media,
        confidence=confidence,
        factors={
            "base_daily": base_daily,
            "creative_count": creative_count,
            "creative_format": creative_format,
            "cc_multiplier": cc_mult,
            "duration_multiplier": duration_mult,
            "format_multiplier": format_mult,
            "est_daily_media_cost": est_daily,
            "total_multiplier": total_mult,
            "active_days": active_days,
            "benchmark_source": benchmark_key,
        },
    )


def get_total_spend_multiplier(channel: str) -> float:
    """Get the media-cost-to-total-spend multiplier for a channel.

    Example: META media cost = 100M -> total spend = 100M * 1.248 = 124.8M
    The difference covers agency fees, net revenue, etc.
    """
    benchmark_key = get_benchmark_key(channel)
    benchmark = REAL_EXECUTION_BENCHMARKS.get(benchmark_key, {})
    return benchmark.get("total_multiplier", 1.20)


def calibrate_media_spend(channel: str, est_media_cost: float) -> float:
    """Convert estimated platform media cost to total advertiser spend (수주액).

    Uses real execution data ratios.
    """
    multiplier = get_total_spend_multiplier(channel)
    return round(est_media_cost * multiplier, 0)


# ── SerpApi 기반 Google Ads 크리에이티브 추정 ──

# Google Ads Transparency Center 크리에이티브 → 일 추정 광고비
# 기준: 크리에이티브 1건이 활성 = 최소 일일 예산 존재
# 텍스트: 검색 → CPC 500원 × 100클릭 = 50,000원/일
# 이미지: GDN → CPM 2,000원 × 50imp/1000 = 100원/일... 실제는 더 큼
# 영상: YouTube → CPV 50원 × 1,000뷰 = 50,000원/일
_SERPAPI_DAILY_PER_CREATIVE = {
    "text": 80_000,    # 검색광고 CPC 기반
    "image": 50_000,   # GDN/디스플레이
    "video": 120_000,  # YouTube 프리롤/인스트림
}


def estimate_from_serpapi(
    advertiser_name: str,
    serpapi_creatives: list[dict],
) -> ReverseEstimation | None:
    """SerpApi Google Ads Transparency 크리에이티브로 광고비 추정.

    Args:
        advertiser_name: 광고주명
        serpapi_creatives: serpapi_ads 테이블 rows

    Returns:
        ReverseEstimation or None
    """
    if not serpapi_creatives:
        return None

    total_daily = 0
    format_counts = {"text": 0, "image": 0, "video": 0}

    for c in serpapi_creatives:
        fmt = c.get("format", "text")
        if fmt not in format_counts:
            fmt = "text"
        format_counts[fmt] += 1
        total_daily += _SERPAPI_DAILY_PER_CREATIVE.get(fmt, 50_000)

    # 크리에이티브 수가 많으면 대형 광고주 → 일부 비활성 감안 50% 할인
    if len(serpapi_creatives) > 50:
        total_daily = int(total_daily * 0.5)
    elif len(serpapi_creatives) > 20:
        total_daily = int(total_daily * 0.7)

    est_monthly = total_daily * 30
    est_media = int(est_monthly / 1.183)  # Google total_multiplier

    return ReverseEstimation(
        channel="google_gdn",
        method="serpapi_transparency",
        est_monthly_spend=est_monthly,
        est_monthly_media_cost=est_media,
        confidence=0.35,
        factors={
            "creative_count": len(serpapi_creatives),
            "format_counts": format_counts,
            "est_daily_total": total_daily,
            "source": "serpapi_google_ads_transparency",
        },
    )
