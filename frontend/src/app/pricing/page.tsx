"use client";

import { useState, FormEvent } from "react";
import Link from "next/link";

const PLANS = [
  {
    id: "lite",
    name: "Lite",
    desc: "광고 정보 중심 분석",
    monthly: 49000,
    yearly: 490000,
    features: [
      "9개 채널 광고 소재 열람",
      "광고주 리포트 (캠페인/모델/메타시그널)",
      "광고비 분석 (4가지 역추산)",
      "산업별 / 제품별 / 경쟁사 비교",
      "SOV / 접촉률 / 페르소나 분석",
      "캠페인 분석 (저니/리프트)",
      "신제품 출시 임팩트 (LII)",
      "마케팅 스케줄 / 쇼핑인사이트",
      "보고서 생성 (광고 정보)",
    ],
    excluded: ["소셜 소재 갤러리", "브랜드 채널 분석", "소셜 채널 분석", "보고서 (소셜 소재)"],
    color: "indigo",
  },
  {
    id: "full",
    name: "Full",
    desc: "광고 + 소셜 통합 분석",
    monthly: 99000,
    yearly: 990000,
    badge: "추천",
    features: [
      "Lite 전체 기능 포함",
      "소셜 소재 갤러리 (YouTube/Instagram)",
      "브랜드 채널 분석",
      "소셜 채널 분석 (구독자/인게이지먼트)",
      "보고서 소셜 섹션 포함",
    ],
    excluded: [],
    color: "emerald",
  },
];

function fmt(n: number) {
  return n.toLocaleString("ko-KR");
}

export default function PricingPage() {
  const [period, setPeriod] = useState<"monthly" | "yearly">("monthly");

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-indigo-50/30">
      {/* Header */}
      <header className="border-b border-gray-100 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/login" className="flex items-center gap-2.5 group">
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
          <Link
            href="/login"
            className="text-sm text-gray-500 hover:text-indigo-600 font-medium transition-colors"
          >
            로그인 →
          </Link>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-16 animate-fade-in">
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 bg-indigo-50 text-indigo-700 text-xs font-semibold px-3 py-1.5 rounded-full mb-4">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
              <path d="M13 10V3L4 14h7v7l9-11h-7z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            디지털 광고 인텔리전스 플랫폼
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-3">
            기업에 맞는 플랜을 선택하세요
          </h1>
          <p className="text-gray-500 max-w-lg mx-auto">
            9개 채널 광고 모니터링, AI 기반 분석, 광고비 역추산까지.
            <br className="hidden sm:block" />
            AdScope로 경쟁사 광고 전략을 한눈에 파악하세요.
          </p>
          <p className="text-xs text-gray-400 mt-3">모든 금액은 부가세 별도입니다.</p>
          <a
            href="/AdScope_서비스소개.pdf"
            download
            className="inline-flex items-center gap-2 mt-5 px-6 py-3 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98] text-sm"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M7 10l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            서비스 소개서 다운로드
          </a>
        </div>

        {/* Period Toggle */}
        <div className="flex justify-center mb-10">
          <div className="inline-flex bg-gray-100 rounded-xl p-1 shadow-inner">
            <button
              onClick={() => setPeriod("monthly")}
              className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                period === "monthly"
                  ? "bg-white text-gray-900 shadow-md"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              월간 결제
            </button>
            <button
              onClick={() => setPeriod("yearly")}
              className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                period === "yearly"
                  ? "bg-white text-gray-900 shadow-md"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              연간 결제
              <span className="ml-1.5 text-xs bg-emerald-100 text-emerald-700 font-semibold px-1.5 py-0.5 rounded-md">
                17% 할인
              </span>
            </button>
          </div>
        </div>

        {/* Plan Cards */}
        <div className="grid md:grid-cols-2 gap-8 max-w-3xl mx-auto">
          {PLANS.map((plan) => {
            const price = period === "monthly" ? plan.monthly : plan.yearly;
            const perMonth =
              period === "yearly"
                ? Math.round(plan.yearly / 12)
                : plan.monthly;
            const isFull = plan.id === "full";

            return (
              <div
                key={plan.id}
                className={`relative rounded-2xl border-2 p-8 bg-white transition-all duration-300 hover:shadow-xl hover:-translate-y-1 ${
                  isFull
                    ? "border-emerald-400 shadow-lg shadow-emerald-100/50 ring-1 ring-emerald-100"
                    : "border-gray-200 hover:border-indigo-200"
                }`}
              >
                {plan.badge && (
                  <span className="absolute -top-3.5 left-1/2 -translate-x-1/2 bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-xs font-bold px-4 py-1.5 rounded-full shadow-lg shadow-emerald-200/50">
                    {plan.badge}
                  </span>
                )}

                <div className="mb-6">
                  <h3 className="text-xl font-bold text-gray-900">
                    {plan.name}
                  </h3>
                  <p className="text-sm text-gray-500 mt-1">{plan.desc}</p>
                </div>

                <div className="mb-6">
                  <div className="flex items-end gap-1">
                    <span className="text-3xl font-bold text-gray-900">
                      {fmt(price)}
                    </span>
                    <span className="text-sm text-gray-500 mb-1">
                      원/{period === "monthly" ? "월" : "년"}
                    </span>
                  </div>
                  {period === "yearly" && (
                    <p className="text-xs text-gray-400 mt-1">
                      월 {fmt(perMonth)}원 (
                      <span className="text-emerald-600 font-medium">
                        {Math.round(
                          (1 - plan.yearly / (plan.monthly * 12)) * 100
                        )}
                        % 할인
                      </span>
                      )
                    </p>
                  )}
                </div>

                <Link
                  href={`/signup?plan=${plan.id}&period=${period}`}
                  className={`block w-full text-center py-3.5 rounded-xl text-sm font-semibold transition-all duration-200 active:scale-[0.98] ${
                    isFull
                      ? "bg-gradient-to-r from-emerald-600 to-teal-600 text-white hover:shadow-lg hover:shadow-emerald-200/50"
                      : "bg-gradient-to-r from-indigo-600 to-violet-600 text-white hover:shadow-lg hover:shadow-indigo-200/50"
                  }`}
                >
                  시작하기
                </Link>

                <ul className="mt-6 space-y-2.5">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <svg
                        className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                          isFull ? "text-emerald-500" : "text-indigo-500"
                        }`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2.5}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                      <span className="text-gray-700">{f}</span>
                    </li>
                  ))}
                  {plan.excluded.map((f) => (
                    <li
                      key={f}
                      className="flex items-start gap-2 text-sm text-gray-400"
                    >
                      <svg
                        className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-300"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={2.5}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M6 18L18 6M6 6l12 12"
                        />
                      </svg>
                      <span className="line-through">{f}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        {/* Important Notes */}
        <div className="max-w-3xl mx-auto mt-10">
          <div className="bg-gradient-to-br from-gray-50 to-slate-50 border border-gray-200 rounded-2xl p-6 space-y-4">
            <h3 className="font-semibold text-gray-900 text-sm flex items-center gap-2">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 text-indigo-500">
                <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              이용 안내
            </h3>
            <div className="grid sm:grid-cols-2 gap-4 text-sm text-gray-600">
              <div className="flex items-start gap-2">
                <svg className="w-4 h-4 mt-0.5 flex-shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                  <p className="font-medium text-gray-700">동시 접속 제한</p>
                  <p className="text-xs text-gray-500 mt-0.5">1개 계정당 1개 기기에서만 동시 접속이 가능합니다. 다른 기기에서 로그인하면 기존 세션이 종료됩니다.</p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <svg className="w-4 h-4 mt-0.5 flex-shrink-0 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <div>
                  <p className="font-medium text-gray-700">데이터 업데이트 주기</p>
                  <p className="text-xs text-gray-500 mt-0.5">광고 소재는 매일 자동 수집되며, AI 분류와 광고비 추정은 매일 새벽에 갱신됩니다. 메타시그널은 04:00~05:30 KST에 순차 업데이트됩니다.</p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <svg className="w-4 h-4 mt-0.5 flex-shrink-0 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                <div>
                  <p className="font-medium text-gray-700">지원 채널</p>
                  <p className="text-xs text-gray-500 mt-0.5">네이버(검색/DA/쇼핑), 카카오 DA, Google GDN, YouTube Ads, Facebook, Instagram, TikTok 등 9개 채널을 지원합니다.</p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <svg className="w-4 h-4 mt-0.5 flex-shrink-0 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                <div>
                  <p className="font-medium text-gray-700">보안</p>
                  <p className="text-xs text-gray-500 mt-0.5">디바이스 핑거프린트 기반 보안이 적용되며, 모든 통신은 SSL/TLS로 암호화됩니다.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Contact / Sample Request Section */}
        <ContactSection />

        {/* Footer note */}
        <div className="text-center mt-16 pb-4">
          <div className="inline-flex items-center gap-2 text-sm text-gray-400">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="w-4 h-4">
              <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            결제 관련 문의: support@adscope.kr
          </div>
        </div>
      </main>
    </div>
  );
}

function ContactSection() {
  const [form, setForm] = useState({
    companyName: "",
    contactName: "",
    email: "",
    phone: "",
    interest: "lite",
    message: "",
  });
  const [submitted, setSubmitted] = useState(false);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className="mt-16 max-w-2xl mx-auto">
        <div className="bg-white border-2 border-emerald-200 rounded-2xl p-10 text-center shadow-lg shadow-emerald-50 animate-scale-in">
          <div className="w-16 h-16 bg-gradient-to-br from-emerald-100 to-teal-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg
              className="w-8 h-8 text-emerald-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M5 13l4 4L19 7"
              />
            </svg>
          </div>
          <h3 className="text-xl font-bold text-gray-900 mb-2">
            문의가 접수되었습니다
          </h3>
          <p className="text-gray-500 mb-1">
            담당자가 확인 후 빠른 시일 내에 연락드리겠습니다.
          </p>
          <p className="text-sm text-gray-400">
            {form.companyName} / {form.contactName} ({form.email})
          </p>
          <button
            onClick={() => setSubmitted(false)}
            className="mt-6 text-sm text-indigo-600 hover:text-indigo-700 font-medium"
          >
            추가 문의하기
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-16 max-w-2xl mx-auto">
      <div className="text-center mb-8">
        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-indigo-200/50">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" className="w-6 h-6">
            <path d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">
          샘플 리포트 요청 / 문의하기
        </h2>
        <p className="text-gray-500 text-sm">
          도입을 검토 중이시라면 샘플 리포트를 요청해 보세요. 맞춤 상담도
          가능합니다.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="bg-white border border-gray-200 rounded-2xl p-8 space-y-5 shadow-sm"
      >
        <div className="grid md:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              회사명 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              name="companyName"
              required
              value={form.companyName}
              onChange={handleChange}
              placeholder="주식회사 OOO"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              담당자명 <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              name="contactName"
              required
              value={form.contactName}
              onChange={handleChange}
              placeholder="홍길동"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow"
            />
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              이메일 <span className="text-red-400">*</span>
            </label>
            <input
              type="email"
              name="email"
              required
              value={form.email}
              onChange={handleChange}
              placeholder="name@company.com"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              연락처 <span className="text-red-400">*</span>
            </label>
            <input
              type="tel"
              name="phone"
              required
              value={form.phone}
              onChange={handleChange}
              placeholder="010-0000-0000"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            관심 플랜
          </label>
          <select
            name="interest"
            value={form.interest}
            onChange={handleChange}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow bg-white"
          >
            <option value="lite">Lite Plan (49,000원/월)</option>
            <option value="full">Full Plan (99,000원/월)</option>
            <option value="custom">Custom (맞춤 상담)</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">
            문의 내용
          </label>
          <textarea
            name="message"
            value={form.message}
            onChange={handleChange}
            rows={4}
            placeholder="샘플 리포트 요청, 도입 문의, 기타 궁금한 사항을 입력해 주세요."
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none transition-shadow resize-none"
          />
        </div>

        <button
          type="submit"
          className="w-full py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98] text-sm"
        >
          문의 접수하기
        </button>

        <p className="text-xs text-gray-400 text-center">
          제출하신 정보는 문의 응대 목적으로만 사용됩니다.
        </p>
      </form>
    </div>
  );
}
