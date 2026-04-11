"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchApi } from "@/lib/api";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";

/* ── Types ── */
interface CategorySummary {
  category: string;
  store_count: number;
  avg_score: number;
  total_gmv: number;
  top_score: number;
  top_store: string | null;
}

interface StoreRanking {
  rank: number;
  store_name: string;
  advertiser_id: number | null;
  composite_score: number;
  product_count: number;
  avg_price: number;
  estimated_daily_sales: number | null;
  estimated_gmv: number | null;
  review_count: number | null;
  review_delta: number | null;
  purchase_cnt: number | null;
  purchase_delta: number | null;
  score_wow_change: number | null;
  rank_wow_change: number | null;
  gmv_wow_change_pct: number | null;
}

interface TrendData {
  date: string;
  total_gmv: number;
  store_count: number;
}

interface TopStoreTrend {
  store_name: string;
  data: { date: string; gmv: number; score: number }[];
}

interface TopMover {
  store_name: string;
  category: string;
  composite_score: number;
  estimated_gmv: number | null;
  gmv_wow_change_pct: number | null;
  rank_in_category: number;
  rank_wow_change: number | null;
}

/* ── Helpers ── */
function formatMoney(v: number | null): string {
  if (!v) return "--";
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억원`;
  if (v >= 10_000) return `${Math.round(v / 10_000).toLocaleString()}만원`;
  return `${v.toLocaleString()}원`;
}

function GrowthIndicator({ pct }: { pct: number | null }) {
  if (pct === null || pct === undefined) return <span className="text-xs text-gray-300">--</span>;
  const isUp = pct > 0;
  return (
    <span className={`text-xs font-medium ${isUp ? "text-emerald-600" : pct < 0 ? "text-red-500" : "text-gray-400"}`}>
      {isUp ? "+" : ""}{pct.toFixed(1)}%
    </span>
  );
}

function RankChange({ change }: { change: number | null }) {
  if (change === null || change === undefined || change === 0) return <span className="text-xs text-gray-300">--</span>;
  const isUp = change > 0;
  return (
    <span className={`text-xs font-semibold ${isUp ? "text-emerald-600" : "text-red-500"}`}>
      {isUp ? "\u25b2" : "\u25bc"}{Math.abs(change)}
    </span>
  );
}

const CHART_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6"];

/* ── Main Page ── */
export default function ShoppingRankingPage() {
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"score" | "gmv" | "reviews" | "products" | "growth">("score");
  const [trendDays, setTrendDays] = useState(30);

  /* Category list */
  const { data: catData, isLoading: catLoading } = useQuery<{ categories: CategorySummary[]; latest_date: string | null }>({
    queryKey: ["shopping-ranking-categories"],
    queryFn: () => fetchApi("/api/shopping-ranking-v2/categories"),
  });

  /* Category detail ranking */
  const { data: rankData, isLoading: rankLoading } = useQuery<{ rankings: StoreRanking[]; total: number; category: string; date: string }>({
    queryKey: ["shopping-ranking-detail", selectedCategory, sortBy],
    queryFn: () => fetchApi(`/api/shopping-ranking-v2/${encodeURIComponent(selectedCategory!)}?sort_by=${sortBy}&limit=50`),
    enabled: !!selectedCategory,
  });

  /* Category trend */
  const { data: trendData } = useQuery<{ category_trend: TrendData[]; top_stores: TopStoreTrend[] }>({
    queryKey: ["shopping-ranking-trend", selectedCategory, trendDays],
    queryFn: () => fetchApi(`/api/shopping-ranking-v2/${encodeURIComponent(selectedCategory!)}/trend?days=${trendDays}`),
    enabled: !!selectedCategory,
  });

  /* Top Movers */
  const { data: moversData } = useQuery<{ risers: TopMover[]; fallers: TopMover[]; date: string }>({
    queryKey: ["shopping-top-movers"],
    queryFn: () => fetchApi("/api/shopping-ranking-v2/top-movers"),
    enabled: !selectedCategory,
  });

  const categories = catData?.categories ?? [];

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg shadow-amber-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
              <path d="M3 3v18h18" />
              <path d="M18 17V9" />
              <path d="M13 17V5" />
              <path d="M8 17v-3" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">카테고리별 스토어 랭킹</h1>
            <p className="text-sm text-gray-500">쇼핑 카테고리별 스토어 판매 활동 랭킹 및 트렌드 분석</p>
          </div>
        </div>
        {catData?.latest_date && (
          <span className="text-xs text-gray-400">기준일: {catData.latest_date}</span>
        )}
      </div>

      {/* Feature Description Banner */}
      <div className="mb-6 bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-xl p-5">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0 mt-0.5">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 text-amber-600">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-amber-900 mb-1">카테고리별 스토어 랭킹이란?</h3>
            <p className="text-xs text-amber-700 leading-relaxed">
              네이버 쇼핑 카테고리별로 스토어의 <strong>판매 활동 점수</strong>, <strong>추정 GMV(거래액)</strong>, <strong>리뷰 증가량</strong> 등을 종합 분석하여 랭킹을 산출합니다.
              카테고리를 선택하면 해당 카테고리 내 상위 스토어 랭킹과 주간 변화 트렌드를 확인할 수 있습니다.
            </p>
          </div>
        </div>
      </div>

      {/* Usage Guide */}
      <div className="mb-6 bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-green-800 mb-2">활용 가이드</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-green-700">
          <div>
            <p className="font-medium mb-1">1. 카테고리 선택</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>상단 카테고리 카드에서 관심 분야 클릭</li>
              <li>총 GMV, 스토어 수, 탑 스토어 한눈에 파악</li>
            </ul>
          </div>
          <div>
            <p className="font-medium mb-1">2. 스토어 랭킹 분석</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>종합점수/GMV/리뷰/성장률 기준 정렬</li>
              <li>주간 순위 변동(WoW)으로 성장 스토어 탐색</li>
            </ul>
          </div>
          <div>
            <p className="font-medium mb-1">3. 트렌드 확인</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>카테고리 전체 GMV 추이 차트 확인</li>
              <li>상위 5개 스토어 시계열 비교</li>
            </ul>
          </div>
        </div>
      </div>

      {selectedCategory ? (
        <>
          {/* Back + Category Title */}
          <div className="flex items-center gap-3 mb-6">
            <button
              onClick={() => setSelectedCategory(null)}
              className="px-3 py-1.5 text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              &larr; 전체 카테고리
            </button>
            <h2 className="text-lg font-bold text-gray-900">{selectedCategory}</h2>
            {rankData?.date && <span className="text-xs text-gray-400 ml-2">({rankData.date})</span>}
          </div>

          {/* Sort + Days */}
          <div className="flex gap-3 mb-4">
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)} className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
              <option value="score">종합점수 순</option>
              <option value="gmv">GMV 순</option>
              <option value="reviews">리뷰 순</option>
              <option value="products">상품수 순</option>
              <option value="growth">성장률 순</option>
            </select>
            <select value={trendDays} onChange={(e) => setTrendDays(Number(e.target.value))} className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
              <option value={7}>7일</option>
              <option value={14}>14일</option>
              <option value={30}>30일</option>
              <option value={90}>90일</option>
            </select>
          </div>

          {/* Trend Chart */}
          {trendData && trendData.category_trend.length > 1 && (
            <div className="bg-white rounded-xl border p-5 shadow-sm mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">카테고리 GMV 추이</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData.category_trend}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v >= 100000000 ? `${(v / 100000000).toFixed(0)}억` : v >= 10000 ? `${(v / 10000).toFixed(0)}만` : v} />
                    <Tooltip formatter={(v: number) => [formatMoney(v), "총 GMV"]} />
                    <Line type="monotone" dataKey="total_gmv" stroke="#f59e0b" strokeWidth={2} dot={false} name="총 GMV" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Top Stores Trend */}
          {trendData && trendData.top_stores.length > 0 && trendData.top_stores[0].data.length > 1 && (
            <div className="bg-white rounded-xl border p-5 shadow-sm mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">TOP 5 스토어 GMV 추이</h3>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} allowDuplicatedCategory={false} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => v >= 100000000 ? `${(v / 100000000).toFixed(0)}억` : v >= 10000 ? `${(v / 10000).toFixed(0)}만` : v} />
                    <Tooltip formatter={(v: number) => [formatMoney(v)]} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    {trendData.top_stores.map((store, i) => (
                      <Line
                        key={store.store_name}
                        data={store.data}
                        type="monotone"
                        dataKey="gmv"
                        name={store.store_name.length > 12 ? store.store_name.slice(0, 12) + "..." : store.store_name}
                        stroke={CHART_COLORS[i % CHART_COLORS.length]}
                        strokeWidth={2}
                        dot={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Rankings Table */}
          <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b">
              <h3 className="text-sm font-semibold text-gray-700">스토어 랭킹 ({rankData?.total ?? 0}개)</h3>
            </div>
            {rankLoading ? (
              <div className="p-12 text-center text-gray-400">로딩 중...</div>
            ) : !rankData?.rankings?.length ? (
              <div className="p-12 text-center text-gray-400">데이터가 없습니다</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-600">
                    <tr>
                      <th className="px-4 py-3 text-center font-medium w-12">#</th>
                      <th className="px-4 py-3 text-left font-medium">스토어</th>
                      <th className="px-4 py-3 text-right font-medium">종합점수</th>
                      <th className="px-4 py-3 text-right font-medium">상품수</th>
                      <th className="px-4 py-3 text-right font-medium">평균가</th>
                      <th className="px-4 py-3 text-right font-medium">추정 GMV</th>
                      <th className="px-4 py-3 text-right font-medium">리뷰 증가</th>
                      <th className="px-4 py-3 text-center font-medium">GMV 변화</th>
                      <th className="px-4 py-3 text-center font-medium">순위 변동</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {rankData.rankings.map((r) => (
                      <tr key={r.store_name} className="hover:bg-gray-50/50">
                        <td className="px-4 py-3 text-center text-gray-400 tabular-nums">{r.rank}</td>
                        <td className="px-4 py-3 font-medium text-gray-900">{r.store_name}</td>
                        <td className="px-4 py-3 text-right tabular-nums font-semibold text-amber-600">{r.composite_score?.toFixed(1)}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-gray-700">{r.product_count}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-gray-600">{r.avg_price ? `${r.avg_price.toLocaleString()}원` : "--"}</td>
                        <td className="px-4 py-3 text-right tabular-nums text-emerald-600 font-medium">{formatMoney(r.estimated_gmv)}</td>
                        <td className="px-4 py-3 text-right">
                          {r.review_delta != null && r.review_delta > 0 ? (
                            <span className="text-emerald-600">+{r.review_delta}</span>
                          ) : (
                            <span className="text-gray-400">{r.review_delta ?? "--"}</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center"><GrowthIndicator pct={r.gmv_wow_change_pct} /></td>
                        <td className="px-4 py-3 text-center"><RankChange change={r.rank_wow_change} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : (
        <>
          {/* Category Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
            {catLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="bg-white rounded-xl border p-5 shadow-sm animate-pulse">
                  <div className="h-5 bg-gray-200 rounded w-2/3 mb-3" />
                  <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />
                  <div className="h-4 bg-gray-200 rounded w-1/3" />
                </div>
              ))
            ) : categories.length === 0 ? (
              <div className="col-span-full text-center py-12 text-gray-400">
                <p className="text-lg mb-2">랭킹 데이터가 없습니다</p>
                <p className="text-sm">쇼핑 데이터 수집 후 표시됩니다</p>
              </div>
            ) : categories.map((cat) => (
              <div
                key={cat.category}
                onClick={() => setSelectedCategory(cat.category)}
                className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md hover:border-amber-300 cursor-pointer transition-all"
              >
                <h3 className="text-base font-bold text-gray-900 mb-3">{cat.category}</h3>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <p className="text-gray-500">스토어 수</p>
                    <p className="text-lg font-bold text-gray-800">{cat.store_count}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">총 GMV</p>
                    <p className="text-lg font-bold text-emerald-600">{formatMoney(cat.total_gmv)}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">평균 점수</p>
                    <p className="font-semibold text-amber-600">{cat.avg_score}</p>
                  </div>
                  <div>
                    <p className="text-gray-500">1위 스토어</p>
                    <p className="font-medium text-gray-700 truncate">{cat.top_store || "--"}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Top Movers */}
          {moversData && (moversData.risers.length > 0 || moversData.fallers.length > 0) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Risers */}
              <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b bg-emerald-50">
                  <h3 className="text-sm font-semibold text-emerald-800">급상승 스토어 (WoW)</h3>
                </div>
                <div className="divide-y divide-gray-100">
                  {moversData.risers.slice(0, 10).map((m, i) => (
                    <div key={i} className="px-5 py-3 flex items-center justify-between hover:bg-gray-50/50">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{m.store_name}</p>
                        <p className="text-xs text-gray-500">{m.category} #{m.rank_in_category}</p>
                      </div>
                      <div className="text-right">
                        <GrowthIndicator pct={m.gmv_wow_change_pct} />
                        {m.rank_wow_change != null && m.rank_wow_change !== 0 && (
                          <span className="text-[10px] text-emerald-500 ml-1">{"\u25b2"}{m.rank_wow_change}</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {moversData.risers.length === 0 && (
                    <div className="px-5 py-6 text-center text-sm text-gray-400">데이터 없음</div>
                  )}
                </div>
              </div>

              {/* Fallers */}
              <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b bg-red-50">
                  <h3 className="text-sm font-semibold text-red-800">급하락 스토어 (WoW)</h3>
                </div>
                <div className="divide-y divide-gray-100">
                  {moversData.fallers.slice(0, 10).map((m, i) => (
                    <div key={i} className="px-5 py-3 flex items-center justify-between hover:bg-gray-50/50">
                      <div>
                        <p className="text-sm font-medium text-gray-900">{m.store_name}</p>
                        <p className="text-xs text-gray-500">{m.category} #{m.rank_in_category}</p>
                      </div>
                      <div className="text-right">
                        <GrowthIndicator pct={m.gmv_wow_change_pct} />
                        {m.rank_wow_change != null && m.rank_wow_change !== 0 && (
                          <span className="text-[10px] text-red-500 ml-1">{"\u25bc"}{Math.abs(m.rank_wow_change)}</span>
                        )}
                      </div>
                    </div>
                  ))}
                  {moversData.fallers.length === 0 && (
                    <div className="px-5 py-6 text-center text-sm text-gray-400">데이터 없음</div>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
