"use client";

import { useEffect, useState, useCallback } from "react";

/**
 * ContentProtection — 사이트 콘텐츠 복사/캡처 방지
 *
 * 1. 텍스트 선택 차단 (CSS user-select: none)
 * 2. 우클릭 컨텍스트 메뉴 차단
 * 3. 단축키 차단: Ctrl+C/S/U/A/P, F12, PrintScreen
 * 4. 인쇄 차단 (@media print)
 * 5. 워터마크 오버레이 (사용자 이메일)
 * 6. 탭 비활성 시 콘텐츠 숨김 (캡처 도구 방지)
 */
export default function ContentProtection() {
  const [showShield, setShowShield] = useState(false);
  const [userEmail, setUserEmail] = useState("");

  useEffect(() => {
    // Get user email for watermark
    try {
      const token = localStorage.getItem("adscope_token");
      if (token) {
        const parts = token.split(".");
        if (parts[1]) {
          const payload = JSON.parse(atob(parts[1]));
          setUserEmail(payload.sub || "");
        }
      }
    } catch {
      // ignore
    }

    // Add protected class to body
    document.body.classList.add("protected");

    return () => {
      document.body.classList.remove("protected");
    };
  }, []);

  // Block right-click
  useEffect(() => {
    const handleContextMenu = (e: MouseEvent) => {
      e.preventDefault();
      return false;
    };
    document.addEventListener("contextmenu", handleContextMenu);
    return () => document.removeEventListener("contextmenu", handleContextMenu);
  }, []);

  // Block keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Block Ctrl+C (copy), Ctrl+S (save), Ctrl+U (view source), Ctrl+A (select all), Ctrl+P (print)
      if (e.ctrlKey && ["c", "s", "u", "a", "p"].includes(e.key.toLowerCase())) {
        // Allow Ctrl+C/A/V in input fields
        const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
        if (["input", "textarea", "select"].includes(tag)) return;
        e.preventDefault();
        return false;
      }

      // Block F12 (DevTools)
      if (e.key === "F12") {
        e.preventDefault();
        return false;
      }

      // Block Ctrl+Shift+I (DevTools), Ctrl+Shift+J (Console), Ctrl+Shift+C (Inspector)
      if (e.ctrlKey && e.shiftKey && ["i", "j", "c"].includes(e.key.toLowerCase())) {
        e.preventDefault();
        return false;
      }

      // Block PrintScreen
      if (e.key === "PrintScreen") {
        e.preventDefault();
        setShowShield(true);
        // Copy blank to clipboard
        navigator.clipboard?.writeText?.("").catch(() => {});
        setTimeout(() => setShowShield(false), 1000);
        return false;
      }
    };
    document.addEventListener("keydown", handleKeyDown, true);
    return () => document.removeEventListener("keydown", handleKeyDown, true);
  }, []);

  // Block drag (prevents dragging images/text)
  useEffect(() => {
    const handleDragStart = (e: DragEvent) => {
      e.preventDefault();
      return false;
    };
    document.addEventListener("dragstart", handleDragStart);
    return () => document.removeEventListener("dragstart", handleDragStart);
  }, []);

  // Visibility change — show shield when tab loses focus (screen capture tools)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === "hidden") {
        setShowShield(true);
      } else {
        // Small delay before removing shield
        setTimeout(() => setShowShield(false), 300);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  // Generate watermark positions
  const watermarks = useCallback(() => {
    if (!userEmail) return null;
    const items = [];
    const cols = 5;
    const rows = 8;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        items.push(
          <span
            key={`${r}-${c}`}
            className="content-watermark-text"
            style={{
              top: `${(r * 100) / rows + 5}%`,
              left: `${(c * 100) / cols - 5}%`,
            }}
          >
            {userEmail} &middot; AdScope
          </span>
        );
      }
    }
    return items;
  }, [userEmail]);

  return (
    <>
      {/* Watermark overlay */}
      <div className="content-watermark" aria-hidden="true">
        {watermarks()}
      </div>

      {/* Capture shield */}
      {showShield && (
        <div className="capture-shield" aria-hidden="true">
          AdScope - 화면 캡처가 제한됩니다
        </div>
      )}
    </>
  );
}
