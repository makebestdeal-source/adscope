"use client";

import { useQuery } from "@tanstack/react-query";
import {
  api,
  PersonaAdvertiserRank,
  PersonaHeatmapCell,
} from "@/lib/api";
import { formatChannel, PERSONA_CODES, PERSONA_LABELS, HEATMAP_COLORS, AGE_GROUPS, CHANNEL_COLORS } from "@/lib/constants";
import { PeriodSelector } from "@/components/PeriodSelector";
import { useState, useMemo } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend, Cell, PieChart, Pie,
} from "recharts";

// ── Shared constants ──

const NETWORK_COLORS: Record<string, string> = {
  gdn: "#4285f4", naver: "#03c75a", kakao: "#fee500", meta: "#0668E1", other: "#9ca3af",
};
const NETWORK_LABELS: Record<string, string> = {
  gdn: "Google GDN", naver: "Naver DA", kakao: "Kakao DA", meta: "Meta (FB/IG)", other: "Other",
};
const PERSONA_LABEL_MAP: Record<string, string> = {
  M10: "10대 남성", F10: "10대 여성", M20: "20대 남성", F20: "20대 여성",
  M30: "30대 남성", F30: "30대 여성", M40: "40대 남성", F40: "40대 여성",
  M50: "50대 남성", F50: "50대 여성", M60: "60대 남성", F60: "60대 여성",
};

const CHANNELS = [
  "", "naver_search", "naver_da", "google_gdn", "youtube_ads", "youtube_surf",
  "kakao_da", "facebook", "facebook_contact", "instagram",
];

const BAR_COLORS = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#06b6d4", "#f97316", "#ec4899", "#14b8a6", "#a855f7",
  "#22d3ee", "#84cc16", "#fb7185", "#38bdf8", "#c084fc",
  "#facc15", "#34d399", "#f472b6", "#60a5fa", "#4ade80",
];

function formatKRW(v: unknown) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "0";
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}억`;
  if (n >= 10_000) return `${Math.round(n / 10_000).toLocaleString()}만`;
  return n.toLocaleString();
}

function personaLabel(code: string): string {
  return PERSONA_LABELS[code] ?? PERSONA_LABEL_MAP[code] ?? code;
}

function intensityClass(intensity: number): string {
  if (intensity <= 0) return "bg-gray-50";
  if (intensity < 0.1) return "bg-blue-50";
  if (intensity < 0.2) return "bg-blue-100";
  if (intensity < 0.3) return "bg-blue-200";
  if (intensity < 0.4) return "bg-blue-300";
  if (intensity < 0.5) return "bg-blue-400 text-white";
  if (intensity < 0.65) return "bg-blue-500 text-white";
  if (intensity < 0.8) return "bg-blue-600 text-white";
  return "bg-blue-700 text-white";
}

// ── Tab definitions ──

type TabKey = "contact-rate" | "persona-ranking";

const TABS: { key: TabKey; label: string }[] = [
  { key: "contact-rate", label: "접촉률 분석" },
  { key: "persona-ranking", label: "페르소나 랭킹" },
];

export default function PersonaContactPage() {
  const [tab, setTab] = useState<TabKey>("contact-rate");
  const [days, setDays] = useState(30);

  return (
    <div className="p-6 lg:p-8 max-w-7xl animate-fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">페르소나 접촉률</h1>
        <p className="text-sm text-gray-500 mt-1">
          페르소나별 광고 접촉률 분석 및 광고주 노출 랭킹
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-6 w-fit">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === t.key
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "contact-rate" ? (
        <ContactRateTab days={days} setDays={setDays} />
      ) : (
        <PersonaRankingTab days={days} setDays={setDays} />
      )}
    </div>
  );
}

// ═══════════════════════════════════════
// Tab 1: 접촉률 분석
// ═══════════════════════════════════════

function ContactRateTab({ days, setDays }: { days: number; setDays: (d: number) => void }) {
  const { data: stealth, isLoading: stealthLoading } = useQuery({
    queryKey: ["stealthSummary", days],
    queryFn: () => api.getStealthSummary(days),
  });
  const { data: personaData } = useQuery({
    queryKey: ["stealthPersona", days],
    queryFn: () => api.getStealthPersonaBreakdown(days),
  });
  const { data: spendData } = useQuery({
    queryKey: ["stealthSpend", days],
    queryFn: () => api.getStealthSpendEstimate(days),
  });
  const { data: rates, isLoading: ratesLoading } = useQuery({
    queryKey: ["contactRates", days],
    queryFn: () => api.getContactRates({ days }),
  });

  const networkPie = useMemo(() => {
    if (!stealth?.by_network) return [];
    return Object.entries(stealth.by_network).map(([net, cnt]) => ({
      name: NETWORK_LABELS[net] ?? net, value: cnt as number,
      color: NETWORK_COLORS[net] ?? "#9ca3af",
    }));
  }, [stealth]);

  const personaBar = useMemo(() => {
    if (!stealth?.by_persona) return [];
    return Object.entries(stealth.by_persona)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([p, cnt]) => ({ persona: PERSONA_LABEL_MAP[p] ?? p, code: p, count: cnt as number }));
  }, [stealth]);

  const heatmapData = useMemo(() => {
    if (!personaData?.cells) return [];
    return personaData.cells.map((c: any) => ({
      ...c,
      personaLabel: PERSONA_LABEL_MAP[c.persona] ?? c.persona,
      networkLabel: NETWORK_LABELS[c.network] ?? c.network,
    }));
  }, [personaData]);

  const spendEstimates = useMemo(() => {
    if (!spendData?.estimates) return [];
    return spendData.estimates.map((e: any) => ({
      ...e, networkLabel: NETWORK_LABELS[e.network] ?? e.network,
    }));
  }, [spendData]);

  const kpi = useMemo(() => {
    const ratesArr = Array.isArray(rates) ? rates : [];
    if (ratesArr.length === 0) return { avgRate: 0, totalSessions: 0, uniqueAdv: 0 };
    const totalSessions = ratesArr.reduce((s: number, r: any) => s + r.total_sessions, 0);
    const totalImpressions = ratesArr.reduce((s: number, r: any) => s + r.total_ad_impressions, 0);
    const uniqueAdv = Math.max(...ratesArr.map((r: any) => r.unique_advertisers), 0);
    return { avgRate: totalSessions > 0 ? +(totalImpressions / totalSessions).toFixed(2) : 0, totalSessions, uniqueAdv };
  }, [rates]);

  const barData = useMemo(() => {
    if (!Array.isArray(rates)) return [];
    const grouped: Record<string, Record<string, number>> = {};
    for (const r of rates as any[]) {
      if (!grouped[r.age_group]) grouped[r.age_group] = {};
      grouped[r.age_group][r.channel] = (grouped[r.age_group][r.channel] ?? 0) + r.contact_rate;
    }
    return Object.entries(grouped).map(([ag, channels]) => ({ age_group: ag, ...channels }));
  }, [rates]);

  const channelsInData = useMemo(() => {
    if (!Array.isArray(rates)) return [];
    return [...new Set((rates as any[]).map((r) => r.channel))];
  }, [rates]);

  return (
    <>
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm flex gap-3 items-center">
        <PeriodSelector days={days} onDaysChange={setDays} />
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-blue-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">총 광고 응답</p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {stealthLoading ? "---" : (stealth?.total_ads ?? 0).toLocaleString()}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-green-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">서프 세션</p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {stealthLoading ? "---" : stealth?.sessions ?? 0}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">페르소나 수</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-purple-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">GDN 접촉률</p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {stealthLoading ? "---" : `${stealth?.contact_rates?.gdn ?? 0}/page`}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">페이지당 노출</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 border-l-4 border-l-yellow-500 p-5 shadow-sm">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">크롤러 접촉률</p>
          <p className="text-2xl font-bold text-gray-900 mt-1 tabular-nums">
            {ratesLoading ? "---" : `${kpi.avgRate}건/세션`}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">{kpi.totalSessions} 세션</p>
        </div>
      </div>

      {/* Network pie + Persona bar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-4">네트워크별 광고 분포</h2>
          {networkPie.length > 0 ? (
            <div className="flex items-center gap-4">
              <ResponsiveContainer width="60%" height={200}>
                <PieChart>
                  <Pie data={networkPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={false}>
                    {networkPie.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                  </Pie>
                  <Tooltip formatter={(v) => Number(v ?? 0).toLocaleString()} />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2">
                {networkPie.map((item) => (
                  <div key={item.name} className="flex items-center gap-2 text-sm">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                    <span className="text-gray-600">{item.name}</span>
                    <span className="ml-auto font-medium tabular-nums">{item.value.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-12">
              {stealthLoading ? "로딩 중..." : "stealth 수집 데이터 없음"}
            </p>
          )}
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900 mb-4">페르소나별 수집량</h2>
          {personaBar.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={personaBar}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="code" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip labelFormatter={(v) => PERSONA_LABEL_MAP[v as string] ?? v} formatter={(v) => Number(v ?? 0).toLocaleString()} />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-400 text-center py-12">데이터 없음</p>
          )}
        </div>
      </div>

      {/* Spend estimate */}
      {spendEstimates.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">접촉률 기반 월간 광고비 추정</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {spendEstimates.map((e: any) => (
              <div key={e.network} className="border border-gray-100 rounded-lg p-4">
                <p className="text-xs font-medium text-gray-500">{e.networkLabel}</p>
                <p className="text-lg font-bold text-gray-900 mt-1">{formatKRW(e.est_monthly_total)}</p>
                <p className="text-xs text-gray-400">접촉률 {e.contact_rate}/page</p>
                <p className="text-xs text-gray-400">매체비 {formatKRW(e.est_monthly_media)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Persona x Network heatmap */}
      {heatmapData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden mb-6">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-900">페르소나 x 네트워크 히트맵</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">페르소나</th>
                  {Object.keys(NETWORK_LABELS).filter(k => k !== "other").map((net) => (
                    <th key={net} className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">
                      {NETWORK_LABELS[net]}
                    </th>
                  ))}
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">합계</th>
                </tr>
              </thead>
              <tbody>
                {(personaData?.personas ?? []).map((p: string) => {
                  const cells = heatmapData.filter((c: any) => c.persona === p);
                  const total = cells.reduce((s: number, c: any) => s + c.count, 0);
                  return (
                    <tr key={p} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-3 px-4 font-medium">{PERSONA_LABEL_MAP[p] ?? p}</td>
                      {Object.keys(NETWORK_LABELS).filter(k => k !== "other").map((net) => {
                        const cell = cells.find((c: any) => c.network === net);
                        const val = cell?.count ?? 0;
                        const maxVal = Math.max(...heatmapData.map((c: any) => c.count), 1);
                        const intensity = val / maxVal;
                        return (
                          <td key={net} className="py-3 px-4 text-right tabular-nums font-medium"
                            style={{ backgroundColor: val > 0 ? `rgba(99, 102, 241, ${0.1 + intensity * 0.4})` : undefined }}>
                            {val > 0 ? val.toLocaleString() : "-"}
                          </td>
                        );
                      })}
                      <td className="py-3 px-4 text-right tabular-nums font-bold">{total.toLocaleString()}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Crawler contact rate */}
      {barData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">크롤러 접촉률 (연령대 x 채널)</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={barData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="age_group" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              {channelsInData.map((ch) => (
                <Bar key={ch} dataKey={ch} name={formatChannel(ch)} fill={CHANNEL_COLORS[ch] ?? "#6366f1"} radius={[4, 4, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {!stealthLoading && !stealth?.total_ads && !ratesLoading && (!Array.isArray(rates) || rates.length === 0) && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center shadow-sm">
          <p className="text-sm text-gray-400">접촉률 데이터가 없습니다</p>
          <p className="text-xs text-gray-300 mt-1">stealth_persona_surf.py를 실행하거나 크롤링을 시작해 주세요</p>
        </div>
      )}
    </>
  );
}

// ═══════════════════════════════════════
// Tab 2: 페르소나 랭킹
// ═══════════════════════════════════════

function PersonaRankingTab({ days, setDays }: { days: number; setDays: (d: number) => void }) {
  const [channel, setChannel] = useState("");
  const [selectedPersona, setSelectedPersona] = useState("");

  const { data: rankingData, isLoading: rankLoading } = useQuery({
    queryKey: ["personaRanking", selectedPersona, days, channel],
    queryFn: () =>
      api.getPersonaRanking({
        persona_code: selectedPersona || undefined,
        days, channel: channel || undefined, limit: 20,
      }),
  });

  const { data: heatmapData, isLoading: heatLoading } = useQuery({
    queryKey: ["personaHeatmap", days, channel],
    queryFn: () => api.getPersonaHeatmap({ days, channel: channel || undefined, top_advertisers: 15 }),
  });

  const kpis = useMemo(() => {
    const rankArr = Array.isArray(rankingData) ? rankingData : [];
    if (rankArr.length === 0) return { personas: 0, advertisers: 0, avgContact: 0 };
    const personaCodes = new Set(rankArr.map((r: any) => r.persona_code));
    const advNames = new Set(rankArr.map((r: any) => r.advertiser_name));
    const totalAvg = rankArr.length > 0
      ? rankArr.reduce((s: number, r: any) => s + r.avg_per_session, 0) / rankArr.length : 0;
    return { personas: personaCodes.size, advertisers: advNames.size, avgContact: Math.round(totalAvg * 100) / 100 };
  }, [rankingData]);

  const heatmapGrid = useMemo(() => {
    const heatArr = Array.isArray(heatmapData) ? heatmapData : [];
    if (heatArr.length === 0) return null;
    const personas = [...new Set((heatArr as any[]).map((c) => c.persona_code))];
    const advertisers = [...new Set((heatArr as any[]).map((c) => c.advertiser_name))];
    const lookup: Record<string, any> = {};
    for (const cell of heatArr as any[]) {
      lookup[`${cell.persona_code}__${cell.advertiser_name}`] = cell;
    }
    return { personas, advertisers, lookup };
  }, [heatmapData]);

  const barData = useMemo(() => {
    const rankArr = Array.isArray(rankingData) ? rankingData : [];
    if (rankArr.length === 0) return [];
    const persona = selectedPersona || ((rankArr as any[]).length > 0 ? (rankArr as any[])[0].persona_code : "");
    return (rankArr as any[])
      .filter((r) => r.persona_code === persona)
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 15)
      .map((r) => ({ name: r.advertiser_name, impressions: r.impression_count, sessions: r.session_count, avg: r.avg_per_session }));
  }, [rankingData, selectedPersona]);

  const tableData = useMemo(() => {
    const rankArr = Array.isArray(rankingData) ? rankingData : [];
    if (rankArr.length === 0) return [];
    if (selectedPersona) return (rankArr as any[]).filter((r) => r.persona_code === selectedPersona);
    return rankArr as any[];
  }, [rankingData, selectedPersona]);

  return (
    <>
      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 shadow-sm flex flex-wrap gap-3 items-center">
        <PeriodSelector days={days} onDaysChange={setDays} />
        <select value={channel} onChange={(e) => setChannel(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-adscope-500/20">
          <option value="">전체 채널</option>
          {CHANNELS.filter(Boolean).map((ch) => <option key={ch} value={ch}>{formatChannel(ch)}</option>)}
        </select>
        <select value={selectedPersona} onChange={(e) => setSelectedPersona(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-adscope-500/20">
          <option value="">전체 페르소나</option>
          {PERSONA_CODES.map((code) => <option key={code} value={code}>{personaLabel(code)}</option>)}
        </select>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">페르소나 수</p>
          <p className="text-3xl font-bold text-gray-900 mt-2">{kpis.personas}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">고유 광고주</p>
          <p className="text-3xl font-bold text-gray-900 mt-2">{kpis.advertisers}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">평균 접촉율</p>
          <p className="text-3xl font-bold text-gray-900 mt-2">{kpis.avgContact}</p>
          <p className="text-xs text-gray-400 mt-1">건/세션</p>
        </div>
      </div>

      {/* Heatmap */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
        <h2 className="text-base font-semibold text-gray-900 mb-4">페르소나 x 광고주 히트맵</h2>
        {heatmapGrid ? (
          <div className="overflow-x-auto">
            <table className="text-xs border-collapse">
              <thead>
                <tr>
                  <th className="px-2 py-1.5 text-left text-gray-500 font-semibold sticky left-0 bg-white z-10">페르소나</th>
                  {heatmapGrid.advertisers.map((adv: string) => (
                    <th key={adv} className="px-2 py-1.5 text-center text-gray-500 font-medium max-w-[80px] truncate" title={adv}>
                      {adv.length > 10 ? adv.slice(0, 9) + ".." : adv}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmapGrid.personas.map((persona: string) => (
                  <tr key={persona}>
                    <td className="px-2 py-1.5 font-semibold text-gray-700 sticky left-0 bg-white z-10 whitespace-nowrap">
                      {personaLabel(persona)}
                    </td>
                    {heatmapGrid.advertisers.map((adv: string) => {
                      const cell = heatmapGrid.lookup[`${persona}__${adv}`];
                      const intensity = cell?.intensity ?? 0;
                      const count = cell?.impression_count ?? 0;
                      return (
                        <td key={adv} className={`px-2 py-1.5 text-center rounded-sm ${intensityClass(intensity)}`}
                          title={`${personaLabel(persona)} / ${adv}: ${count}`}>
                          {count > 0 ? count : ""}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-gray-400 text-center py-12">
            {heatLoading ? "로딩 중..." : "히트맵 데이터 없음"}
          </p>
        )}
        <div className="mt-4 flex items-center gap-2 text-xs text-gray-500">
          <span>낮음</span>
          <div className="flex gap-0.5">
            {HEATMAP_COLORS.map((cls) => <div key={cls} className={`w-5 h-4 rounded-sm ${cls}`} />)}
          </div>
          <span>높음</span>
        </div>
      </div>

      {/* Bar chart */}
      {barData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-5">
            상위 광고주{selectedPersona && ` - ${personaLabel(selectedPersona)}`}
          </h2>
          <ResponsiveContainer width="100%" height={Math.max(barData.length * 36, 200)}>
            <BarChart data={barData} layout="vertical" margin={{ left: 120, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 12 }} width={120} />
              <Tooltip formatter={(value: number, name: string) => {
                if (name === "impressions") return [value.toLocaleString(), "노출"];
                return [value, name];
              }} />
              <Bar dataKey="impressions" radius={[0, 4, 4, 0]}>
                {barData.map((_, i) => <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Table */}
      {tableData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-900">상세 데이터</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">페르소나</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">순위</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">광고주</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">노출</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">세션</th>
                  <th className="text-right py-3 px-4 text-xs font-semibold text-gray-500 uppercase">건/세션</th>
                  <th className="text-left py-3 px-4 text-xs font-semibold text-gray-500 uppercase">채널</th>
                </tr>
              </thead>
              <tbody>
                {tableData.map((d: any, i: number) => (
                  <tr key={`${d.persona_code}-${d.advertiser_name}-${i}`} className="border-b border-gray-50 hover:bg-gray-50">
                    <td className="py-3 px-4 font-medium text-gray-700">{personaLabel(d.persona_code)}</td>
                    <td className="py-3 px-4">
                      <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                        d.rank <= 3 ? "bg-adscope-100 text-adscope-700" : "bg-gray-100 text-gray-500"}`}>{d.rank}</span>
                    </td>
                    <td className="py-3 px-4 font-medium">{d.advertiser_name}</td>
                    <td className="py-3 px-4 text-right tabular-nums">{d.impression_count.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right tabular-nums text-gray-600">{d.session_count.toLocaleString()}</td>
                    <td className="py-3 px-4 text-right tabular-nums font-semibold">{d.avg_per_session.toFixed(2)}</td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1">
                        {d.channels.map((ch: string) => (
                          <span key={ch} className="inline-block px-1.5 py-0.5 text-[10px] font-medium bg-gray-100 text-gray-600 rounded">
                            {formatChannel(ch)}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!rankLoading && (!Array.isArray(rankingData) || rankingData.length === 0) && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 shadow-sm text-center">
          <p className="text-gray-400 text-sm">선택한 기간에 페르소나 랭킹 데이터가 없습니다.</p>
        </div>
      )}

      {rankLoading && (
        <div className="bg-white rounded-xl border border-gray-200 p-12 shadow-sm text-center">
          <p className="text-gray-400 text-sm">로딩 중...</p>
        </div>
      )}
    </>
  );
}
