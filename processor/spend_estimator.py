"""Spend estimation engine -- V1(Naver Search CPC+volume) + V2(CPC frequency-based).

V2 approach (CPC frequency-based):
  All channels except YouTube use CPC (cost per click).
  YouTube uses CPV (cost per view).

  We reverse-engineer daily spend from contact frequency (ad_hits):
    - More ad_hits = advertiser is spending more heavily
    - Map ad_hits to estimated daily clicks, multiply by channel CPC
    - Formula: daily_spend = CPC * estimated_daily_clicks

  CPC values per channel (Korean market, 2025-2026):
    naver_search:     1,000 won
    naver_da:         1,000 won
    kakao_da:         1,000 won
    facebook:           500 won
    instagram:          300 won
    google_gdn:         200 won
    youtube_ads (CPV):   20 won

  ad_hits -> estimated daily clicks mapping:
    1 hit   -> 30~50   (midpoint 40)
    2 hits  -> 80~120  (midpoint 100)
    3 hits  -> 150~250 (midpoint 200)
    4 hits  -> 300~500 (midpoint 400)
    5+ hits -> 500~1000 (midpoint 750)
"""

from __future__ import annotations

from dataclasses import dataclass

from processor.media_pricing import get_industry_cpc


@dataclass
class SpendEstimation:
    channel: str
    keyword: str
    advertiser_name: str | None
    est_daily_spend: float
    confidence: float  # 0.0 ~ 1.0
    calculation_method: str
    factors: dict


class SpendEstimatorV1:
    """Estimate daily ad spend from CPC, search volume, and ad position.

    Calibration note:
    - We assume only a fraction of total search queries become paid-ad clicks.
    - Position controls share within that paid-click pool.
    - This keeps estimates in a realistic range for MVP reporting.
    """

    # Share of *all* daily searches that become paid-ad clicks.
    BASE_PAID_CLICK_SHARE = 0.015  # 1.5%

    # Position share within the paid-click pool (sum ~= 1.0).
    POSITION_CLICK_SHARE = {
        1: 0.24,
        2: 0.18,
        3: 0.13,
        4: 0.10,
        5: 0.08,
        6: 0.07,
        7: 0.06,
        8: 0.05,
        9: 0.05,
        10: 0.04,
    }

    # Industry-level tuning by `industries.id`.
    # 1 금융, 2 의료/뷰티, 3 교육, 4 부동산, 5 법률,
    # 6 쇼핑/커머스, 7 IT/테크, 8 여행, 9 음식/외식, 10 자동차
    INDUSTRY_MULTIPLIER = {
        1: 1.20,
        2: 1.15,
        3: 0.95,
        4: 1.10,
        5: 1.18,
        6: 0.82,
        7: 0.90,
        8: 0.88,
        9: 0.76,
        10: 1.00,
    }

    def estimate_naver_search(
        self,
        keyword: str,
        cpc: int,
        monthly_search_vol: int,
        position: int,
        advertiser_name: str | None = None,
        trend_factor: float = 1.0,
        industry_id: int | None = None,
    ) -> SpendEstimation:
        """Estimate daily spend for a Naver search ad placement."""
        safe_position = min(max(int(position or 10), 1), 10)
        safe_trend = min(max(float(trend_factor), 0.5), 1.5)
        industry_multiplier = self.INDUSTRY_MULTIPLIER.get(int(industry_id), 1.0) if industry_id else 1.0

        daily_search = monthly_search_vol / 30
        paid_click_pool = daily_search * self.BASE_PAID_CLICK_SHARE
        position_share = self.POSITION_CLICK_SHARE.get(safe_position, self.POSITION_CLICK_SHARE[10])
        est_clicks = paid_click_pool * position_share * safe_trend
        est_daily_spend = est_clicks * cpc * industry_multiplier

        volume_score = min(0.35, (monthly_search_vol / 1_000_000) * 0.35)
        position_score = max(0.05, ((11 - safe_position) / 10) * 0.25)
        cpc_score = 0.10 if cpc > 0 else 0.0
        confidence = min(0.85, round(0.25 + volume_score + position_score + cpc_score, 2))

        return SpendEstimation(
            channel="naver_search",
            keyword=keyword,
            advertiser_name=advertiser_name,
            est_daily_spend=round(est_daily_spend, 2),
            confidence=confidence,
            calculation_method="cpc_pool_based",
            factors={
                "cpc": cpc,
                "monthly_search_vol": monthly_search_vol,
                "daily_search": round(daily_search, 2),
                "base_paid_click_share": self.BASE_PAID_CLICK_SHARE,
                "paid_click_pool": round(paid_click_pool, 2),
                "position": safe_position,
                "position_share": position_share,
                "trend_factor": safe_trend,
                "industry_id": industry_id,
                "industry_multiplier": industry_multiplier,
                "est_clicks": round(est_clicks, 2),
            },
        )


class SpendEstimatorV2:
    """CPC/CPV frequency-based multichannel spend estimation engine.

    Reverse-engineers daily ad spend from contact frequency (ad_hits).
    All channels except YouTube use CPC; YouTube uses CPV.

    The model maps ad_hits to estimated daily clicks/views, then
    multiplies by the channel's unit cost to get daily spend.
    """

    # V1 for Naver Search when CPC + search volume data are available
    _v1 = SpendEstimatorV1()

    # -- Channel CPC values (won) --
    # Calibrated from real execution data (미디어광고결과 CSV + 광고비역추산.xlsx)
    _CHANNEL_CPC = {
        "naver_search":      500,   # xlsx: 네이버 CPC 500원
        "naver_da":          800,   # GFA/NOSP avg from real data
        "kakao_da":          600,   # 카카오모먼트 avg
        "facebook":          700,   # xlsx: 메타 CPC 700원
        "instagram":         700,   # 메타 동일 (이전 300 → 700으로 보정)
        "google_gdn":        200,   # 구글 GDN (unchanged)
        "google_search_ads": 800,   # 구글 검색광고 평균 CPC
        "naver_shopping":    300,   # 쇼핑 파워링크 CPC
    }

    # -- YouTube CPV (won) -- 실제 시장 평균 CPV 20원 (보정됨 2/24)
    _YOUTUBE_CPV = 20

    # -- 실집행 데이터 기반 채널별 시장 보정 계수 --
    # 미디어광고결과 CSV 164건 기준 (월 평균 매체비/캠페인수):
    #   META: 264M/31 = 8.5M/월/캠페인 → 283K/일
    #   네이버GFA: 120M/20 = 6.0M → 200K/일
    #   네이버SA: 102M/23 = 4.4M → 148K/일
    #   카카오: 96M/13 = 7.4M → 247K/일
    #   구글: 60M/18 = 3.3M → 111K/일
    #   네이버NOSP: 47M/18 = 2.6M → 87K/일
    # 보정 계수 = 실집행 평균 / (CPC × 기존 40clicks)
    # 시장규모 기반 (2025 리서치애드 + 업계추산):
    #   네이버SA 1.9조 | 유튜브 1.9조 | 카카오 1.5조 | 네이버쇼핑 1.1조
    #   메타 1조 | 구글검색 0.7조 | GDN 0.4조 | 틱톡 0.3조
    _MARKET_CALIBRATION = {
        "naver_search":      3.7,   # 7.4→3.7 하향 (소재수 5,124건으로 과대추정 보정)
        "naver_da":          3.2,   # 6.3→3.2 하향 (소재수 2,905건으로 과대추정 보정)
        "kakao_da":          1.0,   # 10.3→1.0 하향 (수집 부족, 소규모 과대추정 방지)
        "facebook":         10.1,   # 283K / 28K (시장 1조)
        "instagram":        10.1,   # META 동일 적용
        "google_gdn":       13.9,   # 111K / 8K (시장 0.4조)
        "google_search_ads": 9.0,   # 구글검색 (시장 0.7조, CPC 높음)
        "youtube_ads":       8.5,   # 유튜브 (시장 1.9조, CPV 50원)
        "tiktok_ads":        5.0,   # 틱톡 (시장 0.3조)
        "naver_shopping":    5.5,   # 쇼핑검색 (시장 1.1조, CPC 높음)
    }

    # -- 인벤토리 가중치 (트래픽 지표 기반) --
    # 매체별 일간 인벤토리 규모와 광고 밀도를 반영한 가중치.
    # 서프/접촉에서 1회 관측이 실제 시장에서 의미하는 크기가 다름.
    #
    # 네이버검색: 일 3억 쿼리 × 10-15 슬롯 = 30-45억 인벤토리
    # 유튜브: 월 18억시간 시청, 프리롤+미드롤 → 인벤토리 확장성 최대
    # 카카오: DAU 4천만 × 일 70회 앱오픈 = 28억회, 비즈보드 1슬롯 집중
    # 메타(IG): 월 3.8억시간, 피드 4-5포스트당 1광고 + 릴스 급성장
    # GDN: 수백만 제휴사이트, 분산된 배너 → 관측 1회 가치 낮음
    _INVENTORY_WEIGHT = {
        "naver_search":      1.0,   # 기준 (슬롯 많고 쿼리 다양)
        "naver_da":          1.3,   # 타임보드 등 프리미엄 지면
        "kakao_da":          0.4,   # 1.8→0.4 하향 (수집 표본 부족, 소규모 과대추정 방지)
        "google_gdn":        0.6,   # 분산 배너 (관측 1회 가치 낮음)
        "google_search_ads": 0.9,   # 구글 검색 3-4 슬롯
        "youtube_ads":       1.5,   # 인벤토리 확장성 최대
        "youtube_surf":      2.0,   # 영상 서핑 관측 = 실제 인스트림 고가치
        "facebook":          1.2,   # 피드 Ad Load 높음
        "instagram":         1.3,   # 릴스 인벤토리 급성장
        "tiktok_ads":        0.8,   # 소규모 시장
        "naver_shopping":    1.1,   # 쇼핑 검색 의도 높음
    }

    # -- ad_hits -> estimated daily clicks (midpoint of range) --
    # 1 hit -> 30~50 (mid 40), 2 -> 80~120 (mid 100),
    # 3 -> 150~250 (mid 200), 4 -> 300~500 (mid 400),
    # 5+ -> 500~1000 (mid 750)
    # 실집행 보정은 _MARKET_CALIBRATION × _INVENTORY_WEIGHT 계수로 별도 적용
    _HITS_TO_CLICKS = {
        1: 40,
        2: 100,
        3: 200,
        4: 400,
    }
    _HITS_5PLUS_CLICKS = 750

    @classmethod
    def _estimated_daily_clicks(cls, ad_hits: int) -> int:
        """Map observation frequency to estimated daily clicks/views."""
        if ad_hits <= 0:
            return 0
        if ad_hits >= 5:
            return cls._HITS_5PLUS_CLICKS
        return cls._HITS_TO_CLICKS.get(ad_hits, 40)

    @classmethod
    def _confidence_from_hits(cls, ad_hits: int) -> float:
        """Higher ad_hits = higher confidence in the estimate."""
        if ad_hits <= 0:
            return 0.1
        if ad_hits == 1:
            return 0.25
        if ad_hits == 2:
            return 0.35
        if ad_hits == 3:
            return 0.45
        if ad_hits == 4:
            return 0.55
        return 0.65  # 5+

    def _cpc_frequency_spend(
        self, channel: str, ad_hits: int, *, advertiser_id: int = 0, ad_count: int = 1
    ) -> float:
        """Calculate daily spend: CPC * clicks * market_calibration * inventory_weight.

        Uses advertiser_id hash for ±20% variance so same ad_hits yields
        different spend per advertiser.  ad_count scales linearly (more ads = more spend).
        """
        cpc = self._CHANNEL_CPC.get(channel, 500)
        clicks = self._estimated_daily_clicks(ad_hits)
        calibration = self._MARKET_CALIBRATION.get(channel, 1.0)
        inv_weight = self._INVENTORY_WEIGHT.get(channel, 1.0)

        # Advertiser-level variance: hash to 0.80 ~ 1.20
        if advertiser_id:
            h = hash(f"{advertiser_id}_{channel}") % 10000
            variance = 0.80 + (h / 10000) * 0.40  # 0.80 ~ 1.20
        else:
            variance = 1.0

        # Ad count scaling: sqrt to dampen (1→1, 4→2, 9→3, 25→5)
        count_factor = max(1.0, ad_count ** 0.5) if ad_count > 1 else 1.0

        return round(cpc * clicks * calibration * inv_weight * variance * count_factor, 2)

    def _cpv_frequency_spend(self, channel: str, ad_hits: int) -> float:
        """Calculate daily spend for YouTube: CPV * views * inventory_weight."""
        views = self._estimated_daily_clicks(ad_hits)
        inv_weight = self._INVENTORY_WEIGHT.get(channel, 1.0)
        return round(self._YOUTUBE_CPV * views * inv_weight, 2)

    def estimate(
        self,
        channel: str,
        ad_data: dict,
        frequency_data: dict | None = None,
    ) -> SpendEstimation:
        """Route to channel-specific estimator."""
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
                factors={"reason": "inhouse_ad", "inhouse_service": ad_data.get("inhouse_service")},
            )

        if channel == "naver_search":
            return self._estimate_naver_search(ad_data, freq)
        elif channel == "naver_da":
            return self._estimate_naver_da(ad_data, freq)
        elif channel == "kakao_da":
            return self._estimate_kakao(ad_data, freq)
        elif channel == "google_gdn":
            return self._estimate_gdn(ad_data, freq)
        elif channel == "google_search_ads":
            return self._estimate_google_search(ad_data, freq)
        elif channel in ("facebook", "instagram"):
            return self._estimate_meta(ad_data, freq, channel)
        elif channel in ("youtube_ads", "youtube_surf"):
            return self._estimate_youtube(ad_data, freq, channel=channel)
        else:
            return self._fallback(channel, ad_data, freq)

    # -- Naver Search: CPC pool model when data available, CPC frequency fallback --

    def _estimate_naver_search(self, ad: dict, freq: dict) -> SpendEstimation:
        cpc = ad.get("cpc", 0)
        monthly_vol = ad.get("monthly_search_vol", 0)
        position = ad.get("position", 10)
        keyword = ad.get("keyword", "")
        industry_id = ad.get("industry_id")
        ad_hits = freq.get("ad_hits", 1)

        # If we have actual CPC + volume data, use the precise V1 model
        if cpc > 0 and monthly_vol > 0:
            est = self._v1.estimate_naver_search(
                keyword=keyword,
                cpc=cpc,
                monthly_search_vol=monthly_vol,
                position=position,
                advertiser_name=ad.get("advertiser_name"),
                industry_id=industry_id,
            )
            zone = ad.get("position_zone", "unknown")
            zone_multiplier = {"top": 1.0, "middle": 0.7, "bottom": 0.4}.get(zone, 0.7)
            est.est_daily_spend = round(est.est_daily_spend * zone_multiplier, 2)
            est.factors["position_zone"] = zone
            est.factors["zone_multiplier"] = zone_multiplier
            return est

        # Fallback: CPC frequency-based with position weighting + market calibration
        base_spend = self._cpc_frequency_spend(
            "naver_search", ad_hits,
            advertiser_id=ad.get("advertiser_id", 0),
            ad_count=ad.get("ad_count", 1),
        )
        zone = ad.get("position_zone", "unknown")
        zone_multiplier = {"top": 1.0, "middle": 0.7, "bottom": 0.4}.get(zone, 0.7)
        est_spend = round(base_spend * zone_multiplier, 2)

        return SpendEstimation(
            channel="naver_search",
            keyword=keyword,
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=est_spend,
            confidence=self._confidence_from_hits(ad_hits),
            calculation_method="cpc_frequency_calibrated",
            factors={
                "cpc": self._CHANNEL_CPC["naver_search"],
                "ad_hits": ad_hits,
                "estimated_daily_clicks": self._estimated_daily_clicks(ad_hits),
                "market_calibration": self._MARKET_CALIBRATION.get("naver_search", 1.0),
                "inventory_weight": self._INVENTORY_WEIGHT.get("naver_search", 1.0),
                "base_spend": base_spend,
                "position": position,
                "position_zone": zone,
                "zone_multiplier": zone_multiplier,
            },
        )

    # -- Naver DA: CPC frequency-based --

    def _estimate_naver_da(self, ad: dict, freq: dict) -> SpendEstimation:
        ad_hits = freq.get("ad_hits", 1)
        placement = ad.get("ad_placement") or "naver_da_general"
        base_spend = self._cpc_frequency_spend(
            "naver_da", ad_hits,
            advertiser_id=ad.get("advertiser_id", 0),
            ad_count=ad.get("ad_count", 1),
        )

        # Premium placements get higher multiplier
        premium_multiplier = 1.0
        if placement and any(k in placement for k in ("timeboard", "branding")):
            premium_multiplier = 1.5
        elif placement and any(k in placement for k in ("rolling", "smart_channel")):
            premium_multiplier = 1.2

        est_spend = round(base_spend * premium_multiplier, 2)

        return SpendEstimation(
            channel="naver_da",
            keyword=ad.get("keyword", ""),
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=est_spend,
            confidence=self._confidence_from_hits(ad_hits),
            calculation_method="cpc_frequency_calibrated",
            factors={
                "cpc": self._CHANNEL_CPC["naver_da"],
                "placement": placement,
                "ad_hits": ad_hits,
                "estimated_daily_clicks": self._estimated_daily_clicks(ad_hits),
                "market_calibration": self._MARKET_CALIBRATION.get("naver_da", 1.0),
                "inventory_weight": self._INVENTORY_WEIGHT.get("naver_da", 1.0),
                "base_spend": base_spend,
                "premium_multiplier": premium_multiplier,
            },
        )

    # -- Kakao DA: CPC frequency-based --

    def _estimate_kakao(self, ad: dict, freq: dict) -> SpendEstimation:
        ad_hits = freq.get("ad_hits", 1)
        placement = ad.get("ad_placement") or "kakao_content_da"
        base_spend = self._cpc_frequency_spend(
            "kakao_da", ad_hits,
            advertiser_id=ad.get("advertiser_id", 0),
            ad_count=ad.get("ad_count", 1),
        )

        # Bizboard premium
        premium_multiplier = 1.3 if "bizboard" in placement else 1.0
        est_spend = round(base_spend * premium_multiplier, 2)

        return SpendEstimation(
            channel="kakao_da",
            keyword=ad.get("keyword", ""),
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=est_spend,
            confidence=self._confidence_from_hits(ad_hits),
            calculation_method="cpc_frequency_calibrated",
            factors={
                "cpc": self._CHANNEL_CPC["kakao_da"],
                "placement": placement,
                "ad_hits": ad_hits,
                "estimated_daily_clicks": self._estimated_daily_clicks(ad_hits),
                "market_calibration": self._MARKET_CALIBRATION.get("kakao_da", 1.0),
                "inventory_weight": self._INVENTORY_WEIGHT.get("kakao_da", 1.0),
                "base_spend": base_spend,
                "premium_multiplier": premium_multiplier,
            },
        )

    # -- Google GDN: CPC frequency-based --

    def _estimate_gdn(self, ad: dict, freq: dict) -> SpendEstimation:
        ad_hits = freq.get("ad_hits", 1)
        industry = ad.get("industry", "")
        base_spend = self._cpc_frequency_spend(
            "google_gdn", ad_hits,
            advertiser_id=ad.get("advertiser_id", 0),
            ad_count=ad.get("ad_count", 1),
        )

        # Industry weighting: adjust by industry CPC relative to channel CPC
        channel_cpc = self._CHANNEL_CPC["google_gdn"]
        industry_cpc = get_industry_cpc(industry, channel="google_gdn") if industry else channel_cpc
        industry_ratio = min(2.0, max(0.5, industry_cpc / channel_cpc))
        est_spend = round(base_spend * industry_ratio, 2)

        return SpendEstimation(
            channel="google_gdn",
            keyword=ad.get("keyword", ""),
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=est_spend,
            confidence=self._confidence_from_hits(ad_hits),
            calculation_method="cpc_frequency_calibrated",
            factors={
                "cpc": channel_cpc,
                "industry": industry,
                "industry_cpc": industry_cpc,
                "industry_ratio": industry_ratio,
                "ad_hits": ad_hits,
                "estimated_daily_clicks": self._estimated_daily_clicks(ad_hits),
                "market_calibration": self._MARKET_CALIBRATION.get("google_gdn", 1.0),
                "inventory_weight": self._INVENTORY_WEIGHT.get("google_gdn", 1.0),
                "base_spend": base_spend,
            },
        )

    # -- Google Search Ads: CPC catalog-based (Transparency Center) --

    def _estimate_google_search(self, ad: dict, freq: dict) -> SpendEstimation:
        """구글 검색광고 추정 -- 카탈로그 기반 (투명성센터).

        구글 검색광고 CPC: 평균 500~2000원 (업종별 차이 큼)
        """
        google_search_cpc = 800  # 평균 CPC (원)
        calibration = self._MARKET_CALIBRATION.get("google_search_ads", 9.0)
        inv_weight = self._INVENTORY_WEIGHT.get("google_search_ads", 0.9)

        # 카탈로그 수집이므로 frequency 기반 대신 활성일수 기반 추정
        active_days = freq.get("active_days", 1)
        daily_clicks_est = 50  # 검색광고 기본 일 클릭 추정
        est_spend = round(google_search_cpc * daily_clicks_est * calibration * inv_weight, 2)

        return SpendEstimation(
            channel="google_search_ads",
            keyword=ad.get("keyword", ""),
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=est_spend,
            confidence=0.35,
            calculation_method="cpc_catalog_google_search",
            factors={
                "cpc": google_search_cpc,
                "daily_clicks_est": daily_clicks_est,
                "market_calibration": calibration,
                "inventory_weight": inv_weight,
                "active_days": active_days,
            },
        )

    # -- Meta (Facebook / Instagram) --
    # Contact mode (is_contact=True): CPC frequency-based
    # Catalog mode (is_contact=False): no spend estimation possible

    def _estimate_meta(self, ad: dict, freq: dict, channel: str = "facebook") -> SpendEstimation:
        is_contact = ad.get("is_contact", False)
        ad_hits = freq.get("ad_hits", 1)

        if not is_contact:
            # Catalog (library scraping): estimate from creative count + format
            from processor.spend_reverse_estimator import estimate_catalog_daily_spend
            creative_count = ad.get("creative_count", 1)
            creative_format = ad.get("creative_format", "default")
            active_days = ad.get("active_days", 30)
            has_multi = ad.get("has_multiple_formats", False)

            rev_est = estimate_catalog_daily_spend(
                channel=channel,
                creative_count=max(1, creative_count),
                creative_format=creative_format,
                active_days=active_days,
                has_multiple_formats=has_multi,
            )
            return SpendEstimation(
                channel=channel,
                keyword=ad.get("keyword", ""),
                advertiser_name=ad.get("advertiser_name"),
                est_daily_spend=rev_est.est_monthly_media_cost / 30,
                confidence=rev_est.confidence,
                calculation_method="catalog_creative_reverse",
                factors=rev_est.factors,
            )

        base_spend = self._cpc_frequency_spend(
            channel, ad_hits,
            advertiser_id=ad.get("advertiser_id", 0),
            ad_count=ad.get("ad_count", 1),
        )
        return SpendEstimation(
            channel=channel,
            keyword=ad.get("keyword", ""),
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=base_spend,
            confidence=self._confidence_from_hits(ad_hits),
            calculation_method="cpc_frequency_calibrated",
            factors={
                "cpc": self._CHANNEL_CPC.get(channel, 700),
                "ad_hits": ad_hits,
                "estimated_daily_clicks": self._estimated_daily_clicks(ad_hits),
                "market_calibration": self._MARKET_CALIBRATION.get(channel, 1.0),
                "inventory_weight": self._INVENTORY_WEIGHT.get(channel, 1.0),
                "base_spend": base_spend,
            },
        )

    # -- YouTube: CPV x actual view_count (from Ads Transparency Center) --

    def _estimate_youtube(self, ad: dict, freq: dict, channel: str = "youtube_ads") -> SpendEstimation:
        view_count = ad.get("view_count") or 0
        inv_weight = self._INVENTORY_WEIGHT.get(channel, 1.5)
        calibration = self._MARKET_CALIBRATION.get("youtube_ads", 1.0)

        # youtube_surf: 접촉 기반 (실제 인스트림 관측)
        if channel == "youtube_surf":
            ad_hits = freq.get("ad_hits", 1)
            base_spend = self._cpv_frequency_spend(channel, ad_hits)
            est_spend = round(base_spend * calibration, 2)
            return SpendEstimation(
                channel=channel,
                keyword=ad.get("keyword", ""),
                advertiser_name=ad.get("advertiser_name"),
                est_daily_spend=est_spend,
                confidence=self._confidence_from_hits(ad_hits),
                calculation_method="cpv_frequency_calibrated",
                factors={
                    "cpv": self._YOUTUBE_CPV,
                    "ad_hits": ad_hits,
                    "estimated_daily_views": self._estimated_daily_clicks(ad_hits),
                    "market_calibration": calibration,
                    "inventory_weight": inv_weight,
                    "base_spend": base_spend,
                },
            )

        # youtube_ads: 조회수 기반 (view_count = 일일 추정 유료 조회수)
        # calibration/inv_weight 미적용: view_count가 이미 일일 유료 조회수로 변환된 직접 데이터
        if view_count > 0:
            est_spend = round(self._YOUTUBE_CPV * view_count, 2)
            return SpendEstimation(
                channel="youtube_ads",
                keyword=ad.get("keyword", ""),
                advertiser_name=ad.get("advertiser_name"),
                est_daily_spend=est_spend,
                confidence=0.55,
                calculation_method="cpv_view_count",
                factors={
                    "cpv": self._YOUTUBE_CPV,
                    "view_count": view_count,
                },
            )

        # No view count: estimate from creative count + format
        from processor.spend_reverse_estimator import estimate_catalog_daily_spend
        creative_count = ad.get("creative_count", 1)
        active_days = ad.get("active_days", 30)
        rev_est = estimate_catalog_daily_spend(
            channel="youtube_ads",
            creative_count=max(1, creative_count),
            creative_format="video",
            active_days=active_days,
        )
        return SpendEstimation(
            channel="youtube_ads",
            keyword=ad.get("keyword", ""),
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=rev_est.est_monthly_media_cost / 30,
            confidence=rev_est.confidence,
            calculation_method="catalog_creative_reverse",
            factors=rev_est.factors,
        )

    # -- Unsupported channel fallback --

    def _fallback(self, channel: str, ad: dict, freq: dict) -> SpendEstimation:
        ad_hits = freq.get("ad_hits", 0)
        if ad_hits > 0:
            est_spend = self._cpc_frequency_spend(
                channel, ad_hits,
                advertiser_id=ad.get("advertiser_id", 0),
                ad_count=ad.get("ad_count", 1),
            )
        else:
            est_spend = 0.0
        return SpendEstimation(
            channel=channel,
            keyword=ad.get("keyword", ""),
            advertiser_name=ad.get("advertiser_name"),
            est_daily_spend=est_spend,
            confidence=0.1,
            calculation_method="cpc_frequency_based",
            factors={
                "cpc": self._CHANNEL_CPC.get(channel, 500),
                "ad_hits": ad_hits,
                "estimated_daily_clicks": self._estimated_daily_clicks(ad_hits),
            },
        )
