"use client";

import { useQuery } from "@tanstack/react-query";
import { api, SOVData } from "@/lib/api";
import { formatChannel, formatPercent, CHANNEL_COLORS } from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";
import { useState, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, Legend, Cell,
} from "recharts";

const CHANNELS = ["", "naver_search", "naver_da", "google_gdn", "youtube_ads", "youtube_surf", "kakao_da", "meta", "naver_shopping", "tiktok_ads"];
const BAR_COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#f97316", "#ec4899", "#14b8a6", "#a855f7"];

export default function SOVPage() {
  const [days, setDays] = useState(30);
  const [keyword, setKeyword] = useState("");
  const [channel, setChannel] = useState("");
  const [selectedAdvId, setSelectedAdvId] = useState<number | null>(null);

  const { data: sovData, isLoading } = useQuery({
    queryKey: ["sov", keyword, channel, days],
    queryFn: () =>
      api.getSOV({
        keyword: keyword || undefined,
        channel: channel || undefined,
        days,
        limit: 20,
      }),
  });

  const { data: competitive } = useQuery({
    queryKey: ["competitiveSOV", selectedAdvId, days],
    queryFn: () => api.getCompetitiveSOV(selectedAdvId!, days),
    enabled: !!selectedAdvId,
  });

  const competitorIds = useMemo(
    () => competitive?.competitors.map((c) => c.advertiser_id) ?? [],
    [competitive]
  );

  const { data: sovTrend } = useQuery({
    queryKey: ["sovTrend", selectedAdvId, competitorIds, days],
    queryFn: () => api.getSOVTrend(selectedAdvId!, competitorIds.slice(0, 5), days),
    enabled: !!selectedAdvId,
  });

  // SOV 수평 바 차트
  const barData = useMemo(() => {
    if (!sovData) return [];
    return sovData.map((d: SOVData) => ({
      name: d.advertiser_name,
      sov: d.sov_percentage,
      impressions: d.total_impressions,
      id: d.advertiser_id,
    }));
  }, [sovData]);

  // 시계열 데이터 구성
  const trendChartData = useMemo(() => {
    if (!sovTrend) return [];
    const byDate: Record<string, Record<string, number>> = {};
    for (const t of sovTrend) {
      if (!byDate[t.date]) byDate[t.date] = {};
      byDate[t.date][t.advertiser_name] = t.sov_percentage;
    }
    return Object.entries(byDate)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, vals]) => ({ date: date.slice(5), ...vals }));
  }, [sovTrend]);

  const trendNames = useMemo(() => {
    if (!sovTrend) return [];
    return [...new Set(sovTrend.map((t) => t.advertiser_name))];
  }, [sovTrend]);

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">SOV 분석</h1>
        <p className="text-sm text-gray-500 mt-1">
          Share of Voice — 광고주별 광고 점유율 분석
        </p>
      </div>

      {/* 필터 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm flex flex-wrap gap-3 items-center">
        <input
          type="text"
          placeholder="키워드 입력..."
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 w-48 focus:outline-none focus:ring-2 focus:ring-adscope-500/20"
        />
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-adscope-500/20"
        >
          <option value="">전체 채널</option>
          {CHANNELS.filter(Boolean).map((ch) => (
            <option key={ch} value={ch}>{formatChannel(ch)}</option>
          ))}
        </select>
        <PeriodSelector days={days} onDaysChange={setDays} />
      </div>

      {/* Top N SOV 수평 BarChart */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
        <h2 className="text-base font-semibold text-gray-900 mb-5">광고주별 점유율 (SOV)</h2>
        {barData.length > 0 ? (
          <ResponsiveContainer width="100%" height={Math.max(barData.length * 36, 200)}>
            <BarChart data={barData} layout="vertical" margin={{ left: 120, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 12 }} width={120} />
              <Tooltip formatter={(v: number) => `${v}%`} />
              <Bar
                dataKey="sov"
                radius={[0, 4, 4, 0]}
                cursor="pointer"
                onClick={(data) => {
                  if (data?.id) setSelectedAdvId(data.id);
                }}
              >
                {barData.map((entry, i) => (
                  <Cell
                    key={entry.id}
                    fill={entry.id === selectedAdvId ? "#4f46e5" : BAR_COLORS[i % BAR_COLORS.length]}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-gray-400 text-center py-12">
            {isLoading ? "로딩 중..." : "데이터 없음. 키워드를 입력하거나 채널을 선택하세요."}
          </p>
        )}
        {barData.length > 0 && (
          <p className="text-xs text-gray-400 mt-3">광고주 바를 클릭하면 경쟁사 비교를 볼 수 있습니다</p>
        )}
      </div>

      {/* 경쟁사 비교 */}
      {selectedAdvId && competitive && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          {/* 채널별 SOV */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
            <h2 className="text-base font-semibold text-gray-900 mb-4">
              {competitive.target.name} — 채널별 점유율
            </h2>
            {Object.keys(competitive.by_channel).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(competitive.by_channel).map(([ch, advMap]) => (
                  <div key={ch}>
                    <p className="text-xs font-medium text-gray-500 mb-1">{formatChannel(ch)}</p>
                    <div className="space-y-1">
                      {Object.entries(advMap)
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 5)
                        .map(([name, pct]) => (
                          <div key={name} className="flex items-center gap-2">
                            <span className="text-xs text-gray-700 w-24 truncate">{name}</span>
                            <div className="flex-1 bg-gray-100 rounded-full h-2">
                              <div
                                className="h-2 rounded-full"
                                style={{
                                  width: `${Math.min(pct, 100)}%`,
                                  backgroundColor: name === competitive.target.name ? "#4f46e5" : "#94a3b8",
                                }}
                              />
                            </div>
                            <span className="text-xs font-medium tabular-nums w-12 text-right">{pct}%</span>
                          </div>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">채널별 데이터 없음</p>
            )}
          </div>

          {/* 연령대별 SOV */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
            <h2 className="text-base font-semibold text-gray-900 mb-4">
              {competitive.target.name} — 연령대별 점유율
            </h2>
            {Object.keys(competitive.by_age_group).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(competitive.by_age_group).map(([ag, advMap]) => (
                  <div key={ag}>
                    <p className="text-xs font-medium text-gray-500 mb-1">{ag}</p>
                    <div className="space-y-1">
                      {Object.entries(advMap)
                        .sort(([, a], [, b]) => b - a)
                        .slice(0, 5)
                        .map(([name, pct]) => (
                          <div key={name} className="flex items-center gap-2">
                            <span className="text-xs text-gray-700 w-24 truncate">{name}</span>
                            <div className="flex-1 bg-gray-100 rounded-full h-2">
                              <div
                                className="h-2 rounded-full"
                                style={{
                                  width: `${Math.min(pct, 100)}%`,
                                  backgroundColor: name === competitive.target.name ? "#4f46e5" : "#94a3b8",
                                }}
                              />
                            </div>
                            <span className="text-xs font-medium tabular-nums w-12 text-right">{pct}%</span>
                          </div>
                        ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">연령대별 데이터 없음</p>
            )}
          </div>
        </div>
      )}

      {/* SOV 시계열 추이 */}
      {selectedAdvId && trendChartData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-5">SOV 추이</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trendChartData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v: number) => `${v}%`} />
              <Legend />
              {trendNames.map((name, i) => (
                <Line
                  key={name}
                  type="monotone"
                  dataKey={name}
                  stroke={BAR_COLORS[i % BAR_COLORS.length]}
                  strokeWidth={name === competitive?.target.name ? 3 : 1.5}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* SOV 상세 테이블 */}
      {sovData && sovData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-900">상세 데이터</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">순위</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">광고주</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">채널</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">SOV</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">노출</th>
                </tr>
              </thead>
              <tbody>
                {sovData.map((d, i) => (
                  <tr
                    key={`${d.advertiser_id}-${d.channel}`}
                    className={`border-b border-gray-50 hover:bg-gray-50 cursor-pointer ${
                      d.advertiser_id === selectedAdvId ? "bg-adscope-50" : ""
                    }`}
                    onClick={() => setSelectedAdvId(d.advertiser_id)}
                  >
                    <td className="py-3 px-4">
                      <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                        i < 3 ? "bg-adscope-100 text-adscope-700" : "bg-gray-100 text-gray-500"
                      }`}>
                        {i + 1}
                      </span>
                    </td>
                    <td className="py-3 px-4 font-medium">{d.advertiser_name}</td>
                    <td className="py-3 px-4 text-gray-600">{d.channel ? formatChannel(d.channel) : "전체"}</td>
                    <td className="py-3 px-4 text-right tabular-nums font-semibold">{formatPercent(d.sov_percentage)}</td>
                    <td className="py-3 px-4 text-right tabular-nums text-gray-600">{d.total_impressions.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
