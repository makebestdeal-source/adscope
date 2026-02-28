"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { getUser, isPlanExpired, daysUntilExpiry, AuthUser } from "@/lib/auth";

export default function PlanExpiry() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [expired, setExpired] = useState(false);
  const [daysLeft, setDaysLeft] = useState<number | null>(null);

  useEffect(() => {
    setUser(getUser());
    setExpired(isPlanExpired());
    setDaysLeft(daysUntilExpiry());
  }, []);

  if (!user || user.role === "admin") return null;

  if (expired) {
    return (
      <div className="bg-red-50 border-b border-red-200 px-4 py-2.5 text-sm text-red-800 flex items-center justify-between">
        <span>Your plan has expired. Please renew to continue using all features.</span>
        <Link href="/payment?expired=true" className="ml-4 px-3 py-1 bg-red-600 text-white rounded text-xs font-semibold hover:bg-red-700 whitespace-nowrap">
          Renew Now
        </Link>
      </div>
    );
  }

  if (daysLeft !== null && daysLeft <= 7 && daysLeft > 0) {
    return (
      <div className="bg-amber-50 border-b border-amber-200 px-4 py-2.5 text-sm text-amber-800 flex items-center justify-between">
        <span>Your plan expires in {daysLeft} day{daysLeft !== 1 ? "s" : ""}.</span>
        <Link href="/payment" className="ml-4 px-3 py-1 bg-amber-600 text-white rounded text-xs font-semibold hover:bg-amber-700 whitespace-nowrap">
          Renew
        </Link>
      </div>
    );
  }

  return null;
}
