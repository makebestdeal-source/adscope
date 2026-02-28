"use client";

import { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { DailyTrendPoint } from "@/lib/api";
import { CHANNEL_LABELS, CHANNEL_COLORS } from "@/lib/constants";

interface Props {
  data: DailyTrendPoint[];
}

export function DailyTrendChart({ data }: Props) {
  // data = [{date, channel, ad_count}, ...] -> pivot to {date, naver_da: N, ...}
  const { chartData, channels } = useMemo(() => {
    const dateMap: Record<string, Record<string, number>> = {};
    const channelSet = new Set<string>();

    for (const item of data) {
      channelSet.add(item.channel);
      if (!dateMap[item.date]) {
        dateMap[item.date] = {};
      }
      dateMap[item.date][item.channel] = item.ad_count;
    }

    const sortedDates = Object.keys(dateMap).sort();
    const channelList = Array.from(channelSet).sort();

    const chartData = sortedDates.map((date) => {
      const entry: Record<string, string | number> = {
        date: date.slice(5), // MM-DD
        fullDate: date,
      };
      for (const ch of channelList) {
        entry[ch] = dateMap[date][ch] ?? 0;
      }
      return entry;
    });

    return { chartData, channels: channelList };
  }, [data]);

  if (!data || data.length === 0) {
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
            d="M3 12l3-9 4 18 4-9 3 9 4-18"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className="text-sm">트렌드 데이터가 없습니다</p>
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} />
        <Tooltip
          labelFormatter={(label, payload) => {
            const item = payload?.[0]?.payload;
            return item?.fullDate ?? label;
          }}
          formatter={(value: number, name: string) => [
            `${value.toLocaleString()}`,
            CHANNEL_LABELS[name] ?? name,
          ]}
          contentStyle={{
            borderRadius: 8,
            border: "1px solid #e5e7eb",
            fontSize: 12,
          }}
        />
        <Legend
          formatter={(value: string) => CHANNEL_LABELS[value] ?? value}
          wrapperStyle={{ fontSize: 11 }}
        />
        {channels.map((ch) => (
          <Line
            key={ch}
            type="monotone"
            dataKey={ch}
            stroke={CHANNEL_COLORS[ch] ?? "#6366f1"}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
