"use client";

import { useState, useRef, useEffect } from "react";
import { isPaid } from "@/lib/auth";

interface ExportDropdownProps {
  csvUrl: string;
  xlsxUrl: string;
  label?: string;
}

export function ExportDropdown({ csvUrl, xlsxUrl, label = "다운로드" }: ExportDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const download = (url: string) => {
    if (!isPaid()) {
      alert("다운로드는 유료 회원 전용 기능입니다.\n플랜을 업그레이드해주세요.\n\n문의: admin@adscope.kr");
      window.location.href = "/pricing";
      return;
    }
    const token = localStorage.getItem("adscope_token");
    const a = document.createElement("a");
    const sep = url.includes("?") ? "&" : "?";
    a.href = `${url}${sep}_token=${token}`;
    a.click();
    setOpen(false);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => { if (!isPaid()) { alert("다운로드는 유료 회원 전용 기능입니다.\n플랜을 업그레이드해주세요.\n\n문의: admin@adscope.kr"); window.location.href = "/pricing"; return; } setOpen(!open); }}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {label}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-50 min-w-[140px]">
          <button
            onClick={() => download(xlsxUrl)}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 flex items-center gap-2"
          >
            <span className="w-6 h-6 bg-green-100 text-green-700 rounded flex items-center justify-center text-[10px] font-bold">XLS</span>
            Excel (.xlsx)
          </button>
          <button
            onClick={() => download(csvUrl)}
            className="w-full px-4 py-2.5 text-left text-sm hover:bg-gray-50 flex items-center gap-2 border-t border-gray-100"
          >
            <span className="w-6 h-6 bg-gray-100 text-gray-600 rounded flex items-center justify-center text-[10px] font-bold">CSV</span>
            CSV (.csv)
          </button>
        </div>
      )}
    </div>
  );
}
