"use client";

import Link from "next/link";
import { hasFullAccess } from "@/lib/auth";

/**
 * Wraps content that requires Full plan access.
 * Shows upgrade prompt for Lite users.
 */
export function PlanGate({ children }: { children: React.ReactNode }) {
  if (hasFullAccess()) {
    return <>{children}</>;
  }

  return (
    <div className="p-6 lg:p-8 max-w-2xl mx-auto">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-10 text-center">
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-amber-100 flex items-center justify-center">
          <svg className="w-8 h-8 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">Full 플랜 전용 기능</h2>
        <p className="text-sm text-gray-500 mb-6">
          이 기능은 Full 플랜에서 이용 가능합니다.
          <br />
          업그레이드하여 광고 소재, 소셜 소재 등 전체 기능을 이용하세요.
        </p>
        <div className="flex items-center justify-center gap-3">
          <Link
            href="/pricing"
            className="px-6 py-2.5 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700"
          >
            플랜 업그레이드
          </Link>
          <Link
            href="/"
            className="px-6 py-2.5 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200"
          >
            대시보드로
          </Link>
        </div>
      </div>
    </div>
  );
}
