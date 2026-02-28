"""Pydantic 스키마 -- API 요청/응답 직렬화.

금액 필드 네이밍 규칙:
  - est_daily_spend: 일별 추정 매체비 (KRW). SUM(est_daily_spend)으로 기간합 산출.
  - total_est_spend: 캠페인 누적 추정 매체비 (KRW). Campaign 테이블 컬럼 직접 참조.
  - est_spend: 특정 그룹(채널/카테고리)의 기간 내 추정 매체비 합계 (KRW).
  - total_spend: 조회 기간 내 SUM(est_daily_spend). 매체비 기준 (KRW).
  - est_ad_spend: 광고주 단위 추정 매체비 (KRW).
  - media_spend: 순수 매체비 (KRW). 대행수수료 미포함.
  - est_total_spend / est_total_cost: 매체비 + 대행수수료 = 수주액 추정 (KRW).
  - est_monthly_spend: 월간 총 수주액 추정 (매체비+마진, KRW).
  - est_monthly_media_cost: 월간 순수 매체비 추정 (KRW).
  모든 금액 단위: 원(KRW), 소수점 이하 반올림.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ── Industry ──
class IndustryBase(BaseModel):
    name: str
    avg_cpc_min: int | None = Field(default=None, description="업종 평균 CPC 하한 (KRW)")
    avg_cpc_max: int | None = Field(default=None, description="업종 평균 CPC 상한 (KRW)")


class IndustryOut(IndustryBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# ── Keyword ──
class KeywordBase(BaseModel):
    keyword: str
    industry_id: int
    naver_cpc: int | None = Field(default=None, description="네이버 키워드 CPC 단가 (KRW)")
    monthly_search_vol: int | None = None


class KeywordOut(KeywordBase):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


# ── Persona ──
class PersonaOut(BaseModel):
    id: int
    code: str
    age_group: str | None
    gender: str | None
    login_type: str
    description: str | None
    targeting_category: str | None = None
    is_clean: bool = False
    primary_device: str | None = None
    model_config = ConfigDict(from_attributes=True)


# ── AdSnapshot ──
class AdSnapshotOut(BaseModel):
    id: int
    keyword_id: int
    persona_id: int
    device: str
    channel: str
    captured_at: datetime
    ad_count: int
    screenshot_path: str | None = None
    model_config = ConfigDict(from_attributes=True)


# ── AdDetail ──
class AdDetailOut(BaseModel):
    id: int
    snapshot_id: int
    advertiser_name_raw: str | None
    brand: str | None
    ad_text: str | None
    ad_description: str | None
    position: int | None
    url: str | None
    display_url: str | None
    ad_type: str | None
    verification_status: str | None
    verification_source: str | None
    product_name: str | None = None
    product_category: str | None = None
    product_category_id: int | None = None
    ad_placement: str | None = None
    promotion_type: str | None = None
    creative_image_path: str | None = None
    screenshot_path: str | None = None
    model_config = ConfigDict(from_attributes=True)


class AdSnapshotWithDetails(AdSnapshotOut):
    details: list[AdDetailOut] = []


# ── AdDetail (Phase 3 확장) ──
class AdDetailFullOut(AdDetailOut):
    position_zone: str | None = None
    is_inhouse: bool | None = None
    is_retargeted: bool | None = None
    retargeting_network: str | None = None
    ad_marker_type: str | None = None


# ── Advertiser ──
class AdvertiserOut(BaseModel):
    id: int
    name: str
    industry_id: int | None
    brand_name: str | None
    website: str | None
    model_config = ConfigDict(from_attributes=True)


class AdvertiserTreeOut(AdvertiserOut):
    parent_id: int | None = None
    advertiser_type: str | None = None
    aliases: list[str] | None = None
    official_channels: dict[str, str] | None = None
    children: list["AdvertiserTreeOut"] = []


# ── 광고주 검색 응답 ──
class AdvertiserSearchResult(BaseModel):
    id: int
    name: str
    industry_id: int | None = None
    brand_name: str | None = None
    website: str | None = None
    official_channels: dict[str, str] | None = None
    advertiser_type: str | None = None
    parent_id: int | None = None
    match_type: str = "exact"  # exact, alias, fuzzy
    model_config = ConfigDict(from_attributes=True)


# ── 광고비 리포트 ──
class ChannelSpendSummary(BaseModel):
    """채널별 광고비 요약. 광고주 리포트 내 채널 분류용."""
    channel: str
    est_spend: float = Field(
        description="해당 채널의 조회 기간 내 추정 매체비 합계 (KRW). SUM(est_daily_spend)."
    )
    ad_count: int
    position_distribution: dict[str, int] = {}
    top_keywords: list[str] = []
    is_active: bool = True


class DailySpendPoint(BaseModel):
    """일별 광고비 시계열 포인트."""
    date: str
    spend: float = Field(description="해당일 추정 매체비 (KRW)")


class AdvertiserSpendReport(BaseModel):
    """광고주 단위 광고비 리포트 응답."""
    advertiser: AdvertiserOut
    total_est_spend: float = Field(
        description="조회 기간 내 전 채널 추정 매체비 합계 (KRW). SUM(est_daily_spend) over all channels."
    )
    period: dict[str, str] = Field(description="조회 기간 {start, end} ISO format")
    by_channel: list[ChannelSpendSummary]
    daily_trend: list[DailySpendPoint]
    active_campaigns: list["CampaignOut"] = []


# ── Campaign ──
class CampaignOut(BaseModel):
    """캠페인 기본 정보."""
    id: int
    advertiser_id: int
    channel: str
    first_seen: datetime
    last_seen: datetime
    is_active: bool
    total_est_spend: float = Field(
        description="캠페인 누적 추정 매체비 (KRW). Campaign 테이블 컬럼. 캠페인 전 기간 합산."
    )
    snapshot_count: int
    model_config = ConfigDict(from_attributes=True)


class CampaignDetailOut(CampaignOut):
    campaign_name: str | None = None
    objective: str | None = None
    product_service: str | None = None
    promotion_copy: str | None = None
    model_info: str | None = None
    target_keywords: dict | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    creative_ids: list[int] | None = None
    status: str | None = None
    enrichment_status: str | None = None


class CampaignUpdateIn(BaseModel):
    campaign_name: str | None = None
    objective: str | None = None
    product_service: str | None = None
    promotion_copy: str | None = None
    model_info: str | None = None
    target_keywords: dict | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: str | None = None


class JourneyEventOut(BaseModel):
    ts: datetime
    stage: str
    source: str
    metric: str
    value: float
    dims: dict | None = None
    model_config = ConfigDict(from_attributes=True)


class CampaignLiftOut(BaseModel):
    campaign_id: int
    query_lift_pct: float | None = None
    social_lift_pct: float | None = None
    sales_lift_pct: float | None = None
    pre_query_avg: float | None = None
    post_query_avg: float | None = None
    pre_social_avg: float | None = None
    post_social_avg: float | None = None
    pre_sales_avg: float | None = None
    post_sales_avg: float | None = None
    confidence: float | None = None
    calculated_at: datetime | None = None
    factors: dict | None = None
    model_config = ConfigDict(from_attributes=True)


class CampaignEffectOut(BaseModel):
    """캠페인 종합 효과 KPI. 캠페인 상세 카드에 사용."""
    campaign_id: int
    campaign_name: str | None = None
    advertiser_name: str | None = None
    objective: str | None = None
    status: str | None = None
    duration_days: int = 0
    channels: list[str] = []
    total_spend: float = Field(
        default=0.0,
        description="캠페인의 전체 기간 추정 매체비 합계 (KRW). SUM(spend_estimates.est_daily_spend) for this campaign."
    )
    est_impressions: float = Field(
        default=0.0,
        description="추정 노출수 (journey_events impressions 합산)"
    )
    est_clicks: float = Field(
        default=0.0,
        description="추정 클릭수 (est_impressions * 0.02 CTR 추정)"
    )
    query_lift_pct: float | None = None
    social_lift_pct: float | None = None
    sales_lift_pct: float | None = None
    confidence: float | None = None


# ── SpendEstimate ──
class SpendEstimateOut(BaseModel):
    """일별 광고비 추정 레코드. spend_estimates 테이블 직접 매핑."""
    id: int
    campaign_id: int
    date: datetime
    channel: str
    est_daily_spend: float = Field(
        description="해당일 해당 채널의 추정 매체비 (KRW). 대행수수료 미포함 순수 매체비 기준."
    )
    confidence: float | None = Field(default=None, description="추정 신뢰도 (0.0~1.0)")
    calculation_method: str | None = Field(
        default=None,
        description="추정 방법 (cpc_position, catalog_creative, catalog_creative_reverse, meta_signal_reverse 등)"
    )
    model_config = ConfigDict(from_attributes=True)


# ── TrendData ──
class TrendDataOut(BaseModel):
    id: int
    keyword_id: int
    date: datetime
    naver_trend: float | None
    google_trend: float | None
    model_config = ConfigDict(from_attributes=True)


# ── Phase 3B: 광고 접촉율 분석 ──
class ContactRateOut(BaseModel):
    age_group: str
    gender: str
    channel: str
    total_sessions: int
    total_ad_impressions: int
    contact_rate: float  # 세션당 평균 광고 수
    unique_advertisers: int
    avg_ads_per_session: float
    top_ad_types: dict[str, int] = {}
    position_distribution: dict[str, int] = {}


class ContactRateTrendPoint(BaseModel):
    date: str
    age_group: str
    gender: str
    contact_rate: float


# ── Phase 3B: SOV (Share of Voice) 분석 ──
class SOVOut(BaseModel):
    advertiser_name: str
    advertiser_id: int
    channel: str | None = None
    sov_percentage: float
    total_impressions: int


class CompetitiveSOVOut(BaseModel):
    target: SOVOut
    competitors: list[SOVOut] = []
    by_channel: dict[str, list[SOVOut]] = {}
    by_age_group: dict[str, list[SOVOut]] = {}


# ── Phase 3F: 통합 검색 ──
class UnifiedSearchResult(BaseModel):
    advertisers: list[AdvertiserSearchResult] = []
    industry_matches: list[AdvertiserSearchResult] = []
    competitor_ads: list[dict] = []
    ad_text_matches: list[dict] = []
    landing_matches: list[dict] = []


# ── Advertiser Profile ──
class AdvertiserProfileUpdate(BaseModel):
    annual_revenue: float | None = Field(default=None, description="연매출 (KRW)")
    employee_count: int | None = None
    founded_year: int | None = None
    description: str | None = None
    logo_url: str | None = None
    headquarters: str | None = None
    is_public: bool | None = None
    market_cap: float | None = Field(default=None, description="시가총액 (KRW)")
    business_category: str | None = None
    official_channels: dict[str, str] | None = None
    industry_id: int | None = None
    brand_name: str | None = None
    website: str | None = None


class AdvertiserProfileOut(AdvertiserOut):
    parent_id: int | None = None
    advertiser_type: str | None = None
    aliases: list[str] | None = None
    annual_revenue: float | None = Field(default=None, description="연매출 (KRW)")
    employee_count: int | None = None
    founded_year: int | None = None
    description: str | None = None
    logo_url: str | None = None
    headquarters: str | None = None
    is_public: bool = False
    market_cap: float | None = Field(default=None, description="시가총액 (KRW)")
    business_category: str | None = None
    official_channels: dict[str, str] | None = None
    data_source: str | None = None
    profile_updated_at: datetime | None = None


# ── Competitor Mapping ──
class CompetitorScoreOut(BaseModel):
    competitor_id: int
    competitor_name: str
    industry_id: int | None = None
    affinity_score: float
    keyword_overlap: float
    channel_overlap: float
    position_zone_overlap: float
    spend_similarity: float = Field(description="광고비 유사도 (0.0~1.0)")
    co_occurrence_count: int


class CompetitorListOut(BaseModel):
    target_id: int
    target_name: str
    industry_id: int | None = None
    industry_name: str | None = None
    competitors: list[CompetitorScoreOut] = []


# ── Industry Landscape ──
class IndustryAdvertiserOut(BaseModel):
    """업종 내 광고주 정보. 업종 랜드스케이프 응답에 포함."""
    id: int
    name: str
    brand_name: str | None = None
    annual_revenue: float | None = Field(default=None, description="연매출 (KRW)")
    employee_count: int | None = None
    is_public: bool = False
    est_ad_spend: float = Field(
        default=0.0,
        description="조회 기간 내 추정 매체비 합계 (KRW). SUM(est_daily_spend)."
    )
    sov_percentage: float = 0.0
    channel_count: int = 0
    channel_mix: list[str] = []
    ad_count: int = 0


class IndustryLandscapeOut(BaseModel):
    industry: IndustryOut
    total_market_size: float | None = Field(
        default=None,
        description="업종 전체 추정 광고시장 규모 (KRW). 산출 불가시 null."
    )
    advertiser_count: int
    advertisers: list[IndustryAdvertiserOut] = []
    revenue_ranking: list[IndustryAdvertiserOut] = []
    spend_ranking: list[IndustryAdvertiserOut] = []


class MarketMapPoint(BaseModel):
    id: int
    name: str
    x: float
    y: float
    size: float
    is_public: bool = False


class IndustryMarketMapOut(BaseModel):
    industry: IndustryOut
    points: list[MarketMapPoint] = []
    axis_labels: dict[str, str] = {}


# ── Persona Ranking ──
class PersonaAdvertiserRankOut(BaseModel):
    persona_code: str
    age_group: str | None = None
    gender: str | None = None
    advertiser_name: str
    advertiser_id: int | None = None
    impression_count: int
    session_count: int
    avg_per_session: float
    channels: list[str] = []
    rank: int


class PersonaHeatmapCellOut(BaseModel):
    persona_code: str
    age_group: str | None = None
    gender: str | None = None
    advertiser_name: str
    advertiser_id: int | None = None
    impression_count: int
    intensity: float


class PersonaRankingTrendPoint(BaseModel):
    date: str
    advertiser_name: str
    impression_count: int


# ── Brand Channel Monitoring ──
class BrandChannelContentOut(BaseModel):
    id: int
    advertiser_id: int
    platform: str
    channel_url: str
    content_id: str
    content_type: str | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    upload_date: datetime | None = None
    view_count: int | None = None
    like_count: int | None = None
    duration_seconds: int | None = None
    is_ad_content: bool = False
    ad_indicators: dict | None = None
    discovered_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class BrandChannelSummary(BaseModel):
    platform: str
    channel_url: str
    total_contents: int
    latest_upload: datetime | None = None
    ad_content_count: int


class CSVImportResult(BaseModel):
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: list[str] = []


# ── Brand Tree (전체 그룹/광고주 트리) ──
class BrandTreeChild(BaseModel):
    id: int
    name: str
    advertiser_type: str | None = None
    website: str | None = None
    brand_name: str | None = None
    ad_count: int = 0
    children: list["BrandTreeChild"] = []
    model_config = ConfigDict(from_attributes=True)


class BrandTreeGroup(BaseModel):
    id: int
    name: str
    advertiser_type: str | None = "group"
    website: str | None = None
    children: list[BrandTreeChild] = []
    model_config = ConfigDict(from_attributes=True)


class BrandTreeResponse(BaseModel):
    groups: list[BrandTreeGroup] = []
    independents: list[BrandTreeChild] = []


# ── Product Category ──
class ProductCategoryOut(BaseModel):
    id: int
    name: str
    parent_id: int | None = None
    industry_id: int | None = None
    model_config = ConfigDict(from_attributes=True)


class ProductCategoryTreeOut(ProductCategoryOut):
    children: list["ProductCategoryTreeOut"] = []
    advertiser_count: int = 0
    ad_count: int = 0


class ProductCategoryDetailOut(ProductCategoryOut):
    advertiser_count: int = 0
    ad_count: int = 0
    est_spend: float = Field(
        default=0.0,
        description="해당 카테고리의 조회 기간 내 추정 매체비 합계 (KRW)"
    )
    children: list["ProductCategoryTreeOut"] = []


class ProductCategoryAdvertiserOut(BaseModel):
    """카테고리 내 광고주별 요약."""
    advertiser_id: int
    advertiser_name: str
    brand_name: str | None = None
    ad_count: int = 0
    est_spend: float = Field(
        default=0.0,
        description="해당 광고주의 이 카테고리 내 추정 매체비 합계 (KRW)"
    )
    channels: list[str] = []
    rank: int = 0


# ── Meta Signal ──
class SmartStoreSnapshotOut(BaseModel):
    id: int
    advertiser_id: int
    store_name: str | None = None
    product_url: str | None = None
    product_name: str | None = None
    review_count: int | None = None
    review_delta: int = 0
    avg_rating: float | None = None
    price: int | None = Field(default=None, description="상품 가격 (KRW)")
    discount_pct: float = 0.0
    wishlist_count: int | None = None
    qa_count: int | None = None
    estimated_sales_level: str | None = None
    stock_quantity: int | None = None
    purchase_cnt: int | None = None
    purchase_cnt_delta: int = 0
    estimated_daily_sales: int | None = Field(
        default=None, description="추정 일일 판매수량 (개)"
    )
    estimation_method: str | None = None
    category_name: str | None = None
    seller_grade: str | None = None
    captured_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class SmartStoreTrackIn(BaseModel):
    product_url: str
    label: str | None = None


class SmartStoreTrackedOut(BaseModel):
    id: int
    product_url: str
    store_name: str | None = None
    product_name: str | None = None
    label: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class SmartStoreSalesEstimation(BaseModel):
    estimated_daily_sales: int = Field(default=0, description="추정 일일 판매수량 (개)")
    estimated_daily_revenue: int = Field(default=0, description="추정 일일 매출 (KRW)")
    estimated_monthly_revenue: int = Field(default=0, description="추정 월 매출 (KRW)")
    methods: dict[str, int] = {}
    primary_method: str | None = None
    confidence: float = 0.0


class SmartStoreCompareIn(BaseModel):
    product_urls: list[str]


class TrafficSignalOut(BaseModel):
    id: int
    advertiser_id: int
    date: datetime
    brand_keyword: str | None = None
    naver_search_index: float | None = None
    google_trend_index: float | None = None
    composite_index: float | None = None
    wow_change_pct: float | None = None
    traffic_level: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ActivityScoreOut(BaseModel):
    id: int
    advertiser_id: int
    date: datetime
    active_campaigns: int = 0
    new_creatives: int = 0
    creative_variants: int = 0
    social_post_count: int = 0
    channel_count: int = 0
    composite_score: float = 0.0
    activity_state: str | None = None
    factors: dict | None = None
    model_config = ConfigDict(from_attributes=True)


class MetaSignalOverviewOut(BaseModel):
    advertiser_id: int
    date: datetime | None = None
    smartstore_score: float = 0.0
    traffic_score: float = 0.0
    activity_score: float = 0.0
    panel_calibration: float = 1.0
    composite_score: float = 0.0
    spend_multiplier: float = Field(
        default=1.0,
        description="메타시그널 기반 광고비 보정 배수 (0.7~1.5). campaign_builder에 곱하는 레이어."
    )
    activity_state: str | None = None
    raw_factors: dict | None = None


class PanelSummaryOut(BaseModel):
    advertiser_id: int
    ai_observations: int = 0
    human_observations: int = 0
    total_observations: int = 0
    channels: list[str] = []
    panel_calibration: float = 1.0


class PanelSubmitIn(BaseModel):
    advertiser_name: str | None = None
    advertiser_id: int | None = None
    channel: str
    device: str | None = None
    location: str | None = None
    extra_data: dict | None = None


# ── Social Impact ──
class SocialImpactOverviewOut(BaseModel):
    advertiser_id: int
    date: datetime | None = None
    news_impact_score: float = 0.0
    social_posting_score: float = 0.0
    search_lift_score: float = 0.0
    composite_score: float = 0.0
    news_article_count: int = 0
    news_sentiment_avg: float | None = None
    social_engagement_delta_pct: float | None = None
    social_posting_delta_pct: float | None = None
    search_volume_delta_pct: float | None = None
    has_active_campaign: bool = False
    impact_phase: str | None = None
    factors: dict | None = None


class SocialImpactTimelineOut(BaseModel):
    date: datetime
    news_impact_score: float = 0.0
    social_posting_score: float = 0.0
    search_lift_score: float = 0.0
    composite_score: float = 0.0
    impact_phase: str | None = None
    has_active_campaign: bool = False
    model_config = ConfigDict(from_attributes=True)


class NewsMentionOut(BaseModel):
    id: int
    advertiser_id: int
    source: str
    article_url: str
    article_title: str | None = None
    article_description: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    is_pr: bool = False
    model_config = ConfigDict(from_attributes=True)


class SocialImpactTopItem(BaseModel):
    advertiser_id: int
    advertiser_name: str | None = None
    brand_name: str | None = None
    composite_score: float = 0.0
    impact_phase: str | None = None
    news_impact_score: float = 0.0
    social_posting_score: float = 0.0
    search_lift_score: float = 0.0


# ── Launch Impact ──
class LaunchProductCreateIn(BaseModel):
    advertiser_id: int
    name: str
    category: str                       # game / commerce / product
    launch_date: datetime
    product_url: str | None = None
    external_id: str | None = None
    keywords: list[str]


class LaunchProductUpdateIn(BaseModel):
    name: str | None = None
    category: str | None = None
    launch_date: datetime | None = None
    product_url: str | None = None
    external_id: str | None = None
    keywords: list[str] | None = None
    is_active: bool | None = None


class LaunchProductOut(BaseModel):
    id: int
    advertiser_id: int
    name: str
    category: str
    launch_date: datetime
    product_url: str | None = None
    external_id: str | None = None
    keywords: list[str] = []
    is_active: bool = True
    created_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class LaunchImpactOverviewOut(BaseModel):
    launch_product_id: int
    product_name: str
    category: str
    launch_date: datetime
    days_since_launch: int = 0
    date: datetime | None = None
    mrs_score: float = 0.0
    rv_score: float = 0.0
    cs_score: float = 0.0
    lii_score: float = 0.0
    total_mentions: int = 0
    impact_phase: str | None = None
    factors: dict | None = None


class LaunchImpactTimelineOut(BaseModel):
    date: datetime
    mrs_score: float = 0.0
    rv_score: float = 0.0
    cs_score: float = 0.0
    lii_score: float = 0.0
    total_mentions: int = 0
    impact_phase: str | None = None
    model_config = ConfigDict(from_attributes=True)


class LaunchMentionOut(BaseModel):
    id: int
    source_type: str
    source_platform: str | None = None
    url: str
    title: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    sentiment: str | None = None
    matched_keyword: str | None = None
    model_config = ConfigDict(from_attributes=True)


class LaunchImpactRankingItem(BaseModel):
    launch_product_id: int
    product_name: str
    advertiser_id: int
    advertiser_name: str | None = None
    category: str
    launch_date: datetime
    lii_score: float = 0.0
    mrs_score: float = 0.0
    rv_score: float = 0.0
    cs_score: float = 0.0
    total_mentions: int = 0
    impact_phase: str | None = None


# ── Media Source (LII) ──
class MediaSourceCreate(BaseModel):
    name: str
    url: str
    connector_type: str
    weight: float = 1.0
    schedule_interval: int = 60
    is_active: bool = True
    parse_profile_id: int | None = None
    extra_config: dict | None = None


class MediaSourceUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    weight: float | None = None
    schedule_interval: int | None = None
    is_active: bool | None = None
    parse_profile_id: int | None = None
    extra_config: dict | None = None


class MediaSourceOut(BaseModel):
    id: int
    name: str
    url: str
    connector_type: str
    weight: float
    schedule_interval: int
    is_active: bool
    last_crawl_at: datetime | None = None
    error_count: int = 0
    error_rate: float = 0.0
    parse_profile_id: int | None = None
    extra_config: dict | None = None
    created_at: datetime | None = None
    mention_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class ParseProfileCreate(BaseModel):
    name: str
    list_selector: str | None = None
    detail_selector: str | None = None
    title_selector: str | None = None
    date_selector: str | None = None
    content_selector: str | None = None
    test_url: str | None = None


class ParseProfileOut(BaseModel):
    id: int
    name: str
    list_selector: str | None = None
    detail_selector: str | None = None
    title_selector: str | None = None
    date_selector: str | None = None
    content_selector: str | None = None
    test_url: str | None = None
    model_config = ConfigDict(from_attributes=True)


class ReactionTimeseriesOut(BaseModel):
    id: int
    launch_product_id: int
    timestamp: datetime
    metric_type: str
    value: float
    source: str | None = None
    model_config = ConfigDict(from_attributes=True)


# ── Mobile Panel ──
class MobileDeviceRegisterIn(BaseModel):
    device_type: str = "ai"                         # "ai" | "real"
    os_type: str                                     # "android" | "ios"
    os_version: str | None = None
    device_model: str | None = None
    carrier: str | None = None
    screen_res: str | None = None
    app_list: list[str] | None = None
    age_group: str | None = None
    gender: str | None = None
    region: str = "서울"
    persona_code: str | None = None                  # AI 페르소나 코드 (ai일 때)


class MobileDeviceOut(BaseModel):
    id: int
    device_id: str
    device_type: str
    os_type: str
    os_version: str | None = None
    device_model: str | None = None
    carrier: str | None = None
    age_group: str | None = None
    gender: str | None = None
    region: str | None = None
    is_active: bool = True
    last_seen: datetime | None = None
    created_at: datetime | None = None
    exposure_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class MobileExposureIn(BaseModel):
    device_id: str
    app_name: str                                    # "YouTube", "Instagram" 등
    advertiser_name: str | None = None
    ad_text: str | None = None
    ad_type: str | None = None                       # video_preroll, banner, native, story
    creative_url: str | None = None
    click_url: str | None = None
    duration_ms: int | None = None
    was_clicked: bool = False
    was_skipped: bool = False
    screen_position: str | None = None
    observed_at: datetime | None = None
    extra_data: dict | None = None


class MobileExposureBatchIn(BaseModel):
    device_id: str
    exposures: list[MobileExposureIn]


class MobileExposureOut(BaseModel):
    id: int
    device_id: str
    app_name: str | None = None
    channel: str | None = None
    advertiser_name_raw: str | None = None
    ad_text: str | None = None
    ad_type: str | None = None
    duration_ms: int | None = None
    was_clicked: bool = False
    observed_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class MobilePanelStatsOut(BaseModel):
    total_devices: int = 0
    ai_devices: int = 0
    real_devices: int = 0
    active_devices: int = 0
    total_exposures: int = 0
    exposures_today: int = 0
    top_apps: list[dict] = []
    top_advertisers: list[dict] = []
