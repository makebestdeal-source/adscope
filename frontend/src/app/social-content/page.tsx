"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { fetchPublicApi } from "@/lib/api";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line, Legend } from "recharts";

interface ContentItem {
  id: number;
  advertiser_id: number;
  advertiser_name: string;
  platform: string;
  content_type: string;
  title: string;
  thumbnail_url: string | null;
  upload_date: string | null;
  view_count: number | null;
  like_count: number | null;
  duration_seconds: number | null;
  is_ad_content: boolean;
  content_id: string;
  channel_url: string;
}

interface ContentSummary {
  total_contents: number;
  total_advertisers: number;
  avg_views: number;
  avg_likes: number;
  ad_content_pct: number;
  platform_dist: { platform: string; count: number }[];
}

interface ContentAnalysis {
  summary: ContentSummary;
  top_performing: ContentItem[];
  recent: ContentItem[];
  daily_uploads: { date: string; count: number }[];
}

const PLATFORM_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  youtube: { label: "YouTube", color: "text-red-600", bg: "bg-red-50" },
  instagram: { label: "Instagram", color: "text-pink-600", bg: "bg-pink-50" },
};

function formatNumber(v: number | null): string {
  if (v === null || v === undefined) return "--";
  if (v >= 100_000_000) return `${(v / 100_000_000).toFixed(1)}억`;
  if (v >= 10_000) return `${Math.round(v / 10_000).toLocaleString()}만`;
  return v.toLocaleString();
}

function formatDuration(sec: number | null): string {
  if (!sec) return "--";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function getContentUrl(item: ContentItem): string {
  if (item.platform === "youtube") return `https://www.youtube.com/watch?v=${item.content_id}`;
  if (item.platform === "instagram") return `https://www.instagram.com/p/${item.content_id}/`;
  return item.channel_url;
}

export default function SocialContentPage() {
  const [days, setDays] = useState(30);
  const [platform, setPlatform] = useState<string>("all");
  const [showAdsOnly, setShowAdsOnly] = useState(false);

  const { data, isLoading } = useQuery<ContentAnalysis>({
    queryKey: ["social-content", days, platform],
    queryFn: () =>
      fetchPublicApi(`/brand-channels/content-analysis?days=${days}&platform=${platform === "all" ? "" : platform}`),
  });

  const filteredRecent = (data?.recent ?? []).filter(
    (c) => !showAdsOnly || c.is_ad_content
  );

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-pink-500 to-rose-600 flex items-center justify-center shadow-lg shadow-pink-200/50">
            <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
              <path d="M8 21h8M12 17v4" />
              <path d="M10 9l4 2-4 2V9z" fill="white" />
            </svg>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">콘텐츠 성과</h1>
            <p className="text-sm text-gray-500">브랜드 공식 채널의 포스트별 성과 분석</p>
          </div>
        </div>
        <div className="flex gap-2">
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white"
          >
            <option value="all">전체 플랫폼</option>
            <option value="youtube">YouTube</option>
            <option value="instagram">Instagram</option>
          </select>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
            <option value={7}>7일</option>
            <option value={14}>14일</option>
            <option value={30}>30일</option>
            <option value={90}>90일</option>
          </select>
        </div>
      </div>

      {/* Usage Guide */}
      <div className="mb-6 bg-gradient-to-r from-pink-50 to-rose-50 border border-pink-200 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-pink-800 mb-2">사용 가이드</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-pink-700">
          <div>
            <p className="font-medium mb-1">콘텐츠 분석 활용법</p>
            <ul className="space-y-0.5 list-disc list-inside text-pink-600">
              <li>브랜드 공식 채널(YouTube/Instagram) 콘텐츠 성과 분석</li>
              <li>플랫폼별 필터로 채널 비교, 기간 설정으로 트렌드 파악</li>
              <li>광고성 콘텐츠만 필터링하여 브랜드 광고 전략 분석</li>
            </ul>
          </div>
          <div>
            <p className="font-medium mb-1">주요 지표</p>
            <ul className="space-y-0.5 list-disc list-inside text-pink-600">
              <li>조회수/좋아요 기반 인게이지먼트 비교</li>
              <li>일별 업로드 추이로 콘텐츠 전략 패턴 파악</li>
              <li>TOP 콘텐츠 클릭 시 원본 영상/포스트로 이동</li>
            </ul>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      {data?.summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          {[
            { label: "총 콘텐츠", value: formatNumber(data.summary.total_contents), color: "text-pink-600" },
            { label: "모니터링 브랜드", value: data.summary.total_advertisers, color: "text-blue-600" },
            { label: "평균 조회수", value: formatNumber(data.summary.avg_views), color: "text-violet-600" },
            { label: "평균 좋아요", value: formatNumber(data.summary.avg_likes), color: "text-rose-600" },
            { label: "광고 콘텐츠 비율", value: `${data.summary.ad_content_pct}%`, color: "text-amber-600" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-white rounded-xl border p-4 shadow-sm">
              <p className="text-xs text-gray-500 mb-1">{label}</p>
              <p className={`text-2xl font-bold ${color}`}>{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Platform Distribution */}
        {data?.summary?.platform_dist && (
          <div className="bg-white rounded-xl border p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">플랫폼별 콘텐츠 수</h3>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.summary.platform_dist}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="platform" tick={{ fontSize: 12 }} tickFormatter={(p) => PLATFORM_LABELS[p]?.label || p} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip labelFormatter={(p) => PLATFORM_LABELS[p as string]?.label || p} />
                  <Bar dataKey="count" fill="#ec4899" radius={[4, 4, 0, 0]} name="콘텐츠 수" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Daily Uploads Timeline */}
        {data?.daily_uploads && data.daily_uploads.length > 0 && (
          <div className="bg-white rounded-xl border p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 mb-4">일별 업로드 추이</h3>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.daily_uploads}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="count" stroke="#8b5cf6" strokeWidth={2} dot={false} name="업로드 수" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>

      {/* Top Performing */}
      {data?.top_performing && data.top_performing.length > 0 && (
        <div className="bg-white rounded-xl border shadow-sm mb-8 overflow-hidden">
          <div className="px-5 py-4 border-b">
            <h3 className="text-sm font-semibold text-gray-700">조회수 TOP 콘텐츠</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 p-5">
            {data.top_performing.slice(0, 8).map((item) => {
              const plat = PLATFORM_LABELS[item.platform] || { label: item.platform, color: "text-gray-600", bg: "bg-gray-50" };
              return (
                <a
                  key={item.id}
                  href={getContentUrl(item)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block rounded-lg border hover:shadow-md transition-shadow overflow-hidden group"
                >
                  {item.thumbnail_url ? (
                    <div className="aspect-video bg-gray-100 relative overflow-hidden">
                      <img src={item.thumbnail_url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                      {item.is_ad_content && (
                        <span className="absolute top-2 left-2 text-[9px] font-bold px-1.5 py-0.5 rounded bg-yellow-400 text-yellow-900">AD</span>
                      )}
                      <span className={`absolute top-2 right-2 text-[9px] font-semibold px-1.5 py-0.5 rounded ${plat.bg} ${plat.color}`}>
                        {plat.label}
                      </span>
                    </div>
                  ) : (
                    <div className="aspect-video bg-gray-100 flex items-center justify-center">
                      <span className={`text-xs font-semibold ${plat.color}`}>{plat.label}</span>
                    </div>
                  )}
                  <div className="p-3">
                    <p className="text-sm font-medium text-gray-900 line-clamp-2 mb-1">{item.title || "--"}</p>
                    <p className="text-xs text-gray-500 mb-2">{item.advertiser_name}</p>
                    <div className="flex items-center gap-3 text-xs text-gray-600">
                      <span>조회 {formatNumber(item.view_count)}</span>
                      <span>좋아요 {formatNumber(item.like_count)}</span>
                    </div>
                  </div>
                </a>
              );
            })}
          </div>
        </div>
      )}

      {/* Recent Content List */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">최근 콘텐츠 ({filteredRecent.length}개)</h3>
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={showAdsOnly}
              onChange={(e) => setShowAdsOnly(e.target.checked)}
              className="rounded border-gray-300"
            />
            광고만 보기
          </label>
        </div>
        {isLoading ? (
          <div className="p-12 text-center text-gray-400">로딩 중...</div>
        ) : filteredRecent.length === 0 ? (
          <div className="p-12 text-center text-gray-400">
            <p className="text-lg mb-2">수집된 콘텐츠가 없습니다</p>
            <p className="text-sm">브랜드 채널 모니터링이 활성화되면 데이터가 표시됩니다</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">제목</th>
                  <th className="px-4 py-3 text-left font-medium">브랜드</th>
                  <th className="px-4 py-3 text-center font-medium">플랫폼</th>
                  <th className="px-4 py-3 text-center font-medium">유형</th>
                  <th className="px-4 py-3 text-right font-medium">조회수</th>
                  <th className="px-4 py-3 text-right font-medium">좋아요</th>
                  <th className="px-4 py-3 text-right font-medium">길이</th>
                  <th className="px-4 py-3 text-center font-medium">광고</th>
                  <th className="px-4 py-3 text-left font-medium">업로드일</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredRecent.slice(0, 50).map((c) => {
                  const plat = PLATFORM_LABELS[c.platform] || { label: c.platform, color: "text-gray-600", bg: "bg-gray-50" };
                  return (
                    <tr key={c.id} className="hover:bg-gray-50/50">
                      <td className="px-4 py-3 font-medium text-gray-900 max-w-[250px] truncate">
                        <a href={getContentUrl(c)} target="_blank" rel="noopener noreferrer" className="hover:text-blue-600 hover:underline">
                          {c.title || c.content_id}
                        </a>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{c.advertiser_name}</td>
                      <td className="px-4 py-3 text-center">
                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${plat.bg} ${plat.color}`}>{plat.label}</span>
                      </td>
                      <td className="px-4 py-3 text-center text-gray-600">{c.content_type || "--"}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{formatNumber(c.view_count)}</td>
                      <td className="px-4 py-3 text-right text-gray-700">{formatNumber(c.like_count)}</td>
                      <td className="px-4 py-3 text-right text-gray-600">{formatDuration(c.duration_seconds)}</td>
                      <td className="px-4 py-3 text-center">
                        {c.is_ad_content ? (
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-yellow-100 text-yellow-700">AD</span>
                        ) : "--"}
                      </td>
                      <td className="px-4 py-3 text-gray-600">
                        {c.upload_date ? new Date(c.upload_date).toLocaleDateString("ko-KR") : "--"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
