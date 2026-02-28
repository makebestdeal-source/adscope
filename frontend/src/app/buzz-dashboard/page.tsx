"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, BarChart, Bar, Cell,
} from "recharts";
import { PeriodSelector } from "@/components/PeriodSelector";
import { fetchApi } from "@/lib/api";

async function fetchBuzzOverview(days: number) {
  return fetchApi(`/buzz/overview?days=${days}`);
}
async function fetchSentimentMatrix(days: number) {
  return fetchApi(`/buzz/sentiment-matrix?days=${days}`);
}
async function fetchBuzzAlerts(days: number) {
  return fetchApi(`/buzz/alerts?days=${days}`);
}
async function fetchTopBrands(days: number) {
  return fetchApi(`/buzz/top-brands?days=${days}`);
}
async function fetchNewsFeed(days: number, sentiment?: string) {
  const params = new URLSearchParams({ days: String(days), limit: "20" });
  if (sentiment) params.set("sentiment", sentiment);
  return fetchApi(`/buzz/news-feed?${params}`);
}

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "#10b981",
  neutral: "#6b7280",
  negative: "#ef4444",
};
const SENTIMENT_LABELS: Record<string, string> = {
  positive: "긍정",
  neutral: "중립",
  negative: "부정",
};

export default function BuzzDashboardPage() {
  const [days, setDays] = useState(30);
  const [newsSentiment, setNewsSentiment] = useState<string>("");

  const { data: overview, isLoading: loadingOverview } = useQuery({
    queryKey: ["buzz-overview", days],
    queryFn: () => fetchBuzzOverview(days),
  });
  const { data: matrix } = useQuery({
    queryKey: ["buzz-matrix", days],
    queryFn: () => fetchSentimentMatrix(days),
  });
  const { data: alerts } = useQuery({
    queryKey: ["buzz-alerts", days],
    queryFn: () => fetchBuzzAlerts(Math.min(days, 7)),
  });
  const { data: topBrands } = useQuery({
    queryKey: ["buzz-top-brands", days],
    queryFn: () => fetchTopBrands(days),
  });
  const { data: newsFeed } = useQuery({
    queryKey: ["buzz-news", days, newsSentiment],
    queryFn: () => fetchNewsFeed(Math.min(days, 14), newsSentiment || undefined),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">브랜드 버즈</h1>
          <p className="text-sm text-gray-500 mt-1">시장에서 브랜드에 대해 무슨 이야기가 나오고 있는지 한눈에 파악합니다</p>
        </div>
        <PeriodSelector days={days} onDaysChange={setDays} />
      </div>

      {loadingOverview ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl p-6 shadow-sm border animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-20 mb-2" />
              <div className="h-8 bg-gray-200 rounded w-16" />
            </div>
          ))}
        </div>
      ) : overview ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard label="뉴스 언급" value={overview.total_mentions?.toLocaleString()} />
            <KpiCard label="소셜 포스트" value={overview.social_posts?.toLocaleString()} />
            <KpiCard
              label="평균 감성"
              value={overview.avg_sentiment > 0 ? `+${overview.avg_sentiment}` : String(overview.avg_sentiment)}
              color={overview.avg_sentiment > 0 ? "text-green-600" : overview.avg_sentiment < 0 ? "text-red-600" : "text-gray-600"}
            />
            <KpiCard
              label="긍정/부정 비율"
              value={`${overview.positive}/${overview.negative}`}
              sub={`중립 ${overview.neutral}`}
            />
          </div>

          {/* Buzz Volume Timeline */}
          {overview.timeline?.length > 0 && (
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">버즈 볼륨 추이</h2>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={overview.timeline}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="news" stroke="#6366f1" name="뉴스" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="social" stroke="#10b981" name="소셜" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Buzz Alerts */}
          {alerts && alerts.length > 0 && (
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">버즈 알림</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {alerts.slice(0, 6).map((a: any, i: number) => (
                  <div key={i} className={`rounded-lg p-4 border ${a.direction === "up" ? "bg-green-50 border-green-200" : "bg-red-50 border-red-200"}`}>
                    <div className="flex items-center justify-between">
                      <Link href={`/advertisers/${a.advertiser_id}`} className="font-medium text-gray-900 hover:text-indigo-600">
                        {a.advertiser_name}
                      </Link>
                      <span className={`text-sm font-bold ${a.direction === "up" ? "text-green-600" : "text-red-600"}`}>
                        {a.direction === "up" ? "+" : ""}{a.change_pct}%
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{a.latest_score} (이전 {a.prev_score})</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Sentiment Heatmap */}
            {matrix && matrix.length > 0 && (
              <div className="bg-white rounded-xl p-6 shadow-sm border">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">산업별 감성 분포</h2>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={matrix.slice(0, 10)} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis dataKey="industry" type="category" width={100} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="positive" stackId="s" fill="#10b981" name="긍정" />
                    <Bar dataKey="neutral" stackId="s" fill="#9ca3af" name="중립" />
                    <Bar dataKey="negative" stackId="s" fill="#ef4444" name="부정" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Top Industries */}
            {overview.top_industries?.length > 0 && (
              <div className="bg-white rounded-xl p-6 shadow-sm border">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">산업별 언급량</h2>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={overview.top_industries} layout="vertical">
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis type="number" tick={{ fontSize: 11 }} />
                    <YAxis dataKey="name" type="category" width={100} tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" name="언급수" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Top Buzzing Brands Table */}
          {topBrands && topBrands.length > 0 && (
            <div className="bg-white rounded-xl p-6 shadow-sm border">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">버즈 상위 브랜드</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-500">
                      <th className="pb-3 font-medium">#</th>
                      <th className="pb-3 font-medium">브랜드</th>
                      <th className="pb-3 font-medium">산업</th>
                      <th className="pb-3 font-medium text-right">언급수</th>
                      <th className="pb-3 font-medium text-right">감성</th>
                      <th className="pb-3 font-medium text-right">긍정</th>
                      <th className="pb-3 font-medium text-right">부정</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topBrands.map((b: any, i: number) => (
                      <tr key={b.advertiser_id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-3 text-gray-400">{i + 1}</td>
                        <td className="py-3">
                          <Link href={`/advertisers/${b.advertiser_id}`} className="text-indigo-600 hover:underline font-medium">
                            {b.name}
                          </Link>
                        </td>
                        <td className="py-3 text-gray-500">{b.industry || "-"}</td>
                        <td className="py-3 text-right font-medium">{b.mention_count}</td>
                        <td className="py-3 text-right">
                          <span className={b.avg_sentiment > 0 ? "text-green-600" : b.avg_sentiment < 0 ? "text-red-600" : "text-gray-500"}>
                            {b.avg_sentiment > 0 ? "+" : ""}{b.avg_sentiment}
                          </span>
                        </td>
                        <td className="py-3 text-right text-green-600">{b.positive}</td>
                        <td className="py-3 text-right text-red-600">{b.negative}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* News Feed */}
          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">뉴스 피드</h2>
              <div className="flex gap-2">
                {["", "positive", "neutral", "negative"].map((s) => (
                  <button
                    key={s}
                    onClick={() => setNewsSentiment(s)}
                    className={`px-3 py-1 text-xs rounded-full border transition-colors ${
                      newsSentiment === s
                        ? "bg-indigo-600 text-white border-indigo-600"
                        : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
                    }`}
                  >
                    {s ? SENTIMENT_LABELS[s] : "전체"}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {newsFeed?.map((n: any) => (
                <div key={n.id} className="flex items-start gap-3 p-3 rounded-lg hover:bg-gray-50">
                  <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium mt-0.5 ${
                    n.sentiment === "positive" ? "bg-green-100 text-green-700" :
                    n.sentiment === "negative" ? "bg-red-100 text-red-700" :
                    "bg-gray-100 text-gray-600"
                  }`}>
                    {SENTIMENT_LABELS[n.sentiment] || "중립"}
                  </span>
                  <div className="flex-1 min-w-0">
                    <a href={n.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-gray-900 hover:text-indigo-600 line-clamp-1">
                      {n.title}
                    </a>
                    <div className="flex items-center gap-2 mt-1 text-xs text-gray-400">
                      <span>{n.publisher}</span>
                      <span>{n.published_at?.slice(0, 10)}</span>
                      <Link href={`/advertisers/${n.advertiser_id}`} className="text-indigo-500 hover:underline">
                        {n.advertiser_name}
                      </Link>
                      {n.is_pr && <span className="px-1 py-0.5 bg-yellow-100 text-yellow-700 rounded text-[10px]">PR</span>}
                    </div>
                  </div>
                </div>
              ))}
              {(!newsFeed || newsFeed.length === 0) && (
                <p className="text-sm text-gray-400 text-center py-8">뉴스 데이터가 없습니다</p>
              )}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

function KpiCard({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div className="bg-white rounded-xl p-5 shadow-sm border">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${color || "text-gray-900"}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}
