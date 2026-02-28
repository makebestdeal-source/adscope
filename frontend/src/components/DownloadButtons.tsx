"use client";

import { useState, useRef, useEffect } from "react";
import { isPaid } from "@/lib/auth";

function showUpgradeAlert() {
  alert("다운로드는 유료 회원 전용 기능입니다.\n플랜을 업그레이드해주세요.\n\n문의: admin@adscope.kr");
}

async function authDownload(url: string): Promise<boolean> {
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

interface AdvertiserDownloadDropdownProps {
  advertiserId: number;
}

/**
 * Dropdown with all advertiser download options:
 * - Excel report (multi-sheet)
 * - Creative images ZIP
 * - Advertiser list CSV
 */
export function AdvertiserDownloadDropdown({ advertiserId }: AdvertiserDownloadDropdownProps) {
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
        <div className="absolute top-full right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 min-w-[220px]">
          <button
            onClick={() => download(`/api/download/advertiser-report?advertiser_id=${advertiserId}`)}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 flex items-center gap-2"
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
