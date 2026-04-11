"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchApi } from "@/lib/api";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Legend } from "recharts";

interface SalesProduct {
  advertiser_id: number;
  advertiser_name: string;
  store_name: string;
  product_name: string;
  product_url: string;
  price: number | null;
  review_count: number | null;
  review_delta: number;
  purchase_cnt: number | null;
  purchase_cnt_delta: number;
  estimated_daily_sales: number | null;
  estimation_method: string | null;
  seller_grade: string | null;
  category_name: string | null;
  captured_at: string;
}

interface SalesSummary {
  total_products: number;
  total_stores: number;
  avg_daily_sales: number;
  total_estimated_revenue: number;
}

interface SalesData {
  summary: SalesSummary;
  products: SalesProduct[];
  top_sellers: SalesProduct[];
}

const METHOD_LABELS: Record<string, string> = { stock: "재고 추적", purchase_cnt: "구매수 델타", review: "리뷰 속도", composite: "복합" };
const GRADE_COLORS: Record<string, string> = { "파워": "text-blue-600 bg-blue-50", "빅파워": "text-violet-600 bg-violet-50", "프리미엄": "text-amber-600 bg-amber-50" };

function formatMoney(v: number | null): string {
  if (!v) return "--";
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억원`;
  if (v >= 10_000) return `${Math.round(v / 10_000).toLocaleString()}만원`;
  return `${v.toLocaleString()}원`;
}

export default function ShoppingSalesPage() {
  const [days, setDays] = useState(30);
  const [sortBy, setSortBy] = useState<"sales" | "revenue" | "reviews">("sales");

  const { data, isLoading } = useQuery<SalesData>({
    queryKey: ["shopping-sales", days],
    queryFn: () => fetchApi(`/api/shopping-keywords/sales-overview?days=${days}`),
  });

  const sortedProducts = [...(data?.products ?? [])].sort((a, b) => {
    if (sortBy === "sales") return (b.estimated_daily_sales ?? 0) - (a.estimated_daily_sales ?? 0);
    if (sortBy === "revenue") return ((b.estimated_daily_sales ?? 0) * (b.price ?? 0)) - ((a.estimated_daily_sales ?? 0) * (a.price ?? 0));
    return (b.review_delta ?? 0) - (a.review_delta ?? 0);
  });

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">판매량 추정</h1>
            <p className="text-sm text-gray-500">스마트스토어 상품별 일 판매량 및 매출 추정</p>
          </div>
        </div>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
          <option value={7}>7일</option>
          <option value={14}>14일</option>
          <option value={30}>30일</option>
          <option value={90}>90일</option>
        </select>
      </div>

      {/* Feature Description Banner */}
      <div className="mb-6 bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-200 rounded-xl p-5">
        <div className="flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0 mt-0.5">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 text-emerald-600">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-emerald-900 mb-1">판매량 추정이란?</h3>
            <p className="text-xs text-emerald-700 leading-relaxed">
              스마트스토어에서 수집한 <strong>재고 변화</strong>, <strong>구매수 델타</strong>, <strong>리뷰 증가 속도</strong> 등의 데이터를 복합적으로 분석하여
              상품별 <strong>일 판매량</strong>과 <strong>추정 매출</strong>을 자동으로 산출합니다. 경쟁사 상품의 실제 판매 규모를 파악하고, 시장 내 인기 상품과 성장 트렌드를 발견할 수 있습니다.
            </p>
          </div>
        </div>
      </div>

      {/* Usage Guide */}
      <div className="mb-6 bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-green-800 mb-2">활용 가이드</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-green-700">
          <div>
            <p className="font-medium mb-1">1. 판매량 추정 방식</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>재고 변화, 구매수 델타, 리뷰 속도 등 복합 추정</li>
              <li>상품별 일 판매량과 추정 매출을 자동 산출</li>
            </ul>
          </div>
          <div>
            <p className="font-medium mb-1">2. TOP 10 차트</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>일 판매량 기준 상위 10개 상품 시각적 비교</li>
              <li>상품명 클릭 시 스마트스토어로 직접 이동</li>
            </ul>
          </div>
          <div>
            <p className="font-medium mb-1">3. 정렬 및 분석</p>
            <ul className="space-y-0.5 list-disc list-inside text-green-600">
              <li>판매량/매출/리뷰 증가 순 정렬로 다양한 관점</li>
              <li>판매자 등급(파워/빅파워/프리미엄) 구분</li>
            </ul>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      {data?.summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: "추적 상품", value: data.summary.total_products, color: "text-emerald-600" },
            { label: "스토어 수", value: data.summary.total_stores, color: "text-blue-600" },
            { label: "평균 일 판매량", value: `${Math.round(data.summary.avg_daily_sales)}개`, color: "text-violet-600" },
            { label: "추정 월매출 합계", value: formatMoney(data.summary.total_estimated_revenue), color: "text-amber-600" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-white rounded-xl border p-4 shadow-sm">
              <p className="text-xs text-gray-500 mb-1">{label}</p>
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Top Sellers Chart */}
      {data?.top_sellers && data.top_sellers.length > 0 && (
        <div className="bg-white rounded-xl border p-5 shadow-sm mb-8">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">일 판매량 TOP 10</h3>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.top_sellers.slice(0, 10)} layout="vertical" margin={{ left: 120 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" />
                <YAxis
                  dataKey="product_name"
                  type="category"
                  tick={{ fontSize: 11 }}
                  width={115}
                  tickFormatter={(v: string) => v.length > 15 ? v.slice(0, 15) + "..." : v}
                />
                <Tooltip formatter={(v: number) => [`${v}개/일`, "추정 판매량"]} />
                <Bar dataKey="estimated_daily_sales" fill="#10b981" radius={[0, 4, 4, 0]} name="일 판매량" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Sort */}
      <div className="flex gap-3 mb-4">
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
          className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white"
        >
          <option value="sales">판매량 순</option>
          <option value="revenue">매출 순</option>
          <option value="reviews">리뷰 증가 순</option>
        </select>
      </div>

      {/* Products Table */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b">
          <h3 className="text-sm font-semibold text-gray-700">상품별 판매량 추정 ({sortedProducts.length}개)</h3>
        </div>
        {isLoading ? (
          <div className="p-12 text-center text-gray-400">로딩 중...</div>
        ) : sortedProducts.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            <p className="text-lg mb-2">수집된 판매 데이터가 없습니다</p>
            <p className="text-sm">스마트스토어 수집이 시작되면 데이터가 표시됩니다</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">상품명</th>
                  <th className="px-4 py-3 text-left font-medium">스토어</th>
                  <th className="px-4 py-3 text-right font-medium">가격</th>
                  <th className="px-4 py-3 text-right font-medium">일 판매량</th>
                  <th className="px-4 py-3 text-right font-medium">일 매출</th>
                  <th className="px-4 py-3 text-right font-medium">리뷰 증가</th>
                  <th className="px-4 py-3 text-right font-medium">구매수 증가</th>
                  <th className="px-4 py-3 text-center font-medium">추정 방법</th>
                  <th className="px-4 py-3 text-center font-medium">판매자 등급</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sortedProducts.slice(0, 50).map((p, i) => (
                  <tr key={i} className="hover:bg-gray-50/50">
                    <td className="px-4 py-3 font-medium text-gray-900 max-w-[200px] truncate">
                      <a href={p.product_url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-600 hover:underline">
                        {p.product_name || "--"}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{p.store_name || "--"}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{p.price ? `${p.price.toLocaleString()}원` : "--"}</td>
                    <td className="px-4 py-3 text-right font-semibold text-emerald-600">
                      {p.estimated_daily_sales !== null ? `${p.estimated_daily_sales}개` : "--"}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">
                      {p.estimated_daily_sales && p.price ? formatMoney(p.estimated_daily_sales * p.price) : "--"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {p.review_delta > 0 ? (
                        <span className="text-emerald-600">+{p.review_delta}</span>
                      ) : (
                        <span className="text-gray-400">{p.review_delta}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {p.purchase_cnt_delta > 0 ? (
                        <span className="text-blue-600">+{p.purchase_cnt_delta}</span>
                      ) : (
                        <span className="text-gray-400">{p.purchase_cnt_delta}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                        {p.estimation_method ? METHOD_LABELS[p.estimation_method] || p.estimation_method : "--"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      {p.seller_grade ? (
                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${GRADE_COLORS[p.seller_grade] || "text-gray-600 bg-gray-50"}`}>
                          {p.seller_grade}
                        </span>
                      ) : "--"}
                    </td>
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
