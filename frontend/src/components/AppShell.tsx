"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import PlanExpiry from "@/components/PlanExpiry";

/** Wrapper that shows the sidebar on all pages except /login. */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";

  if (isLoginPage) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <div className="flex flex-1">
        <Sidebar />
        <main className="flex-1 mt-14 lg:mt-0 overflow-auto bg-gray-50">
          <PlanExpiry />
          {children}
        </main>
      </div>
      <footer className="border-t border-gray-200 bg-white text-xs text-gray-500 py-6 px-4 lg:ml-56">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row md:justify-between gap-4">
          <div className="space-y-1">
            <p className="font-semibold text-gray-700">더블이스튜디오(DoubleE Studio)</p>
            <p>대표: 박정면 | 사업자등록번호: 717-25-02109</p>
            <p>경기도 남양주시 경춘로 1305, 106동 605호(평내동, 평내호평역대명루첸포레스티움)</p>
            <p>업태: 정보통신업, 도매 및 소매업 | 종목: 모바일 게임 소프트웨어 개발 및 공급업, 전자상거래 소매업</p>
          </div>
          <div className="space-y-1 text-right md:text-right">
            <p>문의: admin@adscope.kr</p>
            <p className="text-gray-400">&copy; {new Date().getFullYear()} DoubleE Studio. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
