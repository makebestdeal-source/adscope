"use client";

import { useState, useEffect, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatChannel } from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";

const BAR_COLORS = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#f97316", "#ec4899", "#14b8a6", "#a855f7",
];

export default function KeywordLandscapePage() {
  return (
    <Suspense fallback={<div className="p-6 lg:p-8 max-w-7xl animate-fade-in"><div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 text-sm shadow-sm">로딩 중...</div></div>}>
      <KeywordLandscapeContent />
    </Suspense>
  );
}

function KeywordLandscapeContent() {
  const searchParams = useSearchParams();
  const initKw = searchParams.get("keyword") || "";

  const [keyword, setKeyword] = useState(initKw);
  const [debouncedKw, setDebouncedKw] = useState(initKw);
  const [days, setDays] = useState(30);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedKw(keyword), 500);
    return () => clearTimeout(t);
  }, [keyword]);

  const { data: landscape, isLoading } = useQuery({
    queryKey: ["keywordLandscape", debouncedKw, days],
    queryFn: () => api.getKeywordLandscape(debouncedKw, days),
    enabled: debouncedKw.length >= 1,
  });

  const chartData = (landscape?.advertisers || []).slice(0, 15).map((a, i) => ({
    name: a.advertiser_name.length > 10 ? a.advertiser_name.slice(0, 10) + "..." : a.advertiser_name,
    fullName: a.advertiser_name,
    sov: a.sov_percentage,
    impressions: a.impression_count,
    id: a.advertiser_id,
    fill: BAR_COLORS[i % BAR_COLORS.length],
  }));

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-600 flex items-center justify-center shadow-lg shadow-blue-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
            <rect x="3" y="3" width="18" height="18" rx="2" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M3 9h18M9 21V9" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">광고 랜드스케이프</h1>
          <p className="text-sm text-gray-500">키워드별 광고주 경쟁 현황 분석</p>
        </div>
      </div>

      {/* 사용법 안내 */}
      {!debouncedKw && (
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-xl text-sm text-blue-800">
          <p className="font-semibold mb-1">사용법</p>
          <ul className="list-disc list-inside space-y-0.5 text-xs text-blue-700">
            <li>키워드를 입력하면 해당 키워드에 광고를 집행 중인 광고주 목록과 SOV(점유율)를 확인할 수 있습니다</li>
            <li>차트로 광고주간 경쟁 현황을 한눈에 비교할 수 있습니다</li>
            <li>광고주를 클릭하면 상세 분석 페이지로 이동합니다</li>
          </ul>
          <p className="text-xs text-blue-600 mt-2">예시: &quot;보험&quot;, &quot;다이어트&quot;, &quot;영어&quot;, &quot;대출&quot; 등 키워드를 검색해보세요</p>
        </div>
      )}

      {/* Controls */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm flex flex-wrap gap-4 items-end">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            키워드 입력
          </label>
          <input
            type="text"
            placeholder="키워드를 입력하세요..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            className="w-full px-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            기간
          </label>
          <PeriodSelector days={days} onDaysChange={setDays} />
        </div>
      </div>

      {/* Loading */}
      {debouncedKw && isLoading && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 text-sm shadow-sm">
          랜드스케이프 분석 중...
        </div>
      )}

      {/* Results */}
      {landscape && landscape.advertisers.length > 0 && (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">검색 키워드</p>
              <p className="text-xl font-bold text-gray-900 mt-1">&ldquo;{debouncedKw}&rdquo;</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">경쟁 광고주</p>
              <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">{landscape.total_advertisers}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">매칭 키워드 수</p>
              <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">{landscape.keyword_ids.length}</p>
            </div>
          </div>

          {/* SOV Chart */}
          {chartData.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
              <h2 className="text-base font-semibold text-gray-900 mb-5">광고주별 점유율 (SOV)</h2>
              <ResponsiveContainer width="100%" height={Math.max(chartData.length * 36, 200)}>
                <BarChart data={chartData} layout="vertical" margin={{ left: 100, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} width={100} />
                  <Tooltip
                    formatter={(v: number) => [`${v}%`, "SOV"]}
                    labelFormatter={(_, payload) => payload?.[0]?.payload?.fullName ?? ""}
                  />
                  <Bar dataKey="sov" radius={[0, 4, 4, 0]}>
                    {chartData.map((entry, idx) => (
                      <Cell key={idx} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Detail Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-base font-semibold text-gray-900">광고주 상세</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">#</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">광고주</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">채널</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">노출수</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">SOV</th>
                    <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">포지션</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">최근 수집</th>
                  </tr>
                </thead>
                <tbody>
                  {landscape.advertisers.map((a, idx) => (
                    <tr key={a.advertiser_id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                      <td className="py-3 px-4 text-gray-400 tabular-nums">{idx + 1}</td>
                      <td className="py-3 px-4">
                        <Link
                          href={`/advertisers/${a.advertiser_id}`}
                          className="font-medium text-blue-600 hover:text-blue-800 hover:underline"
                        >
                          {a.advertiser_name}
                        </Link>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {a.channels.map((ch) => (
                            <span key={ch} className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                              {formatChannel(ch)}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right tabular-nums font-medium text-gray-900">
                        {a.impression_count.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                            <div className="h-full rounded-full bg-blue-500" style={{ width: `${Math.min(a.sov_percentage, 100)}%` }} />
                          </div>
                          <span className="tabular-nums font-medium text-gray-900 w-14 text-right">{a.sov_percentage.toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {Object.entries(a.position_zones)
                            .sort(([, a], [, b]) => b - a)
                            .slice(0, 3)
                            .map(([zone, cnt]) => (
                              <span key={zone} className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-50 text-blue-700">
                                {zone}: {cnt}
                              </span>
                            ))}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right tabular-nums text-gray-500 text-xs">
                        {a.last_seen ?? "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {landscape && landscape.advertisers.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center shadow-sm">
          <h3 className="text-base font-semibold text-gray-600 mb-1">데이터 없음</h3>
          <p className="text-sm text-gray-400">&ldquo;{debouncedKw}&rdquo; 키워드에 대한 광고 데이터가 없습니다.</p>
        </div>
      )}

      {!debouncedKw && (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center shadow-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto mb-4 text-gray-300">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18M9 21V9" />
          </svg>
          <h3 className="text-base font-semibold text-gray-600 mb-1">키워드 광고 랜드스케이프</h3>
          <p className="text-sm text-gray-400 max-w-md mx-auto">
            키워드를 입력하면 해당 키워드에서 경쟁하는 모든 광고주와 점유율을 확인할 수 있습니다.
          </p>
        </div>
      )}
    </div>
  );
}
