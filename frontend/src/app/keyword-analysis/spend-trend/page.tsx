"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, AdvertiserSearchResult } from "@/lib/api";
import { formatChannel, formatSpend, CHANNEL_COLORS } from "@/lib/constants";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

export default function SpendTrendPage() {
  const [advertiserSearch, setAdvertiserSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedName, setSelectedName] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [months, setMonths] = useState(6);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(advertiserSearch), 300);
    return () => clearTimeout(t);
  }, [advertiserSearch]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const { data: searchResults } = useQuery({
    queryKey: ["advertiserSearch", debouncedSearch],
    queryFn: () => api.searchAdvertisers(debouncedSearch),
    enabled: debouncedSearch.length >= 1,
  });

  const { data: monthlySpend, isLoading } = useQuery({
    queryKey: ["advertiserMonthlySpend", selectedId, months],
    queryFn: () => api.getAdvertiserMonthlySpend(selectedId!, months),
    enabled: !!selectedId,
  });

  const handleSelect = (adv: AdvertiserSearchResult) => {
    setSelectedId(adv.id);
    setSelectedName(adv.name);
    setAdvertiserSearch(adv.name);
    setShowDropdown(false);
  };

  const allChannels = useMemo(() => {
    if (!monthlySpend?.monthly_data) return [];
    return Array.from(
      new Set(monthlySpend.monthly_data.flatMap((m) => Object.keys(m.by_channel)))
    ).sort();
  }, [monthlySpend]);

  const chartData = useMemo(() => {
    if (!monthlySpend?.monthly_data) return [];
    return monthlySpend.monthly_data.map((m) => ({
      month: m.month,
      ...m.by_channel,
    }));
  }, [monthlySpend]);

  const totalSpend = useMemo(() => {
    if (!monthlySpend?.monthly_data) return 0;
    return monthlySpend.monthly_data.reduce((sum, m) => sum + m.total_spend, 0);
  }, [monthlySpend]);

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
            <path d="M3 3v18h18" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M7 16l4-8 4 4 4-8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">광고비 추이</h1>
          <p className="text-sm text-gray-500">광고주별 월별 채널별 광고비 추이 분석</p>
        </div>
      </div>

      {/* 사용법 안내 */}
      {!selectedId && (
        <div className="mb-6 p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-sm text-emerald-800">
          <p className="font-semibold mb-1">사용법</p>
          <ul className="list-disc list-inside space-y-0.5 text-xs text-emerald-700">
            <li>광고주를 검색하여 선택하면 월별 채널별 추정 광고비 추이가 차트로 표시됩니다</li>
            <li>네이버, 구글, 메타, 카카오 등 채널별 광고비를 비교 분석할 수 있습니다</li>
            <li>최근 3/6/12개월 기간을 선택하여 트렌드를 확인하세요</li>
          </ul>
          <p className="text-xs text-emerald-600 mt-2">예시: &quot;삼성전자&quot;, &quot;쿠팡&quot;, &quot;배달의민족&quot; 등을 검색해보세요</p>
        </div>
      )}

      {/* Controls */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm flex flex-wrap gap-4 items-end">
        <div className="flex-1 min-w-[200px]" ref={dropdownRef}>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            광고주 검색
          </label>
          <div className="relative">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
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
                if (!e.target.value) { setSelectedId(null); setSelectedName(""); }
              }}
              onFocus={() => debouncedSearch.length >= 1 && setShowDropdown(true)}
              className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500"
            />
            {showDropdown && searchResults && searchResults.length > 0 && (
              <div className="absolute z-20 left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
                {searchResults.map((r: AdvertiserSearchResult) => (
                  <button
                    key={r.id}
                    onClick={() => handleSelect(r)}
                    className="w-full text-left flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 transition-colors"
                  >
                    <p className="text-sm font-medium text-gray-900 truncate">{r.name}</p>
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                      {r.match_type === "exact" ? "정확" : r.match_type === "alias" ? "별칭" : "하위"}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
            기간
          </label>
          <div className="flex gap-1">
            {[3, 6, 12].map((m) => (
              <button
                key={m}
                onClick={() => setMonths(m)}
                className={`px-3 py-2 text-xs rounded-lg border transition-colors ${
                  months === m
                    ? "bg-emerald-50 border-emerald-300 text-emerald-700 font-medium"
                    : "border-gray-200 text-gray-500 hover:bg-gray-50"
                }`}
              >
                {m}개월
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Loading */}
      {selectedId && isLoading && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 text-sm shadow-sm">
          광고비 데이터 조회 중...
        </div>
      )}

      {/* Results */}
      {monthlySpend && monthlySpend.monthly_data.length > 0 && (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">광고주</p>
              <p className="text-xl font-bold text-gray-900 mt-1">{selectedName}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">기간 총 추정 광고비</p>
              <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">{formatSpend(totalSpend)}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">활성 채널</p>
              <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">{allChannels.length}</p>
            </div>
          </div>

          {/* Stacked Bar Chart */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
            <h2 className="text-base font-semibold text-gray-900 mb-5">월별 채널별 광고비 추이</h2>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v) => formatSpend(v)} tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(v: number, name: string) => [formatSpend(v), formatChannel(name)]}
                />
                <Legend formatter={(value) => formatChannel(value)} wrapperStyle={{ fontSize: 11 }} />
                {allChannels.map((ch) => (
                  <Bar
                    key={ch}
                    dataKey={ch}
                    stackId="spend"
                    fill={CHANNEL_COLORS[ch] || "#94a3b8"}
                    radius={0}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Monthly Data Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="text-base font-semibold text-gray-900">월별 상세</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">월</th>
                    <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">총 광고비</th>
                    {allChannels.map((ch) => (
                      <th key={ch} className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                        {formatChannel(ch)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {monthlySpend.monthly_data.map((m) => (
                    <tr key={m.month} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                      <td className="py-3 px-4 font-medium text-gray-900">{m.month}</td>
                      <td className="py-3 px-4 text-right tabular-nums font-semibold text-gray-900">
                        {formatSpend(m.total_spend)}
                      </td>
                      {allChannels.map((ch) => (
                        <td key={ch} className="py-3 px-4 text-right tabular-nums text-gray-700">
                          {m.by_channel[ch] ? formatSpend(m.by_channel[ch]) : "-"}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {monthlySpend && monthlySpend.monthly_data.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center shadow-sm">
          <h3 className="text-base font-semibold text-gray-600 mb-1">광고비 데이터 없음</h3>
          <p className="text-sm text-gray-400">해당 광고주의 광고비 추정 데이터가 없습니다.</p>
        </div>
      )}

      {!selectedId && (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center shadow-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto mb-4 text-gray-300">
            <path d="M3 3v18h18" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M7 16l4-8 4 4 4-8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <h3 className="text-base font-semibold text-gray-600 mb-1">광고비 추이 분석</h3>
          <p className="text-sm text-gray-400 max-w-md mx-auto">
            광고주를 검색하면 월별 채널별 광고비 추이를 확인할 수 있습니다.
          </p>
        </div>
      )}
    </div>
  );
}
