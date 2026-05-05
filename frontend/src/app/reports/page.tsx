"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  AdvertiserSearchResult,
  AdvertiserSpendReport,
  MediaBreakdownResponse,
  CompetitorList,
  GalleryResponse,
  BrandChannelContent,
  MetaSignalOverview,
  SocialImpactOverview,
  CampaignDetail,
  Campaign,
  LIIAdvertiserImpact,
} from "@/lib/api";
import { formatChannel, formatSpend, CHANNEL_COLORS } from "@/lib/constants";
import { toImageUrl } from "@/lib/image-utils";
import { AdvertiserDownloadDropdown, authDownload } from "@/components/DownloadButtons";
import { isAuthenticated } from "@/lib/auth";
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, LineChart, Line,
} from "recharts";

// ── 타입 ──
interface ShoppingInsightData {
  summary: {
    total_ads: number;
    total_advertisers: number;
    total_spend: number;
    total_categories: number;
    days: number;
  };
  top_categories: { category: string; ad_count: number; advertiser_count: number; est_spend: number; growth_pct: number | null }[];
  channel_distribution: { channel: string; ad_count: number }[];
  top_advertisers: { rank: number; advertiser_id: number; name: string; brand_name: string | null; ad_count: number; categories: string[]; channels: string[]; est_spend: number; activity_state: string | null }[];
  promotion_types: { type: string; count: number }[];
}

interface ReportConfig {
  advertiserId: number | null;
  advertiserName: string;
  days: number;
  sections: {
    overview: boolean;
    spend: boolean;
    media: boolean;
    creatives: boolean;
    socialCreatives: boolean;
    competitors: boolean;
    shopping: boolean;
    metaSignal: boolean;
    socialImpact: boolean;
    campaigns: boolean;
    launchImpact: boolean;
  };
}

const DEFAULT_CONFIG: ReportConfig = {
  advertiserId: null,
  advertiserName: "",
  days: 30,
  sections: {
    overview: true,
    spend: true,
    media: true,
    creatives: true,
    socialCreatives: true,
    competitors: true,
    shopping: true,
    metaSignal: true,
    socialImpact: true,
    campaigns: true,
    launchImpact: true,
  },
};

const SECTION_LABELS: Record<string, string> = {
  overview: "광고주 개요",
  spend: "광고비 현황",
  media: "매체별 비중",
  creatives: "광고 소재",
  socialCreatives: "소셜 소재",
  competitors: "경쟁사 비교",
  shopping: "쇼핑 분석",
  metaSignal: "메타 신호",
  socialImpact: "소셜 임팩트",
  campaigns: "캠페인 상세",
  launchImpact: "런칭 임팩트",
};

const PIE_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

function formatCount(n: number): string {
  if (n >= 100000000) return `${(n / 100000000).toFixed(1)}억`;
  if (n >= 10000) return `${(n / 10000).toFixed(1)}만`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}천`;
  return String(n);
}

// ── 광고주 검색 컴포넌트 ──
function AdvertiserSearch({
  onSelect,
}: {
  onSelect: (id: number, name: string) => void;
}) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  const { data: results } = useQuery({
    queryKey: ["advSearch", q],
    queryFn: () => api.searchAdvertisers(q, 10),
    enabled: q.length >= 1,
  });

  const handleInput = useCallback((val: string) => {
    setQ(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setOpen(true), 200);
  }, []);

  return (
    <div className="relative">
      <input
        type="text"
        value={q}
        onChange={(e) => handleInput(e.target.value)}
        onFocus={() => q.length >= 1 && setOpen(true)}
        placeholder="광고주명 검색..."
        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
      />
      {open && results && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto">
          {results.map((r) => (
            <button
              key={r.id}
              onClick={() => {
                onSelect(r.id, r.name);
                setQ(r.name);
                setOpen(false);
              }}
              className="w-full text-left px-4 py-2.5 hover:bg-indigo-50 text-sm border-b border-gray-100 last:border-0"
            >
              <span className="font-medium">{r.name}</span>
              {r.brand_name && (
                <span className="ml-2 text-xs text-gray-400">{r.brand_name}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 보고서 뷰 ──
function ReportView({ config }: { config: ReportConfig }) {
  const advId = config.advertiserId!;
  const days = config.days;

  // Dynamic section numbering based on which sections are enabled
  const sectionOrder: (keyof ReportConfig["sections"])[] = [
    "overview", "spend", "media", "creatives", "socialCreatives", "competitors", "shopping",
    "metaSignal", "socialImpact", "campaigns", "launchImpact",
  ];
  const sectionNum = (key: keyof ReportConfig["sections"]) => {
    let num = 0;
    for (const k of sectionOrder) {
      if (config.sections[k]) num++;
      if (k === key) return num;
    }
    return num;
  };

  const { data: spend, isLoading: spendLoading } = useQuery({
    queryKey: ["reportSpend", advId, days],
    queryFn: () => api.getAdvertiserSpendReport(advId, days),
    enabled: config.sections.spend || config.sections.overview,
  });

  const { data: media, isLoading: mediaLoading } = useQuery({
    queryKey: ["reportMedia", advId, days],
    queryFn: () => api.getAdvertiserMediaBreakdown(advId, days),
    enabled: config.sections.media || config.sections.overview,
  });

  const { data: gallery } = useQuery({
    queryKey: ["reportGallery", config.advertiserName],
    queryFn: () => api.getGallery({ advertiser: config.advertiserName, limit: 12 }),
    enabled: config.sections.creatives,
  });

  const { data: socialContents } = useQuery({
    queryKey: ["reportSocial", advId, days],
    queryFn: () => api.getBrandChannelContents(advId, { days, limit: 12 }),
    enabled: config.sections.socialCreatives,
  });

  const { data: competitors } = useQuery({
    queryKey: ["reportCompetitors", advId, days],
    queryFn: () => api.getCompetitors(advId, days, 10),
    enabled: config.sections.competitors,
  });

  const { data: shoppingData } = useQuery<ShoppingInsightData>({
    queryKey: ["reportShopping", days],
    queryFn: async () => {
      const res = await fetch(`/api/products/shopping-insight?days=${days}`);
      if (!res.ok) throw new Error("Failed to fetch shopping data");
      return res.json();
    },
    enabled: config.sections.shopping,
  });

  // Meta Signal
  const { data: metaSignal } = useQuery<MetaSignalOverview>({
    queryKey: ["reportMetaSignal", advId],
    queryFn: () => api.getMetaSignalOverview(advId),
    enabled: config.sections.metaSignal,
  });

  // Social Impact
  const { data: socialImpact } = useQuery<SocialImpactOverview>({
    queryKey: ["reportSocialImpact", advId],
    queryFn: () => api.getSocialImpactOverview(advId),
    enabled: config.sections.socialImpact,
  });

  // Campaigns
  const { data: campaignList } = useQuery<Campaign[]>({
    queryKey: ["reportCampaigns", advId],
    queryFn: () => api.getAdvertiserCampaigns(advId),
    enabled: config.sections.campaigns,
  });

  // Campaign Details (fetch detail for up to 10 active campaigns)
  const activeCampaignIds = (campaignList ?? [])
    .filter((c) => c.is_active)
    .slice(0, 10)
    .map((c) => c.id);

  const { data: campaignDetails } = useQuery<(CampaignDetail | null)[]>({
    queryKey: ["reportCampaignDetails", activeCampaignIds],
    queryFn: async () => {
      const results = await Promise.allSettled(
        activeCampaignIds.map((id) => api.getCampaignDetail(id))
      );
      return results.map((r) => (r.status === "fulfilled" ? r.value : null));
    },
    enabled: config.sections.campaigns && activeCampaignIds.length > 0,
  });

  // Launch Impact
  const { data: launchImpacts } = useQuery<LIIAdvertiserImpact[]>({
    queryKey: ["reportLaunchImpact", advId],
    queryFn: () => api.getImpactByAdvertiser(advId),
    enabled: config.sections.launchImpact,
  });

  const isLoading = spendLoading || mediaLoading;

  const now = new Date();
  const reportDate = `${now.getFullYear()}.${String(now.getMonth() + 1).padStart(2, "0")}.${String(now.getDate()).padStart(2, "0")}`;

  return (
    <div className="report-content bg-white" id="report-printable">
      {/* 헤더 */}
      <div className="border-b-2 border-indigo-600 pb-4 mb-8">
        <div className="flex justify-between items-end">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-widest mb-1">AdScope Report</p>
            <h1 className="text-2xl font-bold text-gray-900">
              {config.advertiserName} 광고 분석 보고서
            </h1>
          </div>
          <div className="text-right text-sm text-gray-500">
            <p>분석 기간: 최근 {days}일</p>
            <p>생성일: {reportDate}</p>
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="text-center py-20 text-gray-400">데이터 로딩 중...</div>
      )}

      {/* 1. 광고주 개요 */}
      {config.sections.overview && media && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-indigo-500 pl-3 mb-4">
            {sectionNum("overview")}. 광고주 개요
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="총 광고 수" value={String(media.total_ads)} />
            <StatCard label="추정 광고비" value={formatSpend(media.total_est_spend)} />
            <StatCard label="활용 매체" value={`${media.by_channel.length}개 채널`} />
            <StatCard
              label="주력 매체"
              value={media.categories.length > 0 ? media.categories[0].category : "-"}
            />
          </div>
          {media.industry_name && (
            <p className="mt-3 text-sm text-gray-500">
              산업: <span className="font-medium text-gray-700">{media.industry_name}</span>
              {media.website && (
                <> | 웹사이트: <span className="font-medium text-gray-700">{media.website}</span></>
              )}
            </p>
          )}
        </section>
      )}

      {/* 2. 광고비 현황 */}
      {config.sections.spend && spend && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-indigo-500 pl-3 mb-4">
            {sectionNum("spend")}. 광고비 현황
          </h2>
          {/* 채널별 광고비 표 */}
          <div className="overflow-x-auto mb-6">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-200">
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">채널</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">추정 광고비</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">광고 수</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">상태</th>
                </tr>
              </thead>
              <tbody>
                {spend.by_channel.map((ch) => (
                  <tr key={ch.channel} className="border-b border-gray-100">
                    <td className="py-2 px-3 font-medium">{formatChannel(ch.channel)}</td>
                    <td className="py-2 px-3 text-right">{formatSpend(ch.est_spend)}</td>
                    <td className="py-2 px-3 text-right">{ch.ad_count}</td>
                    <td className="py-2 px-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${ch.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                        {ch.is_active ? "Active" : "Paused"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-gray-300 font-bold">
                  <td className="py-2 px-3">합계</td>
                  <td className="py-2 px-3 text-right">{formatSpend(spend.total_est_spend)}</td>
                  <td className="py-2 px-3 text-right">
                    {spend.by_channel.reduce((s, c) => s + c.ad_count, 0)}
                  </td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* 일별 추세 */}
          {spend.daily_trend.length > 0 && (
            <div className="h-48">
              <p className="text-xs font-semibold text-gray-500 mb-2">일별 추정 광고비 추세</p>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={spend.daily_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`} />
                  <Tooltip formatter={(v: number) => formatSpend(v)} />
                  <Line type="monotone" dataKey="spend" stroke="#6366f1" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>
      )}

      {/* 3. 매체별 비중 */}
      {config.sections.media && media && media.categories.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-indigo-500 pl-3 mb-4">
            {sectionNum("media")}. 매체별 비중
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* 도넛 차트 */}
            <div className="flex justify-center">
              <PieChart width={280} height={280}>
                <Pie
                  data={media.categories}
                  dataKey="ad_count"
                  nameKey="category"
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={110}
                  paddingAngle={2}
                  label={({ category, ratio }) => `${category} ${(ratio * 100).toFixed(0)}%`}
                  labelLine={{ strokeWidth: 1 }}
                >
                  {media.categories.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => `${v}건`} />
              </PieChart>
            </div>

            {/* 채널별 바 차트 */}
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={media.by_channel} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis
                    dataKey="channel"
                    type="category"
                    width={100}
                    tick={{ fontSize: 10 }}
                    tickFormatter={formatChannel}
                  />
                  <Tooltip
                    formatter={(v: number) => `${v}건`}
                    labelFormatter={formatChannel}
                  />
                  <Bar dataKey="ad_count" fill="#6366f1" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>
      )}

      {/* 4. 광고 소재 */}
      {config.sections.creatives && gallery && gallery.items.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-indigo-500 pl-3 mb-4">
            {sectionNum("creatives")}. 광고 소재
            <span className="ml-2 text-sm font-normal text-gray-400">
              (최근 {gallery.items.length}건)
            </span>
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {gallery.items.map((item) => {
              const imgUrl = toImageUrl(item.creative_image_path);
              return (
                <div key={item.id} className="border rounded-lg overflow-hidden bg-gray-50">
                  {imgUrl ? (
                    <div className="relative w-full h-32">
                      <img
                        src={imgUrl}
                        alt={item.ad_text || ""}
                        className="w-full h-32 object-cover"
                        referrerPolicy="no-referrer"
                        onError={(e) => {
                          const el = e.target as HTMLImageElement;
                          el.style.display = "none";
                          const placeholder = el.nextElementSibling as HTMLElement;
                          if (placeholder) placeholder.style.display = "flex";
                        }}
                      />
                      <div className="w-full h-32 bg-gray-200 items-center justify-center text-xs text-gray-400" style={{ display: "none" }}>
                        No Image
                      </div>
                    </div>
                  ) : (
                    <div className="w-full h-32 bg-gray-200 flex items-center justify-center text-xs text-gray-400">
                      No Image
                    </div>
                  )}
                  <div className="p-2">
                    <p className="text-xs text-gray-600 truncate">{item.ad_text || item.advertiser_name_raw || "-"}</p>
                    <div className="flex items-center gap-1 mt-0.5">
                      <span className="text-[10px] px-1.5 py-0.5 bg-indigo-50 text-indigo-600 rounded font-medium">
                        {formatChannel(item.channel)}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 5. 소셜 소재 */}
      {config.sections.socialCreatives && socialContents && socialContents.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-emerald-500 pl-3 mb-4">
            {sectionNum("socialCreatives")}. 소셜 소재
            <span className="ml-2 text-sm font-normal text-gray-400">
              (최근 {socialContents.length}건)
            </span>
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {socialContents.map((item) => (
              <div key={item.id} className="border rounded-lg overflow-hidden bg-gray-50">
                {item.thumbnail_url ? (
                  <div className="relative w-full h-32">
                    <img
                      src={item.thumbnail_url}
                      alt={item.title || ""}
                      className="w-full h-32 object-cover"
                      referrerPolicy="no-referrer"
                      onError={(e) => {
                        const el = e.target as HTMLImageElement;
                        el.style.display = "none";
                        const placeholder = el.nextElementSibling as HTMLElement;
                        if (placeholder) placeholder.style.display = "flex";
                      }}
                    />
                    <div className="w-full h-32 bg-gray-200 items-center justify-center text-xs text-gray-400" style={{ display: "none" }}>
                      No Thumbnail
                    </div>
                  </div>
                ) : (
                  <div className="w-full h-32 bg-gray-200 flex items-center justify-center text-xs text-gray-400">
                    No Thumbnail
                  </div>
                )}
                <div className="p-2">
                  <p className="text-xs text-gray-600 truncate">{item.title || "-"}</p>
                  <div className="flex items-center gap-1 mt-0.5">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                      item.platform === "youtube"
                        ? "bg-red-50 text-red-600"
                        : item.platform === "instagram"
                        ? "bg-pink-50 text-pink-600"
                        : "bg-blue-50 text-blue-600"
                    }`}>
                      {item.platform === "youtube" ? "YouTube" : item.platform === "instagram" ? "Instagram" : item.platform}
                    </span>
                    {item.content_type && (
                      <span className="text-[10px] text-gray-400">{item.content_type}</span>
                    )}
                    {item.is_ad_content && (
                      <span className="text-[10px] px-1 py-0.5 bg-amber-50 text-amber-600 rounded">AD</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-[10px] text-gray-400">
                    {item.view_count != null && <span>{formatCount(item.view_count)} views</span>}
                    {item.like_count != null && <span>{formatCount(item.like_count)} likes</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 경쟁사 비교 */}
      {config.sections.competitors && competitors && competitors.competitors.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-indigo-500 pl-3 mb-4">
            {sectionNum("competitors")}. 경쟁사 비교
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-200">
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">순위</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">경쟁사</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">유사도</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">키워드 겹침</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">채널 겹침</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">동시 노출</th>
                </tr>
              </thead>
              <tbody>
                {competitors.competitors.slice(0, 10).map((c, i) => (
                  <tr key={c.competitor_id} className="border-b border-gray-100">
                    <td className="py-2 px-3 font-medium text-gray-400">{i + 1}</td>
                    <td className="py-2 px-3 font-medium">{c.competitor_name}</td>
                    <td className="py-2 px-3 text-right">{c.affinity_score.toFixed(0)}%</td>
                    <td className="py-2 px-3 text-right">{c.keyword_overlap.toFixed(0)}%</td>
                    <td className="py-2 px-3 text-right">{c.channel_overlap.toFixed(0)}%</td>
                    <td className="py-2 px-3 text-right">{c.co_occurrence_count}회</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* 쇼핑 분석 */}
      {config.sections.shopping && shoppingData && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-emerald-500 pl-3 mb-4">
            {sectionNum("shopping")}. 쇼핑 분석
          </h2>

          {/* 쇼핑 KPI */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="카테고리" value={String(shoppingData.summary.total_categories)} />
            <StatCard label="광고주" value={String(shoppingData.summary.total_advertisers)} />
            <StatCard label="광고 수" value={String(shoppingData.summary.total_ads)} />
            <StatCard label="추정 광고비" value={shoppingData.summary.total_spend > 0 ? formatSpend(shoppingData.summary.total_spend) : "-"} />
          </div>

          {/* 카테고리별 광고 현황 */}
          {shoppingData.top_categories.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">카테고리별 광고 현황</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b-2 border-gray-200">
                      <th className="text-left py-2 px-3 font-semibold text-gray-600">카테고리</th>
                      <th className="text-right py-2 px-3 font-semibold text-gray-600">광고 수</th>
                      <th className="text-right py-2 px-3 font-semibold text-gray-600">광고주</th>
                      <th className="text-right py-2 px-3 font-semibold text-gray-600">추정 광고비</th>
                      <th className="text-right py-2 px-3 font-semibold text-gray-600">증감</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shoppingData.top_categories.slice(0, 10).map((cat) => (
                      <tr key={cat.category} className="border-b border-gray-100">
                        <td className="py-2 px-3 font-medium">{cat.category}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{cat.ad_count}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{cat.advertiser_count}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{cat.est_spend > 0 ? formatSpend(cat.est_spend) : "-"}</td>
                        <td className="py-2 px-3 text-right">
                          {cat.growth_pct !== null ? (
                            <span className={`text-xs font-medium ${cat.growth_pct > 0 ? "text-emerald-600" : "text-red-500"}`}>
                              {cat.growth_pct > 0 ? "+" : ""}{cat.growth_pct}%
                            </span>
                          ) : (
                            <span className="text-xs text-gray-300">--</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 채널별 분포 */}
          {shoppingData.channel_distribution.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">채널별 분포</h3>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={shoppingData.channel_distribution} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis type="number" tick={{ fontSize: 10 }} />
                    <YAxis
                      dataKey="channel"
                      type="category"
                      width={100}
                      tick={{ fontSize: 10 }}
                      tickFormatter={formatChannel}
                    />
                    <Tooltip
                      formatter={(v: number) => `${v}건`}
                      labelFormatter={formatChannel}
                    />
                    <Bar dataKey="ad_count" fill="#10b981" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* 광고주 랭킹 */}
          {shoppingData.top_advertisers.length > 0 && (
            <div className="mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">광고주 랭킹</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b-2 border-gray-200">
                      <th className="text-left py-2 px-3 font-semibold text-gray-600">#</th>
                      <th className="text-left py-2 px-3 font-semibold text-gray-600">광고주</th>
                      <th className="text-right py-2 px-3 font-semibold text-gray-600">광고 수</th>
                      <th className="text-right py-2 px-3 font-semibold text-gray-600">추정 광고비</th>
                      <th className="text-left py-2 px-3 font-semibold text-gray-600">카테고리</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shoppingData.top_advertisers.slice(0, 10).map((adv) => (
                      <tr key={adv.advertiser_id} className="border-b border-gray-100">
                        <td className="py-2 px-3 text-gray-400">{adv.rank}</td>
                        <td className="py-2 px-3 font-medium">{adv.name}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{adv.ad_count}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{adv.est_spend > 0 ? formatSpend(adv.est_spend) : "-"}</td>
                        <td className="py-2 px-3">
                          <div className="flex flex-wrap gap-1">
                            {adv.categories.slice(0, 3).map((c) => (
                              <span key={c} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-600">{c}</span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 프로모션 유형 */}
          {shoppingData.promotion_types.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">프로모션 유형</h3>
              <div className="flex flex-wrap gap-2">
                {shoppingData.promotion_types.map((p) => (
                  <span
                    key={p.type}
                    className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200"
                  >
                    {p.type}
                    <span className="font-bold tabular-nums">{p.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* 메타 신호 */}
      {config.sections.metaSignal && metaSignal && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-violet-500 pl-3 mb-4">
            {sectionNum("metaSignal")}. 메타 신호
          </h2>
          <p className="text-xs text-gray-500 mb-4">
            광고주의 복합 활동 지표를 기반으로 산출된 메타 신호 현황입니다.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
            <StatCard label="종합 점수" value={metaSignal.composite_score.toFixed(1)} />
            <StatCard
              label="활동 상태"
              value={metaSignal.activity_state ?? "-"}
            />
            <StatCard label="광고비 배수" value={`x${metaSignal.spend_multiplier.toFixed(2)}`} />
            <StatCard label="스마트스토어" value={metaSignal.smartstore_score.toFixed(1)} />
            <StatCard label="트래픽 지수" value={metaSignal.traffic_score.toFixed(1)} />
            <StatCard label="활동 점수" value={metaSignal.activity_score.toFixed(1)} />
          </div>
          {/* 시각적 게이지 바 */}
          <div className="space-y-3">
            {[
              { label: "종합 점수", value: metaSignal.composite_score, color: "bg-violet-500" },
              { label: "스마트스토어", value: metaSignal.smartstore_score, color: "bg-emerald-500" },
              { label: "트래픽", value: metaSignal.traffic_score, color: "bg-blue-500" },
              { label: "활동", value: metaSignal.activity_score, color: "bg-amber-500" },
            ].map((item) => (
              <div key={item.label} className="flex items-center gap-3">
                <span className="text-xs text-gray-600 w-24 text-right">{item.label}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-3 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${item.color} transition-all`}
                    style={{ width: `${Math.min(item.value, 100)}%` }}
                  />
                </div>
                <span className="text-xs font-semibold text-gray-700 w-10 tabular-nums">
                  {item.value.toFixed(1)}
                </span>
              </div>
            ))}
          </div>
          {metaSignal.panel_calibration > 0 && (
            <p className="mt-3 text-xs text-gray-400">
              패널 보정값: {metaSignal.panel_calibration.toFixed(2)}
              {metaSignal.date && <> | 기준일: {metaSignal.date}</>}
            </p>
          )}
        </section>
      )}

      {/* 소셜 임팩트 */}
      {config.sections.socialImpact && socialImpact && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-pink-500 pl-3 mb-4">
            {sectionNum("socialImpact")}. 소셜 임팩트
          </h2>
          <p className="text-xs text-gray-500 mb-4">
            뉴스 보도, 소셜 활동, 검색량 변화를 종합한 소셜 영향력 분석입니다.
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="종합 점수" value={socialImpact.composite_score.toFixed(1)} />
            <StatCard label="뉴스 임팩트" value={socialImpact.news_impact_score.toFixed(1)} />
            <StatCard label="소셜 포스팅" value={socialImpact.social_posting_score.toFixed(1)} />
            <StatCard label="검색 리프트" value={socialImpact.search_lift_score.toFixed(1)} />
          </div>

          {/* 상세 지표 테이블 */}
          <div className="overflow-x-auto mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-200">
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">지표</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">값</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">변화율</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-gray-100">
                  <td className="py-2 px-3 font-medium">뉴스 기사 수</td>
                  <td className="py-2 px-3 text-right tabular-nums">{socialImpact.news_article_count}</td>
                  <td className="py-2 px-3 text-right">-</td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-2 px-3 font-medium">뉴스 감성 평균</td>
                  <td className="py-2 px-3 text-right tabular-nums">
                    {socialImpact.news_sentiment_avg != null ? socialImpact.news_sentiment_avg.toFixed(2) : "-"}
                  </td>
                  <td className="py-2 px-3 text-right">-</td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-2 px-3 font-medium">소셜 인게이지먼트</td>
                  <td className="py-2 px-3 text-right">-</td>
                  <td className="py-2 px-3 text-right">
                    {socialImpact.social_engagement_delta_pct != null ? (
                      <span className={`text-xs font-medium ${socialImpact.social_engagement_delta_pct > 0 ? "text-emerald-600" : socialImpact.social_engagement_delta_pct < 0 ? "text-red-500" : "text-gray-500"}`}>
                        {socialImpact.social_engagement_delta_pct > 0 ? "+" : ""}
                        {socialImpact.social_engagement_delta_pct.toFixed(1)}%
                      </span>
                    ) : "-"}
                  </td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-2 px-3 font-medium">소셜 포스팅</td>
                  <td className="py-2 px-3 text-right">-</td>
                  <td className="py-2 px-3 text-right">
                    {socialImpact.social_posting_delta_pct != null ? (
                      <span className={`text-xs font-medium ${socialImpact.social_posting_delta_pct > 0 ? "text-emerald-600" : socialImpact.social_posting_delta_pct < 0 ? "text-red-500" : "text-gray-500"}`}>
                        {socialImpact.social_posting_delta_pct > 0 ? "+" : ""}
                        {socialImpact.social_posting_delta_pct.toFixed(1)}%
                      </span>
                    ) : "-"}
                  </td>
                </tr>
                <tr className="border-b border-gray-100">
                  <td className="py-2 px-3 font-medium">검색량</td>
                  <td className="py-2 px-3 text-right">-</td>
                  <td className="py-2 px-3 text-right">
                    {socialImpact.search_volume_delta_pct != null ? (
                      <span className={`text-xs font-medium ${socialImpact.search_volume_delta_pct > 0 ? "text-emerald-600" : socialImpact.search_volume_delta_pct < 0 ? "text-red-500" : "text-gray-500"}`}>
                        {socialImpact.search_volume_delta_pct > 0 ? "+" : ""}
                        {socialImpact.search_volume_delta_pct.toFixed(1)}%
                      </span>
                    ) : "-"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap gap-2">
            {socialImpact.impact_phase && (
              <span className="inline-flex items-center text-xs px-2.5 py-1.5 rounded-full bg-pink-50 text-pink-700 border border-pink-200 font-medium">
                임팩트 단계: {socialImpact.impact_phase}
              </span>
            )}
            {socialImpact.has_active_campaign && (
              <span className="inline-flex items-center text-xs px-2.5 py-1.5 rounded-full bg-green-50 text-green-700 border border-green-200 font-medium">
                캠페인 활성
              </span>
            )}
          </div>
        </section>
      )}

      {/* 캠페인 상세 */}
      {config.sections.campaigns && campaignList && campaignList.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-cyan-500 pl-3 mb-4">
            {sectionNum("campaigns")}. 캠페인 상세
            <span className="ml-2 text-sm font-normal text-gray-400">
              (전체 {campaignList.length}건, 활성 {campaignList.filter((c) => c.is_active).length}건)
            </span>
          </h2>

          {/* 캠페인 요약 KPI */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="전체 캠페인" value={String(campaignList.length)} />
            <StatCard label="활성 캠페인" value={String(campaignList.filter((c) => c.is_active).length)} />
            <StatCard
              label="총 추정 광고비"
              value={formatSpend(campaignList.reduce((s, c) => s + (c.total_est_spend || 0), 0))}
            />
            <StatCard
              label="활용 채널"
              value={`${new Set(campaignList.map((c) => c.channel)).size}개`}
            />
          </div>

          {/* 캠페인 목록 테이블 */}
          <div className="overflow-x-auto mb-6">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-200">
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">캠페인명</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">채널</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">목적</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">추정 광고비</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">상태</th>
                </tr>
              </thead>
              <tbody>
                {campaignList.slice(0, 15).map((c, idx) => {
                  const detail = campaignDetails?.find(
                    (d) => d && d.id === c.id
                  );
                  return (
                    <tr key={c.id} className="border-b border-gray-100">
                      <td className="py-2 px-3 font-medium">
                        {detail?.campaign_name || `캠페인 #${c.id}`}
                      </td>
                      <td className="py-2 px-3">
                        <span className="text-[10px] px-1.5 py-0.5 bg-cyan-50 text-cyan-600 rounded font-medium">
                          {formatChannel(c.channel)}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-xs text-gray-600">
                        {detail?.objective || "-"}
                      </td>
                      <td className="py-2 px-3 text-right tabular-nums">
                        {formatSpend(c.total_est_spend)}
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            c.is_active
                              ? "bg-green-100 text-green-700"
                              : "bg-gray-100 text-gray-500"
                          }`}
                        >
                          {c.is_active ? "Active" : "Ended"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 캠페인 상세 카드 (enriched details) */}
          {campaignDetails && campaignDetails.filter(Boolean).length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700 mb-3">주요 캠페인 상세</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {campaignDetails
                  .filter((d): d is CampaignDetail => d !== null)
                  .slice(0, 6)
                  .map((d) => (
                    <div
                      key={d.id}
                      className="bg-gray-50 rounded-lg p-4 border border-gray-100"
                    >
                      <p className="text-sm font-bold text-gray-800 mb-2">
                        {d.campaign_name || `캠페인 #${d.id}`}
                      </p>
                      <div className="space-y-1 text-xs text-gray-600">
                        {d.objective && (
                          <p>
                            <span className="text-gray-400">목적:</span>{" "}
                            <span className="font-medium">{d.objective}</span>
                          </p>
                        )}
                        {d.product_service && (
                          <p>
                            <span className="text-gray-400">제품/서비스:</span>{" "}
                            {d.product_service}
                          </p>
                        )}
                        {d.promotion_copy && (
                          <p>
                            <span className="text-gray-400">프로모션:</span>{" "}
                            {d.promotion_copy}
                          </p>
                        )}
                        {d.model_info && (
                          <p>
                            <span className="text-gray-400">모델:</span>{" "}
                            {d.model_info}
                          </p>
                        )}
                        {d.target_keywords && (
                          <div className="flex flex-wrap gap-1 mt-1">
                            {d.target_keywords.brand?.map((kw) => (
                              <span
                                key={kw}
                                className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 rounded text-[10px]"
                              >
                                {kw}
                              </span>
                            ))}
                            {d.target_keywords.product?.map((kw) => (
                              <span
                                key={kw}
                                className="px-1.5 py-0.5 bg-emerald-50 text-emerald-600 rounded text-[10px]"
                              >
                                {kw}
                              </span>
                            ))}
                          </div>
                        )}
                        <p className="text-gray-400 mt-1">
                          {formatChannel(d.channel)} | {d.first_seen?.slice(0, 10)} ~ {d.last_seen?.slice(0, 10)}
                          {d.status && ` | ${d.status}`}
                        </p>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* 런칭 임팩트 */}
      {config.sections.launchImpact && launchImpacts && launchImpacts.length > 0 && (
        <section className="mb-10">
          <h2 className="text-lg font-bold text-gray-800 border-l-4 border-orange-500 pl-3 mb-4">
            {sectionNum("launchImpact")}. 런칭 임팩트
            <span className="ml-2 text-sm font-normal text-gray-400">
              ({launchImpacts.length}개 제품)
            </span>
          </h2>
          <p className="text-xs text-gray-500 mb-4">
            신제품/서비스 런칭 후 미디어 반응, 소비자 반응, 시장 반응을 종합한 LII(Launch Impact Index) 점수입니다.
          </p>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b-2 border-gray-200">
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">제품명</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">카테고리</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">LII 점수</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">MRS</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">RV</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">CS</th>
                  <th className="text-right py-2 px-3 font-semibold text-gray-600">멘션</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">단계</th>
                  <th className="text-left py-2 px-3 font-semibold text-gray-600">상태</th>
                </tr>
              </thead>
              <tbody>
                {launchImpacts.map((item) => (
                  <tr key={item.product.id} className="border-b border-gray-100">
                    <td className="py-2 px-3 font-medium">{item.product.name}</td>
                    <td className="py-2 px-3">
                      <span className="text-[10px] px-1.5 py-0.5 bg-orange-50 text-orange-600 rounded font-medium">
                        {item.product.category}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <span className={`text-sm font-bold tabular-nums ${
                        item.latest_score.lii_score >= 70
                          ? "text-emerald-600"
                          : item.latest_score.lii_score >= 40
                          ? "text-amber-600"
                          : "text-gray-600"
                      }`}>
                        {item.latest_score.lii_score.toFixed(1)}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-xs">
                      {item.latest_score.mrs_score.toFixed(1)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-xs">
                      {item.latest_score.rv_score.toFixed(1)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-xs">
                      {item.latest_score.cs_score.toFixed(1)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums">
                      {item.latest_score.total_mentions}
                    </td>
                    <td className="py-2 px-3">
                      {item.latest_score.impact_phase ? (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-orange-50 text-orange-700 border border-orange-200">
                          {item.latest_score.impact_phase}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-300">--</span>
                      )}
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          item.product.is_active
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {item.product.is_active ? "Active" : "Ended"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* LII 점수 설명 */}
          <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-100">
            <p className="text-[10px] text-gray-400 leading-relaxed">
              <strong>LII</strong>: Launch Impact Index (종합) |
              <strong> MRS</strong>: Media Response Score (미디어 반응) |
              <strong> RV</strong>: Review Volume (리뷰/소비자 반응) |
              <strong> CS</strong>: Conversation Score (대화/검색 반응)
            </p>
          </div>
        </section>
      )}

      {/* 푸터 */}
      <div className="mt-12 pt-4 border-t border-gray-200 text-center text-xs text-gray-400">
        <p>Generated by AdScope | {reportDate}</p>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-lg font-bold text-gray-900">{value}</p>
    </div>
  );
}

// ── 광고주 / 캠페인 목록 다운로드 ──
function ListDownloadPanel() {
  const download = async (url: string) => {
    await authDownload(url);
  };

  const items = [
    {
      key: "advertiser-xlsx",
      icon: "XLS",
      iconColor: "bg-green-100 text-green-700",
      title: "광고주 목록",
      desc: "전체 광고주 명단, 업종, 채널, 광고비 Excel",
      onClick: () => download("/api/export/advertisers.xlsx"),
    },
    {
      key: "advertiser-csv",
      icon: "CSV",
      iconColor: "bg-gray-100 text-gray-600",
      title: "광고주 목록 (CSV)",
      desc: "간략 광고주 목록 CSV",
      onClick: () => download("/api/export/advertisers"),
    },
    {
      key: "ad-report-single",
      icon: "ZIP",
      iconColor: "bg-teal-100 text-teal-700",
      title: "광고주별 보고서 (ZIP)",
      desc: "특정 광고주의 PPTX + PDF + Excel 묶음 — 아래 '맞춤 보고서'에서 생성",
      onClick: null,
    },
  ];

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-4">
      <div className="flex items-center gap-2 mb-1">
        <div className="w-6 h-6 rounded bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold">↓</div>
        <h2 className="text-lg font-bold text-gray-900">광고주 & 캠페인 목록</h2>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {items.map((item) => (
          <button
            key={item.key}
            onClick={item.onClick ?? undefined}
            disabled={!item.onClick}
            className={`text-left rounded-lg border p-4 transition-colors ${
              item.onClick
                ? "border-gray-200 hover:bg-gray-50 hover:border-gray-300 cursor-pointer"
                : "border-gray-100 bg-gray-50 cursor-default opacity-70"
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-7 h-7 rounded flex items-center justify-center text-[10px] font-bold ${item.iconColor}`}>{item.icon}</span>
              <span className="text-sm font-semibold text-gray-900">{item.title}</span>
            </div>
            <p className="text-xs text-gray-400">{item.desc}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Scope별 Raw Data 다운로드 ──
type ScopeTab = "ad" | "social" | "shop";

const SCOPE_TABS: { key: ScopeTab; label: string; desc: string; color: string }[] = [
  { key: "ad", label: "Ad Scope", desc: "광고소재 / 광고주 / 캠페인 / 광고비", color: "indigo" },
  { key: "social", label: "Social Scope", desc: "채널 / 콘텐츠 / 통계 추이", color: "emerald" },
  { key: "shop", label: "Shop Scope", desc: "추적상품 / 상품 스냅샷", color: "amber" },
];

const AD_CHANNELS = [
  { value: "", label: "전체 채널" },
  { value: "naver_search", label: "네이버 검색" },
  { value: "naver_da", label: "네이버 DA" },
  { value: "naver_shopping", label: "네이버 쇼핑" },
  { value: "google_search_ads", label: "구글 검색광고" },
  { value: "google_gdn", label: "구글 GDN" },
  { value: "youtube_ads", label: "유튜브" },
  { value: "youtube_surf", label: "유튜브 서핑" },
  { value: "meta", label: "메타" },
  { value: "meta_feed", label: "메타 피드" },
  { value: "kakao_da", label: "카카오 DA" },
  { value: "tiktok_ads", label: "틱톡" },
];

const SOCIAL_PLATFORMS = [
  { value: "", label: "전체 플랫폼" },
  { value: "youtube", label: "YouTube" },
  { value: "instagram", label: "Instagram" },
  { value: "meta", label: "메타" },
];

function ScopeDownloadPanel() {
  const [scope, setScope] = useState<ScopeTab>("ad");
  const [days, setDays] = useState(30);
  const [advertiserId, setAdvertiserId] = useState<number | null>(null);
  const [advertiserName, setAdvertiserName] = useState("");
  const [channel, setChannel] = useState("");
  const [platform, setPlatform] = useState("");
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async () => {
    setDownloading(true);
    const dateTo = new Date();
    const dateFrom = new Date();
    dateFrom.setDate(dateFrom.getDate() - days);

    const params = new URLSearchParams();
    params.set("date_from", dateFrom.toISOString());
    params.set("date_to", dateTo.toISOString());
    if (advertiserId) params.set("advertiser_id", String(advertiserId));

    if (scope === "ad" && channel) params.set("channel", channel);
    if (scope === "social" && platform) params.set("platform", platform);

    await authDownload(`/api/export/${scope}-scope.xlsx?${params.toString()}`);
    setTimeout(() => setDownloading(false), 2000);
  };

  const tabColors: Record<ScopeTab, { active: string; ring: string; btn: string }> = {
    ad: { active: "bg-indigo-600 text-white", ring: "ring-indigo-200", btn: "bg-indigo-600 hover:bg-indigo-700" },
    social: { active: "bg-emerald-600 text-white", ring: "ring-emerald-200", btn: "bg-emerald-600 hover:bg-emerald-700" },
    shop: { active: "bg-amber-600 text-white", ring: "ring-amber-200", btn: "bg-amber-600 hover:bg-amber-700" },
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-5">
      <div className="flex items-center gap-2 mb-1">
        <div className="w-6 h-6 rounded bg-green-100 text-green-700 flex items-center justify-center text-xs font-bold">XLS</div>
        <h2 className="text-lg font-bold text-gray-900">Raw Data 다운로드</h2>
      </div>

      {/* Scope 탭 */}
      <div className="flex gap-2">
        {SCOPE_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setScope(t.key); setChannel(""); setPlatform(""); }}
            className={`px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${
              scope === t.key
                ? `${tabColors[t.key].active} shadow-sm ring-2 ${tabColors[t.key].ring}`
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Scope 설명 */}
      <p className="text-sm text-gray-500">
        {SCOPE_TABS.find((t) => t.key === scope)?.desc}
      </p>

      {/* 필터 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* 기간 */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 mb-1.5">기간</label>
          <div className="flex gap-1.5">
            {[7, 14, 30, 60, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                  days === d
                    ? `${tabColors[scope].active}`
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {d}일
              </button>
            ))}
          </div>
        </div>

        {/* 광고주 (선택) */}
        <div>
          <label className="block text-xs font-semibold text-gray-500 mb-1.5">광고주 (선택)</label>
          <AdvertiserSearch
            onSelect={(id, name) => { setAdvertiserId(id); setAdvertiserName(name); }}
          />
          {advertiserId && (
            <div className="mt-1 flex items-center gap-1">
              <span className="text-xs text-indigo-600 font-medium">{advertiserName}</span>
              <button onClick={() => { setAdvertiserId(null); setAdvertiserName(""); }} className="text-xs text-gray-400 hover:text-red-500">x</button>
            </div>
          )}
        </div>

        {/* 채널/플랫폼 필터 */}
        {scope === "ad" && (
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1.5">채널</label>
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            >
              {AD_CHANNELS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>
        )}
        {scope === "social" && (
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1.5">플랫폼</label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-white"
            >
              {SOCIAL_PLATFORMS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>
        )}
        {scope === "shop" && <div />}
      </div>

      {/* 다운로드 버튼 */}
      <button
        onClick={handleDownload}
        disabled={downloading}
        className={`w-full py-3 rounded-lg text-sm font-semibold text-white transition-colors ${
          downloading ? "bg-gray-400 cursor-not-allowed" : tabColors[scope].btn
        }`}
      >
        {downloading ? "다운로드 중..." : `${SCOPE_TABS.find((t) => t.key === scope)?.label} Excel 다운로드`}
      </button>
    </div>
  );
}


// ── 메인 페이지 ──
export default function ReportsPage() {
  const [config, setConfig] = useState<ReportConfig>(DEFAULT_CONFIG);
  const [generating, setGenerating] = useState(false);
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  const handleGenerate = () => {
    if (!config.advertiserId) return;
    setGenerating(true);
  };

  const handlePrint = () => {
    window.print();
  };

  const toggleSection = (key: keyof ReportConfig["sections"]) => {
    setConfig((prev) => ({
      ...prev,
      sections: { ...prev.sections, [key]: !prev.sections[key] },
    }));
  };

  const allChecked = Object.values(config.sections).every(Boolean);
  const toggleAll = () => {
    const newVal = !allChecked;
    setConfig((prev) => ({
      ...prev,
      sections: {
        overview: newVal,
        spend: newVal,
        media: newVal,
        creatives: newVal,
        socialCreatives: newVal,
        competitors: newVal,
        shopping: newVal,
        metaSignal: newVal,
        socialImpact: newVal,
        campaigns: newVal,
        launchImpact: newVal,
      },
    }));
  };

  // 설정 패널 (인쇄 시 숨김)
  if (!generating) {
    return (
      <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
        {/* Header */}
        <div className="mb-8 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-500 to-slate-700 flex items-center justify-center shadow-lg shadow-slate-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
              <polyline points="10 9 9 9 8 9" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">보고서 & 자료 다운로드</h1>
            <p className="text-sm text-gray-500">광고주 목록, 광고 소재, 소셜 소재, 맞춤 보고서를 한 곳에서 내려받으세요.</p>
          </div>
        </div>

        {/* 광고주 목록 */}
        <ListDownloadPanel />

        {/* 구분선 */}
        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-gray-200" />
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">소재 & 원자료 다운로드</span>
          <div className="h-px flex-1 bg-gray-200" />
        </div>

        {/* Scope별 Raw Data 다운로드 */}
        <ScopeDownloadPanel />

        {!authed && (
          <div className="mt-4 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-900">
            비회원도 보고서 구성과 공개 데이터는 열람할 수 있습니다. Raw Data Excel과 광고 소재 다운로드는 로그인 후 유료 가입 상태에서 사용할 수 있습니다.
          </div>
        )}

        {/* 구분선 */}
        <div className="my-8 flex items-center gap-3">
          <div className="h-px flex-1 bg-gray-200" />
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">커스텀 보고서</span>
          <div className="h-px flex-1 bg-gray-200" />
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 space-y-6">
          {/* 광고주 선택 */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">
              광고주 선택
            </label>
            <AdvertiserSearch
              onSelect={(id, name) =>
                setConfig((prev) => ({ ...prev, advertiserId: id, advertiserName: name }))
              }
            />
            {config.advertiserId && (
              <p className="mt-2 text-sm text-indigo-600 font-medium">
                선택됨: {config.advertiserName}
              </p>
            )}
          </div>

          {/* 기간 선택 */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">
              분석 기간
            </label>
            <div className="flex gap-2">
              {[7, 14, 30, 60, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => setConfig((prev) => ({ ...prev, days: d }))}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    config.days === d
                      ? "bg-indigo-600 text-white"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                  }`}
                >
                  {d}일
                </button>
              ))}
            </div>
          </div>

          {/* 섹션 선택 */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="text-sm font-semibold text-gray-700">
                보고서 항목
              </label>
              <button
                onClick={toggleAll}
                className="text-xs text-indigo-600 hover:text-indigo-800"
              >
                {allChecked ? "전체 해제" : "전체 선택"}
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {(Object.keys(SECTION_LABELS) as (keyof ReportConfig["sections"])[]).map(
                (key) => (
                  <label
                    key={key}
                    className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      config.sections[key]
                        ? "bg-indigo-50 border-indigo-300"
                        : "bg-white border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={config.sections[key]}
                      onChange={() => toggleSection(key)}
                      className="w-4 h-4 text-indigo-600 rounded"
                    />
                    <span className="text-sm font-medium text-gray-700">
                      {SECTION_LABELS[key]}
                    </span>
                  </label>
                )
              )}
            </div>
          </div>

          {/* 생성 버튼 */}
          <button
            onClick={handleGenerate}
            disabled={!config.advertiserId}
            className={`w-full py-3 rounded-lg text-sm font-semibold transition-colors ${
              config.advertiserId
                ? "bg-indigo-600 text-white hover:bg-indigo-700"
                : "bg-gray-200 text-gray-400 cursor-not-allowed"
            }`}
          >
            보고서 생성
          </button>
        </div>
      </div>
    );
  }

  // 보고서 뷰
  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* 컨트롤 바 (인쇄 시 숨김) */}
      <div className="flex items-center gap-3 mb-6 print:hidden">
        <button
          onClick={() => setGenerating(false)}
          className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200"
        >
          ← 설정으로
        </button>
        <button
          onClick={handlePrint}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700"
        >
          PDF 출력 / 인쇄
        </button>
        {config.advertiserId && (
          <>
            <button
              onClick={() => {
                const token = localStorage.getItem("adscope_token");
                const a = document.createElement("a");
                a.href = `/api/export/report/${config.advertiserId}.xlsx?_token=${token}`;
                a.click();
              }}
              className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700"
            >
              Excel 다운로드
            </button>
            <AdvertiserDownloadDropdown advertiserId={config.advertiserId} />
          </>
        )}
      </div>

      {!authed && (
        <div className="mb-6 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-900 print:hidden">
          비회원은 보고서 내용을 미리 볼 수 있습니다. Excel 내보내기와 광고 소재 다운로드는 로그인 후 유료 가입 상태에서 사용할 수 있습니다.
        </div>
      )}

      <ReportView config={config} />
    </div>
  );
}
