"use client";

import { useMemo } from "react";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { CHANNEL_LABELS, CHANNEL_COLORS } from "@/lib/constants";

interface Props {
  data: Record<string, number>; // { naver_da: 100, google_gdn: 50, ... }
}

const FALLBACK_COLORS = [
  "#6366f1",
  "#8b5cf6",
  "#a855f7",
  "#d946ef",
  "#ec4899",
  "#f43f5e",
  "#f97316",
];

export function ChannelDonutChart({ data }: Props) {
  const chartData = useMemo(() => {
    return Object.entries(data)
      .map(([channel, count], idx) => ({
        name: CHANNEL_LABELS[channel] ?? channel,
        value: count,
        color: CHANNEL_COLORS[channel] ?? FALLBACK_COLORS[idx % FALLBACK_COLORS.length],
      }))
      .sort((a, b) => b.value - a.value);
  }, [data]);

  const total = useMemo(
    () => chartData.reduce((sum, item) => sum + item.value, 0),
    [chartData]
  );

  if (chartData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-gray-400">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          className="w-10 h-10 mb-2"
        >
          <path
            d="M21.21 15.89A10 10 0 1 1 8 2.83"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M22 12A10 10 0 0 0 12 2v10z"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-sm">채널 데이터가 없습니다</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center">
      <ResponsiveContainer width="100%" height={250}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={90}
            paddingAngle={2}
            dataKey="value"
            nameKey="name"
            label={({ name, percent }) =>
              `${name} ${(percent * 100).toFixed(0)}%`
            }
            labelLine={{ strokeWidth: 1 }}
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number, name: string) => [
              `${value.toLocaleString()}`,
              name,
            ]}
            contentStyle={{
              borderRadius: 8,
              border: "1px solid #e5e7eb",
              fontSize: 12,
            }}
          />
        </PieChart>
      </ResponsiveContainer>
      <p className="text-sm text-gray-500 mt-1">
        Total: <span className="font-semibold text-gray-900">{total.toLocaleString()}</span>
      </p>
    </div>
  );
}
