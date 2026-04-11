"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, AdvertiserSearchResult } from "@/lib/api";
import { formatChannel, formatSpend } from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";

export default function KeywordReversePage() {
  const [advertiserSearch, setAdvertiserSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedName, setSelectedName] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [days, setDays] = useState(30);
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

  const { data: keywordData, isLoading } = useQuery({
    queryKey: ["advertiserKeywords", selectedId, days],
    queryFn: () => api.getAdvertiserKeywords(selectedId!, days),
    enabled: !!selectedId,
  });

  const handleSelect = (adv: AdvertiserSearchResult) => {
    setSelectedId(adv.id);
    setSelectedName(adv.name);
    setAdvertiserSearch(adv.name);
    setShowDropdown(false);
  };

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
            <path d="M9 14l-4-4 4-4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 10h11a4 4 0 110 8h-1" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">키워드 역추적</h1>
          <p className="text-sm text-gray-500">광고주가 어떤 키워드에 광고를 집행하고 있는지 역추적</p>
        </div>
      </div>

      {/* 사용법 안내 */}
      {!selectedId && (
        <div className="mb-6 p-4 bg-violet-50 border border-violet-200 rounded-xl text-sm text-violet-800">
          <p className="font-semibold mb-1">사용법</p>
          <ul className="list-disc list-inside space-y-0.5 text-xs text-violet-700">
            <li>광고주명을 검색하여 선택하면 해당 광고주가 집행 중인 키워드 목록이 표시됩니다</li>
            <li>키워드별 노출 횟수, 채널, 포지션 등 상세 정보를 확인할 수 있습니다</li>
            <li>키워드를 클릭하면 광고 랜드스케이프 페이지에서 경쟁 현황을 확인할 수 있습니다</li>
          </ul>
          <p className="text-xs text-violet-600 mt-2">예시: &quot;삼성전자&quot;, &quot;LG생활건강&quot;, &quot;아모레퍼시픽&quot; 등을 검색해보세요</p>
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
              className="w-full pl-10 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-500/20 focus:border-violet-500"
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
          <PeriodSelector days={days} onDaysChange={setDays} />
        </div>
      </div>

      {/* Results */}
      {selectedId && isLoading && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400 text-sm shadow-sm">
          키워드 역추적 중...
        </div>
      )}

      {keywordData && keywordData.keywords.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                {selectedName} 키워드 역추적
              </h2>
              <p className="text-xs text-gray-500 mt-0.5">
                {keywordData.keywords.length}개 키워드에서 광고 노출 확인
              </p>
            </div>
            <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-violet-100 text-violet-700">
              최근 {days}일
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">#</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">키워드</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">채널</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">노출수</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">월간 검색량</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">CPC</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">최초 수집</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">최근 수집</th>
                </tr>
              </thead>
              <tbody>
                {keywordData.keywords.map((kw, idx) => (
                  <tr key={kw.keyword_id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="py-3 px-4 text-gray-400 tabular-nums">{idx + 1}</td>
                    <td className="py-3 px-4">
                      <Link
                        href={`/keyword-analysis/landscape?keyword=${encodeURIComponent(kw.keyword)}`}
                        className="font-medium text-violet-600 hover:text-violet-800 hover:underline"
                      >
                        {kw.keyword}
                      </Link>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {kw.channels.map((ch) => (
                          <span key={ch} className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                            {formatChannel(ch)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums font-medium text-gray-900">
                      {kw.impression_count.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                      {kw.monthly_search_vol ? kw.monthly_search_vol.toLocaleString() : "-"}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums text-gray-700">
                      {kw.naver_cpc ? `${kw.naver_cpc.toLocaleString()}원` : "-"}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums text-gray-500 text-xs">
                      {kw.first_seen ?? "-"}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums text-gray-500 text-xs">
                      {kw.last_seen ?? "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {keywordData && keywordData.keywords.length === 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center shadow-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto mb-4 text-gray-300">
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <h3 className="text-base font-semibold text-gray-600 mb-1">키워드 데이터 없음</h3>
          <p className="text-sm text-gray-400">해당 광고주의 키워드 광고 노출 이력이 없습니다.</p>
        </div>
      )}

      {!selectedId && (
        <div className="bg-white rounded-xl border border-gray-200 p-16 text-center shadow-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto mb-4 text-gray-300">
            <path d="M9 14l-4-4 4-4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M5 10h11a4 4 0 110 8h-1" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <h3 className="text-base font-semibold text-gray-600 mb-1">키워드 역추적 시작하기</h3>
          <p className="text-sm text-gray-400 max-w-md mx-auto">
            광고주를 검색하면 해당 광고주가 어떤 키워드에 광고를 집행하고 있는지 확인할 수 있습니다.
          </p>
        </div>
      )}
    </div>
  );
}
