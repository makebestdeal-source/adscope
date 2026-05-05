"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis,
  Tooltip, ResponsiveContainer,
} from "recharts";
import {
  api,
  type CampaignCreative,
  type CampaignDetail,
  type CampaignEffect,
} from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";
import { CreativeImage } from "@/components/CreativeImage";
import { formatSpend } from "@/lib/constants";

/* ── 상수 ── */
const CHANNEL_COLORS: Record<string, string> = {
  naver_search: "#03C75A", naver_da: "#1EC800", naver_shopping: "#00C73C",
  google_search_ads: "#4285F4", google_gdn: "#4285F4",
  youtube_ads: "#FF0000", youtube_surf: "#FF4444",
  meta: "#0081FB", meta_feed: "#0081FB",
  kakao_da: "#FEE500", tiktok_ads: "#010101",
};

const OBJECTIVE_LABELS: Record<string, string> = {
  brand_awareness: "브랜드 인지", traffic: "트래픽", engagement: "참여",
  conversion: "전환", retention: "리텐션",
};

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-700",
  completed: "bg-gray-100 text-gray-600",
  paused: "bg-yellow-100 text-yellow-700",
};

const STAGE_COLORS: Record<string, string> = {
  exposure: "#6366F1",  // indigo
  interest: "#3B82F6",  // blue
  consideration: "#F59E0B",  // amber
  conversion: "#10B981",  // green
};

/* ── 유틸 ── */
function fmtNum(n: number | null | undefined): string {
  if (n == null) return "-";
  if (Math.abs(n) >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  if (Math.abs(n) >= 1e4) return `${(n / 1e4).toFixed(1)}만`;
  return n.toLocaleString("ko-KR");
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "-";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function fmtDate(d: string | null): string {
  if (!d) return "-";
  return new Date(d).toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
}

/* ── 페이지 ── */
export default function CampaignDetailPage() {
  const { id } = useParams<{ id: string }>();
  const campaignId = Number(id);
  const router = useRouter();
  const queryClient = useQueryClient();
  const [authed, setAuthed] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  // Data fetching
  const { data: detail } = useQuery({
    queryKey: ["campaignDetail", campaignId],
    queryFn: () => api.getCampaignDetail(campaignId),
    enabled: !!campaignId,
  });

  const { data: effect } = useQuery({
    queryKey: ["campaignEffect", campaignId],
    queryFn: () => api.getCampaignEffect(campaignId),
    enabled: !!campaignId,
  });

  const { data: lift } = useQuery({
    queryKey: ["campaignLift", campaignId],
    queryFn: () => api.getCampaignLift(campaignId),
    enabled: !!campaignId,
  });

  // Edit mutation
  const [editForm, setEditForm] = useState<Partial<CampaignDetail>>({});

  const updateMut = useMutation({
    mutationFn: (data: Partial<CampaignDetail>) => api.updateCampaign(campaignId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaignDetail", campaignId] });
      setEditing(false);
    },
  });

  // Loading states
  if (!detail) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-gray-200 rounded w-1/3" />
          <div className="grid grid-cols-6 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-24 bg-gray-200 rounded" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const startEdit = () => {
    setEditForm({
      campaign_name: detail.campaign_name,
      objective: detail.objective,
      product_service: detail.product_service,
      promotion_copy: detail.promotion_copy,
      model_info: detail.model_info,
    });
    setEditing(true);
  };

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      {/* ── 헤더 ── */}
      <div className="flex items-start justify-between">
        <div>
          <button
            onClick={() => router.back()}
            className="text-sm text-gray-500 hover:text-gray-700 mb-1"
          >
            &larr; 뒤로
          </button>
          <h1 className="text-2xl font-bold text-gray-900">
            {detail.campaign_name || `캠페인 #${detail.id}`}
          </h1>
          <div className="flex gap-2 mt-2 flex-wrap">
            {detail.status && (
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[detail.status] || "bg-gray-100"}`}>
                {detail.status}
              </span>
            )}
            {detail.objective && (
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-700">
                {OBJECTIVE_LABELS[detail.objective] || detail.objective}
              </span>
            )}
            <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700">
              {detail.channel}
            </span>
            {detail.start_at && detail.end_at && (
              <span className="text-xs text-gray-500">
                {fmtDate(detail.start_at)} ~ {fmtDate(detail.end_at)}
              </span>
            )}
          </div>
        </div>
        {(detail.advertiser_name || effect?.advertiser_name) && (
          <div className="text-right">
            <p className="text-sm text-gray-500">광고주</p>
            {detail.advertiser_exists ? (
              <button
                onClick={() => router.push(`/advertisers/${detail.advertiser_id}`)}
                className="font-semibold text-indigo-700 hover:underline"
              >
                {detail.advertiser_name || effect?.advertiser_name}
              </button>
            ) : (
              <p className="font-semibold text-gray-800">
                {detail.advertiser_name || effect?.advertiser_name}
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Section 1: KPI Cards ── */}
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="총 광고비" value={formatSpend(effect?.total_spend ?? 0)} color="blue" />
        <KpiCard label="추정 노출" value={fmtNum(effect?.est_impressions)} unit="회" color="blue" />
        <KpiCard label="추정 클릭" value={fmtNum(effect?.est_clicks)} unit="회" color="blue" />
      </div>

      {/* ── Section 3: Campaign Details Card (데이터 있을 때만) ── */}
      {(detail.objective || detail.product_service || detail.promotion_copy || detail.model_info || detail.target_keywords) && (
        <div className="bg-white rounded-xl shadow p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800">캠페인 상세</h2>
            {!editing && authed ? (
              <button
                onClick={startEdit}
                className="text-sm text-indigo-600 hover:text-indigo-800"
              >
                편집
              </button>
            ) : editing ? (
              <div className="flex gap-2">
                <button
                  onClick={() => updateMut.mutate(editForm)}
                  className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700"
                  disabled={updateMut.isPending}
                >
                  {updateMut.isPending ? "저장중..." : "저장"}
                </button>
                <button
                  onClick={() => setEditing(false)}
                  className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                >
                  취소
                </button>
              </div>
            ) : (
              <span className="text-xs text-gray-400">비회원은 읽기 전용으로 열람할 수 있습니다.</span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DetailField
              label="광고목적"
              value={editing ? editForm.objective : detail.objective}
              editing={editing}
              onChange={(v) => setEditForm({ ...editForm, objective: v })}
              options={Object.entries(OBJECTIVE_LABELS).map(([k, v]) => ({ value: k, label: v }))}
            />
            <DetailField
              label="광고상품/서비스"
              value={editing ? editForm.product_service : detail.product_service}
              editing={editing}
              onChange={(v) => setEditForm({ ...editForm, product_service: v })}
            />
            <DetailField
              label="프로모션 카피"
              value={editing ? editForm.promotion_copy : detail.promotion_copy}
              editing={editing}
              onChange={(v) => setEditForm({ ...editForm, promotion_copy: v })}
              multiline
            />
            <DetailField
              label="모델/셀럽 정보"
              value={editing ? editForm.model_info : detail.model_info}
              editing={editing}
              onChange={(v) => setEditForm({ ...editForm, model_info: v })}
            />
          </div>

          {/* Keywords */}
          {detail.target_keywords && (
            <div className="mt-4">
              <p className="text-xs text-gray-500 mb-1">타겟 키워드</p>
              <div className="flex flex-wrap gap-1">
                {Object.entries(detail.target_keywords).map(([type, keywords]) =>
                  (keywords as string[])?.map((kw) => (
                    <span
                      key={`${type}-${kw}`}
                      className={`px-2 py-0.5 rounded-full text-xs ${
                        type === "brand"
                          ? "bg-indigo-50 text-indigo-600"
                          : type === "product"
                            ? "bg-green-50 text-green-600"
                            : "bg-red-50 text-red-600"
                      }`}
                    >
                      {kw}
                    </span>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Section 4: Lift Analysis ── */}
      {lift && (
        <div className="bg-white rounded-xl shadow p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-800">사전/사후 효과 분석</h2>
            {lift.confidence != null && (
              <span className="text-xs text-gray-500">
                신뢰도: {(lift.confidence * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <LiftCard
              title="Query Lift"
              subtitle="검색 지수 변화"
              preAvg={lift.pre_query_avg}
              postAvg={lift.post_query_avg}
              liftPct={lift.query_lift_pct}
              color="#3B82F6"
            />
            <LiftCard
              title="Social Lift"
              subtitle="소셜 반응 변화"
              preAvg={lift.pre_social_avg}
              postAvg={lift.post_social_avg}
              liftPct={lift.social_lift_pct}
              color="#F59E0B"
            />
            <LiftCard
              title="Sales Lift"
              subtitle="판매/전환 변화"
              preAvg={lift.pre_sales_avg}
              postAvg={lift.post_sales_avg}
              liftPct={lift.sales_lift_pct}
              color="#10B981"
            />
          </div>
        </div>
      )}

      {/* ── Section 5: Linked Creatives (실제 로드된 것만) ── */}
      {detail.creatives && detail.creatives.length > 0 && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-lg font-semibold text-gray-800 mb-4">
            연결 소재 ({detail.creatives.length}건
            {detail.creative_ids && detail.creative_ids.length > 20 && ", 최대 20건 표시"})
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {detail.creatives.map((c) => (
              <CreativeCard key={c.id} creative={c} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ── */

function KpiCard({
  label, value, unit, color, isLift,
}: {
  label: string;
  value: string;
  unit?: string;
  color: string;
  isLift?: boolean;
}) {
  const borderColor = {
    blue: "border-l-blue-500",
    green: "border-l-green-500",
    red: "border-l-red-500",
    gray: "border-l-gray-400",
  }[color] || "border-l-blue-500";

  return (
    <div className={`bg-white rounded-lg shadow p-3 border-l-4 ${borderColor}`}>
      <p className="text-xs text-gray-500 truncate">{label}</p>
      <p className={`text-lg font-bold mt-1 ${
        isLift && value.startsWith("+") ? "text-green-600" :
        isLift && value.startsWith("-") ? "text-red-600" : "text-gray-900"
      }`}>
        {value}
        {unit && <span className="text-xs font-normal text-gray-500 ml-1">{unit}</span>}
      </p>
    </div>
  );
}

function liftColor(pct: number | null | undefined): string {
  if (pct == null) return "gray";
  return pct >= 0 ? "green" : "red";
}

function DetailField({
  label, value, editing, onChange, multiline, options,
}: {
  label: string;
  value: string | null | undefined;
  editing: boolean;
  onChange?: (v: string) => void;
  multiline?: boolean;
  options?: { value: string; label: string }[];
}) {
  if (editing && onChange) {
    if (options) {
      return (
        <div>
          <p className="text-xs text-gray-500 mb-1">{label}</p>
          <select
            value={value || ""}
            onChange={(e) => onChange(e.target.value)}
            className="w-full border rounded px-2 py-1 text-sm"
          >
            <option value="">-</option>
            {options.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      );
    }
    if (multiline) {
      return (
        <div>
          <p className="text-xs text-gray-500 mb-1">{label}</p>
          <textarea
            value={value || ""}
            onChange={(e) => onChange(e.target.value)}
            rows={3}
            className="w-full border rounded px-2 py-1 text-sm"
          />
        </div>
      );
    }
    return (
      <div>
        <p className="text-xs text-gray-500 mb-1">{label}</p>
        <input
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border rounded px-2 py-1 text-sm"
        />
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm text-gray-800 mt-0.5">
        {value || <span className="text-gray-400">-</span>}
      </p>
    </div>
  );
}

function LiftCard({
  title, subtitle, preAvg, postAvg, liftPct, color,
}: {
  title: string;
  subtitle: string;
  preAvg: number | null;
  postAvg: number | null;
  liftPct: number | null;
  color: string;
}) {
  const barData = [
    { name: "사전(7일)", value: preAvg ?? 0 },
    { name: "사후(7일)", value: postAvg ?? 0 },
  ];

  return (
    <div className="border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <p className="font-semibold text-sm">{title}</p>
          <p className="text-xs text-gray-500">{subtitle}</p>
        </div>
        <span className={`text-lg font-bold ${
          liftPct != null && liftPct >= 0 ? "text-green-600" : "text-red-600"
        }`}>
          {fmtPct(liftPct)}
        </span>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={barData} layout="vertical">
          <XAxis type="number" tick={{ fontSize: 10 }} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={70} />
          <Tooltip contentStyle={{ fontSize: 12 }} />
          <Bar dataKey="value" fill={color} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

const TEXT_AD_CHANNELS = new Set(["naver_search", "google_search_ads"]);

function CreativeCard({ creative }: { creative: CampaignCreative }) {
  const isText = TEXT_AD_CHANNELS.has(creative.channel);

  const domain = (() => {
    try { return new URL(creative.url || "").hostname.replace("www.", ""); }
    catch { return creative.url || ""; }
  })();

  return (
    <div className="rounded-lg border border-gray-200 overflow-hidden hover:shadow-md transition-shadow">
      <div className="relative aspect-[4/3] bg-gray-100">
        {creative.creative_image_path ? (
          <CreativeImage
            path={creative.creative_image_path}
            alt={creative.advertiser_name_raw || creative.ad_text || "creative"}
            className="w-full h-full object-cover"
            fallback={<CreativeTextPreview creative={creative} domain={domain} isText={isText} />}
          />
        ) : (
          <div className={`w-full h-full flex flex-col justify-center p-2 ${
            creative.channel === "naver_search" ? "bg-[#f0f8ff]" : "bg-[#f8fff0]"
          }`}>
            <p className="text-[10px] text-gray-500 truncate">{domain}</p>
            <p className="text-xs font-semibold text-gray-800 line-clamp-2 mt-0.5">
              {creative.ad_text || "-"}
            </p>
          </div>
        )}
      </div>
      <div className="p-2">
        <p className="text-[10px] text-gray-500 truncate">{creative.channel}</p>
        {creative.ad_text && (
          <p className="text-xs text-gray-700 line-clamp-2 mt-0.5">{creative.ad_text}</p>
        )}
      </div>
    </div>
  );
}

function CreativeTextPreview({
  creative,
  domain,
  isText,
}: {
  creative: CampaignCreative;
  domain: string;
  isText: boolean;
}) {
  return (
    <div className={`w-full h-full flex flex-col justify-center p-2 ${
      isText ? (creative.channel === "naver_search" ? "bg-[#f0f8ff]" : "bg-[#f8fff0]") : "bg-gray-50"
    }`}>
      <p className="text-[10px] text-gray-500 truncate">{domain}</p>
      <p className="text-xs font-semibold text-gray-800 line-clamp-2 mt-0.5">
        {creative.ad_text || "이미지 없음"}
      </p>
    </div>
  );
}
