"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, AdvertiserSearchResult, BrandTreeChild, BrandTreeGroup, FavoriteAdvertiser } from "@/lib/api";
import { useState, useEffect, useRef, useMemo } from "react";
import Link from "next/link";
import { ExportDropdown } from "@/components/ExportDropdown";
import { DownloadButton } from "@/components/DownloadButtons";

/* ── Tree Node Component ── */
function TreeNode({ node, depth = 0 }: { node: BrandTreeChild; depth?: number }) {
  const [open, setOpen] = useState(false);
  const hasChildren = node.children && node.children.length > 0;
  const indent = depth * 24;

  return (
    <div>
      <div
        className="flex items-center gap-2 py-2 px-4 hover:bg-gray-50 transition-colors border-b border-gray-50"
        style={{ paddingLeft: `${16 + indent}px` }}
      >
        {/* Expand/collapse toggle */}
        {hasChildren ? (
          <button
            onClick={() => setOpen(!open)}
            className="w-5 h-5 flex items-center justify-center text-gray-400 hover:text-gray-600 flex-shrink-0"
          >
            <svg
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`w-4 h-4 transition-transform ${open ? "rotate-90" : ""}`}
            >
              <path
                fillRule="evenodd"
                d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        ) : (
          <span className="w-5 h-5 flex-shrink-0" />
        )}

        {/* Type badge */}
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded flex-shrink-0 ${
          node.advertiser_type === "company"
            ? "bg-blue-50 text-blue-600"
            : node.advertiser_type === "brand"
            ? "bg-purple-50 text-purple-600"
            : node.advertiser_type === "product"
            ? "bg-amber-50 text-amber-600"
            : "bg-gray-50 text-gray-500"
        }`}>
          {node.advertiser_type === "company" ? "Company"
            : node.advertiser_type === "brand" ? "Brand"
            : node.advertiser_type === "product" ? "Product"
            : node.advertiser_type ?? "N/A"}
        </span>

        {/* Name */}
        <Link
          href={`/advertisers/${node.id}`}
          className="font-medium text-sm text-adscope-600 hover:text-adscope-800 hover:underline truncate"
        >
          {node.name}
        </Link>

        {node.brand_name && (
          <span className="text-xs text-gray-400 truncate hidden sm:inline">
            ({node.brand_name})
          </span>
        )}

        <span className="ml-auto flex items-center gap-3 flex-shrink-0">
          {/* Website */}
          {node.website && (
            <a
              href={node.website}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-adscope-500 hover:text-adscope-700 truncate max-w-[160px] hidden md:inline"
            >
              {node.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
            </a>
          )}
          {/* Ad count */}
          {node.ad_count > 0 ? (
            <span className="text-xs font-medium text-gray-700 tabular-nums whitespace-nowrap">
              {node.ad_count.toLocaleString()}
            </span>
          ) : (
            <span className="text-xs text-gray-300 tabular-nums">0</span>
          )}
        </span>
      </div>

      {/* Children */}
      {open && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Group Accordion Component ── */
function GroupAccordion({ group }: { group: BrandTreeGroup }) {
  const [open, setOpen] = useState(false);
  const childCount = group.children.length;

  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-3 py-3 px-4 hover:bg-gray-50 transition-colors text-left"
      >
        <svg
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-4 h-4 text-gray-400 transition-transform flex-shrink-0 ${open ? "rotate-90" : ""}`}
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
            clipRule="evenodd"
          />
        </svg>
        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-600 flex-shrink-0">
          Group
        </span>
        <span className="font-semibold text-sm text-gray-900 truncate">
          {group.name}
        </span>
        <span className="ml-auto text-xs text-gray-400 flex-shrink-0">
          {childCount}
        </span>
      </button>
      {open && (
        <div className="bg-gray-50/50">
          {group.children.length > 0 ? (
            group.children.map((child) => (
              <TreeNode key={child.id} node={child} depth={1} />
            ))
          ) : (
            <p className="text-xs text-gray-400 py-3 px-8">
              No child advertisers
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Star Button Component ── */
function StarButton({ advertiserId, isFavorite, onToggle }: { advertiserId: number; isFavorite: boolean; onToggle: (id: number, current: boolean) => void }) {
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle(advertiserId, isFavorite);
      }}
      className={`flex-shrink-0 p-1 rounded transition-colors ${
        isFavorite
          ? "text-amber-400 hover:text-amber-500"
          : "text-gray-300 hover:text-amber-400"
      }`}
      title={isFavorite ? "즐겨찾기 해제" : "즐겨찾기 추가"}
    >
      <svg viewBox="0 0 24 24" fill={isFavorite ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" className="w-4 h-4">
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
      </svg>
    </button>
  );
}

/* ── Main Page ── */
export default function AdvertisersPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);
  const [viewMode, setViewMode] = useState<"list" | "tree">("list");
  const [sortKey, setSortKey] = useState<"name" | "brand" | "website" | "ad_count">("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const dropdownRef = useRef<HTMLDivElement>(null);

  // debounce 300ms
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const params: Record<string, string> = { limit: "5000" };
  if (debouncedSearch) params.search = debouncedSearch;

  const { data: advertisers, isLoading } = useQuery({
    queryKey: ["advertisers", debouncedSearch],
    queryFn: () => api.getAdvertisers(params),
  });

  const { data: searchResults } = useQuery({
    queryKey: ["advertiserSearch", debouncedSearch],
    queryFn: () => api.searchAdvertisers(debouncedSearch),
    enabled: debouncedSearch.length >= 1,
  });

  const { data: topAdvertisers } = useQuery({
    queryKey: ["topAdvertisers30"],
    queryFn: () => api.getTopAdvertisers(30, 200),
  });

  const { data: brandTree, isLoading: treeLoading } = useQuery({
    queryKey: ["brandTree"],
    queryFn: () => api.getBrandTree(),
    enabled: viewMode === "tree",
  });

  // Favorites
  const { data: favoritesData } = useQuery({
    queryKey: ["favorites"],
    queryFn: () => api.getFavorites(),
  });

  const favoriteIds = useMemo(() => {
    const set = new Set<number>();
    if (favoritesData) {
      for (const fav of favoritesData) {
        set.add(fav.advertiser_id);
      }
    }
    return set;
  }, [favoritesData]);

  const addFavMutation = useMutation({
    mutationFn: (advertiserId: number) => api.addFavorite(advertiserId),
    onMutate: async (advertiserId) => {
      // Optimistic update
      await queryClient.cancelQueries({ queryKey: ["favorites"] });
      const prev = queryClient.getQueryData<FavoriteAdvertiser[]>(["favorites"]);
      queryClient.setQueryData<FavoriteAdvertiser[]>(["favorites"], (old) => [
        ...(old || []),
        { id: 0, user_id: 0, advertiser_id: advertiserId, advertiser_name: "", brand_name: null, category: "other", notes: null, is_pinned: false, sort_order: 0, recent_ad_count: 0, total_est_spend: 0, created_at: null, updated_at: null, industry_name: null, website: null, logo_url: null },
      ]);
      return { prev };
    },
    onError: (_err, _id, context) => {
      if (context?.prev) queryClient.setQueryData(["favorites"], context.prev);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const removeFavMutation = useMutation({
    mutationFn: (advertiserId: number) => api.removeFavorite(advertiserId),
    onMutate: async (advertiserId) => {
      await queryClient.cancelQueries({ queryKey: ["favorites"] });
      const prev = queryClient.getQueryData<FavoriteAdvertiser[]>(["favorites"]);
      queryClient.setQueryData<FavoriteAdvertiser[]>(["favorites"], (old) =>
        (old || []).filter((f) => f.advertiser_id !== advertiserId)
      );
      return { prev };
    },
    onError: (_err, _id, context) => {
      if (context?.prev) queryClient.setQueryData(["favorites"], context.prev);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
    },
  });

  const handleToggleFavorite = (advertiserId: number, currentlyFavorite: boolean) => {
    if (currentlyFavorite) {
      removeFavMutation.mutate(advertiserId);
    } else {
      addFavMutation.mutate(advertiserId);
    }
  };

  const adCountMap = new Map(
    topAdvertisers?.map((a) => [a.advertiser, a.ad_count]) ?? []
  );

  const handleSort = (key: typeof sortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir(key === "ad_count" ? "desc" : "asc");
    }
  };

  const sortedAdvertisers = useMemo(() => {
    if (!advertisers) return [];
    return [...advertisers].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      switch (sortKey) {
        case "name":
          return dir * (a.name || "").localeCompare(b.name || "");
        case "brand":
          return dir * (a.brand_name || "").localeCompare(b.brand_name || "");
        case "website":
          return dir * (a.website || "").localeCompare(b.website || "");
        case "ad_count": {
          const ca = adCountMap.get(a.name) ?? 0;
          const cb = adCountMap.get(b.name) ?? 0;
          return dir * (ca - cb);
        }
        default:
          return 0;
      }
    });
  }, [advertisers, sortKey, sortDir, adCountMap]);

  const SortIcon = ({ col }: { col: typeof sortKey }) => (
    <span className="inline-block ml-1 text-gray-400">
      {sortKey === col ? (sortDir === "asc" ? "\u25B2" : "\u25BC") : "\u25B4\u25BE"}
    </span>
  );

  const matchBadge = (type: string) => {
    switch (type) {
      case "exact": return "bg-green-100 text-green-700";
      case "alias": return "bg-blue-100 text-blue-700";
      case "child": return "bg-purple-100 text-purple-700";
      default: return "bg-gray-100 text-gray-600";
    }
  };

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
              <circle cx="9" cy="7" r="3" />
              <path d="M3 21v-2a4 4 0 014-4h4a4 4 0 014 4v2" />
              <circle cx="17" cy="8" r="2" />
              <path d="M21 21v-1a3 3 0 00-2-2.8" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">광고주</h1>
            <p className="text-sm text-gray-500">등록된 광고주 목록 및 활동 현황</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <DownloadButton
            url="/api/download/advertiser-list"
            label="전체 CSV"
            icon="csv"
          />
          <ExportDropdown
            csvUrl="/api/export/advertisers"
            xlsxUrl="/api/export/advertisers.xlsx"
            label="광고주 목록 다운로드"
          />
        </div>
      </div>

      {/* 검색 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm" ref={dropdownRef}>
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
            placeholder="광고주명, 브랜드, 별칭으로 검색..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setShowDropdown(true);
            }}
            onFocus={() => debouncedSearch.length >= 1 && setShowDropdown(true)}
            className="w-full pl-10 pr-4 py-2.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-adscope-500/20 focus:border-adscope-500"
          />

          {/* 검색 자동완성 드롭다운 */}
          {showDropdown && searchResults && searchResults.length > 0 && (
            <div className="absolute z-20 left-0 right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
              {searchResults.map((r: AdvertiserSearchResult) => (
                <Link
                  key={r.id}
                  href={`/advertisers/${r.id}`}
                  onClick={() => setShowDropdown(false)}
                  className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {r.name}
                    </p>
                    {r.brand_name && (
                      <p className="text-xs text-gray-500 truncate">{r.brand_name}</p>
                    )}
                  </div>
                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${matchBadge(r.match_type)}`}>
                    {r.match_type === "exact" ? "정확" : r.match_type === "alias" ? "별칭" : "하위"}
                  </span>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            전체 광고주
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {isLoading ? "-" : (advertisers?.length ?? 0).toLocaleString()}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            30일 활성 광고주
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {topAdvertisers?.length ?? "-"}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hidden lg:block">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            30일 총 노출
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {topAdvertisers
              ? topAdvertisers.reduce((s, a) => s + a.ad_count, 0).toLocaleString()
              : "-"}
          </p>
        </div>
      </div>

      {/* 뷰 모드 토글 */}
      <div className="flex items-center gap-2 mb-4">
        <div className="inline-flex rounded-lg border border-gray-200 bg-white shadow-sm p-0.5">
          <button
            onClick={() => setViewMode("list")}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              viewMode === "list"
                ? "bg-adscope-500 text-white shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 inline mr-1 -mt-0.5">
              <path fillRule="evenodd" d="M2 4.75A.75.75 0 012.75 4h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 4.75zm0 10.5a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75a.75.75 0 01-.75-.75zM2 10a.75.75 0 01.75-.75h14.5a.75.75 0 010 1.5H2.75A.75.75 0 012 10z" clipRule="evenodd" />
            </svg>
            리스트
          </button>
          <button
            onClick={() => setViewMode("tree")}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              viewMode === "tree"
                ? "bg-adscope-500 text-white shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <svg viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5 inline mr-1 -mt-0.5">
              <path d="M3.5 2A1.5 1.5 0 002 3.5v3A1.5 1.5 0 003.5 8h1.293l1.5 1.5H3.5A1.5 1.5 0 002 11v3A1.5 1.5 0 003.5 15.5h3A1.5 1.5 0 008 14v-3a1.5 1.5 0 00-1.5-1.5H5.207l-1.5-1.5H6.5A1.5 1.5 0 008 6.5v-3A1.5 1.5 0 006.5 2h-3zM11 3.5A1.5 1.5 0 0112.5 2h4A1.5 1.5 0 0118 3.5v3A1.5 1.5 0 0116.5 8h-4A1.5 1.5 0 0111 6.5v-3zM12.5 11A1.5 1.5 0 0011 12.5v3a1.5 1.5 0 001.5 1.5h4a1.5 1.5 0 001.5-1.5v-3a1.5 1.5 0 00-1.5-1.5h-4z" />
            </svg>
            트리 뷰
          </button>
        </div>
        {viewMode === "tree" && brandTree && (
          <span className="text-xs text-gray-400">
            {(brandTree?.groups || []).length}개 그룹 / {(brandTree?.independents || []).length}개 독립 광고주
          </span>
        )}
      </div>

      {/* 리스트 뷰 */}
      {viewMode === "list" && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort("name")}>
                    광고주명<SortIcon col="name" />
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort("brand")}>
                    브랜드<SortIcon col="brand" />
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort("website")}>
                    웹사이트<SortIcon col="website" />
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer select-none hover:text-gray-700" onClick={() => handleSort("ad_count")}>
                    30일 노출<SortIcon col="ad_count" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  Array.from({ length: 10 }).map((_, i) => (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-3 px-4"><div className="skeleton h-4 w-32" /></td>
                      <td className="py-3 px-4"><div className="skeleton h-4 w-20" /></td>
                      <td className="py-3 px-4"><div className="skeleton h-4 w-40" /></td>
                      <td className="py-3 px-4"><div className="skeleton h-4 w-12 ml-auto" /></td>
                    </tr>
                  ))
                ) : sortedAdvertisers.length > 0 ? (
                  sortedAdvertisers.map((adv) => (
                    <tr
                      key={adv.id}
                      className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <StarButton
                            advertiserId={adv.id}
                            isFavorite={favoriteIds.has(adv.id)}
                            onToggle={handleToggleFavorite}
                          />
                          <Link
                            href={adv.id ? `/advertisers/${adv.id}` : "#"}
                            className="font-medium text-adscope-600 hover:text-adscope-800 hover:underline"
                          >
                            {adv.name}
                          </Link>
                        </div>
                      </td>
                      <td className="py-3 px-4 text-gray-600">
                        {adv.brand_name ?? "-"}
                      </td>
                      <td className="py-3 px-4">
                        {adv.website ? (
                          <span className="text-adscope-600 text-xs truncate block max-w-[200px]">
                            {adv.website}
                          </span>
                        ) : (
                          <span className="text-gray-300">-</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right tabular-nums">
                        {adCountMap.has(adv.name) ? (
                          <span className="font-medium text-gray-900">
                            {(adCountMap.get(adv.name) ?? 0).toLocaleString()}회
                          </span>
                        ) : (
                          <span className="text-gray-300">-</span>
                        )}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} className="py-12 text-center text-gray-400 text-sm">
                      {search ? `"${search}" 검색 결과가 없습니다` : "등록된 광고주가 없습니다"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 트리 뷰 */}
      {viewMode === "tree" && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          {treeLoading ? (
            <div className="p-8 text-center">
              <div className="inline-block w-6 h-6 border-2 border-adscope-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-400 mt-2">Loading...</p>
            </div>
          ) : brandTree ? (
            <div>
              {/* 헤더 */}
              <div className="bg-gray-50 border-b border-gray-200 flex items-center py-3 px-4">
                <span className="text-xs font-semibold text-gray-500 uppercase flex-1">
                  광고주 / 그룹
                </span>
                <span className="text-xs font-semibold text-gray-500 uppercase w-20 text-right">
                  90일 광고
                </span>
              </div>

              {/* 그룹 섹션 */}
              {(brandTree?.groups || []).length > 0 && (
                <div>
                  <div className="bg-indigo-50/50 px-4 py-2 border-b border-gray-100">
                    <span className="text-[11px] font-semibold text-indigo-600 uppercase tracking-wider">
                      Groups ({(brandTree?.groups || []).length})
                    </span>
                  </div>
                  {(brandTree?.groups || []).map((group) => (
                    <GroupAccordion key={group.id} group={group} />
                  ))}
                </div>
              )}

              {/* 독립 광고주 섹션 */}
              {(brandTree?.independents || []).length > 0 && (
                <div>
                  <div className="bg-gray-50/80 px-4 py-2 border-b border-t border-gray-100">
                    <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                      독립 광고주 ({(brandTree?.independents || []).length})
                    </span>
                  </div>
                  {(brandTree?.independents || []).map((adv) => (
                    <TreeNode key={adv.id} node={adv} depth={0} />
                  ))}
                </div>
              )}

              {(brandTree?.groups || []).length === 0 && (brandTree?.independents || []).length === 0 && (
                <p className="py-12 text-center text-gray-400 text-sm">
                  등록된 광고주가 없습니다
                </p>
              )}
            </div>
          ) : (
            <p className="py-12 text-center text-gray-400 text-sm">
              데이터를 불러올 수 없습니다
            </p>
          )}
        </div>
      )}
    </div>
  );
}
