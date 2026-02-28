"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  api,
  ProductCategoryTree,
  ProductCategoryDetail,
  ProductCategoryAdvertiser,
} from "@/lib/api";
import { formatSpend } from "@/lib/constants";

// 대분류 아이콘 매핑
const CATEGORY_ICONS: Record<string, string> = {
  "가전/전자": "M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z",
  "모바일/IT": "M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z",
  "소프트웨어/SaaS": "M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4",
  "게임": "M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z",
  "앱서비스": "M12 18h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z",
  "통신/인터넷": "M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.858 15.355-5.858 21.213 0",
  "뷰티/화장품": "M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01",
  "패션": "M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z",
  "식품/음료": "M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 100 4 2 2 0 000-4z",
  "금융서비스": "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z",
  "자동차": "M13 10V3L4 14h7v7l9-11h-7z",
  "여행/레저": "M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z",
  "교육": "M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14zm-4 6v-7.5l4-2.222",
  "생활서비스": "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6",
  "엔터테인먼트": "M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z",
  "건강/의료": "M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z",
  "부동산": "M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4",
  "유통/쇼핑": "M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z",
};

function CategoryIcon({ name }: { name: string }) {
  const path = CATEGORY_ICONS[name] || "M4 6h16M4 10h16M4 14h16M4 18h16";
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="w-8 h-8"
    >
      <path d={path} />
    </svg>
  );
}

function CategoryCard({
  category,
  onClick,
}: {
  category: ProductCategoryTree;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-lg hover:border-adscope-300 hover:-translate-y-1 transition-all duration-300 cursor-pointer group text-left w-full"
    >
      <div className="flex items-start gap-3 mb-3">
        <div className="p-2 rounded-lg bg-adscope-50 text-adscope-600 group-hover:bg-adscope-100 transition-colors">
          <CategoryIcon name={category.name} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-lg font-semibold text-gray-900 group-hover:text-adscope-600 transition-colors">
            {category.name}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {category.children.length}개 소분류
          </p>
        </div>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="w-5 h-5 text-gray-300 group-hover:text-adscope-500 transition-colors flex-shrink-0"
        >
          <path
            d="M9 18l6-6-6-6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">광고주</span>
          <span className="text-sm font-bold text-adscope-600 tabular-nums">
            {category.advertiser_count}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">광고 수</span>
          <span className="text-sm font-medium text-gray-700 tabular-nums">
            {category.ad_count.toLocaleString()}
          </span>
        </div>
      </div>
      {category.ad_count > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <div className="w-full bg-gray-100 rounded-full h-1.5">
            <div
              className="bg-adscope-500 h-1.5 rounded-full transition-all"
              style={{
                width: `${Math.min(category.ad_count / 5, 100)}%`,
              }}
            />
          </div>
        </div>
      )}
    </button>
  );
}

function SubcategoryList({
  detail,
  onSubClick,
}: {
  detail: ProductCategoryDetail;
  onSubClick: (id: number) => void;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="font-semibold text-gray-900">소분류</h3>
      </div>
      <div className="divide-y divide-gray-50">
        {detail.children.length > 0 ? (
          detail.children.map((child) => (
            <button
              key={child.id}
              onClick={() => onSubClick(child.id)}
              className="w-full px-5 py-3 flex items-center justify-between hover:bg-gray-50 transition-colors text-left"
            >
              <span className="text-sm font-medium text-gray-700">
                {child.name}
              </span>
              <div className="flex items-center gap-4">
                <span className="text-xs text-gray-400">
                  {child.advertiser_count} 광고주
                </span>
                <span className="text-xs font-medium text-adscope-600 tabular-nums">
                  {child.ad_count} 광고
                </span>
              </div>
            </button>
          ))
        ) : (
          <div className="px-5 py-6 text-center text-sm text-gray-400">
            소분류 없음
          </div>
        )}
      </div>
    </div>
  );
}

function AdvertiserRankTable({
  advertisers,
}: {
  advertisers: ProductCategoryAdvertiser[];
}) {
  if (!advertisers.length) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center shadow-sm">
        <p className="text-sm text-gray-400">광고주 데이터 없음</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="font-semibold text-gray-900">광고주 랭킹</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wider">
              <th className="px-4 py-3 text-left font-medium">#</th>
              <th className="px-4 py-3 text-left font-medium">광고주</th>
              <th className="px-4 py-3 text-right font-medium">광고 수</th>
              <th className="px-4 py-3 text-right font-medium">추정 광고비</th>
              <th className="px-4 py-3 text-left font-medium">채널</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {advertisers.map((adv) => (
              <tr key={adv.advertiser_id} className="hover:bg-gray-50">
                <td className="px-4 py-3 text-gray-400 tabular-nums">
                  {adv.rank}
                </td>
                <td className="px-4 py-3">
                  <div>
                    <span className="font-medium text-gray-900">
                      {adv.advertiser_name}
                    </span>
                    {adv.brand_name && (
                      <span className="text-xs text-gray-400 ml-1">
                        ({adv.brand_name})
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-medium text-gray-700">
                  {adv.ad_count.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-gray-600">
                  {adv.est_spend > 0
                    ? formatSpend(adv.est_spend)
                    : "-"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {adv.channels.map((ch) => (
                      <span
                        key={ch}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500"
                      >
                        {ch}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SpendBarChart({
  advertisers,
}: {
  advertisers: ProductCategoryAdvertiser[];
}) {
  const withSpend = advertisers.filter((a) => a.est_spend > 0).slice(0, 10);
  if (!withSpend.length) return null;
  const maxSpend = Math.max(...withSpend.map((a) => a.est_spend));

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-4 border-b border-gray-100">
        <h3 className="font-semibold text-gray-900">광고비 분포 (Top 10)</h3>
      </div>
      <div className="p-5 space-y-3">
        {withSpend.map((adv) => (
          <div key={adv.advertiser_id}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-700 truncate max-w-[200px]">
                {adv.advertiser_name}
              </span>
              <span className="text-xs text-gray-500 tabular-nums">
                {formatSpend(adv.est_spend)}
              </span>
            </div>
            <div className="w-full bg-gray-100 rounded-full h-2">
              <div
                className="bg-adscope-500 h-2 rounded-full transition-all"
                style={{
                  width: `${(adv.est_spend / maxSpend) * 100}%`,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ProductsPage() {
  const [selectedCategoryId, setSelectedCategoryId] = useState<number | null>(
    null
  );
  const [days] = useState(30);

  const { data: categories, isLoading: loadingCategories } = useQuery({
    queryKey: ["productCategories", days],
    queryFn: () => api.getProductCategories(days),
  });

  const { data: detail, isLoading: loadingDetail } = useQuery({
    queryKey: ["productCategoryDetail", selectedCategoryId, days],
    queryFn: () => api.getProductCategoryDetail(selectedCategoryId!, days),
    enabled: !!selectedCategoryId,
  });

  const { data: advertisers, isLoading: loadingAdvertisers } = useQuery({
    queryKey: ["productCategoryAdvertisers", selectedCategoryId, days],
    queryFn: () =>
      api.getProductCategoryAdvertisers(selectedCategoryId!, days, 50),
    enabled: !!selectedCategoryId,
  });

  const selectedCategory = categories?.find(
    (c) => c.id === selectedCategoryId
  );

  // Check if selectedCategoryId is a subcategory
  const parentOfSub = categories?.find((c) =>
    c.children.some((ch) => ch.id === selectedCategoryId)
  );

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-1">
          {selectedCategoryId && (
            <button
              onClick={() => setSelectedCategoryId(null)}
              className="text-adscope-600 hover:text-adscope-800 transition-colors"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="w-5 h-5"
              >
                <path
                  d="M15 18l-6-6 6-6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          )}
          <h1 className="text-2xl font-bold text-gray-900">
            {selectedCategoryId
              ? parentOfSub
                ? `${parentOfSub.name} > ${
                    parentOfSub.children.find(
                      (c) => c.id === selectedCategoryId
                    )?.name || ""
                  }`
                : selectedCategory?.name || ""
              : "제품/서비스 분석"}
          </h1>
        </div>
        <p className="text-sm text-gray-500 mt-1">
          {selectedCategoryId
            ? "카테고리별 광고주 랭킹 및 광고비 분석"
            : "제품/서비스 카테고리별 광고 현황"}
        </p>
      </div>

      {/* Stats */}
      {!selectedCategoryId && (
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              대분류
            </p>
            <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
              {loadingCategories ? "-" : categories?.length ?? 0}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              전체 소분류
            </p>
            <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
              {loadingCategories
                ? "-"
                : categories?.reduce(
                    (sum, c) => sum + c.children.length,
                    0
                  ) ?? 0}
            </p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hidden lg:block">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              분석 기간
            </p>
            <p className="text-2xl font-bold text-gray-900 mt-1">
              {days}일
            </p>
          </div>
        </div>
      )}

      {/* Main Content */}
      {!selectedCategoryId ? (
        // Category Grid
        loadingCategories ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm"
              >
                <div className="skeleton h-8 w-8 mb-3 rounded-lg" />
                <div className="skeleton h-5 w-24 mb-2" />
                <div className="skeleton h-4 w-16 mb-4" />
                <div className="skeleton h-4 w-32" />
              </div>
            ))}
          </div>
        ) : categories && categories.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {categories.map((cat) => (
              <CategoryCard
                key={cat.id}
                category={cat}
                onClick={() => setSelectedCategoryId(cat.id)}
              />
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="w-12 h-12 text-gray-300 mx-auto mb-3"
            >
              <path
                d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <p className="text-sm text-gray-400">
              카테고리를 시드해주세요
            </p>
            <p className="text-xs text-gray-300 mt-1">
              python -m scripts.seed_product_categories
            </p>
          </div>
        )
      ) : (
        // Category Detail View
        <div className="space-y-6">
          {/* Detail Stats */}
          {detail && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  광고주
                </p>
                <p className="text-2xl font-bold text-adscope-600 mt-1 tabular-nums">
                  {detail.advertiser_count}
                </p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  광고 수
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                  {detail.ad_count.toLocaleString()}
                </p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  추정 광고비
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                  {detail.est_spend > 0
                    ? formatSpend(detail.est_spend)
                    : "-"}
                </p>
              </div>
              <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                  소분류
                </p>
                <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
                  {detail.children.length}
                </p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Subcategories + Spend Chart */}
            <div className="space-y-6">
              {loadingDetail ? (
                <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                  <div className="skeleton h-5 w-20 mb-4" />
                  <div className="space-y-3">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <div key={i} className="skeleton h-8 w-full" />
                    ))}
                  </div>
                </div>
              ) : detail ? (
                <>
                  <SubcategoryList
                    detail={detail}
                    onSubClick={(id) => setSelectedCategoryId(id)}
                  />
                  {advertisers && <SpendBarChart advertisers={advertisers} />}
                </>
              ) : null}
            </div>

            {/* Right: Advertiser Ranking */}
            <div className="lg:col-span-2">
              {loadingAdvertisers ? (
                <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
                  <div className="skeleton h-5 w-24 mb-4" />
                  <div className="space-y-3">
                    {Array.from({ length: 8 }).map((_, i) => (
                      <div key={i} className="skeleton h-10 w-full" />
                    ))}
                  </div>
                </div>
              ) : advertisers ? (
                <AdvertiserRankTable advertisers={advertisers} />
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
