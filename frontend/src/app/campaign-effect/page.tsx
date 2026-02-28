"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, BarChart, Bar, Cell,
} from "recharts";
import { fetchApi } from "@/lib/api";

async function fetchCampaigns(advertiserId?: number, days = 90) {
  const params = new URLSearchParams({ days: String(days), limit: "30" });
  if (advertiserId) params.set("advertiser_id", String(advertiserId));
  return fetchApi(`/campaign-effect/campaigns?${params}`);
}
async function fetchOverview(campaignId: number) {
  return fetchApi(`/campaign-effect/overview?campaign_id=${campaignId}`);
}
async function fetchBeforeAfter(campaignId: number, metric: string) {
  return fetchApi(`/campaign-effect/before-after?campaign_id=${campaignId}&metric=${metric}`);
}
async function fetchSentimentShift(campaignId: number) {
  return fetchApi(`/campaign-effect/sentiment-shift?campaign_id=${campaignId}`);
}
async function fetchComparison(advertiserId: number) {
  return fetchApi(`/campaign-effect/comparison?advertiser_id=${advertiserId}&limit=10`);
}

const PHASE_COLORS: Record<string, string> = {
  before: "#94a3b8",
  during: "#6366f1",
  after: "#10b981",
};
const SENTIMENT_COLORS: Record<string, string> = {
  positive: "#10b981",
  neutral: "#94a3b8",
  negative: "#ef4444",
};

function formatKRW(v: number) {
  if (v >= 1e8) return `${(v / 1e8).toFixed(1)}억`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}만`;
  return v.toLocaleString();
}

function LiftBadge({ value, label }: { value: number | null; label: string }) {
  if (value === null || value === undefined) return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 text-center">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className="text-lg text-slate-500">-</p>
    </div>
  );
  const isPositive = value > 0;
  return (
    <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 text-center">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold ${isPositive ? "text-green-400" : value < 0 ? "text-red-400" : "text-slate-300"}`}>
        {isPositive ? "+" : ""}{value.toFixed(1)}%
      </p>
    </div>
  );
}

export default function CampaignEffectPage() {
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null);
  const [metric, setMetric] = useState("search");

  const { data: rawCampaigns } = useQuery({
    queryKey: ["campaign-effect-list"],
    queryFn: () => fetchCampaigns(undefined, 90),
  });
  const campaigns = Array.isArray(rawCampaigns) ? rawCampaigns : [];

  const { data: overview } = useQuery({
    queryKey: ["campaign-effect-overview", selectedCampaignId],
    queryFn: () => fetchOverview(selectedCampaignId!),
    enabled: !!selectedCampaignId,
  });

  const { data: beforeAfter } = useQuery({
    queryKey: ["campaign-effect-ba", selectedCampaignId, metric],
    queryFn: () => fetchBeforeAfter(selectedCampaignId!, metric),
    enabled: !!selectedCampaignId,
  });

  const { data: sentimentShift } = useQuery({
    queryKey: ["campaign-effect-sentiment", selectedCampaignId],
    queryFn: () => fetchSentimentShift(selectedCampaignId!),
    enabled: !!selectedCampaignId,
  });

  const { data: rawComparison } = useQuery({
    queryKey: ["campaign-effect-comparison", overview?.advertiser_id],
    queryFn: () => fetchComparison(overview!.advertiser_id),
    enabled: !!overview?.advertiser_id,
  });
  const comparison = Array.isArray(rawComparison) ? rawComparison : [];

  // Auto-select first campaign
  if (!selectedCampaignId && campaigns.length > 0) {
    setSelectedCampaignId(campaigns[0].id);
  }

  const sentimentData = sentimentShift ? [
    { phase: "캠페인 전", ...sentimentShift.pre },
    { phase: "캠페인 중", ...sentimentShift.during },
    { phase: "캠페인 후", ...sentimentShift.post },
  ] : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">캠페인 효과</h1>
          <p className="text-slate-400 text-sm mt-1">캠페인 전후 리프트 분석 및 효과 비교</p>
        </div>
      </div>

      {/* Campaign Selector */}
      <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
        <label className="block text-sm font-medium text-slate-300 mb-2">캠페인 선택</label>
        <select
          className="w-full bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm"
          value={selectedCampaignId || ""}
          onChange={(e) => setSelectedCampaignId(Number(e.target.value) || null)}
        >
          <option value="">캠페인을 선택하세요</option>
          {campaigns.map((c: any) => (
            <option key={c.id} value={c.id}>
              {c.campaign_name} — {c.advertiser_name} ({c.channel})
            </option>
          ))}
        </select>
      </div>

      {!selectedCampaignId && (
        <div className="text-center py-16 text-slate-400">
          <p className="text-lg mb-2">캠페인을 선택하면 효과 분석 결과를 확인할 수 있습니다</p>
          <p className="text-sm">최근 90일 내 {campaigns.length}개 캠페인 분석 가능</p>
        </div>
      )}

      {overview && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <LiftBadge value={overview.lift?.query_lift_pct ?? null} label="검색 리프트" />
            <LiftBadge value={overview.lift?.social_lift_pct ?? null} label="소셜 리프트" />
            <LiftBadge value={overview.lift?.sales_lift_pct ?? null} label="매출 리프트" />
            <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50 text-center">
              <p className="text-xs text-slate-400 mb-1">추정 광고비</p>
              <p className="text-2xl font-bold text-indigo-400">
                {overview.total_est_spend ? formatKRW(overview.total_est_spend) : "-"}
              </p>
            </div>
          </div>

          {/* Campaign Info */}
          <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700/50">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
              <div>
                <span className="text-slate-400">광고주</span>
                <p className="text-white font-medium mt-0.5">
                  <Link href={`/advertisers/${overview.advertiser_id}`} className="text-indigo-400 hover:underline">
                    {overview.advertiser_name}
                  </Link>
                </p>
              </div>
              <div>
                <span className="text-slate-400">채널</span>
                <p className="text-white font-medium mt-0.5">{overview.channel || overview.channels || "-"}</p>
              </div>
              <div>
                <span className="text-slate-400">목적</span>
                <p className="text-white font-medium mt-0.5">{overview.objective || "-"}</p>
              </div>
              <div>
                <span className="text-slate-400">시작일</span>
                <p className="text-white font-medium mt-0.5">{overview.first_seen?.slice(0, 10) || "-"}</p>
              </div>
              <div>
                <span className="text-slate-400">상태</span>
                <p className={`font-medium mt-0.5 ${overview.status === "active" ? "text-green-400" : "text-slate-300"}`}>
                  {overview.status === "active" ? "진행 중" : "종료"}
                </p>
              </div>
            </div>
          </div>

          {/* Before/After Timeline */}
          <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700/50">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">캠페인 전후 비교</h2>
              <div className="flex gap-2">
                {[
                  { key: "search", label: "검색량" },
                  { key: "news", label: "뉴스" },
                  { key: "social", label: "소셜" },
                ].map((m) => (
                  <button
                    key={m.key}
                    onClick={() => setMetric(m.key)}
                    className={`px-3 py-1 text-xs rounded-full transition-colors ${
                      metric === m.key
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-700 text-slate-300 hover:bg-slate-600"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>
            </div>
            {beforeAfter?.series?.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={beforeAfter.series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis
                    dataKey="date"
                    stroke="#94a3b8"
                    fontSize={11}
                    tickFormatter={(v) => v?.slice(5)}
                  />
                  <YAxis stroke="#94a3b8" fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #475569", borderRadius: 8 }}
                    labelStyle={{ color: "#94a3b8" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#6366f1"
                    strokeWidth={2}
                    dot={(props: any) => {
                      const { cx, cy, payload } = props;
                      const color = PHASE_COLORS[payload.phase] || "#6366f1";
                      return <circle cx={cx} cy={cy} r={3} fill={color} stroke={color} />;
                    }}
                  />
                  {beforeAfter.campaign_start && (
                    <>
                      <Legend
                        payload={[
                          { value: "캠페인 전", color: PHASE_COLORS.before },
                          { value: "캠페인 중", color: PHASE_COLORS.during },
                          { value: "캠페인 후", color: PHASE_COLORS.after },
                        ]}
                      />
                    </>
                  )}
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center py-12 text-slate-500">데이터가 부족합니다</div>
            )}
          </div>

          {/* Sentiment Shift */}
          <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700/50">
            <h2 className="text-lg font-semibold text-white mb-4">캠페인 전후 감성 변화</h2>
            {sentimentData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={sentimentData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="phase" stroke="#94a3b8" fontSize={12} />
                  <YAxis stroke="#94a3b8" fontSize={11} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #475569", borderRadius: 8 }}
                  />
                  <Legend />
                  <Bar dataKey="positive" name="긍정" fill={SENTIMENT_COLORS.positive} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="neutral" name="중립" fill={SENTIMENT_COLORS.neutral} radius={[4, 4, 0, 0]} />
                  <Bar dataKey="negative" name="부정" fill={SENTIMENT_COLORS.negative} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center py-12 text-slate-500">뉴스 감성 데이터가 부족합니다</div>
            )}
          </div>

          {/* Multi-Campaign Comparison */}
          {comparison.length > 1 && (
            <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700/50">
              <h2 className="text-lg font-semibold text-white mb-4">
                {overview.advertiser_name} 캠페인 효과 비교
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-slate-400 border-b border-slate-700">
                      <th className="text-left py-2 px-3">캠페인</th>
                      <th className="text-left py-2 px-3">채널</th>
                      <th className="text-right py-2 px-3">검색 리프트</th>
                      <th className="text-right py-2 px-3">소셜 리프트</th>
                      <th className="text-right py-2 px-3">매출 리프트</th>
                      <th className="text-right py-2 px-3">추정 광고비</th>
                      <th className="text-right py-2 px-3">신뢰도</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.map((c: any) => (
                      <tr
                        key={c.campaign_id}
                        className={`border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer ${
                          c.campaign_id === selectedCampaignId ? "bg-indigo-900/20" : ""
                        }`}
                        onClick={() => setSelectedCampaignId(c.campaign_id)}
                      >
                        <td className="py-2 px-3 text-white">{c.campaign_name}</td>
                        <td className="py-2 px-3 text-slate-300">{c.channel || c.channels || "-"}</td>
                        <td className={`py-2 px-3 text-right font-medium ${
                          (c.query_lift_pct ?? 0) > 0 ? "text-green-400" : "text-slate-400"
                        }`}>
                          {c.query_lift_pct !== null ? `${c.query_lift_pct > 0 ? "+" : ""}${c.query_lift_pct}%` : "-"}
                        </td>
                        <td className={`py-2 px-3 text-right font-medium ${
                          (c.social_lift_pct ?? 0) > 0 ? "text-green-400" : "text-slate-400"
                        }`}>
                          {c.social_lift_pct !== null ? `${c.social_lift_pct > 0 ? "+" : ""}${c.social_lift_pct}%` : "-"}
                        </td>
                        <td className={`py-2 px-3 text-right font-medium ${
                          (c.sales_lift_pct ?? 0) > 0 ? "text-green-400" : "text-slate-400"
                        }`}>
                          {c.sales_lift_pct !== null ? `${c.sales_lift_pct > 0 ? "+" : ""}${c.sales_lift_pct}%` : "-"}
                        </td>
                        <td className="py-2 px-3 text-right text-slate-300">
                          {c.total_est_spend ? formatKRW(c.total_est_spend) : "-"}
                        </td>
                        <td className="py-2 px-3 text-right text-slate-400">
                          {c.confidence !== null ? `${(c.confidence * 100).toFixed(0)}%` : "-"}
                        </td>
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
