"use client";

import { useState, useEffect, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function headers() {
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  return { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

// ── Platform type labels ──
const PLATFORM_TYPE_LABELS: Record<string, string> = {
  search: "검색", display: "디스플레이", video: "영상", social: "소셜",
  commerce: "커머스", programmatic: "프로그래매틱", reward: "리워드",
  affiliate: "제휴", ott: "OTT", audio: "오디오", dooh: "DOOH",
  mobile: "모바일", local: "로컬", messaging: "메시징",
};

const PLATFORM_TYPE_COLORS: Record<string, string> = {
  search: "bg-green-100 text-green-800", display: "bg-blue-100 text-blue-800",
  video: "bg-red-100 text-red-800", social: "bg-purple-100 text-purple-800",
  commerce: "bg-orange-100 text-orange-800", programmatic: "bg-cyan-100 text-cyan-800",
  reward: "bg-yellow-100 text-yellow-800", affiliate: "bg-pink-100 text-pink-800",
  ott: "bg-indigo-100 text-indigo-800", audio: "bg-teal-100 text-teal-800",
  dooh: "bg-amber-100 text-amber-800", mobile: "bg-lime-100 text-lime-800",
  local: "bg-emerald-100 text-emerald-800", messaging: "bg-fuchsia-100 text-fuchsia-800",
};

export default function MasterIndexPage() {
  const [tab, setTab] = useState<"platforms" | "advertisers" | "media-map" | "advertiser-map">("platforms");

  return (
    <div className="p-6 max-w-[1400px] mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-1">마스터 인덱스 관리</h1>
        <p className="text-sm text-slate-400">광고 매체 및 광고주 마스터 데이터베이스</p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 mb-6 bg-slate-800 rounded-lg p-1 w-fit">
        <button
          onClick={() => setTab("platforms")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === "platforms" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
          }`}
        >
          매체 관리
        </button>
        <button
          onClick={() => setTab("advertisers")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === "advertisers" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
          }`}
        >
          광고주 관리
        </button>
        <button
          onClick={() => setTab("media-map")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === "media-map" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
          }`}
        >
          미디어 지도
        </button>
        <button
          onClick={() => setTab("advertiser-map")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === "advertiser-map" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
          }`}
        >
          광고주 지도
        </button>
      </div>

      {tab === "platforms" && <PlatformManager />}
      {tab === "advertisers" && <AdvertiserManager />}
      {tab === "media-map" && <MediaMapView />}
      {tab === "advertiser-map" && <AdvertiserMapView />}
    </div>
  );
}

// ═══════════════════════════════════════════
// PLATFORM MANAGER
// ═══════════════════════════════════════════
function PlatformManager() {
  const [platforms, setPlatforms] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [typeSummary, setTypeSummary] = useState<{type: string; count: number}[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const fetchPlatforms = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (search) params.set("search", search);
    if (typeFilter) params.set("platform_type", typeFilter);
    try {
      const res = await fetch(`${API}/api/master/platforms?${params}`, { headers: headers() });
      const data = await res.json();
      setPlatforms(data.items || []);
      setTotal(data.total || 0);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [page, search, typeFilter]);

  const fetchTypes = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/master/platforms/types`, { headers: headers() });
      const data = await res.json();
      setTypeSummary(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchPlatforms(); }, [fetchPlatforms]);
  useEffect(() => { fetchTypes(); }, [fetchTypes]);

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`'${name}' 매체를 삭제하시겠습니까?`)) return;
    await fetch(`${API}/api/master/platforms/${id}`, { method: "DELETE", headers: headers() });
    fetchPlatforms();
    fetchTypes();
  };

  const totalPages = Math.ceil(total / 50);

  return (
    <div>
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
        <div className="bg-slate-800 rounded-lg p-3">
          <div className="text-2xl font-bold text-white">{total}</div>
          <div className="text-xs text-slate-400">전체 매체</div>
        </div>
        {typeSummary.slice(0, 5).map((t) => (
          <div key={t.type} className="bg-slate-800 rounded-lg p-3">
            <div className="text-xl font-bold text-white">{t.count}</div>
            <div className="text-xs text-slate-400">{PLATFORM_TYPE_LABELS[t.type] || t.type}</div>
          </div>
        ))}
      </div>

      {/* Search + Filter */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="text"
          placeholder="매체명 검색..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="bg-slate-800 text-white rounded-lg px-4 py-2 text-sm w-64 border border-slate-700 focus:border-indigo-500 focus:outline-none"
        />
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
          className="bg-slate-800 text-white rounded-lg px-3 py-2 text-sm border border-slate-700"
        >
          <option value="">전체 유형</option>
          {Object.entries(PLATFORM_TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <button
          onClick={() => setShowAdd(true)}
          className="ml-auto bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          + 매체 등록
        </button>
      </div>

      {/* Table */}
      <div className="bg-slate-800 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left px-4 py-3 text-slate-400 font-medium">운영사</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">플랫폼</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">서비스명</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">유형</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">과금</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">MAU/규모</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">URL</th>
                <th className="text-center px-4 py-3 text-slate-400 font-medium">작업</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">로딩 중...</td></tr>
              ) : platforms.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">데이터 없음</td></tr>
              ) : platforms.map((p) => (
                <tr key={p.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                  <td className="px-4 py-3 text-slate-300">{p.operator_name}</td>
                  <td className="px-4 py-3 text-white font-medium">{p.platform_name}</td>
                  <td className="px-4 py-3 text-slate-300 text-xs">{p.service_name || "-"}</td>
                  <td className="px-4 py-3">
                    {p.platform_type && (
                      <span className={`text-xs px-2 py-0.5 rounded ${PLATFORM_TYPE_COLORS[p.platform_type] || "bg-slate-600 text-slate-300"}`}>
                        {PLATFORM_TYPE_LABELS[p.platform_type] || p.platform_type}
                      </span>
                    )}
                    {p.sub_type && (
                      <span className="text-xs text-slate-500 ml-1">{p.sub_type}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {(p.billing_types || []).join(", ")}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">{p.monthly_reach || "-"}</td>
                  <td className="px-4 py-3">
                    {p.url ? (
                      <a href={p.url} target="_blank" rel="noopener noreferrer" className="text-xs text-indigo-400 hover:underline truncate block max-w-[200px]">
                        {p.url.replace(/^https?:\/\//, "")}
                      </a>
                    ) : "-"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button onClick={() => handleDelete(p.id, p.platform_name)} className="text-red-400 hover:text-red-300 text-xs">
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex justify-center gap-2 py-4 border-t border-slate-700">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-3 py-1 text-sm text-slate-400 hover:text-white disabled:opacity-30">이전</button>
            <span className="px-3 py-1 text-sm text-slate-300">{page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="px-3 py-1 text-sm text-slate-400 hover:text-white disabled:opacity-30">다음</button>
          </div>
        )}
      </div>

      {/* Add Modal */}
      {showAdd && (
        <PlatformAddModal onClose={() => setShowAdd(false)} onSaved={() => { setShowAdd(false); fetchPlatforms(); fetchTypes(); }} />
      )}
    </div>
  );
}

function PlatformAddModal({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    operator_name: "", platform_name: "", service_name: "",
    platform_type: "display", sub_type: "", url: "",
    description: "", billing_types: "CPC", monthly_reach: "", notes: "",
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!form.operator_name || !form.platform_name) return alert("운영사와 플랫폼명은 필수입니다.");
    setSaving(true);
    await fetch(`${API}/api/master/platforms`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        ...form,
        billing_types: form.billing_types.split(",").map((s) => s.trim()).filter(Boolean),
      }),
    });
    setSaving(false);
    onSaved();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-800 rounded-xl p-6 w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-white mb-4">매체 등록</h3>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">운영사 *</label>
              <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.operator_name} onChange={(e) => setForm({ ...form, operator_name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">플랫폼명 *</label>
              <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.platform_name} onChange={(e) => setForm({ ...form, platform_name: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">서비스명</label>
            <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.service_name} onChange={(e) => setForm({ ...form, service_name: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">매체 유형</label>
              <select className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.platform_type} onChange={(e) => setForm({ ...form, platform_type: e.target.value })}>
                {Object.entries(PLATFORM_TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">서브 유형</label>
              <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" placeholder="dsp, ssp, ad_network..." value={form.sub_type} onChange={(e) => setForm({ ...form, sub_type: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">URL</label>
            <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" placeholder="https://..." value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">과금 유형 (쉼표 구분)</label>
              <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" placeholder="CPC, CPM" value={form.billing_types} onChange={(e) => setForm({ ...form, billing_types: e.target.value })} />
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">MAU/규모</label>
              <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.monthly_reach} onChange={(e) => setForm({ ...form, monthly_reach: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">설명</label>
            <textarea className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm h-20" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white">취소</button>
          <button onClick={handleSave} disabled={saving} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">
            {saving ? "저장 중..." : "등록"}
          </button>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════
// ADVERTISER MANAGER
// ═══════════════════════════════════════════
function AdvertiserManager() {
  const [advertisers, setAdvertisers] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<any>({});
  const [industries, setIndustries] = useState<{id: number; name: string}[]>([]);
  const [search, setSearch] = useState("");
  const [industryFilter, setIndustryFilter] = useState("");
  const [websiteFilter, setWebsiteFilter] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [showAdd, setShowAdd] = useState(false);

  const fetchAdvertisers = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), page_size: "50" });
    if (search) params.set("search", search);
    if (industryFilter) params.set("industry_id", industryFilter);
    if (websiteFilter === "yes") params.set("has_website", "true");
    if (websiteFilter === "no") params.set("has_website", "false");
    try {
      const res = await fetch(`${API}/api/master/advertisers?${params}`, { headers: headers() });
      const data = await res.json();
      setAdvertisers(data.items || []);
      setTotal(data.total || 0);
      if (data.industries) setIndustries(data.industries);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, [page, search, industryFilter, websiteFilter]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/master/advertisers/stats`, { headers: headers() });
      setStats(await res.json());
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { fetchAdvertisers(); }, [fetchAdvertisers]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`'${name}' 광고주를 삭제하시겠습니까? 관련 소재/캠페인도 삭제됩니다.`)) return;
    await fetch(`${API}/api/master/advertisers/${id}`, { method: "DELETE", headers: headers() });
    fetchAdvertisers();
    fetchStats();
  };

  const totalPages = Math.ceil(total / 50);

  return (
    <div>
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
        <div className="bg-slate-800 rounded-lg p-3">
          <div className="text-2xl font-bold text-white">{stats.total || 0}</div>
          <div className="text-xs text-slate-400">전체 광고주</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3">
          <div className="text-2xl font-bold text-green-400">{stats.has_website || 0}</div>
          <div className="text-xs text-slate-400">웹사이트 확인</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3">
          <div className="text-2xl font-bold text-blue-400">{stats.has_channels || 0}</div>
          <div className="text-xs text-slate-400">채널 보유</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3">
          <div className="text-2xl font-bold text-purple-400">{stats.has_industry || 0}</div>
          <div className="text-xs text-slate-400">산업 분류</div>
        </div>
        <div className="bg-slate-800 rounded-lg p-3">
          <div className="text-2xl font-bold text-amber-400">{stats.has_type || 0}</div>
          <div className="text-xs text-slate-400">유형 지정</div>
        </div>
      </div>

      {/* Search + Filter */}
      <div className="flex flex-wrap gap-3 mb-4">
        <input
          type="text"
          placeholder="광고주명 검색..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="bg-slate-800 text-white rounded-lg px-4 py-2 text-sm w-64 border border-slate-700 focus:border-indigo-500 focus:outline-none"
        />
        <select
          value={industryFilter}
          onChange={(e) => { setIndustryFilter(e.target.value); setPage(1); }}
          className="bg-slate-800 text-white rounded-lg px-3 py-2 text-sm border border-slate-700"
        >
          <option value="">전체 산업</option>
          {industries.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
        </select>
        <select
          value={websiteFilter}
          onChange={(e) => { setWebsiteFilter(e.target.value); setPage(1); }}
          className="bg-slate-800 text-white rounded-lg px-3 py-2 text-sm border border-slate-700"
        >
          <option value="">웹사이트 전체</option>
          <option value="yes">확인됨</option>
          <option value="no">미확인</option>
        </select>
        <button
          onClick={() => setShowAdd(true)}
          className="ml-auto bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium"
        >
          + 광고주 등록
        </button>
      </div>

      {/* Table */}
      <div className="bg-slate-800 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left px-4 py-3 text-slate-400 font-medium">광고주명</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">산업</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">유형</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">웹사이트</th>
                <th className="text-center px-4 py-3 text-slate-400 font-medium">채널</th>
                <th className="text-center px-4 py-3 text-slate-400 font-medium">소재수</th>
                <th className="text-left px-4 py-3 text-slate-400 font-medium">출처</th>
                <th className="text-center px-4 py-3 text-slate-400 font-medium">작업</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">로딩 중...</td></tr>
              ) : advertisers.length === 0 ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">데이터 없음</td></tr>
              ) : advertisers.map((a) => {
                const channelCount = a.official_channels ? Object.keys(a.official_channels).length : 0;
                return (
                  <tr key={a.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="px-4 py-3">
                      <div className="text-white font-medium">{a.name}</div>
                      {a.brand_name && a.brand_name !== a.name && (
                        <div className="text-xs text-slate-500">{a.brand_name}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-300">{a.industry_name || "-"}</td>
                    <td className="px-4 py-3">
                      {a.advertiser_type && (
                        <span className="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300">{a.advertiser_type}</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {a.website ? (
                        <a href={`https://${a.website}`} target="_blank" rel="noopener noreferrer" className="text-xs text-indigo-400 hover:underline">
                          {a.website}
                        </a>
                      ) : (
                        <span className="text-xs text-red-400">미확인</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {channelCount > 0 ? (
                        <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded">{channelCount}</span>
                      ) : (
                        <span className="text-xs text-slate-500">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center text-xs text-slate-300">{a.ad_count || 0}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">{a.data_source || "-"}</td>
                    <td className="px-4 py-3 text-center">
                      <button onClick={() => handleDelete(a.id, a.name)} className="text-red-400 hover:text-red-300 text-xs">
                        삭제
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex justify-center gap-2 py-4 border-t border-slate-700">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="px-3 py-1 text-sm text-slate-400 hover:text-white disabled:opacity-30">이전</button>
            <span className="px-3 py-1 text-sm text-slate-300">{page} / {totalPages}</span>
            <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} className="px-3 py-1 text-sm text-slate-400 hover:text-white disabled:opacity-30">다음</button>
          </div>
        )}
      </div>

      {/* Add Modal */}
      {showAdd && (
        <AdvertiserAddModal
          industries={industries}
          onClose={() => setShowAdd(false)}
          onSaved={() => { setShowAdd(false); fetchAdvertisers(); fetchStats(); }}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════
// MEDIA MAP VIEW
// ═══════════════════════════════════════════
function MediaMapView() {
  const [platforms, setPlatforms] = useState<any[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/api/master/platforms?page_size=200`, { headers: headers() });
        const data = await res.json();
        setPlatforms(data.items || []);
      } catch (e) { console.error(e); }
      setLoading(false);
    })();
  }, []);

  // Build tree: type -> operator -> services
  const tree: Record<string, Record<string, any[]>> = {};
  for (const p of platforms) {
    const type = p.platform_type || "기타";
    const op = p.operator_name;
    if (!tree[type]) tree[type] = {};
    if (!tree[type][op]) tree[type][op] = [];
    tree[type][op].push(p);
  }

  const toggle = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  if (loading) return <div className="text-slate-400 py-8 text-center">로딩 중...</div>;

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">미디어 지도</h3>
        <span className="text-sm text-slate-400">{platforms.length}개 매체</span>
      </div>
      <div className="space-y-1">
        {Object.entries(tree).sort((a, b) => {
          const countA = Object.values(a[1]).reduce((s, arr) => s + arr.length, 0);
          const countB = Object.values(b[1]).reduce((s, arr) => s + arr.length, 0);
          return countB - countA;
        }).map(([type, operators]) => {
          const typeKey = `type-${type}`;
          const typeCount = Object.values(operators).reduce((s, arr) => s + arr.length, 0);
          const isTypeOpen = expanded.has(typeKey);
          return (
            <div key={type}>
              <button
                onClick={() => toggle(typeKey)}
                className="flex items-center gap-2 w-full px-3 py-2 rounded hover:bg-slate-700/50 transition-colors"
              >
                <span className="text-slate-500 text-xs w-4">{isTypeOpen ? "▼" : "▶"}</span>
                <span className={`text-xs px-2 py-0.5 rounded ${PLATFORM_TYPE_COLORS[type] || "bg-slate-600 text-slate-300"}`}>
                  {PLATFORM_TYPE_LABELS[type] || type}
                </span>
                <span className="text-white font-medium text-sm">{typeCount}개 매체</span>
              </button>
              {isTypeOpen && (
                <div className="ml-6 border-l border-slate-700 pl-2">
                  {Object.entries(operators).sort((a, b) => b[1].length - a[1].length).map(([op, services]) => {
                    const opKey = `op-${type}-${op}`;
                    const isOpOpen = expanded.has(opKey);
                    return (
                      <div key={op}>
                        <button
                          onClick={() => toggle(opKey)}
                          className="flex items-center gap-2 w-full px-3 py-1.5 rounded hover:bg-slate-700/30 transition-colors"
                        >
                          <span className="text-slate-600 text-xs w-4">{isOpOpen ? "▼" : "▶"}</span>
                          <span className="text-slate-200 text-sm font-medium">{op}</span>
                          <span className="text-slate-500 text-xs">({services.length})</span>
                        </button>
                        {isOpOpen && (
                          <div className="ml-8 space-y-0.5">
                            {services.map((s: any) => (
                              <div key={s.id} className="flex items-center gap-2 px-3 py-1 text-xs">
                                <span className="text-slate-500">└</span>
                                <span className="text-slate-300">{s.service_name || s.platform_name}</span>
                                {s.billing_types && s.billing_types.length > 0 && (
                                  <span className="text-slate-500">[{(s.billing_types || []).join("/")}]</span>
                                )}
                                {s.monthly_reach && (
                                  <span className="text-blue-400">{s.monthly_reach}</span>
                                )}
                                {s.url && (
                                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:underline ml-auto truncate max-w-[200px]">
                                    {s.url.replace(/^https?:\/\//, "")}
                                  </a>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════
// ADVERTISER MAP VIEW
// ═══════════════════════════════════════════
function AdvertiserMapView() {
  const [advertisers, setAdvertisers] = useState<any[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/api/master/advertisers?page_size=200`, { headers: headers() });
        const data = await res.json();
        setAdvertisers(data.items || []);
      } catch (e) { console.error(e); }
      setLoading(false);
    })();
  }, []);

  // Build tree: industry -> type -> advertisers
  const tree: Record<string, Record<string, any[]>> = {};
  for (const a of advertisers) {
    const ind = a.industry_name || "미분류";
    const type = a.advertiser_type || "미지정";
    if (!tree[ind]) tree[ind] = {};
    if (!tree[ind][type]) tree[ind][type] = [];
    tree[ind][type].push(a);
  }

  const toggle = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const TYPE_LABELS: Record<string, string> = {
    group: "그룹", company: "기업", brand: "브랜드", product: "제품",
  };

  if (loading) return <div className="text-slate-400 py-8 text-center">로딩 중...</div>;

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">광고주 지도</h3>
        <span className="text-sm text-slate-400">{advertisers.length}개 광고주</span>
      </div>
      <div className="space-y-1">
        {Object.entries(tree).sort((a, b) => {
          const countA = Object.values(a[1]).reduce((s, arr) => s + arr.length, 0);
          const countB = Object.values(b[1]).reduce((s, arr) => s + arr.length, 0);
          return countB - countA;
        }).map(([ind, types]) => {
          const indKey = `ind-${ind}`;
          const indCount = Object.values(types).reduce((s, arr) => s + arr.length, 0);
          const isIndOpen = expanded.has(indKey);
          return (
            <div key={ind}>
              <button onClick={() => toggle(indKey)} className="flex items-center gap-2 w-full px-3 py-2 rounded hover:bg-slate-700/50 transition-colors">
                <span className="text-slate-500 text-xs w-4">{isIndOpen ? "▼" : "▶"}</span>
                <span className="text-white font-medium text-sm">{ind}</span>
                <span className="text-slate-500 text-xs">({indCount})</span>
              </button>
              {isIndOpen && (
                <div className="ml-6 border-l border-slate-700 pl-2">
                  {Object.entries(types).sort((a, b) => b[1].length - a[1].length).map(([type, advs]) => {
                    const typeKey = `type-${ind}-${type}`;
                    const isTypeOpen = expanded.has(typeKey);
                    return (
                      <div key={type}>
                        <button onClick={() => toggle(typeKey)} className="flex items-center gap-2 w-full px-3 py-1.5 rounded hover:bg-slate-700/30 transition-colors">
                          <span className="text-slate-600 text-xs w-4">{isTypeOpen ? "▼" : "▶"}</span>
                          <span className="text-xs px-2 py-0.5 rounded bg-slate-600 text-slate-300">{TYPE_LABELS[type] || type}</span>
                          <span className="text-slate-400 text-xs">({advs.length})</span>
                        </button>
                        {isTypeOpen && (
                          <div className="ml-8 space-y-0.5">
                            {advs.map((a: any) => {
                              const channelCount = a.official_channels ? Object.keys(a.official_channels).length : 0;
                              return (
                                <div key={a.id} className="flex items-center gap-2 px-3 py-1 text-xs">
                                  <span className="text-slate-500">└</span>
                                  <span className="text-slate-200 font-medium">{a.name}</span>
                                  {a.website ? (
                                    <a href={`https://${a.website}`} target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:underline">
                                      {a.website}
                                    </a>
                                  ) : (
                                    <span className="text-red-400/60">URL없음</span>
                                  )}
                                  {channelCount > 0 && <span className="text-blue-400">CH:{channelCount}</span>}
                                  {a.ad_count > 0 && <span className="text-green-400 ml-auto">소재 {a.ad_count}</span>}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AdvertiserAddModal({ industries, onClose, onSaved }: { industries: {id: number; name: string}[]; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({
    name: "", industry_id: "", advertiser_type: "company",
    brand_name: "", website: "", description: "", headquarters: "",
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!form.name) return alert("광고주명은 필수입니다.");
    setSaving(true);
    await fetch(`${API}/api/master/advertisers`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        ...form,
        industry_id: form.industry_id ? parseInt(form.industry_id) : null,
        data_source: "manual",
      }),
    });
    setSaving(false);
    onSaved();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-slate-800 rounded-xl p-6 w-full max-w-lg mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-white mb-4">광고주 등록</h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">광고주명 *</label>
            <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 mb-1 block">산업</label>
              <select className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.industry_id} onChange={(e) => setForm({ ...form, industry_id: e.target.value })}>
                <option value="">선택 안 함</option>
                {industries.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-slate-400 mb-1 block">유형</label>
              <select className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.advertiser_type} onChange={(e) => setForm({ ...form, advertiser_type: e.target.value })}>
                <option value="group">그룹</option>
                <option value="company">기업</option>
                <option value="brand">브랜드</option>
                <option value="product">제품</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">브랜드명</label>
            <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.brand_name} onChange={(e) => setForm({ ...form, brand_name: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">공식 웹사이트</label>
            <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" placeholder="example.com" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">본사 위치</label>
            <input className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm" value={form.headquarters} onChange={(e) => setForm({ ...form, headquarters: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">설명</label>
            <textarea className="w-full bg-slate-700 text-white rounded px-3 py-2 text-sm h-16" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </div>
        </div>
        <div className="flex justify-end gap-3 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white">취소</button>
          <button onClick={handleSave} disabled={saving} className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">
            {saving ? "저장 중..." : "등록"}
          </button>
        </div>
      </div>
    </div>
  );
}
