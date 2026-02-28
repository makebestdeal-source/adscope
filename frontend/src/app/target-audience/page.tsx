"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, RadarChart, Radar, PolarGrid,
  PolarAngleAxis, PolarRadiusAxis,
} from "recharts";
import { PeriodSelector } from "@/components/PeriodSelector";
import { fetchApi } from "@/lib/api";


async function fetchChannelPriority(days: number, advertiserId?: number, industryId?: number) {
  const params = new URLSearchParams({ days: String(days) });
  if (advertiserId) params.set("advertiser_id", String(advertiserId));
  if (industryId) params.set("industry_id", String(industryId));
  return fetchApi(`/target-audience/channel-priority?${params}`);
}
async function fetchAudienceOverlap(days: number, industryId?: number) {
  const params = new URLSearchParams({ days: String(days) });
  if (industryId) params.set("industry_id", String(industryId));
  return fetchApi(`/target-audience/audience-overlap?${params}`);
}
async function fetchRecommendation(advertiserId: number, days: number) {
  return fetchApi(`/target-audience/recommendation?advertiser_id=${advertiserId}&days=${days}`);
}
async function searchAdvertisers(q: string) {
  const r = await fetchApi(`/advertisers/search?q=${encodeURIComponent(q)}&limit=10`);
  return r.json();
}

const COMPETITION_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};
const COMPETITION_LABELS: Record<string, string> = {
  high: "높음",
  medium: "보통",
  low: "낮음",
};

export default function TargetAudiencePage() {
  const [days, setDays] = useState(30);
  const [advertiserId, setAdvertiserId] = useState<number | undefined>();
  const [advSearch, setAdvSearch] = useState("");
  const [showSearch, setShowSearch] = useState(false);

  const { data: channelData } = useQuery({
    queryKey: ["ta-channel", days, advertiserId],
    queryFn: () => fetchChannelPriority(days, advertiserId),
  });
  const { data: overlapData } = useQuery({
    queryKey: ["ta-overlap", days],
    queryFn: () => fetchAudienceOverlap(days),
  });
  const { data: recommendation } = useQuery({
    queryKey: ["ta-reco", advertiserId, days],
    queryFn: () => advertiserId ? fetchRecommendation(advertiserId, days) : null,
    enabled: !!advertiserId,
  });
  const { data: searchResults } = useQuery({
    queryKey: ["adv-search", advSearch],
    queryFn: () => searchAdvertisers(advSearch),
    enabled: advSearch.length >= 2,
  });

  // Radar chart data: merge advertiser + industry channels
  const radarData = (() => {
    if (!channelData) return [];
    const channels = new Set<string>();
    channelData.advertiser?.forEach((c: any) => channels.add(c.channel));
    channelData.industry_avg?.forEach((c: any) => channels.add(c.channel));

    const advMap = Object.fromEntries((channelData.advertiser || []).map((c: any) => [c.channel, c.share_pct]));
    const indMap = Object.fromEntries((channelData.industry_avg || []).map((c: any) => [c.channel, c.share_pct]));

    return Array.from(channels).map((ch) => ({
      channel: ch,
      advertiser: advMap[ch] || 0,
      industry: indMap[ch] || 0,
    }));
  })();

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">타겟 오디언스</h1>
          <p className="text-sm text-gray-500 mt-1">누구에게, 어떤 채널에서 광고를 보여줘야 효과적인지 분석합니다</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <input
              type="text"
              placeholder="광고주 검색..."
              value={advSearch}
              onChange={(e) => {
                setAdvSearch(e.target.value);
                setShowSearch(true);
              }}
              onFocus={() => setShowSearch(true)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm w-48 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            {showSearch && searchResults?.items?.length > 0 && (
              <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg max-h-60 overflow-y-auto">
                {searchResults.items.map((a: any) => (
                  <button
                    key={a.id}
                    onClick={() => {
                      setAdvertiserId(a.id);
                      setAdvSearch(a.name);
                      setShowSearch(false);
                    }}
                    className="block w-full text-left px-4 py-2 text-sm hover:bg-indigo-50 text-gray-700"
                  >
                    {a.name}
                  </button>
                ))}
              </div>
            )}
          </div>
          <PeriodSelector days={days} onDaysChange={setDays} />
        </div>
      </div>

      {/* Recommendation Cards */}
      {recommendation?.recommendations?.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {recommendation.recommendations.map((rec: any, i: number) => (
            <div key={i} className={`rounded-xl p-5 border shadow-sm ${
              rec.type === "channel_gap" ? "bg-amber-50 border-amber-200" :
              rec.type === "primary_target" ? "bg-indigo-50 border-indigo-200" :
              "bg-green-50 border-green-200"
            }`}>
              <p className="text-xs font-medium uppercase tracking-wide mb-1 text-gray-500">
                {rec.type === "primary_target" ? "주요 타겟" :
                 rec.type === "primary_channel" ? "주력 채널" : "확대 권장"}
              </p>
              <p className="text-sm font-medium text-gray-900">{rec.message}</p>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Channel Priority Radar */}
        {radarData.length > 0 && (
          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">채널별 비중 비교</h2>
            <ResponsiveContainer width="100%" height={350}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="channel" tick={{ fontSize: 10 }} />
                <PolarRadiusAxis tick={{ fontSize: 10 }} />
                <Radar name="광고주" dataKey="advertiser" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
                <Radar name="업종 평균" dataKey="industry" stroke="#10b981" fill="#10b981" fillOpacity={0.15} />
                <Legend />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Audience Overlap */}
        {overlapData && overlapData.length > 0 && (
          <div className="bg-white rounded-xl p-6 shadow-sm border">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">연령/성별 경쟁 밀도</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={overlapData.map((r: any) => ({
                ...r,
                label: `${r.age_group} ${r.gender === "male" ? "남" : r.gender === "female" ? "여" : r.gender}`,
              }))}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="unique_advertisers" fill="#6366f1" name="광고주 수" radius={[4, 4, 0, 0]} />
                <Bar dataKey="total_ads" fill="#a5b4fc" name="광고 수" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Channel Scorecard Table */}
      {channelData?.industry_avg?.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">채널별 스코어카드</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-3 font-medium">채널</th>
                  <th className="pb-3 font-medium text-right">광고 수</th>
                  <th className="pb-3 font-medium text-right">업종 비중</th>
                  {advertiserId && <th className="pb-3 font-medium text-right">광고주 비중</th>}
                  {advertiserId && <th className="pb-3 font-medium text-right">차이</th>}
                </tr>
              </thead>
              <tbody>
                {channelData.industry_avg.map((ch: any) => {
                  const advCh = channelData.advertiser?.find((a: any) => a.channel === ch.channel);
                  const diff = advCh ? advCh.share_pct - ch.share_pct : null;
                  return (
                    <tr key={ch.channel} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-3 font-medium text-gray-900">{ch.channel}</td>
                      <td className="py-3 text-right">{ch.count}</td>
                      <td className="py-3 text-right">{ch.share_pct}%</td>
                      {advertiserId && <td className="py-3 text-right">{advCh?.share_pct ?? "-"}%</td>}
                      {advertiserId && (
                        <td className={`py-3 text-right font-medium ${
                          diff && diff > 0 ? "text-green-600" : diff && diff < 0 ? "text-red-600" : "text-gray-400"
                        }`}>
                          {diff !== null ? `${diff > 0 ? "+" : ""}${diff.toFixed(1)}%` : "-"}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Persona Distribution Table */}
      {recommendation?.persona_distribution?.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {recommendation.advertiser_name} 페르소나 분포
          </h2>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={recommendation.persona_distribution.map((p: any) => ({
              ...p,
              label: `${p.age_group} ${p.gender === "male" ? "남" : p.gender === "female" ? "여" : p.gender}`,
            }))}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#8b5cf6" name="노출 수" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Audience Overlap Detail Table */}
      {overlapData && overlapData.length > 0 && (
        <div className="bg-white rounded-xl p-6 shadow-sm border">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">경쟁 밀도 상세</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-3 font-medium">연령대</th>
                  <th className="pb-3 font-medium">성별</th>
                  <th className="pb-3 font-medium text-right">광고주 수</th>
                  <th className="pb-3 font-medium text-right">광고 수</th>
                  <th className="pb-3 font-medium">경쟁 수준</th>
                </tr>
              </thead>
              <tbody>
                {overlapData.map((r: any, i: number) => (
                  <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-2">{r.age_group}</td>
                    <td className="py-2">{r.gender === "male" ? "남성" : r.gender === "female" ? "여성" : r.gender}</td>
                    <td className="py-2 text-right font-medium">{r.unique_advertisers}</td>
                    <td className="py-2 text-right">{r.total_ads}</td>
                    <td className="py-2">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${COMPETITION_COLORS[r.competition_level] || ""}`}>
                        {COMPETITION_LABELS[r.competition_level] || r.competition_level}
                      </span>
                    </td>
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
