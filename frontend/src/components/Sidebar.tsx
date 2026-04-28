"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import clsx from "clsx";
import { useState, useEffect } from "react";
import { useTheme } from "next-themes";
import { getUser, logout, AuthUser, isInTrial } from "@/lib/auth";

type NavItem = { href: string; label: string; icon: string; beta?: boolean; soon?: boolean; adminOnly?: boolean; public?: boolean };
type NavGroup = { title: string; items: NavItem[]; public?: boolean; adminOnly?: boolean };

const NAV_GROUPS: NavGroup[] = [
  {
    title: "",
    public: true,
    items: [
      { href: "/reports", label: "보고서", icon: "report" },
      { href: "/advertisers/favorites", label: "나의 광고주", icon: "star" },
      { href: "/advertisers", label: "광고주", icon: "advertisers", public: true },
      { href: "/campaigns", label: "캠페인", icon: "campaign" },
      { href: "/gallery", label: "광고소재(이미지)", icon: "gallery", public: true },
      { href: "/gallery/keyword", label: "광고소재(키워드)", icon: "keyword", public: true },
      { href: "/social-gallery", label: "소셜 소재", icon: "social" },
    ],
  },
  {
    title: "키워드 분석",
    public: true,
    items: [
      { href: "/keyword-analysis/reverse", label: "키워드 역추적", icon: "reverse" },
      { href: "/keyword-analysis/landscape", label: "광고 랜드스케이프", icon: "landscape_kw" },
      { href: "/keyword-analysis/spend-trend", label: "광고비 추이", icon: "trend" },
    ],
  },
  {
    title: "소셜 인사이트",
    public: true,
    items: [
      { href: "/social-channels", label: "소셜 채널 분석", icon: "brand" },
      { href: "/social-content", label: "콘텐츠 성과", icon: "content" },
      { href: "/buzz-dashboard", label: "브랜드 버즈", icon: "buzz" },
      { href: "/campaign-effect", label: "캠페인 효과", icon: "effect" },
    ],
  },
  {
    title: "시장 분석",
    public: true,
    items: [
      { href: "/industries", label: "산업별 현황", icon: "landscape" },
      { href: "/products", label: "제품/서비스 현황", icon: "products" },
      { href: "/competitors", label: "경쟁사 비교", icon: "competitors" },
      { href: "/advertiser-trends", label: "광고주 트렌드", icon: "ranking" },
    ],
  },
  {
    title: "안내",
    public: true,
    items: [
      { href: "/guide", label: "서비스 소개", icon: "guide" },
      { href: "/manual", label: "이용 매뉴얼", icon: "manual" },
      { href: "/faq", label: "FAQ", icon: "faq" },
    ],
  },
  {
    title: "관리",
    adminOnly: true,
    items: [
      { href: "/", label: "대시보드", icon: "dashboard", adminOnly: true },
      { href: "/spend", label: "매체별 광고비", icon: "spend", adminOnly: true },
      { href: "/master-index", label: "매체/광고주 관리", icon: "database", adminOnly: true },
      { href: "/admin", label: "관리", icon: "admin", adminOnly: true },
      { href: "/admin/staging", label: "데이터 스테이징", icon: "staging", adminOnly: true },
    ],
  },
  {
    title: "쇼핑 분석",
    adminOnly: true,
    items: [
      { href: "/shopping-insight", label: "쇼핑인사이트", icon: "shopping" },
      { href: "/shopping-keyword", label: "키워드 분석", icon: "keyword" },
      { href: "/shopping-sales", label: "판매량 추정", icon: "sales" },
      { href: "/shopping-ranking", label: "상품 순위 추적", icon: "ranking" },
    ],
  },
  {
    title: "분석 도구",
    adminOnly: true,
    items: [
      { href: "/analytics/sov", label: "SOV 분석", icon: "sov" },
      { href: "/analytics/persona-contact", label: "페르소나 접촉률", icon: "contact" },
      { href: "/target-audience", label: "타겟 오디언스", icon: "target" },
      { href: "/consumer-insights", label: "소비자 인사이트", icon: "insight", soon: true },
      { href: "/launch-impact", label: "신상품 임팩트", icon: "launch", soon: true },
      { href: "/marketing-schedule", label: "마케팅 플랜", icon: "schedule", soon: true },
    ],
  },
];

function NavIcon({ name, className = "w-5 h-5" }: { name: string; className?: string }) {
  const props = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
  };

  switch (name) {
    case "star":
      return (
        <svg {...props}>
          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
        </svg>
      );
    case "dashboard":
      return (
        <svg {...props}>
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
      );
    case "snapshots":
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v5l3 3" />
        </svg>
      );
    case "advertisers":
      return (
        <svg {...props}>
          <circle cx="9" cy="7" r="3" />
          <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
          <circle cx="17" cy="8" r="2" />
          <path d="M21 21v-1a3 3 0 0 0-2-2.8" />
        </svg>
      );
    case "spend":
      return (
        <svg {...props}>
          <rect x="2" y="6" width="20" height="12" rx="2" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "contact":
      return (
        <svg {...props}>
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
      );
    case "sov":
      return (
        <svg {...props}>
          <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
          <path d="M22 12A10 10 0 0 0 12 2v10z" />
        </svg>
      );
    case "gallery":
      return (
        <svg {...props}>
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
      );
    case "admin":
      return (
        <svg {...props}>
          <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
        </svg>
      );
    case "ranking":
      return (
        <svg {...props}>
          <path d="M3 3v18h18" />
          <path d="M18 17V9" />
          <path d="M13 17V5" />
          <path d="M8 17v-3" />
        </svg>
      );
    case "competitors":
      return (
        <svg {...props}>
          <path d="M16 3h5v5" />
          <path d="M8 3H3v5" />
          <path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3" />
          <path d="m15 9 6-6" />
        </svg>
      );
    case "landscape":
      return (
        <svg {...props}>
          <path d="M2 20L8.5 8 13 16l4-6 5 10" />
          <path d="M2 20h20" />
        </svg>
      );
    case "brand":
      return (
        <svg {...props}>
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
        </svg>
      );
    case "social":
      return (
        <svg {...props}>
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 01-3.46 0" />
          <circle cx="18" cy="3" r="2" fill="currentColor" />
        </svg>
      );
    case "products":
      return (
        <svg {...props}>
          <path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
        </svg>
      );
    case "shopping":
      return (
        <svg {...props}>
          <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z" />
          <path d="M3 6h18" />
          <path d="M16 10a4 4 0 01-8 0" />
        </svg>
      );
    case "report":
      return (
        <svg {...props}>
          <path d="M9 17h6M9 13h6M9 9h4" />
          <path d="M5 3h10l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
          <path d="M15 3v4h4" />
        </svg>
      );
    case "guide":
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <circle cx="12" cy="17" r="0.5" fill="currentColor" />
        </svg>
      );
    case "manual":
      return (
        <svg {...props}>
          <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
          <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
          <path d="M8 7h8M8 11h6" />
        </svg>
      );
    case "settings":
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
        </svg>
      );
    case "faq":
      return (
        <svg {...props}>
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          <path d="M12 8v.01M12 12v3" />
        </svg>
      );
    case "buzz":
      return (
        <svg {...props}>
          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z" />
          <path d="M8 12l2 2 4-4" />
          <path d="M12 6v1M12 17v1M6 12h1M17 12h1" />
        </svg>
      );
    case "insight":
      return (
        <svg {...props}>
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
          <path d="M11 8v6M8 11h6" />
        </svg>
      );
    case "target":
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="10" />
          <circle cx="12" cy="12" r="6" />
          <circle cx="12" cy="12" r="2" />
        </svg>
      );
    case "effect":
      return (
        <svg {...props}>
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
          <circle cx="12" cy="12" r="2" fill="currentColor" />
        </svg>
      );
    case "signal":
      return (
        <svg {...props}>
          <path d="M2 20h.01" />
          <path d="M7 20v-4" />
          <path d="M12 20v-8" />
          <path d="M17 20V8" />
          <path d="M22 4v16" />
        </svg>
      );
    case "database":
      return (
        <svg {...props}>
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        </svg>
      );
    case "staging":
      return (
        <svg {...props}>
          <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
          <path d="M3.27 6.96L12 12.01l8.73-5.05M12 22.08V12" />
        </svg>
      );
    case "launch":
      return (
        <svg {...props}>
          <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 00-2.91-.09z" />
          <path d="M12 15l-3-3a22 22 0 012-3.95A12.88 12.88 0 0122 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 01-4 2z" />
          <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
          <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
        </svg>
      );
    case "campaign":
      return (
        <svg {...props}>
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      );
    case "schedule":
      return (
        <svg {...props}>
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
          <line x1="16" y1="2" x2="16" y2="6" />
          <line x1="8" y1="2" x2="8" y2="6" />
          <line x1="3" y1="10" x2="21" y2="10" />
          <path d="M8 14h.01M12 14h.01M16 14h.01M8 18h.01M12 18h.01" />
        </svg>
      );
    case "keyword":
      return (
        <svg {...props}>
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
          <path d="M8 11h6" />
        </svg>
      );
    case "reverse":
      return (
        <svg {...props}>
          <path d="M9 14l-4-4 4-4" />
          <path d="M5 10h11a4 4 0 110 8h-1" />
        </svg>
      );
    case "landscape_kw":
      return (
        <svg {...props}>
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M9 21V9" />
          <circle cx="15" cy="15" r="2" />
        </svg>
      );
    case "trend":
      return (
        <svg {...props}>
          <path d="M3 3v18h18" />
          <path d="M7 16l4-8 4 4 4-8" />
        </svg>
      );
    case "sales":
      return (
        <svg {...props}>
          <path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
        </svg>
      );
    case "content":
      return (
        <svg {...props}>
          <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
          <path d="M8 21h8M12 17v4" />
          <path d="M10 9l4 2-4 2V9z" fill="currentColor" />
        </svg>
      );
    default:
      return null;
  }
}

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setUser(getUser());
    setMounted(true);
  }, []);

  const DarkModeToggle = () =>
    mounted ? (
      <button
        onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        className="flex-shrink-0 p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/70 transition-colors"
        aria-label="Toggle dark mode"
        title={theme === "dark" ? "라이트 모드" : "다크 모드"}
      >
        {theme === "dark" ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
            <circle cx="12" cy="12" r="5" />
            <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
            <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        )}
      </button>
    ) : null;

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <Link href="/about" className="block px-6 py-4 hover:bg-slate-800/50 transition-colors group">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-900/30 group-hover:shadow-indigo-800/40 transition-shadow">
            <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-white">
              <path d="M3 3v18h18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              <path d="M7 16l4-6 3 3 3-7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-bold text-white tracking-tight">AdScope</h1>
            <p className="text-[10px] text-slate-400">광고 인텔리전스 플랫폼</p>
          </div>
        </div>
      </Link>

      {/* User / Login — top */}
      <div className="px-4 py-3 border-y border-slate-700/50">
        {user ? (
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-adscope-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              {(user.name || user.email)?.[0]?.toUpperCase() || "U"}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-white truncate leading-tight">
                {user.name || user.email}
              </p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={clsx(
                  "text-[9px] font-semibold px-1 py-0.5 rounded leading-none",
                  user.role === "admin" ? "bg-amber-500/20 text-amber-300" :
                  isInTrial() ? "bg-violet-500/20 text-violet-300" :
                  user.plan === "full" ? "bg-green-500/20 text-green-300" :
                  "bg-slate-600 text-slate-300"
                )}>
                  {user.role === "admin" ? "Admin" : isInTrial() ? "체험판" : user.plan === "full" ? "Full" : "Lite"}
                </span>
                <Link href="/settings" onClick={() => setOpen(false)} className="text-[10px] text-slate-400 hover:text-white transition-colors">설정</Link>
                <button
                  onClick={() => { if (window.confirm("로그아웃 하시겠습니까?")) logout(); }}
                  className="text-[10px] text-slate-400 hover:text-white transition-colors"
                >로그아웃</button>
              </div>
            </div>
            <DarkModeToggle />
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="flex-1 text-center py-1.5 px-3 bg-adscope-600 hover:bg-adscope-700 text-white text-xs font-medium rounded-lg transition-colors"
            >
              로그인
            </Link>
            <Link
              href="/pricing"
              className="flex-1 text-center py-1.5 px-3 border border-slate-600 text-slate-300 hover:text-white hover:border-slate-400 text-xs font-medium rounded-lg transition-colors"
            >
              회원가입
            </Link>
            <DarkModeToggle />
          </div>
        )}
      </div>

      {!user && (
        <div className="mx-3 mt-3 p-3 rounded-lg bg-indigo-950/60 border border-indigo-800/40">
          <p className="text-[11px] text-indigo-300 font-medium leading-snug mb-1.5">
            비회원 공개 열람
          </p>
          <p className="text-[10px] text-slate-400 leading-relaxed mb-2">
            리포트, 광고주, 캠페인, 소재, 키워드 분석과 시장 분석 화면을 회원 가입 없이 둘러볼 수 있습니다. 다운로드와 내보내기는 유료 가입 후 사용할 수 있습니다.
          </p>
          <Link
            href="/pricing"
            className="block text-center py-1 px-2 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-[11px] font-medium transition-colors"
          >
            요금제 보기 →
          </Link>
        </div>
      )}

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
        {NAV_GROUPS
          .map((group) => ({
            ...group,
            items: group.items.filter((item) => {
              if (item.adminOnly && user?.role !== "admin") return false;
              if (!user && !group.public && !item.public) return false;
              return true;
            }),
          }))
          .filter((group) => (!group.adminOnly || user?.role === "admin") && group.items.length > 0)
          .map((group, gi) => (
          <div key={gi}>
            {group.title && (
              <p className="px-3 mb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-widest">
                {group.title}
              </p>
            )}
            <div className="space-y-1">
              {group.items.map((item) => {
                const isActive =
                  item.href === "/"
                    ? pathname === "/"
                    : item.href === "/advertisers"
                    ? pathname === "/advertisers" || (pathname.startsWith("/advertisers/") && !pathname.startsWith("/advertisers/favorites"))
                    : item.href === "/admin"
                    ? pathname === "/admin"
                    : item.href === "/gallery"
                    ? pathname === "/gallery"
                    : pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={clsx(
                      "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200",
                      isActive
                        ? "bg-gradient-to-r from-adscope-600 to-indigo-600 text-white shadow-md shadow-indigo-900/20"
                        : "text-slate-300 hover:bg-slate-800/70 hover:text-white hover:translate-x-0.5"
                    )}
                  >
                    <NavIcon name={item.icon} />
                    <span className="flex items-center gap-1.5">
                      {item.label}
                      {item.beta && (
                        <span className="text-[9px] font-semibold leading-none px-1 py-0.5 rounded bg-amber-500/20 text-amber-300 uppercase tracking-wide">
                          Beta
                        </span>
                      )}
                      {item.soon && (
                        <span className="text-[9px] font-semibold leading-none px-1 py-0.5 rounded bg-slate-600 text-slate-400 uppercase tracking-wide">
                          준비중
                        </span>
                      )}
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-slate-700/50">
        <a
          href="https://doubleestudio.com"
          target="_blank"
          rel="noopener noreferrer"
          className="block text-center text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
        >
          Powered by DoubleE Studio
        </a>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile top bar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-30 bg-slate-900 border-b border-slate-700/50 px-4 py-3 flex items-center gap-3">
        <button
          onClick={() => setOpen(!open)}
          className="text-white p-1 hover:bg-slate-800 rounded"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6">
            {open ? (
              <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" strokeLinejoin="round" />
            )}
          </svg>
        </button>
        <Link href="/about" className="text-white font-bold">AdScope</Link>
      </div>

      {/* Mobile overlay */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-backdrop"
            onClick={() => setOpen(false)}
          />
          <div className="absolute left-0 top-0 bottom-0 w-64 bg-slate-900 shadow-2xl animate-slide-in-left">
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Desktop sidebar */}
      <aside className="hidden lg:block w-64 bg-gradient-to-b from-slate-900 to-slate-950 min-h-screen flex-shrink-0 border-r border-slate-800/50">
        {sidebarContent}
      </aside>
    </>
  );
}
