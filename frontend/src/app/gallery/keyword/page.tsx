"use client";

import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type GalleryItem } from "@/lib/api";
import { CHANNEL_LABELS, CHANNEL_BADGE_COLORS } from "@/lib/constants";
import { DataFreshness } from "@/components/DataFreshness";
import { ExportDropdown } from "@/components/ExportDropdown";

const KEYWORD_CHANNELS = ["naver_search", "google_search_ads"];

function getKeywordLabel(item: GalleryItem) {
  return item.keyword || item.search_keyword || null;
}

function getDisplayDate(item: GalleryItem) {
  const dateValue = item.captured_at;
  return dateValue
    ? new Date(dateValue).toLocaleDateString("ko-KR", { year: "numeric", month: "short", day: "numeric" })
    : "";
}

export default function KeywordCreativesPage() {
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set());
  const [advertiserSearch, setAdvertiserSearch] = useState("");
  const [keywordSearch, setKeywordSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);

  const ITEMS_PER_PAGE = 80;
  const dateRangeInvalid = dateFrom && dateTo && dateTo < dateFrom;

  const queryParams = useMemo(() => {
    const params: Record<string, string | number> = {
      limit: ITEMS_PER_PAGE,
      offset: page * ITEMS_PER_PAGE,
      source: "ads",
    };
    if (selectedChannels.size === 1) {
      params.channel = Array.from(selectedChannels)[0];
    }
    if (advertiserSearch.trim()) params.advertiser = advertiserSearch.trim();
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    return params;
  }, [selectedChannels, advertiserSearch, dateFrom, dateTo, page]);

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["gallery-keyword", queryParams],
    queryFn: () => api.getGallery(queryParams as Parameters<typeof api.getGallery>[0]),
    refetchInterval: 5 * 60 * 1000,
  });

  // 키워드 채널만 필터링 + 멀티채널 필터 + 키워드 텍스트 검색
  const filteredItems = useMemo(() => {
    if (!data?.items) return [];
    return data.items.filter((item) => {
      if (!KEYWORD_CHANNELS.includes(item.channel)) return false;
      if (selectedChannels.size > 1 && !selectedChannels.has(item.channel)) return false;
      if (keywordSearch.trim()) {
        const q = keywordSearch.trim().toLowerCase();
        const kw = (item.keyword || item.search_keyword || "").toLowerCase();
        const adText = (item.ad_text || "").toLowerCase();
        const advName = (item.advertiser_name_raw || "").toLowerCase();
        if (!kw.includes(q) && !adText.includes(q) && !advName.includes(q)) return false;
      }
      return true;
    });
  }, [data?.items, selectedChannels, keywordSearch]);

  const totalItems = data?.total ?? 0;
  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);

  const toggleChannel = useCallback((ch: string) => {
    setSelectedChannels((prev) => {
      const next = new Set(prev);
      if (next.has(ch)) next.delete(ch); else next.add(ch);
      return next;
    });
    setPage(0);
  }, []);

  const clearFilters = useCallback(() => {
    setSelectedChannels(new Set());
    setAdvertiserSearch("");
    setKeywordSearch("");
    setDateFrom("");
    setDateTo("");
    setPage(0);
  }, []);

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center shadow-lg shadow-emerald-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.35-4.35" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">광고소재(키워드)</h1>
            <p className="text-sm text-gray-500">
              검색 키워드 광고 소재 — 네이버 검색광고, 구글 검색광고
            </p>
          </div>
        </div>
        <DataFreshness dataUpdatedAt={dataUpdatedAt} onRefresh={() => refetch()} isRefreshing={isLoading} />
      </div>

      <div className="mb-6 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
        네이버·구글 검색광고 키워드 소재를 광고주·키워드·날짜별로 확인할 수 있습니다.
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
        {/* Channel chips */}
        <div className="mb-4">
          <p className="text-xs font-medium text-gray-500 mb-2">채널 필터</p>
          <div className="flex flex-wrap gap-2">
            {KEYWORD_CHANNELS.map((ch) => {
              const isActive = selectedChannels.has(ch);
              return (
                <button
                  key={ch}
                  onClick={() => toggleChannel(ch)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                    isActive
                      ? "bg-adscope-600 text-white border-adscope-600"
                      : "bg-white text-gray-600 border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                  }`}
                >
                  {CHANNEL_LABELS[ch] ?? ch}
                </button>
              );
            })}
          </div>
        </div>

        {/* Search + Date */}
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[180px]">
            <label className="text-xs font-medium text-gray-500 block mb-1">광고주 검색</label>
            <input
              type="text"
              value={advertiserSearch}
              onChange={(e) => { setAdvertiserSearch(e.target.value); setPage(0); }}
              placeholder="광고주 이름..."
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent"
            />
          </div>
          <div className="flex-1 min-w-[180px]">
            <label className="text-xs font-medium text-gray-500 block mb-1">키워드 / 광고문구 검색</label>
            <input
              type="text"
              value={keywordSearch}
              onChange={(e) => { setKeywordSearch(e.target.value); setPage(0); }}
              placeholder="키워드, 광고 문구..."
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent"
            />
          </div>
          <div className="min-w-[140px]">
            <label className="text-xs font-medium text-gray-500 block mb-1">시작일</label>
            <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(0); }}
              className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent ${dateRangeInvalid ? "border-red-400 bg-red-50" : "border-gray-200"}`} />
          </div>
          <div className="min-w-[140px]">
            <label className="text-xs font-medium text-gray-500 block mb-1">종료일</label>
            <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(0); }}
              className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent ${dateRangeInvalid ? "border-red-400 bg-red-50" : "border-gray-200"}`} />
          </div>
          <button onClick={clearFilters} className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors">
            초기화
          </button>
        </div>
        {dateRangeInvalid && <p className="text-xs text-red-500 mt-2">종료일이 시작일보다 이전입니다.</p>}
      </div>

      {/* Results bar */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <p className="text-sm text-gray-500">
            <span className="font-semibold text-gray-900">{filteredItems.length.toLocaleString()}</span> / {totalItems.toLocaleString()}개 소재
          </p>
          <ExportDropdown csvUrl="/api/export/gallery" xlsxUrl="/api/export/gallery.xlsx" />
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
              className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50">이전</button>
            <span className="text-xs text-gray-500">{page + 1} / {totalPages}</span>
            <button onClick={() => setPage((p) => Math.min(Math.max(0, totalPages - 1), p + 1))} disabled={page >= Math.max(0, totalPages - 1)}
              className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50">다음</button>
          </div>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <div className="skeleton h-4 w-32 mb-2" />
              <div className="skeleton h-5 w-full mb-1" />
              <div className="skeleton h-3 w-2/3" />
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <p className="text-sm text-gray-500 mb-3">데이터를 불러오는 중 오류가 발생했습니다</p>
          <button onClick={() => refetch()} className="px-4 py-2 text-sm font-medium text-white bg-adscope-600 rounded-lg hover:bg-adscope-700 transition-colors">
            다시 시도
          </button>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto mb-3 text-gray-300">
            <circle cx="11" cy="11" r="7" /><path d="m21 21-4.35-4.35" />
          </svg>
          <p className="text-sm text-gray-500">표시할 키워드 소재가 없습니다</p>
          <p className="text-xs text-gray-400 mt-1">필터 조건을 변경해 보세요</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filteredItems.map((item) => (
            <KeywordAdCard key={item.id} item={item} />
          ))}
        </div>
      )}

      {/* Pagination bottom */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50">이전 페이지</button>
          <span className="text-sm text-gray-500 px-4">{page + 1} / {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(Math.max(0, totalPages - 1), p + 1))} disabled={page >= Math.max(0, totalPages - 1)}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50">다음 페이지</button>
        </div>
      )}
    </div>
  );
}

function KeywordAdCard({ item }: { item: GalleryItem }) {
  const isNaver = item.channel === "naver_search";
  const badgeColor = CHANNEL_BADGE_COLORS[item.channel] ?? "bg-gray-100 text-gray-700";
  const channelLabel = CHANNEL_LABELS[item.channel] ?? item.channel;
  const keyword = item.keyword || item.search_keyword || null;
  const dateStr = getDisplayDate(item);

  const isGoogleTransparency = item.url?.includes("adstransparency.google.com");
  const displayUrl = isGoogleTransparency ? null : item.url;
  const domain = displayUrl
    ? (() => { try { return new URL(displayUrl).hostname.replace(/^www\./, ""); } catch { return displayUrl; } })()
    : (item.display_url || null);

  const isFormatPlaceholder = /^(google_search|youtube_transparency)_\d+$/.test(item.ad_text || "");
  const adText = isFormatPlaceholder ? null : item.ad_text;

  return (
    <article className={`rounded-xl border shadow-sm overflow-hidden ${isNaver ? "border-blue-100 bg-white" : "border-green-100 bg-white"}`}>
      <div className={`border-l-4 p-4 ${isNaver ? "border-[#03c75a]" : "border-[#4285f4]"}`}>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badgeColor}`}>{channelLabel}</span>
          {keyword && (
            <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
              키워드: {keyword}
            </span>
          )}
          <span className="text-xs font-semibold text-gray-700">{item.advertiser_name_raw || "광고주 미상"}</span>
          {dateStr && <span className="ml-auto text-xs text-gray-400">{dateStr}</span>}
        </div>
        {domain && (
          <p className={`text-xs mb-1 font-medium ${isNaver ? "text-green-700" : "text-green-600"}`}>{domain}</p>
        )}
        <p className={`text-base font-bold leading-snug mb-1 ${isNaver ? "text-blue-700" : "text-blue-600"}`}>
          {adText || item.advertiser_name_raw || "(광고 제목 미제공)"}
        </p>
        {displayUrl && (
          <p className="text-xs text-gray-400 truncate">{displayUrl}</p>
        )}
      </div>
    </article>
  );
}
