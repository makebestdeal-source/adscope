"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { fetchApi, api, SmartStoreDashboard, SmartStoreSalesData, SmartStoreSalesEstimation } from "@/lib/api";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from "recharts";


/* ── Types (category tab) ── */
interface ShoppingSummary { total_ads: number; total_advertisers: number; total_spend: number; total_categories: number; days: number; }
interface CategoryItem { category: string; ad_count: number; advertiser_count: number; est_spend: number; growth_pct: number | null; }
interface ChannelDist { channel: string; ad_count: number; }
interface TopAdvertiser { rank: number; advertiser_id: number; name: string; brand_name: string | null; ad_count: number; categories: string[]; channels: string[]; est_spend: number; activity_state: string | null; }
interface PromotionType { type: string; count: number; }
interface ShoppingInsightData { summary: ShoppingSummary; top_categories: CategoryItem[]; channel_distribution: ChannelDist[]; top_advertisers: TopAdvertiser[]; promotion_types: PromotionType[]; }

const CHANNEL_LABELS: Record<string, string> = { naver_search: "네이버 검색", naver_da: "네이버 DA", youtube_ads: "유튜브", google_gdn: "GDN", kakao_da: "카카오", meta: "Meta", naver_shopping: "네이버 쇼핑", tiktok_ads: "TikTok" };
const ACTIVITY_LABELS: Record<string, { label: string; color: string }> = { test: { label: "테스트", color: "bg-gray-100 text-gray-600" }, scale: { label: "확장", color: "bg-blue-100 text-blue-700" }, push: { label: "푸시", color: "bg-orange-100 text-orange-700" }, peak: { label: "피크", color: "bg-red-100 text-red-700" }, cooldown: { label: "쿨다운", color: "bg-green-100 text-green-700" } };
const METHOD_LABELS: Record<string, string> = { stock: "재고 추적", purchase_cnt: "구매수 델타", review: "리뷰 속도", composite: "복합" };

function formatSpend(v: number): string {
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억`;
  if (v >= 10_000) return `${Math.round(v / 10_000).toLocaleString()}만`;
  return `${Math.round(v).toLocaleString()}`;
}

function GrowthBadge({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-xs text-gray-300">--</span>;
  const isUp = pct > 0;
  return <span className={`text-xs font-medium ${isUp ? "text-emerald-600" : "text-red-500"}`}>{isUp ? "+" : ""}{pct}%</span>;
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "text-emerald-600 bg-emerald-50" : pct >= 40 ? "text-amber-600 bg-amber-50" : "text-gray-500 bg-gray-50";
  return <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${color}`}>{pct}%</span>;
}

/* ──────── Main Page ──────── */
export default function ShoppingInsightPage() {
  const [tab, setTab] = useState<"category" | "smartstore">("smartstore");
  const [days, setDays] = useState(30);

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">쇼핑인사이트</h1>
          <p className="text-sm text-gray-500 mt-1">카테고리별 광고 트렌드 + 스마트스토어 매출 추정</p>
        </div>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
          <option value={7}>7일</option>
          <option value={14}>14일</option>
          <option value={30}>30일</option>
          <option value={90}>90일</option>
        </select>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
        {([["category", "카테고리 분석"], ["smartstore", "스마트스토어 매출"]] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === key ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "category" ? <CategoryTab days={days} /> : <SmartStoreTab days={days} />}
    </div>
  );
}

/* ──────── Category Tab (existing) ──────── */
function CategoryTab({ days }: { days: number }) {
  const { data, isLoading } = useQuery<ShoppingInsightData>({
    queryKey: ["shoppingInsight", days],
    queryFn: async () => { return fetchApi(`/products/shopping-insight?days=${days}`); },
  });
  const summary = data?.summary;
  const maxCatAds = data?.top_categories?.[0]?.ad_count || 1;
  const totalChAds = data?.channel_distribution?.reduce((s, c) => s + c.ad_count, 0) || 1;

  return (
    <>
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label: "카테고리", value: summary?.total_categories },
          { label: "광고주", value: summary?.total_advertisers },
          { label: "광고 수", value: summary?.total_ads },
          { label: "추정 광고비", value: summary?.total_spend ? formatSpend(summary.total_spend) + "원" : "-" },
        ].map((kpi) => (
          <div key={kpi.label} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{kpi.label}</p>
            <p className="text-2xl font-bold text-gray-900 tabular-nums">
              {isLoading ? "-" : typeof kpi.value === "number" ? kpi.value.toLocaleString() : kpi.value || "-"}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Categories */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100">
            <h3 className="font-semibold text-gray-900">카테고리별 광고 현황</h3>
          </div>
          <div className="divide-y divide-gray-50">
            {isLoading ? Array.from({ length: 6 }).map((_, i) => <div key={i} className="px-5 py-3"><div className="skeleton h-6 w-full" /></div>) :
              data?.top_categories?.length ? data.top_categories.map((cat) => (
                <div key={cat.category} className="px-5 py-3 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-800">{cat.category}</span>
                      <GrowthBadge pct={cat.growth_pct} />
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>{cat.advertiser_count} 광고주</span>
                      <span className="font-medium text-gray-700 tabular-nums">{cat.ad_count}건</span>
                      {cat.est_spend > 0 && <span className="text-adscope-600 tabular-nums">{formatSpend(cat.est_spend)}원</span>}
                    </div>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-1.5">
                    <div className="bg-adscope-500 h-1.5 rounded-full transition-all" style={{ width: `${(cat.ad_count / maxCatAds) * 100}%` }} />
                  </div>
                </div>
              )) : <div className="px-5 py-8 text-center text-sm text-gray-400">데이터 없음</div>}
          </div>
        </div>

        {/* Channel Distribution */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-100"><h3 className="font-semibold text-gray-900">채널별 분포</h3></div>
          <div className="p-5 space-y-3">
            {isLoading ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-5 w-full" />) :
              data?.channel_distribution?.length ? data.channel_distribution.map((ch) => {
                const pct = Math.round((ch.ad_count / totalChAds) * 100);
                return (
                  <div key={ch.channel}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-medium text-gray-700">{CHANNEL_LABELS[ch.channel] || ch.channel}</span>
                      <span className="text-xs text-gray-500 tabular-nums">{ch.ad_count}건 ({pct}%)</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2">
                      <div className="bg-indigo-500 h-2 rounded-full transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              }) : <p className="text-sm text-gray-400 text-center py-4">데이터 없음</p>}
          </div>
        </div>
      </div>

      {/* Top Advertisers */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900">쇼핑 광고주 랭킹</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left font-medium w-10">#</th>
                <th className="px-4 py-3 text-left font-medium">광고주</th>
                <th className="px-4 py-3 text-left font-medium">카테고리</th>
                <th className="px-4 py-3 text-right font-medium">광고 수</th>
                <th className="px-4 py-3 text-right font-medium">추정 광고비</th>
                <th className="px-4 py-3 text-left font-medium">채널</th>
                <th className="px-4 py-3 text-left font-medium">활동</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {isLoading ? Array.from({ length: 6 }).map((_, i) => <tr key={i}><td colSpan={7} className="px-4 py-3"><div className="skeleton h-5 w-full" /></td></tr>) :
                data?.top_advertisers?.length ? data.top_advertisers.map((adv) => {
                  const act = adv.activity_state ? ACTIVITY_LABELS[adv.activity_state] : null;
                  return (
                    <tr key={adv.advertiser_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-400 tabular-nums">{adv.rank}</td>
                      <td className="px-4 py-3"><span className="font-medium text-gray-900">{adv.name}</span>{adv.brand_name && <span className="text-xs text-gray-400 ml-1">({adv.brand_name})</span>}</td>
                      <td className="px-4 py-3"><div className="flex flex-wrap gap-1">{adv.categories.map((c) => <span key={c} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-600">{c}</span>)}</div></td>
                      <td className="px-4 py-3 text-right tabular-nums font-medium text-gray-700">{adv.ad_count.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-600">{adv.est_spend > 0 ? `${formatSpend(adv.est_spend)}원` : "-"}</td>
                      <td className="px-4 py-3"><div className="flex flex-wrap gap-1">{adv.channels.map((ch) => <span key={ch} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">{CHANNEL_LABELS[ch] || ch}</span>)}</div></td>
                      <td className="px-4 py-3">{act ? <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${act.color}`}>{act.label}</span> : <span className="text-xs text-gray-300">--</span>}</td>
                    </tr>
                  );
                }) : <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-gray-400">데이터 없음</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

/* ──────── SmartStore Tab ──────── */
function SmartStoreTab({ days }: { days: number }) {
  const queryClient = useQueryClient();
  const [newUrl, setNewUrl] = useState("");
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);

  const { data: dashboard, isLoading: dashLoading } = useQuery<SmartStoreDashboard>({
    queryKey: ["smartstore-dashboard", days],
    queryFn: () => api.smartstoreDashboard(days),
  });

  const { data: tracked } = useQuery({
    queryKey: ["smartstore-tracked"],
    queryFn: () => api.smartstoreTracked(),
  });

  const { data: salesData, isLoading: salesLoading } = useQuery<SmartStoreSalesData>({
    queryKey: ["smartstore-sales", selectedUrl, days],
    queryFn: () => api.smartstoreSales(selectedUrl!, days),
    enabled: !!selectedUrl,
  });

  const trackMutation = useMutation({
    mutationFn: (url: string) => api.smartstoreTrack(url),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["smartstore-tracked"] });
      queryClient.invalidateQueries({ queryKey: ["smartstore-dashboard"] });
      setNewUrl("");
    },
  });

  const untrackMutation = useMutation({
    mutationFn: (id: number) => api.smartstoreUntrack(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["smartstore-tracked"] });
      queryClient.invalidateQueries({ queryKey: ["smartstore-dashboard"] });
    },
  });

  const topSellers = dashboard?.top_sellers || [];

  return (
    <>
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {[
          { label: "추적 상품", value: dashboard?.total_tracked ?? "-" },
          { label: "평균 일 판매", value: dashboard?.total_with_data ? Math.round((dashboard.total_daily_sales || 0) / Math.max(1, dashboard.total_with_data)) : "-", suffix: "건" },
          { label: "총 추정 월매출", value: dashboard?.total_monthly_revenue ? formatSpend(dashboard.total_monthly_revenue) + "원" : "-" },
          { label: "알림", value: dashboard?.alerts?.length ?? 0, suffix: "건" },
        ].map((kpi) => (
          <div key={kpi.label} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">{kpi.label}</p>
            <p className="text-2xl font-bold text-gray-900 tabular-nums">
              {dashLoading ? "-" : typeof kpi.value === "number" ? kpi.value.toLocaleString() + (kpi.suffix || "") : kpi.value}
            </p>
          </div>
        ))}
      </div>

      {/* Add Product */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 mb-6">
        <h3 className="font-semibold text-gray-900 mb-3">상품 추적 등록</h3>
        <div className="flex gap-2">
          <input
            type="text"
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            placeholder="https://smartstore.naver.com/store/products/12345"
            className="flex-1 text-sm border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
          />
          <button
            onClick={() => newUrl && trackMutation.mutate(newUrl)}
            disabled={!newUrl || trackMutation.isPending}
            className="px-4 py-2 text-sm font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            {trackMutation.isPending ? "..." : "추적 시작"}
          </button>
        </div>
        {trackMutation.isError && (
          <p className="text-xs text-red-500 mt-2">{(trackMutation.error as Error).message}</p>
        )}
      </div>

      {/* Tracked Products Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6">
        <div className="px-5 py-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900">추적 상품 목록</h3>
          <p className="text-xs text-gray-400 mt-0.5">클릭하여 상세 분석 확인</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wider">
                <th className="px-4 py-3 text-left font-medium">상품명</th>
                <th className="px-4 py-3 text-left font-medium">스토어</th>
                <th className="px-4 py-3 text-right font-medium">가격</th>
                <th className="px-4 py-3 text-right font-medium">추정 일 판매</th>
                <th className="px-4 py-3 text-right font-medium">추정 월매출</th>
                <th className="px-4 py-3 text-center font-medium">신뢰도</th>
                <th className="px-4 py-3 text-center font-medium">방법</th>
                <th className="px-4 py-3 text-center font-medium w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {dashLoading ? Array.from({ length: 3 }).map((_, i) => <tr key={i}><td colSpan={8} className="px-4 py-3"><div className="skeleton h-5 w-full" /></td></tr>) :
                topSellers.length ? topSellers.map((p) => (
                  <tr
                    key={p.product_url}
                    onClick={() => setSelectedUrl(p.product_url)}
                    className={`cursor-pointer transition-colors ${selectedUrl === p.product_url ? "bg-green-50" : "hover:bg-gray-50"}`}
                  >
                    <td className="px-4 py-3 font-medium text-gray-900 max-w-[200px] truncate">{p.product_name || p.product_url.split("/").pop()}</td>
                    <td className="px-4 py-3 text-gray-600">{p.store_name || "-"}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-700">{p.price ? `${p.price.toLocaleString()}원` : "-"}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-medium text-gray-900">{p.estimation.estimated_daily_sales}건</td>
                    <td className="px-4 py-3 text-right tabular-nums text-emerald-600 font-medium">
                      {p.estimation.estimated_monthly_revenue ? formatSpend(p.estimation.estimated_monthly_revenue) + "원" : "-"}
                    </td>
                    <td className="px-4 py-3 text-center"><ConfidenceBadge value={p.estimation.confidence} /></td>
                    <td className="px-4 py-3 text-center">
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                        {METHOD_LABELS[p.estimation.primary_method || ""] || "-"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {tracked?.find((t) => t.product_url === p.product_url) && (
                        <button
                          onClick={(e) => { e.stopPropagation(); const t = tracked.find((t) => t.product_url === p.product_url); if (t) untrackMutation.mutate(t.id); }}
                          className="text-gray-400 hover:text-red-500 transition-colors"
                          title="추적 해제"
                        >
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4"><path d="M6 18L18 6M6 6l12 12" /></svg>
                        </button>
                      )}
                    </td>
                  </tr>
                )) : (
                  <tr><td colSpan={8} className="px-4 py-8 text-center text-sm text-gray-400">
                    추적 중인 상품이 없습니다. 위에서 스마트스토어 URL을 등록해주세요.
                  </td></tr>
                )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Product Detail */}
      {selectedUrl && (
        <ProductDetail url={selectedUrl} data={salesData} isLoading={salesLoading} />
      )}

      {/* Alerts */}
      {dashboard?.alerts && dashboard.alerts.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mt-6">
          <h4 className="text-sm font-semibold text-amber-800 mb-2">알림</h4>
          <div className="space-y-1">
            {dashboard.alerts.map((a, i) => (
              <p key={i} className="text-xs text-amber-700">{a.message}</p>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

/* ──────── Product Detail ──────── */
function ProductDetail({ url, data, isLoading }: { url: string; data?: SmartStoreSalesData; isLoading: boolean }) {
  if (isLoading) return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="animate-pulse space-y-4">
        <div className="h-6 bg-gray-200 rounded w-1/3" />
        <div className="h-64 bg-gray-200 rounded" />
      </div>
    </div>
  );

  if (!data || !data.latest) return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 text-center text-sm text-gray-400">
      데이터가 아직 수집되지 않았습니다. 다음 수집 사이클 (04:00 / 16:00) 후 확인해주세요.
    </div>
  );

  const est = data.estimation;
  const timeline = data.timeline || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-lg font-bold text-gray-900">{data.product_name || "상품"}</h3>
            <p className="text-sm text-gray-500 mt-0.5">{data.store_name} {data.seller_grade && <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-600 ml-2">{data.seller_grade}</span>}</p>
            {data.category_name && <p className="text-xs text-gray-400 mt-1">{data.category_name}</p>}
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500">현재 가격</p>
            <p className="text-xl font-bold text-gray-900 tabular-nums">{data.latest.price ? `${data.latest.price.toLocaleString()}원` : "-"}</p>
            {data.latest.discount_pct ? <p className="text-xs text-red-500">-{data.latest.discount_pct}% 할인</p> : null}
          </div>
        </div>

        {/* Estimation Summary */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-5">
          {Object.entries(est.methods).map(([method, value]) => (
            <div key={method} className={`rounded-lg border p-3 ${method === est.primary_method ? "border-green-300 bg-green-50" : "border-gray-100"}`}>
              <p className="text-[10px] font-medium text-gray-500 uppercase">{METHOD_LABELS[method] || method}</p>
              <p className="text-lg font-bold text-gray-900 tabular-nums mt-0.5">{value}건/일</p>
            </div>
          ))}
          <div className="rounded-lg border border-emerald-300 bg-emerald-50 p-3">
            <p className="text-[10px] font-medium text-emerald-700 uppercase">종합 추정</p>
            <p className="text-lg font-bold text-emerald-800 tabular-nums mt-0.5">{est.estimated_daily_sales}건/일</p>
            <p className="text-xs text-emerald-600 tabular-nums">{formatSpend(est.estimated_monthly_revenue)}원/월</p>
          </div>
        </div>

        {/* Current Metrics */}
        <div className="grid grid-cols-3 lg:grid-cols-6 gap-3 mt-4">
          {[
            { label: "재고", value: data.latest.stock_quantity },
            { label: "누적 구매", value: data.latest.purchase_cnt },
            { label: "리뷰", value: data.latest.review_count },
            { label: "평점", value: data.latest.avg_rating?.toFixed(1) },
            { label: "찜", value: data.latest.wishlist_count },
            { label: "신뢰도", value: `${Math.round(est.confidence * 100)}%` },
          ].map((m) => (
            <div key={m.label} className="text-center">
              <p className="text-[10px] text-gray-500 uppercase">{m.label}</p>
              <p className="text-sm font-bold text-gray-800 tabular-nums mt-0.5">{m.value ?? "-"}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Timeline Chart */}
      {timeline.length > 1 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h4 className="font-semibold text-gray-900 mb-4">판매 추이</h4>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={timeline.map((t) => ({ ...t, date: t.date?.slice(5, 10) }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {timeline.some((t) => t.stock_quantity != null) && (
                <Line type="monotone" dataKey="stock_quantity" name="재고" stroke="#6366f1" dot={false} strokeWidth={2} />
              )}
              {timeline.some((t) => t.purchase_cnt != null) && (
                <Line type="monotone" dataKey="purchase_cnt" name="누적구매" stroke="#10b981" dot={false} strokeWidth={2} />
              )}
              <Line type="monotone" dataKey="review_count" name="리뷰수" stroke="#f59e0b" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Review Delta Chart */}
      {timeline.length > 1 && timeline.some((t) => (t.review_delta ?? 0) > 0) && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h4 className="font-semibold text-gray-900 mb-4">일별 리뷰 증가 / 추정 판매량</h4>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={timeline.map((t) => ({ ...t, date: t.date?.slice(5, 10) }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="review_delta" name="리뷰 증가" fill="#f59e0b" radius={[2, 2, 0, 0]} />
              <Bar dataKey="estimated_daily_sales" name="추정 판매" fill="#10b981" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
