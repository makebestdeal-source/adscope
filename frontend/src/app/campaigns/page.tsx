"use client";

import { useState, useEffect, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatChannel, formatSpend, CHANNEL_COLORS } from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, ReferenceLine, Cell,
} from "recharts";

// ── Tab types ──

type CampaignTab = "list" | "effect" | "impact" | "signal";

const TABS: { key: CampaignTab; label: string }[] = [
  { key: "list", label: "캠페인 목록" },
  { key: "effect", label: "캠페인 효과" },
  { key: "impact", label: "소셜 임팩트" },
  { key: "signal", label: "메타시그널" },
];

export default function CampaignsPage() {
  const [tab, setTab] = useState<CampaignTab>("list");

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-cyan-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
            <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">캠페인</h1>
          <p className="text-sm text-gray-500">캠페인 목록, 효과 분석, 브랜드 임팩트, 메타시그널</p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6 w-fit">
        {TABS.map((t) => (
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

      {tab === "list" && <CampaignListTab />}
      {tab === "effect" && <CampaignEffectTab />}
      {tab === "impact" && <SocialImpactTab />}
      {tab === "signal" && <MetaSignalTab />}
    </div>
  );
}

// ═══════════════════════════════════════
// Tab 1: 캠페인 목록
// ═══════════════════════════════════════

interface EnrichedCampaign {
  id: number;
  advertiser_id: number;
  advertiser_name: string | null;
  channel: string;
  campaign_name: string | null;
  objective: string | null;
  product_service: string | null;
  model_info: string | null;
  promotion_copy: string | null;
  first_seen: string | null;
  last_seen: string | null;
  is_active: boolean;
  total_est_spend: number;
  snapshot_count: number;
  status: string | null;
}

const OBJECTIVE_KO: Record<string, { label: string; color: string }> = {
  brand_awareness: { label: "인지", color: "bg-purple-100 text-purple-700" },
  traffic: { label: "트래픽", color: "bg-blue-100 text-blue-700" },
  engagement: { label: "참여", color: "bg-green-100 text-green-700" },
  conversion: { label: "전환", color: "bg-orange-100 text-orange-700" },
  retention: { label: "리텐션", color: "bg-teal-100 text-teal-700" },
};

const CHANNELS = [
  "", "naver_search", "naver_da", "google_gdn", "google_search_ads",
  "youtube_ads", "kakao_da", "facebook", "instagram", "tiktok", "naver_shopping",
];

type SortKey = "advertiser_name" | "channel" | "campaign_name" | "objective" | "total_est_spend" | "last_seen" | "snapshot_count" | "status";

function CampaignListTab() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [channel, setChannel] = useState("");
  const [activeFilter, setActiveFilter] = useState<string>("");
  const [sortKey, setSortKey] = useState<SortKey>("last_seen");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(0);
  const pageSize = 50;

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const { data, isLoading } = useQuery({
    queryKey: ["campaigns-enriched", channel, activeFilter, debouncedSearch, sortKey, sortDir, page],
    queryFn: () =>
      api.get<{ total: number; items: EnrichedCampaign[] }>(
        `/api/campaigns/enriched?` +
        new URLSearchParams({
          ...(channel ? { channel } : {}),
          ...(activeFilter ? { is_active: activeFilter } : {}),
          ...(debouncedSearch ? { search: debouncedSearch } : {}),
          sort_by: sortKey, sort_dir: sortDir,
          limit: String(pageSize), offset: String(page * pageSize),
        }).toString()
      ),
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalSpendSum = (data as any)?.total_spend_sum ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) { setSortDir(sortDir === "asc" ? "desc" : "asc"); }
    else { setSortKey(key); setSortDir(key === "total_est_spend" || key === "last_seen" || key === "snapshot_count" ? "desc" : "asc"); }
    setPage(0);
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    const isActive = sortKey === col;
    return (
      <span className={`inline-flex flex-col text-[8px] leading-[8px] ml-1 ${isActive ? "text-adscope-600" : "text-gray-300"}`}>
        <span className={isActive && sortDir === "asc" ? "text-adscope-600" : isActive ? "text-gray-300" : ""}>&#9650;</span>
        <span className={isActive && sortDir === "desc" ? "text-adscope-600" : isActive ? "text-gray-300" : ""}>&#9660;</span>
      </span>
    );
  };

  const activeCount = items.filter(c => c.is_active).length;

  return (
    <>
      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
            <circle cx="11" cy="11" r="7" /><path d="m21 21-4.35-4.35" />
          </svg>
          <input type="text" placeholder="광고주명, 캠페인명, 모델명 검색..." value={search}
            onChange={(e) => { setSearch(e.target.value); setDebouncedSearch(e.target.value); setPage(0); }}
            className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500/20 focus:border-adscope-500" />
        </div>
        <select value={channel} onChange={(e) => { setChannel(e.target.value); setPage(0); }}
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-adscope-500/20">
          <option value="">전체 매체</option>
          {CHANNELS.filter(Boolean).map(ch => <option key={ch} value={ch}>{formatChannel(ch)}</option>)}
        </select>
        <div className="flex gap-0.5 bg-gray-100 rounded-lg p-0.5">
          {[{ label: "전체", value: "" }, { label: "활성", value: "true" }, { label: "종료", value: "false" }].map(opt => (
            <button key={opt.value} onClick={() => { setActiveFilter(opt.value); setPage(0); }}
              className={`px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors ${
                activeFilter === opt.value ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>{opt.label}</button>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase">전체 캠페인</p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">{total.toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase">현재 페이지 활성</p>
          <p className="text-2xl font-bold text-green-600 mt-1 tabular-nums">{activeCount}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase">페이지</p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">{page + 1} / {Math.max(1, totalPages)}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase">총 추정 광고비</p>
          <p className="text-lg font-bold text-gray-900 mt-1 tabular-nums">{formatSpend(totalSpendSum)}</p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {([
                  ["advertiser_name", "광고주", "text-left"], ["campaign_name", "캠페인명", "text-left"],
                  ["channel", "매체", "text-left"], ["objective", "목적", "text-left"],
                  ["total_est_spend", "추정 광고비", "text-right"], ["last_seen", "최근 활동", "text-right"],
                  ["snapshot_count", "스냅샷", "text-right"], ["status", "상태", "text-center"],
                ] as [SortKey, string, string][]).map(([key, label, align]) => (
                  <th key={key} onClick={() => handleSort(key)}
                    className={`py-3 px-4 text-xs font-semibold uppercase cursor-pointer select-none transition-colors ${
                      sortKey === key ? "text-adscope-700 bg-adscope-50/50" : "text-gray-500 hover:text-gray-700 hover:bg-gray-100/50"} ${align}`}>
                    <span className={`inline-flex items-center gap-0.5 ${align === "text-right" ? "justify-end" : align === "text-center" ? "justify-center" : ""}`}>
                      {label}<SortIcon col={key} />
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="border-b border-gray-50">
                    {Array.from({ length: 8 }).map((_, j) => <td key={j} className="py-3 px-4"><div className="skeleton h-4 w-20" /></td>)}
                  </tr>
                ))
              ) : items.length > 0 ? (
                items.map((c) => {
                  const obj = c.objective ? OBJECTIVE_KO[c.objective] : null;
                  return (
                    <tr key={c.id} className="border-b border-gray-50 hover:bg-adscope-50/30 transition-colors group">
                      <td className="py-3 px-4">
                        <Link href={`/advertisers/${c.advertiser_id}`} className="text-sm font-medium text-adscope-600 hover:text-adscope-800 hover:underline">
                          {c.advertiser_name || "-"}
                        </Link>
                      </td>
                      <td className="py-3 px-4">
                        <Link href={`/campaigns/${c.id}`} className="text-sm text-gray-900 hover:text-adscope-600 hover:underline font-medium">
                          {c.campaign_name || `#${c.id}`}
                        </Link>
                        {c.model_info && <span className="ml-1.5 text-[10px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded">{c.model_info}</span>}
                        {c.product_service && <p className="text-xs text-gray-400 mt-0.5 truncate max-w-[250px]">{c.product_service}</p>}
                      </td>
                      <td className="py-3 px-4">
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded"
                          style={{ backgroundColor: (CHANNEL_COLORS[c.channel] || "#666") + "18", color: CHANNEL_COLORS[c.channel] || "#666" }}>
                          {formatChannel(c.channel)}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        {obj ? <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${obj.color}`}>{obj.label}</span> : <span className="text-gray-300 text-xs">-</span>}
                      </td>
                      <td className="py-3 px-4 text-right tabular-nums"><span className="font-medium text-gray-900">{formatSpend(c.total_est_spend)}</span></td>
                      <td className="py-3 px-4 text-right text-xs text-gray-500 tabular-nums">{c.last_seen ? c.last_seen.slice(0, 10) : "-"}</td>
                      <td className="py-3 px-4 text-right tabular-nums text-gray-600">{c.snapshot_count}</td>
                      <td className="py-3 px-4 text-center">
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${c.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                          {c.is_active ? "활성" : "종료"}
                        </span>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr><td colSpan={8} className="py-12 text-center text-gray-400 text-sm">{search ? `"${search}" 검색 결과가 없습니다` : "캠페인이 없습니다"}</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between">
            <p className="text-xs text-gray-500">전체 {total.toLocaleString()}건 중 {page * pageSize + 1}~{Math.min((page + 1) * pageSize, total)}</p>
            <div className="flex gap-1">
              <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 disabled:opacity-30 hover:bg-gray-50 transition-colors">이전</button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                const start = Math.max(0, Math.min(page - 2, totalPages - 5));
                const p = start + i;
                if (p >= totalPages) return null;
                return <button key={p} onClick={() => setPage(p)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${p === page ? "bg-adscope-600 text-white" : "border border-gray-200 hover:bg-gray-50"}`}>{p + 1}</button>;
              })}
              <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
                className="px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 disabled:opacity-30 hover:bg-gray-50 transition-colors">다음</button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

// ═══════════════════════════════════════
// Tab 2: 캠페인 효과
// ═══════════════════════════════════════

async function fetchCE(path: string) {
  const { fetchApi } = await import("@/lib/api");
  return fetchApi(path);
}

function CampaignEffectTab() {
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null);
  const [metric, setMetric] = useState<"search" | "news" | "social">("search");

  const { data: campaigns } = useQuery({ queryKey: ["ce-campaigns"], queryFn: () => fetchCE("/campaign-effect/campaigns?limit=30&days=90") });
  const { data: overview } = useQuery({ queryKey: ["ce-overview", selectedCampaignId], queryFn: () => selectedCampaignId ? fetchCE(`/campaign-effect/overview?campaign_id=${selectedCampaignId}`) : null, enabled: !!selectedCampaignId });
  const { data: beforeAfter } = useQuery({ queryKey: ["ce-ba", selectedCampaignId, metric], queryFn: () => selectedCampaignId ? fetchCE(`/campaign-effect/before-after?campaign_id=${selectedCampaignId}&metric=${metric}`) : null, enabled: !!selectedCampaignId });
  const { data: sentShift } = useQuery({ queryKey: ["ce-sentiment", selectedCampaignId], queryFn: () => selectedCampaignId ? fetchCE(`/campaign-effect/sentiment-shift?campaign_id=${selectedCampaignId}`) : null, enabled: !!selectedCampaignId });
  const { data: comparison } = useQuery({ queryKey: ["ce-comparison", overview?.advertiser_id], queryFn: () => overview?.advertiser_id ? fetchCE(`/campaign-effect/comparison?advertiser_id=${overview.advertiser_id}&limit=10`) : null, enabled: !!overview?.advertiser_id });

  const sentimentChartData = sentShift ? [
    { phase: "캠페인 전", ...sentShift.pre }, { phase: "캠페인 중", ...sentShift.during }, { phase: "캠페인 후", ...sentShift.post },
  ] : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <select value={selectedCampaignId || ""} onChange={(e) => setSelectedCampaignId(e.target.value ? Number(e.target.value) : null)}
          className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 max-w-xs">
          <option value="">캠페인 선택...</option>
          {campaigns?.map((c: any) => <option key={c.id} value={c.id}>{c.campaign_name} ({c.advertiser_name})</option>)}
        </select>
      </div>

      {!selectedCampaignId ? (
        <div className="bg-white rounded-xl p-12 shadow-sm border text-center">
          <p className="text-gray-400">캠페인을 선택하면 효과 분석이 표시됩니다</p>
          {campaigns?.length > 0 && (
            <div className="mt-8 text-left">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">최근 캠페인</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b text-left text-gray-500">
                    <th className="pb-2 font-medium">캠페인</th><th className="pb-2 font-medium">광고주</th>
                    <th className="pb-2 font-medium">채널</th><th className="pb-2 font-medium">기간</th>
                    <th className="pb-2 font-medium text-right">추정 광고비</th>
                  </tr></thead>
                  <tbody>
                    {campaigns.slice(0, 15).map((c: any) => (
                      <tr key={c.id} className="border-b border-gray-50 hover:bg-indigo-50 cursor-pointer" onClick={() => setSelectedCampaignId(c.id)}>
                        <td className="py-2 text-indigo-600 font-medium">{c.campaign_name}</td>
                        <td className="py-2 text-gray-600">{c.advertiser_name}</td>
                        <td className="py-2"><span className="px-2 py-0.5 bg-gray-100 rounded text-xs">{c.channel}</span></td>
                        <td className="py-2 text-gray-500 text-xs">{c.first_seen?.slice(0, 10)} ~ {c.last_seen?.slice(0, 10)}</td>
                        <td className="py-2 text-right">{(c.total_est_spend || 0).toLocaleString()}원</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : overview ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <EffectKpi label="캠페인" value={overview.campaign_name} small />
            <EffectKpi label="검색 리프트" value={formatLift(overview.lift?.query_lift_pct)} color={liftColor(overview.lift?.query_lift_pct)} />
            <EffectKpi label="소셜 리프트" value={formatLift(overview.lift?.social_lift_pct)} color={liftColor(overview.lift?.social_lift_pct)} />
            <EffectKpi label="매출 리프트" value={formatLift(overview.lift?.sales_lift_pct)} color={liftColor(overview.lift?.sales_lift_pct)} />
            <EffectKpi label="추정 광고비" value={`${(overview.total_est_spend || 0).toLocaleString()}원`} />
          </div>

          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">캠페인 전후 비교</h2>
              <div className="flex gap-2">
                {(["search", "news", "social"] as const).map((m) => (
                  <button key={m} onClick={() => setMetric(m)}
                    className={`px-3 py-1 text-xs rounded-full border transition-colors ${metric === m ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"}`}>
                    {m === "search" ? "검색량" : m === "news" ? "뉴스" : "소셜"}
                  </button>
                ))}
              </div>
            </div>
            {beforeAfter?.series?.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={beforeAfter.series}>
                  <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="date" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip />
                  {beforeAfter.campaign_start && <ReferenceLine x={beforeAfter.campaign_start.slice(0, 10)} stroke="#6366f1" strokeDasharray="5 5" label={{ value: "시작", fill: "#6366f1", fontSize: 10 }} />}
                  {beforeAfter.campaign_end && <ReferenceLine x={beforeAfter.campaign_end.slice(0, 10)} stroke="#ef4444" strokeDasharray="5 5" label={{ value: "종료", fill: "#ef4444", fontSize: 10 }} />}
                  <Area type="monotone" dataKey="value" stroke="#6366f1" fill="#6366f1" fillOpacity={0.1} strokeWidth={2} name={metric === "search" ? "검색량" : metric === "news" ? "뉴스 건수" : "소셜 점수"} />
                </AreaChart>
              </ResponsiveContainer>
            ) : <p className="text-sm text-gray-400 text-center py-12">데이터가 없습니다</p>}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {sentimentChartData.length > 0 && (
              <div className="bg-white rounded-xl p-6 shadow-sm border">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">캠페인 전후 감성 변화</h2>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={sentimentChartData}>
                    <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="phase" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Legend />
                    <Bar dataKey="positive" stackId="s" fill="#10b981" name="긍정" />
                    <Bar dataKey="neutral" stackId="s" fill="#9ca3af" name="중립" />
                    <Bar dataKey="negative" stackId="s" fill="#ef4444" name="부정" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">캠페인 정보</h2>
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between"><dt className="text-gray-500">광고주</dt><dd><Link href={`/advertisers/${overview.advertiser_id}`} className="text-indigo-600 hover:underline">{overview.advertiser_name}</Link></dd></div>
                <div className="flex justify-between"><dt className="text-gray-500">채널</dt><dd>{overview.channel}</dd></div>
                <div className="flex justify-between"><dt className="text-gray-500">목표</dt><dd>{overview.objective || "-"}</dd></div>
                <div className="flex justify-between"><dt className="text-gray-500">기간</dt><dd className="text-xs">{overview.first_seen?.slice(0, 10)} ~ {overview.last_seen?.slice(0, 10)}</dd></div>
                <div className="flex justify-between"><dt className="text-gray-500">상태</dt><dd><span className={`px-2 py-0.5 rounded text-xs font-medium ${overview.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"}`}>{overview.status === "active" ? "진행중" : "완료"}</span></dd></div>
              </dl>
            </div>
          </div>

          {comparison && comparison.length > 1 && (
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">{overview.advertiser_name} 캠페인 비교</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead><tr className="border-b text-left text-gray-500">
                    <th className="pb-3 font-medium">캠페인</th><th className="pb-3 font-medium">채널</th><th className="pb-3 font-medium">기간</th>
                    <th className="pb-3 font-medium text-right">광고비</th><th className="pb-3 font-medium text-right">검색 리프트</th>
                    <th className="pb-3 font-medium text-right">소셜 리프트</th><th className="pb-3 font-medium text-right">매출 리프트</th>
                  </tr></thead>
                  <tbody>
                    {comparison.map((c: any) => (
                      <tr key={c.campaign_id} className={`border-b border-gray-50 hover:bg-gray-50 cursor-pointer ${c.campaign_id === selectedCampaignId ? "bg-indigo-50" : ""}`}
                        onClick={() => setSelectedCampaignId(c.campaign_id)}>
                        <td className="py-3 font-medium text-gray-900">{c.campaign_name}</td>
                        <td className="py-3"><span className="px-2 py-0.5 bg-gray-100 rounded text-xs">{c.channel}</span></td>
                        <td className="py-3 text-xs text-gray-500">{c.first_seen?.slice(0, 10)} ~ {c.last_seen?.slice(0, 10)}</td>
                        <td className="py-3 text-right">{(c.total_est_spend || 0).toLocaleString()}원</td>
                        <td className={`py-3 text-right font-medium ${liftColor(c.query_lift_pct)}`}>{formatLift(c.query_lift_pct)}</td>
                        <td className={`py-3 text-right font-medium ${liftColor(c.social_lift_pct)}`}>{formatLift(c.social_lift_pct)}</td>
                        <td className={`py-3 text-right font-medium ${liftColor(c.sales_lift_pct)}`}>{formatLift(c.sales_lift_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

function EffectKpi({ label, value, color, small }: { label: string; value: string; color?: string; small?: boolean }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`${small ? "text-sm" : "text-2xl"} font-bold mt-1 ${color || "text-gray-900"} truncate`}>{value}</p>
    </div>
  );
}

function formatLift(v: number | null | undefined): string {
  if (v == null) return "-";
  return `${v > 0 ? "+" : ""}${v}%`;
}
function liftColor(v: number | null | undefined): string {
  if (v == null) return "text-gray-400";
  return v > 0 ? "text-green-600" : v < 0 ? "text-red-600" : "text-gray-600";
}

// ═══════════════════════════════════════
// Tab 3: 소셜 임팩트
// ═══════════════════════════════════════

interface TopImpactItem {
  advertiser_id: number; advertiser_name: string; composite_score: number;
  news_impact_score: number; social_posting_score: number; search_lift_score: number;
  impact_phase: string | null; news_article_count: number; date: string | null;
}

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  pre: { label: "캠페인 전", color: "bg-gray-100 text-gray-700" },
  during: { label: "캠페인 중", color: "bg-blue-100 text-blue-700" },
  post: { label: "캠페인 후", color: "bg-green-100 text-green-700" },
  none: { label: "-", color: "bg-gray-50 text-gray-400" },
};

function SocialImpactTab() {
  const [topItems, setTopItems] = useState<TopImpactItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const data = await api.get("/api/social-impact/top-impact?limit=30"); setTopItems(data); }
    catch (e) { console.error("Failed to load social impact:", e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center min-h-[400px]"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>;

  return (
    <div className="bg-white rounded-xl border shadow-sm">
      <div className="p-5 border-b"><h2 className="text-lg font-semibold">브랜드 임팩트 랭킹 TOP 30</h2></div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50"><tr>
            <th className="px-4 py-3 text-left font-medium text-gray-500">#</th>
            <th className="px-4 py-3 text-left font-medium text-gray-500">광고주</th>
            <th className="px-4 py-3 text-center font-medium text-gray-500">종합 점수</th>
            <th className="px-4 py-3 text-center font-medium text-gray-500">뉴스 임팩트</th>
            <th className="px-4 py-3 text-center font-medium text-gray-500">소셜 포스팅</th>
            <th className="px-4 py-3 text-center font-medium text-gray-500">검색 상승</th>
            <th className="px-4 py-3 text-center font-medium text-gray-500">뉴스 건수</th>
            <th className="px-4 py-3 text-center font-medium text-gray-500">캠페인 상태</th>
          </tr></thead>
          <tbody className="divide-y">
            {topItems.map((item, idx) => {
              const phase = PHASE_LABELS[item.impact_phase || "none"] || PHASE_LABELS.none;
              return (
                <tr key={item.advertiser_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-400">{idx + 1}</td>
                  <td className="px-4 py-3"><Link href={`/advertisers/${item.advertiser_id}`} className="text-blue-600 hover:underline font-medium">{item.advertiser_name}</Link></td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex items-center justify-center gap-2">
                      <div className="w-16 bg-gray-200 rounded-full h-2"><div className="bg-blue-500 h-2 rounded-full" style={{ width: `${item.composite_score}%` }} /></div>
                      <span className="font-semibold">{item.composite_score.toFixed(1)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center text-gray-700">{item.news_impact_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-center text-gray-700">{item.social_posting_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-center text-gray-700">{item.search_lift_score.toFixed(1)}</td>
                  <td className="px-4 py-3 text-center text-gray-700">{item.news_article_count}</td>
                  <td className="px-4 py-3 text-center"><span className={`px-2 py-1 rounded text-xs ${phase.color}`}>{phase.label}</span></td>
                </tr>
              );
            })}
            {topItems.length === 0 && <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">소셜 임팩트 데이터가 아직 없습니다.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════
// Tab 4: 메타시그널
// ═══════════════════════════════════════

interface TopActiveItem {
  advertiser_id: number; advertiser_name: string; composite_score: number;
  spend_multiplier: number; smartstore_score: number; traffic_score: number;
  activity_score: number; activity_state: string | null; date: string | null;
}

const STATE_LABELS: Record<string, { label: string; color: string }> = {
  test: { label: "테스트", color: "bg-gray-100 text-gray-700" },
  scale: { label: "스케일업", color: "bg-blue-100 text-blue-700" },
  push: { label: "푸시", color: "bg-orange-100 text-orange-700" },
  peak: { label: "피크", color: "bg-red-100 text-red-700" },
  cooldown: { label: "쿨다운", color: "bg-green-100 text-green-700" },
};

function MetaSignalTab() {
  const [topItems, setTopItems] = useState<TopActiveItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try { const data = await api.get("/api/meta-signals/top-active?limit=30"); setTopItems(data); }
    catch (e) { console.error("Failed to load meta signals:", e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center min-h-[400px]"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "스마트스토어", desc: "리뷰/매출/재고 변화", color: "border-green-200 bg-green-50" },
          { label: "트래픽 시그널", desc: "네이버/구글 검색량", color: "border-blue-200 bg-blue-50" },
          { label: "활동 점수", desc: "크리에이티브/캠페인 활동량", color: "border-orange-200 bg-orange-50" },
          { label: "광고비 배율", desc: "0.7x~1.5x 보정 계수", color: "border-purple-200 bg-purple-50" },
        ].map((card) => (
          <div key={card.label} className={`rounded-lg border p-4 ${card.color}`}>
            <div className="text-sm font-semibold">{card.label}</div>
            <div className="text-xs text-gray-500 mt-0.5">{card.desc}</div>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border shadow-sm">
        <div className="p-5 border-b"><h2 className="text-lg font-semibold">광고 활동 랭킹 TOP 30</h2></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50"><tr>
              <th className="px-4 py-3 text-left font-medium text-gray-500">#</th>
              <th className="px-4 py-3 text-left font-medium text-gray-500">광고주</th>
              <th className="px-4 py-3 text-center font-medium text-gray-500">종합 점수</th>
              <th className="px-4 py-3 text-center font-medium text-gray-500">스마트스토어</th>
              <th className="px-4 py-3 text-center font-medium text-gray-500">트래픽</th>
              <th className="px-4 py-3 text-center font-medium text-gray-500">활동 점수</th>
              <th className="px-4 py-3 text-center font-medium text-gray-500">광고비 배율</th>
              <th className="px-4 py-3 text-center font-medium text-gray-500">활동 상태</th>
            </tr></thead>
            <tbody className="divide-y">
              {topItems.map((item, idx) => {
                const state = STATE_LABELS[item.activity_state || ""] || { label: "-", color: "bg-gray-50 text-gray-400" };
                return (
                  <tr key={item.advertiser_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-400">{idx + 1}</td>
                    <td className="px-4 py-3"><Link href={`/advertisers/${item.advertiser_id}`} className="text-blue-600 hover:underline font-medium">{item.advertiser_name}</Link></td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-16 bg-gray-200 rounded-full h-2"><div className="bg-blue-500 h-2 rounded-full" style={{ width: `${item.composite_score ?? 0}%` }} /></div>
                        <span className="font-semibold">{(item.composite_score ?? 0).toFixed(1)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">{(item.smartstore_score ?? 0).toFixed(1)}</td>
                    <td className="px-4 py-3 text-center">{(item.traffic_score ?? 0).toFixed(1)}</td>
                    <td className="px-4 py-3 text-center">{(item.activity_score ?? 0).toFixed(1)}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`font-semibold ${(item.spend_multiplier ?? 0) >= 1.2 ? "text-red-600" : (item.spend_multiplier ?? 0) >= 1.0 ? "text-orange-600" : "text-green-600"}`}>
                        {(item.spend_multiplier ?? 0).toFixed(2)}x
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center"><span className={`px-2 py-1 rounded text-xs ${state.color}`}>{state.label}</span></td>
                  </tr>
                );
              })}
              {topItems.length === 0 && <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">메타시그널 데이터가 아직 없습니다.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
