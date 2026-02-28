"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, FavoriteAdvertiser } from "@/lib/api";
import { formatSpend } from "@/lib/constants";
import { useState } from "react";
import Link from "next/link";

const CATEGORIES = [
  { key: "all", label: "전체" },
  { key: "my_advertiser", label: "나의 광고주" },
  { key: "competing", label: "경쟁사" },
  { key: "monitoring", label: "모니터링" },
  { key: "interested", label: "관심사" },
  { key: "other", label: "기타" },
] as const;

const CATEGORY_BADGE: Record<string, string> = {
  my_advertiser: "bg-emerald-50 text-emerald-600",
  competing: "bg-red-50 text-red-600",
  monitoring: "bg-blue-50 text-blue-600",
  interested: "bg-amber-50 text-amber-600",
  other: "bg-gray-100 text-gray-500",
};

const CATEGORY_LABEL: Record<string, string> = {
  my_advertiser: "나의 광고주",
  competing: "경쟁사",
  monitoring: "모니터링",
  interested: "관심사",
  other: "기타",
};

export default function FavoritesPage() {
  const queryClient = useQueryClient();
  const [activeCategory, setActiveCategory] = useState("all");
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [noteText, setNoteText] = useState("");

  const { data: favorites, isLoading } = useQuery({
    queryKey: ["favorites", activeCategory],
    queryFn: () => api.getFavorites(activeCategory),
  });

  const removeMutation = useMutation({
    mutationFn: (advertiserId: number) => api.removeFavorite(advertiserId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ advertiserId, data }: { advertiserId: number; data: { category?: string; notes?: string; is_pinned?: boolean } }) =>
      api.updateFavorite(advertiserId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const handleTogglePin = (fav: FavoriteAdvertiser) => {
    updateMutation.mutate({
      advertiserId: fav.advertiser_id,
      data: { is_pinned: !fav.is_pinned },
    });
  };

  const handleSaveNote = (advertiserId: number) => {
    updateMutation.mutate({
      advertiserId,
      data: { notes: noteText },
    });
    setEditingNoteId(null);
    setNoteText("");
  };

  const handleStartEditNote = (fav: FavoriteAdvertiser) => {
    setEditingNoteId(fav.advertiser_id);
    setNoteText(fav.notes || "");
  };

  // Sort: pinned first, then by name
  const sorted = [...(favorites || [])].sort((a, b) => {
    if (a.is_pinned !== b.is_pinned) return a.is_pinned ? -1 : 1;
    return (a.advertiser_name || "").localeCompare(b.advertiser_name || "");
  });

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-yellow-500 flex items-center justify-center shadow-lg shadow-amber-200/50">
          <svg viewBox="0 0 24 24" fill="white" className="w-5 h-5">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">나의 광고주</h1>
          <p className="text-sm text-gray-500">즐겨찾기한 광고주를 관리하세요</p>
        </div>
      </div>

      {/* Category Filter Tabs */}
      <div className="flex items-center gap-1 mb-6 bg-white rounded-xl border border-gray-200 p-1.5 shadow-sm w-fit">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setActiveCategory(cat.key)}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              activeCategory === cat.key
                ? "bg-adscope-500 text-white shadow-sm"
                : "text-gray-500 hover:text-gray-700 hover:bg-gray-50"
            }`}
          >
            {cat.label}
            {favorites && cat.key === "all" && (
              <span className="ml-1.5 text-xs opacity-70">
                ({favorites.length})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
              <div className="animate-pulse space-y-3">
                <div className="h-5 w-40 bg-gray-200 rounded" />
                <div className="h-4 w-24 bg-gray-100 rounded" />
                <div className="flex gap-4">
                  <div className="h-4 w-20 bg-gray-100 rounded" />
                  <div className="h-4 w-20 bg-gray-100 rounded" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-16 shadow-sm text-center">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-12 h-12 mx-auto text-gray-300 mb-4">
            <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <p className="text-gray-500 text-sm">
            즐겨찾기한 광고주가 없습니다.
          </p>
          <p className="text-gray-400 text-xs mt-1">
            광고주 리포트에서 관심 광고주를 추가하세요.
          </p>
          <Link
            href="/advertisers"
            className="inline-block mt-4 px-4 py-2 bg-adscope-500 text-white text-sm font-medium rounded-lg hover:bg-adscope-600 transition-colors"
          >
            광고주 리포트로 이동
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sorted.map((fav) => (
            <div
              key={fav.id}
              className={`bg-white rounded-xl border shadow-sm hover:shadow-md transition-shadow ${
                fav.is_pinned ? "border-amber-300 ring-1 ring-amber-100" : "border-gray-200"
              }`}
            >
              <div className="p-5">
                {/* Top row: name + actions */}
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div className="min-w-0">
                    <Link
                      href={`/advertisers/${fav.advertiser_id}`}
                      className="text-base font-semibold text-adscope-600 hover:text-adscope-800 hover:underline line-clamp-1"
                    >
                      {fav.advertiser_name}
                    </Link>
                    {fav.brand_name && (
                      <p className="text-xs text-gray-400 mt-0.5 truncate">
                        {fav.brand_name}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {/* Pin */}
                    <button
                      onClick={() => handleTogglePin(fav)}
                      className={`p-1.5 rounded-lg transition-colors ${
                        fav.is_pinned
                          ? "text-amber-500 bg-amber-50 hover:bg-amber-100"
                          : "text-gray-300 hover:text-amber-400 hover:bg-gray-50"
                      }`}
                      title={fav.is_pinned ? "핀 해제" : "핀 고정"}
                    >
                      <svg viewBox="0 0 24 24" fill={fav.is_pinned ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" className="w-4 h-4">
                        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z" />
                        <circle cx="12" cy="9" r="2.5" />
                      </svg>
                    </button>
                    {/* Remove */}
                    <button
                      onClick={() => {
                        if (window.confirm("즐겨찾기에서 삭제하시겠습니까?")) {
                          removeMutation.mutate(fav.advertiser_id);
                        }
                      }}
                      className="p-1.5 rounded-lg text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="즐겨찾기 해제"
                    >
                      <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
                        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* Category badge */}
                <div className="mb-3">
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${CATEGORY_BADGE[fav.category] || CATEGORY_BADGE.other}`}>
                    {CATEGORY_LABEL[fav.category] || fav.category}
                  </span>
                </div>

                {/* Stats */}
                <div className="flex items-center gap-4 mb-3">
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">30일 광고</p>
                    <p className="text-sm font-semibold text-gray-900 tabular-nums">
                      {(fav.recent_ad_count ?? 0).toLocaleString()}건
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] text-gray-400 uppercase">추정 광고비</p>
                    <p className="text-sm font-semibold text-gray-900 tabular-nums">
                      {formatSpend(fav.total_est_spend ?? 0)}
                    </p>
                  </div>
                </div>

                {/* Note */}
                {editingNoteId === fav.advertiser_id ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      value={noteText}
                      onChange={(e) => setNoteText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSaveNote(fav.advertiser_id);
                        if (e.key === "Escape") {
                          setEditingNoteId(null);
                          setNoteText("");
                        }
                      }}
                      placeholder="메모 입력..."
                      className="flex-1 text-xs border border-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-adscope-500/20 focus:border-adscope-500"
                      autoFocus
                    />
                    <button
                      onClick={() => handleSaveNote(fav.advertiser_id)}
                      className="text-xs text-adscope-600 font-medium hover:text-adscope-800"
                    >
                      저장
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleStartEditNote(fav)}
                    className="w-full text-left text-xs text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded-lg px-2.5 py-1.5 transition-colors"
                  >
                    {fav.notes || "메모 추가..."}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
