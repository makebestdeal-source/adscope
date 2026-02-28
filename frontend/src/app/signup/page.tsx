"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

const PLAN_NAMES: Record<string, string> = { lite: "Lite", full: "Full" };
const PLAN_PRICES: Record<string, Record<string, number>> = {
  lite: { monthly: 49000, yearly: 490000 },
  full: { monthly: 99000, yearly: 990000 },
};

function fmt(n: number) {
  return n.toLocaleString("ko-KR");
}

/** Validate Korean phone number format: 010-XXXX-XXXX or 01012345678 */
function isValidKoreanPhone(phone: string): boolean {
  if (!phone) return true; // phone is optional
  const cleaned = phone.replace(/[-\s]/g, "");
  return /^01[016789]\d{7,8}$/.test(cleaned);
}

/** Basic email format validation */
function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/** Format phone as 010-XXXX-XXXX */
function formatPhone(value: string): string {
  const digits = value.replace(/\D/g, "");
  if (digits.length <= 3) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 7)}-${digits.slice(7, 11)}`;
}

export default function SignupPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <SignupForm />
    </Suspense>
  );
}

function SignupForm() {
  const router = useRouter();
  const params = useSearchParams();
  const defaultPlan = params.get("plan") === "full" ? "full" : "lite";
  const defaultPeriod =
    params.get("period") === "yearly" ? "yearly" : "monthly";

  const [form, setForm] = useState({
    email: "",
    password: "",
    passwordConfirm: "",
    name: "",
    company_name: "",
    phone: "",
    plan: defaultPlan,
    plan_period: defaultPeriod,
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [phoneError, setPhoneError] = useState("");
  const [emailError, setEmailError] = useState("");

  const price = PLAN_PRICES[form.plan]?.[form.plan_period] || 0;

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const formatted = formatPhone(e.target.value);
    setForm((f) => ({ ...f, phone: formatted }));
    if (formatted && !isValidKoreanPhone(formatted)) {
      setPhoneError("올바른 전화번호 형식이 아닙니다 (예: 010-1234-5678)");
    } else {
      setPhoneError("");
    }
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setForm((f) => ({ ...f, email: value }));
    if (value && !isValidEmail(value)) {
      setEmailError("올바른 이메일 형식이 아닙니다");
    } else {
      setEmailError("");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!isValidEmail(form.email)) {
      setError("올바른 이메일 형식을 입력해주세요.");
      return;
    }
    if (form.password.length < 6) {
      setError("비밀번호는 6자 이상이어야 합니다.");
      return;
    }
    if (form.password !== form.passwordConfirm) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }
    if (!form.company_name.trim()) {
      setError("회사명을 입력해주세요.");
      return;
    }
    if (!form.name.trim()) {
      setError("담당자명을 입력해주세요.");
      return;
    }
    if (form.phone && !isValidKoreanPhone(form.phone)) {
      setError("올바른 전화번호 형식을 입력해주세요 (예: 010-1234-5678)");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: form.email,
          password: form.password,
          name: form.name,
          company_name: form.company_name,
          phone: form.phone || null,
          plan: form.plan,
          plan_period: form.plan_period,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "가입에 실패했습니다.");
      }

      setSuccess(true);
    } catch (err: any) {
      setError(err.message || "오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-indigo-50/30 flex items-center justify-center px-6">
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-10 max-w-md w-full text-center animate-scale-in">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gradient-to-br from-emerald-100 to-teal-100 flex items-center justify-center">
            <svg className="w-8 h-8 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">가입이 완료되었습니다!</h2>
          <p className="text-sm text-gray-500 mb-6">
            7일간 무료 체험이 시작되었습니다.
            <br />
            바로 구독하거나 서비스를 먼저 이용해 보세요.
          </p>
          <div className="space-y-3">
            <Link
              href={`/payment?plan=${form.plan}&period=${form.plan_period}`}
              className="block px-6 py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98]"
            >
              지금 구독하기
            </Link>
            <Link
              href="/login"
              className="block px-6 py-3.5 border border-gray-200 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-50 transition-colors"
            >
              무료 체험 시작 (로그인)
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-indigo-50/30">
      <header className="border-b border-gray-100 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/pricing" className="flex items-center gap-2.5 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-md shadow-indigo-200/50 group-hover:shadow-lg group-hover:shadow-indigo-300/50 transition-shadow">
              <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" className="w-4 h-4">
                <path d="M3 3v18h18" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M7 16l4-8 4 6 4-10" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
              AdScope
            </span>
          </Link>
          <Link href="/login" className="text-sm text-gray-500 hover:text-indigo-600 font-medium transition-colors">
            이미 계정이 있으신가요? <span className="text-indigo-600">로그인 →</span>
          </Link>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-6 py-12 animate-fade-in">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">기업회원 가입</h1>
        <p className="text-sm text-gray-500 mb-8">
          아래 정보를 입력하여 AdScope 서비스에 가입하세요.
        </p>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Plan Selection */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">
              요금제
            </label>
            <div className="grid grid-cols-2 gap-3">
              {(["lite", "full"] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, plan: p }))}
                  className={`p-3 rounded-lg border-2 text-left transition-colors ${
                    form.plan === p
                      ? p === "full"
                        ? "border-emerald-500 bg-emerald-50"
                        : "border-indigo-500 bg-indigo-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <span className="text-sm font-bold text-gray-900">
                    {PLAN_NAMES[p]}
                  </span>
                  <span className="block text-xs text-gray-500 mt-0.5">
                    {p === "lite" ? "광고 정보 열람" : "전체 기능"}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Period Selection */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">
              결제 주기
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, plan_period: "monthly" }))}
                className={`p-3 rounded-lg border-2 text-left transition-colors ${
                  form.plan_period === "monthly"
                    ? "border-indigo-500 bg-indigo-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <span className="text-sm font-bold text-gray-900">월간</span>
                <span className="block text-xs text-gray-500 mt-0.5">
                  {fmt(PLAN_PRICES[form.plan].monthly)}원/월
                </span>
              </button>
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, plan_period: "yearly" }))}
                className={`p-3 rounded-lg border-2 text-left transition-colors ${
                  form.plan_period === "yearly"
                    ? "border-indigo-500 bg-indigo-50"
                    : "border-gray-200 hover:border-gray-300"
                }`}
              >
                <span className="text-sm font-bold text-gray-900">
                  연간{" "}
                  <span className="text-emerald-600 text-xs font-medium">
                    할인
                  </span>
                </span>
                <span className="block text-xs text-gray-500 mt-0.5">
                  {fmt(PLAN_PRICES[form.plan].yearly)}원/년
                </span>
              </button>
            </div>
          </div>

          <hr className="border-gray-200" />

          {/* Company Name */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              회사명 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={form.company_name}
              onChange={(e) => setForm((f) => ({ ...f, company_name: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="(주) 회사명"
            />
          </div>

          {/* Name */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              담당자명 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="홍길동"
            />
          </div>

          {/* Email */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              이메일 <span className="text-red-500">*</span>
            </label>
            <input
              type="email"
              required
              value={form.email}
              onChange={handleEmailChange}
              className={`w-full px-4 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 ${
                emailError ? "border-red-400 bg-red-50" : "border-gray-300"
              }`}
              placeholder="name@company.com"
            />
            {emailError && (
              <p className="text-xs text-red-500 mt-1">{emailError}</p>
            )}
          </div>

          {/* Phone */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              연락처
            </label>
            <input
              type="tel"
              value={form.phone}
              onChange={handlePhoneChange}
              maxLength={13}
              className={`w-full px-4 py-2.5 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 ${
                phoneError ? "border-red-400 bg-red-50" : "border-gray-300"
              }`}
              placeholder="010-0000-0000"
            />
            {phoneError && (
              <p className="text-xs text-red-500 mt-1">{phoneError}</p>
            )}
          </div>

          {/* Password */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              비밀번호 <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              required
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="6자 이상"
            />
          </div>
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              비밀번호 확인 <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              required
              value={form.passwordConfirm}
              onChange={(e) => setForm((f) => ({ ...f, passwordConfirm: e.target.value }))}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="비밀번호 재입력"
            />
          </div>

          {error && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
              {error}
            </div>
          )}

          {/* Summary */}
          <div className="bg-gradient-to-br from-gray-50 to-indigo-50/30 rounded-xl p-4 border border-gray-200">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">선택 요금제</span>
              <span className="font-semibold text-gray-900">
                {PLAN_NAMES[form.plan]} ({form.plan_period === "monthly" ? "월간" : "연간"})
              </span>
            </div>
            <div className="flex justify-between text-sm mt-1">
              <span className="text-gray-600">결제 금액</span>
              <span className="font-semibold text-gray-900">
                {fmt(price)}원
                <span className="text-xs text-gray-400 ml-1">(부가세 별도)</span>
              </span>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className={`w-full py-3.5 rounded-xl text-sm font-semibold transition-all duration-200 ${
              loading
                ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                : "bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:shadow-lg hover:shadow-indigo-200/50 active:scale-[0.98]"
            }`}
          >
            {loading ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                가입 처리 중...
              </span>
            ) : "가입하기"}
          </button>

          <p className="text-xs text-center text-gray-400">
            가입 시{" "}
            <span className="underline cursor-pointer">이용약관</span>과{" "}
            <span className="underline cursor-pointer">개인정보처리방침</span>에
            동의합니다.
          </p>
        </form>
      </main>
    </div>
  );
}
