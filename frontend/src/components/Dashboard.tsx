"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatChannel as formatChannelLabel } from "@/lib/constants";
import { DownloadButton } from "./DownloadButtons";
import { AdTimeline } from "./AdTimeline";
import { DailyTrendChart } from "./DailyTrendChart";
import { ChannelDonutChart } from "./ChannelDonutChart";
import { SpendChart } from "./SpendChart";

const CHANNEL_COLORS: Record<string, string> = {
  naver_search: "bg-green-500",
  naver_da: "bg-emerald-500",
  youtube_ads: "bg-red-500",
  youtube_surf: "bg-red-400",
  google_gdn: "bg-sky-500",
  kakao_da: "bg-yellow-500",
  facebook: "bg-blue-500",
  facebook_contact: "bg-blue-400",
  instagram: "bg-pink-500",
};

/** KST ISO 문자열 -> "N분 전" / "N시간 전" / "N일 전" 형식 */
function timeAgo(isoKst: string | null | undefined): string {
  if (!isoKst) return "-";
  try {
    const d = new Date(isoKst);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime() + 9 * 60 * 60 * 1000; // KST 보정
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "방금 전";
    if (mins < 60) return `${mins}분 전`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}시간 전`;
    const days = Math.floor(hours / 24);
    return `${days}일 전`;
  } catch {
    return "-";
  }
}

/** KST ISO 문자열 -> "2024.02.17 14:30" 형식 */
function formatKSTShort(isoKst: string | null | undefined): string {
  if (!isoKst) return "-";
  try {
    const d = new Date(isoKst);
    return d.toLocaleString("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "-";
  }
}

export function Dashboard() {
  const queryClient = useQueryClient();

  const { data: stats, isLoading: statsLoading, dataUpdatedAt } = useQuery({
    queryKey: ["dailyStats"],
    queryFn: () => api.getDailyStats(),
    refetchInterval: 60_000, // 60초마다 자동 새로고침
  });

  const { data: topAdvertisers, isLoading: topLoading } = useQuery({
    queryKey: ["topAdvertisers"],
    queryFn: () => api.getTopAdvertisers(30, 30),
    refetchInterval: 60_000,
  });

  const { data: dailyTrend, isLoading: trendLoading } = useQuery({
    queryKey: ["dailyTrend"],
    queryFn: () => api.getDailyTrend(30),
    refetchInterval: 60_000,
  });

  const { data: spendSummary, isLoading: spendLoading } = useQuery({
    queryKey: ["spendSummary"],
    queryFn: () => api.getSpendSummary(30),
    refetchInterval: 120_000,
  });

  const totalAdvertisers = topAdvertisers?.length ?? 0;

  // 최근 수집 시각 (KST ISO string from API)
  const latestCrawlAt = stats?.latest_crawl_at ?? null;
  const todayTotalAds = stats?.today_total_ads ?? 0;

  return (
    <div className="space-y-6 animate-fade-in">
      {/* 수집 현황 상태 바 */}
      <CrawlStatusBar
        latestCrawlAt={latestCrawlAt}
        todayTotalAds={todayTotalAds}
        loading={statsLoading}
        dataUpdatedAt={dataUpdatedAt}
        onRefresh={() => {
          queryClient.invalidateQueries({ queryKey: ["dailyStats"] });
          queryClient.invalidateQueries({ queryKey: ["dailyTrend"] });
          queryClient.invalidateQueries({ queryKey: ["topAdvertisers"] });
          queryClient.invalidateQueries({ queryKey: ["spendSummary"] });
        }}
      />

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <KpiCard
          title="실접촉 광고"
          value={stats?.total_contacts ?? 0}
          subtitle={
            latestCrawlAt
              ? `최근: ${formatKSTShort(latestCrawlAt)}`
              : stats?.date
                ? `${stats.date} 기준`
                : undefined
          }
          loading={statsLoading}
          accent="border-l-adscope-500"
        />
        <KpiCard
          title="카탈로그"
          value={stats?.total_catalog ?? 0}
          subtitle="투명성 센터/광고 라이브러리"
          loading={statsLoading}
          accent="border-l-indigo-400"
        />
        <KpiCard
          title="전체 광고"
          value={stats?.total_ads ?? 0}
          subtitle={`${(stats?.total_snapshots ?? 0).toLocaleString()}개 스냅샷`}
          loading={statsLoading}
          accent="border-l-green-500"
        />
        <KpiCard
          title="활성 채널"
          value={Object.keys(stats?.by_channel ?? {}).length}
          loading={statsLoading}
          accent="border-l-amber-500"
        />
        <KpiCard
          title="상위 광고주"
          value={totalAdvertisers}
          subtitle="30일 기준"
          loading={topLoading}
          accent="border-l-rose-500"
        />
      </div>

      {/* Daily Trend Chart (full width) */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm card-hover">
        <h2 className="section-title">일별 수집 트렌드 (14일)</h2>
        {trendLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="skeleton h-64 w-full rounded-lg" />
          </div>
        ) : (
          <DailyTrendChart data={dailyTrend ?? []} />
        )}
      </div>

      {/* Charts row: Channel Donut + Channel Bar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Channel Donut Chart */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm card-hover">
          <h2 className="section-title">
            채널별 수집 비율
          </h2>
          {statsLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="skeleton h-48 w-48 rounded-full" />
            </div>
          ) : (
            <ChannelDonutChart data={stats?.by_channel ?? {}} />
          )}
        </div>

        {/* Channel Bar (existing) */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm card-hover">
          <h2 className="section-title">
            채널별 수집 현황
          </h2>
          {stats?.by_channel && Object.keys(stats.by_channel).length > 0 ? (
            <div className="space-y-4">
              {Object.entries(stats.by_channel).map(([channel, count]) => {
                const vals = Object.values(stats.by_channel); const max = vals.length > 0 ? Math.max(...vals) : 1;
                const pct = max > 0 ? (count / max) * 100 : 0;
                return (
                  <div key={channel}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm text-gray-700 font-medium">
                        {formatChannelLabel(channel)}
                      </span>
                      <span className="text-sm font-semibold text-gray-900">
                        {count.toLocaleString()}
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2.5">
                      <div
                        className={`h-2.5 rounded-full transition-all ${CHANNEL_COLORS[channel] ?? "bg-adscope-500"}`}
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : statsLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i}>
                  <div className="skeleton h-4 w-24 mb-2" />
                  <div className="skeleton h-2.5 w-full" />
                </div>
              ))}
            </div>
          ) : (
            <EmptyState text="수집된 채널 데이터가 없습니다" />
          )}
        </div>
      </div>

      {/* Contact vs Catalog breakdown */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm card-hover">
        <h2 className="text-base font-semibold text-gray-900 mb-5">
          접촉 채널별 광고 수집 현황
        </h2>
        {stats?.contact_channels && Object.keys(stats.contact_channels).length > 0 ? (
          <div className="space-y-4">
            {Object.entries(stats.contact_channels)
              .sort(([, a], [, b]) => b - a)
              .map(([channel, count]) => {
                const vals = Object.values(stats.contact_channels); const max = vals.length > 0 ? Math.max(...vals) : 1;
                const pct = max > 0 ? (count / max) * 100 : 0;
                return (
                  <div key={channel}>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm text-gray-700 font-medium">
                        {formatChannelLabel(channel)}
                      </span>
                      <span className="text-sm font-semibold text-gray-900">
                        {count.toLocaleString()}건
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-3">
                      <div
                        className={`h-3 rounded-full transition-all ${CHANNEL_COLORS[channel] ?? "bg-adscope-500"}`}
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            <div className="pt-2 border-t border-gray-100 flex items-center justify-between">
              <span className="text-xs text-gray-500">접촉 광고 합계</span>
              <span className="text-sm font-bold text-adscope-600">
                {Object.values(stats.contact_channels).reduce((a, b) => a + b, 0).toLocaleString()}건
              </span>
            </div>
          </div>
        ) : statsLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i}>
                <div className="skeleton h-4 w-24 mb-2" />
                <div className="skeleton h-3 w-full" />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState text="접촉 광고 데이터가 없습니다" />
        )}
      </div>

      {/* Spend Chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm card-hover">
        <h2 className="text-base font-semibold text-gray-900 mb-5">
          채널별 추정 광고비 (30일)
        </h2>
        {spendLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="skeleton h-64 w-full rounded-lg" />
          </div>
        ) : (
          <SpendChart data={spendSummary ?? []} />
        )}
      </div>

      {/* Bottom: Advertiser Ranking + Timeline */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Advertisers */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm card-hover">
          <div className="flex items-center justify-between mb-4">
            <h2 className="section-title !mb-0">
              광고 노출 TOP 10 (7일)
            </h2>
            <DownloadButton
              url="/api/download/advertiser-list"
              label="광고주 CSV"
              icon="csv"
            />
          </div>
          {topLoading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="skeleton h-6 w-6 rounded-full" />
                  <div className="skeleton h-4 flex-1" />
                  <div className="skeleton h-4 w-12" />
                </div>
              ))}
            </div>
          ) : topAdvertisers && topAdvertisers.length > 0 ? (
            <div className="space-y-0">
              {topAdvertisers.map((adv, idx) => (
                <div
                  key={adv.advertiser}
                  className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0"
                >
                  <span
                    className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      idx < 3
                        ? "bg-adscope-100 text-adscope-700"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {idx + 1}
                  </span>
                  <span className="flex-1 text-sm font-medium text-gray-900 truncate">
                    {adv.advertiser}
                  </span>
                  <span className="text-sm text-gray-500 tabular-nums">
                    {adv.ad_count.toLocaleString()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState text="광고주 데이터가 없습니다" />
          )}
        </div>

        {/* Recent Snapshot Timeline */}
        <AdTimeline />
      </div>

      {/* Meta Signal Top Active + Social Impact */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <MetaSignalWidget />
        <SocialImpactWidget />
      </div>
    </div>
  );
}

/** 수집 현황 상태 바 */
function CrawlStatusBar({
  latestCrawlAt,
  todayTotalAds,
  loading,
  dataUpdatedAt,
  onRefresh,
}: {
  latestCrawlAt: string | null;
  todayTotalAds: number;
  loading: boolean;
  dataUpdatedAt: number;
  onRefresh?: () => void;
}) {
  const lastRefresh = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

  return (
    <div className="bg-gradient-to-r from-white to-indigo-50/30 rounded-xl border border-gray-200 px-5 py-3.5 shadow-sm flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-4">
        {/* 수집 상태 표시등 */}
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            {(loading || latestCrawlAt) && (
              <span className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                loading ? "bg-yellow-400 animate-ping" : "bg-green-400 animate-ping"
              }`} style={{ animationDuration: "2s" }} />
            )}
            <span
              className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                loading
                  ? "bg-yellow-500"
                  : latestCrawlAt
                    ? "bg-green-500"
                    : "bg-gray-300"
              }`}
            />
          </span>
          <span className="text-sm font-semibold text-gray-700">수집 현황</span>
        </div>

        <div className="h-4 w-px bg-gray-200" />

        {/* 오늘 수집 건수 */}
        <div className="text-sm text-gray-600">
          오늘{" "}
          <span className="font-bold text-indigo-600">
            {todayTotalAds.toLocaleString()}
          </span>
          건 수집
        </div>

        {/* 최근 수집 시각 */}
        {latestCrawlAt && (
          <>
            <div className="h-4 w-px bg-gray-200 hidden sm:block" />
            <div className="text-sm text-gray-500 hidden sm:block">
              최근 수집: {timeAgo(latestCrawlAt)}
            </div>
          </>
        )}
      </div>

      {/* 새로고침 시각 + 수동 리프레시 */}
      <div className="flex items-center gap-2 text-xs text-gray-400">
        {lastRefresh && <span>{lastRefresh} 갱신</span>}
        <span>실시간 연동</span>
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={loading}
            className="ml-1 px-1.5 py-0.5 rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-40"
            title="수동 새로고침"
          >
            <svg
              className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}

function KpiCard({
  title,
  value,
  subtitle,
  loading,
  accent,
}: {
  title: string;
  value: number;
  subtitle?: string;
  loading: boolean;
  accent: string;
}) {
  return (
    <div className={`rounded-xl border border-gray-100 p-5 shadow-sm card-hover ${accent}`}>
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
        {title}
      </p>
      {loading ? (
        <div className="skeleton h-8 w-20 mt-2" />
      ) : (
        <>
          <p className="text-2xl font-bold text-gray-900 mt-1.5 tabular-nums animate-count">
            {value.toLocaleString()}
          </p>
          {subtitle && (
            <p className="text-[10px] text-gray-400 mt-1">{subtitle}</p>
          )}
        </>
      )}
    </div>
  );
}

function MetaSignalWidget() {
  const { data: topActive, isLoading } = useQuery({
    queryKey: ["metaSignalTopActive"],
    queryFn: () => api.getMetaSignalTopActive(30, 10),
    refetchInterval: 120_000,
  });

  const STATE_COLORS: Record<string, string> = {
    peak: "bg-red-100 text-red-700",
    push: "bg-orange-100 text-orange-700",
    scale: "bg-yellow-100 text-yellow-700",
    cooldown: "bg-blue-100 text-blue-700",
    test: "bg-gray-100 text-gray-600",
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900 mb-5">
        메타신호 활동 TOP 10
      </h2>
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="skeleton h-6 w-6 rounded-full" />
              <div className="skeleton h-4 flex-1" />
              <div className="skeleton h-4 w-16" />
            </div>
          ))}
        </div>
      ) : topActive && topActive.length > 0 ? (
        <div className="space-y-0">
          {topActive.map((item, idx) => (
            <div
              key={item.advertiser_id}
              className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0"
            >
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  idx < 3
                    ? "bg-violet-100 text-violet-700"
                    : "bg-gray-100 text-gray-500"
                }`}
              >
                {idx + 1}
              </span>
              <span className="flex-1 text-sm font-medium text-gray-900 truncate">
                {item.brand_name || item.advertiser_name}
              </span>
              <span className="text-xs font-bold text-violet-600 tabular-nums w-10 text-right">
                {item.composite_score?.toFixed(0)}
              </span>
              <span className="text-[10px] text-gray-400 w-12 text-right">
                x{item.spend_multiplier?.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState text="메타신호 데이터가 없습니다" />
      )}
    </div>
  );
}

function SocialImpactWidget() {
  const { data: topImpact, isLoading } = useQuery({
    queryKey: ["socialImpactTop"],
    queryFn: () => api.getSocialImpactTopImpact(30, 10),
    refetchInterval: 120_000,
  });

  const PHASE_COLORS: Record<string, string> = {
    during: "bg-orange-100 text-orange-700",
    post: "bg-blue-100 text-blue-700",
    pre: "bg-gray-100 text-gray-600",
    none: "bg-gray-50 text-gray-400",
  };

  const PHASE_LABELS: Record<string, string> = {
    during: "Active",
    post: "Post",
    pre: "Pre",
    none: "-",
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900 mb-5">
        Social Impact TOP 10
      </h2>
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="skeleton h-6 w-6 rounded-full" />
              <div className="skeleton h-4 flex-1" />
              <div className="skeleton h-4 w-16" />
            </div>
          ))}
        </div>
      ) : topImpact && topImpact.length > 0 ? (
        <div className="space-y-0">
          {topImpact.map((item, idx) => (
            <div
              key={item.advertiser_id}
              className="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0"
            >
              <span
                className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  idx < 3
                    ? "bg-teal-100 text-teal-700"
                    : "bg-gray-100 text-gray-500"
                }`}
              >
                {idx + 1}
              </span>
              <span className="flex-1 text-sm font-medium text-gray-900 truncate">
                {item.brand_name || item.advertiser_name}
              </span>
              <span className="text-xs font-bold text-teal-600 tabular-nums w-10 text-right">
                {item.composite_score?.toFixed(0)}
              </span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
                PHASE_COLORS[item.impact_phase || "none"] || PHASE_COLORS.none
              }`}>
                {PHASE_LABELS[item.impact_phase || "none"] || "-"}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState text="Social Impact data unavailable" />
      )}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-gray-400">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-10 h-10 mb-2">
        <path d="M20 13V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7m16 0v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-5m16 0h-2.586a1 1 0 0 0-.707.293l-2.414 2.414a1 1 0 0 1-.707.293h-3.172a1 1 0 0 1-.707-.293l-2.414-2.414A1 1 0 0 0 6.586 13H4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <p className="text-sm">{text}</p>
    </div>
  );
}

