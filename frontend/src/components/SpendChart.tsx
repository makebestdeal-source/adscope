"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { SpendSummary } from "@/lib/api";
import { formatChannel, formatSpend, CHANNEL_COLORS } from "@/lib/constants";

export function SpendChart({ data }: { data: SpendSummary[] }) {
  if (!data || data.length === 0) {
    return <p className="text-gray-400 text-sm">데이터 수집 대기 중...</p>;
  }

  const chartData = data.map((item) => ({
    name: formatChannel(item.channel),
    spend: item.total_spend,
    confidence: item.avg_confidence,
    fill: CHANNEL_COLORS[item.channel] ?? "#6366f1",
  }));

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} />
        <YAxis
          tick={{ fontSize: 12 }}
          tickFormatter={(v) => formatSpend(v)}
        />
        <Tooltip
          formatter={(value: number) => [
            formatSpend(value),
            "추정 광고비",
          ]}
        />
        <Bar dataKey="spend" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
