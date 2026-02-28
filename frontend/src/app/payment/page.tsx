"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { getUser, getToken } from "@/lib/auth";

declare global {
  interface Window {
    IMP?: {
      init: (storeId: string) => void;
      request_pay: (
        params: Record<string, unknown>,
        callback: (response: { success: boolean; imp_uid?: string; merchant_uid?: string; error_msg?: string }) => void
      ) => void;
    };
  }
}

const PLAN_NAMES: Record<string, string> = { lite: "Lite", full: "Full" };
const PLAN_PRICES: Record<string, Record<string, number>> = {
  lite: { monthly: 49000, yearly: 490000 },
  full: { monthly: 99000, yearly: 990000 },
};

function fmt(n: number) {
  return n.toLocaleString("ko-KR");
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
  const defaultPeriod = params.get("period") || "monthly";

  const [plan, setPlan] = useState(defaultPlan);
  const [period, setPeriod] = useState(defaultPeriod);
  const [step, setStep] = useState<"select" | "processing" | "done" | "error">("select");
  const [message, setMessage] = useState("");
  const [sdkLoaded, setSdkLoaded] = useState(false);

  const user = getUser();
  const token = getToken();
  const price = PLAN_PRICES[plan]?.[period] || 0;

  useEffect(() => {
    if (document.getElementById("iamport-sdk")) {
      setSdkLoaded(true);
      return;
    }
    const script = document.createElement("script");
    script.id = "iamport-sdk";
    script.src = "https://cdn.iamport.kr/v1/iamport.js";
    script.async = true;
    script.onload = () => setSdkLoaded(true);
    document.head.appendChild(script);
  }, []);

  const handlePayment = async () => {
    if (!token || !user) {
      setMessage("Please log in first.");
      setStep("error");
      return;
    }

    setStep("processing");

    try {
      const prepared = await api.preparePayment(plan, period);

      if (!sdkLoaded || !window.IMP) {
        setMessage("Payment SDK is loading. Please try again.");
        setStep("error");
        return;
      }

      window.IMP.init(prepared.store_id);

      window.IMP.request_pay(
        {
          pg: "html5_inicis",
          pay_method: "card",
          merchant_uid: prepared.merchant_uid,
          name: `AdScope ${PLAN_NAMES[plan]} (${period === "monthly" ? "Monthly" : "Yearly"})`,
          amount: prepared.amount,
          buyer_email: prepared.buyer_email,
          buyer_name: prepared.buyer_name,
        },
        async (response) => {
          if (response.success && response.imp_uid && response.merchant_uid) {
            try {
              await api.completePayment(response.imp_uid, response.merchant_uid);
              setMessage("Payment completed successfully. Please wait for admin approval to activate your plan.");
              setStep("done");
            } catch {
              setMessage("Payment was processed but verification failed. Please contact support.");
              setStep("error");
            }
          } else {
            setMessage(response.error_msg || "Payment was cancelled or failed.");
            setStep("error");
          }
        }
      );
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : "Payment preparation failed.");
      setStep("error");
    }
  };

  if (!user || !token) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-600 mb-4">Please log in to proceed with payment.</p>
          <Link href="/login" className="px-6 py-3 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700">
            Login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-indigo-600">AdScope</Link>
          <Link href="/" className="text-sm text-gray-600 hover:text-indigo-600">Back to Dashboard</Link>
        </div>
      </header>

      <main className="max-w-lg mx-auto px-6 py-12">
        {isExpired && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
            Your free trial or plan has expired. Please subscribe to continue using AdScope.
          </div>
        )}

        {step === "select" && (
          <>
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Subscribe to AdScope</h1>
            <p className="text-sm text-gray-500 mb-8">Select your plan and proceed to payment.</p>

            {/* Plan Selection */}
            <div className="mb-5">
              <label className="block text-sm font-semibold text-gray-700 mb-2">Plan</label>
              <div className="grid grid-cols-2 gap-3">
                {(["lite", "full"] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPlan(p)}
                    className={`p-4 rounded-lg border-2 text-left transition-colors ${
                      plan === p
                        ? "border-indigo-500 bg-indigo-50"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    <span className="text-sm font-bold text-gray-900">{PLAN_NAMES[p]}</span>
                    <span className="block text-xs text-gray-500 mt-0.5">
                      {p === "lite" ? "Ad data only" : "Full features"}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Period */}
            <div className="mb-6">
              <label className="block text-sm font-semibold text-gray-700 mb-2">Billing Period</label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setPeriod("monthly")}
                  className={`p-3 rounded-lg border-2 text-left ${
                    period === "monthly" ? "border-indigo-500 bg-indigo-50" : "border-gray-200"
                  }`}
                >
                  <span className="text-sm font-bold">Monthly</span>
                  <span className="block text-xs text-gray-500">{fmt(PLAN_PRICES[plan].monthly)} KRW/mo</span>
                </button>
                <button
                  type="button"
                  onClick={() => setPeriod("yearly")}
                  className={`p-3 rounded-lg border-2 text-left ${
                    period === "yearly" ? "border-indigo-500 bg-indigo-50" : "border-gray-200"
                  }`}
                >
                  <span className="text-sm font-bold">Yearly <span className="text-emerald-600 text-xs">Save 17%</span></span>
                  <span className="block text-xs text-gray-500">{fmt(PLAN_PRICES[plan].yearly)} KRW/yr</span>
                </button>
              </div>
            </div>

            {/* Summary */}
            <div className="bg-white rounded-lg p-5 border border-gray-200 mb-6">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-600">Plan</span>
                <span className="font-semibold">{PLAN_NAMES[plan]} ({period === "monthly" ? "Monthly" : "Yearly"})</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Amount</span>
                <span className="font-bold text-lg text-gray-900">{fmt(price)} KRW <span className="text-xs text-gray-400">(excl. VAT)</span></span>
              </div>
            </div>

            <button
              onClick={handlePayment}
              className="w-full py-3 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 transition-colors"
            >
              Proceed to Payment
            </button>
          </>
        )}

        {step === "processing" && (
          <div className="text-center py-20">
            <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mx-auto mb-4" />
            <p className="text-gray-600">Processing payment...</p>
          </div>
        )}

        {step === "done" && (
          <div className="text-center py-10">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-emerald-100 flex items-center justify-center">
              <svg className="w-8 h-8 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Payment Submitted!</h2>
            <p className="text-sm text-gray-500 mb-6">{message}</p>
            <Link href="/" className="px-6 py-3 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700">
              Go to Dashboard
            </Link>
          </div>
        )}

        {step === "error" && (
          <div className="text-center py-10">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
              <svg className="w-8 h-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Payment Issue</h2>
            <p className="text-sm text-gray-500 mb-6">{message}</p>
            <button
              onClick={() => setStep("select")}
              className="px-6 py-3 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700"
            >
              Try Again
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
