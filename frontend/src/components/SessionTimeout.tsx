"use client";

import { useState, useEffect, useCallback } from "react";
import { getToken } from "@/lib/auth";

/** Decode JWT payload without external libraries */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const payload = parts[1];
    const decoded = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

/** Get JWT expiry timestamp in ms, or null if unavailable */
function getTokenExpiry(token: string): number | null {
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return null;
  return payload.exp * 1000; // convert seconds to ms
}

const WARNING_BEFORE_MS = 5 * 60 * 1000; // 5 minutes before expiry
const CHECK_INTERVAL_MS = 30 * 1000; // check every 30 seconds

export function SessionTimeout() {
  const [showWarning, setShowWarning] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(0);

  const checkExpiry = useCallback(() => {
    const token = getToken();
    if (!token) {
      setShowWarning(false);
      return;
    }

    const expiry = getTokenExpiry(token);
    if (!expiry) {
      setShowWarning(false);
      return;
    }

    const now = Date.now();
    const remaining = expiry - now;

    if (remaining <= 0) {
      // Token already expired -- the api.ts 401 handler will redirect
      setShowWarning(false);
      return;
    }

    if (remaining <= WARNING_BEFORE_MS) {
      setShowWarning(true);
      setRemainingSeconds(Math.ceil(remaining / 1000));
    } else {
      setShowWarning(false);
    }
  }, []);

  useEffect(() => {
    checkExpiry();
    const interval = setInterval(checkExpiry, CHECK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [checkExpiry]);

  // Countdown timer when warning is shown
  useEffect(() => {
    if (!showWarning) return;
    const countdown = setInterval(() => {
      setRemainingSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(countdown);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(countdown);
  }, [showWarning]);

  const handleExtend = async () => {
    try {
      const token = getToken();
      if (!token) return;

      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.ok) {
        const data = await res.json();
        if (data.access_token) {
          localStorage.setItem("adscope_token", data.access_token);
          // Update cookie as well
          const expires = new Date(Date.now() + 1 * 864e5).toUTCString();
          document.cookie = `adscope_token=${encodeURIComponent(data.access_token)}; expires=${expires}; path=/; SameSite=Lax`;
        }
        setShowWarning(false);
      } else {
        // If refresh fails, redirect to login
        window.location.href = "/login";
      }
    } catch {
      window.location.href = "/login";
    }
  };

  const formatRemaining = () => {
    const min = Math.floor(remainingSeconds / 60);
    const sec = remainingSeconds % 60;
    return `${min}:${sec.toString().padStart(2, "0")}`;
  };

  if (!showWarning) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[9999] max-w-sm">
      <div className="bg-amber-50 border border-amber-300 rounded-xl shadow-lg p-4">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 mt-0.5">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className="w-5 h-5 text-amber-600"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12,6 12,12 16,14" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-amber-800">
              세션이 곧 만료됩니다
            </p>
            <p className="text-xs text-amber-600 mt-0.5">
              {formatRemaining()} 후 자동 로그아웃됩니다
            </p>
            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={handleExtend}
                className="px-3 py-1.5 text-xs font-medium text-white bg-amber-600 rounded-lg hover:bg-amber-700 transition-colors"
              >
                연장
              </button>
              <button
                onClick={() => setShowWarning(false)}
                className="px-3 py-1.5 text-xs font-medium text-amber-700 hover:text-amber-900 transition-colors"
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
