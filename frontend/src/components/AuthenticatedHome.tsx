"use client";

import { useEffect, useState } from "react";
import { Dashboard } from "@/components/Dashboard";
import { AuthUser, getUser } from "@/lib/auth";

export function AuthenticatedHome() {
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setUser(getUser());
  }, []);

  if (user?.role !== "admin") return null;

  return (
    <>
      <style jsx global>{`
        #seo-home-landing {
          display: none;
        }
      `}</style>
      <div className="p-6 lg:p-8 max-w-7xl">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 shadow-lg shadow-indigo-200/50">
            <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5 text-white">
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
    </>
  );
}
