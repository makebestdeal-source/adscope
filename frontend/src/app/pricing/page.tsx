"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import {
  BillingCycle,
  PLAN_CATALOG,
  PlanId,
  formatKrw,
  priceFor,
  usageLabel,
} from "@/lib/plans";

const PLAN_ORDER: PlanId[] = ["lite", "full", "enterprise"];

function discountRate(original: number | undefined, sale: number | null) {
  if (!original || !sale) return null;
  return Math.round((1 - sale / original) * 100);
}

function usageRows() {
  return [
    ["사용자 계정", "users", "명"],
    ["모니터링 광고주", "trackedAdvertisers", "개"],
    ["월 리포트/Export", "reportExports", "회"],
    ["월 소재 다운로드", "creativeDownloads", "건"],
    ["API 호출", "apiCalls", "회"],
    ["데이터 조회 기간", "historyMonths", "개월"],
  ] as const;
}

export default function PricingPage() {
  const [cycle, setCycle] = useState<BillingCycle>("monthly");

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-sm font-bold text-white">
              AS
            </div>
            <span className="text-lg font-bold">AdScope</span>
          </Link>
          <div className="flex items-center gap-3 text-sm">
            <Link href="/manual" className="text-slate-500 hover:text-slate-900">
              사용 가이드
            </Link>
            <Link href="/login" className="rounded-lg border border-slate-300 px-3 py-2 font-medium text-slate-700 hover:bg-slate-100">
              로그인
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-12">
        <section className="mb-10">
          <p className="mb-3 text-sm font-semibold text-slate-500">요금제 및 사용량 정책</p>
          <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr] lg:items-end">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
                열람은 공개하고, 다운로드와 운영 사용량은 플랜으로 관리합니다.
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-600">
                Lite와 Full은 즉시 온라인 결제가 가능하고, Enterprise는 사용량과 정산 방식에 맞춰 견적서, 계약서,
                세금계산서, 계좌이체로 진행합니다. 모든 금액은 부가세 별도입니다.
              </p>
            </div>
            <div className="flex rounded-lg border border-slate-200 bg-white p-1 shadow-sm">
              {(["monthly", "yearly"] as BillingCycle[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setCycle(item)}
                  className={`flex-1 rounded-md px-4 py-2 text-sm font-semibold transition ${
                    cycle === item ? "bg-slate-900 text-white" : "text-slate-500 hover:bg-slate-100"
                  }`}
                >
                  {item === "monthly" ? "월간 결제" : "연간 결제"}
                  {item === "yearly" && <span className="ml-2 text-xs opacity-80">2개월 할인</span>}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          {PLAN_ORDER.map((planId) => {
            const plan = PLAN_CATALOG[planId];
            const price = priceFor(plan.id, cycle);
            const original = cycle === "monthly" ? plan.originalMonthly : plan.originalYearly;
            const discount = discountRate(original, price);
            const highlighted = plan.id === "full";

            return (
              <article
                key={plan.id}
                className={`relative flex flex-col rounded-lg border bg-white p-6 shadow-sm ${
                  highlighted ? "border-slate-900 ring-1 ring-slate-900" : "border-slate-200"
                }`}
              >
                {plan.badge && (
                  <span className="absolute right-4 top-4 rounded-full bg-slate-900 px-2.5 py-1 text-xs font-bold text-white">
                    {plan.badge}
                  </span>
                )}
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{plan.audience}</p>
                <h2 className="mt-3 text-2xl font-bold">{plan.name}</h2>
                <p className="mt-2 min-h-12 text-sm leading-6 text-slate-600">{plan.description}</p>

                <div className="mt-6 border-t border-slate-100 pt-5">
                  {price !== null ? (
                    <>
                      {original && (
                        <p className="text-sm text-slate-400">
                          정가 <span className="line-through">{formatKrw(original)}원</span>
                          {discount !== null && <span className="ml-2 text-slate-700">{discount}% 할인</span>}
                        </p>
                      )}
                      <p className="mt-1 text-4xl font-extrabold tracking-tight">
                        {formatKrw(price)}
                        <span className="text-sm font-semibold text-slate-500">원/{cycle === "monthly" ? "월" : "년"}</span>
                      </p>
                      {cycle === "yearly" && (
                        <p className="mt-1 text-xs text-slate-500">월 환산 {formatKrw(Math.round(price / 12))}원</p>
                      )}
                    </>
                  ) : (
                    <>
                      <p className="text-sm font-semibold text-slate-500">맞춤 견적</p>
                      <p className="mt-1 text-3xl font-extrabold">협의</p>
                      <p className="mt-1 text-xs text-slate-500">{plan.paymentNote}</p>
                    </>
                  )}
                </div>

                <div className="mt-6">
                  {plan.checkoutEnabled ? (
                    <Link
                      href={`/payment?plan=${plan.id}&cycle=${cycle}`}
                      className={`block rounded-lg px-4 py-3 text-center text-sm font-bold text-white ${
                        highlighted ? "bg-slate-950 hover:bg-slate-800" : "bg-indigo-600 hover:bg-indigo-700"
                      }`}
                    >
                      {plan.name} 결제하기
                    </Link>
                  ) : (
                    <a
                      href="#enterprise"
                      className="block rounded-lg border border-slate-900 px-4 py-3 text-center text-sm font-bold text-slate-900 hover:bg-slate-100"
                    >
                      Enterprise 상담 신청
                    </a>
                  )}
                </div>

                <dl className="mt-6 grid grid-cols-2 gap-3 text-sm">
                  {usageRows().slice(0, 4).map(([label, key, suffix]) => (
                    <div key={key} className="rounded-md bg-slate-50 p-3">
                      <dt className="text-xs text-slate-500">{label}</dt>
                      <dd className="mt-1 font-bold text-slate-900">
                        {usageLabel(plan.usage[key], suffix)}
                      </dd>
                    </div>
                  ))}
                </dl>

                <ul className="mt-6 space-y-2 text-sm text-slate-700">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-slate-900" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
              </article>
            );
          })}
        </section>

        <section className="mt-12 rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-6 py-5">
            <h2 className="text-lg font-bold">사용량 기준표</h2>
            <p className="mt-1 text-sm text-slate-500">
              비회원은 열람 중심으로 사용할 수 있고, 소재 다운로드/내보내기/업무용 반복 사용은 아래 기준으로 관리합니다.
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-6 py-3">항목</th>
                  <th className="px-6 py-3">Lite</th>
                  <th className="px-6 py-3">Full</th>
                  <th className="px-6 py-3">Enterprise</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {usageRows().map(([label, key, suffix]) => (
                  <tr key={key}>
                    <td className="px-6 py-4 font-medium text-slate-800">{label}</td>
                    <td className="px-6 py-4">{usageLabel(PLAN_CATALOG.lite.usage[key], suffix)}</td>
                    <td className="px-6 py-4">{usageLabel(PLAN_CATALOG.full.usage[key], suffix)}</td>
                    <td className="px-6 py-4">{usageLabel(PLAN_CATALOG.enterprise.usage[key], suffix)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <EnterpriseSection />
      </main>
    </div>
  );
}

function EnterpriseSection() {
  const [form, setForm] = useState({
    company_name: "",
    contact_name: "",
    email: "",
    phone: "",
    expected_users: "",
    expected_advertisers: "",
    message: "",
  });
  const [state, setState] = useState<"idle" | "submitting" | "done" | "error">("idle");

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setState("submitting");
    try {
      const res = await fetch("/api/payments/enterprise-inquiry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (!res.ok) throw new Error("submit failed");
      setState("done");
    } catch {
      setState("error");
    }
  };

  return (
    <section id="enterprise" className="mt-12 grid gap-8 rounded-lg border border-slate-200 bg-white p-6 shadow-sm lg:grid-cols-[0.9fr_1.1fr]">
      <div>
        <p className="text-sm font-semibold text-slate-500">Enterprise 결제 흐름</p>
        <h2 className="mt-2 text-2xl font-bold">사용량을 먼저 확정하고 견적/정산으로 진행합니다.</h2>
        <div className="mt-6 space-y-4 text-sm text-slate-600">
          <p>1. 광고주 수, 사용자 수, API/Export 필요량을 확인합니다.</p>
          <p>2. 월 이용료, 데이터 보강 범위, SLA를 포함한 견적서를 발행합니다.</p>
          <p>3. 계약 후 세금계산서와 계좌이체 또는 월 정산으로 결제합니다.</p>
        </div>
        <p className="mt-6 text-sm text-slate-500">
          급한 문의는 <a className="font-semibold text-slate-900 underline" href="mailto:support@adscope.kr">support@adscope.kr</a>로 바로 보내셔도 됩니다.
        </p>
      </div>

      {state === "done" ? (
        <div className="rounded-lg bg-emerald-50 p-6 text-emerald-900">
          <h3 className="text-lg font-bold">상담 요청이 접수됐습니다.</h3>
          <p className="mt-2 text-sm">사용 규모를 확인한 뒤 견적/정산 방식으로 연락드리겠습니다.</p>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="회사명" name="company_name" value={form.company_name} required onChange={(value) => setForm((prev) => ({ ...prev, company_name: value }))} />
            <Field label="담당자명" name="contact_name" value={form.contact_name} required onChange={(value) => setForm((prev) => ({ ...prev, contact_name: value }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="이메일" name="email" type="email" value={form.email} required onChange={(value) => setForm((prev) => ({ ...prev, email: value }))} />
            <Field label="연락처" name="phone" value={form.phone} onChange={(value) => setForm((prev) => ({ ...prev, phone: value }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="예상 사용자 수" name="expected_users" value={form.expected_users} onChange={(value) => setForm((prev) => ({ ...prev, expected_users: value }))} />
            <Field label="모니터링 광고주 수" name="expected_advertisers" value={form.expected_advertisers} onChange={(value) => setForm((prev) => ({ ...prev, expected_advertisers: value }))} />
          </div>
          <label className="grid gap-1.5 text-sm font-medium text-slate-700">
            문의 내용
            <textarea
              value={form.message}
              onChange={(event) => setForm((prev) => ({ ...prev, message: event.target.value }))}
              rows={4}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
              placeholder="필요한 데이터 범위, 계약/정산 방식, API 사용 여부를 적어주세요."
            />
          </label>
          {state === "error" && <p className="text-sm text-red-600">접수에 실패했습니다. support@adscope.kr로 문의해 주세요.</p>}
          <button
            type="submit"
            disabled={state === "submitting"}
            className="rounded-lg bg-slate-950 px-4 py-3 text-sm font-bold text-white disabled:opacity-60"
          >
            {state === "submitting" ? "접수 중..." : "Enterprise 상담 신청"}
          </button>
        </form>
      )}
    </section>
  );
}

function Field({
  label,
  name,
  value,
  onChange,
  type = "text",
  required = false,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
}) {
  return (
    <label className="grid gap-1.5 text-sm font-medium text-slate-700">
      {label}
      <input
        name={name}
        type={type}
        required={required}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
      />
    </label>
  );
}
