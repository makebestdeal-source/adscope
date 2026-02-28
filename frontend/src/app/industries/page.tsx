"use client";

import { useQuery } from "@tanstack/react-query";
import { api, IndustryInfo, IndustryLandscape } from "@/lib/api";
import Link from "next/link";

function IndustryCard({ industry }: { industry: IndustryInfo }) {
  const { data: landscape } = useQuery({
    queryKey: ["industryLandscape", industry.id],
    queryFn: () => api.getIndustryLandscapeFull(industry.id, 30),
    staleTime: 5 * 60 * 1000,
  });

  const advertiserCount = landscape?.advertiser_count ?? 0;
  const cpcRange =
    industry.avg_cpc_min != null && industry.avg_cpc_max != null
      ? `${industry.avg_cpc_min.toLocaleString()} ~ ${industry.avg_cpc_max.toLocaleString()}원`
      : "CPC 미등록";

  return (
    <Link href={`/industries/${industry.id}`}>
      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-lg hover:border-adscope-300 hover:-translate-y-1 transition-all duration-300 cursor-pointer group">
        <div className="flex items-start justify-between mb-3">
          <h3 className="text-lg font-semibold text-gray-900 group-hover:text-adscope-600 transition-colors">
            {industry.name}
          </h3>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            className="w-5 h-5 text-gray-300 group-hover:text-adscope-500 transition-colors"
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
            <span className="text-xs text-gray-500">CPC</span>
            <span className="text-sm font-medium text-gray-700">
              {cpcRange}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">광고주 수</span>
            <span className="text-sm font-bold text-adscope-600 tabular-nums">
              {advertiserCount}
            </span>
          </div>
        </div>

        {advertiserCount > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <div className="w-full bg-gray-100 rounded-full h-1.5">
              <div
                className="bg-adscope-500 h-1.5 rounded-full transition-all"
                style={{
                  width: `${Math.min(advertiserCount * 5, 100)}%`,
                }}
              />
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}

export default function IndustriesPage() {
  const { data: industries, isLoading } = useQuery({
    queryKey: ["industries"],
    queryFn: () => api.getIndustries(),
  });

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center shadow-lg shadow-sky-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
            <path d="M2 20L8.5 8 13 16l4-6 5 10" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M2 20h20" strokeLinecap="round" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">업종 분석</h1>
          <p className="text-sm text-gray-500">
            업종별 광고 시장 현황 및 경쟁 구도
          </p>
        </div>
      </div>

      {/* Stats overview */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            전체 업종
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {isLoading ? "-" : (industries?.length ?? 0)}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            CPC 등록 업종
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {isLoading
              ? "-"
              : industries?.filter((i) => i.avg_cpc_min != null).length ?? 0}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hidden lg:block">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            분석 기간
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1">30일</p>
        </div>
      </div>

      {/* Industry grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm"
            >
              <div className="skeleton h-5 w-20 mb-4" />
              <div className="skeleton h-4 w-32 mb-2" />
              <div className="skeleton h-4 w-24" />
            </div>
          ))}
        </div>
      ) : industries && industries.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {industries.map((ind) => (
            <IndustryCard key={ind.id} industry={ind} />
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
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <p className="text-sm text-gray-400">등록된 업종이 없습니다</p>
        </div>
      )}
    </div>
  );
}
