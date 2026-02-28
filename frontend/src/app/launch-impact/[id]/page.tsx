"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import Link from "next/link";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from "recharts";

interface Overview {
  launch_product_id: number;
  product_name: string;
  category: string;
  launch_date: string;
  days_since_launch: number;
  date: string | null;
  mrs_score: number;
  rv_score: number;
  cs_score: number;
  lii_score: number;
  total_mentions: number;
  impact_phase: string | null;
  factors: any;
}

interface TimelinePoint {
  date: string;
  mrs_score: number;
  rv_score: number;
  cs_score: number;
  lii_score: number;
  total_mentions: number;
  impact_phase: string | null;
}

interface Mention {
  id: number;
  source_type: string;
  source_platform: string | null;
  url: string;
  title: string | null;
  author: string | null;
  published_at: string | null;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  sentiment: string | null;
  matched_keyword: string | null;
}

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  pre_launch: { label: "출시 전", color: "bg-gray-100 text-gray-700" },
  launch_week: { label: "출시 주", color: "bg-blue-100 text-blue-700" },
  growth: { label: "성장", color: "bg-green-100 text-green-700" },
  plateau: { label: "안정", color: "bg-yellow-100 text-yellow-700" },
  decline: { label: "하락", color: "bg-red-100 text-red-700" },
};

const CATEGORY_LABELS: Record<string, string> = {
  game: "게임", commerce: "커머스", product: "제품",
};

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  news: { label: "뉴스", color: "bg-red-100 text-red-700" },
  blog: { label: "블로그", color: "bg-green-100 text-green-700" },
  community: { label: "커뮤니티", color: "bg-yellow-100 text-yellow-700" },
  youtube: { label: "유튜브", color: "bg-rose-100 text-rose-700" },
  sns: { label: "SNS", color: "bg-blue-100 text-blue-700" },
  review: { label: "리뷰", color: "bg-purple-100 text-purple-700" },
};

const SENTIMENT_LABELS: Record<string, { label: string; color: string }> = {
  positive: { label: "긍정", color: "text-green-600" },
  neutral: { label: "중립", color: "text-gray-500" },
  negative: { label: "부정", color: "text-red-600" },
};

export default function LaunchImpactDetailPage() {
  const params = useParams();
  const productId = params.id as string;

  const [overview, setOverview] = useState<Overview | null>(null);
  const [timeline, setTimeline] = useState<TimelinePoint[]>([]);
  const [mentions, setMentions] = useState<Mention[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [ov, tl, mt] = await Promise.all([
        api.get(`/api/launch-impact/${productId}/overview`),
        api.get(`/api/launch-impact/${productId}/timeline?days=30`),
        api.get(`/api/launch-impact/${productId}/mentions?days=30&limit=100`),
      ]);
      setOverview(ov);
      setTimeline(tl);
      setMentions(mt);
    } catch (e) {
      console.error("Failed to load detail:", e);
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => { load(); }, [load]);

  if (loading || !overview) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  const phase = PHASE_LABELS[overview.impact_phase || ""] || { label: "-", color: "bg-gray-50 text-gray-400" };
  const launchDateStr = overview.launch_date?.slice(0, 10) || "";

  const filteredMentions = sourceFilter
    ? mentions.filter((m) => m.source_type === sourceFilter)
    : mentions;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link href="/launch-impact" className="text-sm text-blue-600 hover:underline mb-1 inline-block">
            &larr; 랭킹으로 돌아가기
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">{overview.product_name}</h1>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-sm text-gray-500">{CATEGORY_LABELS[overview.category] || overview.category}</span>
            <span className="text-sm text-gray-400">|</span>
            <span className="text-sm text-gray-500">출시일: {launchDateStr}</span>
            <span className="text-sm text-gray-400">|</span>
            <span className="text-sm text-gray-500">D+{overview.days_since_launch}</span>
            <span className={`px-2 py-0.5 rounded text-xs ${phase.color}`}>{phase.label}</span>
          </div>
        </div>
      </div>

      {/* Score Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "LII", value: overview.lii_score, color: "border-purple-300 bg-purple-50", textColor: "text-purple-700" },
          { label: "MRS (매체 파급력)", value: overview.mrs_score, color: "border-blue-200 bg-blue-50", textColor: "text-blue-700" },
          { label: "RV (반응 속도)", value: overview.rv_score, color: "border-green-200 bg-green-50", textColor: "text-green-700" },
          { label: "CS (전환 신호)", value: overview.cs_score, color: "border-orange-200 bg-orange-50", textColor: "text-orange-700" },
        ].map((card) => (
          <div key={card.label} className={`rounded-xl border-2 p-5 ${card.color}`}>
            <p className="text-xs font-medium text-gray-500 uppercase">{card.label}</p>
            <p className={`text-3xl font-bold tabular-nums mt-1 ${card.textColor}`}>
              {card.value.toFixed(1)}
            </p>
            <div className="w-full bg-gray-200 rounded-full h-1.5 mt-2">
              <div
                className={`h-1.5 rounded-full transition-all ${
                  card.label === "LII" ? "bg-purple-500" :
                  card.label.startsWith("MRS") ? "bg-blue-500" :
                  card.label.startsWith("RV") ? "bg-green-500" : "bg-orange-500"
                }`}
                style={{ width: `${card.value}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Timeline Chart */}
      {timeline.length > 1 && (
        <div className="bg-white rounded-xl border shadow-sm p-5">
          <h3 className="font-semibold text-gray-900 mb-4">점수 추이</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={timeline.map((t) => ({ ...t, date: t.date?.slice(5, 10) }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Line type="monotone" dataKey="lii_score" name="LII" stroke="#8b5cf6" strokeWidth={2.5} dot={false} />
              <Line type="monotone" dataKey="mrs_score" name="MRS" stroke="#3b82f6" strokeWidth={1.5} dot={false} />
              <Line type="monotone" dataKey="rv_score" name="RV" stroke="#10b981" strokeWidth={1.5} dot={false} />
              <Line type="monotone" dataKey="cs_score" name="CS" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Mention Volume Chart */}
      {timeline.length > 1 && (
        <div className="bg-white rounded-xl border shadow-sm p-5">
          <h3 className="font-semibold text-gray-900 mb-4">일별 멘션 수</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={timeline.map((t) => ({ ...t, date: t.date?.slice(5, 10) }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Bar dataKey="total_mentions" name="멘션 수" fill="#6366f1" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Mentions Table */}
      <div className="bg-white rounded-xl border shadow-sm">
        <div className="p-5 border-b flex items-center justify-between">
          <h3 className="font-semibold text-gray-900">매체 언급 ({filteredMentions.length}건)</h3>
          <div className="flex gap-1">
            <button
              onClick={() => setSourceFilter("")}
              className={`px-2 py-1 text-xs rounded ${!sourceFilter ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
            >
              전체
            </button>
            {Object.entries(SOURCE_LABELS).map(([key, { label }]) => (
              <button
                key={key}
                onClick={() => setSourceFilter(key)}
                className={`px-2 py-1 text-xs rounded ${sourceFilter === key ? "bg-gray-900 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="divide-y max-h-[500px] overflow-y-auto">
          {filteredMentions.map((m) => {
            const src = SOURCE_LABELS[m.source_type] || { label: m.source_type, color: "bg-gray-100 text-gray-600" };
            const sent = m.sentiment ? SENTIMENT_LABELS[m.sentiment] : null;
            return (
              <div key={m.id} className="px-5 py-3 hover:bg-gray-50">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] ${src.color}`}>{src.label}</span>
                  {sent && <span className={`text-[10px] font-medium ${sent.color}`}>{sent.label}</span>}
                  {m.matched_keyword && (
                    <span className="text-[10px] text-gray-400">"{m.matched_keyword}"</span>
                  )}
                  <span className="text-[10px] text-gray-300 ml-auto">
                    {m.published_at ? new Date(m.published_at).toLocaleDateString("ko-KR") : ""}
                  </span>
                </div>
                <a
                  href={m.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-blue-600 hover:underline line-clamp-1"
                >
                  {m.title || m.url}
                </a>
                {m.author && <span className="text-xs text-gray-400 ml-2">{m.author}</span>}
                <div className="flex gap-3 mt-1 text-xs text-gray-400">
                  {m.view_count != null && <span>조회 {m.view_count.toLocaleString()}</span>}
                  {m.like_count != null && <span>좋아요 {m.like_count.toLocaleString()}</span>}
                  {m.comment_count != null && <span>댓글 {m.comment_count.toLocaleString()}</span>}
                </div>
              </div>
            );
          })}
          {filteredMentions.length === 0 && (
            <div className="px-5 py-8 text-center text-gray-400 text-sm">
              멘션 데이터가 아직 없습니다. 수집 후 확인해주세요.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
