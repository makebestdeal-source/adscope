"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatChannel, formatSpend } from "@/lib/constants";
import { SpendChart } from "@/components/SpendChart";
import { PeriodSelector } from "@/components/PeriodSelector";
import { useState } from "react";

export default function SpendPage() {
  const [days, setDays] = useState(30);

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["spendSummary", days],
    queryFn: () => api.getSpendSummary(days),
  });

  const { data: byAdvertiser, isLoading: byAdvLoading } = useQuery({
    queryKey: ["spendByAdvertiser", days],
    queryFn: () => api.getSpendByAdvertiser(days, 20),
  });

  const totalSpend = summary?.reduce((s, c) => s + c.total_spend, 0) ?? 0;
  const avgConfidence =
    summary && summary.length > 0
      ? summary.reduce((s, c) => s + c.avg_confidence, 0) / summary.length
      : 0;

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      <div className="flex items-start justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-500 flex items-center justify-center shadow-lg shadow-emerald-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-5 h-5">
              <rect x="2" y="6" width="20" height="12" rx="2" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">광고비 분석</h1>
            <p className="text-sm text-gray-500">
              채널별·광고주별 추정 광고비
            </p>
          </div>
        </div>
        <PeriodSelector days={days} onDaysChange={setDays} dataStartDate="2026-02-15" showCustom={false} />
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <div className="rounded-xl border border-gray-100 p-5 shadow-sm kpi-gradient-indigo card-hover">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            총 추정 광고비
          </p>
          {summaryLoading ? (
            <div className="skeleton h-8 w-28 mt-2" />
          ) : (
            <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
              {formatSpend(totalSpend)}
            </p>
          )}
        </div>
        <div className="rounded-xl border border-gray-100 p-5 shadow-sm kpi-gradient-green card-hover">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            데이터 포인트
          </p>
          {summaryLoading ? (
            <div className="skeleton h-8 w-20 mt-2" />
          ) : (
            <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
              {summary?.reduce((s, c) => s + c.data_points, 0).toLocaleString() ?? 0}
            </p>
          )}
        </div>
        <div className="rounded-xl border border-gray-100 p-5 shadow-sm kpi-gradient-amber card-hover hidden lg:block">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            평균 신뢰도
          </p>
          {summaryLoading ? (
            <div className="skeleton h-8 w-16 mt-2" />
          ) : (
            <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
              {(avgConfidence * 100).toFixed(0)}%
            </p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 채널별 광고비 차트 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-5">
            채널별 추정 광고비
          </h2>
          <SpendChart data={summary ?? []} />
        </div>

        {/* 채널별 상세 테이블 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-5">
            채널별 상세
          </h2>
          {summaryLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-10 w-full rounded-lg" />
              ))}
            </div>
          ) : summary && summary.length > 0 ? (
            <div className="space-y-3">
              {summary.map((ch) => (
                <div
                  key={ch.channel}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {formatChannel(ch.channel)}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      데이터 {ch.data_points}건 · 신뢰도{" "}
                      {(ch.avg_confidence * 100).toFixed(0)}%
                    </p>
                  </div>
                  <p className="text-sm font-bold text-gray-900 tabular-nums">
                    {formatSpend(ch.total_spend)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-8">
              광고비 데이터가 없습니다
            </p>
          )}
        </div>
      </div>

      {/* 광고주별 광고비 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mt-6">
        <h2 className="text-base font-semibold text-gray-900 mb-5">
          광고주별 추정 광고비 TOP 20
        </h2>
        {byAdvLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="skeleton h-6 w-6 rounded-full" />
                <div className="skeleton h-4 flex-1" />
                <div className="skeleton h-4 w-20" />
              </div>
            ))}
          </div>
        ) : byAdvertiser && byAdvertiser.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
            {byAdvertiser.map((adv, idx) => {
              const maxSpend = byAdvertiser[0]?.total_spend || 1;
              const pct = (adv.total_spend / maxSpend) * 100;
              return (
                <div
                  key={adv.advertiser}
                  className="flex items-center gap-3 py-2.5 border-b border-gray-50"
                >
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                      idx < 3
                        ? "bg-adscope-100 text-adscope-700"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {idx + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {adv.advertiser}
                    </p>
                    <div className="w-full bg-gray-100 rounded-full h-1.5 mt-1">
                      <div
                        className="bg-adscope-400 h-1.5 rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                  <span className="text-sm font-semibold text-gray-900 tabular-nums flex-shrink-0">
                    {formatSpend(adv.total_spend)}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-gray-400 text-center py-8">
            광고비 데이터가 없습니다
          </p>
        )}
      </div>
    </div>
  );
}

