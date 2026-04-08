"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export function LoginRequiredModal() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const handler = () => setOpen(true);
    window.addEventListener("adscope:requireAuth", handler);
    return () => window.removeEventListener("adscope:requireAuth", handler);
  }, []);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-white dark:bg-slate-800 rounded-2xl p-8 max-w-sm w-full mx-4 shadow-2xl">
        <div className="text-center space-y-4">
          <div className="w-16 h-16 mx-auto bg-indigo-50 dark:bg-indigo-900/30 rounded-full flex items-center justify-center">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8 text-indigo-600">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-white">로그인이 필요합니다</h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed">
            데이터를 조회하려면 로그인이 필요합니다.<br />
            로그인 후 AdScope의 모든 서비스를 이용해 보세요.
          </p>
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => setOpen(false)}
              className="flex-1 py-2.5 px-4 border border-gray-300 dark:border-slate-600 text-gray-700 dark:text-gray-300 text-sm font-medium rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors"
            >
              닫기
            </button>
            <Link
              href="/login"
              className="flex-1 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg text-center transition-colors"
            >
              로그인
            </Link>
          </div>
          <Link
            href="/pricing"
            className="block text-xs text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors pt-1"
          >
            계정이 없으신가요? 회원가입 →
          </Link>
        </div>
      </div>
    </div>
  );
}
