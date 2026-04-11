"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { loadTossPayments, type TossPaymentsWidgets } from "@tosspayments/tosspayments-sdk";
import { getUser, getToken } from "@/lib/auth";
import { fetchApi } from "@/lib/api";

const PLAN_NAMES: Record<string, string> = { lite: "Lite", full: "Full" };
const PLAN_PRICES: Record<string, Record<string, number>> = {
  lite: { monthly: 49000, yearly: 490000 },
  full: { monthly: 99000, yearly: 990000 },
};
// PayPal USD prices (PayPal does not support KRW)
const PLAN_PRICES_USD: Record<string, Record<string, number>> = {
  lite: { monthly: 35, yearly: 350 },
  full: { monthly: 70, yearly: 700 },
};

function fmt(n: number) {
  return n.toLocaleString("ko-KR");
}

interface PreparedOrder {
  order_id: string;
  order_name: string;
  amount: number;
  client_key: string;
  customer_email: string;
  customer_name: string;
}

interface PaypalDoneInfo {
  plan: string;
  plan_period: string;
  amount: number;
  plan_expires_at: string | null;
}

export default function PaymentPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-gray-50" />}>
      <PaymentFlow />
    </Suspense>
  );
}

function PaymentFlow() {
  const params = useSearchParams();
  const isExpired = params.get("expired") === "true";
  const defaultPlan = params.get("plan") || "lite";
  const defaultCycle = params.get("cycle") || params.get("period") || "monthly";

  const [plan, setPlan] = useState(defaultPlan);
  const [cycle, setCycle] = useState(defaultCycle);
  const [paymentMethod, setPaymentMethod] = useState<"toss" | "paypal">("paypal");
  const [step, setStep] = useState<"select" | "widget" | "paypal-done" | "error">("select");
  const [errorMsg, setErrorMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [preparedOrder, setPreparedOrder] = useState<PreparedOrder | null>(null);
  const [paypalClientId, setPaypalClientId] = useState<string | null>(null);
  const [paypalLoaded, setPaypalLoaded] = useState(false);
  const [paypalDoneInfo, setPaypalDoneInfo] = useState<PaypalDoneInfo | null>(null);

  const widgetsRef = useRef<TossPaymentsWidgets | null>(null);
  const paymentMethodRef = useRef<HTMLDivElement>(null);
  const agreementRef = useRef<HTMLDivElement>(null);
  const paypalButtonRef = useRef<HTMLDivElement>(null);

  const user = getUser();
  const token = getToken();
  const price = PLAN_PRICES[plan]?.[cycle] || 0;

  // PayPal config 로드
  useEffect(() => {
    fetchApi<{ client_id: string; mode: string }>("/payments/paypal/config")
      .then((cfg) => setPaypalClientId(cfg.client_id))
      .catch(() => {}); // PayPal 미설정 시 조용히 무시
  }, []);

  // PayPal JS SDK 스크립트 로드
  useEffect(() => {
    if (!paypalClientId || paymentMethod !== "paypal") return;
    if ((window as unknown as Record<string, unknown>).paypal) {
      setPaypalLoaded(true);
      return;
    }
    if (document.getElementById("paypal-sdk")) return; // 이미 로딩 중
    const script = document.createElement("script");
    script.id = "paypal-sdk";
    script.src = `https://www.paypal.com/sdk/js?client-id=${paypalClientId}&currency=USD&locale=ko_KR&components=buttons`;
    script.onload = () => setPaypalLoaded(true);
    document.head.appendChild(script);
  }, [paypalClientId, paymentMethod]);

  // PayPal 버튼 렌더링
  useEffect(() => {
    if (!paypalLoaded || paymentMethod !== "paypal" || step !== "select") return;
    const container = paypalButtonRef.current;
    const paypalSDK = (window as unknown as Record<string, unknown>).paypal as Record<string, unknown> | undefined;
    if (!container || !paypalSDK) return;
    container.innerHTML = "";

    type PaypalButtonsInstance = { render: (el: HTMLElement) => Promise<void> };
    type PaypalButtonsFactory = (opts: unknown) => PaypalButtonsInstance;

    (paypalSDK.Buttons as PaypalButtonsFactory)({
      style: { layout: "vertical", color: "gold", shape: "rect", label: "pay", height: 48 },
      createOrder: async () => {
        const res = await fetchApi<{ paypal_order_id: string }>("/payments/paypal/create-order", {
          method: "POST",
          body: JSON.stringify({ plan, plan_period: cycle }),
        });
        return res.paypal_order_id;
      },
      onApprove: async (data: { orderID: string }) => {
        setLoading(true);
        try {
          const res = await fetchApi<{
            plan: string;
            plan_period: string;
            amount: number;
            plan_expires_at: string | null;
          }>("/payments/paypal/capture-order", {
            method: "POST",
            body: JSON.stringify({ paypal_order_id: data.orderID }),
          });
          const currentUser = getUser();
          if (currentUser) {
            localStorage.setItem(
              "adscope_user",
              JSON.stringify({
                ...currentUser,
                plan: res.plan,
                plan_period: res.plan_period,
                plan_expires_at: res.plan_expires_at,
                paid: true,
              })
            );
          }
          setPaypalDoneInfo({
            plan: res.plan,
            plan_period: res.plan_period,
            amount: res.amount,
            plan_expires_at: res.plan_expires_at,
          });
          setStep("paypal-done");
        } catch (err: unknown) {
          setErrorMsg(err instanceof Error ? err.message : "PayPal 결제 처리에 실패했습니다.");
          setStep("error");
        } finally {
          setLoading(false);
        }
      },
      onError: () => {
        setErrorMsg("PayPal 결제 중 오류가 발생했습니다. 다시 시도해주세요.");
        setStep("error");
      },
    })
      .render(container)
      .catch(() => {});
  }, [paypalLoaded, paymentMethod, step, plan, cycle]);

  // 토스 위젯 렌더링
  const renderWidget = useCallback(
    async (order: PreparedOrder) => {
      try {
        const tossPayments = await loadTossPayments(order.client_key);
        const widgets = tossPayments.widgets({ customerKey: `customer_${user?.id}` });
        widgetsRef.current = widgets;
        await widgets.setAmount({ currency: "KRW", value: order.amount });
        if (paymentMethodRef.current) {
          await widgets.renderPaymentMethods({ selector: "#payment-method", variantKey: "DEFAULT" });
        }
        if (agreementRef.current) {
          await widgets.renderAgreement({ selector: "#agreement", variantKey: "AGREEMENT" });
        }
      } catch (err) {
        console.error("Toss widget render error:", err);
        setErrorMsg("결제 위젯을 불러오는 데 실패했습니다. 새로고침 후 다시 시도해주세요.");
        setStep("error");
      }
    },
    [user?.id]
  );

  // 토스 결제 시작
  const handleStartPayment = async () => {
    if (!token || !user) {
      setErrorMsg("로그인이 필요합니다.");
      setStep("error");
      return;
    }
    setLoading(true);
    try {
      const prepared = await fetchApi<PreparedOrder>("/payments/ready", {
        method: "POST",
        body: JSON.stringify({ plan, plan_period: cycle }),
      });
      setPreparedOrder(prepared);
      setStep("widget");
      setTimeout(() => renderWidget(prepared), 100);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : "결제 준비에 실패했습니다.");
      setStep("error");
    } finally {
      setLoading(false);
    }
  };

  // 토스 결제 요청
  const handleRequestPayment = async () => {
    if (!widgetsRef.current || !preparedOrder) return;
    setLoading(true);
    try {
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      await widgetsRef.current.requestPayment({
        orderId: preparedOrder.order_id,
        orderName: preparedOrder.order_name,
        successUrl: `${origin}/payment/success`,
        failUrl: `${origin}/payment/fail`,
        customerEmail: preparedOrder.customer_email,
        customerName: preparedOrder.customer_name,
      });
    } catch (err: unknown) {
      if (err instanceof Error && err.message.includes("USER_CANCEL")) {
        setStep("select");
      } else {
        setErrorMsg(err instanceof Error ? err.message : "결제 요청에 실패했습니다.");
        setStep("error");
      }
    } finally {
      setLoading(false);
    }
  };

  if (!user || !token) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 mb-4">결제를 진행하려면 먼저 로그인해주세요.</p>
          <Link
            href="/login"
            className="px-6 py-3 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700"
          >
            로그인
          </Link>
        </div>
      </div>
    );
  }

  const planLabel = PLAN_NAMES[paypalDoneInfo?.plan || plan] || "Lite";
  const periodLabel = (paypalDoneInfo?.plan_period || cycle) === "yearly" ? "연간" : "월간";
  const expiresAt = paypalDoneInfo?.plan_expires_at
    ? new Date(paypalDoneInfo.plan_expires_at).toLocaleDateString("ko-KR", {
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
          <Link href="/" className="flex items-center gap-2.5 group">
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
          <Link href="/" className="text-sm text-gray-500 hover:text-indigo-600 font-medium transition-colors">
            대시보드로 돌아가기
          </Link>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-6 py-12">
        {isExpired && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl text-sm text-amber-800">
            <div className="flex items-start gap-2">
              <svg
                className="w-5 h-5 flex-shrink-0 text-amber-500 mt-0.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div>
                <p className="font-semibold">이용 기간이 만료되었습니다</p>
                <p className="text-xs text-amber-700 mt-0.5">
                  AdScope를 계속 이용하시려면 결제를 진행해주세요.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Step 1: 플랜 선택 */}
        {step === "select" && (
          <>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">AdScope 구독하기</h1>
            <p className="text-sm text-gray-500 mb-8">플랜과 결제 주기를 선택한 뒤 결제를 진행해주세요.</p>

            {/* Plan Selection */}
            <div className="mb-5">
              <label className="block text-sm font-semibold text-gray-700 mb-2">플랜 선택</label>
              <div className="grid grid-cols-2 gap-3">
                {(["lite", "full"] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPlan(p)}
                    className={`p-4 rounded-xl border-2 text-left transition-all duration-200 ${
                      plan === p
                        ? p === "full"
                          ? "border-emerald-500 bg-emerald-50 shadow-sm"
                          : "border-indigo-500 bg-indigo-50 shadow-sm"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-gray-900">{PLAN_NAMES[p]}</span>
                      {p === "full" && (
                        <span className="text-[10px] bg-emerald-500 text-white px-1.5 py-0.5 rounded-full font-bold">
                          추천
                        </span>
                      )}
                    </div>
                    <span className="block text-xs text-gray-500 mt-1">
                      {p === "lite" ? "광고 정보 중심 분석" : "광고 + 소셜 통합 분석"}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Billing Cycle */}
            <div className="mb-5">
              <label className="block text-sm font-semibold text-gray-700 mb-2">결제 주기</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setCycle("monthly")}
                  className={`p-3.5 rounded-xl border-2 text-left transition-all duration-200 ${
                    cycle === "monthly"
                      ? "border-indigo-500 bg-indigo-50 shadow-sm"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <span className="text-sm font-bold">월간 결제</span>
                  <span className="block text-xs text-gray-500 mt-0.5">
                    {fmt(PLAN_PRICES[plan]?.monthly || 0)}원/월
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setCycle("yearly")}
                  className={`p-3.5 rounded-xl border-2 text-left transition-all duration-200 ${
                    cycle === "yearly"
                      ? "border-indigo-500 bg-indigo-50 shadow-sm"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm font-bold">연간 결제</span>
                    <span className="text-[10px] bg-emerald-100 text-emerald-700 font-semibold px-1.5 py-0.5 rounded-md">
                      17% 할인
                    </span>
                  </div>
                  <span className="block text-xs text-gray-500 mt-0.5">
                    {fmt(PLAN_PRICES[plan]?.yearly || 0)}원/년
                  </span>
                </button>
              </div>
            </div>

            {/* Payment Method */}
            {paypalClientId && (
              <div className="mb-5">
                <label className="block text-sm font-semibold text-gray-700 mb-2">결제 수단</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    disabled
                    className="p-3.5 rounded-xl border-2 text-left border-gray-200 opacity-50 cursor-not-allowed"
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-bold text-gray-900">토스페이먼츠</span>
                      <span className="text-[10px] bg-gray-200 text-gray-500 px-1.5 py-0.5 rounded-full font-semibold">준비중</span>
                    </div>
                    <span className="block text-xs text-gray-400 mt-0.5">카드·계좌이체·간편결제</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setPaymentMethod("paypal")}
                    className={`p-3.5 rounded-xl border-2 text-left transition-all duration-200 ${
                      paymentMethod === "paypal"
                        ? "border-blue-500 bg-blue-50 shadow-sm"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-bold text-[#003087]">Pay</span>
                      <span className="text-sm font-bold text-[#009cde]">Pal</span>
                    </div>
                    <span className="block text-xs text-gray-500 mt-0.5">해외 카드·페이팔 계정</span>
                  </button>
                </div>
              </div>
            )}

            {/* Order Summary */}
            <div className="bg-white rounded-xl p-5 border border-gray-200 mb-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">주문 요약</h3>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">플랜</span>
                  <span className="font-medium text-gray-900">
                    {PLAN_NAMES[plan]} ({cycle === "monthly" ? "월간" : "연간"})
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">결제 금액</span>
                  {paymentMethod === "paypal" && paypalClientId ? (
                    <span className="font-bold text-lg text-gray-900">
                      ${PLAN_PRICES_USD[plan]?.[cycle] || 0} USD
                    </span>
                  ) : (
                    <span className="font-bold text-lg text-gray-900">{fmt(price)}원</span>
                  )}
                </div>
                <p className="text-[11px] text-gray-400 text-right">부가세 별도</p>
              </div>
            </div>

            {/* CTA: 토스 or PayPal */}
            {paymentMethod === "toss" || !paypalClientId ? (
              <>
                <button
                  onClick={handleStartPayment}
                  disabled={loading}
                  className="w-full py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                        <path
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                          fill="currentColor"
                          className="opacity-75"
                        />
                      </svg>
                      준비 중...
                    </span>
                  ) : (
                    "결제하기"
                  )}
                </button>
                <p className="text-xs text-gray-400 text-center mt-3">
                  토스페이먼츠를 통해 안전하게 결제가 진행됩니다.
                </p>
              </>
            ) : (
              <>
                {loading && (
                  <div className="flex items-center justify-center gap-2 py-3 text-sm text-gray-500 mb-2">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                      <path
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        fill="currentColor"
                        className="opacity-75"
                      />
                    </svg>
                    처리 중...
                  </div>
                )}
                {!paypalLoaded && (
                  <div className="flex items-center justify-center gap-2 py-4 text-sm text-gray-400">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                      <path
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        fill="currentColor"
                        className="opacity-75"
                      />
                    </svg>
                    PayPal 로딩 중...
                  </div>
                )}
                <div ref={paypalButtonRef} className={paypalLoaded ? "" : "hidden"} />
                <p className="text-xs text-gray-400 text-center mt-3">
                  PayPal을 통해 안전하게 결제가 진행됩니다.
                </p>
              </>
            )}

            {/* 계좌이체·세금계산서 안내 */}
            <div className="mt-6 p-4 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-600">
              <p className="font-semibold text-gray-700 mb-1">계좌이체·세금계산서가 필요하신가요?</p>
              <p className="text-xs text-gray-500 leading-relaxed">
                현재 온라인 결제는 카드(토스페이먼츠·PayPal)만 지원됩니다.
                현금영수증 발급이나 세금계산서 처리가 필요하신 경우{" "}
                <a
                  href="mailto:support@adscope.kr"
                  className="text-indigo-600 font-medium hover:underline"
                >
                  support@adscope.kr
                </a>
                {" "}로 문의해 주세요.
              </p>
            </div>
          </>
        )}

        {/* Step 2: 토스 결제 위젯 */}
        {step === "widget" && (
          <>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">결제 수단 선택</h1>
            <p className="text-sm text-gray-500 mb-6">결제 수단을 선택하고 결제를 완료해주세요.</p>
            <div className="bg-indigo-50 rounded-xl p-4 mb-6 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold text-indigo-900">
                  AdScope {PLAN_NAMES[plan]} ({cycle === "monthly" ? "월간" : "연간"})
                </p>
                <p className="text-xs text-indigo-600 mt-0.5">{user.email}</p>
              </div>
              <p className="text-lg font-bold text-indigo-900">{fmt(price)}원</p>
            </div>
            <div id="payment-method" ref={paymentMethodRef} className="mb-4" />
            <div id="agreement" ref={agreementRef} className="mb-6" />
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setStep("select");
                  widgetsRef.current = null;
                }}
                className="flex-1 py-3 border border-gray-300 text-gray-700 rounded-xl text-sm font-semibold hover:bg-gray-50 transition-colors"
              >
                이전으로
              </button>
              <button
                onClick={handleRequestPayment}
                disabled={loading}
                className="flex-[2] py-3 bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98] disabled:opacity-50"
              >
                {loading ? "처리 중..." : `${fmt(price)}원 결제하기`}
              </button>
            </div>
          </>
        )}

        {/* Step 3: PayPal 결제 완료 */}
        {step === "paypal-done" && paypalDoneInfo && (
          <div className="text-center">
            <div className="w-20 h-20 mx-auto mb-6 rounded-full bg-gradient-to-br from-emerald-100 to-teal-100 flex items-center justify-center shadow-lg shadow-emerald-100/50">
              <svg
                className="w-10 h-10 text-emerald-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">결제가 완료되었습니다!</h2>
            <p className="text-sm text-gray-500 mb-8">PayPal 결제가 성공적으로 처리되었습니다.</p>
            <div className="bg-white rounded-2xl border border-gray-200 p-6 mb-8 text-left shadow-sm">
              <h3 className="text-sm font-semibold text-gray-500 mb-3">구독 정보</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">플랜</span>
                  <span className="font-semibold text-gray-900">AdScope {planLabel}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">결제 주기</span>
                  <span className="font-medium text-gray-900">{periodLabel}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">결제 금액</span>
                  <span className="font-bold text-gray-900">${paypalDoneInfo.amount} USD</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">결제 수단</span>
                  <span className="font-medium text-gray-900">PayPal</span>
                </div>
                {expiresAt && (
                  <div className="flex justify-between items-center pt-2 border-t border-gray-100">
                    <span className="text-sm text-gray-600">이용 기간</span>
                    <span className="font-medium text-gray-900">{expiresAt}까지</span>
                  </div>
                )}
              </div>
            </div>
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-8 py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-xl text-sm font-semibold hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98]"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
                />
              </svg>
              대시보드로 이동
            </Link>
          </div>
        )}

        {/* Error */}
        {step === "error" && (
          <div className="text-center py-10">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
              <svg
                className="w-8 h-8 text-red-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">결제 오류</h2>
            <p className="text-sm text-gray-500 mb-6">{errorMsg}</p>
            <button
              onClick={() => {
                setStep("select");
                setErrorMsg("");
              }}
              className="px-6 py-3 bg-indigo-600 text-white rounded-xl text-sm font-semibold hover:bg-indigo-700 transition-colors"
            >
              다시 시도하기
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
