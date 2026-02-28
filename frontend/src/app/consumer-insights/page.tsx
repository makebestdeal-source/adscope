"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, PieChart, Pie, Cell,
  ScatterChart, Scatter, ZAxis,
} from "recharts";
import { PeriodSelector } from "@/components/PeriodSelector";
import { fetchApi } from "@/lib/api";


async function fetchAdCopyThemes(days: number, industryId?: number) {
  const params = new URLSearchParams({ days: String(days), limit: "30" });
  if (industryId) params.set("industry_id", String(industryId));
  return fetchApi(`/consumer-insights/ad-copy-themes?${params}`);
}
async function fetchPromotionDist(days: number, industryId?: number) {
  const params = new URLSearchParams({ days: String(days) });
  if (industryId) params.set("industry_id", String(industryId));
  return fetchApi(`/consumer-insights/promotion-distribution?${params}`);
}
async function fetchWinningCreatives(days: number, industryId?: number) {
  const params = new URLSearchParams({ days: String(days), limit: "15" });
  if (industryId) params.set("industry_id", String(industryId));
  return fetchApi(`/consumer-insights/winning-creatives?${params}`);
}
async function fetchKeywordLandscape(industryId?: number) {
  const params = new URLSearchParams();
  if (industryId) params.set("industry_id", String(industryId));
  return fetchApi(`/consumer-insights/keyword-landscape?${params}`);
}
async function fetchCategoryHeatmap(days: number) {
  return fetchApi(`/consumer-insights/category-heatmap?days=${days}`);
}

const PIE_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#f97316", "#84cc16"];

const PROMO_LABELS: Record<string, string> = {
  product_launch: "신제품 출시",
  sale: "할인/세일",
  branding: "브랜드 인지",
  event: "이벤트",
  promotion: "프로모션",
  performance: "퍼포먼스",
  retargeting: "리타겟팅",
};
const OBJ_LABELS: Record<string, string> = {
  brand_awareness: "브랜드 인지",
  traffic: "트래픽",
  engagement: "참여",
  conversion: "전환",
  retention: "리텐션",
};

export default function ConsumerInsightsPage() {
  const [days, setDays] = useState(30);
  const [industryId, setIndustryId] = useState<number | undefined>();

  const { data: themes, isLoading } = useQuery({
    queryKey: ["ci-themes", days, industryId],
    queryFn: () => fetchAdCopyThemes(days, industryId),
  });
  const { data: promoDist } = useQuery({
    queryKey: ["ci-promo", days, industryId],
    queryFn: () => fetchPromotionDist(days, industryId),
  });
  const { data: winCreatives } = useQuery({
    queryKey: ["ci-winning", days, industryId],
    queryFn: () => fetchWinningCreatives(days, industryId),
  });
  const { data: kwLandscape } = useQuery({
    queryKey: ["ci-keywords", industryId],
    queryFn: () => fetchKeywordLandscape(industryId),
  });
  const { data: catHeatmap } = useQuery({
    queryKey: ["ci-category", days],
    queryFn: () => fetchCategoryHeatmap(days),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">소비자 인사이트</h1>
          <p className="text-sm text-gray-500 mt-1">광고 카피 트렌드, 프로모션 유형, 효과적인 메시지를 분석합니다</p>
        </div>
        <PeriodSelector days={days} onDaysChange={setDays} />
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl p-6 shadow-sm border animate-pulse h-80" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Ad Copy Themes */}
            {themes && themes.length > 0 && (
              <div className="bg-white rounded-xl p-6 shadow-sm border">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">광고 카피 빈출 키워드</h2>
                <ResponsiveContainer width="100%" height={350}>
                  <BarChart data={themes.slice(0, 20)} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis dataKey="word" type="category" width={80} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" name="빈도" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Promotion Distribution */}
            {promoDist && (
              <div className="bg-white rounded-xl p-6 shadow-sm border">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">프로모션 유형 분포</h2>
                <div className="grid grid-cols-2 gap-4">
                  {promoDist.promotion_types?.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-2">프로모션 유형</p>
                      <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                          <Pie
                            data={promoDist.promotion_types.map((p: any) => ({
                              ...p,
                              name: PROMO_LABELS[p.type] || p.type,
                            }))}
                            dataKey="count"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            outerRadius={70}
                            label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}
                          >
                            {promoDist.promotion_types.map((_: any, i: number) => (
                              <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                  {promoDist.objectives?.length > 0 && (
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-2">캠페인 목표</p>
                      <ResponsiveContainer width="100%" height={200}>
                        <PieChart>
                          <Pie
                            data={promoDist.objectives.map((o: any) => ({
                              ...o,
                              name: OBJ_LABELS[o.objective] || o.objective,
                            }))}
                            dataKey="count"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            outerRadius={70}
                            label={({ name, percent }: any) => `${name} ${(percent * 100).toFixed(0)}%`}
                          >
                            {promoDist.objectives.map((_: any, i: number) => (
                              <Cell key={i} fill={PIE_COLORS[(i + 3) % PIE_COLORS.length]} />
                            ))}
                          </Pie>
                          <Tooltip />
                        </PieChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Keyword Landscape */}
          {kwLandscape && kwLandscape.length > 0 && (
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">키워드 랜드스케이프</h2>
              <p className="text-xs text-gray-500 mb-3">X: 월간 검색량 | Y: CPC(원) | 크기: 광고 수</p>
              <ResponsiveContainer width="100%" height={350}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="search_vol" name="검색량" type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="cpc" name="CPC" type="number" tick={{ fontSize: 11 }} />
                  <ZAxis dataKey="ad_count" name="광고수" range={[40, 400]} />
                  <Tooltip
                    content={({ payload }: any) => {
                      if (!payload?.length) return null;
                      const d = payload[0]?.payload;
                      return (
                        <div className="bg-white border rounded-lg p-3 shadow-lg text-sm">
                          <p className="font-medium">{d?.keyword}</p>
                          <p>검색량: {d?.search_vol?.toLocaleString()}</p>
                          <p>CPC: {d?.cpc?.toLocaleString()}원</p>
                          <p>광고수: {d?.ad_count}</p>
                        </div>
                      );
                    }}
                  />
                  <Scatter data={kwLandscape} fill="#6366f1" fillOpacity={0.6} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Winning Creatives */}
          {winCreatives && winCreatives.length > 0 && (
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">반복 노출 상위 소재</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="pb-3 font-medium">#</th>
                      <th className="pb-3 font-medium">광고주</th>
                      <th className="pb-3 font-medium">광고 카피</th>
                      <th className="pb-3 font-medium">제품</th>
                      <th className="pb-3 font-medium">채널</th>
                      <th className="pb-3 font-medium text-right">노출 횟수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {winCreatives.map((c: any, i: number) => (
                      <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-3 text-gray-400">{i + 1}</td>
                        <td className="py-3">
                          {c.advertiser_id ? (
                            <Link href={`/advertisers/${c.advertiser_id}`} className="text-indigo-600 hover:underline">
                              {c.advertiser_name}
                            </Link>
                          ) : "-"}
                        </td>
                        <td className="py-3 text-gray-700 max-w-xs truncate">{c.ad_text || "-"}</td>
                        <td className="py-3 text-gray-500">{c.product_name || "-"}</td>
                        <td className="py-3">
                          <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">{c.channel}</span>
                        </td>
                        <td className="py-3 text-right font-semibold text-indigo-600">{c.seen_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Category Heatmap */}
          {catHeatmap && catHeatmap.length > 0 && (
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">산업 x 제품 카테고리 집중도</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="pb-3 font-medium">산업</th>
                      <th className="pb-3 font-medium">카테고리</th>
                      <th className="pb-3 font-medium text-right">광고 수</th>
                      <th className="pb-3 font-medium text-right">광고주 수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {catHeatmap.slice(0, 30).map((r: any, i: number) => (
                      <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2 text-gray-700">{r.industry}</td>
                        <td className="py-2 text-gray-600">{r.category}</td>
                        <td className="py-2 text-right font-medium">{r.ad_count}</td>
                        <td className="py-2 text-right text-gray-500">{r.advertiser_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
