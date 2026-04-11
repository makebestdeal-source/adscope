"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

export default function PaymentFailPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <FailContent />
    </Suspense>
  );
}

function FailContent() {
  const params = useSearchParams();
  const code = params.get("code") || "";
  const message = params.get("message") || "결제가 취소되었거나 실패했습니다.";
  const orderId = params.get("orderId") || "";

  // 사용자 친화적 에러 메시지 매핑
  const friendlyMessages: Record<string, string> = {
    PAY_PROCESS_CANCELED: "결제가 취소되었습니다.",
    PAY_PROCESS_ABORTED: "결제 진행 중 문제가 발생했습니다.",
    REJECT_CARD_COMPANY: "카드사에서 결제가 거절되었습니다. 다른 카드를 사용해주세요.",
    BELOW_MINIMUM_AMOUNT: "결제 금액이 최소 금액 미만입니다.",
    EXCEED_MAX_DAILY_PAYMENT_COUNT: "일일 결제 횟수를 초과했습니다. 내일 다시 시도해주세요.",
    EXCEED_MAX_PAYMENT_AMOUNT: "결제 한도를 초과했습니다.",
    NOT_SUPPORTED_INSTALLMENT_PLAN_CARD_OR_MERCHANT: "할부가 지원되지 않는 카드입니다.",
    INVALID_CARD_EXPIRATION: "카드 유효기간이 만료되었습니다.",
    INVALID_STOPPED_CARD: "정지된 카드입니다.",
    EXCEED_MAX_AMOUNT: "거래 금액 한도를 초과했습니다.",
    INVALID_CARD_LOST_OR_STOLEN: "분실 또는 도난 카드입니다.",
    INVALID_CARD_NUMBER: "카드번호가 올바르지 않습니다.",
    NOT_AVAILABLE_PAYMENT: "결제가 불가능한 시간대입니다.",
  };

  const displayMessage = code && friendlyMessages[code]
    ? friendlyMessages[code]
    : message;

  const isCancelled = code === "PAY_PROCESS_CANCELED";

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
        <div className="text-center">
          <div className={`w-20 h-20 mx-auto mb-6 rounded-full flex items-center justify-center ${
            isCancelled ? "bg-amber-100" : "bg-red-100"
          }`}>
            {isCancelled ? (
              <svg className="w-10 h-10 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            ) : (
              <svg className="w-10 h-10 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
          </div>

          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            {isCancelled ? "결제가 취소되었습니다" : "결제에 실패했습니다"}
          </h2>
          <p className="text-sm text-gray-500 mb-2">{displayMessage}</p>
          {code && !isCancelled && (
            <p className="text-xs text-gray-400 mb-8">오류 코드: {code}</p>
          )}
          {!code && <div className="mb-8" />}

          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/payment"
              className="px-6 py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98]"
            >
              다시 결제하기
            </Link>
            <Link
              href="/pricing"
              className="px-6 py-3.5 border border-gray-300 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-50 transition-colors"
            >
              요금제 확인
            </Link>
          </div>

          {orderId && (
            <p className="text-xs text-gray-400 mt-8">
              주문번호: {orderId}
            </p>
          )}

          <p className="text-xs text-gray-400 mt-4">
            문제가 지속되면 support@adscope.kr로 문의해주세요.
          </p>
        </div>
      </main>
    </div>
  );
}
