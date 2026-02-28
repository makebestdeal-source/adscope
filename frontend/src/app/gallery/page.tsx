"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import { useQuery, useIsFetching } from "@tanstack/react-query";
import { api, type GalleryItem } from "@/lib/api";
import { CHANNEL_LABELS, CHANNEL_BADGE_COLORS } from "@/lib/constants";
import { parseImagePath, type ParsedImagePath, type AtlasCoords } from "@/lib/image-utils";
import { PlanGate } from "@/components/PlanGate";
import { DataFreshness } from "@/components/DataFreshness";
import { ExportDropdown } from "@/components/ExportDropdown";
import { GallerySelectionDownload, DownloadButton } from "@/components/DownloadButtons";

const ALL_CHANNELS = [
  "naver_search",
  "naver_da",
  "google_gdn",
  "youtube_ads",
  "kakao_da",
  "meta",
];

export default function GalleryPage() {
  return <PlanGate><GalleryContent /></PlanGate>;
}

function GalleryContent() {
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(
    new Set()
  );
  const [advertiserSearch, setAdvertiserSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(0);
  const [modalItem, setModalItem] = useState<GalleryItem | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectMode, setSelectMode] = useState(false);

  const ITEMS_PER_PAGE = 60;

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
    setSelectMode(false);
  }, []);

  // Date range validation
  const dateRangeInvalid = dateFrom && dateTo && dateTo < dateFrom;

  // Build API params
  const queryParams = useMemo(() => {
    const params: Record<string, string | number> = {
      limit: ITEMS_PER_PAGE,
      offset: page * ITEMS_PER_PAGE,
    };
    // Only send channel filter if exactly one channel selected
    // (API supports single channel filter)
    if (selectedChannels.size === 1) {
      params.channel = Array.from(selectedChannels)[0];
    }
    if (advertiserSearch.trim()) {
      params.advertiser = advertiserSearch.trim();
    }
    if (dateFrom) {
      params.date_from = dateFrom;
    }
    if (dateTo) {
      params.date_to = dateTo;
    }
    params.source = "ads";
    return params;
  }, [selectedChannels, advertiserSearch, dateFrom, dateTo, page]);

  const { data, isLoading, isError, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["gallery", queryParams],
    queryFn: () =>
      api.getGallery(queryParams as Parameters<typeof api.getGallery>[0]),
    refetchInterval: 5 * 60 * 1000, // 5분마다 자동 갱신
  });

  // Client-side multi-channel filter (API only supports single channel)
  const filteredItems = useMemo(() => {
    if (!data?.items) return [];
    if (selectedChannels.size <= 1) return data.items;
    return data.items.filter((item) => selectedChannels.has(item.channel));
  }, [data?.items, selectedChannels]);

  const totalItems = data?.total ?? 0;
  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);

  const toggleChannel = useCallback((channel: string) => {
    setSelectedChannels((prev) => {
      const next = new Set(prev);
      if (next.has(channel)) {
        next.delete(channel);
      } else {
        next.add(channel);
      }
      return next;
    });
    setPage(0);
  }, []);

  const selectAllChannels = useCallback(() => {
    setSelectedChannels(new Set(ALL_CHANNELS));
    setPage(0);
  }, []);

  const deselectAllChannels = useCallback(() => {
    setSelectedChannels(new Set());
    setPage(0);
  }, []);

  const clearFilters = useCallback(() => {
    setSelectedChannels(new Set());
    setAdvertiserSearch("");
    setDateFrom("");
    setDateTo("");
    setPage(0);
  }, []);

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-500 flex items-center justify-center shadow-lg shadow-amber-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              광고 소재
            </h1>
            <p className="text-sm text-gray-500">
              수집된 광고 크리에이티브 갤러리
            </p>
          </div>
        </div>
        <DataFreshness
          dataUpdatedAt={dataUpdatedAt}
          onRefresh={() => refetch()}
          isRefreshing={isLoading}
        />
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
        <div className="flex flex-wrap items-center gap-4">
          {/* Channel filter chips */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <p className="text-xs font-medium text-gray-500">채널 필터</p>
              <button
                onClick={selectAllChannels}
                className="text-[10px] text-adscope-600 hover:text-adscope-800 font-medium hover:underline"
              >
                전체 선택
              </button>
              <span className="text-gray-300 text-[10px]">|</span>
              <button
                onClick={deselectAllChannels}
                className="text-[10px] text-gray-500 hover:text-gray-700 font-medium hover:underline"
              >
                전체 해제
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {ALL_CHANNELS.map((ch) => {
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
        </div>

        {/* Search + Date range */}
        <div className="flex flex-wrap items-end gap-4 mt-4">
          {/* Advertiser search */}
          <div className="flex-1 min-w-[200px]">
            <label className="text-xs font-medium text-gray-500 block mb-1">
              광고주 검색
            </label>
            <input
              type="text"
              value={advertiserSearch}
              onChange={(e) => {
                setAdvertiserSearch(e.target.value);
                setPage(0);
              }}
              placeholder="광고주 이름..."
              className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent"
            />
          </div>

          {/* Date from */}
          <div className="min-w-[150px]">
            <label className="text-xs font-medium text-gray-500 block mb-1">
              시작일
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(0);
              }}
              className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent ${
                dateRangeInvalid ? "border-red-400 bg-red-50" : "border-gray-200"
              }`}
            />
          </div>

          {/* Date to */}
          <div className="min-w-[150px]">
            <label className="text-xs font-medium text-gray-500 block mb-1">
              종료일
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(0);
              }}
              className={`w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500 focus:border-transparent ${
                dateRangeInvalid ? "border-red-400 bg-red-50" : "border-gray-200"
              }`}
            />
          </div>

          {/* Clear button */}
          <button
            onClick={clearFilters}
            className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
          >
            초기화
          </button>
        </div>

        {/* Date range warning */}
        {dateRangeInvalid && (
          <p className="text-xs text-red-500 mt-2">
            종료일이 시작일보다 이전입니다. 날짜 범위를 확인해 주세요.
          </p>
        )}
      </div>

      {/* Results count + Download */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <p className="text-sm text-gray-500">
            총 <span className="font-semibold text-gray-900">{totalItems.toLocaleString()}</span>개 소재
          </p>
          <ExportDropdown
            csvUrl="/api/export/gallery"
            xlsxUrl="/api/export/gallery.xlsx"
          />
          <button
            onClick={() => { setSelectMode(!selectMode); if (selectMode) clearSelection(); }}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors ${
              selectMode
                ? "text-white bg-indigo-600 border-indigo-600"
                : "text-gray-600 bg-white border-gray-200 hover:bg-gray-50"
            }`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
              <path d="M9 11l3 3L22 4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {selectMode ? "선택 취소" : "이미지 선택"}
          </button>
          {selectMode && selectedIds.size > 0 && (
            <GallerySelectionDownload selectedIds={Array.from(selectedIds)} />
          )}
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
            >
              이전
            </button>
            <span className="text-xs text-gray-500">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(Math.max(0, totalPages - 1), p + 1))}
              disabled={page >= Math.max(0, totalPages - 1)}
              className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
            >
              다음
            </button>
          </div>
        )}
      </div>

      {/* Gallery Grid */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm"
            >
              <div className="skeleton h-48 w-full" />
              <div className="p-3 space-y-2">
                <div className="skeleton h-4 w-3/4" />
                <div className="skeleton h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : isError ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="w-12 h-12 mx-auto mb-3 text-red-300"
          >
            <path
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <p className="text-sm text-gray-500 mb-3">데이터를 불러오는 중 오류가 발생했습니다</p>
          <button
            onClick={() => refetch()}
            className="px-4 py-2 text-sm font-medium text-white bg-adscope-600 rounded-lg hover:bg-adscope-700 transition-colors"
          >
            다시 시도
          </button>
        </div>
      ) : filteredItems.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            className="w-12 h-12 mx-auto mb-3 text-gray-300"
          >
            <path
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <p className="text-sm text-gray-500">이미지가 있는 광고 소재가 없습니다</p>
          <p className="text-xs text-gray-400 mt-1">필터 조건을 변경해 보세요</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {filteredItems.map((item) => (
            <GalleryCard
              key={item.id}
              item={item}
              onClick={() => selectMode ? toggleSelect(Number(item.id)) : setModalItem(item)}
              selectMode={selectMode}
              selected={selectedIds.has(Number(item.id))}
            />
          ))}
        </div>
      )}

      {/* Pagination bottom */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
          >
            이전 페이지
          </button>
          <span className="text-sm text-gray-500 px-4">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(Math.max(0, totalPages - 1), p + 1))}
            disabled={page >= Math.max(0, totalPages - 1)}
            className="px-4 py-2 text-sm rounded-lg border border-gray-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-50 transition-colors"
          >
            다음 페이지
          </button>
        </div>
      )}

      {/* Modal */}
      {modalItem && (
        <ImageModal item={modalItem} onClose={() => setModalItem(null)} />
      )}
    </div>
  );
}

function ImagePlaceholder({ channel }: { channel?: string }) {
  const channelLabel = channel ? (CHANNEL_LABELS[channel] ?? channel) : null;
  return (
    <div className="flex items-center justify-center h-full bg-gray-100 text-gray-400">
      <div className="text-center">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="w-8 h-8 mx-auto mb-1 text-gray-300"
        >
          <path
            d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-xs text-gray-400">이미지 없음</p>
        {channelLabel && (
          <p className="text-[10px] text-gray-300 mt-0.5">{channelLabel}</p>
        )}
      </div>
    </div>
  );
}

/**
 * 아틀라스 스프라이트 이미지 컴포넌트.
 * 아틀라스 경로인 경우 CSS background-position으로 잘라서 표시,
 * 일반 이미지인 경우 그대로 <img> 태그로 표시.
 */
function CreativeImage({
  path,
  alt,
  className,
  containerClassName,
  onError,
  loading,
  objectFit = "cover",
}: {
  path: string | null | undefined;
  alt: string;
  className?: string;
  containerClassName?: string;
  onError?: () => void;
  loading?: "lazy" | "eager";
  objectFit?: "cover" | "contain";
}) {
  const parsed = parseImagePath(path);
  const [imgError, setImgError] = useState(false);

  const handleError = () => {
    setImgError(true);
    onError?.();
  };

  if (!parsed || imgError) {
    return null;
  }

  // 아틀라스 스프라이트: CSS background-image로 잘라서 표시
  if (parsed.isAtlas && parsed.atlas) {
    const { x, y, w, h } = parsed.atlas;
    return (
      <div
        className={containerClassName || className}
        style={{
          backgroundImage: `url(${parsed.url})`,
          backgroundPosition: `-${x}px -${y}px`,
          backgroundRepeat: "no-repeat",
          backgroundSize: "auto",
          width: "100%",
          height: "100%",
        }}
        role="img"
        aria-label={alt}
      >
        {/* 숨겨진 img로 로드 에러 감지 */}
        <img
          src={parsed.url}
          alt=""
          className="hidden"
          referrerPolicy="no-referrer"
          onError={handleError}
        />
      </div>
    );
  }

  // 일반 이미지: 기존 <img> 태그
  return (
    <img
      src={parsed.url}
      alt={alt}
      className={className}
      loading={loading}
      referrerPolicy="no-referrer"
      onError={handleError}
      style={objectFit === "contain" ? { objectFit: "contain" } : undefined}
    />
  );
}

function GalleryCard({
  item,
  onClick,
  selectMode = false,
  selected = false,
}: {
  item: GalleryItem;
  onClick: () => void;
  selectMode?: boolean;
  selected?: boolean;
}) {
  const parsed = parseImagePath(item.creative_image_path);
  const [imgError, setImgError] = useState(false);
  const badgeColor =
    CHANNEL_BADGE_COLORS[item.channel] ?? "bg-gray-100 text-gray-700";
  const channelLabel = CHANNEL_LABELS[item.channel] ?? item.channel;

  const isSocial = item.source === "social";
  // For social items: prefer upload_date (original publish date); for ads: use captured_at
  const displayDate = isSocial ? (item.upload_date || item.captured_at) : item.captured_at;
  const dateStr = displayDate
    ? new Date(displayDate).toLocaleDateString("ko-KR", {
        month: "short",
        day: "numeric",
      })
    : "";
  const dateLabelSuffix = isSocial && !item.upload_date && item.captured_at ? " (수집일)" : "";

  const showImage = parsed && !imgError;

  return (
    <div
      className={`rounded-xl overflow-hidden shadow-sm hover:shadow-lg transition-all duration-300 cursor-pointer group ${
        selected
          ? "bg-white border-2 border-indigo-500 ring-2 ring-indigo-200"
          : isSocial
            ? "bg-white border-2 border-blue-200 hover:border-blue-400 hover:-translate-y-1"
            : "bg-white border border-gray-200 hover:border-indigo-200 hover:-translate-y-1"
      }`}
      onClick={onClick}
    >
      {/* Image area */}
      <div className="relative aspect-[4/3] bg-gray-100 overflow-hidden">
        {showImage ? (
          <CreativeImage
            path={item.creative_image_path}
            alt={item.advertiser_name_raw || "ad creative"}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <ImagePlaceholder channel={item.channel} />
        )}

        {/* Selection checkbox overlay */}
        {selectMode && (
          <div className={`absolute top-2 left-2 w-6 h-6 rounded-md border-2 flex items-center justify-center transition-colors z-10 ${
            selected
              ? "bg-indigo-600 border-indigo-600"
              : "bg-white/80 border-gray-300 hover:border-indigo-400"
          }`}>
            {selected && (
              <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" className="w-4 h-4">
                <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
        )}

        {/* Channel badge overlay */}
        <span
          className={`absolute ${selectMode ? "top-2 left-10" : "top-2 left-2"} px-2 py-0.5 rounded text-[10px] font-medium ${badgeColor}`}
        >
          {channelLabel}
        </span>
        {isSocial ? (
          <span className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500 text-white">
            SOCIAL
          </span>
        ) : (
          <span className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500 text-white">
            AD
          </span>
        )}
      </div>

      {/* Info area */}
      <div className={`p-3 ${isSocial ? "bg-blue-50/50" : ""}`}>
        <p className="text-sm font-semibold text-gray-900 truncate">
          {item.advertiser_name_raw || "광고주 미상"}
        </p>
        {item.ad_text && (
          <p className="text-xs text-gray-500 line-clamp-2 mt-0.5">
            {item.ad_text}
          </p>
        )}
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-1.5">
            {item.ad_type && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                isSocial
                  ? "bg-blue-100 text-blue-700"
                  : "bg-gray-100 text-gray-600"
              }`}>
                {item.ad_type}
              </span>
            )}
            {isSocial && item.view_count != null && (
              <span className="text-[10px] text-blue-400">
                {item.view_count >= 10000
                  ? `${(item.view_count / 10000).toFixed(1)}만회`
                  : `${item.view_count.toLocaleString()}회`}
              </span>
            )}
          </div>
          <span className="text-[10px] text-gray-400 ml-auto">{dateStr}{dateLabelSuffix}</span>
        </div>
      </div>
    </div>
  );
}

function ImageModal({
  item,
  onClose,
}: {
  item: GalleryItem;
  onClose: () => void;
}) {
  const parsed = parseImagePath(item.creative_image_path);
  const [imgError, setImgError] = useState(false);
  const badgeColor =
    CHANNEL_BADGE_COLORS[item.channel] ?? "bg-gray-100 text-gray-700";
  const channelLabel = CHANNEL_LABELS[item.channel] ?? item.channel;

  const isSocial = item.source === "social";
  const displayDate = isSocial ? (item.upload_date || item.captured_at) : item.captured_at;
  const dateStr = displayDate
    ? new Date(displayDate).toLocaleString("ko-KR", {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
  const dateLabel = isSocial
    ? (item.upload_date ? "게시일:" : "수집일:")
    : "수집일:";

  const showImage = parsed && !imgError;

  // ESC key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fade-backdrop" />

      {/* Modal content */}
      <div
        className="relative bg-white rounded-2xl shadow-2xl max-w-3xl w-full max-h-[90vh] overflow-auto animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 z-10 w-8 h-8 flex items-center justify-center rounded-full bg-black/30 text-white hover:bg-black/50 transition-colors"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="w-5 h-5"
          >
            <path
              d="M6 18L18 6M6 6l12 12"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        {/* Image */}
        {showImage ? (
          <div className="bg-gray-100">
            <CreativeImage
              path={item.creative_image_path}
              alt={item.advertiser_name_raw || "ad creative"}
              className="w-full max-h-[60vh] object-contain"
              onError={() => setImgError(true)}
              objectFit="contain"
            />
          </div>
        ) : (
          <div className="w-full h-64 bg-gray-100 flex items-center justify-center">
            <div className="text-center text-gray-400">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                className="w-12 h-12 mx-auto mb-2"
              >
                <path
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <p className="text-sm">
                {imgError
                  ? "이미지를 불러올 수 없습니다"
                  : "이미지 없음"}
              </p>
            </div>
          </div>
        )}

        {/* Detail info */}
        <div className="p-6 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-bold text-gray-900">
                {item.advertiser_name_raw || "광고주 미상"}
              </h3>
              {item.brand && (
                <p className="text-sm text-gray-500">{item.brand}</p>
              )}
            </div>
            <span
              className={`px-3 py-1 rounded-full text-xs font-medium flex-shrink-0 ${badgeColor}`}
            >
              {channelLabel}
            </span>
          </div>

          {item.ad_text && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">광고 문구</p>
              <p className="text-sm text-gray-700">{item.ad_text}</p>
            </div>
          )}

          {item.landing_analysis && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">랜딩 분석</p>
              <div className="text-sm text-gray-700 space-y-0.5">
                {item.landing_analysis.brand_name && (
                  <p>브랜드: <span className="font-medium">{item.landing_analysis.brand_name}</span></p>
                )}
                {item.landing_analysis.business_name && (
                  <p>사업자: {item.landing_analysis.business_name}</p>
                )}
                {item.landing_analysis.domain && (
                  <p>도메인: <span className="text-blue-500">{item.landing_analysis.domain}</span></p>
                )}
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-4 text-xs text-gray-500 pt-2 border-t border-gray-100">
            {item.ad_type && (
              <div>
                <span className="font-medium text-gray-600">유형:</span>{" "}
                {item.ad_type}
              </div>
            )}
            {dateStr && (
              <div>
                <span className="font-medium text-gray-600">{dateLabel}</span>{" "}
                {dateStr}
              </div>
            )}
            {item.url && (
              <div className="min-w-0 flex-1">
                <span className="font-medium text-gray-600">URL:</span>{" "}
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-500 hover:underline truncate inline-block max-w-[300px] align-bottom"
                >
                  {item.url}
                </a>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
