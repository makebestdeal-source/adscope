"use client";

import { useState, useMemo, useCallback, useRef, useEffect, memo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api,
  MarketingScheduleData,
  MarketingOverviewItem,
  MarketingDetectionEvent,
  AdvertiserProductItem,
  ProductActivityMatrixItem,
} from "@/lib/api";
import {
  CHANNEL_COLORS,
  formatChannel,
  formatSpend,
} from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";

const PURPOSE_LABELS: Record<string, string> = {
  commerce: "커머스",
  event: "이벤트",
  branding: "브랜딩",
  awareness: "인지도",
  performance: "퍼포먼스",
  launch: "런칭",
  promotion: "프로모션",
  retargeting: "리타겟팅",
};

const STATUS_BADGE: Record<string, string> = {
  active: "bg-green-100 text-green-800",
  discontinued: "bg-gray-100 text-gray-600",
  seasonal: "bg-amber-100 text-amber-800",
  unknown: "bg-gray-100 text-gray-500",
};

const EVENT_LABELS: Record<string, string> = {
  new_product_started: "신규 광고 시작",
  product_stopped: "광고 중단",
  channel_expansion: "채널 확장",
  spend_spike: "예산 급증",
};

/** Max products to render in the Gantt chart at once */
const GANTT_PAGE_SIZE = 30;

export default function MarketingSchedulePage() {
  const [search, setSearch] = useState("");
  const [selectedAdv, setSelectedAdv] = useState<number | null>(null);
  const [days, setDays] = useState(90);
  const [tab, setTab] = useState<"schedule" | "overview" | "detection">("overview");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const searchBoxRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (searchBoxRef.current && !searchBoxRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  // Search advertisers - only query when dropdown is open and text is typed
  const { data: searchResults } = useQuery({
    queryKey: ["advSearch", search],
    queryFn: () => api.searchAdvertisers(search),
    enabled: dropdownOpen && search.length >= 2,
  });

  // Marketing schedule for selected advertiser
  const { data: schedule, isLoading: scheduleLoading } = useQuery({
    queryKey: ["marketingSchedule", selectedAdv, days],
    queryFn: () => api.getMarketingSchedule(selectedAdv!, days),
    enabled: !!selectedAdv,
  });

  // Overview (top advertisers)
  const { data: overview } = useQuery({
    queryKey: ["marketingOverview", days],
    queryFn: () => api.getMarketingOverview(days, 30),
  });

  // Detections
  const { data: detections } = useQuery({
    queryKey: ["marketingDetections"],
    queryFn: () => api.getMarketingDetections(14, 50),
  });

  // Generate date range for Gantt
  const dateRange = useMemo(() => {
    const dates: string[] = [];
    const end = new Date();
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(end);
      d.setDate(d.getDate() - i);
      dates.push(d.toISOString().slice(0, 10));
    }
    return dates;
  }, [days]);

  // Activity lookup map
  const activityMap = useMemo(() => {
    if (!schedule) return new Map<string, ProductActivityMatrixItem>();
    const map = new Map<string, ProductActivityMatrixItem>();
    for (const a of schedule.activity_matrix) {
      const key = `${a.product_id}-${a.date}`;
      const existing = map.get(key);
      if (!existing || a.ad_count > existing.ad_count) {
        map.set(key, a);
      }
    }
    return map;
  }, [schedule]);

  const maxAdCount = useMemo(() => {
    if (!schedule) return 1;
    return Math.max(1, ...schedule.activity_matrix.map((a) => a.ad_count));
  }, [schedule]);

  // Select advertiser handler -- close dropdown, stop search query
  const handleSelectAdvertiser = useCallback((id: number, name: string) => {
    setDropdownOpen(false);
    setSelectedAdv(id);
    setSearch(name);
    setTab("schedule");
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Marketing Plan</h1>
          <p className="text-sm text-gray-500 mt-1">
            광고주별 상품/서비스 광고 스케줄 추적
          </p>
        </div>
        <PeriodSelector days={days} onDaysChange={setDays} />
      </div>

      {/* Search + Tabs */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md" ref={searchBoxRef}>
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setDropdownOpen(true);
            }}
            onFocus={() => setDropdownOpen(true)}
            placeholder="광고주 검색..."
            className="w-full px-4 py-2 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
          />
          {dropdownOpen && searchResults && searchResults.length > 0 && search.length >= 2 && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto">
              {searchResults.map((adv: { id: number; name: string }) => (
                <button
                  key={adv.id}
                  onClick={() => handleSelectAdvertiser(adv.id, adv.name)}
                  className="block w-full px-4 py-2 text-left text-sm hover:bg-indigo-50"
                >
                  {adv.name}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          {(
            [
              { key: "overview", label: "개요" },
              { key: "schedule", label: "스케줄" },
              { key: "detection", label: "감지" },
            ] as const
          ).map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-1.5 text-xs rounded-md transition ${
                tab === t.key
                  ? "bg-white text-gray-900 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {tab === "overview" && (
        <OverviewTab overview={overview || []} onSelect={handleSelectAdvertiser} />
      )}

      {tab === "schedule" && selectedAdv && (
        scheduleLoading ? (
          <div className="text-center py-12 text-gray-400">Loading...</div>
        ) : schedule ? (
          <ScheduleTab
            schedule={schedule}
            dateRange={dateRange}
            activityMap={activityMap}
            maxAdCount={maxAdCount}
            days={days}
          />
        ) : (
          <div className="text-center py-12 text-gray-400">
            광고주를 선택하세요
          </div>
        )
      )}

      {tab === "schedule" && !selectedAdv && (
        <div className="text-center py-12 text-gray-400">
          상단 검색창에서 광고주를 선택하세요
        </div>
      )}

      {tab === "detection" && (
        <DetectionTab detections={detections || []} />
      )}
    </div>
  );
}

// ── Overview Tab ──
function OverviewTab({
  overview,
  onSelect,
}: {
  overview: MarketingOverviewItem[];
  onSelect: (id: number, name: string) => void;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h3 className="text-sm font-semibold text-gray-900">
          광고주별 상품 포트폴리오 현황
        </h3>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-500 text-xs">
          <tr>
            <th className="px-6 py-3 text-left">#</th>
            <th className="px-6 py-3 text-left">광고주</th>
            <th className="px-6 py-3 text-right">전체 상품</th>
            <th className="px-6 py-3 text-right">활성 광고</th>
            <th className="px-6 py-3 text-right">추정 예산</th>
            <th className="px-6 py-3 text-right">커버리지</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {overview.map((item, idx) => {
            const coverage =
              item.total_products > 0
                ? Math.round((item.active_products / item.total_products) * 100)
                : 0;
            return (
              <tr
                key={item.advertiser_id}
                className="hover:bg-indigo-50/30 cursor-pointer transition"
                onClick={() =>
                  onSelect(item.advertiser_id, item.advertiser_name)
                }
              >
                <td className="px-6 py-3 text-gray-400">{idx + 1}</td>
                <td className="px-6 py-3 font-medium text-gray-900">
                  {item.advertiser_name}
                  {item.brand_name && item.brand_name !== item.advertiser_name && (
                    <span className="ml-2 text-xs text-gray-400">
                      {item.brand_name}
                    </span>
                  )}
                </td>
                <td className="px-6 py-3 text-right">{item.total_products}</td>
                <td className="px-6 py-3 text-right font-medium text-green-600">
                  {item.active_products}
                </td>
                <td className="px-6 py-3 text-right text-gray-600">
                  {formatSpend(item.total_spend)}
                </td>
                <td className="px-6 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{ width: `${coverage}%` }}
                      />
                    </div>
                    <span className="text-xs text-gray-500">{coverage}%</span>
                  </div>
                </td>
              </tr>
            );
          })}
          {overview.length === 0 && (
            <tr>
              <td
                colSpan={6}
                className="px-6 py-12 text-center text-gray-400"
              >
                데이터가 없습니다. 스크립트를 실행하세요.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Schedule Tab ──
function ScheduleTab({
  schedule,
  dateRange,
  activityMap,
  maxAdCount,
  days,
}: {
  schedule: MarketingScheduleData;
  dateRange: string[];
  activityMap: Map<string, ProductActivityMatrixItem>;
  maxAdCount: number;
  days: number;
}) {
  const [ganttLimit, setGanttLimit] = useState(GANTT_PAGE_SIZE);
  const products = schedule.products;

  // Summary stats
  const totalProducts = products.length;
  const activeProducts = products.filter(
    (p) => p.last_ad_seen && daysSince(p.last_ad_seen) < 14
  ).length;
  const pausedProducts = totalProducts - activeProducts;

  // Determine cell width for scrolling
  const cellW = days <= 60 ? 20 : days <= 90 ? 14 : 10;

  // Only render a subset of products in the Gantt to avoid DOM overload
  const visibleProducts = useMemo(
    () => products.slice(0, ganttLimit),
    [products, ganttLimit]
  );
  const hasMore = ganttLimit < products.length;

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <SummaryCard label="전체 상품" value={totalProducts} color="indigo" />
        <SummaryCard label="활성 광고 중" value={activeProducts} color="green" />
        <SummaryCard label="일시 중단" value={pausedProducts} color="amber" />
        <SummaryCard
          label="추정 총예산"
          value={formatSpend(
            products.reduce((s, p) => s + (p.total_spend_est || 0), 0)
          )}
          color="blue"
        />
      </div>

      {/* Product Table + Gantt */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center">
          <h3 className="text-sm font-semibold text-gray-900">
            {schedule.advertiser_name} - 제품별 광고 타임라인
          </h3>
          <span className="text-xs text-gray-400">
            {dateRange[0]} ~ {dateRange[dateRange.length - 1]}
          </span>
        </div>

        {products.length === 0 ? (
          <div className="px-6 py-12 text-center text-gray-400">
            등록된 상품이 없습니다
          </div>
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-max">
              {/* Header row */}
              <div className="flex border-b border-gray-100">
                <div className="w-52 flex-shrink-0 px-4 py-2 text-xs font-medium text-gray-500 bg-gray-50">
                  상품/서비스
                </div>
                <div className="w-20 flex-shrink-0 px-2 py-2 text-xs text-gray-500 bg-gray-50 text-center">
                  상태
                </div>
                <div className="w-20 flex-shrink-0 px-2 py-2 text-xs text-gray-500 bg-gray-50 text-right">
                  광고수
                </div>
                <div className="flex-1 flex bg-gray-50">
                  {dateRange.filter((_, i) => i % Math.max(1, Math.floor(days / 15)) === 0).map((d) => (
                    <div
                      key={d}
                      className="text-[9px] text-gray-400 text-center"
                      style={{ width: cellW * Math.max(1, Math.floor(days / 15)) }}
                    >
                      {d.slice(5)}
                    </div>
                  ))}
                </div>
              </div>

              {/* Product rows (paginated to avoid DOM overload) */}
              {visibleProducts.map((product) => (
                <GanttRow
                  key={product.id}
                  product={product}
                  dateRange={dateRange}
                  activityMap={activityMap}
                  maxAdCount={maxAdCount}
                  cellW={cellW}
                />
              ))}

              {/* Load more */}
              {hasMore && (
                <div className="px-6 py-3 text-center border-t border-gray-100">
                  <button
                    onClick={() => setGanttLimit((prev) => prev + GANTT_PAGE_SIZE)}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium"
                  >
                    더 보기 ({products.length - ganttLimit}개 남음)
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Product detail table */}
      {products.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">
              제품별 상세 정보
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 text-gray-500">
                <tr>
                  <th className="px-4 py-2 text-left">상품/서비스</th>
                  <th className="px-4 py-2 text-left">카테고리</th>
                  <th className="px-4 py-2 text-left">목적</th>
                  <th className="px-4 py-2 text-left">광고상품</th>
                  <th className="px-4 py-2 text-left">모델</th>
                  <th className="px-4 py-2 text-left">매체</th>
                  <th className="px-4 py-2 text-right">광고수</th>
                  <th className="px-4 py-2 text-right">예산</th>
                  <th className="px-4 py-2 text-left">기간</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {products.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50/50">
                    <td className="px-4 py-2 font-medium text-gray-900">
                      {p.product_name}
                      {p.is_flagship && (
                        <span className="ml-1 text-[9px] bg-yellow-100 text-yellow-700 px-1 rounded">
                          주력
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-gray-500">
                      {p.product_category_name || "-"}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-1 flex-wrap">
                        {(p.purposes || []).map((pu) => (
                          <span
                            key={pu}
                            className="text-[9px] px-1.5 py-0.5 bg-indigo-50 text-indigo-700 rounded"
                          >
                            {PURPOSE_LABELS[pu] || pu}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-1 flex-wrap">
                        {(p.ad_products_used || []).slice(0, 3).map((ap) => (
                          <span
                            key={ap}
                            className="text-[9px] px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded"
                          >
                            {ap}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-gray-600">
                      {(p.model_names || []).join(", ") || "-"}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-1 flex-wrap">
                        {(p.channels || []).map((ch) => (
                          <span
                            key={ch}
                            className="text-[9px] px-1 rounded"
                            style={{
                              backgroundColor:
                                (CHANNEL_COLORS[ch] || "#999") + "20",
                              color: CHANNEL_COLORS[ch] || "#999",
                            }}
                          >
                            {formatChannel(ch)}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-right">{p.ad_count}</td>
                    <td className="px-4 py-2 text-right text-gray-600">
                      {formatSpend(p.total_spend_est)}
                    </td>
                    <td className="px-4 py-2 text-gray-400">
                      {p.first_ad_seen?.slice(0, 10) || "?"} ~{" "}
                      {p.last_ad_seen?.slice(0, 10) || "?"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Gantt Row (memoized to avoid re-rendering all rows on parent state change) ──
const GanttRow = memo(function GanttRow({
  product,
  dateRange,
  activityMap,
  maxAdCount,
  cellW,
}: {
  product: AdvertiserProductItem;
  dateRange: string[];
  activityMap: Map<string, ProductActivityMatrixItem>;
  maxAdCount: number;
  cellW: number;
}) {
  const isActive = product.last_ad_seen && daysSince(product.last_ad_seen) < 14;
  return (
    <div className="flex border-b border-gray-50 hover:bg-indigo-50/20 transition">
      {/* Product name */}
      <div className="w-52 flex-shrink-0 px-4 py-2">
        <div className="text-xs font-medium text-gray-900 truncate">
          {product.product_name}
        </div>
        <div className="flex gap-1 mt-0.5 flex-wrap">
          {(product.channels || []).slice(0, 3).map((ch) => (
            <span
              key={ch}
              className="text-[9px] px-1 py-0 rounded"
              style={{
                backgroundColor: (CHANNEL_COLORS[ch] || "#999") + "20",
                color: CHANNEL_COLORS[ch] || "#999",
              }}
            >
              {formatChannel(ch)}
            </span>
          ))}
        </div>
      </div>

      {/* Status */}
      <div className="w-20 flex-shrink-0 px-2 py-2 flex items-center justify-center">
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded-full ${
            STATUS_BADGE[isActive ? "active" : "discontinued"]
          }`}
        >
          {isActive ? "활성" : "중단"}
        </span>
      </div>

      {/* Ad count */}
      <div className="w-20 flex-shrink-0 px-2 py-2 text-xs text-right text-gray-600 flex items-center justify-end">
        {product.ad_count}
      </div>

      {/* Gantt cells */}
      <div className="flex-1 flex items-center py-1">
        {dateRange.map((date) => {
          const activity = activityMap.get(`${product.id}-${date}`);
          const intensity = activity
            ? Math.min(activity.ad_count / maxAdCount, 1)
            : 0;
          const channelColor = activity
            ? CHANNEL_COLORS[activity.channel] || "#6366f1"
            : "transparent";

          return (
            <div
              key={date}
              className="rounded-sm"
              style={{
                width: cellW,
                height: 18,
                margin: "0 0.5px",
                backgroundColor:
                  intensity > 0 ? channelColor : "#f3f4f6",
                opacity: intensity > 0 ? 0.3 + intensity * 0.7 : 1,
              }}
              title={
                activity
                  ? `${date}: ${activity.ad_count}건 (${activity.ad_product_name || activity.channel}), ${formatSpend(activity.est_daily_spend)}`
                  : `${date}: No activity`
              }
            />
          );
        })}
      </div>
    </div>
  );
});

// ── Detection Tab ──
function DetectionTab({
  detections,
}: {
  detections: MarketingDetectionEvent[];
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100">
        <h3 className="text-sm font-semibold text-gray-900">
          최근 마케팅 패턴 변화 감지
        </h3>
      </div>
      <div className="divide-y divide-gray-50">
        {detections.map((d, idx) => (
          <div key={idx} className="px-6 py-3 flex items-center gap-4">
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                d.event_type === "new_product_started"
                  ? "bg-green-100 text-green-700"
                  : d.event_type === "product_stopped"
                  ? "bg-red-100 text-red-700"
                  : "bg-blue-100 text-blue-700"
              }`}
            >
              {EVENT_LABELS[d.event_type] || d.event_type}
            </span>
            <div className="flex-1">
              <span className="text-sm font-medium text-gray-900">
                {d.advertiser_name}
              </span>
              <span className="text-sm text-gray-400 mx-2">/</span>
              <span className="text-sm text-gray-600">{d.product_name}</span>
            </div>
            <span className="text-xs text-gray-400">
              {d.detected_at?.slice(0, 10) || "?"}
            </span>
          </div>
        ))}
        {detections.length === 0 && (
          <div className="px-6 py-12 text-center text-gray-400">
            최근 감지된 변화가 없습니다
          </div>
        )}
      </div>
    </div>
  );
}

// ── Helper Components ──
function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number | string;
  color: string;
}) {
  const colors: Record<string, string> = {
    indigo: "border-indigo-200 bg-indigo-50",
    green: "border-green-200 bg-green-50",
    amber: "border-amber-200 bg-amber-50",
    blue: "border-blue-200 bg-blue-50",
  };
  const textColors: Record<string, string> = {
    indigo: "text-indigo-700",
    green: "text-green-700",
    amber: "text-amber-700",
    blue: "text-blue-700",
  };

  return (
    <div
      className={`rounded-xl border p-4 ${colors[color] || colors.indigo}`}
    >
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-xl font-bold mt-1 ${textColors[color]}`}>
        {value}
      </div>
    </div>
  );
}

function daysSince(dateStr: string): number {
  const d = new Date(dateStr);
  const now = new Date();
  return Math.floor((now.getTime() - d.getTime()) / (1000 * 60 * 60 * 24));
}
