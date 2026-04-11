"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { fetchApi } from "@/lib/api";
import { getUser, getToken } from "@/lib/auth";

export default function PaymentSuccessPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <SuccessFlow />
    </Suspense>
  );
}

function SuccessFlow() {
  const params = useSearchParams();
  const paymentKey = params.get("paymentKey") || "";
  const orderId = params.get("orderId") || "";
  const amount = params.get("amount") || "0";

  const [status, setStatus] = useState<"confirming" | "done" | "error">("confirming");
  const [message, setMessage] = useState("");
  const [planInfo, setPlanInfo] = useState<{
    plan: string;
    plan_period: string;
    plan_expires_at: string | null;
  } | null>(null);

  const user = getUser();
  const token = getToken();

  useEffect(() => {
    if (!paymentKey || !orderId || !amount) {
      setMessage("결제 정보가 올바르지 않습니다.");
      setStatus("error");
      return;
    }

    if (!token) {
      setMessage("로그인이 필요합니다. 로그인 후 다시 시도해주세요.");
      setStatus("error");
      return;
    }

    const confirmPayment = async () => {
      try {
        const result = await fetchApi<{
          status: string;
          message: string;
          payment_id: number;
          plan: string;
          plan_period: string;
          plan_expires_at: string | null;
        }>("/payments/confirm", {
          method: "POST",
          body: JSON.stringify({
            payment_key: paymentKey,
            order_id: orderId,
            amount: parseInt(amount, 10),
          }),
        });

        setPlanInfo({
          plan: result.plan,
          plan_period: result.plan_period,
          plan_expires_at: result.plan_expires_at,
        });

        // 로컬 스토리지의 유저 정보 업데이트
        if (user) {
          const updatedUser = {
            ...user,
            plan: result.plan,
            plan_period: result.plan_period,
            plan_expires_at: result.plan_expires_at,
            paid: true,
          };
          localStorage.setItem("adscope_user", JSON.stringify(updatedUser));
        }

        setMessage("결제가 완료되었습니다!");
        setStatus("done");
      } catch (err: unknown) {
        const errorMsg = err instanceof Error ? err.message : "결제 승인에 실패했습니다.";
        setMessage(errorMsg);
        setStatus("error");
      }
    };

    confirmPayment();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paymentKey, orderId, amount, token]);

  const planLabel = planInfo?.plan === "full" ? "Full" : "Lite";
  const periodLabel = planInfo?.plan_period === "yearly" ? "연간" : "월간";
  const expiresAt = planInfo?.plan_expires_at
    ? new Date(planInfo.plan_expires_at).toLocaleDateString("ko-KR", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-600 to-violet-600 flex items-center justify-center shadow-md shadow-indigo-200/50">
              <svg viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" className="w-4 h-4">
                <path d="M3 3v18h18" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M7 16l4-8 4 6 4-10" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <span className="text-xl font-bold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
              AdScope
            </span>
          </Link>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-6 py-16">
        {/* Confirming */}
        {status === "confirming" && (
          <div className="text-center py-20">
            <div className="w-16 h-16 mx-auto mb-6">
              <svg className="w-full h-full animate-spin text-indigo-600" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                <path d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" fill="currentColor" className="opacity-75" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">결제를 확인하고 있습니다</h2>
            <p className="text-sm text-gray-500">잠시만 기다려주세요...</p>
          </div>
        )}

        {/* Done */}
        {status === "done" && (
          <div className="text-center">
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-emerald-100 to-teal-100 flex items-center justify-center shadow-lg shadow-emerald-100/50">
              <svg className="w-10 h-10 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">결제가 완료되었습니다!</h2>
            <p className="text-sm text-gray-500 mb-8">{message}</p>

            {/* Plan Info Card */}
            {planInfo && (
              <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-8 text-left shadow-sm">
                <h3 className="text-sm font-semibold text-gray-500 mb-3">구독 정보</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">플랜</span>
                    <span className="font-semibold text-gray-900">
                      AdScope {planLabel}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">결제 주기</span>
                    <span className="font-medium text-gray-900">{periodLabel}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-600">결제 금액</span>
                    <span className="font-bold text-gray-900">
                      {parseInt(amount, 10).toLocaleString("ko-KR")}원
                    </span>
                  </div>
                  {expiresAt && (
                    <div className="flex justify-between items-center pt-2 border-t border-gray-100">
                      <span className="text-sm text-gray-600">이용 기간</span>
                      <span className="font-medium text-gray-900">{expiresAt}까지</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            <Link
              href="/"
              className="inline-flex items-center gap-2 px-8 py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98]"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              대시보드로 이동
            </Link>
          </div>
        )}

        {/* Error */}
        {status === "error" && (
          <div className="text-center">
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-red-100 flex items-center justify-center">
              <svg className="w-10 h-10 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">결제 승인 실패</h2>
            <p className="text-sm text-gray-500 mb-8">{message}</p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link
                href="/payment"
                className="px-6 py-3 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
              >
                다시 결제하기
              </Link>
              <Link
                href="/"
                className="px-6 py-3 border border-gray-300 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-50 transition-colors"
              >
                대시보드로 이동
              </Link>
            </div>
            <p className="text-xs text-gray-400 mt-6">
              문제가 지속되면 support@adscope.kr로 문의해주세요.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
