"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { PlanGate } from "@/components/PlanGate";
import { PeriodSelector } from "@/components/PeriodSelector";
import { api } from "@/lib/api";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from "recharts";

// ── Authenticated fetch helper (mirrors lib/api.ts fetchApi) ──

async function fetchApi<T>(path: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
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
  const res = await fetch(path, { headers });
  if (!res.ok) {
    throw new Error(`API Error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// ── Types (API response) ──

interface AdvertiserSearchResult {
  id: number;
  name: string;
  brand_name: string | null;
  match_type: string;
}

interface ApiPlatformStats {
  platform: string;
  subscribers: number | null;
  followers: number | null;
  total_posts: number | null;
  avg_likes: number | null;
  avg_views: number | null;
  engagement_rate: number | null;
  posting_frequency: number | null;
}

interface ApiRankingItem {
  advertiser_id: number;
  name: string;
  brand_name: string | null;
  logo_url: string | null;
  platforms: ApiPlatformStats[];
}

interface ApiRankingsResponse {
  items: ApiRankingItem[];
  total: number;
}

interface OverviewData {
  total_monitored_channels: number;
  total_posts_tracked: number;
  avg_engagement_rate: number | null;
  engagement_rate_mom_change: number | null;
  subscribers_mom_change: number | null;
  content_count_mom_change: number | null;
  total_subscribers: number | null;
}

interface ApiDailyPostCount {
  date: string;
  count: number;
}

interface ApiCompareItem {
  advertiser_id: number;
  name: string;
  brand_name: string | null;
  logo_url: string | null;
  platforms: ApiPlatformStats[];
  posting_trend: ApiDailyPostCount[];
}

interface ApiCompareResponse {
  items: ApiCompareItem[];
}

// ── Flattened types for display ──

interface RankingItem {
  rank: number;
  advertiser_id: number;
  advertiser_name: string;
  platform: string;
  followers: number;
  total_posts: number;
  avg_likes: number;
  avg_views: number;
  engagement_rate: number;
  weekly_posting: number;
}

interface CompareAdvertiser {
  advertiser_id: number;
  advertiser_name: string;
  platform: string;
  followers: number;
  total_posts: number;
  avg_likes: number;
  engagement_rate: number;
  weekly_posting: number;
}

interface DailyPostingPoint {
  date: string;
  [key: string]: string | number;
}

// ── Constants ──

const COMPARE_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6"];

const PLATFORM_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "\uC804\uCCB4" },
  { value: "youtube", label: "YouTube" },
  { value: "instagram", label: "Instagram" },
];

// PeriodSelector imported for date range

// ── Helpers ──

function formatLargeNumber(n: number | null | undefined): string {
  if (n == null) return "0";
  if (n >= 100_000_000) {
    return `${(n / 100_000_000).toFixed(1)}\uC5B5`;
  }
  if (n >= 10_000) {
    return `${(n / 10_000).toFixed(1)}\uB9CC`;
  }
  return n.toLocaleString();
}

function formatPercent(v: number | null | undefined): string {
  if (v == null) return "0.0%";
  return `${v.toFixed(1)}%`;
}

function platformLabel(p: string): string {
  if (p === "youtube") return "YouTube";
  if (p === "instagram") return "Instagram";
  return p;
}

function platformColor(p: string): string {
  if (p === "youtube") return "#ef4444";
  if (p === "instagram") return "#e1306c";
  return "#6366f1";
}

function MomIndicator({ value, suffix = "" }: { value: number | null | undefined; suffix?: string }) {
  if (value == null) {
    return (
      <span className="inline-flex items-center text-xs text-gray-400 mt-1">
        -- MoM
      </span>
    );
  }

  const isPositive = value > 0;
  const isNeutral = value === 0;

  if (isNeutral) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-gray-500 mt-1">
        <span>0.0%{suffix}</span>
        <span className="text-gray-400 ml-1">MoM</span>
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-0.5 text-xs font-medium mt-1 ${
        isPositive ? "text-emerald-600" : "text-red-500"
      }`}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        className={`w-3 h-3 ${isPositive ? "" : "rotate-180"}`}
      >
        <path d="m5 15 7-7 7 7" />
      </svg>
      <span>
        {isPositive ? "+" : ""}
        {value.toFixed(1)}%{suffix}
      </span>
      <span className="text-gray-400 font-normal ml-1">MoM</span>
    </span>
  );
}

// ── Component ──

type SocialTab = "channels" | "brand";

export default function SocialChannelsPage() {
  const [tab, setTab] = useState<SocialTab>("channels");

  return (
    <PlanGate>
      <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">소셜 채널 분석</h1>
          <p className="text-sm text-gray-500 mt-1">소셜 채널 랭킹 및 브랜드 채널 모니터링</p>
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6 w-fit">
          {([
            { key: "channels" as SocialTab, label: "채널 랭킹" },
            { key: "brand" as SocialTab, label: "브랜드 채널" },
          ]).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                tab === t.key ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        {tab === "channels" ? <SocialChannelsContent /> : <BrandChannelsContent />}
      </div>
    </PlanGate>
  );
}

function SocialChannelsContent() {
  const router = useRouter();
  const [platform, setPlatform] = useState("");
  const [days, setDays] = useState(30);
  const [advertiserSearch, setAdvertiserSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedAdvertisers, setSelectedAdvertisers] = useState<
    { id: number; name: string }[]
  >([]);
  const [sortKey, setSortKey] = useState<keyof RankingItem>("rank");
  const [sortAsc, setSortAsc] = useState(true);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(advertiserSearch), 300);
    return () => clearTimeout(timer);
  }, [advertiserSearch]);

  // Click outside to close dropdown
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const selectedIds = selectedAdvertisers.map((a) => a.id);

  // ── Queries ──

  const { data: searchResults } = useQuery<AdvertiserSearchResult[]>({
    queryKey: ["advertiserSearch", debouncedSearch],
    queryFn: () =>
      fetchApi<AdvertiserSearchResult[]>(`/api/advertisers/search?q=${encodeURIComponent(debouncedSearch)}&limit=20`),
    enabled: debouncedSearch.length >= 1,
  });

  const { data: overview } = useQuery<OverviewData>({
    queryKey: ["socialOverview"],
    queryFn: () => fetchApi<OverviewData>(`/api/social-channels/overview`),
    staleTime: 5 * 60 * 1000,
  });

  const rankingsUrl = `/api/social-channels/rankings?days=${days}&limit=20${platform ? `&platform=${platform}` : ""}`;
  const {
    data: rankingsRaw,
    isLoading: rankingsLoading,
  } = useQuery<ApiRankingsResponse>({
    queryKey: ["socialRankings", days, platform],
    queryFn: () => fetchApi<ApiRankingsResponse>(rankingsUrl),
    enabled: selectedIds.length < 2,
  });

  // Flatten nested platforms into flat ranking items
  const rankingsData = useMemo(() => {
    if (!rankingsRaw?.items) return { items: [] as RankingItem[], total: 0 };
    const flat: RankingItem[] = [];
    let rank = 1;
    for (const item of rankingsRaw.items) {
      if (item.platforms && item.platforms.length > 0) {
        for (const p of item.platforms) {
          flat.push({
            rank: rank++,
            advertiser_id: item.advertiser_id,
            advertiser_name: item.name,
            platform: p.platform,
            followers: p.subscribers ?? p.followers ?? 0,
            total_posts: p.total_posts ?? 0,
            avg_likes: p.avg_likes ?? 0,
            avg_views: p.avg_views ?? 0,
            engagement_rate: p.engagement_rate ?? 0,
            weekly_posting: p.posting_frequency ?? 0,
          });
        }
      } else {
        flat.push({
          rank: rank++,
          advertiser_id: item.advertiser_id,
          advertiser_name: item.name,
          platform: "-",
          followers: 0,
          total_posts: 0,
          avg_likes: 0,
          avg_views: 0,
          engagement_rate: 0,
          weekly_posting: 0,
        });
      }
    }
    return { items: flat, total: rankingsRaw.total };
  }, [rankingsRaw]);

  const compareUrl = `/api/social-channels/compare?days=${days}&advertiser_ids=${selectedIds.join(",")}`;
  const {
    data: compareRaw,
    isLoading: compareLoading,
  } = useQuery<ApiCompareResponse>({
    queryKey: ["socialCompare", days, selectedIds.join(",")],
    queryFn: () => fetchApi<ApiCompareResponse>(compareUrl),
    enabled: selectedIds.length >= 2,
  });

  // Transform compare API response to flat format
  const compareData = useMemo(() => {
    if (!compareRaw?.items) return null;
    const advertisers: CompareAdvertiser[] = [];
    for (const item of compareRaw.items) {
      const bestPlatform = item.platforms?.[0];
      advertisers.push({
        advertiser_id: item.advertiser_id,
        advertiser_name: item.name,
        platform: bestPlatform?.platform ?? "-",
        followers: bestPlatform?.subscribers ?? bestPlatform?.followers ?? 0,
        total_posts: bestPlatform?.total_posts ?? 0,
        avg_likes: bestPlatform?.avg_likes ?? 0,
        engagement_rate: bestPlatform?.engagement_rate ?? 0,
        weekly_posting: bestPlatform?.posting_frequency ?? 0,
      });
    }
    // Merge daily posting trends into a single array with advertiser names as keys
    const dateMap: Record<string, DailyPostingPoint> = {};
    for (const item of compareRaw.items) {
      for (const dp of (item.posting_trend ?? [])) {
        if (!dateMap[dp.date]) {
          dateMap[dp.date] = { date: dp.date };
        }
        dateMap[dp.date][item.name] = dp.count;
      }
    }
    const daily_posting = Object.values(dateMap).sort((a, b) =>
      a.date.localeCompare(b.date)
    );
    return { advertisers, daily_posting };
  }, [compareRaw]);

  // ── Handlers ──

  const handleSelectAdvertiser = useCallback(
    (adv: AdvertiserSearchResult) => {
      if (selectedAdvertisers.length >= 5) return;
      if (selectedAdvertisers.some((s) => s.id === adv.id)) return;
      setSelectedAdvertisers((prev) => [
        ...prev,
        { id: adv.id, name: adv.name },
      ]);
      setAdvertiserSearch("");
      setShowDropdown(false);
    },
    [selectedAdvertisers]
  );

  const handleRemoveAdvertiser = useCallback((id: number) => {
    setSelectedAdvertisers((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const handleSort = useCallback(
    (key: keyof RankingItem) => {
      if (sortKey === key) {
        setSortAsc(!sortAsc);
      } else {
        setSortKey(key);
        // 숫자 컬럼은 내림차순(큰 값 먼저)이 기본, rank만 오름차순
        setSortAsc(key === "rank" || key === "advertiser_name" || key === "platform");
      }
    },
    [sortKey, sortAsc]
  );

  // ── Sorted rankings ──

  const sortedRankings = useMemo(() => {
    if (!rankingsData?.items) return [];
    const items = [...rankingsData.items];
    items.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") {
        return sortAsc ? av - bv : bv - av;
      }
      return sortAsc
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return items;
  }, [rankingsData, sortKey, sortAsc]);

  // ── Compare chart data ──

  const followerChartData = useMemo(() => {
    if (!compareData?.advertisers?.length) return [];
    return compareData.advertisers.map((a, i) => ({
      name:
        a.advertiser_name.length > 10
          ? a.advertiser_name.slice(0, 10) + "..."
          : a.advertiser_name,
      fullName: a.advertiser_name,
      value: a.followers ?? 0,
      fill: COMPARE_COLORS[i % COMPARE_COLORS.length],
    }));
  }, [compareData]);

  const engagementChartData = useMemo(() => {
    if (!compareData?.advertisers?.length) return [];
    return compareData.advertisers.map((a, i) => ({
      name:
        a.advertiser_name.length > 10
          ? a.advertiser_name.slice(0, 10) + "..."
          : a.advertiser_name,
      fullName: a.advertiser_name,
      value: a.engagement_rate ?? 0,
      fill: COMPARE_COLORS[i % COMPARE_COLORS.length],
    }));
  }, [compareData]);

  // ── KPI values ──

  const kpis = useMemo(() => {
    if (overview) {
      // Compute weekly posting from rankings data if available
      const totalWeekly = rankingsData.items.reduce((sum, r) => sum + r.weekly_posting, 0);
      const avgWeekly = rankingsData.items.length > 0 ? totalWeekly / rankingsData.items.length : 0;
      return {
        channels: overview.total_monitored_channels ?? 0,
        posts: overview.total_posts_tracked ?? 0,
        engagement: overview.avg_engagement_rate ?? 0,
        weekly: avgWeekly,
        totalSubscribers: overview.total_subscribers ?? 0,
        engagementMom: overview.engagement_rate_mom_change ?? null,
        subscribersMom: overview.subscribers_mom_change ?? null,
        contentMom: overview.content_count_mom_change ?? null,
      };
    }
    return {
      channels: 0, posts: 0, engagement: 0, weekly: 0,
      totalSubscribers: 0, engagementMom: null, subscribersMom: null, contentMom: null,
    };
  }, [overview, rankingsData]);

  // ── Render ──

  return (
    <div>
      {/* Filters Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {/* Platform filter */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            플랫폼
          </label>
          <div className="flex gap-2">
            {PLATFORM_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setPlatform(opt.value)}
                className={`flex-1 py-2 text-sm rounded-lg font-medium transition-colors ${
                  platform === opt.value
                    ? "bg-adscope-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Period */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            분석 기간
          </label>
          <PeriodSelector days={days} onDaysChange={setDays} />
        </div>

        {/* Advertiser multi-select */}
        <div
          className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm"
          ref={dropdownRef}
        >
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            광고주 비교 (최대 5개)
          </label>
          <div className="relative">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              placeholder="광고주명 검색..."
              value={advertiserSearch}
              onChange={(e) => {
                setAdvertiserSearch(e.target.value);
                setShowDropdown(true);
              }}
              onFocus={() =>
                debouncedSearch.length >= 1 && setShowDropdown(true)
              }
              className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500/20 focus:border-adscope-500"
            />
            {showDropdown && searchResults && searchResults.length > 0 && (
              <div className="absolute z-20 left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                {searchResults
                  .filter((r) => !selectedIds.includes(r.id))
                  .map((r) => (
                    <button
                      key={r.id}
                      onClick={() => handleSelectAdvertiser(r)}
                      className="w-full text-left flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 transition-colors"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {r.name}
                        </p>
                        {r.brand_name && (
                          <p className="text-xs text-gray-500 truncate">
                            {r.brand_name}
                          </p>
                        )}
                      </div>
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                        {r.match_type === "exact"
                          ? "\uC815\uD655"
                          : r.match_type === "alias"
                            ? "\uBCC4\uCE6D"
                            : "\uD558\uC704"}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>
          {/* Selected tags */}
          {selectedAdvertisers.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {selectedAdvertisers.map((adv, i) => (
                <span
                  key={adv.id}
                  className="inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full text-white"
                  style={{
                    backgroundColor: COMPARE_COLORS[i % COMPARE_COLORS.length],
                  }}
                >
                  {adv.name}
                  <button
                    onClick={() => handleRemoveAdvertiser(adv.id)}
                    className="ml-0.5 hover:opacity-70"
                    aria-label={`${adv.name} \uC81C\uAC70`}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      className="w-3 h-3"
                    >
                      <path d="M18 6 6 18M6 6l12 12" />
                    </svg>
                  </button>
                </span>
              ))}
              {selectedAdvertisers.length > 0 && (
                <button
                  onClick={() => setSelectedAdvertisers([])}
                  className="text-xs text-gray-400 hover:text-gray-600 px-1"
                >
                  전체 해제
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            모니터링 채널 수
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {kpis.channels.toLocaleString()}
          </p>
          {kpis.totalSubscribers > 0 && (
            <p className="text-xs text-gray-400 mt-1">
              총 구독자 {formatLargeNumber(kpis.totalSubscribers)}
            </p>
          )}
          <MomIndicator value={kpis.subscribersMom} />
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            총 게시물
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {formatLargeNumber(kpis.posts)}
          </p>
          <MomIndicator value={kpis.contentMom} />
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            평균 인게이지먼트율
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {formatPercent(kpis.engagement)}
          </p>
          <MomIndicator value={kpis.engagementMom} />
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            주간 포스팅 빈도
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {kpis.weekly.toFixed(1)}
          </p>
        </div>
      </div>

      {/* Section A: Rankings Table (no comparison selected) */}
      {selectedIds.length < 2 && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-sm font-semibold text-gray-700">
                소셜 채널 활동 랭킹
              </h2>
              <p className="text-xs text-gray-400 mt-0.5">
                광고주 소셜 채널 활동량 기준 순위 &middot; 클릭하여 상세 보기
              </p>
            </div>

            {rankingsLoading ? (
              <div className="p-12 text-center text-gray-400 text-sm">
                랭킹 데이터 로딩 중...
              </div>
            ) : sortedRankings.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      {([
                        ["rank", "순위"],
                        ["advertiser_name", "광고주"],
                        ["platform", "플랫폼"],
                        ["followers", "구독자/팔로워"],
                        ["total_posts", "총 게시물"],
                        ["avg_likes", "평균 좋아요"],
                        ["engagement_rate", "인게이지먼트율"],
                        ["weekly_posting", "주간 포스팅"],
                      ] as [keyof RankingItem, string][]).map(
                        ([key, label]) => {
                          const isActive = sortKey === key;
                          return (
                            <th
                              key={key}
                              onClick={() => handleSort(key)}
                              className={`py-3 px-4 text-xs font-semibold uppercase cursor-pointer select-none transition-colors ${
                                isActive
                                  ? "text-adscope-700 bg-adscope-50/50"
                                  : "text-gray-500 hover:text-gray-700 hover:bg-gray-100/50"
                              } ${
                                key === "advertiser_name" || key === "platform"
                                  ? "text-left"
                                  : "text-right"
                              }`}
                            >
                              <span className={`inline-flex items-center gap-1.5 ${
                                key !== "advertiser_name" && key !== "platform" ? "justify-end" : ""
                              }`}>
                                {label}
                                {isActive && (
                                  <span className="text-adscope-600 text-sm font-bold">
                                    {sortAsc ? "\u2191" : "\u2193"}
                                  </span>
                                )}
                                {!isActive && (
                                  <span className="text-gray-300 text-xs">\u2195</span>
                                )}
                              </span>
                            </th>
                          );
                        }
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedRankings.map((item) => (
                      <tr
                        key={`${item.advertiser_id}-${item.platform}`}
                        onClick={() => router.push(`/advertisers/${item.advertiser_id}`)}
                        className="border-b border-gray-50 hover:bg-adscope-50/40 transition-colors cursor-pointer group"
                        style={{
                          borderLeft: `3px solid ${platformColor(item.platform)}`,
                        }}
                      >
                        <td className="py-3 px-4 text-right tabular-nums text-gray-400">
                          {item.rank}
                        </td>
                        <td className="py-3 px-4 font-medium">
                          <Link
                            href={`/advertisers/${item.advertiser_id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="text-gray-900 hover:text-adscope-600 transition-colors group-hover:text-adscope-600"
                          >
                            <span className="inline-flex items-center gap-1.5">
                              {item.advertiser_name}
                              <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity text-adscope-400"
                              >
                                <path d="M9 18l6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            </span>
                          </Link>
                        </td>
                        <td className="py-3 px-4">
                          <span
                            className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
                            style={{
                              color: platformColor(item.platform),
                              backgroundColor:
                                item.platform === "youtube"
                                  ? "#fef2f2"
                                  : "#fdf2f8",
                            }}
                          >
                            {platformLabel(item.platform)}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                          {formatLargeNumber(item.followers)}
                        </td>
                        <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                          {formatLargeNumber(item.total_posts)}
                        </td>
                        <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                          {formatLargeNumber(item.avg_likes)}
                        </td>
                        <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                          {formatPercent(item.engagement_rate)}
                        </td>
                        <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                          {item.weekly_posting.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-12 text-center">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  className="w-10 h-10 mx-auto mb-3 text-gray-300"
                >
                  <rect x="3" y="3" width="7" height="7" rx="1" />
                  <rect x="14" y="3" width="7" height="7" rx="1" />
                  <rect x="3" y="14" width="7" height="7" rx="1" />
                  <rect x="14" y="14" width="7" height="7" rx="1" />
                </svg>
                <p className="text-sm text-gray-400">
                  소셜 채널 랭킹 데이터가 없습니다
                </p>
                <p className="text-xs text-gray-300 mt-1">
                  소셜 채널 모니터링 데이터가 축적되면 자동으로 표시됩니다
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Section B: Comparison View (2+ advertisers selected) */}
      {selectedIds.length >= 2 && (
        <div className="space-y-6">
          {compareLoading ? (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 text-sm shadow-sm">
              비교 데이터 로딩 중...
            </div>
          ) : compareData && compareData.advertisers && compareData.advertisers.length > 0 ? (
            <>
              {/* Charts: 2-column on large screens */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Bar Chart: Followers */}
                <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                  <h3 className="text-sm font-semibold text-gray-700 mb-4">
                    구독자/팔로워 비교
                  </h3>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart
                      data={followerChartData}
                      layout="vertical"
                      margin={{ left: 10, right: 20 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#f0f0f0"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => formatLargeNumber(v)}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={100}
                        tick={{ fontSize: 11 }}
                      />
                      <Tooltip
                        formatter={(value: number) => [
                          formatLargeNumber(value),
                          "구독자/팔로워",
                        ]}
                        labelFormatter={(_, payload) => {
                          const item = payload?.[0]?.payload;
                          return item?.fullName ?? "";
                        }}
                        contentStyle={{
                          borderRadius: 8,
                          border: "1px solid #e5e7eb",
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {followerChartData.map((entry, idx) => (
                          <Cell key={idx} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Bar Chart: Engagement Rate */}
                <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                  <h3 className="text-sm font-semibold text-gray-700 mb-4">
                    평균 인게이지먼트율 비교
                  </h3>
                  <ResponsiveContainer width="100%" height={280}>
                    <BarChart
                      data={engagementChartData}
                      layout="vertical"
                      margin={{ left: 10, right: 20 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="#f0f0f0"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => `${v.toFixed(1)}%`}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        width={100}
                        tick={{ fontSize: 11 }}
                      />
                      <Tooltip
                        formatter={(value: number) => [
                          formatPercent(value),
                          "인게이지먼트율",
                        ]}
                        labelFormatter={(_, payload) => {
                          const item = payload?.[0]?.payload;
                          return item?.fullName ?? "";
                        }}
                        contentStyle={{
                          borderRadius: 8,
                          border: "1px solid #e5e7eb",
                          fontSize: 12,
                        }}
                      />
                      <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {engagementChartData.map((entry, idx) => (
                          <Cell key={idx} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Line Chart: Daily Posting Trend */}
              {compareData.daily_posting &&
                compareData.daily_posting.length > 0 && (
                  <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
                    <h3 className="text-sm font-semibold text-gray-700 mb-4">
                      포스팅 추이
                    </h3>
                    <ResponsiveContainer width="100%" height={320}>
                      <LineChart
                        data={compareData.daily_posting}
                        margin={{ left: 0, right: 10, top: 5, bottom: 5 }}
                      >
                        <CartesianGrid
                          strokeDasharray="3 3"
                          stroke="#f0f0f0"
                        />
                        <XAxis
                          dataKey="date"
                          tick={{ fontSize: 11 }}
                          tickFormatter={(v) => {
                            const d = new Date(v);
                            return `${d.getMonth() + 1}/${d.getDate()}`;
                          }}
                        />
                        <YAxis
                          tick={{ fontSize: 11 }}
                          allowDecimals={false}
                        />
                        <Tooltip
                          contentStyle={{
                            borderRadius: 8,
                            border: "1px solid #e5e7eb",
                            fontSize: 12,
                          }}
                        />
                        <Legend
                          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                        />
                        {selectedAdvertisers.map((adv, i) => (
                          <Line
                            key={adv.id}
                            type="monotone"
                            dataKey={adv.name}
                            stroke={
                              COMPARE_COLORS[i % COMPARE_COLORS.length]
                            }
                            strokeWidth={2}
                            dot={{ r: 2 }}
                            activeDot={{ r: 4 }}
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}

              {/* Detail Comparison Table */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-100">
                  <h3 className="text-sm font-semibold text-gray-700">
                    상세 비교
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          지표
                        </th>
                        {compareData.advertisers.map((adv, i) => (
                          <th
                            key={adv.advertiser_id}
                            className="text-right py-3 px-4 text-xs font-semibold uppercase"
                            style={{
                              color:
                                COMPARE_COLORS[i % COMPARE_COLORS.length],
                            }}
                          >
                            {adv.advertiser_name}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {([
                        [
                          "플랫폼",
                          (a: CompareAdvertiser) => platformLabel(a.platform),
                        ],
                        [
                          "구독자/팔로워",
                          (a: CompareAdvertiser) =>
                            formatLargeNumber(a.followers),
                        ],
                        [
                          "총 게시물",
                          (a: CompareAdvertiser) =>
                            formatLargeNumber(a.total_posts),
                        ],
                        [
                          "평균 좋아요",
                          (a: CompareAdvertiser) =>
                            formatLargeNumber(a.avg_likes),
                        ],
                        [
                          "인게이지먼트율",
                          (a: CompareAdvertiser) =>
                            formatPercent(a.engagement_rate),
                        ],
                        [
                          "주간 포스팅",
                          (a: CompareAdvertiser) =>
                            (a.weekly_posting ?? 0).toFixed(1),
                        ],
                      ] as [string, (a: CompareAdvertiser) => string][]).map(
                        ([label, fn]) => (
                          <tr
                            key={label}
                            className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                          >
                            <td className="py-3 px-4 font-medium text-gray-700">
                              {label}
                            </td>
                            {compareData.advertisers.map((adv) => (
                              <td
                                key={adv.advertiser_id}
                                className="py-3 px-4 text-right tabular-nums text-gray-900"
                              >
                                {fn(adv)}
                              </td>
                            ))}
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="w-10 h-10 mx-auto mb-3 text-gray-300"
              >
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              <p className="text-sm text-gray-400">
                선택한 광고주의 소셜 채널 비교 데이터가 없습니다
              </p>
              <p className="text-xs text-gray-300 mt-1">
                소셜 채널 데이터가 수집된 광고주를 선택해 주세요
              </p>
            </div>
          )}
        </div>
      )}

      {/* Empty initial state: nothing selected and no rankings */}
      {selectedIds.length >= 1 && selectedIds.length < 2 && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm mt-6">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="w-10 h-10 mx-auto mb-3 text-gray-300"
          >
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <line x1="20" y1="8" x2="20" y2="14" />
            <line x1="23" y1="11" x2="17" y2="11" />
          </svg>
          <p className="text-sm text-gray-500">
            비교 분석을 하려면 광고주를 1개 더 선택해 주세요
          </p>
          <p className="text-xs text-gray-300 mt-1">
            최소 2개 이상 선택 시 비교 차트가 표시됩니다
          </p>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// Tab 2: 브랜드 채널 모니터
// ═══════════════════════════════════════

interface BrandChannelStats {
  monitored_brands: number;
  total_channels: number;
  total_contents: number;
  new_this_week: number;
  ad_content_count: number;
}

interface BrandContentItem {
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
  discovered_at: string | null;
}

const BRAND_PLATFORM_BADGES: Record<string, { label: string; className: string }> = {
  youtube: { label: "YouTube", className: "bg-red-100 text-red-800" },
  instagram: { label: "Instagram", className: "bg-pink-100 text-pink-800" },
};

const BRAND_PLATFORM_OPTIONS = [
  { value: "", label: "전체 플랫폼" },
  { value: "youtube", label: "YouTube" },
  { value: "instagram", label: "Instagram" },
];

function formatBrandViewCount(count: number | null): string {
  if (count === null || count === undefined) return "-";
  if (count >= 100_000_000) return `${(count / 100_000_000).toFixed(1)}억`;
  if (count >= 10_000) return `${(count / 10_000).toFixed(1)}만`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}천`;
  return count.toLocaleString();
}

function formatBrandDuration(seconds: number | null): string {
  if (!seconds) return "";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatBrandDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  try {
    return new Date(dateStr).toLocaleDateString("ko-KR", { year: "numeric", month: "short", day: "numeric" });
  } catch { return dateStr; }
}

function BrandChannelsContent() {
  const [brandPlatform, setBrandPlatform] = useState("");
  const [isAdOnly, setIsAdOnly] = useState(false);
  const [brandDays, setBrandDays] = useState(30);

  const { data: stats } = useQuery<BrandChannelStats>({
    queryKey: ["brand-channel-stats"],
    queryFn: () => api.getBrandChannelStats(),
  });

  const { data: recentUploads, isLoading, isError } = useQuery<BrandContentItem[]>({
    queryKey: ["brand-recent-uploads", brandPlatform, isAdOnly, brandDays],
    queryFn: () =>
      api.getBrandRecentUploads({
        days: brandDays, limit: 50,
        platform: brandPlatform || undefined,
        is_ad: isAdOnly ? true : undefined,
      }),
  });

  const filteredItems = useMemo(() => recentUploads ?? [], [recentUploads]);

  return (
    <div>
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <BrandKpiCard label="모니터링 브랜드" value={stats?.monitored_brands ?? 0} />
        <BrandKpiCard label="전체 채널" value={stats?.total_channels ?? 0} />
        <BrandKpiCard label="이번 주 신규" value={stats?.new_this_week ?? 0} accent />
        <BrandKpiCard label="광고/협찬 콘텐츠" value={stats?.ad_content_count ?? 0} />
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">플랫폼</p>
            <div className="flex gap-2">
              {BRAND_PLATFORM_OPTIONS.map((opt) => (
                <button key={opt.value} onClick={() => setBrandPlatform(opt.value)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                    brandPlatform === opt.value
                      ? "bg-adscope-600 text-white border-adscope-600"
                      : "bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                  }`}>{opt.label}</button>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">콘텐츠 유형</p>
            <button onClick={() => setIsAdOnly(!isAdOnly)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                isAdOnly ? "bg-amber-500 text-white border-amber-500" : "bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50"
              }`}>광고/협찬만</button>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">기간</p>
            <PeriodSelector days={brandDays} onDaysChange={setBrandDays} />
          </div>
          <div className="ml-auto self-end">
            <button onClick={() => { setBrandPlatform(""); setIsAdOnly(false); setBrandDays(30); }}
              className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">초기화</button>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between mb-4">
        <p className="text-sm text-gray-500">총 <span className="font-semibold text-gray-900">{filteredItems.length}</span>건</p>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
              <div className="h-48 w-full bg-gray-200 animate-pulse" />
              <div className="p-3 space-y-2">
                <div className="h-4 w-3/4 bg-gray-200 animate-pulse rounded" />
                <div className="h-3 w-1/2 bg-gray-200 animate-pulse rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <p className="text-sm text-gray-500">브랜드 채널 데이터를 불러오지 못했습니다</p>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <p className="text-sm text-gray-500">데이터 수집 준비 중</p>
          <p className="text-xs text-gray-400 mt-1">광고주에 공식 채널을 등록하고 브랜드 모니터 스크립트를 실행하면 콘텐츠가 표시됩니다</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {filteredItems.map((item) => <BrandContentCard key={item.id} item={item} />)}
        </div>
      )}
    </div>
  );
}

function BrandKpiCard({ label, value, accent = false }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${accent ? "bg-adscope-100 text-adscope-600" : "bg-gray-100 text-gray-500"}`}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
            <path d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0H5m14 0h2m-16 0H3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <p className="text-2xl font-bold text-gray-900 tabular-nums">{value.toLocaleString()}</p>
          <p className="text-xs text-gray-500">{label}</p>
        </div>
      </div>
    </div>
  );
}

function BrandContentCard({ item }: { item: BrandContentItem }) {
  const [thumbError, setThumbError] = useState(false);
  const badge = BRAND_PLATFORM_BADGES[item.platform] ?? { label: item.platform, className: "bg-gray-100 text-gray-700" };
  const dateStr = formatBrandDate(item.discovered_at || item.upload_date);
  const durationStr = formatBrandDuration(item.duration_seconds);
  const viewStr = formatBrandViewCount(item.view_count);
  const showThumb = item.thumbnail_url && !thumbError;

  let contentUrl: string | null = null;
  if (item.platform === "youtube" && item.content_id) contentUrl = `https://www.youtube.com/watch?v=${item.content_id}`;
  else if (item.platform === "instagram" && item.content_id) contentUrl = `https://www.instagram.com/p/${item.content_id}/`;

  return (
    <div className={`bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm hover:shadow-md hover:border-gray-300 transition-all group ${contentUrl ? "cursor-pointer" : ""}`}
      onClick={() => contentUrl && window.open(contentUrl, "_blank", "noopener,noreferrer")}>
      <div className="relative aspect-video bg-gray-100 overflow-hidden">
        {showThumb ? (
          <img src={item.thumbnail_url!} alt={item.title || "thumbnail"} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy" referrerPolicy="no-referrer" onError={() => setThumbError(true)} />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400">
            <p className="text-xs">썸네일 없음</p>
          </div>
        )}
        <span className={`absolute top-2 left-2 px-2 py-0.5 rounded text-[10px] font-medium ${badge.className}`}>{badge.label}</span>
        {durationStr && <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-medium bg-black/70 text-white">{durationStr}</span>}
        {item.is_ad_content && <span className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-400 text-amber-900">AD</span>}
      </div>
      <div className="p-3">
        <p className="text-sm font-semibold text-gray-900 line-clamp-2 leading-tight">{item.title || item.content_id}</p>
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2 text-[10px] text-gray-500">
            {item.content_type && <span className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded">{item.content_type}</span>}
            {viewStr !== "-" && <span>조회 {viewStr}</span>}
          </div>
          <span className="text-[10px] text-gray-400">{dateStr}</span>
        </div>
      </div>
    </div>
  );
}
