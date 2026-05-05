"use client";

import { useState, useRef, useEffect } from "react";
import { isPaid } from "@/lib/auth";

function showUpgradeAlert() {
  alert("다운로드는 유료 회원 전용 기능입니다.\n플랜을 업그레이드해주세요.\n\n문의: support@adscope.kr");
}

export async function authDownload(url: string): Promise<boolean> {
  const token = localStorage.getItem("adscope_token");
  if (!token) {
    alert("로그인이 필요합니다.");
    window.location.href = "/login";
    return false;
  }

  const fp = localStorage.getItem("adscope_device_fp") || "";

  // 권한 체크 (HEAD 요청)
  try {
    const res = await fetch(url, {
      method: "HEAD",
      headers: {
        "Authorization": `Bearer ${token}`,
        "X-Device-Fingerprint": fp,
      },
    });
    if (res.status === 403) {
      showUpgradeAlert();
      window.location.href = "/pricing";
      return false;
    }
    if (res.status === 401) {
      alert("로그인이 필요합니다.");
      window.location.href = "/login";
      return false;
    }
  } catch {
    // HEAD not supported, proceed
  }

  // 실제 다운로드 (토큰을 쿼리로 전달)
  const sep = url.includes("?") ? "&" : "?";
  const a = document.createElement("a");
  a.href = `${url}${sep}_token=${token}`;
  a.click();
  return true;
}

interface DownloadButtonProps {
  url: string;
  label: string;
  icon?: "excel" | "zip" | "csv";
  className?: string;
}

/**
 * Single download button that triggers a file download with auth token.
 */
export function DownloadButton({
  url,
  label,
  icon = "excel",
  className = "",
}: DownloadButtonProps) {
  const [loading, setLoading] = useState(false);

  const iconColors: Record<string, string> = {
    excel: "bg-green-100 text-green-700",
    zip: "bg-purple-100 text-purple-700",
    csv: "bg-gray-100 text-gray-600",
  };

  const iconLabels: Record<string, string> = {
    excel: "XLS",
    zip: "ZIP",
    csv: "CSV",
  };

  const handleDownload = async () => {
    if (!isPaid()) {
      showUpgradeAlert();
      window.location.href = "/pricing";
      return;
    }
    setLoading(true);
    await authDownload(url);
    setTimeout(() => setLoading(false), 2000);
  };

  return (
    <button
      onClick={handleDownload}
      disabled={loading}
      title={isPaid() ? label : "유료 회원 전용"}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg transition-colors disabled:opacity-50 ${className || "text-gray-600 bg-white border-gray-200 hover:bg-gray-50"}`}
    >
      <span className={`w-5 h-5 rounded flex items-center justify-center text-[9px] font-bold ${iconColors[icon]}`}>
        {iconLabels[icon]}
      </span>
      {loading ? "..." : label}
    </button>
  );
}

interface ReportBundleButtonProps {
  advertiserId: number;
  days?: number;
}

export function ReportBundleButton({ advertiserId, days = 30 }: ReportBundleButtonProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleDownload = async () => {
    if (!isPaid()) {
      showUpgradeAlert();
      window.location.href = "/pricing";
      return;
    }
    setLoading(true);
    try {
      await authDownload(`/api/reports/advertiser/${advertiserId}/bundle?days=${days}`);
      setOpen(false);
    } finally {
      setTimeout(() => setLoading(false), 2000);
    }
  };

  return (
    <>
      <button
        onClick={() => {
          if (!isPaid()) {
            showUpgradeAlert();
            window.location.href = "/pricing";
            return;
          }
          setOpen(true);
        }}
        disabled={loading}
        title="보고서 양식 선택"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-teal-700 bg-teal-50 border border-teal-200 rounded-lg hover:bg-teal-100 transition-colors disabled:opacity-50"
      >
        <span className="w-5 h-5 rounded flex items-center justify-center text-[9px] font-bold bg-teal-100 text-teal-700">
          ZIP
        </span>
        {loading ? "생성 중..." : "보고서 양식"}
      </button>

      {open && (
        <div className="fixed inset-0 z-[100] bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-3xl bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-slate-900">보고서 양식 선택</h2>
                <p className="text-xs text-slate-500 mt-1">선택 기간 {days}일 기준으로 PPT, PDF, XLSX를 함께 생성합니다.</p>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="w-8 h-8 rounded-lg text-slate-500 hover:bg-slate-100"
                aria-label="닫기"
              >
                ×
              </button>
            </div>

            <div className="p-6 grid md:grid-cols-[1fr_1.05fr] gap-5">
              <button
                onClick={handleDownload}
                disabled={loading}
                className="text-left rounded-lg border-2 border-teal-500 bg-teal-50/60 p-5 hover:bg-teal-50 transition-colors disabled:opacity-60"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-bold text-teal-800">요약형 리포트</p>
                    <p className="text-xs text-teal-700 mt-1">광고주 활동 요약, 채널, 소재, 캠페인</p>
                  </div>
                  <span className="text-[10px] font-bold text-white bg-teal-600 px-2 py-1 rounded">기본</span>
                </div>
                <div className="mt-5 aspect-[16/9] rounded-lg bg-white border border-teal-100 p-4">
                  <div className="h-2 w-16 rounded bg-teal-500 mb-4" />
                  <div className="h-5 w-4/5 rounded bg-slate-800 mb-3" />
                  <div className="h-2 w-2/3 rounded bg-slate-200 mb-5" />
                  <div className="grid grid-cols-4 gap-2">
                    {[0, 1, 2, 3].map((i) => (
                      <div key={i} className="h-12 rounded border border-slate-100 bg-slate-50" />
                    ))}
                  </div>
                  <div className="mt-4 space-y-2">
                    <div className="h-2 rounded bg-slate-200" />
                    <div className="h-2 w-10/12 rounded bg-slate-200" />
                    <div className="h-2 w-8/12 rounded bg-slate-200" />
                  </div>
                </div>
                <p className="mt-4 text-xs font-medium text-teal-800">
                  {loading ? "보고서를 생성하고 있습니다..." : "이 양식으로 ZIP 생성"}
                </p>
              </button>

              <div className="rounded-lg border border-slate-200 p-5">
                <p className="text-sm font-semibold text-slate-900 mb-3">포함 내용</p>
                <div className="space-y-3 text-sm text-slate-700">
                  <div className="flex gap-2"><span className="font-bold text-slate-900">1.</span><span>표지: 광고주명, 분석 기간, 생성일</span></div>
                  <div className="flex gap-2"><span className="font-bold text-slate-900">2.</span><span>요약: 소재 수, 캠페인 수, 추정 광고비, 주요 채널</span></div>
                  <div className="flex gap-2"><span className="font-bold text-slate-900">3.</span><span>채널: 채널별 소재 수, 관측일, 추정 광고비</span></div>
                  <div className="flex gap-2"><span className="font-bold text-slate-900">4.</span><span>소재: 실제 광고 이미지 썸네일과 광고 문구</span></div>
                  <div className="flex gap-2"><span className="font-bold text-slate-900">5.</span><span>원자료: XLSX 다중 시트와 이미지 소재 시트</span></div>
                </div>
                <div className="mt-5 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-lg bg-orange-50 text-orange-700 py-3 font-bold">PPTX</div>
                  <div className="rounded-lg bg-red-50 text-red-700 py-3 font-bold">PDF</div>
                  <div className="rounded-lg bg-green-50 text-green-700 py-3 font-bold">XLSX</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

interface AdvertiserDownloadDropdownProps {
  advertiserId: number;
  days?: number;
}

/**
 * Dropdown with all advertiser download options:
 * - One-click report bundle (PPTX/PDF/XLSX)
 * - Excel report (multi-sheet)
 * - Creative images ZIP
 * - Advertiser list CSV
 */
export function AdvertiserDownloadDropdown({ advertiserId, days = 30 }: AdvertiserDownloadDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const download = async (url: string) => {
    if (!isPaid()) {
      showUpgradeAlert();
      window.location.href = "/pricing";
      return;
    }
    await authDownload(url);
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => { if (!isPaid()) { showUpgradeAlert(); window.location.href = "/pricing"; return; } setOpen(!open); }}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition-colors"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        데이터 다운로드
      </button>
      {open && (
        <div className="absolute top-full right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 min-w-[240px]">
          <button
            onClick={() => download(`/api/reports/advertiser/${advertiserId}/bundle?days=${days}`)}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 flex items-center gap-2"
          >
            <span className="w-6 h-6 bg-teal-100 text-teal-700 rounded flex items-center justify-center text-[10px] font-bold">ZIP</span>
            <div>
              <p className="font-medium text-gray-900">원클릭 보고서</p>
              <p className="text-[10px] text-gray-400">PPT + PDF + XLSX 묶음</p>
            </div>
          </button>
          <button
            onClick={() => download(`/api/download/advertiser-report?advertiser_id=${advertiserId}`)}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 flex items-center gap-2 border-t border-gray-100"
          >
            <span className="w-6 h-6 bg-green-100 text-green-700 rounded flex items-center justify-center text-[10px] font-bold">XLS</span>
            <div>
              <p className="font-medium text-gray-900">광고주 리포트</p>
              <p className="text-[10px] text-gray-400">소재+채널+광고비 Excel</p>
            </div>
          </button>
          <button
            onClick={() => download(`/api/download/advertiser-creatives?advertiser_id=${advertiserId}`)}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 flex items-center gap-2 border-t border-gray-100"
          >
            <span className="w-6 h-6 bg-purple-100 text-purple-700 rounded flex items-center justify-center text-[10px] font-bold">ZIP</span>
            <div>
              <p className="font-medium text-gray-900">소재 이미지</p>
              <p className="text-[10px] text-gray-400">모든 크리에이티브 이미지 ZIP</p>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}

interface GallerySelectionDownloadProps {
  selectedIds: number[];
  disabled?: boolean;
}

/**
 * Download button for selected gallery items (ZIP of images).
 */
export function GallerySelectionDownload({ selectedIds, disabled }: GallerySelectionDownloadProps) {
  const handleDownload = async () => {
    if (!isPaid()) { showUpgradeAlert(); window.location.href = "/pricing"; return; }
    if (selectedIds.length === 0) return;
    const ids = selectedIds.join(",");
    await authDownload(`/api/download/gallery-selection?ids=${ids}`);
  };

  return (
    <button
      onClick={handleDownload}
      disabled={disabled || selectedIds.length === 0}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-purple-600 bg-purple-50 border border-purple-200 rounded-lg hover:bg-purple-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {selectedIds.length > 0 ? `${selectedIds.length}개 이미지 다운로드` : "선택 다운로드"}
    </button>
  );
}
