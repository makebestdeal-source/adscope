"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import Link from "next/link";

interface RankingItem {
  launch_product_id: number;
  product_name: string;
  advertiser_id: number;
  advertiser_name: string | null;
  category: string;
  launch_date: string;
  lii_score: number;
  mrs_score: number;
  rv_score: number;
  cs_score: number;
  total_mentions: number;
  impact_phase: string | null;
}

interface LaunchProduct {
  id: number;
  name: string;
  category: string;
  launch_date: string;
  advertiser_id: number;
}

const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  pre_launch: { label: "출시 전", color: "bg-gray-100 text-gray-700" },
  launch_week: { label: "출시 주", color: "bg-blue-100 text-blue-700" },
  growth: { label: "성장", color: "bg-green-100 text-green-700" },
  plateau: { label: "안정", color: "bg-yellow-100 text-yellow-700" },
  decline: { label: "하락", color: "bg-red-100 text-red-700" },
};

const CATEGORY_LABELS: Record<string, { label: string; color: string }> = {
  game: { label: "게임", color: "bg-purple-100 text-purple-700" },
  commerce: { label: "커머스", color: "bg-orange-100 text-orange-700" },
  product: { label: "제품", color: "bg-indigo-100 text-indigo-700" },
};

export default function LaunchImpactPage() {
  const [items, setItems] = useState<RankingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<string>("");
  const [showModal, setShowModal] = useState(false);

  const load = useCallback(async () => {
    try {
      const params = new URLSearchParams({ limit: "30" });
      if (category) params.set("category", category);
      const data = await api.get(`/api/launch-impact/ranking?${params}`);
      setItems(data);
    } catch (e) {
      console.error("Failed to load ranking:", e);
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">신상품 영향력 분석</h1>
          <p className="text-sm text-gray-500 mt-1">
            출시 상품의 매체 파급력(MRS), 반응 속도(RV), 전환 신호(CS)를 종합한 LII 지수
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white"
          >
            <option value="">전체 카테고리</option>
            <option value="game">게임</option>
            <option value="commerce">커머스</option>
            <option value="product">제품</option>
          </select>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            상품 등록
          </button>
        </div>
      </div>

      {/* Score Explanation */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "MRS", desc: "매체 파급력", color: "border-blue-200 bg-blue-50" },
          { label: "RV", desc: "반응 속도", color: "border-green-200 bg-green-50" },
          { label: "CS", desc: "전환 신호", color: "border-orange-200 bg-orange-50" },
          { label: "LII", desc: "종합 임팩트 지수", color: "border-purple-200 bg-purple-50" },
        ].map((card) => (
          <div key={card.label} className={`rounded-lg border p-4 ${card.color}`}>
            <div className="text-sm font-semibold">{card.label}</div>
            <div className="text-xs text-gray-500 mt-0.5">{card.desc}</div>
          </div>
        ))}
      </div>

      {/* Ranking Table */}
      <div className="bg-white rounded-xl border shadow-sm">
        <div className="p-5 border-b">
          <h2 className="text-lg font-semibold">신상품 임팩트 랭킹</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">#</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">상품명</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">광고주</th>
                <th className="px-4 py-3 text-center font-medium text-gray-500">카테고리</th>
                <th className="px-4 py-3 text-center font-medium text-gray-500">LII</th>
                <th className="px-4 py-3 text-center font-medium text-gray-500">MRS</th>
                <th className="px-4 py-3 text-center font-medium text-gray-500">RV</th>
                <th className="px-4 py-3 text-center font-medium text-gray-500">CS</th>
                <th className="px-4 py-3 text-center font-medium text-gray-500">멘션</th>
                <th className="px-4 py-3 text-center font-medium text-gray-500">단계</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((item, idx) => {
                const phase = PHASE_LABELS[item.impact_phase || ""] || { label: "-", color: "bg-gray-50 text-gray-400" };
                const cat = CATEGORY_LABELS[item.category] || { label: item.category, color: "bg-gray-100 text-gray-600" };
                return (
                  <tr key={item.launch_product_id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-400">{idx + 1}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/launch-impact/${item.launch_product_id}`}
                        className="text-blue-600 hover:underline font-medium"
                      >
                        {item.product_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-gray-600">
                      <Link href={`/advertisers/${item.advertiser_id}`} className="hover:underline">
                        {item.advertiser_name || "-"}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded text-xs ${cat.color}`}>{cat.label}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-16 bg-gray-200 rounded-full h-2">
                          <div
                            className="bg-purple-500 h-2 rounded-full"
                            style={{ width: `${item.lii_score}%` }}
                          />
                        </div>
                        <span className="font-semibold">{item.lii_score.toFixed(1)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center">{item.mrs_score.toFixed(1)}</td>
                    <td className="px-4 py-3 text-center">{item.rv_score.toFixed(1)}</td>
                    <td className="px-4 py-3 text-center">{item.cs_score.toFixed(1)}</td>
                    <td className="px-4 py-3 text-center font-medium">{item.total_mentions}</td>
                    <td className="px-4 py-3 text-center">
                      <span className={`px-2 py-1 rounded text-xs ${phase.color}`}>{phase.label}</span>
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-4 py-8 text-center text-gray-400">
                    등록된 상품이 없습니다. "상품 등록" 버튼으로 추적을 시작하세요.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Registration Modal */}
      {showModal && <RegisterModal onClose={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

function RegisterModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("product");
  const [launchDate, setLaunchDate] = useState("");
  const [keywords, setKeywords] = useState("");
  const [productUrl, setProductUrl] = useState("");
  const [advertiserId, setAdvertiserId] = useState("");
  const [advSearch, setAdvSearch] = useState("");
  const [advResults, setAdvResults] = useState<{ id: number; name: string }[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const searchAdvertisers = async (q: string) => {
    if (q.length < 2) { setAdvResults([]); return; }
    try {
      const data = await api.get(`/api/advertisers/search?q=${encodeURIComponent(q)}&limit=10`);
      setAdvResults(data.advertisers || data || []);
    } catch { setAdvResults([]); }
  };

  const handleSubmit = async () => {
    if (!name || !advertiserId || !launchDate || !keywords.trim()) {
      setError("모든 필수 항목을 입력해주세요");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await api.post("/api/launch-impact/products", {
        advertiser_id: Number(advertiserId),
        name,
        category,
        launch_date: new Date(launchDate).toISOString(),
        product_url: productUrl || null,
        keywords: keywords.split(",").map((k) => k.trim()).filter(Boolean),
      });
      onClose();
    } catch (e: any) {
      setError(e.message || "등록 실패");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-white rounded-xl shadow-xl p-6 w-full max-w-md mx-4 space-y-4">
        <h3 className="text-lg font-bold">신상품 등록</h3>

        {/* Advertiser search */}
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">광고주 *</label>
          {advertiserId ? (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">{advResults.find(a => String(a.id) === advertiserId)?.name || `ID: ${advertiserId}`}</span>
              <button onClick={() => { setAdvertiserId(""); setAdvSearch(""); }} className="text-xs text-red-500">변경</button>
            </div>
          ) : (
            <>
              <input
                type="text"
                value={advSearch}
                onChange={(e) => { setAdvSearch(e.target.value); searchAdvertisers(e.target.value); }}
                placeholder="광고주 검색..."
                className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
              />
              {advResults.length > 0 && (
                <div className="mt-1 border rounded-lg max-h-32 overflow-y-auto divide-y">
                  {advResults.map((a) => (
                    <button
                      key={a.id}
                      onClick={() => { setAdvertiserId(String(a.id)); setAdvResults([]); }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50"
                    >
                      {a.name}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">상품명 *</label>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2" placeholder="갤럭시 S26 Ultra" />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">카테고리 *</label>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white">
              <option value="product">제품</option>
              <option value="game">게임</option>
              <option value="commerce">커머스</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">출시일 *</label>
            <input type="date" value={launchDate} onChange={(e) => setLaunchDate(e.target.value)}
              className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2" />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">키워드 * (콤마 구분)</label>
          <input type="text" value={keywords} onChange={(e) => setKeywords(e.target.value)}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
            placeholder="갤럭시 S26, galaxy s26, 삼성 신제품" />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">상품 URL (선택)</label>
          <input type="text" value={productUrl} onChange={(e) => setProductUrl(e.target.value)}
            className="w-full text-sm border border-gray-300 rounded-lg px-3 py-2"
            placeholder="https://smartstore.naver.com/..." />
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}

        <div className="flex gap-2 justify-end pt-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">취소</button>
          <button onClick={handleSubmit} disabled={submitting}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            {submitting ? "등록 중..." : "등록"}
          </button>
        </div>
      </div>
    </div>
  );
}
