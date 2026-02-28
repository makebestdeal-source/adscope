"use client";

import { useQuery, useQueries, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, AdvertiserTreeNode, MediaCategoryBreakdown, ChannelBreakdown, MetaSignalOverview, ActivityScorePoint, SocialImpactOverview, SocialImpactTimelinePoint, NewsMention, FavoriteAdvertiser, LIIAdvertiserImpact, CampaignDetail } from "@/lib/api";
import {
  formatChannel,
  formatSpend,
  CHANNEL_COLORS,
  CHANNEL_BADGE_COLORS,
  INDUSTRIES,
} from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";
import { ExportDropdown } from "@/components/ExportDropdown";
import { AdvertiserDownloadDropdown } from "@/components/DownloadButtons";
import { toImageUrl } from "@/lib/image-utils";
import { useState, useMemo, useRef, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

// -- media category colors --
const CATEGORY_COLORS: Record<string, string> = {
  video: "#FF0000",
  social: "#1877F2",
  portal: "#03C75A",
  network: "#4285F4",
};

const CATEGORY_KO: Record<string, string> = {
  video: "\ub3d9\uc601\uc0c1",
  social: "\uc18c\uc15c/SNS",
  portal: "\ud3ec\ud138",
  network: "\ub124\ud2b8\uc6cc\ud06c/\ub514\uc2a4\ud50c\ub808\uc774",
};

const OBJECTIVE_KO: Record<string, { label: string; color: string }> = {
  brand_awareness: { label: "브랜드 인지", color: "bg-purple-100 text-purple-700" },
  traffic: { label: "트래픽", color: "bg-blue-100 text-blue-700" },
  engagement: { label: "참여", color: "bg-green-100 text-green-700" },
  conversion: { label: "전환", color: "bg-orange-100 text-orange-700" },
  retention: { label: "리텐션", color: "bg-teal-100 text-teal-700" },
};

function AdvertiserTree({
  node,
  currentId,
}: {
  node: AdvertiserTreeNode;
  currentId: number;
}) {
  const isCurrent = node.id === currentId;
  return (
    <div className="pl-4 border-l-2 border-gray-200">
      <div
        className={`py-1.5 px-2 rounded text-sm ${
          isCurrent
            ? "bg-adscope-50 font-semibold text-adscope-700"
            : "text-gray-700"
        }`}
      >
        <Link href={`/advertisers/${node.id}`} className="hover:underline">
          {node.name}
        </Link>
        {node.advertiser_type && (
          <span className="ml-2 text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
            {node.advertiser_type}
          </span>
        )}
      </div>
      {node.children?.map((child) => (
        <AdvertiserTree key={child.id} node={child} currentId={currentId} />
      ))}
    </div>
  );
}

export default function AdvertiserDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [days, setDays] = useState(30);

  const { data: report, isLoading: reportLoading } = useQuery({
    queryKey: ["advertiserSpendReport", id, days],
    queryFn: () => api.getAdvertiserSpendReport(id, days),
    enabled: !!id,
  });

  const { data: tree } = useQuery({
    queryKey: ["advertiserTree", id],
    queryFn: () => api.getAdvertiserTree(id),
    enabled: !!id,
  });

  const { data: mediaBreakdown, isLoading: mediaLoading } = useQuery({
    queryKey: ["advertiserMediaBreakdown", id, days],
    queryFn: () => api.getAdvertiserMediaBreakdown(id, days),
    enabled: !!id,
  });

  const { data: metaSignal } = useQuery({
    queryKey: ["metaSignalOverview", id],
    queryFn: () => api.getMetaSignalOverview(id),
    enabled: !!id,
  });

  const { data: activityTimeline } = useQuery({
    queryKey: ["metaSignalActivity", id, days],
    queryFn: () => api.getMetaSignalActivity(id, days),
    enabled: !!id,
  });

  const { data: socialImpact } = useQuery({
    queryKey: ["socialImpactOverview", id],
    queryFn: () => api.getSocialImpactOverview(id),
    enabled: !!id,
  });

  const { data: socialTimeline } = useQuery({
    queryKey: ["socialImpactTimeline", id, days],
    queryFn: () => api.getSocialImpactTimeline(id, days),
    enabled: !!id,
  });

  const { data: newsItems } = useQuery({
    queryKey: ["socialImpactNews", id],
    queryFn: () => api.getSocialImpactNews(id, 30),
    enabled: !!id,
  });

  const { data: launchImpacts } = useQuery<LIIAdvertiserImpact[]>({
    queryKey: ["launchImpact", id],
    queryFn: () => api.getImpactByAdvertiser(id),
    enabled: !!id,
  });

  // Fetch campaign details for all active campaigns
  const activeCampaignIds = useMemo(
    () => (report?.active_campaigns ?? []).map((c) => c.id),
    [report]
  );

  const campaignDetailQueries = useQueries({
    queries: activeCampaignIds.map((cid) => ({
      queryKey: ["campaignDetail", cid],
      queryFn: () => api.getCampaignDetail(cid),
      enabled: !!cid,
      staleTime: 5 * 60 * 1000,
    })),
  });

  const campaignDetailsMap = useMemo(() => {
    const map: Record<number, CampaignDetail> = {};
    campaignDetailQueries.forEach((q, i) => {
      if (q.data) {
        map[activeCampaignIds[i]] = q.data;
      }
    });
    return map;
  }, [campaignDetailQueries, activeCampaignIds]);

  // Favorites
  const queryClient = useQueryClient();
  const [showFavDropdown, setShowFavDropdown] = useState(false);
  const [favNote, setFavNote] = useState("");
  const favDropdownRef = useRef<HTMLDivElement>(null);

  const { data: favoritesData } = useQuery({
    queryKey: ["favorites"],
    queryFn: () => api.getFavorites(),
  });

  const currentFav = useMemo(() => {
    if (!favoritesData) return null;
    return favoritesData.find((f) => f.advertiser_id === id) || null;
  }, [favoritesData, id]);

  const isFavorite = !!currentFav;

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (favDropdownRef.current && !favDropdownRef.current.contains(e.target as Node)) {
        setShowFavDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const addFavMutation = useMutation({
    mutationFn: ({ category, note }: { category: string; note?: string }) =>
      api.addFavorite(id, category, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      setShowFavDropdown(false);
      setFavNote("");
    },
  });

  const removeFavMutation = useMutation({
    mutationFn: () => api.removeFavorite(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const updateFavMutation = useMutation({
    mutationFn: (data: { category?: string; notes?: string }) =>
      api.updateFavorite(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      setShowFavDropdown(false);
    },
  });

  const FAV_CATEGORIES = [
    { key: "my_advertiser", label: "나의 광고주", color: "text-emerald-600 bg-emerald-50 hover:bg-emerald-100" },
    { key: "competing", label: "경쟁사", color: "text-red-600 bg-red-50 hover:bg-red-100" },
    { key: "monitoring", label: "모니터링", color: "text-blue-600 bg-blue-50 hover:bg-blue-100" },
    { key: "interested", label: "관심사", color: "text-amber-600 bg-amber-50 hover:bg-amber-100" },
    { key: "other", label: "기타", color: "text-gray-600 bg-gray-50 hover:bg-gray-100" },
  ];

  const isLoading = reportLoading || mediaLoading;

  // donut chart data for media categories
  const donutData = useMemo(() => {
    if (!mediaBreakdown?.categories) return [];
    return (mediaBreakdown?.categories || []).map((cat: MediaCategoryBreakdown) => ({
      name: cat.category,
      key: cat.category_key,
      value: cat.est_spend > 0 ? cat.est_spend : cat.ad_count,
      spend: cat.est_spend,
      adCount: cat.ad_count,
      ratio: cat.ratio,
      color: CATEGORY_COLORS[cat.category_key] || "#94A3B8",
    }));
  }, [mediaBreakdown]);

  // bar chart data for channels
  const channelBarData = useMemo(() => {
    if (!mediaBreakdown?.by_channel) return [];
    return (mediaBreakdown?.by_channel || [])
      .filter((ch: ChannelBreakdown) => ch.ad_count > 0 || ch.est_spend > 0)
      .map((ch: ChannelBreakdown) => ({
        channel: formatChannel(ch.channel),
        rawChannel: ch.channel,
        spend: ch.est_spend,
        count: ch.ad_count,
        fill: CHANNEL_COLORS[ch.channel] || "#6366f1",
      }))
      .sort((a: { spend: number; count: number }, b: { spend: number; count: number }) => {
        const va = a.spend > 0 ? a.spend : a.count;
        const vb = b.spend > 0 ? b.spend : b.count;
        return vb - va;
      });
  }, [mediaBreakdown]);

  // daily trend from spend report
  const trendData = useMemo(() => {
    if (!report?.daily_trend) return [];
    return (report?.daily_trend || []).map((d) => ({
      date: d.date?.slice(5) ?? "",
      spend: d.spend,
    }));
  }, [report]);

  if (isLoading) {
    return (
      <div className="p-6 lg:p-8 max-w-7xl">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-48 bg-gray-200 rounded" />
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-24 bg-gray-200 rounded-xl" />
            ))}
          </div>
          <div className="grid grid-cols-2 gap-6">
            <div className="h-72 bg-gray-200 rounded-xl" />
            <div className="h-72 bg-gray-200 rounded-xl" />
          </div>
        </div>
      </div>
    );
  }

  if (!report && !mediaBreakdown) {
    return (
      <div className="p-6 lg:p-8 max-w-7xl">
        <p className="text-gray-500">
          광고주 데이터를 찾을 수 없습니다.
        </p>
        <Link
          href="/advertisers"
          className="text-adscope-600 hover:underline text-sm mt-2 inline-block"
        >
          목록으로 돌아가기
        </Link>
      </div>
    );
  }

  const adv = report?.advertiser;
  const mb = mediaBreakdown;

  const advName = mb?.advertiser_name || adv?.name || "";
  const brandName = mb?.brand_name || adv?.brand_name;
  const website = mb?.website || adv?.website;
  const advType = mb?.advertiser_type;
  const industryName = mb?.industry_name;

  return (
    <div className="p-6 lg:p-8 max-w-7xl">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500 mb-4">
        <Link href="/advertisers" className="hover:text-adscope-600">
          광고주
        </Link>
        <span>/</span>
        <span className="text-gray-900 font-medium">{advName}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{advName}</h1>
            {/* Favorite button with dropdown */}
            <div className="relative" ref={favDropdownRef}>
              <button
                onClick={() => setShowFavDropdown(!showFavDropdown)}
                className={`p-1.5 rounded-lg transition-colors ${
                  isFavorite
                    ? "text-amber-400 hover:text-amber-500 bg-amber-50"
                    : "text-gray-300 hover:text-amber-400 hover:bg-gray-50"
                }`}
                title={isFavorite ? "즐겨찾기 편집" : "즐겨찾기 추가"}
              >
                <svg viewBox="0 0 24 24" fill={isFavorite ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" className="w-5 h-5">
                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                </svg>
              </button>
              {showFavDropdown && (
                <div className="absolute top-full left-0 mt-1 z-30 bg-white border border-gray-200 rounded-xl shadow-lg w-64 overflow-hidden">
                  <div className="p-3 border-b border-gray-100">
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-2">카테고리</p>
                    <div className="flex flex-wrap gap-1.5">
                      {FAV_CATEGORIES.map((cat) => (
                        <button
                          key={cat.key}
                          onClick={() => {
                            if (isFavorite) {
                              updateFavMutation.mutate({ category: cat.key });
                            } else {
                              addFavMutation.mutate({ category: cat.key, note: favNote || undefined });
                            }
                          }}
                          className={`text-xs font-medium px-2.5 py-1 rounded-lg transition-colors ${cat.color} ${
                            currentFav?.category === cat.key ? "ring-2 ring-offset-1 ring-adscope-500" : ""
                          }`}
                        >
                          {cat.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="p-3">
                    <p className="text-xs font-semibold text-gray-500 uppercase mb-2">노트</p>
                    <div className="flex items-center gap-2">
                      <input
                        type="text"
                        value={favNote || currentFav?.notes || ""}
                        onChange={(e) => setFavNote(e.target.value)}
                        placeholder="메모 입력..."
                        className="flex-1 text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-adscope-500/20 focus:border-adscope-500"
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && isFavorite) {
                            updateFavMutation.mutate({ notes: favNote });
                          }
                        }}
                      />
                      {isFavorite && (
                        <button
                          onClick={() => updateFavMutation.mutate({ notes: favNote })}
                          className="text-xs text-adscope-600 font-medium hover:text-adscope-800"
                        >
                          저장
                        </button>
                      )}
                    </div>
                  </div>
                  {isFavorite && (
                    <div className="p-3 border-t border-gray-100">
                      <button
                        onClick={() => {
                          if (window.confirm("즐겨찾기에서 삭제하시겠습니까?")) {
                            removeFavMutation.mutate();
                            setShowFavDropdown(false);
                          }
                        }}
                        className="w-full text-xs text-red-500 hover:text-red-700 hover:bg-red-50 font-medium py-1.5 rounded-lg transition-colors"
                      >
                        즐겨찾기 해제
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3 mt-1.5 flex-wrap">
            {advType && (
              <span className="text-[11px] font-medium bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                {advType}
              </span>
            )}
            {industryName && (
              <span className="text-[11px] font-medium bg-indigo-50 text-indigo-600 px-2 py-0.5 rounded">
                {industryName}
              </span>
            )}
            {brandName && (
              <span className="text-sm text-gray-500">{brandName}</span>
            )}
            {website && (
              <a
                href={website.startsWith("http") ? website : `https://${website}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-adscope-600 hover:underline"
              >
                {website}
              </a>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <AdvertiserDownloadDropdown advertiserId={id} />
          <ExportDropdown
            csvUrl={`/api/export/report/${id}`}
            xlsxUrl={`/api/export/report/${id}.xlsx`}
            label="리포트 다운로드"
          />
          <PeriodSelector days={days} onDaysChange={setDays} />
        </div>
      </div>

      {/* Tree */}
      {tree && tree.children && tree.children.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-3">
            그룹 구조
          </h2>
          <AdvertiserTree node={tree} currentId={id} />
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-adscope-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            총 추정 광고비
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {formatSpend(mb?.total_est_spend || report?.total_est_spend || 0)}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-blue-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            총 광고 수
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {(mb?.total_ads || 0).toLocaleString()}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-green-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            활성 채널
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {(report?.by_channel ?? []).filter((c) => c.is_active).length}개
          </p>
          <div className="flex gap-1 mt-2 flex-wrap">
            {(report?.by_channel ?? [])
              .filter((c) => c.is_active)
              .map((c) => (
                <span
                  key={c.channel}
                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    CHANNEL_BADGE_COLORS[c.channel] ??
                    "bg-gray-100 text-gray-600"
                  }`}
                >
                  {formatChannel(c.channel)}
                </span>
              ))}
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-orange-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            매체 카테고리
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {(mb?.categories?.length || 0)}개
          </p>
          <div className="flex gap-1 mt-2 flex-wrap">
            {(mb?.categories || []).map((cat: MediaCategoryBreakdown) => (
              <span
                key={cat.category_key}
                className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                style={{
                  backgroundColor: `${CATEGORY_COLORS[cat.category_key] || "#94A3B8"}18`,
                  color: CATEGORY_COLORS[cat.category_key] || "#94A3B8",
                }}
              >
                {cat.category}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Charts row: Donut + Channel bar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Media Category Donut */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-5">
            매체 카테고리별 비중
          </h2>
          {donutData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={280}>
                <PieChart>
                  <Pie
                    data={donutData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={({
                      name,
                      percent,
                    }: {
                      name: string;
                      percent: number;
                    }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={{ strokeWidth: 1 }}
                  >
                    {donutData.map(
                      (entry: { color: string }, index: number) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      )
                    )}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, name: string) => {
                      const item = donutData.find(
                        (d: { name: string }) => d.name === name
                      );
                      if (item && item.spend > 0) {
                        return [
                          `${formatSpend(item.spend)} (${item.adCount}건)`,
                          name,
                        ];
                      }
                      return [`${value.toLocaleString()}건`, name];
                    }}
                    contentStyle={{
                      borderRadius: 8,
                      border: "1px solid #e5e7eb",
                      fontSize: 12,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
              {/* Category detail table */}
              <div className="mt-4 space-y-2">
                {(mb?.categories || []).map((cat: MediaCategoryBreakdown) => (
                  <div
                    key={cat.category_key}
                    className="flex items-center justify-between py-2 px-3 rounded-lg bg-gray-50"
                  >
                    <div className="flex items-center gap-2">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{
                          backgroundColor:
                            CATEGORY_COLORS[cat.category_key] || "#94A3B8",
                        }}
                      />
                      <span className="text-sm font-medium text-gray-700">
                        {cat.category}
                      </span>
                      <span className="text-[10px] text-gray-400">
                        {cat.channels.map((c) => formatChannel(c)).join(", ")}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm font-semibold text-gray-900 tabular-nums">
                        {cat.ad_count.toLocaleString()}건
                      </span>
                      {cat.est_spend > 0 && (
                        <span className="text-sm text-gray-500 tabular-nums">
                          {formatSpend(cat.est_spend)}
                        </span>
                      )}
                      <span className="text-xs font-medium text-adscope-600 tabular-nums min-w-[42px] text-right">
                        {(cat.ratio * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400 text-center py-16">
              매체 데이터 없음
            </p>
          )}
        </div>

        {/* Channel Bar Chart */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-5">
            채널별 광고 현황
          </h2>
          {channelBarData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={channelBarData}
                layout="vertical"
                margin={{ left: 80, right: 20 }}
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  tickFormatter={(v) =>
                    channelBarData[0]?.spend > 0
                      ? formatSpend(v)
                      : `${v}`
                  }
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  dataKey="channel"
                  type="category"
                  tick={{ fontSize: 12 }}
                  width={80}
                />
                <Tooltip
                  formatter={(v: number, name: string) => {
                    if (name === "spend") return [formatSpend(v), "추정 비용"];
                    return [`${v.toLocaleString()}건`, "광고 수"];
                  }}
                  contentStyle={{
                    borderRadius: 8,
                    border: "1px solid #e5e7eb",
                    fontSize: 12,
                  }}
                />
                <Bar
                  dataKey={channelBarData[0]?.spend > 0 ? "spend" : "count"}
                  radius={[0, 4, 4, 0]}
                >
                  {channelBarData.map(
                    (entry: { fill: string }, index: number) => (
                      <Cell key={`bar-${index}`} fill={entry.fill} />
                    )
                  )}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 text-center py-16">
              채널 데이터 없음
            </p>
          )}
        </div>
      </div>

      {/* Daily trend */}
      {trendData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-5">
            일별 광고비 추이
          </h2>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis
                tickFormatter={(v) => formatSpend(v)}
                tick={{ fontSize: 11 }}
              />
              <Tooltip formatter={(v: number) => [formatSpend(v), "광고비"]} />
              <Line
                type="monotone"
                dataKey="spend"
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent Ads Gallery */}
      {(mb?.recent_ads || []).length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm mb-6">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-900">
              최근 광고 소재
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              이미지가 있는 최근 광고 소재
            </p>
          </div>
          <div className="p-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {(mb?.recent_ads || []).map((ad) => (
              <div
                key={ad.id}
                className="group border border-gray-200 rounded-lg overflow-hidden hover:shadow-md transition-shadow"
              >
                {ad.creative_image_path && (
                  <div className="aspect-[4/3] bg-gray-100 overflow-hidden relative">
                    <img
                      src={toImageUrl(ad.creative_image_path) || `/images/${ad.creative_image_path}`}
                      alt={ad.ad_text || "ad creative"}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                      referrerPolicy="no-referrer"
                      loading="lazy"
                      onError={(e) => {
                        const el = e.target as HTMLImageElement;
                        el.style.display = "none";
                        const placeholder = el.nextElementSibling as HTMLElement;
                        if (placeholder) placeholder.style.display = "flex";
                      }}
                    />
                    <div className="absolute inset-0 items-center justify-center bg-gray-100 text-gray-300" style={{ display: "none" }}>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-8 h-8">
                        <path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </div>
                  </div>
                )}
                <div className="p-2.5">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span
                      className={`text-[9px] font-medium px-1.5 py-0.5 rounded ${
                        CHANNEL_BADGE_COLORS[ad.channel] ??
                        "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {formatChannel(ad.channel)}
                    </span>
                    {ad.ad_type && (
                      <span className="text-[9px] text-gray-400">
                        {ad.ad_type}
                      </span>
                    )}
                  </div>
                  {ad.ad_text && (
                    <p className="text-xs text-gray-700 line-clamp-2 leading-relaxed">
                      {ad.ad_text}
                    </p>
                  )}
                  {ad.captured_at && (
                    <p className="text-[10px] text-gray-400 mt-1">
                      {ad.captured_at.slice(0, 10)}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Campaigns - Enriched */}
      {(report?.active_campaigns ?? []).length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                캠페인 상세
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                {(report?.active_campaigns ?? []).length}개 캠페인 | 클릭하여 상세 보기
              </p>
            </div>
          </div>
          <div className="divide-y divide-gray-100">
            {(report?.active_campaigns ?? []).map((c) => {
              const detail = campaignDetailsMap[c.id];
              const obj = detail?.objective ? OBJECTIVE_KO[detail.objective] : null;
              return (
                <Link
                  key={c.id}
                  href={`/campaigns/${c.id}`}
                  className="block hover:bg-indigo-50/50 transition-colors"
                >
                  <div className="px-6 py-4">
                    {/* Row 1: Campaign name + badges */}
                    <div className="flex items-center gap-2 flex-wrap mb-2">
                      <span
                        className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                          CHANNEL_BADGE_COLORS[c.channel] ??
                          "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {formatChannel(c.channel)}
                      </span>
                      <h3 className="text-sm font-semibold text-gray-900 truncate max-w-md">
                        {detail?.campaign_name || `캠페인 #${c.id}`}
                      </h3>
                      {obj && (
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${obj.color}`}>
                          {obj.label}
                        </span>
                      )}
                      {detail?.objective && !obj && (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                          {detail.objective}
                        </span>
                      )}
                      <span
                        className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
                          c.is_active
                            ? "bg-green-100 text-green-700"
                            : "bg-gray-100 text-gray-500"
                        }`}
                      >
                        {c.is_active ? "활성" : "종료"}
                      </span>
                      <span className="ml-auto text-xs font-semibold text-gray-900 tabular-nums">
                        {formatSpend(c.total_est_spend)}
                      </span>
                    </div>

                    {/* Row 2: Detail info cards */}
                    <div className="flex items-start gap-4 flex-wrap text-xs">
                      {/* Period */}
                      <div className="flex items-center gap-1.5 text-gray-500">
                        <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        <span>
                          {c.first_seen?.slice(0, 10) ?? "-"} ~ {c.last_seen?.slice(0, 10) ?? "-"}
                        </span>
                      </div>

                      {/* Snapshot count */}
                      <div className="flex items-center gap-1.5 text-gray-500">
                        <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                          <path strokeLinecap="round" strokeLinejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <span>{c.snapshot_count}건</span>
                      </div>

                      {/* Product/Service */}
                      {detail?.product_service && (
                        <div className="flex items-center gap-1.5 text-gray-600">
                          <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                          </svg>
                          <span className="font-medium">{detail.product_service}</span>
                        </div>
                      )}

                      {/* Model/Talent info */}
                      {detail?.model_info && (
                        <div className="flex items-center gap-1.5">
                          <svg className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                          </svg>
                          <span className="text-amber-700 font-medium bg-amber-50 px-1.5 py-0.5 rounded">
                            {detail.model_info}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Row 3: Promotion copy */}
                    {detail?.promotion_copy && (
                      <p className="mt-2 text-xs text-gray-500 line-clamp-2 leading-relaxed bg-gray-50 rounded-lg px-3 py-2">
                        {detail.promotion_copy}
                      </p>
                    )}

                    {/* Row 4: Target keywords */}
                    {detail?.target_keywords && (
                      <div className="mt-2 flex items-center gap-1 flex-wrap">
                        {detail.target_keywords.brand?.map((kw) => (
                          <span key={`b-${kw}`} className="text-[10px] bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded">
                            {kw}
                          </span>
                        ))}
                        {detail.target_keywords.product?.map((kw) => (
                          <span key={`p-${kw}`} className="text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded">
                            {kw}
                          </span>
                        ))}
                        {detail.target_keywords.competitor?.map((kw) => (
                          <span key={`c-${kw}`} className="text-[10px] bg-rose-50 text-rose-600 px-1.5 py-0.5 rounded">
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Meta Signal Section ── */}
      {metaSignal && (
        <div className="space-y-4">
          <h2 className="text-lg font-bold text-gray-900">
            메타신호 종합
          </h2>

          {/* Composite Score + State Badge */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-violet-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">종합 점수</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {metaSignal.composite_score?.toFixed(1) ?? "0.0"}
                <span className="text-sm text-gray-400 ml-1">/ 100</span>
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-amber-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">활동 상태</p>
              <p className="text-2xl font-bold mt-1">
                <span className={`px-2 py-1 rounded text-sm font-semibold ${
                  metaSignal.activity_state === "peak" ? "bg-red-100 text-red-700" :
                  metaSignal.activity_state === "push" ? "bg-orange-100 text-orange-700" :
                  metaSignal.activity_state === "scale" ? "bg-yellow-100 text-yellow-700" :
                  metaSignal.activity_state === "cooldown" ? "bg-blue-100 text-blue-700" :
                  "bg-gray-100 text-gray-600"
                }`}>
                  {metaSignal.activity_state?.toUpperCase() ?? "N/A"}
                </span>
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-green-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">스마트스토어</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {metaSignal.smartstore_score?.toFixed(1) ?? "0.0"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-blue-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">트래픽 지수</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {metaSignal.traffic_score?.toFixed(1) ?? "0.0"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-rose-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">광고비 보정</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                x{metaSignal.spend_multiplier?.toFixed(2) ?? "1.00"}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                {metaSignal.spend_multiplier > 1 ? "상향 보정" : metaSignal.spend_multiplier < 1 ? "하향 보정" : "기본"}
              </p>
            </div>
          </div>

          {/* Activity Timeline Chart */}
          {Array.isArray(activityTimeline) && activityTimeline.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h3 className="text-base font-semibold text-gray-900 mb-4">
                활동 점수 추이
              </h3>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={activityTimeline.map(d => ({
                  date: d.date?.slice(5, 10) ?? "",
                  score: d.composite_score,
                  campaigns: d.active_campaigns,
                  creatives: d.creative_variants,
                }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                    formatter={(v: number, name: string) => [
                      v?.toFixed(1),
                      name === "score" ? "활동 점수" : name === "campaigns" ? "활성 캠페인" : "크리에이티브",
                    ]}
                  />
                  <Line type="monotone" dataKey="score" stroke="#8B5CF6" strokeWidth={2} dot={false} name="score" />
                  <Line type="monotone" dataKey="campaigns" stroke="#F59E0B" strokeWidth={1.5} dot={false} name="campaigns" strokeDasharray="4 4" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* ── Social Impact Section ── */}
      {socialImpact && socialImpact.composite_score > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-bold text-gray-900">Social Impact</h2>

          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-teal-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">Composite</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {socialImpact.composite_score?.toFixed(1) ?? "0.0"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-pink-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">News</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {socialImpact.news_impact_score?.toFixed(1) ?? "0.0"}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                {socialImpact.news_article_count ?? 0}articles
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-blue-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">Social</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {socialImpact.social_posting_score?.toFixed(1) ?? "0.0"}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                {socialImpact.social_posting_delta_pct != null
                  ? `${socialImpact.social_posting_delta_pct > 0 ? "+" : ""}${socialImpact.social_posting_delta_pct.toFixed(1)}%`
                  : "-"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-green-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">Search Lift</p>
              <p className="text-2xl font-bold text-gray-900 mt-1">
                {socialImpact.search_lift_score?.toFixed(1) ?? "0.0"}
              </p>
              <p className="text-[10px] text-gray-400 mt-0.5">
                {socialImpact.search_volume_delta_pct != null
                  ? `${socialImpact.search_volume_delta_pct > 0 ? "+" : ""}${socialImpact.search_volume_delta_pct.toFixed(1)}%`
                  : "-"}
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-amber-500 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase">Phase</p>
              <p className="mt-1">
                <span className={`inline-block px-2 py-1 rounded-full text-xs font-semibold ${
                  socialImpact.impact_phase === "during" ? "bg-orange-100 text-orange-700" :
                  socialImpact.impact_phase === "post" ? "bg-blue-100 text-blue-700" :
                  socialImpact.impact_phase === "pre" ? "bg-gray-100 text-gray-600" :
                  "bg-gray-50 text-gray-400"
                }`}>
                  {socialImpact.impact_phase === "during" ? "Campaign Active" :
                   socialImpact.impact_phase === "post" ? "Post Campaign" :
                   socialImpact.impact_phase === "pre" ? "Pre Campaign" : "No Campaign"}
                </span>
              </p>
            </div>
          </div>

          {/* Timeline Chart */}
          {Array.isArray(socialTimeline) && socialTimeline.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h3 className="text-base font-semibold text-gray-900 mb-4">
                Social Impact Timeline
              </h3>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={socialTimeline.map(d => ({
                  date: d.date?.slice(5, 10) ?? "",
                  composite: d.composite_score,
                  news: d.news_impact_score,
                  social: d.social_posting_score,
                  search: d.search_lift_score,
                }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                    formatter={(v: number, name: string) => [
                      v?.toFixed(1),
                      name === "composite" ? "Composite" :
                      name === "news" ? "News" :
                      name === "social" ? "Social" : "Search",
                    ]}
                  />
                  <Line type="monotone" dataKey="composite" stroke="#14B8A6" strokeWidth={2} dot={false} name="composite" />
                  <Line type="monotone" dataKey="news" stroke="#EC4899" strokeWidth={1.5} dot={false} name="news" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="social" stroke="#3B82F6" strokeWidth={1.5} dot={false} name="social" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="search" stroke="#22C55E" strokeWidth={1.5} dot={false} name="search" strokeDasharray="4 4" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Recent News Table */}
          {Array.isArray(newsItems) && newsItems.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <h3 className="text-base font-semibold text-gray-900 mb-4">
                Recent News ({newsItems.length})
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left py-2 px-3 text-gray-500 font-medium">Date</th>
                      <th className="text-left py-2 px-3 text-gray-500 font-medium">Title</th>
                      <th className="text-left py-2 px-3 text-gray-500 font-medium">Publisher</th>
                      <th className="text-center py-2 px-3 text-gray-500 font-medium">Sentiment</th>
                      <th className="text-center py-2 px-3 text-gray-500 font-medium">PR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(newsItems || []).slice(0, 20).map((item) => (
                      <tr key={item.id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2 px-3 text-gray-600 whitespace-nowrap">
                          {item.published_at ? item.published_at.slice(0, 10) : "-"}
                        </td>
                        <td className="py-2 px-3">
                          <a
                            href={item.article_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 hover:underline line-clamp-1"
                          >
                            {item.article_title || "Untitled"}
                          </a>
                        </td>
                        <td className="py-2 px-3 text-gray-500 whitespace-nowrap">
                          {item.publisher
                            ? new URL(item.publisher).hostname.replace("www.", "").slice(0, 20)
                            : "-"}
                        </td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                            item.sentiment === "positive" ? "bg-green-100 text-green-700" :
                            item.sentiment === "negative" ? "bg-red-100 text-red-700" :
                            "bg-gray-100 text-gray-600"
                          }`}>
                            {item.sentiment === "positive" ? "+" :
                             item.sentiment === "negative" ? "-" : "o"}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center">
                          {item.is_pr && (
                            <span className="inline-block px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700 font-medium">
                              PR
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Launch Impact Intelligence Section ── */}
      {Array.isArray(launchImpacts) && launchImpacts.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-bold text-gray-900">출시 영향력</h2>
          {(launchImpacts || []).map((item) => (
            <div key={item.product.id} className="space-y-3">
              {/* Product Header */}
              <div className="flex items-center gap-3">
                <h3 className="text-base font-semibold text-gray-800">{item.product.name}</h3>
                {item.product.category && (
                  <span className="text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">
                    {item.product.category}
                  </span>
                )}
                {item.latest_score.impact_phase && (
                  <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${
                    item.latest_score.impact_phase === "growth" ? "bg-green-100 text-green-700" :
                    item.latest_score.impact_phase === "peak" ? "bg-orange-100 text-orange-700" :
                    item.latest_score.impact_phase === "decline" ? "bg-red-100 text-red-700" :
                    "bg-gray-100 text-gray-600"
                  }`}>
                    {item.latest_score.impact_phase}
                  </span>
                )}
                <span className="text-xs text-gray-400 ml-auto">
                  {item.mention_count} mentions
                </span>
              </div>

              {/* KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-violet-500 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase">LII</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">
                    {item.latest_score.lii_score?.toFixed(1) ?? "0.0"}
                  </p>
                  <p className="text-[10px] text-gray-400 mt-0.5">Launch Impact Index</p>
                </div>
                <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-rose-500 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase">MRS</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">
                    {item.latest_score.mrs_score?.toFixed(1) ?? "0.0"}
                  </p>
                  <p className="text-[10px] text-gray-400 mt-0.5">Media Reaction Speed</p>
                </div>
                <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-sky-500 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase">RV</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">
                    {item.latest_score.rv_score?.toFixed(1) ?? "0.0"}
                  </p>
                  <p className="text-[10px] text-gray-400 mt-0.5">Reaction Volume</p>
                </div>
                <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-emerald-500 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase">CS</p>
                  <p className="text-2xl font-bold text-gray-900 mt-1">
                    {item.latest_score.cs_score?.toFixed(1) ?? "0.0"}
                  </p>
                  <p className="text-[10px] text-gray-400 mt-0.5">Coverage Spread</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
