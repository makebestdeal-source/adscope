/** AdScope API 클라이언트 */

const API_BASE = "/api";

export async function fetchApi<T = any>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };

  // Auto-attach JWT token + device fingerprint
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("adscope_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const fp = localStorage.getItem("adscope_device_fp");
    if (fp) {
      headers["X-Device-Fingerprint"] = fp;
    }
  }

  // AbortController-based 30s timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30_000);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal: init?.signal ?? controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }

  if (res.status === 401) {
    // Token expired - clear storage but don't force redirect (let pages handle it)
    if (typeof window !== "undefined") {
      localStorage.removeItem("adscope_token");
      localStorage.removeItem("adscope_user");
      // Only redirect if not on admin page (admin has its own login)
      if (!window.location.pathname.startsWith("/admin")) {
        window.location.href = "/login";
      }
    }
    throw new Error("Session expired");
  }

  if (res.status === 403) {
    if (typeof window !== "undefined") {
      const upgradeRequired = res.headers.get("X-Upgrade-Required");
      const requiredPlan = res.headers.get("X-Required-Plan");
      const planExpired = res.headers.get("X-Plan-Expired");

      if (upgradeRequired === "true" || requiredPlan || planExpired === "true") {
        alert("유료 회원 전용 기능입니다.\n플랜을 업그레이드해주세요.\n\n문의: admin@adscope.kr");
        window.location.href = "/pricing";
        throw new Error("Upgrade required");
      }
    }
  }

  if (!res.ok) {
    throw new Error(`API Error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── 기존 타입 ──

export interface AdSnapshot {
  id: number;
  keyword_id: number;
  persona_id: number;
  device: string;
  channel: string;
  captured_at: string;
  ad_count: number;
  screenshot_path: string | null;
}

export interface AdDetail {
  id: number;
  snapshot_id: number;
  advertiser_name_raw: string | null;
  brand: string | null;
  ad_text: string | null;
  ad_description: string | null;
  position: number | null;
  url: string | null;
  display_url: string | null;
  ad_type: string | null;
  verification_status: string | null;
  verification_source: string | null;
  product_name: string | null;
  product_category: string | null;
  product_category_id: number | null;
  ad_placement: string | null;
  promotion_type: string | null;
  creative_image_path: string | null;
  screenshot_path: string | null;
}

export interface Advertiser {
  id: number;
  name: string;
  industry_id: number | null;
  brand_name: string | null;
  website: string | null;
}

export interface DailyStats {
  date: string;
  total_snapshots: number;
  total_ads: number;
  total_contacts: number;
  total_catalog: number;
  by_channel: Record<string, number>;
  contact_channels: Record<string, number>;
  latest_crawl_at: string | null;
  today_total_ads: number;
}

/** 채널별 추정 매체비 요약. GET /api/spend/summary 응답. */
export interface SpendSummary {
  channel: string;
  /** 조회 기간 내 추정 매체비 합계 (KRW). SUM(est_daily_spend). 대행수수료 미포함 순수 매체비. */
  total_spend: number;
  /** 추정 신뢰도 평균 (0.0~1.0) */
  avg_confidence: number;
  /** 집계에 사용된 spend_estimates 레코드 수 */
  data_points: number;
}

export interface TopAdvertiser {
  advertiser: string;
  ad_count: number;
}

/** 광고주별 추정 매체비 랭킹. GET /api/spend/by-advertiser 응답. */
export interface SpendByAdvertiser {
  advertiser: string;
  /** 조회 기간 내 전 채널 추정 매체비 합계 (KRW). SUM(est_daily_spend). 대행수수료 미포함. */
  total_spend: number;
}

// ── Phase 3 신규 타입 ──

export interface AdvertiserSearchResult {
  id: number;
  name: string;
  industry_id: number | null;
  brand_name: string | null;
  website: string | null;
  advertiser_type: string | null;
  parent_id: number | null;
  match_type: string;
}

export interface AdvertiserTreeNode {
  id: number;
  name: string;
  industry_id: number | null;
  brand_name: string | null;
  website: string | null;
  parent_id: number | null;
  advertiser_type: string | null;
  aliases: string[];
  children: AdvertiserTreeNode[];
}

/** 광고주 리포트 내 채널별 광고비 요약. */
export interface ChannelSpendSummaryReport {
  channel: string;
  /** 해당 채널의 조회 기간 내 추정 매체비 합계 (KRW). SUM(est_daily_spend). */
  est_spend: number;
  ad_count: number;
  position_distribution: Record<string, number>;
  top_keywords: string[];
  is_active: boolean;
}

/** 일별 광고비 시계열 포인트. */
export interface DailySpendPoint {
  date: string;
  /** 해당일 추정 매체비 (KRW) */
  spend: number;
}

/** 캠페인 기본 정보. */
export interface Campaign {
  id: number;
  advertiser_id: number;
  channel: string;
  first_seen: string;
  last_seen: string;
  is_active: boolean;
  /** 캠페인 누적 추정 매체비 (KRW). Campaign 테이블 컬럼. 캠페인 전 기간 합산. */
  total_est_spend: number;
  snapshot_count: number;
}

export interface CampaignDetail extends Campaign {
  campaign_name: string | null;
  objective: string | null;
  product_service: string | null;
  promotion_copy: string | null;
  model_info: string | null;
  target_keywords: { brand?: string[]; product?: string[]; competitor?: string[] } | null;
  start_at: string | null;
  end_at: string | null;
  creative_ids: number[] | null;
  status: string | null;
  enrichment_status: string | null;
}

export interface JourneyEvent {
  ts: string;
  stage: "exposure" | "interest" | "consideration" | "conversion";
  source: string;
  metric: string;
  value: number;
  dims: Record<string, unknown> | null;
}

export interface CampaignLiftData {
  campaign_id: number;
  query_lift_pct: number | null;
  social_lift_pct: number | null;
  sales_lift_pct: number | null;
  pre_query_avg: number | null;
  post_query_avg: number | null;
  pre_social_avg: number | null;
  post_social_avg: number | null;
  pre_sales_avg: number | null;
  post_sales_avg: number | null;
  confidence: number | null;
  calculated_at: string | null;
  factors: Record<string, unknown> | null;
}

/** 캠페인 종합 효과 KPI. GET /api/campaigns/{id}/effect 응답. */
export interface CampaignEffect {
  campaign_id: number;
  campaign_name: string | null;
  advertiser_name: string | null;
  objective: string | null;
  status: string | null;
  duration_days: number;
  channels: string[];
  /** 캠페인 전체 기간 추정 매체비 합계 (KRW). SUM(spend_estimates.est_daily_spend). 대행수수료 미포함. */
  total_spend: number;
  /** 추정 노출수 */
  est_impressions: number;
  /** 추정 클릭수 (est_impressions * 0.02 CTR) */
  est_clicks: number;
  query_lift_pct: number | null;
  social_lift_pct: number | null;
  sales_lift_pct: number | null;
  confidence: number | null;
}

/** 광고주 단위 광고비 리포트 응답. */
export interface AdvertiserSpendReport {
  advertiser: Advertiser;
  /** 조회 기간 내 전 채널 추정 매체비 합계 (KRW). SUM(est_daily_spend). */
  total_est_spend: number;
  /** 조회 기간 {start, end} ISO format */
  period: { start: string; end: string };
  by_channel: ChannelSpendSummaryReport[];
  daily_trend: DailySpendPoint[];
  active_campaigns: Campaign[];
}

// Stealth Surf types
export interface StealthSurfSummary {
  total_ads: number;
  period_days: number;
  by_network: Record<string, number>;
  by_persona: Record<string, number>;
  by_source: Record<string, number>;
  contact_rates: Record<string, number>;
  sessions: number;
}

export interface StealthPersonaBreakdown {
  cells: Array<{ persona: string; network: string; count: number }>;
  personas: string[];
}

export interface StealthSpendEstimate {
  estimates?: Array<{
    network: string;
    contact_rate: number;
    est_monthly_media: number;
    est_monthly_total: number;
  }>;
  calibration?: Record<string, unknown>;
  error?: string;
}

export interface ContactRateData {
  age_group: string;
  gender: string;
  channel: string;
  total_sessions: number;
  total_ad_impressions: number;
  contact_rate: number;
  unique_advertisers: number;
  avg_ads_per_session: number;
  top_ad_types: Record<string, number>;
  position_distribution: Record<string, number>;
}

export interface ContactRateTrendPoint {
  date: string;
  age_group: string;
  gender: string;
  contact_rate: number;
}

export interface ContactRateComparison {
  age_group: string;
  gender: string;
  channel: string;
  sessions_with_ad: number;
  ad_impressions: number;
  avg_per_session: number;
}

export interface SOVData {
  advertiser_name: string;
  advertiser_id: number;
  channel: string | null;
  sov_percentage: number;
  total_impressions: number;
}

export interface CompetitiveSOV {
  target: {
    advertiser_id: number;
    name: string;
    sov_percentage: number;
    total_impressions: number;
  };
  competitors: {
    advertiser_id: number;
    name: string;
    sov_percentage: number;
    total_impressions: number;
  }[];
  by_channel: Record<string, Record<string, number>>;
  by_age_group: Record<string, Record<string, number>>;
}

export interface SOVTrendPoint {
  date: string;
  advertiser_name: string;
  advertiser_id: number;
  sov_percentage: number;
}

// ── 대시보드 / 갤러리 추가 타입 ──

export interface DailyTrendPoint {
  date: string;
  channel: string;
  ad_count: number;
}

export interface GalleryItem {
  id: number | string;
  advertiser_name_raw: string | null;
  ad_text: string | null;
  ad_type: string | null;
  creative_image_path: string | null;
  url: string | null;
  brand: string | null;
  channel: string;
  captured_at: string | null;
  source?: "ads" | "social";
  view_count?: number | null;
  like_count?: number | null;
  upload_date?: string | null;
  thumbnail_url?: string | null;
  landing_analysis?: {
    brand_name?: string;
    business_name?: string;
    page_title?: string;
    domain?: string;
  } | null;
}

export interface GalleryResponse {
  total: number;
  items: GalleryItem[];
}

// ── Competitor Mapping ──

export interface CompetitorScore {
  competitor_id: number;
  competitor_name: string;
  industry_id: number | null;
  affinity_score: number;
  keyword_overlap: number;
  channel_overlap: number;
  position_zone_overlap: number;
  spend_similarity: number;
  co_occurrence_count: number;
}

export interface CompetitorList {
  target_id: number;
  target_name: string;
  industry_id: number | null;
  industry_name: string | null;
  competitors: CompetitorScore[];
}

// ── Industry Landscape ──

export interface IndustryInfo {
  id: number;
  name: string;
  avg_cpc_min: number | null;
  avg_cpc_max: number | null;
}

export interface LandscapeAdvertiser {
  id: number;
  name: string;
  brand_name: string | null;
  annual_revenue: number | null;
  employee_count: number | null;
  is_public: boolean;
  est_ad_spend: number;
  sov_percentage: number;
  channel_count: number;
  channel_mix: string[];
  ad_count: number;
}

export interface IndustryLandscape {
  industry: IndustryInfo;
  total_market_size: number | null;
  advertiser_count: number;
  advertisers: LandscapeAdvertiser[];
  revenue_ranking: LandscapeAdvertiser[];
  spend_ranking: LandscapeAdvertiser[];
}

export interface MarketMapPoint {
  id: number;
  name: string;
  x: number;
  y: number;
  size: number;
  is_public: boolean;
}

export interface IndustryMarketMap {
  industry: IndustryInfo;
  points: MarketMapPoint[];
  axis_labels: { x: string; y: string };
}

// ── Advertiser Profile ──

export interface AdvertiserProfile extends Advertiser {
  parent_id: number | null;
  advertiser_type: string | null;
  aliases: string[];
  annual_revenue: number | null;
  employee_count: number | null;
  founded_year: number | null;
  description: string | null;
  logo_url: string | null;
  headquarters: string | null;
  is_public: boolean;
  market_cap: number | null;
  business_category: string | null;
  official_channels: Record<string, string> | null;
  data_source: string | null;
  profile_updated_at: string | null;
}

// ── Persona Ranking ──

export interface PersonaAdvertiserRank {
  persona_code: string;
  age_group: string | null;
  gender: string | null;
  advertiser_name: string;
  advertiser_id: number | null;
  impression_count: number;
  session_count: number;
  avg_per_session: number;
  channels: string[];
  rank: number;
}

export interface PersonaHeatmapCell {
  persona_code: string;
  age_group: string | null;
  gender: string | null;
  advertiser_name: string;
  advertiser_id: number | null;
  impression_count: number;
  intensity: number;
}

export interface PersonaRankingTrendPoint {
  date: string;
  advertiser_name: string;
  impression_count: number;
}

// ── Brand Channel ──

export interface BrandChannelContent {
  id: number;
  advertiser_id: number;
  platform: string;
  channel_url: string;
  content_id: string;
  content_type: string | null;
  title: string | null;
  thumbnail_url: string | null;
  upload_date: string | null;
  view_count: number | null;
  like_count: number | null;
  duration_seconds: number | null;
  is_ad_content: boolean;
  ad_indicators: Record<string, unknown> | null;
  discovered_at: string;
}

export interface BrandChannelSummary {
  platform: string;
  channel_url: string;
  total_contents: number;
  latest_upload: string | null;
  ad_content_count: number;
}

// ── Brand Tree ──

export interface BrandTreeChild {
  id: number;
  name: string;
  advertiser_type: string | null;
  website: string | null;
  brand_name: string | null;
  ad_count: number;
  children: BrandTreeChild[];
}

export interface BrandTreeGroup {
  id: number;
  name: string;
  advertiser_type: string | null;
  website: string | null;
  children: BrandTreeChild[];
}

export interface BrandTreeResponse {
  groups: BrandTreeGroup[];
  independents: BrandTreeChild[];
}

// ── Media Breakdown (advertiser detail) ──

export interface MediaCategoryBreakdown {
  category: string;
  category_key: string;
  channels: string[];
  ad_count: number;
  est_spend: number;
  ratio: number;
}

export interface ChannelBreakdown {
  channel: string;
  category: string;
  ad_count: number;
  est_spend: number;
}

export interface MediaBreakdownResponse {
  advertiser_id: number;
  advertiser_name: string;
  brand_name: string | null;
  website: string | null;
  advertiser_type: string | null;
  industry_name: string | null;
  total_ads: number;
  /** 조회 기간 내 추정 매체비 합계 (KRW) */
  total_est_spend: number;
  period_days: number;
  categories: MediaCategoryBreakdown[];
  by_channel: ChannelBreakdown[];
  recent_ads: GalleryItem[];
}

// ── Product Category ──

export interface ProductCategoryTree {
  id: number;
  name: string;
  parent_id: number | null;
  industry_id: number | null;
  children: ProductCategoryTree[];
  advertiser_count: number;
  ad_count: number;
}

export interface ProductCategoryDetail {
  id: number;
  name: string;
  parent_id: number | null;
  industry_id: number | null;
  advertiser_count: number;
  ad_count: number;
  est_spend: number;
  children: ProductCategoryTree[];
}

export interface ProductCategoryAdvertiser {
  advertiser_id: number;
  advertiser_name: string;
  brand_name: string | null;
  ad_count: number;
  est_spend: number;
  channels: string[];
  rank: number;
}

// ── API 함수 ──

export const api = {
  // 광고 스냅샷
  getSnapshots: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return fetchApi<AdSnapshot[]>(`/ads/snapshots${qs}`);
  },

  getSnapshot: (id: number) =>
    fetchApi<AdSnapshot & { details: AdDetail[] }>(`/ads/snapshots/${id}`),

  getDailyStats: (date?: string) => {
    const qs = date ? `?date=${date}` : "";
    return fetchApi<DailyStats>(`/ads/stats/daily${qs}`);
  },

  getDailyTrend: (days = 14) =>
    fetchApi<DailyTrendPoint[]>(`/ads/stats/daily-trend?days=${days}`),

  getGallery: (params?: {
    channel?: string;
    advertiser?: string;
    date_from?: string;
    date_to?: string;
    source?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.advertiser) qs.set("advertiser", params.advertiser);
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.source) qs.set("source", params.source);
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const q = qs.toString();
    return fetchApi<GalleryResponse>(`/ads/gallery${q ? "?" + q : ""}`);
  },

  // 광고주
  getAdvertisers: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return fetchApi<Advertiser[]>(`/advertisers${qs}`);
  },

  getTopAdvertisers: (days = 7, limit = 20) =>
    fetchApi<TopAdvertiser[]>(
      `/advertisers/ranking/top?days=${days}&limit=${limit}`
    ),

  searchAdvertisers: (q: string, limit = 20) =>
    fetchApi<AdvertiserSearchResult[]>(
      `/advertisers/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),

  getBrandTree: () =>
    fetchApi<BrandTreeResponse>(`/advertisers/brand-tree`),

  getAdvertiserTree: (id: number) =>
    fetchApi<AdvertiserTreeNode>(`/advertisers/${id}/tree`),

  getAdvertiserSpendReport: (id: number, days = 30) =>
    fetchApi<AdvertiserSpendReport>(
      `/advertisers/${id}/spend-report?days=${days}`
    ),

  getAdvertiserCampaigns: (id: number) =>
    fetchApi<Campaign[]>(`/advertisers/${id}/campaigns`),

  getAdvertiserMediaBreakdown: (id: number, days = 30) =>
    fetchApi<MediaBreakdownResponse>(
      `/advertisers/media-breakdown/${id}?days=${days}`
    ),

  // 광고비
  getSpendSummary: (days = 7) =>
    fetchApi<SpendSummary[]>(`/spend/summary?days=${days}`),

  getSpendByAdvertiser: (days = 7, limit = 20) =>
    fetchApi<SpendByAdvertiser[]>(
      `/spend/by-advertiser?days=${days}&limit=${limit}`
    ),

  // 접촉율
  getContactRates: (params?: { days?: number; channel?: string; age_group?: string }) => {
    const qs = new URLSearchParams();
    if (params?.days) qs.set("days", String(params.days));
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.age_group) qs.set("age_group", params.age_group);
    const q = qs.toString();
    return fetchApi<ContactRateData[]>(`/analytics/contact-rate${q ? "?" + q : ""}`);
  },

  // Stealth Surf (페르소나 서프 수집)
  getStealthSummary: (days = 30) =>
    fetchApi<StealthSurfSummary>(`/stealth-surf/summary?days=${days}`),

  getStealthPersonaBreakdown: (days = 30) =>
    fetchApi<StealthPersonaBreakdown>(`/stealth-surf/persona-breakdown?days=${days}`),

  getStealthSpendEstimate: (days = 30) =>
    fetchApi<StealthSpendEstimate>(`/stealth-surf/spend-estimate?days=${days}`),

  // SOV
  getSOV: (params?: { keyword?: string; channel?: string; days?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.keyword) qs.set("keyword", params.keyword);
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.days) qs.set("days", String(params.days));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return fetchApi<SOVData[]>(`/analytics/sov${q ? "?" + q : ""}`);
  },

  getCompetitiveSOV: (advertiserId: number, days = 30) =>
    fetchApi<CompetitiveSOV>(
      `/analytics/sov/competitive/${advertiserId}?days=${days}`
    ),

  getSOVTrend: (advertiserId: number, competitorIds?: number[], days = 30) => {
    const qs = new URLSearchParams({ advertiser_id: String(advertiserId), days: String(days) });
    if (competitorIds?.length) qs.set("competitor_ids", competitorIds.join(","));
    return fetchApi<SOVTrendPoint[]>(`/analytics/sov/trend?${qs.toString()}`);
  },

  // Persona Ranking
  getPersonaRanking: (params?: {
    persona_code?: string;
    days?: number;
    channel?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.persona_code) qs.set("persona_code", params.persona_code);
    if (params?.days) qs.set("days", String(params.days));
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return fetchApi<PersonaAdvertiserRank[]>(`/analytics/persona-ranking${q ? "?" + q : ""}`);
  },

  getPersonaHeatmap: (params?: {
    days?: number;
    channel?: string;
    top_advertisers?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.days) qs.set("days", String(params.days));
    if (params?.channel) qs.set("channel", params.channel);
    if (params?.top_advertisers) qs.set("top_advertisers", String(params.top_advertisers));
    const q = qs.toString();
    return fetchApi<PersonaHeatmapCell[]>(`/analytics/persona-ranking/heatmap${q ? "?" + q : ""}`);
  },

  getPersonaRankingTrend: (params: {
    persona_code: string;
    days?: number;
    channel?: string;
    limit?: number;
  }) => {
    const qs = new URLSearchParams({ persona_code: params.persona_code });
    if (params.days) qs.set("days", String(params.days));
    if (params.channel) qs.set("channel", params.channel);
    if (params.limit) qs.set("limit", String(params.limit));
    return fetchApi<PersonaRankingTrendPoint[]>(`/analytics/persona-ranking/trend?${qs.toString()}`);
  },

  // Admin (JWT Bearer authentication)
  adminStats: (token: string) =>
    fetchApi<AdminStats>(`/admin/stats`, { headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminStartCrawl: (token: string) =>
    fetchApi<{ status: string; message: string }>(`/admin/crawl/start`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminCrawlStatus: (token: string) =>
    fetchApi<CrawlStatusResponse>(`/admin/crawl-status`, { headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminScheduleOverview: (token: string) =>
    fetchApi<ScheduleOverview>(`/admin/schedule-overview`, { headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminCollectSocial: (token: string) =>
    fetchApi<{ status: string; message: string }>(`/admin/collect/social`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminCollectSmartstore: (token: string) =>
    fetchApi<{ status: string; message: string }>(`/admin/collect/smartstore`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminCollectTraffic: (token: string) =>
    fetchApi<{ status: string; message: string }>(`/admin/collect/traffic`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminCollectActivity: (token: string) =>
    fetchApi<{ status: string; message: string }>(`/admin/collect/activity`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminCollectMetaAggregate: (token: string) =>
    fetchApi<{ status: string; message: string }>(`/admin/collect/meta-aggregate`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminCollectCampaignRebuild: (token: string) =>
    fetchApi<{ status: string; message: string }>(`/admin/collect/campaign-rebuild`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  adminAiEnrich: (token: string) =>
    fetchApi<{ status: string }>(`/admin/ai-enrich`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` } }),

  // Competitor Mapping
  getCompetitors: (advertiserId: number, days = 30, limit = 20) =>
    fetchApi<CompetitorList>(
      `/competitors/${advertiserId}?days=${days}&limit=${limit}`
    ),

  getIndustryLandscape: (industryId: number, days = 30) =>
    fetchApi<IndustryLandscape>(
      `/competitors/industry/${industryId}/landscape?days=${days}`
    ),

  // Industries
  getIndustries: () =>
    fetchApi<IndustryInfo[]>(`/industries`),

  getIndustryLandscapeFull: (industryId: number, days = 30) =>
    fetchApi<IndustryLandscape>(
      `/industries/${industryId}/landscape?days=${days}`
    ),

  getIndustryMarketMap: (industryId: number, days = 30) =>
    fetchApi<IndustryMarketMap>(
      `/industries/${industryId}/market-map?days=${days}`
    ),

  // Brand Channel Monitoring
  getBrandChannelStats: () =>
    fetchApi<{
      monitored_brands: number;
      total_channels: number;
      total_contents: number;
      new_this_week: number;
      ad_content_count: number;
    }>("/brand-channels/stats/summary"),

  getBrandRecentUploads: (params?: {
    days?: number;
    limit?: number;
    platform?: string;
    is_ad?: boolean;
  }) => {
    const qs = new URLSearchParams();
    if (params?.days) qs.set("days", String(params.days));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.platform) qs.set("platform", params.platform);
    if (params?.is_ad !== undefined) qs.set("is_ad", String(params.is_ad));
    const q = qs.toString();
    return fetchApi<BrandChannelContent[]>(`/brand-channels/recent-uploads${q ? "?" + q : ""}`);
  },

  getBrandChannelContents: (
    advertiserId: number,
    params?: {
      platform?: string;
      content_type?: string;
      is_ad?: boolean;
      days?: number;
      limit?: number;
    }
  ) => {
    const qs = new URLSearchParams();
    if (params?.platform) qs.set("platform", params.platform);
    if (params?.content_type) qs.set("content_type", params.content_type);
    if (params?.is_ad !== undefined) qs.set("is_ad", String(params.is_ad));
    if (params?.days) qs.set("days", String(params.days));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return fetchApi<BrandChannelContent[]>(
      `/brand-channels/${advertiserId}/contents${q ? "?" + q : ""}`
    );
  },

  // Product Categories
  getProductCategories: (days = 30) =>
    fetchApi<ProductCategoryTree[]>(`/products/categories?days=${days}`),

  getProductCategoryDetail: (id: number, days = 30) =>
    fetchApi<ProductCategoryDetail>(`/products/categories/${id}?days=${days}`),

  getProductCategoryAdvertisers: (id: number, days = 30, limit = 50) =>
    fetchApi<ProductCategoryAdvertiser[]>(
      `/products/categories/${id}/advertisers?days=${days}&limit=${limit}`
    ),

  // Meta Signals
  getMetaSignalOverview: (advertiserId: number) =>
    fetchApi<MetaSignalOverview>(`/meta-signals/${advertiserId}/overview`),

  getMetaSignalActivity: (advertiserId: number, days = 30) =>
    fetchApi<ActivityScorePoint[]>(`/meta-signals/${advertiserId}/activity?days=${days}`),

  getMetaSignalTopActive: (days = 30, limit = 10) =>
    fetchApi<MetaSignalTopItem[]>(`/meta-signals/top-active?days=${days}&limit=${limit}`),

  // SmartStore Sales
  smartstoreTrack: (productUrl: string, label?: string) =>
    fetchApi<SmartStoreTracked>("/smartstore/track", {
      method: "POST",
      body: JSON.stringify({ product_url: productUrl, label }),
    }),

  smartstoreTracked: () =>
    fetchApi<SmartStoreTracked[]>("/smartstore/tracked"),

  smartstoreUntrack: (id: number) =>
    fetchApi<{ status: string }>(`/smartstore/tracked/${id}`, { method: "DELETE" }),

  smartstoreSales: (productUrl: string, days = 30) =>
    fetchApi<SmartStoreSalesData>(`/smartstore/sales?product_url=${encodeURIComponent(productUrl)}&days=${days}`),

  smartstoreDashboard: (days = 30) =>
    fetchApi<SmartStoreDashboard>(`/smartstore/dashboard?days=${days}`),

  // Advertiser Trends
  getAdvertiserTrends: (days = 30, limit = 20) =>
    fetchApi<AdvertiserTrendsSummary>(
      `/advertiser-trends/summary?days=${days}&limit=${limit}`
    ),

  // Social Impact
  getSocialImpactOverview: (advertiserId: number) =>
    fetchApi<SocialImpactOverview>(`/social-impact/${advertiserId}/overview`),

  getSocialImpactTimeline: (advertiserId: number, days = 30) =>
    fetchApi<SocialImpactTimelinePoint[]>(`/social-impact/${advertiserId}/timeline?days=${days}`),

  getSocialImpactNews: (advertiserId: number, days = 30) =>
    fetchApi<NewsMention[]>(`/social-impact/${advertiserId}/news?days=${days}`),

  getSocialImpactTopImpact: (days = 30, limit = 10) =>
    fetchApi<SocialImpactTopItem[]>(`/social-impact/top-impact?days=${days}&limit=${limit}`),

  // Payments
  preparePayment: (plan: string, period: string) =>
    fetchApi<{
      merchant_uid: string;
      amount: number;
      plan: string;
      plan_period: string;
      buyer_email: string;
      buyer_name: string;
      store_id: string;
      channel_key: string;
      payment_id: number;
    }>("/payments/prepare", {
      method: "POST",
      body: JSON.stringify({ plan, plan_period: period }),
    }),

  completePayment: (impUid: string, merchantUid: string) =>
    fetchApi<{ status: string; message: string; payment_id: number }>(
      "/payments/complete",
      {
        method: "POST",
        body: JSON.stringify({ imp_uid: impUid, merchant_uid: merchantUid }),
      }
    ),

  // Admin: User/Payment management
  adminListUsers: (token: string) =>
    fetchApi<Array<{
      id: number;
      email: string;
      name: string | null;
      company_name: string | null;
      role: string;
      plan: string | null;
      plan_period: string | null;
      is_active: boolean;
      plan_expires_at: string | null;
      trial_started_at: string | null;
      created_at: string | null;
    }>>("/admin/users", {
      headers: { Authorization: `Bearer ${token}` },
    }),

  adminListPayments: (token: string, status?: string) =>
    fetchApi<Array<{
      id: number;
      user_id: number;
      email: string;
      company_name: string | null;
      plan: string;
      plan_period: string;
      amount: number;
      status: string;
      paid_at: string | null;
      created_at: string | null;
    }>>(`/admin/payments${status ? `?status=${status}` : ""}`, {
      headers: { Authorization: `Bearer ${token}` },
    }),

  adminActivatePayment: (id: number, token: string) =>
    fetchApi<{ status: string; payment_id: number }>(
      `/admin/payments/${id}/activate`,
      { method: "POST", headers: { Authorization: `Bearer ${token}` } }
    ),

  adminRejectPayment: (id: number, token: string) =>
    fetchApi<{ status: string }>(`/admin/payments/${id}/reject`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }),

  adminExtendUser: (userId: number, days: number, token: string) =>
    fetchApi<{ status: string; new_expires_at: string }>(
      `/admin/users/${userId}/extend?days=${days}`,
      { method: "POST", headers: { Authorization: `Bearer ${token}` } }
    ),

  adminDeactivateUser: (userId: number, token: string) =>
    fetchApi<{ status: string }>(`/admin/users/${userId}/deactivate`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }),

  // Advertiser Favorites
  getFavorites: (category?: string) => {
    const qs = category && category !== "all" ? `?category=${category}` : "";
    return fetchApi<FavoriteAdvertiser[]>(`/advertisers/favorites${qs}`);
  },

  addFavorite: (advertiserId: number, category = "other", note?: string) =>
    fetchApi<FavoriteToggleResponse>(`/advertisers/${advertiserId}/favorite`, {
      method: "POST",
      body: JSON.stringify({ category, notes: note || null }),
    }),

  removeFavorite: (advertiserId: number) =>
    fetchApi<FavoriteToggleResponse>(`/advertisers/${advertiserId}/favorite`, {
      method: "DELETE",
    }),

  updateFavorite: (advertiserId: number, data: { category?: string; notes?: string; is_pinned?: boolean }) =>
    fetchApi<FavoriteAdvertiser>(`/advertisers/${advertiserId}/favorite`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ── LII (Launch Impact) ──
  getImpactByAdvertiser: (advertiserId: number) =>
    fetchApi<LIIAdvertiserImpact[]>(`/impact/by-advertiser/${advertiserId}`),

  // Admin: Media Sources
  adminListMediaSources: () =>
    fetchApi<MediaSourceItem[]>("/impact/media-sources"),

  adminCreateMediaSource: (data: Partial<MediaSourceItem>) =>
    fetchApi<MediaSourceItem>("/impact/media-sources", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  adminUpdateMediaSource: (id: number, data: Partial<MediaSourceItem>) =>
    fetchApi<MediaSourceItem>(`/impact/media-sources/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  adminCreateParseProfile: (data: Partial<ParseProfileItem>) =>
    fetchApi<ParseProfileItem>("/impact/parse-profiles", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  adminGetCrawlLog: () =>
    fetchApi<CrawlLogItem[]>("/impact/crawl-log"),

  adminTriggerLIICrawl: () =>
    fetchApi<{ status: string; stats: Record<string, number> }>("/impact/crawl-now", { method: "POST" }),

  adminTriggerLIICalcScores: () =>
    fetchApi<{ status: string; stats: Record<string, number> }>("/impact/calc-scores", { method: "POST" }),

  // ── Generic helpers (strip /api prefix if present) ──
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  get: <T = any>(path: string): Promise<T> => {
    const p = path.startsWith("/api/") ? path.slice(4) : path;
    return fetchApi<T>(p);
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  post: <T = any>(path: string, body?: unknown): Promise<T> => {
    const p = path.startsWith("/api/") ? path.slice(4) : path;
    return fetchApi<T>(p, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  // ── Campaign Journey & Lift ──
  getCampaignDetail: (id: number) =>
    fetchApi<CampaignDetail>(`/campaigns/${id}/detail`),

  getCampaignJourney: (id: number, params?: { stage?: string; days?: number }) => {
    const qs = new URLSearchParams();
    if (params?.stage) qs.set("stage", params.stage);
    if (params?.days) qs.set("days", String(params.days));
    const q = qs.toString();
    return fetchApi<JourneyEvent[]>(`/campaigns/${id}/journey${q ? "?" + q : ""}`);
  },

  getCampaignLift: (id: number) =>
    fetchApi<CampaignLiftData | null>(`/campaigns/${id}/lift`),

  getCampaignEffect: (id: number) =>
    fetchApi<CampaignEffect>(`/campaigns/${id}/effect`),

  updateCampaign: (id: number, data: Partial<CampaignDetail>) =>
    fetchApi<CampaignDetail>(`/campaigns/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ── Marketing Schedule ──
  getMarketingSchedule: (advertiserId: number, days = 90) =>
    fetchApi<MarketingScheduleData>(
      `/marketing-schedule?advertiser_id=${advertiserId}&days=${days}`
    ),

  getMarketingOverview: (days = 30, limit = 20) =>
    fetchApi<MarketingOverviewItem[]>(
      `/marketing-schedule/overview?days=${days}&limit=${limit}`
    ),

  getMarketingDetections: (days = 7, limit = 50) =>
    fetchApi<MarketingDetectionEvent[]>(
      `/marketing-schedule/detection?days=${days}&limit=${limit}`
    ),

};

// ── Meta Signal types ──
export interface MetaSignalOverview {
  advertiser_id: number;
  date: string | null;
  smartstore_score: number;
  traffic_score: number;
  activity_score: number;
  panel_calibration: number;
  composite_score: number;
  spend_multiplier: number;
  activity_state: string | null;
  raw_factors: Record<string, unknown> | null;
}

export interface SmartStoreSnapshot {
  id: number;
  advertiser_id: number;
  store_name: string | null;
  product_url: string | null;
  product_name: string | null;
  review_count: number | null;
  review_delta: number;
  avg_rating: number | null;
  price: number | null;
  discount_pct: number;
  estimated_sales_level: string | null;
  stock_quantity: number | null;
  purchase_cnt: number | null;
  purchase_cnt_delta: number;
  estimated_daily_sales: number | null;
  estimation_method: string | null;
  category_name: string | null;
  seller_grade: string | null;
  captured_at: string | null;
}

export interface SmartStoreTracked {
  id: number;
  product_url: string;
  store_name: string | null;
  product_name: string | null;
  label: string | null;
  is_active: boolean;
  created_at: string | null;
}

export interface SmartStoreSalesEstimation {
  estimated_daily_sales: number;
  estimated_daily_revenue: number;
  estimated_monthly_revenue: number;
  methods: Record<string, number>;
  primary_method: string | null;
  confidence: number;
}

export interface SmartStoreSalesData {
  product_url: string;
  store_name: string | null;
  product_name: string | null;
  category_name: string | null;
  seller_grade: string | null;
  latest: {
    stock_quantity: number | null;
    purchase_cnt: number | null;
    review_count: number | null;
    price: number | null;
    avg_rating: number | null;
    wishlist_count: number | null;
    discount_pct: number | null;
  } | null;
  estimation: SmartStoreSalesEstimation;
  timeline: {
    date: string;
    stock_quantity: number | null;
    purchase_cnt: number | null;
    review_count: number | null;
    review_delta: number | null;
    price: number | null;
    wishlist_count: number | null;
    avg_rating: number | null;
    estimated_daily_sales: number | null;
  }[];
  snapshot_count: number;
}

export interface SmartStoreDashboard {
  total_tracked: number;
  total_with_data: number;
  total_daily_sales: number;
  total_daily_revenue: number;
  total_monthly_revenue: number;
  top_sellers: {
    product_url: string;
    store_name: string | null;
    product_name: string | null;
    price: number | null;
    review_count: number | null;
    stock_quantity: number | null;
    estimation: SmartStoreSalesEstimation;
  }[];
  alerts: { product_url: string; type: string; message: string }[];
}

export interface TrafficSignal {
  id: number;
  advertiser_id: number;
  date: string;
  brand_keyword: string | null;
  naver_search_index: number | null;
  google_trend_index: number | null;
  composite_index: number | null;
  wow_change_pct: number | null;
  traffic_level: string | null;
}

export interface ActivityScorePoint {
  id: number;
  advertiser_id: number;
  date: string;
  active_campaigns: number;
  new_creatives: number;
  creative_variants: number;
  social_post_count: number;
  channel_count: number;
  composite_score: number;
  activity_state: string | null;
}

export interface PanelSummary {
  advertiser_id: number;
  ai_observations: number;
  human_observations: number;
  total_observations: number;
  channels: string[];
  panel_calibration: number;
}

export interface MetaSignalTopItem {
  advertiser_id: number;
  composite_score: number;
  spend_multiplier: number;
  activity_score: number;
  advertiser_name: string;
  brand_name: string | null;
}

// Social Impact types
export interface SocialImpactOverview {
  advertiser_id: number;
  date: string | null;
  news_impact_score: number;
  social_posting_score: number;
  search_lift_score: number;
  composite_score: number;
  news_article_count: number;
  news_sentiment_avg: number | null;
  social_engagement_delta_pct: number | null;
  social_posting_delta_pct: number | null;
  search_volume_delta_pct: number | null;
  has_active_campaign: boolean;
  impact_phase: string | null;
  factors: Record<string, unknown> | null;
}

export interface SocialImpactTimelinePoint {
  date: string;
  news_impact_score: number;
  social_posting_score: number;
  search_lift_score: number;
  composite_score: number;
  impact_phase: string | null;
  has_active_campaign: boolean;
}

export interface NewsMention {
  id: number;
  advertiser_id: number;
  source: string;
  article_url: string;
  article_title: string | null;
  article_description: string | null;
  publisher: string | null;
  published_at: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  is_pr: boolean;
}

export interface SocialImpactTopItem {
  advertiser_id: number;
  advertiser_name: string | null;
  brand_name: string | null;
  composite_score: number;
  impact_phase: string | null;
  news_impact_score: number;
  social_posting_score: number;
  search_lift_score: number;
}

// ── Advertiser Favorites ──

export interface FavoriteAdvertiser {
  id: number;
  user_id: number;
  advertiser_id: number;
  advertiser_name: string | null;
  brand_name: string | null;
  category: string;
  notes: string | null;
  is_pinned: boolean;
  sort_order: number;
  recent_ad_count: number;
  total_est_spend: number;
  // frontend aliases
  ad_count_30d?: number;
  est_spend_30d?: number;
  created_at: string | null;
  updated_at: string | null;
  industry_name: string | null;
  website: string | null;
  logo_url: string | null;
}

export interface FavoriteToggleResponse {
  status: string;
  favorite_id: number | null;
  is_favorite: boolean;
}

// ── Advertiser Trends ──

export interface AdvertiserTrendItem {
  advertiser_id: number;
  advertiser_name: string;
  brand_name: string | null;
  industry_id: number | null;
  current_score: number;
  prev_score: number;
  delta: number;
  delta_pct: number;
  activity_state: string | null;
}

export interface NewEntrantItem {
  advertiser_id: number;
  advertiser_name: string | null;
  brand_name: string | null;
  entered_at: string | null;
  campaign_count: number;
}

export interface ExitedItem {
  advertiser_id: number;
  advertiser_name: string | null;
  brand_name: string | null;
  last_active: string | null;
}

export interface ChannelTrendItem {
  channel: string;
  current_count: number;
  prev_count: number;
  growth_pct: number;
}

export interface IndustrySummaryItem {
  industry_id: number;
  industry_name: string;
  active_advertisers: number;
  avg_activity: number;
}

export interface AdvertiserTrendsSummary {
  period_days: number;
  analysis_date: string;
  total_active_advertisers: number;
  avg_activity_score: number;
  rising: AdvertiserTrendItem[];
  falling: AdvertiserTrendItem[];
  new_entrants: NewEntrantItem[];
  exited: ExitedItem[];
  channel_trends: ChannelTrendItem[];
  industry_summary: IndustrySummaryItem[];
}

export interface AdvertiserTrajectoryPoint {
  date: string;
  activity_score: number;
  activity_state: string | null;
  active_campaigns: number;
  new_creatives: number;
  /** 해당일 추정 매체비 (KRW) */
  est_daily_spend: number;
}

export interface AdvertiserTrajectory {
  advertiser_id: number;
  advertiser_name: string;
  brand_name: string | null;
  timeline: AdvertiserTrajectoryPoint[];
  current_state: string | null;
  score_trend: string;
}

// Admin types
export interface AdminStats {
  total_snapshots: number;
  total_ads: number;
  total_advertisers: number;
  total_keywords: number;
  total_personas: number;
  by_channel: Record<string, number>;
  latest_crawl: string | null;
  db_size_mb: number;
  server_time: string;
}

export interface AdminChannel {
  channel: string;
  snapshots: number;
  ads: number;
  last_crawl: string | null;
}

export interface CrawlChannelStatus {
  channel: string;
  last_crawl_kst: string | null;
  minutes_ago: number | null;
  status: "recent" | "today" | "stale" | "idle";
  total_snapshots: number;
  today_ads: number;
}

export interface CrawlStatusResponse {
  channels: CrawlChannelStatus[];
  summary: {
    total_advertisers: number;
    total_ads: number;
    total_snapshots: number;
    today_total_ads: number;
  };
  server_time_kst: string;
}

export interface ScheduleItem {
  id: string;
  name: string;
  schedule: string;
  schedule_time: string;
  last_run: string | null;
  data_count?: number;
  trigger_endpoint: string;
  description: string;
}

export interface ScheduleCategory {
  id: string;
  name: string;
  description: string;
  items: ScheduleItem[];
}

export interface ScheduleTimeline {
  time: string;
  label: string;
  category: string;
}

export interface ScheduleOverview {
  categories: ScheduleCategory[];
  timeline: ScheduleTimeline[];
  server_time_kst: string;
}


// ── LII (Launch Impact Intelligence) types ──

export interface LaunchProductItem {
  id: number;
  advertiser_id: number;
  name: string;
  category: string;
  launch_date: string;
  product_url: string | null;
  external_id: string | null;
  keywords: string[];
  is_active: boolean;
  created_at: string | null;
}

export interface LIIOverview {
  launch_product_id: number;
  product_name: string;
  category: string;
  launch_date: string;
  days_since_launch: number;
  date: string | null;
  mrs_score: number;
  rv_score: number;
  cs_score: number;
  lii_score: number;
  total_mentions: number;
  impact_phase: string | null;
  factors: Record<string, unknown> | null;
}

export interface LIITimelinePoint {
  date: string;
  mrs_score: number;
  rv_score: number;
  cs_score: number;
  lii_score: number;
  total_mentions: number;
  impact_phase: string | null;
}

export interface LIIMention {
  id: number;
  source_type: string;
  source_platform: string | null;
  url: string;
  title: string | null;
  author: string | null;
  published_at: string | null;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  sentiment: string | null;
  matched_keyword: string | null;
}

export interface LIIRankingItem {
  launch_product_id: number;
  product_name: string;
  advertiser_id: number;
  advertiser_name: string | null;
  category: string;
  launch_date: string | null;
  lii_score: number;
  mrs_score: number;
  rv_score: number;
  cs_score: number;
  total_mentions: number;
  impact_phase: string | null;
}

export interface LIIReaction {
  id: number;
  launch_product_id: number;
  timestamp: string;
  metric_type: string;
  value: number;
  source: string | null;
}

export interface LIIAdvertiserImpact {
  product: {
    id: number;
    name: string;
    category: string;
    launch_date: string | null;
    is_active: boolean;
  };
  latest_score: {
    lii_score: number;
    mrs_score: number;
    rv_score: number;
    cs_score: number;
    total_mentions: number;
    impact_phase: string | null;
    date: string | null;
  };
  mention_count: number;
}

export interface MediaSourceItem {
  id: number;
  name: string;
  url: string;
  connector_type: string;
  weight: number;
  schedule_interval: number;
  is_active: boolean;
  last_crawl_at: string | null;
  error_count: number;
  error_rate: number;
  parse_profile_id: number | null;
  extra_config: Record<string, unknown> | null;
  created_at: string | null;
  mention_count: number;
}

export interface ParseProfileItem {
  id: number;
  name: string;
  list_selector: string | null;
  detail_selector: string | null;
  title_selector: string | null;
  date_selector: string | null;
  content_selector: string | null;
  test_url: string | null;
}

export interface CrawlLogItem {
  media_source_id: number;
  media_source_name: string;
  connector_type: string;
  is_active: boolean;
  last_crawl_at: string | null;
  error_count: number;
  error_rate: number;
  mention_count: number;
}

// ── Marketing Schedule types ──
export interface AdvertiserProductItem {
  id: number;
  advertiser_id: number;
  product_name: string;
  product_category_id: number | null;
  product_category_name: string | null;
  is_flagship: boolean;
  status: string;
  source: string;
  first_ad_seen: string | null;
  last_ad_seen: string | null;
  total_campaigns: number;
  /** 해당 상품의 추정 매체비 누적 합계 (KRW) */
  total_spend_est: number;
  channels: string[];
  ad_count: number;
  model_names?: string[];
  ad_products_used?: string[];
  purposes?: string[];
}

/** 상품별 일간 광고 활동 매트릭스. */
export interface ProductActivityMatrixItem {
  product_id: number;
  date: string;
  channel: string;
  ad_product_name: string | null;
  ad_count: number;
  /** 해당일 추정 매체비 (KRW) */
  est_daily_spend: number;
  unique_creatives: number;
}

export interface MarketingScheduleData {
  advertiser_id: number;
  advertiser_name: string;
  period_days: number;
  products: AdvertiserProductItem[];
  activity_matrix: ProductActivityMatrixItem[];
}

export interface MarketingDetectionEvent {
  advertiser_id: number;
  advertiser_name: string;
  product_name: string;
  event_type: string;
  detected_at: string | null;
  details: Record<string, unknown> | null;
}

/** 마케팅 스케줄 광고주 요약. */
export interface MarketingOverviewItem {
  advertiser_id: number;
  advertiser_name: string;
  brand_name: string | null;
  total_products: number;
  active_products: number;
  /** 전체 상품 추정 매체비 합계 (KRW) */
  total_spend: number;
}

export interface AdProductMasterItem {
  id: number;
  channel: string;
  product_code: string;
  product_name_ko: string;
  product_name_en: string | null;
  format_type: string;
  billing_type: string;
  description: string | null;
  // pricing (absorbed from legacy media_ad_products)
  position_zone: string | null;
  base_price: number | null;
  price_range_min: number | null;
  price_range_max: number | null;
  device: string;
  is_active: boolean;
}
