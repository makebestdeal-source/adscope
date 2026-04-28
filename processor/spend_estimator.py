"""Spend estimation engine -- 시장 규모 역산(Inverse Sampling) 모델.

【핵심 원리】
크롤러는 전체 시장의 극히 일부만 관찰한다.
따라서 한 번이라도 포착된 광고주는 이미 상당한 예산을 집행 중이다.

    est_daily_spend = CHANNEL_DAILY_REVENUE × (ad_hits / CRAWL_DAILY_CAPACITY)

- CHANNEL_DAILY_REVENUE : 해당 채널의 일 광고 매출 (2024 한국 기준, 원)
- ad_hits               : 해당 날 크롤러가 해당 광고주를 관찰한 횟수
- CRAWL_DAILY_CAPACITY  : 크롤러가 하루 관찰하는 총 광고 슬롯 수 (보정 기준)

CRAWL_DAILY_CAPACITY 보정 원칙
  - 1회 관찰 → 해당 채널의 중·대형 광고주 수준(월 30~70억원) 추정되도록 설정
  - 5회 관찰 → 대형 광고주 수준(월 150~350억원)
  - 10회 이상 → 최상위 광고주 수준
  이 값은 크롤러 실제 처리량이 아니라 '시장점유율 산정 기준'으로 이해할 것.

【채널별 특수 처리】
- youtube_ads / tiktok_ads: 실제 조회수(daily_view_count)가 있으면 CPV 모델 우선 적용
  (Transparency Center 데이터 = 시장 전수에 가까우므로 더 정확)
- 그 외 모든 채널: 역산 모델 단일 적용

【근거 데이터 (2024 Korea)】
- 네이버 SA(검색광고) 연 매출    : 약 3.1조원  (NAVER IR, 서치플랫폼 SA 비중 80% 추정)
- 네이버 GFA(DA)    연 매출      : 약 8,000억원 (서치플랫폼 내 DA 비중 추정)
- 네이버 쇼핑검색광고 연 매출    : 약 1.25조원 (커머스 세그먼트 내 추정)
- 구글 검색광고(Korea) 연 매출  : 약 2조원    (역산 추정, 공식 비공개)
- GDN(Korea) 연 매출            : 약 1조원    (역산 추정)
- 유튜브(Korea) 연 매출         : 약 1.75조원 (글로벌 비중 1.8% 적용)
- 메타(FB+IG Korea) 연 매출     : 약 2조원    (법인 공시 + 직접거래 합산 추정)
- 카카오 모먼트/DA 연 매출      : 약 1.2조원  (카카오 톡비즈 광고형, 2024 IR)
- 틱톡(Korea) 연 매출           : 약 1,500억원 (급성장 중, 업계 추정)

- 네이버 일 검색쿼리 추정       : 약 2~3억 건
- 네이버 GFA 일 노출 추정       : 약 30~50억 회
- 카카오 DA 일 노출 추정        : 약 15~30억 회
- 유튜브(Korea) 일 광고 노출    : 약 7~14억 회
- 메타(Korea) 일 광고 노출      : 약 5~15억 회
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


# ──────────────────────────────────────────────────────────
# 채널별 연간 광고 매출 (원, 2024 Korea 추정)
# ──────────────────────────────────────────────────────────
CHANNEL_ANNUAL_REVENUE: dict[str, int] = {
    "naver_search":      3_100_000_000_000,   # 3.1조  (SA 검색광고)
    "naver_da":            800_000_000_000,   # 8,000억 (GFA DA)
    "naver_shopping":    1_250_000_000_000,   # 1.25조 (쇼핑검색광고)
    "google_search_ads": 2_000_000_000_000,   # 2조    (구글 검색)
    "google_gdn":        1_000_000_000_000,   # 1조    (GDN Korea)
    "youtube_ads":       1_750_000_000_000,   # 1.75조 (유튜브)
    "youtube_surf":        500_000_000_000,   # 5,000억 (서핑형)
    "meta":              2_000_000_000_000,   # 2조    (FB+IG Korea)
    "kakao_da":          1_200_000_000_000,   # 1.2조  (카카오모먼트+DA)
    "tiktok_ads":          150_000_000_000,   # 1,500억 (틱톡)
}

# 일 매출 = 연 매출 / 365
CHANNEL_DAILY_REVENUE: dict[str, float] = {
    k: v / 365.0 for k, v in CHANNEL_ANNUAL_REVENUE.items()
}

# ──────────────────────────────────────────────────────────
# 크롤러 일 관찰 슬롯 수 (시장점유율 산정 기준)
#
# 해석: 이 채널에서 크롤러가 하루 관찰하는 총 광고 슬롯 수.
# 설계 기준: 1회 관찰 → 월 40~70억원 수준 (중·대형 광고주 최소 기준)
#            5회 관찰 → 월 200~350억원 (대형)
#           10회 관찰 → 월 400~700억원 (최상위)
# ──────────────────────────────────────────────────────────
CRAWL_DAILY_CAPACITY: dict[str, int] = {
    "naver_search":      4_000,
    "naver_da":          1_500,
    "naver_shopping":    2_000,
    "google_search_ads": 2_000,
    "google_gdn":        1_500,
    "youtube_ads":       2_000,
    "youtube_surf":      2_000,
    "meta":              3_000,
    "kakao_da":          1_500,
    "tiktok_ads":          800,
}

# ──────────────────────────────────────────────────────────
# 동영상 CPV (실제 조회수 있을 때만 사용)
# ──────────────────────────────────────────────────────────
VIDEO_CPV: dict[str, int] = {
    "youtube_ads":  50,   # 원/조회
    "youtube_surf": 50,
    "tiktok_ads":   40,
}

# ──────────────────────────────────────────────────────────
# 일 최대 상한 (이상치 방지 — 채널 일 매출의 5% 초과 불가)
# 실제로는 시장점유율 5%를 넘는 단일 광고주는 없음
# ──────────────────────────────────────────────────────────
DAILY_CAP: dict[str, float] = {
    k: v * 0.05 for k, v in CHANNEL_DAILY_REVENUE.items()
}

# DB에 facebook/instagram 채널명으로 저장된 것 → meta 베이스 적용
_CHANNEL_ALIAS: dict[str, str] = {
    "facebook":  "meta",
    "instagram": "meta",
}


def _confidence_from_hits(ad_hits: int) -> float:
    """관찰 횟수 → 신뢰도."""
    if ad_hits <= 0:
        return 0.1
    if ad_hits == 1:
        return 0.4
    if ad_hits == 2:
        return 0.5
    if ad_hits == 3:
        return 0.6
    if ad_hits < 7:
        return 0.7
    return 0.8


def _market_share_estimate(
    channel: str,
    ad_hits: int,
) -> tuple[float, dict]:
    """역산 모델 핵심: 채널 일 매출 × 시장점유율.

    market_share = ad_hits / CRAWL_DAILY_CAPACITY[channel]
    est = CHANNEL_DAILY_REVENUE[channel] × market_share
    """
    daily_revenue = CHANNEL_DAILY_REVENUE.get(channel, 1_000_000_000)
    capacity = CRAWL_DAILY_CAPACITY.get(channel, 2_000)

    safe_hits = max(1, ad_hits)  # 0 hit는 이 함수로 오지 않아야 하지만 방어
    market_share = safe_hits / capacity
    est = daily_revenue * market_share
    est = min(est, DAILY_CAP.get(channel, daily_revenue * 0.05))

    factors = {
        "method": "market_share_inverse",
        "channel_daily_revenue": round(daily_revenue),
        "crawl_daily_capacity": capacity,
        "ad_hits": safe_hits,
        "market_share_pct": round(market_share * 100, 4),
    }
    return round(est, 2), factors


def _video_cpv_estimate(
    channel: str,
    ad_hits: int,
    daily_view_count: int,
) -> tuple[float, dict]:
    """동영상 CPV 모델 (실 조회수 보유 시).

    YouTube Transparency Center / TikTok Creative Center 데이터는
    실제 집계값이므로 역산보다 더 정확.
    """
    cpv = VIDEO_CPV.get(channel, 50)
    est = daily_view_count * cpv
    est = min(est, DAILY_CAP.get(channel, 5_000_000_000 * 0.05))

    factors = {
        "method": "video_cpv",
        "cpv": cpv,
        "daily_views": daily_view_count,
        "ad_hits": ad_hits,
    }
    return round(est, 2), factors


# ── Legacy V1 (호환성 유지) ──────────────────────────────
class SpendEstimatorV1:
    """Legacy V1 -- kept for import compatibility."""

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
        est, factors = _market_share_estimate("naver_search", ad_hits=1)
        return SpendEstimation(
            channel="naver_search",
            keyword=keyword,
            advertiser_name=advertiser_name,
            est_daily_spend=est,
            confidence=0.4,
            calculation_method="market_share_inverse",
            factors=factors,
        )


# ── V2 (메인 엔진) ───────────────────────────────────────
class SpendEstimatorV2:
    """채널별 시장 역산 모델.

    estimate()의 ad_data 키:
      - is_inhouse: bool         인하우스 광고 여부
      - keyword: str             키워드
      - advertiser_name: str     광고주명
      - daily_view_count: int    일일 조회수 (YouTube/TikTok CPV 모델용)
      - ad_hits_total: int       캠페인 전체 수집 횟수 (신뢰도 계산)

    frequency_data 키:
      - ad_hits: int             당일 광고 감지 횟수
    """

    _v1 = SpendEstimatorV1()

    def estimate(
        self,
        channel: str,
        ad_data: dict,
        frequency_data: dict | None = None,
    ) -> SpendEstimation:
        freq = frequency_data or {}

        # 인하우스 광고: 0원
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

        ad_hits = max(1, int(freq.get("ad_hits", 1)))
        ad_hits_total = int(ad_data.get("ad_hits_total", ad_hits))
        daily_view_count = int(ad_data.get("daily_view_count") or 0)

        resolved = _CHANNEL_ALIAS.get(channel, channel)

        # ── 동영상: 실 조회수 있으면 CPV 우선 ──
        if resolved in ("youtube_ads", "youtube_surf", "tiktok_ads") and daily_view_count > 0:
            est, factors = _video_cpv_estimate(resolved, ad_hits, daily_view_count)
            method = "video_cpv"
            confidence = 0.75  # 실 조회수 기반 = 높은 신뢰도

        # ── 그 외 모든 채널: 역산 모델 ──
        else:
            est, factors = _market_share_estimate(resolved, ad_hits)
            method = "market_share_inverse"
            confidence = _confidence_from_hits(ad_hits)

        factors["ad_hits_total"] = ad_hits_total

        return SpendEstimation(
            channel=channel,
            keyword=ad_data.get("keyword", ""),
            advertiser_name=ad_data.get("advertiser_name"),
            est_daily_spend=est,
            confidence=confidence,
            calculation_method=method,
            factors=factors,
        )
