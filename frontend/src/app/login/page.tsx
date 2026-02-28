"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { login } from "@/lib/auth";
import Link from "next/link";

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Handle OAuth callback token
  useEffect(() => {
    const oauthToken = searchParams.get("oauth_token");
    if (oauthToken) {
      // Decode JWT to get user info
      try {
        const payload = JSON.parse(atob(oauthToken.split(".")[1]));
        const user = {
          id: payload.sub,
          email: payload.email,
          name: payload.email?.split("@")[0],
          role: payload.role,
          plan: payload.plan,
        };
        localStorage.setItem("adscope_token", oauthToken);
        localStorage.setItem("adscope_user", JSON.stringify(user));
        document.cookie = `adscope_token=${oauthToken}; path=/; max-age=${60 * 60 * 24}; SameSite=Lax`;
        router.push("/");
      } catch {
        setError("소셜 로그인 처리 중 오류가 발생했습니다");
      }
    }
  }, [searchParams, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(email, password);
      router.push("/");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "로그인에 실패했습니다";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function handleOAuth(provider: string) {
    window.location.href = `/api/auth/oauth/${provider}`;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 via-indigo-50/30 to-slate-100">
      {/* Background decoration */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute -top-40 -right-40 w-80 h-80 rounded-full bg-indigo-100/40 blur-3xl" />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 rounded-full bg-violet-100/30 blur-3xl" />
      </div>

      <div className="relative w-full max-w-sm mx-4 animate-fade-in">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-600 to-violet-600 shadow-lg shadow-indigo-200 mb-4">
            <svg viewBox="0 0 24 24" fill="none" className="w-7 h-7 text-white">
              <path d="M3 3v18h18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              <path d="M7 16l4-6 3 3 3-7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            AdScope
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            광고 인텔리전스 플랫폼
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-xl shadow-slate-200/50 border border-white/60 p-7">
          <h2 className="text-lg font-semibold text-slate-800 mb-6">
            로그인
          </h2>

          {error && (
            <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-100 text-sm text-red-600 flex items-center gap-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 flex-shrink-0">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4m0 4h.01" strokeLinecap="round" />
              </svg>
              {error}
            </div>
          )}

          {/* Social Login Buttons */}
          <div className="space-y-2.5 mb-5">
            <button
              onClick={() => handleOAuth("google")}
              className="w-full flex items-center justify-center gap-3 py-2.5 px-4 bg-white border border-slate-200 rounded-xl text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm"
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              Google로 시작하기
            </button>

            <button
              onClick={() => handleOAuth("kakao")}
              className="w-full flex items-center justify-center gap-3 py-2.5 px-4 bg-[#FEE500] border border-[#FEE500] rounded-xl text-sm font-medium text-[#191919] hover:bg-[#FADA0A] transition-all shadow-sm"
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="#191919">
                <path d="M12 3C6.48 3 2 6.36 2 10.44c0 2.62 1.75 4.93 4.38 6.24l-1.12 4.16c-.1.36.31.65.63.44l4.98-3.3c.37.04.74.06 1.13.06 5.52 0 10-3.36 10-7.6C22 6.36 17.52 3 12 3z"/>
              </svg>
              카카오로 시작하기
            </button>

            <button
              onClick={() => handleOAuth("naver")}
              className="w-full flex items-center justify-center gap-3 py-2.5 px-4 bg-[#03C75A] border border-[#03C75A] rounded-xl text-sm font-medium text-white hover:bg-[#02B350] transition-all shadow-sm"
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5" fill="white">
                <path d="M16.27 12.73L7.44 3H3v18h4.73V11.27L16.56 21H21V3h-4.73z"/>
              </svg>
              네이버로 시작하기
            </button>
          </div>

          {/* Divider */}
          <div className="relative mb-5">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white/80 px-3 text-slate-400">또는 이메일로 로그인</span>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-slate-700 mb-1.5"
              >
                이메일
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-slate-50/50
                           focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 focus:bg-white
                           placeholder-slate-400 transition-all"
                placeholder="admin@adscope.kr"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-slate-700 mb-1.5"
              >
                비밀번호
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-sm bg-slate-50/50
                           focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 focus:bg-white
                           placeholder-slate-400 transition-all"
                placeholder="비밀번호 입력"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700
                         disabled:from-indigo-400 disabled:to-violet-400 disabled:cursor-not-allowed
                         text-white text-sm font-semibold rounded-xl transition-all
                         shadow-lg shadow-indigo-200/50 hover:shadow-indigo-300/60
                         focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2
                         active:scale-[0.98]"
            >
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="60" strokeLinecap="round" className="opacity-30" />
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeDasharray="15 45" strokeLinecap="round" />
                  </svg>
                  로그인 중...
                </span>
              ) : (
                "로그인"
              )}
            </button>
          </form>

          <div className="mt-5 text-center">
            <Link
              href="/forgot-password"
              className="text-sm text-slate-500 hover:text-indigo-600 transition-colors"
            >
              비밀번호를 잊으셨나요?
            </Link>
          </div>
        </div>

        <div className="text-center mt-6 space-y-3">
          <Link
            href="/pricing"
            className="inline-flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium transition-colors"
          >
            기업회원 가입
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
              <path d="M9 18l6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
          <p className="text-xs text-slate-400">AdScope v0.2.0</p>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center"><p>Loading...</p></div>}>
      <LoginContent />
    </Suspense>
  );
}
