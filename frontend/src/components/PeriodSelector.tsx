"use client";

import { useState } from "react";

interface PeriodSelectorProps {
  days: number;
  onDaysChange: (days: number) => void;
  customRange?: { from: string; to: string };
  onCustomRangeChange?: (from: string, to: string) => void;
  dataStartDate?: string;  // 최초 데이터 날짜
  showCustom?: boolean;
}

const PRESETS = [7, 14, 30, 60, 90];

export function PeriodSelector({
  days,
  onDaysChange,
  customRange,
  onCustomRangeChange,
  dataStartDate,
  showCustom = true,
}: PeriodSelectorProps) {
  const [isCustom, setIsCustom] = useState(false);

  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-0.5 bg-gray-100 rounded-lg p-0.5">
        {PRESETS.map((d) => (
          <button
            key={d}
            onClick={() => {
              setIsCustom(false);
              onDaysChange(d);
            }}
            className={`px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors ${
              !isCustom && days === d
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {d}일
          </button>
        ))}
        {showCustom && (
          <button
            onClick={() => setIsCustom(!isCustom)}
            className={`px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors ${
              isCustom
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            직접선택
          </button>
        )}
      </div>

      {isCustom && onCustomRangeChange && (
        <div className="flex items-center gap-1.5">
          <input
            type="date"
            value={customRange?.from || ""}
            onChange={(e) => onCustomRangeChange(e.target.value, customRange?.to || "")}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-adscope-500/20"
          />
          <span className="text-gray-400 text-xs">~</span>
          <input
            type="date"
            value={customRange?.to || ""}
            onChange={(e) => onCustomRangeChange(customRange?.from || "", e.target.value)}
            className="text-xs border border-gray-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-adscope-500/20"
          />
        </div>
      )}

      {dataStartDate && (
        <span className="text-[10px] text-gray-400 ml-1">
          데이터 시작: {dataStartDate}
        </span>
      )}
    </div>
  );
}
