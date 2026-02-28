"use client";

/**
 * 데이터 최신성 표시 + 수동 새로고침 버튼.
 *
 * 사용법:
 *   <DataFreshness dataUpdatedAt={dataUpdatedAt} onRefresh={refetch} isRefreshing={isFetching} />
 */

interface DataFreshnessProps {
  dataUpdatedAt: number;
  onRefresh: () => void;
  isRefreshing?: boolean;
  label?: string;
}

export function DataFreshness({
  dataUpdatedAt,
  onRefresh,
  isRefreshing,
  label,
}: DataFreshnessProps) {
  const lastRefresh = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

  return (
    <div className="flex items-center gap-2 text-xs text-gray-400">
      {label && <span>{label}</span>}
      {lastRefresh && <span>{lastRefresh} 갱신</span>}
      <button
        onClick={onRefresh}
        disabled={isRefreshing}
        className="ml-1 px-2 py-0.5 rounded text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors disabled:opacity-40"
        title="수동 새로고침"
      >
        <svg
          className={`w-3.5 h-3.5 inline-block ${isRefreshing ? "animate-spin" : ""}`}
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
    </div>
  );
}
