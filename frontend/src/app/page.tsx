"use client";

import { useEffect, useState } from "react";
import { Dashboard } from "@/components/Dashboard";
import { GuestLanding } from "@/components/GuestLanding";
import { isAuthenticated } from "@/lib/auth";

export default function Home() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    setAuthed(isAuthenticated());
  }, []);

  // SSR 하이드레이션 전에는 아무것도 렌더하지 않음
  if (authed === null) return null;

  if (!authed) {
    return <GuestLanding />;
  }

  return (
    <div className="p-6 lg:p-8 max-w-7xl">
      <div className="mb-8 flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-200/50">
          <svg viewBox="0 0 24 24" fill="none" className="w-5 h-5 text-white">
            <rect x="3" y="3" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
            <rect x="14" y="3" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
            <rect x="3" y="14" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
            <rect x="14" y="14" width="7" height="7" rx="1" stroke="currentColor" strokeWidth="2" />
          </svg>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">대시보드</h1>
          <p className="text-sm text-gray-500">
            실시간 광고 수집 현황 및 분석 요약
          </p>
        </div>
      </div>
      <Dashboard />
    </div>
  );
}
