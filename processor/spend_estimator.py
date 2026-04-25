"""Spend estimation engine -- Channel-specific CPC/CPV/slot-based model.

채널별 광고비 추정 로직:

1. 검색 (naver_search, google_search_ads):
   - CPC × (일검색량 × CTR_by_position)
   - 단일 키워드 1슬롯 기준, 캡 적용으로 과대계산 방지

2. DA/배너 (naver_da, kakao_da, google_gdn):
   - CPC(1천원대) × 1구좌당 일클릭
   - 전체 구좌 수로 나눠서 시장 점유 비율 반영
   - 관찰된 슬롯(ad_hits)가 많을수록 더 많은 비중

3. 소셜 (meta):
   - 평균 CPC × 1소재당 일클릭

4. 동영상 (youtube_ads, youtube_surf):
   - 영상 조회수 × CPV 50원
   - 조회수 없으면 보수적 기본값 (1,000조회)

5. 틱톡 (tiktok_ads):
   - 영상 조회수 × CPV 40원
   - 조회수 없으면 보수적 기본값 (500조회)

6. 쇼핑 (naver_shopping):
   - CPC 기반 보수적 추정

과대계산 방지:
 - DA: 전체 구좌수(BANNER_TOTAL_SLOTS)로 나눠서 시장 점유 비율 반영
 - 전체 수집량(ad_hits_total)이 LOW_SAMPLE_THRESHOLD 미만이면
   CONSERVATIVE_MULTIPLIER(0.5) 적용 → 수집 1건이면 보수적으로 절반만 인정
 - 채널별 일일 상한(DAILY_CAP) 으로 이상치 방지
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


# ── 검색 광고 채널별 평균 CPC (원) ──
SEARCH_CPC: dict[str, int] = {
    "naver_search":      1_000,
    "google_search_ads": 800,
}

# ── 검색 광고 포지션별 CTR ──
SEARCH_CTR_BY_POSITION: dict[int, float] = {
    1: 0.040,
    2: 0.020,
    3: 0.015,
    4: 0.010,
}
SEARCH_CTR_DEFAULT = 0.010

# ── 검색 기본 일 검색량 (키워드 볼륨 없을 때) ──
DEFAULT_KEYWORD_SEARCH_VOLUME = 3_000

# ── DA/배너 채널별 평균 CPC (원) ──
BANNER_CPC: dict[str, int] = {
    "naver_da":   1_000,
    "kakao_da":   1_000,
    "google_gdn": 500,    # GDN은 낮음 (CPM 매체 특성)
}

# ── DA/배너: 시장 전체 구좌 수 추정 (과대계산 방지) ──
# 하나의 광고주가 점유할 수 있는 슬롯의 최대치 → ad_hits를 이 값으로 나눔
BANNER_TOTAL_SLOTS: dict[str, int] = {
    "naver_da":   30,   # 네이버 GFA 전체 구좌 추정
    "kakao_da":   25,   # 카카오 DA 전체 구좌 추정
    "google_gdn": 50,   # GDN 지면 多
}

# ── DA/배너: 1구좌당 일일 클릭 추정 ──
# (노출수 × CTR): 네이버 DA 1구좌 노출 4만 × CTR 0.1% = 40클릭
BANNER_DEFAULT_CTR = 0.001

BANNER_DAILY_IMPRESSIONS_PER_SLOT: dict[str, int] = {
    "naver_da":   40_000,
    "kakao_da":   35_000,
    "google_gdn": 40_000,
}

# ── 메타 평균 CPC / 소재당 일일 클릭 기본값 ──
META_CPC = 700
META_DEFAULT_DAILY_CLICKS = 200   # 소재 1개당 기본 200클릭/일

# ── 동영상 CPV (원/조회) ──
VIDEO_CPV: dict[str, int] = {
    "youtube_ads":  50,
    "youtube_surf": 50,
    "tiktok_ads":   40,
}

# ── 동영상: 조회수 없을 때 보수적 기본 일 조회수 ──
VIDEO_DEFAULT_DAILY_VIEWS: dict[str, int] = {
    "youtube_ads":  1_000,
    "youtube_surf": 1_000,
    "tiktok_ads":   500,
}

# ── 쇼핑 ──
SHOPPING_CPC = 500
SHOPPING_DEFAULT_DAILY_CLICKS = 300

# ── 과대계산 방지: 수집량 부족 시 보수적 계수 ──
CONSERVATIVE_MULTIPLIER = 0.5   # 수집 1건 기준 → 50%
LOW_SAMPLE_THRESHOLD = 3        # 이 값 미만이면 보수적 모드

# ── 채널별 일일 최대 상한 (이상치 방지) ──
DAILY_CAP: dict[str, int] = {
    "naver_search":      2_000_000,
    "google_search_ads": 1_500_000,
    "naver_da":          5_000_000,
    "kakao_da":          3_000_000,
    "google_gdn":        3_000_000,
    "meta":              3_000_000,
    "youtube_ads":      10_000_000,
    "youtube_surf":     10_000_000,
    "tiktok_ads":        5_000_000,
    "naver_shopping":    1_000_000,
}

# DB에 facebook/instagram 채널명으로 저장된 것 → meta 베이스 적용
_CHANNEL_ALIAS: dict[str, str] = {
    "facebook": "meta",
    "instagram": "meta",
}


def _confidence_from_hits(ad_hits: int) -> float:
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
    return 0.7


def _conservative_flag(ad_hits_total: int) -> bool:
    """수집량이 임계값 미만이면 True (보수적 계수 적용)."""
    return ad_hits_total < LOW_SAMPLE_THRESHOLD


def _apply_cap(channel: str, value: float) -> float:
    cap = DAILY_CAP.get(channel, 5_000_000)
    return min(value, cap)


def _estimate_search(
    channel: str,
    ad_hits: int,
    ad_hits_total: int,
    avg_position: float,
    keyword_search_volume: int,
) -> tuple[float, float, dict]:
    """검색 광고 일일 추정.

    CPC × (검색량 × CTR_by_position).
    단일 키워드 1슬롯 기준으로 계산 후 cap 적용.
    """
    cpc = SEARCH_CPC.get(channel, 900)
    pos_key = max(1, min(4, round(avg_position)))
    ctr = SEARCH_CTR_BY_POSITION.get(pos_key, SEARCH_CTR_DEFAULT)
    vol = keyword_search_volume if keyword_search_volume > 0 else DEFAULT_KEYWORD_SEARCH_VOLUME

    daily_clicks = vol * ctr
    est = cpc * daily_clicks

    conservative = _conservative_flag(ad_hits_total)
    if conservative:
        est *= CONSERVATIVE_MULTIPLIER

    est = _apply_cap(channel, est)
    confidence = _confidence_from_hits(ad_hits)
    factors = {
        "method": "search_cpc",
        "cpc": cpc,
        "keyword_search_volume": vol,
        "avg_position": avg_position,
        "ctr": ctr,
        "daily_clicks": round(daily_clicks, 1),
        "conservative": conservative,
    }
    return round(est, 2), confidence, factors


def _estimate_banner(
    channel: str,
    ad_hits: int,
    ad_hits_total: int,
    daily_impressions_per_slot: int | None = None,
    placement_traffic_multiplier: float = 1.0,
) -> tuple[float, float, dict]:
    """DA/배너 일일 추정.

    CPC × 1구좌당 일클릭 × (관찰슬롯 / 전체구좌).
    ad_hits = 관찰된 노출 횟수 → 점유 슬롯 수 대리변수.
    """
    cpc = BANNER_CPC.get(channel, 1_000)
    total_slots = BANNER_TOTAL_SLOTS.get(channel, 30)
    base_impressions = (
        daily_impressions_per_slot
        if daily_impressions_per_slot and daily_impressions_per_slot > 0
        else BANNER_DAILY_IMPRESSIONS_PER_SLOT.get(channel, 30_000)
    )
    traffic_multiplier = max(0.1, float(placement_traffic_multiplier or 1.0))
    impressions_per_slot = base_impressions * traffic_multiplier

    # 관찰된 슬롯 수 추정 (ad_hits를 슬롯수로 해석, max 전체구좌)
    observed_slots = min(ad_hits, total_slots)
    slot_ratio = observed_slots / total_slots

    daily_impressions = impressions_per_slot * total_slots * slot_ratio
    daily_clicks = daily_impressions * BANNER_DEFAULT_CTR
    est = cpc * daily_clicks

    conservative = _conservative_flag(ad_hits_total)
    if conservative:
        est *= CONSERVATIVE_MULTIPLIER

    est = _apply_cap(channel, est)
    confidence = _confidence_from_hits(ad_hits)
    factors = {
        "method": "banner_slot",
        "cpc": cpc,
        "total_slots": total_slots,
        "observed_slots": observed_slots,
        "slot_ratio": round(slot_ratio, 3),
        "ctr": BANNER_DEFAULT_CTR,
        "daily_impressions_per_slot": round(impressions_per_slot, 1),
        "placement_traffic_multiplier": round(traffic_multiplier, 3),
        "daily_impressions": round(daily_impressions, 1),
        "daily_clicks": round(daily_clicks, 1),
        "conservative": conservative,
    }
    return round(est, 2), confidence, factors


def _estimate_meta(
    ad_hits: int,
    ad_hits_total: int,
    daily_view_count: int,
) -> tuple[float, float, dict]:
    """메타 일일 추정.

    평균 CPC × 소재당 일일 클릭.
    daily_view_count가 있으면 조회수 기반으로 보완.
    """
    cpc = META_CPC
    daily_clicks = META_DEFAULT_DAILY_CLICKS

    if daily_view_count > 0:
        # 조회수(노출) × CTR로 클릭 추정 (메타 CTR 0.4%)
        daily_clicks = max(daily_clicks, int(daily_view_count * 0.004))

    est = cpc * daily_clicks

    conservative = _conservative_flag(ad_hits_total)
    if conservative:
        est *= CONSERVATIVE_MULTIPLIER

    est = _apply_cap("meta", est)
    confidence = _confidence_from_hits(ad_hits)
    factors = {
        "method": "meta_cpc",
        "cpc": cpc,
        "daily_clicks": daily_clicks,
        "daily_view_count": daily_view_count,
        "conservative": conservative,
    }
    return round(est, 2), confidence, factors


def _estimate_video(
    channel: str,
    ad_hits: int,
    ad_hits_total: int,
    daily_view_count: int,
) -> tuple[float, float, dict]:
    """동영상(YouTube/TikTok) 일일 추정.

    영상 조회수 × CPV.
    조회수 없으면 보수적 기본 조회수 사용.
    """
    cpv = VIDEO_CPV.get(channel, 50)
    default_views = VIDEO_DEFAULT_DAILY_VIEWS.get(channel, 500)

    if daily_view_count > 0:
        views = daily_view_count
        has_view_data = True
    else:
        views = default_views
        has_view_data = False

    est = views * cpv

    # 조회수 데이터 없으면 보수적 계수 추가 적용
    conservative = not has_view_data
    if conservative:
        est *= CONSERVATIVE_MULTIPLIER

    est = _apply_cap(channel, est)
    confidence = 0.5 if has_view_data else 0.3
    confidence = min(confidence, _confidence_from_hits(ad_hits))
    factors = {
        "method": "video_cpv",
        "cpv": cpv,
        "daily_views": views,
        "has_view_data": has_view_data,
        "view_count_based": has_view_data,
        "conservative": conservative,
    }
    return round(est, 2), confidence, factors


def _estimate_shopping(
    ad_hits: int,
    ad_hits_total: int,
) -> tuple[float, float, dict]:
    """네이버 쇼핑 일일 추정 (CPC 기반 보수적)."""
    cpc = SHOPPING_CPC
    daily_clicks = SHOPPING_DEFAULT_DAILY_CLICKS

    est = cpc * daily_clicks

    conservative = _conservative_flag(ad_hits_total)
    if conservative:
        est *= CONSERVATIVE_MULTIPLIER

    est = _apply_cap("naver_shopping", est)
    confidence = _confidence_from_hits(ad_hits)
    factors = {
        "method": "shopping_cpc",
        "cpc": cpc,
        "daily_clicks": daily_clicks,
        "conservative": conservative,
    }
    return round(est, 2), confidence, factors


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
        est, confidence, factors = _estimate_search(
            channel="naver_search",
            ad_hits=1,
            ad_hits_total=1,
            avg_position=float(position),
            keyword_search_volume=monthly_search_vol // 30 if monthly_search_vol else 0,
        )
        return SpendEstimation(
            channel="naver_search",
            keyword=keyword,
            advertiser_name=advertiser_name,
            est_daily_spend=est,
            confidence=confidence,
            calculation_method="search_cpc",
            factors=factors,
        )


class SpendEstimatorV2:
    """Channel-specific CPC/CPV/slot-based spend estimation engine.

    estimate()의 ad_data 키:
      - is_inhouse: bool         인하우스 광고 여부
      - keyword: str             키워드
      - advertiser_name: str     광고주명
      - avg_position: float      평균 노출 순위 (검색 채널)
      - keyword_search_volume: int  일일 검색량 (검색 채널)
      - daily_view_count: int    일일 조회수 (동영상/메타)
      - ad_hits_total: int       이 광고주 전체 수집 횟수 (보수적 모드 판단)

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

        ad_hits = freq.get("ad_hits", 1)
        ad_hits_total = ad_data.get("ad_hits_total", ad_hits)
        avg_position = float(ad_data.get("avg_position") or 2.0)
        keyword_search_volume = int(ad_data.get("keyword_search_volume") or 0)
        daily_view_count = int(ad_data.get("daily_view_count") or 0)
        daily_impressions_per_slot = int(ad_data.get("daily_impressions_per_slot") or 0)
        placement_traffic_multiplier = float(ad_data.get("placement_traffic_multiplier") or 1.0)

        resolved = _CHANNEL_ALIAS.get(channel, channel)

        # ── 채널별 분기 ──
        if resolved in ("naver_search", "google_search_ads"):
            est, conf, factors = _estimate_search(
                channel=resolved,
                ad_hits=ad_hits,
                ad_hits_total=ad_hits_total,
                avg_position=avg_position,
                keyword_search_volume=keyword_search_volume,
            )
            method = "search_cpc"

        elif resolved in ("naver_da", "kakao_da", "google_gdn"):
            est, conf, factors = _estimate_banner(
                channel=resolved,
                ad_hits=ad_hits,
                ad_hits_total=ad_hits_total,
                daily_impressions_per_slot=daily_impressions_per_slot,
                placement_traffic_multiplier=placement_traffic_multiplier,
            )
            method = "banner_slot"

        elif resolved == "meta":
            est, conf, factors = _estimate_meta(
                ad_hits=ad_hits,
                ad_hits_total=ad_hits_total,
                daily_view_count=daily_view_count,
            )
            method = "meta_cpc"

        elif resolved in ("youtube_ads", "youtube_surf", "tiktok_ads"):
            est, conf, factors = _estimate_video(
                channel=resolved,
                ad_hits=ad_hits,
                ad_hits_total=ad_hits_total,
                daily_view_count=daily_view_count,
            )
            method = "video_cpv"

        elif resolved == "naver_shopping":
            est, conf, factors = _estimate_shopping(
                ad_hits=ad_hits,
                ad_hits_total=ad_hits_total,
            )
            method = "shopping_cpc"

        else:
            # 알 수 없는 채널: 보수적 기본값
            est = 200_000.0
            if _conservative_flag(ad_hits_total):
                est *= CONSERVATIVE_MULTIPLIER
            est = min(est, 1_000_000)
            conf = 0.2
            method = "fallback"
            factors = {"channel": resolved, "fallback": True}

        factors["ad_hits"] = ad_hits
        factors["ad_hits_total"] = ad_hits_total

        return SpendEstimation(
            channel=channel,
            keyword=ad_data.get("keyword", ""),
            advertiser_name=ad_data.get("advertiser_name"),
            est_daily_spend=est,
            confidence=conf,
            calculation_method=method,
            factors=factors,
        )
