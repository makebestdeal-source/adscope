"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { getUser, isPlanExpired, daysUntilExpiry, isInTrial, AuthUser } from "@/lib/auth";

export default function PlanExpiry() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [expired, setExpired] = useState(false);
  const [daysLeft, setDaysLeft] = useState<number | null>(null);
  const [trial, setTrial] = useState(false);

  useEffect(() => {
    setUser(getUser());
    setExpired(isPlanExpired());
    setDaysLeft(daysUntilExpiry());
    setTrial(isInTrial());
  }, []);

  if (!user || user.role === "admin") return null;

  if (expired) {
    return (
      <div className="bg-red-50 border-b border-red-200 px-4 py-2.5 text-sm text-red-800 flex items-center justify-between">
        <span>무료 체험이 종료되었습니다. 유료 플랜으로 전환하여 모든 기능을 이용하세요.</span>
        <Link href="/payment?expired=true" className="ml-4 px-3 py-1 bg-red-600 text-white rounded text-xs font-semibold hover:bg-red-700 whitespace-nowrap">
          플랜 결제
        </Link>
      </div>
    );
  }

  if (trial && daysLeft !== null && daysLeft > 0) {
    return (
      <div className="bg-violet-50 border-b border-violet-200 px-4 py-2.5 text-sm text-violet-800 flex items-center justify-between">
        <span>무료 체험 {daysLeft}일 남았습니다. 모든 기능을 자유롭게 둘러보세요!</span>
        <Link href="/pricing" className="ml-4 px-3 py-1 bg-violet-600 text-white rounded text-xs font-semibold hover:bg-violet-700 whitespace-nowrap">
          플랜 보기
        </Link>
      </div>
    );
  }

  if (daysLeft !== null && daysLeft <= 7 && daysLeft > 0) {
    return (
      <div className="bg-amber-50 border-b border-amber-200 px-4 py-2.5 text-sm text-amber-800 flex items-center justify-between">
        <span>플랜 만료까지 {daysLeft}일 남았습니다.</span>
        <Link href="/payment" className="ml-4 px-3 py-1 bg-amber-600 text-white rounded text-xs font-semibold hover:bg-amber-700 whitespace-nowrap">
          갱신하기
        </Link>
      </div>
    );
  }

  return null;
}
