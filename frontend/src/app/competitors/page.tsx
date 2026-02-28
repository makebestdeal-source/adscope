"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  api,
  CompetitorList,
  CompetitorScore,
  IndustryLandscape,
  IndustryInfo,
  LandscapeAdvertiser,
  AdvertiserSearchResult,
} from "@/lib/api";
import { formatChannel, formatSpend } from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";

const BAR_COLORS = [
  "#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe",
  "#818cf8", "#4f46e5", "#4338ca", "#3730a3", "#312e81",
  "#7c3aed", "#6d28d9", "#5b21b6", "#7e22ce", "#9333ea",
  "#a855f7", "#b47afe", "#c084fc", "#d8b4fe", "#e9d5ff",
];

function AffinityScoreBar({ score }: { score: number }) {
  const color =
    score >= 70 ? "bg-red-500" : score >= 40 ? "bg-yellow-500" : "bg-blue-400";
  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color}`}
          style={{ width: `${Math.min(score, 100)}%` }}
        />
      </div>
      <span className="text-xs font-medium tabular-nums w-10 text-right">
        {score.toFixed(1)}
      </span>
    </div>
  );
}

export default function CompetitorsPage() {
  const [selectedIndustry, setSelectedIndustry] = useState<number | null>(null);
  const [advertiserSearch, setAdvertiserSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedAdvertiserId, setSelectedAdvertiserId] = useState<number | null>(null);
  const [selectedAdvertiserName, setSelectedAdvertiserName] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [days, setDays] = useState(30);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Fetch industries from API
  const { data: industries } = useQuery({
    queryKey: ["industries"],
    queryFn: () => api.getIndustries(),
    staleTime: 10 * 60 * 1000,
  });

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(advertiserSearch), 300);
    return () => clearTimeout(timer);
  }, [advertiserSearch]);

  // Click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Advertiser search
  const { data: searchResults } = useQuery({
    queryKey: ["advertiserSearch", debouncedSearch],
    queryFn: () => api.searchAdvertisers(debouncedSearch),
    enabled: debouncedSearch.length >= 1,
  });

  // Competitor data
  const { data: competitorData, isLoading: competitorLoading } = useQuery({
    queryKey: ["competitors", selectedAdvertiserId, days],
    queryFn: () => api.getCompetitors(selectedAdvertiserId!, days),
    enabled: !!selectedAdvertiserId,
  });

  // Industry landscape
  const { data: landscapeData, isLoading: landscapeLoading } = useQuery({
    queryKey: ["industryLandscape", selectedIndustry, days],
    queryFn: () => api.getIndustryLandscape(selectedIndustry!, days),
    enabled: !!selectedIndustry,
  });

  const handleSelectAdvertiser = (adv: AdvertiserSearchResult) => {
    setSelectedAdvertiserId(adv.id);
    setSelectedAdvertiserName(adv.name);
    setAdvertiserSearch(adv.name);
    setShowDropdown(false);
  };

  // Chart data for competitor affinity
  const chartData =
    competitorData?.competitors.map((c, i) => ({
      name: c.competitor_name.length > 8
        ? c.competitor_name.slice(0, 8) + "..."
        : c.competitor_name,
      fullName: c.competitor_name,
      score: c.affinity_score,
      fill: BAR_COLORS[i % BAR_COLORS.length],
    })) ?? [];

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-rose-500 to-pink-600 flex items-center justify-center shadow-lg shadow-rose-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
            <path d="M16 3h5v5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M8 3H3v5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M12 22v-8.3a4 4 0 00-1.172-2.872L3 3" strokeLinecap="round" strokeLinejoin="round" />
            <path d="m15 9 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">경쟁사 분석</h1>
          <p className="text-sm text-gray-500">
            광고주별 경쟁사 자동 매핑 및 업종 랜드스케이프
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {/* Industry selector */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            업종 선택
          </label>
          <select
            value={selectedIndustry ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              setSelectedIndustry(val ? Number(val) : null);
            }}
            className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500/20 focus:border-adscope-500"
          >
            <option value="">-- 업종 선택 --</option>
            {(industries ?? []).map((ind) => (
              <option key={ind.id} value={ind.id}>
                {ind.name}
              </option>
            ))}
          </select>
        </div>

        {/* Advertiser search */}
        <div
          className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm"
          ref={dropdownRef}
        >
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            광고주 검색
          </label>
          <div className="relative">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              placeholder="광고주명 입력..."
              value={advertiserSearch}
              onChange={(e) => {
                setAdvertiserSearch(e.target.value);
                setShowDropdown(true);
                if (!e.target.value) {
                  setSelectedAdvertiserId(null);
                  setSelectedAdvertiserName("");
                }
              }}
              onFocus={() => debouncedSearch.length >= 1 && setShowDropdown(true)}
              className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500/20 focus:border-adscope-500"
            />
            {showDropdown && searchResults && searchResults.length > 0 && (
              <div className="absolute z-20 left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                {searchResults.map((r: AdvertiserSearchResult) => (
                  <button
                    key={r.id}
                    onClick={() => handleSelectAdvertiser(r)}
                    className="w-full text-left flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 transition-colors"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {r.name}
                      </p>
                      {r.brand_name && (
                        <p className="text-xs text-gray-500 truncate">
                          {r.brand_name}
                        </p>
                      )}
                    </div>
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                      {r.match_type === "exact"
                        ? "정확"
                        : r.match_type === "alias"
                          ? "별칭"
                          : "하위"}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Period selector */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            분석 기간
          </label>
          <PeriodSelector days={days} onDaysChange={setDays} />
        </div>
      </div>

      {/* Competitor Affinity Section */}
      {selectedAdvertiserId && (
        <div className="space-y-6 mb-8">
          {/* Header */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-lg font-bold text-gray-900">
                {selectedAdvertiserName} 경쟁사 매핑
              </h2>
              {competitorData?.industry_name && (
                <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-indigo-100 text-indigo-700">
                  {competitorData.industry_name}
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500">
              키워드 중복, 채널 중복, 포지션, 광고비 유사도, 동시 출현 빈도 기반 친밀도 점수
            </p>
          </div>

          {competitorLoading ? (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 text-sm shadow-sm">
              경쟁사 분석 중...
            </div>
          ) : competitorData && competitorData.competitors.length > 0 ? (
            <>
              {/* Bar Chart */}
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <h3 className="text-sm font-semibold text-gray-700 mb-4">
                  경쟁사 친밀도 점수 (상위 {competitorData.competitors.length}개)
                </h3>
                <ResponsiveContainer width="100%" height={Math.max(250, competitorData.competitors.length * 32)}>
                  <BarChart
                    data={chartData}
                    layout="vertical"
                    margin={{ left: 10, right: 20 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
                    <XAxis
                      type="number"
                      domain={[0, 100]}
                      tick={{ fontSize: 11 }}
                      tickFormatter={(v) => `${v}`}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={90}
                      tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                      formatter={(value: number) => [
                        `${value.toFixed(1)}`,
                        "Affinity Score",
                      ]}
                      labelFormatter={(_, payload) => {
                        const item = payload?.[0]?.payload;
                        return item?.fullName ?? "";
                      }}
                      contentStyle={{
                        borderRadius: 8,
                        border: "1px solid #e5e7eb",
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="score" radius={[0, 4, 4, 0]}>
                      {chartData.map((entry, idx) => (
                        <Cell key={idx} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Detail Table */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-100">
                  <h3 className="text-sm font-semibold text-gray-700">
                    경쟁사 상세
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          경쟁사
                        </th>
                        <th className="text-center py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          친밀도
                        </th>
                        <th className="text-center py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          키워드 중복
                        </th>
                        <th className="text-center py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          채널 중복
                        </th>
                        <th className="text-center py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          광고비 유사
                        </th>
                        <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          동시 출현
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {competitorData.competitors.map((c) => (
                        <tr
                          key={c.competitor_id}
                          className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                        >
                          <td className="py-3 px-4 font-medium text-gray-900">
                            {c.competitor_name}
                          </td>
                          <td className="py-3 px-4">
                            <AffinityScoreBar score={c.affinity_score} />
                          </td>
                          <td className="py-3 px-4 text-center tabular-nums text-gray-700">
                            {c.keyword_overlap.toFixed(1)}%
                          </td>
                          <td className="py-3 px-4 text-center tabular-nums text-gray-700">
                            {c.channel_overlap.toFixed(1)}%
                          </td>
                          <td className="py-3 px-4 text-center tabular-nums text-gray-700">
                            {c.spend_similarity.toFixed(1)}%
                          </td>
                          <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                            {c.co_occurrence_count.toLocaleString()}회
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="w-10 h-10 mx-auto mb-3 text-gray-300"
              >
                <circle cx="9" cy="7" r="3" />
                <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
                <circle cx="17" cy="8" r="2" />
                <path d="M21 21v-1a3 3 0 0 0-2-2.8" />
              </svg>
              <p className="text-sm text-gray-400">
                해당 광고주의 경쟁사 데이터가 없습니다
              </p>
              <p className="text-xs text-gray-300 mt-1">
                광고 수집 데이터가 축적되면 자동으로 매핑됩니다
              </p>
            </div>
          )}
        </div>
      )}

      {/* Industry Landscape Section */}
      {selectedIndustry && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <h2 className="text-lg font-bold text-gray-900">
              {(industries ?? []).find((i) => i.id === selectedIndustry)?.name ?? "업종"} 랜드스케이프
            </h2>
            <p className="text-xs text-gray-500 mt-1">
              업종 내 광고주 SOV, 추정 광고비, 활성 채널 현황
            </p>
          </div>

          {landscapeLoading ? (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 text-sm shadow-sm">
              랜드스케이프 분석 중...
            </div>
          ) : landscapeData && landscapeData.advertiser_count > 0 ? (
            <>
              {/* Summary cards */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    업종 광고주
                  </p>
                  <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                    {landscapeData.advertiser_count}
                  </p>
                </div>
                <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    총 추정 광고비
                  </p>
                  <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                    {landscapeData.total_market_size
                      ? formatSpend(landscapeData.total_market_size)
                      : "-"}
                  </p>
                </div>
                <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    CPC 최소
                  </p>
                  <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                    {landscapeData.industry.avg_cpc_min
                      ? `${landscapeData.industry.avg_cpc_min.toLocaleString()}원`
                      : "-"}
                  </p>
                </div>
                <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    CPC 최대
                  </p>
                  <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                    {landscapeData.industry.avg_cpc_max
                      ? `${landscapeData.industry.avg_cpc_max.toLocaleString()}원`
                      : "-"}
                  </p>
                </div>
              </div>

              {/* Landscape Table */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-5 py-4 border-b border-gray-100">
                  <h3 className="text-sm font-semibold text-gray-700">
                    광고주 현황 (SOV 순)
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          #
                        </th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          광고주
                        </th>
                        <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          SOV
                        </th>
                        <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          추정 광고비
                        </th>
                        <th className="text-center py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          채널 수
                        </th>
                        <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          활성 채널
                        </th>
                        <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                          광고 수
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {landscapeData.advertisers.map(
                        (adv: LandscapeAdvertiser, idx: number) => (
                          <tr
                            key={adv.id}
                            className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                          >
                            <td className="py-3 px-4 text-gray-400 tabular-nums">
                              {idx + 1}
                            </td>
                            <td className="py-3 px-4">
                              <div>
                                <p className="font-medium text-gray-900">
                                  {adv.name}
                                </p>
                                {adv.brand_name && (
                                  <p className="text-xs text-gray-500">
                                    {adv.brand_name}
                                  </p>
                                )}
                              </div>
                            </td>
                            <td className="py-3 px-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                  <div
                                    className="h-full rounded-full bg-indigo-500"
                                    style={{
                                      width: `${Math.min(adv.sov_percentage, 100)}%`,
                                    }}
                                  />
                                </div>
                                <span className="tabular-nums font-medium text-gray-900 w-14 text-right">
                                  {adv.sov_percentage.toFixed(1)}%
                                </span>
                              </div>
                            </td>
                            <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                              {adv.est_ad_spend > 0
                                ? formatSpend(adv.est_ad_spend)
                                : "-"}
                            </td>
                            <td className="py-3 px-4 text-center tabular-nums text-gray-700">
                              {adv.channel_count}
                            </td>
                            <td className="py-3 px-4">
                              <div className="flex flex-wrap gap-1">
                                {adv.channel_mix.map((ch) => (
                                  <span
                                    key={ch}
                                    className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600"
                                  >
                                    {formatChannel(ch)}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                              {adv.ad_count.toLocaleString()}
                            </td>
                          </tr>
                        )
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="w-10 h-10 mx-auto mb-3 text-gray-300"
              >
                <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
                <path d="M22 12A10 10 0 0 0 12 2v10z" />
              </svg>
              <p className="text-sm text-gray-400">
                해당 업종의 광고주 데이터가 없습니다
              </p>
              <p className="text-xs text-gray-300 mt-1">
                업종에 등록된 광고주가 있어야 랜드스케이프가 표시됩니다
              </p>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!selectedAdvertiserId && !selectedIndustry && (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center shadow-sm">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="w-12 h-12 mx-auto mb-4 text-gray-300"
          >
            <circle cx="9" cy="7" r="3" />
            <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            <path d="M21 21v-2a4 4 0 0 0-3-3.87" />
          </svg>
          <h3 className="text-base font-semibold text-gray-600 mb-1">
            경쟁사 분석 시작하기
          </h3>
          <p className="text-sm text-gray-400 max-w-md mx-auto">
            광고주를 검색하면 경쟁사 친밀도 점수를 확인할 수 있고,
            업종을 선택하면 업종 내 광고 랜드스케이프를 볼 수 있습니다.
          </p>
        </div>
      )}
    </div>
  );
}
