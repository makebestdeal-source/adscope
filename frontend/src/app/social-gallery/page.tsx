"use client";

import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type GalleryItem } from "@/lib/api";
import { toImageUrl } from "@/lib/image-utils";
import { PlanGate } from "@/components/PlanGate";
import { ExportDropdown } from "@/components/ExportDropdown";
import { GallerySelectionDownload } from "@/components/DownloadButtons";

const PLATFORM_OPTIONS = [
  { value: "", label: "전체 플랫폼" },
  { value: "youtube", label: "YouTube" },
  { value: "meta", label: "Meta" },
];

function formatViewCount(n: number | null | undefined): string {
  if (n == null) return "-";
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억회`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}만회`;
  return `${n.toLocaleString()}회`;
}

function formatLikeCount(n: number | null | undefined): string {
  if (n == null) return "-";
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}만`;
  return n.toLocaleString();
}

export default function SocialGalleryPage() {
  return <PlanGate><SocialGalleryContent /></PlanGate>;
}

function SocialGalleryContent() {
  const [platform, setPlatform] = useState("");
  const [advertiserSearch, setAdvertiserSearch] = useState("");
  const [page, setPage] = useState(0);
  const [modalItem, setModalItem] = useState<GalleryItem | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectMode, setSelectMode] = useState(false);

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const ITEMS_PER_PAGE = 60;

  const queryParams = useMemo(() => {
    const params: Record<string, string | number> = {
      limit: ITEMS_PER_PAGE,
      offset: page * ITEMS_PER_PAGE,
      source: "social",
    };
    if (platform) {
      params.channel = platform;
    }
    if (advertiserSearch.trim()) {
      params.advertiser = advertiserSearch.trim();
    }
    return params;
  }, [platform, advertiserSearch, page]);

  const { data, isLoading } = useQuery({
    queryKey: ["social-gallery", queryParams],
    queryFn: () =>
      api.getGallery(queryParams as Parameters<typeof api.getGallery>[0]),
    refetchInterval: 5 * 60 * 1000, // 5분마다 자동 갱신
  });

  const items = data?.items ?? [];
  const totalItems = data?.total ?? 0;
  const totalPages = Math.ceil(totalItems / ITEMS_PER_PAGE);

  const clearFilters = useCallback(() => {
    setPlatform("");
    setAdvertiserSearch("");
    setPage(0);
  }, []);

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
              <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">소셜 소재</h1>
            <p className="text-sm text-gray-500">광고주 공식 채널 YouTube, Meta(Facebook/Instagram) 콘텐츠</p>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-blue-100 p-5 shadow-sm mb-6">
        <div className="flex flex-wrap items-center gap-4">
          {/* Platform */}
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">플랫폼</p>
            <div className="flex gap-2">
              {PLATFORM_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => { setPlatform(opt.value); setPage(0); }}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
                    platform === opt.value
                      ? "bg-blue-500 text-white border-blue-500"
                      : "bg-white text-gray-600 border-gray-200 hover:border-gray-300"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Advertiser search */}
          <div className="flex-1 min-w-[200px]">
            <p className="text-xs font-medium text-gray-500 mb-2">광고주</p>
            <input
              type="text"
              value={advertiserSearch}
              onChange={(e) => { setAdvertiserSearch(e.target.value); setPage(0); }}
              placeholder="광고주 검색..."
              className="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-300"
            />
          </div>

          {/* Clear */}
          <div className="self-end">
            <button
              onClick={clearFilters}
              className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
            >
              초기화
            </button>
          </div>
        </div>
      </div>

      {/* Count + pagination */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <p className="text-sm text-gray-500">
            총 <span className="font-semibold text-gray-900">{totalItems.toLocaleString()}</span>건
          </p>
          <ExportDropdown
            csvUrl="/api/export/social"
            xlsxUrl="/api/export/social.xlsx"
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
              className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40"
            >
              이전
            </button>
            <span className="text-xs text-gray-500">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg disabled:opacity-40"
            >
              다음
            </button>
          </div>
        )}
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-blue-100 overflow-hidden">
              <div className="aspect-video bg-gray-200 animate-pulse" />
              <div className="p-3 space-y-2">
                <div className="h-4 w-3/4 bg-gray-200 animate-pulse rounded" />
                <div className="h-3 w-1/2 bg-gray-200 animate-pulse rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white rounded-xl border border-blue-100 p-12 text-center shadow-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto mb-3 text-blue-200">
            <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <p className="text-sm text-gray-500">소셜 콘텐츠가 없습니다</p>
          <p className="text-xs text-gray-400 mt-1">브랜드 모니터를 실행하면 콘텐츠가 수집됩니다</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {items.map((item) => (
            <SocialCard
              key={item.id}
              item={item}
              onClick={() => selectMode ? toggleSelect(Number(item.id)) : setModalItem(item)}
              selectMode={selectMode}
              selected={selectedIds.has(Number(item.id))}
            />
          ))}
        </div>
      )}

      {/* Modal */}
      {modalItem && (
        <SocialModal item={modalItem} onClose={() => setModalItem(null)} />
      )}
    </div>
  );
}

function SocialCard({ item, onClick, selectMode = false, selected = false }: { item: GalleryItem; onClick: () => void; selectMode?: boolean; selected?: boolean }) {
  const localImgUrl = toImageUrl(item.creative_image_path);
  // Fallback chain: local image -> external thumbnail_url -> null
  const imgSrc = localImgUrl || item.thumbnail_url || null;
  const [imgError, setImgError] = useState(false);
  const showImage = imgSrc && !imgError;

  const platformBadge = item.channel === "youtube"
    ? { label: "YouTube", cls: "bg-red-100 text-red-800" }
    : (item.channel === "instagram" || item.channel === "facebook" || item.channel === "meta")
    ? { label: "Meta", cls: "bg-blue-100 text-blue-800" }
    : { label: item.channel, cls: "bg-gray-100 text-gray-700" };

  // Prefer upload_date (original publish date); fall back to captured_at (crawl date)
  const hasUploadDate = !!item.upload_date;
  const displayDate = item.upload_date || item.captured_at;
  const dateStr = displayDate
    ? new Date(displayDate).toLocaleDateString("ko-KR", { month: "short", day: "numeric" })
    : "";
  const dateSuffix = hasUploadDate ? "" : " (수집일)";

  // Content link (YouTube/Instagram original post)
  const contentUrl = item.url;

  const handleClick = (e: React.MouseEvent) => {
    if (selectMode) {
      onClick();
      return;
    }
    // If there's a content URL, open it in a new tab; otherwise show modal
    if (contentUrl) {
      e.stopPropagation();
      window.open(contentUrl, "_blank", "noopener,noreferrer");
    } else {
      onClick();
    }
  };

  return (
    <div
      className="bg-white rounded-xl border-2 border-blue-100 overflow-hidden shadow-sm hover:shadow-lg hover:border-blue-300 hover:-translate-y-1 transition-all duration-300 cursor-pointer group"
      onClick={handleClick}
    >
      <div className="relative aspect-video bg-gray-100 overflow-hidden">
        {showImage ? (
          <img
            src={imgSrc}
            alt={item.ad_text || "social content"}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-300">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-10 h-10">
              <path d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        )}
        {selectMode && (
          <span className={`absolute top-2 left-2 w-5 h-5 rounded border-2 flex items-center justify-center z-10 ${
            selected ? "bg-indigo-600 border-indigo-600 text-white" : "bg-white/80 border-gray-300"
          }`}>
            {selected && (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" className="w-3 h-3">
                <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </span>
        )}
        <span className={`absolute ${selectMode ? "top-2 left-10" : "top-2 left-2"} px-2 py-0.5 rounded text-[10px] font-medium ${platformBadge.cls}`}>
          {platformBadge.label}
        </span>
        {item.ad_type && (
          <span className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded text-[10px] font-medium bg-black/60 text-white">
            {item.ad_type}
          </span>
        )}
        {/* External link icon overlay when content URL exists */}
        {contentUrl && (
          <span className="absolute top-2 right-2 p-1 rounded bg-black/50 text-white opacity-0 group-hover:opacity-100 transition-opacity">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        )}
      </div>

      <div className="p-3 bg-blue-50/40">
        <p className="text-sm font-semibold text-gray-900 truncate">
          {item.advertiser_name_raw || "광고주 미상"}
        </p>
        {item.ad_text && (
          <p className="text-xs text-gray-500 line-clamp-2 mt-0.5">
            {item.ad_text}
          </p>
        )}
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2 text-[10px] text-blue-500">
            {item.view_count != null && (
              <span>{formatViewCount(item.view_count)}</span>
            )}
            {item.like_count != null && (
              <span>{formatLikeCount(item.like_count)}</span>
            )}
          </div>
          <span className="text-[10px] text-gray-400">
            {dateStr ? `${hasUploadDate ? "게시일 " : ""}${dateStr}${dateSuffix}` : ""}
          </span>
        </div>
      </div>
    </div>
  );
}

function SocialModal({ item, onClose }: { item: GalleryItem; onClose: () => void }) {
  const localImgUrl = toImageUrl(item.creative_image_path);
  const imgSrc = localImgUrl || item.thumbnail_url || null;
  const [imgError, setImgError] = useState(false);
  const contentUrl = item.url;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-fade-backdrop"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 truncate pr-4">
            {item.ad_text || item.advertiser_name_raw || "소셜 콘텐츠"}
          </h3>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>

        {imgSrc && !imgError && (
          <div className="bg-gray-50 p-4 flex justify-center">
            <img
              src={imgSrc}
              alt="social content"
              className="max-h-[60vh] object-contain rounded-lg"
              referrerPolicy="no-referrer"
              onError={() => setImgError(true)}
            />
          </div>
        )}

        <div className="p-4 space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-gray-900">
              {item.advertiser_name_raw}
            </span>
            {item.brand && (
              <span className="text-xs text-gray-400">{item.brand}</span>
            )}
          </div>

          {item.ad_text && (
            <p className="text-sm text-gray-600">{item.ad_text}</p>
          )}

          <div className="flex items-center gap-4 text-sm text-gray-500">
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${
              item.channel === "youtube" ? "bg-red-100 text-red-800" : "bg-blue-100 text-blue-800"
            }`}>
              {item.channel === "youtube" ? "YouTube" : "Meta"}
            </span>
            {item.view_count != null && (
              <span>조회 {formatViewCount(item.view_count)}</span>
            )}
            {item.like_count != null && (
              <span>좋아요 {formatLikeCount(item.like_count)}</span>
            )}
            {(item.upload_date || item.captured_at) && (
              <span>
                {item.upload_date
                  ? `게시일 ${new Date(item.upload_date).toLocaleDateString("ko-KR")}`
                  : `${new Date(item.captured_at!).toLocaleDateString("ko-KR")} (수집일)`}
              </span>
            )}
          </div>

          {/* Link to original content */}
          {contentUrl && (
            <a
              href={contentUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 transition-colors"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
                <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              원본 콘텐츠 보기
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
