"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchApi } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

interface KeywordItem {
  id: number;
  keyword: string;
  category: string;
  subcategory: string;
  monthly_search_vol: number | null;
  avg_product_price: number | null;
  competition_level: string | null;
  ad_count: number;
  advertiser_count: number;
  last_crawled_at: string | null;
}

interface KeywordSummary {
  total_keywords: number;
  active_keywords: number;
  categories: number;
  total_ads_collected: number;
}

interface KeywordAnalysis {
  summary: KeywordSummary;
  keywords: KeywordItem[];
  category_stats: { category: string; keyword_count: number; ad_count: number }[];
}

const COMPETITION_COLORS: Record<string, { label: string; color: string }> = {
  high: { label: "높음", color: "text-red-600 bg-red-50" },
  mid: { label: "보통", color: "text-amber-600 bg-amber-50" },
  low: { label: "낮음", color: "text-emerald-600 bg-emerald-50" },
};

const CHART_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#f97316", "#ec4899", "#84cc16", "#14b8a6"];

function formatNumber(v: number | null): string {
  if (v === null || v === undefined) return "--";
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억`;
  if (v >= 10_000) return `${Math.round(v / 10_000).toLocaleString()}만`;
  return v.toLocaleString();
}

export default function ShoppingKeywordPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [sortBy, setSortBy] = useState<"ad_count" | "monthly_search_vol" | "keyword">("ad_count");

  const { data, isLoading } = useQuery<KeywordAnalysis>({
    queryKey: ["shopping-keyword-analysis", selectedCategory],
    queryFn: () => fetchApi(`/api/shopping-keywords/analysis?category=${selectedCategory === "all" ? "" : selectedCategory}`),
  });

  const filteredKeywords = (data?.keywords ?? [])
    .filter((kw) => !searchTerm || kw.keyword.includes(searchTerm) || kw.subcategory?.includes(searchTerm))
    .sort((a, b) => {
      if (sortBy === "keyword") return a.keyword.localeCompare(b.keyword);
      const av = sortBy === "ad_count" ? a.ad_count : (a.monthly_search_vol ?? 0);
      const bv = sortBy === "ad_count" ? b.ad_count : (b.monthly_search_vol ?? 0);
      return bv - av;
    });

  const categories = [...new Set((data?.keywords ?? []).map((k) => k.category))].filter(Boolean).sort();

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
            <path d="M8 11h6" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">키워드 분석</h1>
          <p className="text-sm text-gray-500">쇼핑 키워드별 검색량, 경쟁강도, 광고 현황 분석</p>
        </div>
      </div>

      {/* Feature Description Banner */}
      <div className="mb-6 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl p-5">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center flex-shrink-0 mt-0.5">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 text-blue-600">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-blue-900 mb-1">쇼핑 키워드 분석이란?</h3>
            <p className="text-xs text-blue-700 leading-relaxed">
              네이버 쇼핑에서 수집한 키워드별 <strong>월간 검색량</strong>, <strong>경쟁강도</strong>, <strong>광고 집행 현황</strong>을 종합 분석하는 페이지입니다.
              카테고리별로 어떤 키워드에 광고가 집중되고 있는지, 검색량 대비 경쟁이 낮은 블루오션 키워드는 무엇인지 한눈에 파악할 수 있습니다.
            </p>
          </div>
        </div>
      </div>

      {/* Usage Guide */}
      <div className="mb-6 bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-green-800 mb-2">활용 가이드</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-green-700">
          <div>
            <p className="font-medium mb-1">1. 키워드 탐색</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>카테고리별 쇼핑 키워드의 검색량과 경쟁강도 확인</li>
              <li>키워드별 광고 수, 광고주 수로 시장 포화도 파악</li>
            </ul>
          </div>
          <div>
            <p className="font-medium mb-1">2. 블루오션 발굴</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>검색량 대비 경쟁이 낮은 키워드 발굴</li>
              <li>카테고리별 광고 분포 차트로 시장 트렌드 파악</li>
            </ul>
          </div>
          <div>
            <p className="font-medium mb-1">3. 필터 및 정렬</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>카테고리 필터로 관심 분야만 집중 분석</li>
              <li>검색량/광고수/가나다 순 정렬로 비교</li>
            </ul>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      {data?.summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: "등록 키워드", value: data.summary.total_keywords, color: "text-indigo-600" },
            { label: "활성 키워드", value: data.summary.active_keywords, color: "text-emerald-600" },
            { label: "카테고리", value: data.summary.categories, color: "text-amber-600" },
            { label: "수집 광고", value: formatNumber(data.summary.total_ads_collected), color: "text-violet-600" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-white rounded-xl border p-4 shadow-sm">
              <p className="text-xs text-gray-500 mb-1">{label}</p>
              <p className={`text-2xl font-bold ${color}`}>{typeof value === "number" ? value.toLocaleString() : value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white"
        >
          <option value="all">전체 카테고리</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <input
          type="text"
          placeholder="키워드 검색..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white w-48"
        />
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white"
        >
          <option value="ad_count">광고수 순</option>
          <option value="monthly_search_vol">검색량 순</option>
          <option value="keyword">가나다 순</option>
        </select>
      </div>

      {/* Charts Row */}
      {data?.category_stats && data.category_stats.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Category keyword count */}
          <div className="bg-white rounded-xl border p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">카테고리별 키워드 수</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.category_stats.slice(0, 10)} layout="vertical" margin={{ left: 80 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis dataKey="category" type="category" tick={{ fontSize: 11 }} width={75} />
                  <Tooltip />
                  <Bar dataKey="keyword_count" fill="#6366f1" radius={[0, 4, 4, 0]} name="키워드 수" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Category ad distribution */}
          <div className="bg-white rounded-xl border p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">카테고리별 광고 분포</h3>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={data.category_stats.filter((c) => c.ad_count > 0).slice(0, 8)}
                    dataKey="ad_count"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {data.category_stats.slice(0, 8).map((_, i) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {/* Keyword Table */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b">
          <h3 className="text-sm font-semibold text-gray-700">키워드 목록 ({filteredKeywords.length}개)</h3>
        </div>
        {isLoading ? (
          <div className="p-12 text-center text-gray-400">로딩 중...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">키워드</th>
                  <th className="px-4 py-3 text-left font-medium">카테고리</th>
                  <th className="px-4 py-3 text-left font-medium">서브카테고리</th>
                  <th className="px-4 py-3 text-right font-medium">월간 검색량</th>
                  <th className="px-4 py-3 text-right font-medium">평균 가격</th>
                  <th className="px-4 py-3 text-center font-medium">경쟁강도</th>
                  <th className="px-4 py-3 text-right font-medium">수집 광고</th>
                  <th className="px-4 py-3 text-right font-medium">광고주</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredKeywords.slice(0, 100).map((kw) => (
                  <tr key={kw.id} className="hover:bg-gray-50/50">
                    <td className="px-4 py-3 font-medium text-gray-900">{kw.keyword}</td>
                    <td className="px-4 py-3 text-gray-600">{kw.category}</td>
                    <td className="px-4 py-3 text-gray-500">{kw.subcategory}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{formatNumber(kw.monthly_search_vol)}</td>
                    <td className="px-4 py-3 text-right text-gray-700">
                      {kw.avg_product_price ? `${kw.avg_product_price.toLocaleString()}원` : "--"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {kw.competition_level && COMPETITION_COLORS[kw.competition_level] ? (
                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${COMPETITION_COLORS[kw.competition_level].color}`}>
                          {COMPETITION_COLORS[kw.competition_level].label}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-300">--</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">{kw.ad_count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right text-gray-600">{kw.advertiser_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
