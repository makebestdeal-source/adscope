"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell,
} from "recharts";
import { api, AdvertiserTrendsSummary } from "@/lib/api";
import { formatChannel, CHANNEL_COLORS } from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";

const STATE_COLORS: Record<string, string> = {
  peak: "bg-red-100 text-red-700",
  push: "bg-orange-100 text-orange-700",
  scale: "bg-blue-100 text-blue-700",
  test: "bg-gray-100 text-gray-600",
  cooldown: "bg-slate-100 text-slate-500",
};

const STATE_LABELS: Record<string, string> = {
  peak: "피크",
  push: "푸시",
  scale: "스케일",
  test: "테스트",
  cooldown: "쿨다운",
};

export default function AdvertiserTrendsPage() {
  const [days, setDays] = useState(30);

  const { data, isLoading } = useQuery({
    queryKey: ["advertiser-trends", days],
    queryFn: () => api.getAdvertiserTrends(days),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">광고주 트렌드</h1>
          <p className="text-sm text-gray-500 mt-1">광고주 활동 변화와 시장 동향을 한눈에 확인합니다</p>
        </div>
        <PeriodSelector days={days} onDaysChange={setDays} />
      </div>

      {isLoading ? <LoadingSkeleton /> : data ? <TrendContent data={data} /> : null}
    </div>
  );
}

function TrendContent({ data }: { data: AdvertiserTrendsSummary }) {
  return (
    <>
      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="활성 광고주" value={data.total_active_advertisers.toLocaleString()} accent="border-l-indigo-500" sub="기간 내 캠페인 보유" />
        <KpiCard label="신규 진입" value={`${(data?.new_entrants || []).length}개`} accent="border-l-emerald-500" sub="기간 내 첫 등장" />
        <KpiCard label="이탈" value={`${(data?.exited || []).length}개`} accent="border-l-rose-500" sub="기간 내 활동 중단" />
        <KpiCard label="평균 활동점수" value={`${data.avg_activity_score}`} accent="border-l-violet-500" sub="0~100 스케일" />
      </div>

      {/* Rising / Falling */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TrendTable
          title="급상승 광고주"
          icon="up"
          items={data?.rising || []}
          emptyMsg="활동 증가 광고주가 없습니다"
        />
        <TrendTable
          title="급하강 광고주"
          icon="down"
          items={data?.falling || []}
          emptyMsg="활동 감소 광고주가 없습니다"
        />
      </div>

      {/* New / Exited */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <EntrantList title="신규 진입" items={data?.new_entrants || []} />
        <ExitedList title="이탈 광고주" items={data?.exited || []} />
      </div>

      {/* Channel Mix */}
      {(data?.channel_trends || []).length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">채널 믹스 변화</h2>
          <p className="text-xs text-gray-400 mb-4">전반기 vs 후반기 광고 수 비교</p>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart
              data={(data?.channel_trends || []).map((c) => ({
                ...c,
                name: formatChannel(c.channel),
              }))}
              layout="vertical"
              margin={{ left: 100, right: 40 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis type="number" />
              <YAxis dataKey="name" type="category" width={90} tick={{ fontSize: 12 }} />
              <Tooltip
                formatter={(v: number, name: string) => [v.toLocaleString(), name]}
              />
              <Legend />
              <Bar dataKey="prev_count" name="이전 기간" fill="#94a3b8" radius={[0, 4, 4, 0]} />
              <Bar dataKey="current_count" name="현재 기간" fill="#6366f1" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Industry Summary */}
      {(data?.industry_summary || []).length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">산업별 활동 현황</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">산업</th>
                  <th className="text-right py-3 px-2 text-gray-500 font-medium">활성 광고주</th>
                  <th className="text-right py-3 px-2 text-gray-500 font-medium">평균 활동점수</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium w-40">활동 수준</th>
                </tr>
              </thead>
              <tbody>
                {(data?.industry_summary || []).map((ind) => (
                  <tr key={ind.industry_id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-2 font-medium text-gray-900">{ind.industry_name}</td>
                    <td className="py-3 px-2 text-right text-gray-700">{ind.active_advertisers}</td>
                    <td className="py-3 px-2 text-right font-medium text-gray-900">{ind.avg_activity}</td>
                    <td className="py-3 px-2">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-indigo-500"
                            style={{ width: `${Math.min(ind.avg_activity, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-8 text-right">{ind.avg_activity}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

/* ── Sub Components ── */

function KpiCard({ label, value, accent, sub }: {
  label: string; value: string; accent: string; sub: string;
}) {
  return (
    <div className={`bg-white rounded-xl border border-gray-200 p-5 shadow-sm border-l-4 ${accent}`}>
      <p className="text-xs text-gray-500 font-medium">{label}</p>
      <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
      <p className="text-[11px] text-gray-400 mt-1">{sub}</p>
    </div>
  );
}

function TrendTable({ title, icon, items, emptyMsg }: {
  title: string;
  icon: "up" | "down";
  items: AdvertiserTrendsSummary["rising"];
  emptyMsg: string;
}) {
  const isUp = icon === "up";

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900 mb-1 flex items-center gap-2">
        <span className={`text-lg ${isUp ? "text-emerald-500" : "text-rose-500"}`}>
          {isUp ? "\u25B2" : "\u25BC"}
        </span>
        {title}
      </h2>
      <p className="text-xs text-gray-400 mb-4">활동점수 변화 기준</p>
      {(items || []).length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">{emptyMsg}</p>
      ) : (
        <div className="space-y-2">
          {(items || []).slice(0, 10).map((item, idx) => (
            <Link
              key={item.advertiser_id}
              href={`/advertisers/${item.advertiser_id}`}
              className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                idx < 3
                  ? (isUp ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700")
                  : "bg-gray-100 text-gray-500"
              }`}>
                {idx + 1}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {item.advertiser_name}
                </p>
                {item.brand_name && (
                  <p className="text-[11px] text-gray-400 truncate">{item.brand_name}</p>
                )}
              </div>
              {item.activity_state && (
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                  STATE_COLORS[item.activity_state] || "bg-gray-100 text-gray-500"
                }`}>
                  {STATE_LABELS[item.activity_state] || item.activity_state}
                </span>
              )}
              <div className="text-right">
                <p className={`text-sm font-bold ${isUp ? "text-emerald-600" : "text-rose-600"}`}>
                  {item.delta > 0 ? "+" : ""}{item.delta}
                </p>
                <p className="text-[10px] text-gray-400">
                  {item.prev_score} → {item.current_score}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function EntrantList({ title, items }: {
  title: string;
  items: AdvertiserTrendsSummary["new_entrants"];
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900 mb-1 flex items-center gap-2">
        <span className="text-emerald-500 text-lg">+</span>
        {title}
      </h2>
      <p className="text-xs text-gray-400 mb-4">분석 기간 내 첫 광고 집행</p>
      {(items || []).length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">신규 진입 광고주가 없습니다</p>
      ) : (
        <div className="space-y-2">
          {(items || []).slice(0, 10).map((item) => (
            <Link
              key={item.advertiser_id}
              href={`/advertisers/${item.advertiser_id}`}
              className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-emerald-50 flex items-center justify-center">
                <span className="text-emerald-600 text-xs font-bold">NEW</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {item.advertiser_name || `광고주 #${item.advertiser_id}`}
                </p>
                {item.brand_name && (
                  <p className="text-[11px] text-gray-400 truncate">{item.brand_name}</p>
                )}
              </div>
              <div className="text-right text-xs text-gray-400">
                <p>{item.campaign_count}개 캠페인</p>
                {item.entered_at && (
                  <p>{new Date(item.entered_at).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })}</p>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function ExitedList({ title, items }: {
  title: string;
  items: AdvertiserTrendsSummary["exited"];
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-lg font-semibold text-gray-900 mb-1 flex items-center gap-2">
        <span className="text-rose-500 text-lg">-</span>
        {title}
      </h2>
      <p className="text-xs text-gray-400 mb-4">분석 기간 중 활동 중단</p>
      {(items || []).length === 0 ? (
        <p className="text-sm text-gray-400 py-4 text-center">이탈 광고주가 없습니다</p>
      ) : (
        <div className="space-y-2">
          {(items || []).slice(0, 10).map((item) => (
            <Link
              key={item.advertiser_id}
              href={`/advertisers/${item.advertiser_id}`}
              className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="w-8 h-8 rounded-full bg-rose-50 flex items-center justify-center">
                <span className="text-rose-400 text-xs font-bold">OUT</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {item.advertiser_name || `광고주 #${item.advertiser_id}`}
                </p>
                {item.brand_name && (
                  <p className="text-[11px] text-gray-400 truncate">{item.brand_name}</p>
                )}
              </div>
              <div className="text-right text-xs text-gray-400">
                {item.last_active && (
                  <p>마지막 {new Date(item.last_active).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })}</p>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="h-3 bg-gray-200 rounded w-20 animate-pulse" />
            <div className="h-8 bg-gray-200 rounded w-16 mt-2 animate-pulse" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[1, 2].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
            <div className="h-5 bg-gray-200 rounded w-32 animate-pulse mb-4" />
            {[1, 2, 3, 4, 5].map((j) => (
              <div key={j} className="h-10 bg-gray-100 rounded mb-2 animate-pulse" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
