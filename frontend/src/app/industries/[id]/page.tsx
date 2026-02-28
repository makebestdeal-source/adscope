"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState, useMemo } from "react";
import Link from "next/link";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { formatSpend, formatChannel } from "@/lib/constants";
import { api, IndustryLandscape, IndustryMarketMap, LandscapeAdvertiser } from "@/lib/api";

// ── Color palette for SOV pie chart ──

const SOV_COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#a855f7",
  "#ec4899",
  "#f43f5e",
  "#f97316",
  "#eab308",
  "#22c55e",
  "#14b8a6",
  "#3b82f6",
  "#6b7280",
];

type SortKey = "sov" | "spend" | "revenue" | "ads" | "name";
type SortDir = "asc" | "desc";

export default function IndustryDetailPage() {
  const params = useParams();
  const industryId = Number(params.id);

  const [days, setDays] = useState(30);
  const [sortKey, setSortKey] = useState<SortKey>("sov");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const { data: landscape, isLoading } = useQuery({
    queryKey: ["industryLandscape", industryId, days],
    queryFn: () => api.getIndustryLandscapeFull(industryId, days),
    enabled: !!industryId,
  });

  const { data: marketMap } = useQuery({
    queryKey: ["industryMarketMap", industryId, days],
    queryFn: () => api.getIndustryMarketMap(industryId, days),
    enabled: !!industryId,
  });

  // Sort advertisers
  const sortedAdvertisers = useMemo(() => {
    if (!landscape?.advertisers) return [];
    const list = [...landscape.advertisers];
    list.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "sov":
          cmp = a.sov_percentage - b.sov_percentage;
          break;
        case "spend":
          cmp = a.est_ad_spend - b.est_ad_spend;
          break;
        case "revenue":
          cmp = (a.annual_revenue ?? 0) - (b.annual_revenue ?? 0);
          break;
        case "ads":
          cmp = a.ad_count - b.ad_count;
          break;
        case "name":
          cmp = a.name.localeCompare(b.name, "ko");
          break;
      }
      return sortDir === "desc" ? -cmp : cmp;
    });
    return list;
  }, [landscape, sortKey, sortDir]);

  // SOV pie data (top 10 + others)
  const sovPieData = useMemo(() => {
    if (!landscape?.advertisers) return [];
    const sorted = [...landscape.advertisers].sort(
      (a, b) => b.sov_percentage - a.sov_percentage
    );
    const top = sorted.slice(0, 10);
    const othersSum = sorted
      .slice(10)
      .reduce((s, a) => s + a.sov_percentage, 0);
    const items = top.map((a) => ({
      name: a.name,
      value: Math.round(a.sov_percentage * 100) / 100,
    }));
    if (othersSum > 0) {
      items.push({ name: "기타", value: Math.round(othersSum * 100) / 100 });
    }
    return items;
  }, [landscape]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sortArrow = (key: SortKey) =>
    sortKey === key ? (sortDir === "desc" ? " \u25BC" : " \u25B2") : "";

  if (isLoading) {
    return (
      <div className="p-6 lg:p-8 max-w-7xl">
        <div className="skeleton h-8 w-40 mb-2" />
        <div className="skeleton h-4 w-64 mb-8" />
        <div className="grid grid-cols-3 gap-4 mb-6">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-white rounded-xl border border-gray-200 p-5"
            >
              <div className="skeleton h-4 w-20 mb-2" />
              <div className="skeleton h-8 w-28" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!landscape) {
    return (
      <div className="p-6 lg:p-8 max-w-7xl text-center py-20">
        <p className="text-gray-400">업종 데이터를 찾을 수 없습니다</p>
        <Link
          href="/industries"
          className="text-adscope-600 text-sm mt-2 inline-block hover:underline"
        >
          업종 목록으로 돌아가기
        </Link>
      </div>
    );
  }

  const industry = landscape.industry;

  return (
    <div className="p-6 lg:p-8 max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-1">
          <Link href="/industries" className="hover:text-adscope-600">
            업종 분석
          </Link>
          <span>/</span>
          <span className="text-gray-900">{industry.name}</span>
        </div>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">{industry.name}</h1>
          <div className="flex gap-2">
            {[7, 14, 30, 90].map((d) => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  days === d
                    ? "bg-adscope-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {d}일
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Overview cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            광고주 수
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {landscape.advertiser_count}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            CPC
          </p>
          <p className="text-lg font-bold text-gray-900 mt-1">
            {industry.avg_cpc_min != null && industry.avg_cpc_max != null
              ? `${industry.avg_cpc_min.toLocaleString()} ~ ${industry.avg_cpc_max.toLocaleString()}원`
              : "미등록"}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            추정 광고비 합계
          </p>
          <p className="text-lg font-bold text-gray-900 mt-1">
            {landscape.total_market_size
              ? formatSpend(landscape.total_market_size)
              : "-"}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            총 광고 수
          </p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {(landscape.advertisers ?? [])
              .reduce((s, a) => s + a.ad_count, 0)
              .toLocaleString()}
          </p>
        </div>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* Market Map (Scatter) */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            Market Map
          </h2>
          <p className="text-xs text-gray-400 mb-3">
            X: 매출 / Y: 추정 광고비 / 크기: SOV
          </p>
          {marketMap && marketMap.points.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="x"
                  type="number"
                  name="Revenue"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v) =>
                    v >= 1_000_000_000_000
                      ? `${(v / 1_000_000_000_000).toFixed(0)}조`
                      : v >= 100_000_000
                        ? `${(v / 100_000_000).toFixed(0)}억`
                        : v.toLocaleString()
                  }
                />
                <YAxis
                  dataKey="y"
                  type="number"
                  name="Ad Spend"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(v) =>
                    v >= 100_000_000
                      ? `${(v / 100_000_000).toFixed(0)}억`
                      : v >= 10_000
                        ? `${(v / 10_000).toFixed(0)}만`
                        : v.toLocaleString()
                  }
                />
                <ZAxis dataKey="size" range={[40, 400]} name="SOV" />
                <Tooltip
                  content={({ payload }) => {
                    if (!payload || !payload.length) return null;
                    const d = payload[0].payload;
                    return (
                      <div className="bg-white border border-gray-200 rounded-lg p-3 shadow-lg text-xs">
                        <p className="font-semibold text-gray-900">{d.name}</p>
                        <p className="text-gray-600">
                          매출: {d.x > 0 ? formatSpend(d.x) : "N/A"}
                        </p>
                        <p className="text-gray-600">
                          광고비: {formatSpend(d.y)}
                        </p>
                        <p className="text-gray-600">SOV: {d.size.toFixed(1)}%</p>
                      </div>
                    );
                  }}
                />
                <Scatter
                  data={marketMap.points}
                  fill="#6366f1"
                  fillOpacity={0.7}
                />
              </ScatterChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[300px] text-gray-400 text-sm">
              데이터가 부족합니다
            </div>
          )}
        </div>

        {/* SOV Pie Chart */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            광고 점유율 (SOV)
          </h2>
          {sovPieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={sovPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={95}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, percent }) =>
                    percent > 0.05 ? `${name} ${(percent * 100).toFixed(0)}%` : ""
                  }
                  labelLine={{ strokeWidth: 1 }}
                >
                  {sovPieData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={SOV_COLORS[index % SOV_COLORS.length]}
                    />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(value: number, name: string) => [
                    `${value.toFixed(1)}%`,
                    name,
                  ]}
                  contentStyle={{
                    borderRadius: 8,
                    border: "1px solid #e5e7eb",
                    fontSize: 12,
                  }}
                />
                <Legend
                  layout="vertical"
                  verticalAlign="middle"
                  align="right"
                  wrapperStyle={{ fontSize: 11 }}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[300px] text-gray-400 text-sm">
              광고 데이터가 없습니다
            </div>
          )}
        </div>
      </div>

      {/* Advertiser table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-700">
            광고주 상세 ({landscape.advertiser_count})
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th
                  className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer hover:text-gray-700 select-none"
                  onClick={() => handleSort("name")}
                >
                  광고주{sortArrow("name")}
                </th>
                <th
                  className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer hover:text-gray-700 select-none"
                  onClick={() => handleSort("sov")}
                >
                  SOV{sortArrow("sov")}
                </th>
                <th
                  className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer hover:text-gray-700 select-none"
                  onClick={() => handleSort("ads")}
                >
                  광고 수{sortArrow("ads")}
                </th>
                <th
                  className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer hover:text-gray-700 select-none"
                  onClick={() => handleSort("spend")}
                >
                  추정 광고비{sortArrow("spend")}
                </th>
                <th
                  className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase cursor-pointer hover:text-gray-700 select-none"
                  onClick={() => handleSort("revenue")}
                >
                  매출{sortArrow("revenue")}
                </th>
                <th className="text-center py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                  채널
                </th>
                <th className="text-center py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                  상장
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedAdvertisers.length === 0 ? (
                <tr>
                  <td
                    colSpan={7}
                    className="py-12 text-center text-gray-400 text-sm"
                  >
                    이 업종에 등록된 광고주가 없습니다
                  </td>
                </tr>
              ) : (
                sortedAdvertisers.map((adv) => (
                  <tr
                    key={adv.id}
                    className="border-b border-gray-50 hover:bg-gray-50 transition-colors"
                  >
                    <td className="py-3 px-4">
                      <Link
                        href={`/advertisers/${adv.id}`}
                        className="font-medium text-adscope-600 hover:text-adscope-800 hover:underline"
                      >
                        {adv.name}
                      </Link>
                      {adv.brand_name && adv.brand_name !== adv.name && (
                        <p className="text-xs text-gray-400 mt-0.5">
                          {adv.brand_name}
                        </p>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 bg-gray-100 rounded-full h-1.5">
                          <div
                            className="bg-adscope-500 h-1.5 rounded-full"
                            style={{
                              width: `${Math.min(adv.sov_percentage, 100)}%`,
                            }}
                          />
                        </div>
                        <span className="font-medium text-gray-900 w-14 text-right">
                          {adv.sov_percentage.toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums font-medium text-gray-700">
                      {adv.ad_count.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums">
                      {adv.est_ad_spend > 0
                        ? formatSpend(adv.est_ad_spend)
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-right tabular-nums text-gray-600">
                      {adv.annual_revenue
                        ? formatSpend(adv.annual_revenue)
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className="text-xs text-gray-500 tabular-nums">
                        {adv.channel_count}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      {adv.is_public ? (
                        <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium rounded bg-blue-50 text-blue-700">
                          상장
                        </span>
                      ) : (
                        <span className="text-gray-300">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
