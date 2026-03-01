"use client";

import { useState, useEffect, useCallback } from "react";
import { getToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface StagingStats {
  total: number;
  approved: number;
  rejected: number;
  quarantine: number;
  pending: number;
  promoted: number;
}

interface BatchSummary {
  batch_id: string;
  channel: string;
  created_at: string | null;
  total: number;
  approved: number;
  rejected: number;
  quarantine: number;
  pending: number;
  promoted: number;
}

interface StagingAd {
  id: number;
  status: string;
  rejection_reason: string | null;
  wash_score: number | null;
  channel: string;
  keyword: string;
  advertiser_name: string | null;
  resolved_advertiser_name: string | null;
  ad_text: string | null;
  url: string | null;
  promoted_at: string | null;
  promoted_ad_detail_id: number | null;
}

async function apiFetch(path: string, opts?: RequestInit) {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts?.headers || {}),
    },
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

const STATUS_COLORS: Record<string, string> = {
  approved: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  quarantine: "bg-yellow-100 text-yellow-800",
  pending: "bg-gray-100 text-gray-600",
};

const CHANNEL_LABELS: Record<string, string> = {
  naver_search: "N-Search",
  naver_da: "N-DA",
  youtube_ads: "YT-Ads",
  google_gdn: "GDN",
  kakao_da: "Kakao",
  meta: "Meta",
  tiktok_ads: "TikTok",
  naver_shopping: "N-Shop",
};

export default function StagingPage() {
  const [stats, setStats] = useState<StagingStats | null>(null);
  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<string | null>(null);
  const [batchAds, setBatchAds] = useState<StagingAd[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [s, b] = await Promise.all([
        apiFetch("/api/staging/stats"),
        apiFetch("/api/staging/batches?limit=50"),
      ]);
      setStats(s);
      setBatches(b);
    } catch (e) {
      console.error("Failed to load staging data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const loadBatchDetail = async (batchId: string) => {
    setSelectedBatch(batchId);
    try {
      const data = await apiFetch(`/api/staging/batch/${batchId}`);
      setBatchAds(data.ads || []);
    } catch (e) {
      console.error("Failed to load batch:", e);
    }
  };

  const handleApprove = async (batchId: string) => {
    try {
      await apiFetch(`/api/staging/approve/${batchId}`, { method: "POST" });
      await loadData();
      if (selectedBatch === batchId) await loadBatchDetail(batchId);
    } catch (e) {
      console.error("Approve failed:", e);
    }
  };

  const handleReject = async (batchId: string) => {
    try {
      await apiFetch(`/api/staging/reject/${batchId}`, { method: "POST" });
      await loadData();
      if (selectedBatch === batchId) await loadBatchDetail(batchId);
    } catch (e) {
      console.error("Reject failed:", e);
    }
  };

  const handleApproveAd = async (adId: number) => {
    try {
      await apiFetch(`/api/staging/approve-ad/${adId}`, { method: "POST" });
      if (selectedBatch) await loadBatchDetail(selectedBatch);
      await loadData();
    } catch (e) {
      console.error("Approve ad failed:", e);
    }
  };

  const handleRejectAd = async (adId: number) => {
    try {
      await apiFetch(`/api/staging/reject-ad/${adId}?reason=manual_reject`, { method: "POST" });
      if (selectedBatch) await loadBatchDetail(selectedBatch);
      await loadData();
    } catch (e) {
      console.error("Reject ad failed:", e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">
          Data Staging Monitor
        </h1>

        {/* Stats Cards */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-8">
            {[
              { label: "Total", value: stats.total, color: "bg-white" },
              { label: "Approved", value: stats.approved, color: "bg-green-50 border-green-200" },
              { label: "Promoted", value: stats.promoted, color: "bg-blue-50 border-blue-200" },
              { label: "Rejected", value: stats.rejected, color: "bg-red-50 border-red-200" },
              { label: "Quarantine", value: stats.quarantine, color: "bg-yellow-50 border-yellow-200" },
              { label: "Pending", value: stats.pending, color: "bg-gray-50 border-gray-200" },
            ].map((card) => (
              <div key={card.label} className={`rounded-lg border p-4 ${card.color}`}>
                <div className="text-sm text-gray-500">{card.label}</div>
                <div className="text-2xl font-bold mt-1">{card.value.toLocaleString()}</div>
              </div>
            ))}
          </div>
        )}

        {/* Approval Rate */}
        {stats && stats.total > 0 && (
          <div className="bg-white rounded-lg border p-4 mb-8">
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-500">Approval Rate:</span>
              <div className="flex-1 bg-gray-200 rounded-full h-4 overflow-hidden">
                <div
                  className="bg-green-500 h-full rounded-full transition-all"
                  style={{ width: `${(stats.approved / stats.total) * 100}%` }}
                />
              </div>
              <span className="text-sm font-medium">
                {((stats.approved / stats.total) * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Batch List */}
          <div className="bg-white rounded-lg border">
            <div className="p-4 border-b">
              <h2 className="text-lg font-semibold">Recent Batches</h2>
            </div>
            <div className="divide-y max-h-[600px] overflow-y-auto">
              {batches.map((b) => (
                <div
                  key={b.batch_id}
                  className={`p-3 cursor-pointer hover:bg-gray-50 ${
                    selectedBatch === b.batch_id ? "bg-blue-50" : ""
                  }`}
                  onClick={() => loadBatchDetail(b.batch_id)}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-mono text-gray-400">
                        {b.batch_id.slice(0, 8)}
                      </span>
                      <span className="ml-2 px-2 py-0.5 text-xs rounded bg-gray-100">
                        {CHANNEL_LABELS[b.channel] || b.channel}
                      </span>
                    </div>
                    <div className="text-xs text-gray-400">
                      {b.created_at ? new Date(b.created_at).toLocaleString("ko-KR") : ""}
                    </div>
                  </div>
                  <div className="flex gap-2 mt-1">
                    <span className="text-xs bg-green-100 text-green-700 px-1.5 rounded">
                      {b.approved}ok
                    </span>
                    <span className="text-xs bg-red-100 text-red-700 px-1.5 rounded">
                      {b.rejected}rej
                    </span>
                    {b.quarantine > 0 && (
                      <span className="text-xs bg-yellow-100 text-yellow-700 px-1.5 rounded">
                        {b.quarantine}q
                      </span>
                    )}
                    <span className="text-xs bg-blue-100 text-blue-700 px-1.5 rounded">
                      {b.promoted}prom
                    </span>
                    <span className="text-xs text-gray-400 ml-auto">{b.total} total</span>
                  </div>
                  {b.quarantine > 0 && (
                    <div className="flex gap-2 mt-2">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleApprove(b.batch_id); }}
                        className="text-xs px-2 py-1 bg-green-600 text-white rounded hover:bg-green-700"
                      >
                        Approve All
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleReject(b.batch_id); }}
                        className="text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700"
                      >
                        Reject All
                      </button>
                    </div>
                  )}
                </div>
              ))}
              {batches.length === 0 && (
                <div className="p-6 text-center text-gray-400">No batches yet</div>
              )}
            </div>
          </div>

          {/* Batch Detail */}
          <div className="bg-white rounded-lg border">
            <div className="p-4 border-b">
              <h2 className="text-lg font-semibold">
                {selectedBatch ? `Batch ${selectedBatch.slice(0, 8)}...` : "Select a batch"}
              </h2>
            </div>
            <div className="divide-y max-h-[600px] overflow-y-auto">
              {batchAds.map((ad) => (
                <div key={ad.id} className="p-3">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${STATUS_COLORS[ad.status] || ""}`}>
                          {ad.status}
                        </span>
                        {ad.wash_score !== null && (
                          <span className="text-xs text-gray-400">
                            score: {ad.wash_score}
                          </span>
                        )}
                      </div>
                      <div className="text-sm font-medium truncate">
                        {ad.resolved_advertiser_name || ad.advertiser_name || "(unknown)"}
                      </div>
                      <div className="text-xs text-gray-500 truncate mt-0.5">
                        {ad.ad_text || "(no text)"}
                      </div>
                      {ad.rejection_reason && (
                        <div className="text-xs text-red-500 mt-0.5">{ad.rejection_reason}</div>
                      )}
                      {ad.promoted_at && (
                        <div className="text-xs text-blue-500 mt-0.5">
                          Promoted: {new Date(ad.promoted_at).toLocaleString("ko-KR")}
                        </div>
                      )}
                    </div>
                    {ad.status === "quarantine" && (
                      <div className="flex gap-1 ml-2 shrink-0">
                        <button
                          onClick={() => handleApproveAd(ad.id)}
                          className="text-xs px-2 py-1 bg-green-600 text-white rounded"
                        >
                          OK
                        </button>
                        <button
                          onClick={() => handleRejectAd(ad.id)}
                          className="text-xs px-2 py-1 bg-red-600 text-white rounded"
                        >
                          Rej
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {batchAds.length === 0 && selectedBatch && (
                <div className="p-6 text-center text-gray-400">No ads in this batch</div>
              )}
              {!selectedBatch && (
                <div className="p-6 text-center text-gray-400">
                  Click a batch to view details
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
