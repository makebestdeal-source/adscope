"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, PublicStats } from "@/lib/api";

// ─── 브라우저 프레임 래퍼 ─────────────────────────────────────────
function BrowserFrame({
  url,
  children,
}: {
  url: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-2xl overflow-hidden">
      <div className="bg-gray-100 border-b border-gray-200 px-4 py-2.5 flex items-center gap-3">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-400" />
          <div className="w-3 h-3 rounded-full bg-yellow-400" />
          <div className="w-3 h-3 rounded-full bg-green-400" />
        </div>
        <div className="flex-1 bg-white rounded-md text-[11px] text-gray-400 px-3 py-1 font-mono border border-gray-200">
          {url}
        </div>
      </div>
      {children}
    </div>
  );
}

// ─── 광고 소재 갤러리 목업 ────────────────────────────────────────
function AdGalleryMockup() {
  const ads = [
    {
      brand: "삼성전자",
      ch: "유튜브",
      tagBg: "bg-red-500",
      tag: "영상",
      cardBg: "from-red-500 to-red-700",
    },
    {
      brand: "LG전자",
      ch: "네이버",
      tagBg: "bg-green-500",
      tag: "검색",
      cardBg: "from-green-500 to-green-700",
    },
    {
      brand: "현대자동차",
      ch: "메타",
      tagBg: "bg-blue-500",
      tag: "피드",
      cardBg: "from-blue-500 to-blue-700",
    },
    {
      brand: "카카오",
      ch: "카카오",
      tagBg: "bg-yellow-500",
      tag: "DA",
      cardBg: "from-yellow-400 to-yellow-600",
    },
    {
      brand: "쿠팡",
      ch: "구글",
      tagBg: "bg-sky-500",
      tag: "GDN",
      cardBg: "from-sky-400 to-sky-600",
    },
    {
      brand: "배달의민족",
      ch: "틱톡",
      tagBg: "bg-gray-600",
      tag: "숏폼",
      cardBg: "from-gray-600 to-gray-900",
    },
  ];
  return (
    <BrowserFrame url="adscope.kr/gallery">
      <div className="p-5 bg-gray-50">
        <div className="flex items-center justify-between mb-4">
          <span className="text-sm font-semibold text-gray-800">
            광고 소재 갤러리
          </span>
          <div className="flex gap-1.5">
            {["전체", "유튜브", "네이버", "메타"].map((f, i) => (
              <span
                key={f}
                className={`text-xs px-2.5 py-1 rounded-full ${
                  i === 0
                    ? "bg-indigo-600 text-white"
                    : "bg-white border border-gray-200 text-gray-500"
                }`}
              >
                {f}
              </span>
            ))}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {ads.map((ad, i) => (
            <div
              key={i}
              className="rounded-xl overflow-hidden border border-gray-200 bg-white shadow-sm"
            >
              <div
                className={`h-20 bg-gradient-to-br ${ad.cardBg} flex items-end p-2 relative`}
              >
                <span
                  className={`absolute top-2 right-2 text-[10px] ${ad.tagBg} text-white px-1.5 py-0.5 rounded-full`}
                >
                  {ad.tag}
                </span>
                <div>
                  <p className="text-white text-xs font-bold leading-tight">
                    {ad.brand}
                  </p>
                  <p className="text-white/70 text-[10px]">{ad.ch}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between">
          <span className="text-[10px] text-gray-400">총 39,609개 소재</span>
          <span className="text-[10px] text-indigo-600 font-medium">
            + 오늘 수집 284건
          </span>
        </div>
      </div>
    </BrowserFrame>
  );
}

// ─── 캠페인 리포트 목업 ───────────────────────────────────────────
function CampaignMockup() {
  const rows = [
    {
      name: "갤럭시 S25 론칭 캠페인",
      ch: "유튜브",
      spend: 88,
      color: "bg-red-500",
    },
    {
      name: "봄 신제품 프로모션",
      ch: "네이버",
      spend: 72,
      color: "bg-green-500",
    },
    {
      name: "아이오닉 6 브랜드필름",
      ch: "메타",
      spend: 65,
      color: "bg-blue-500",
    },
    {
      name: "로켓배송 혜택 광고",
      ch: "구글",
      spend: 54,
      color: "bg-sky-500",
    },
    {
      name: "카카오페이 포인트",
      ch: "카카오",
      spend: 43,
      color: "bg-yellow-500",
    },
  ];
  return (
    <BrowserFrame url="adscope.kr/campaigns">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-semibold text-gray-800">
              캠페인 리포트
            </p>
            <p className="text-xs text-gray-400">최근 30일 추정 집행 현황</p>
          </div>
          <span className="text-xs bg-indigo-50 text-indigo-600 px-3 py-1 rounded-full font-medium">
            광고비 추정
          </span>
        </div>
        <div className="space-y-3">
          {rows.map((r, i) => (
            <div key={i}>
              <div className="flex justify-between text-xs mb-1.5">
                <span className="text-gray-700 font-medium truncate max-w-[180px]">
                  {r.name}
                </span>
                <span className="text-gray-400 flex-shrink-0 ml-2">
                  {r.ch}
                </span>
              </div>
              <div className="w-full bg-gray-100 rounded-full h-2.5">
                <div
                  className={`h-2.5 rounded-full ${r.color}`}
                  style={{ width: `${r.spend}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-3 gap-3">
          {[
            ["총 캠페인", "1,286"],
            ["신규 (7일)", "+23"],
            ["채널", "9개"],
          ].map(([l, v]) => (
            <div key={l} className="bg-gray-50 rounded-xl p-3 text-center">
              <p className="text-[10px] text-gray-400 mb-0.5">{l}</p>
              <p className="text-sm font-bold text-indigo-600">{v}</p>
            </div>
          ))}
        </div>
      </div>
    </BrowserFrame>
  );
}

// ─── 키워드 역추적 목업 ───────────────────────────────────────────
function KeywordMockup() {
  const keywords = [
    { kw: "삼성 갤럭시 S25", adv: 8, bid: "3,200", trend: "+12%", up: true },
    { kw: "전기차 추천 2025", adv: 5, bid: "4,800", trend: "+28%", up: true },
    { kw: "다이어트 보조제", adv: 12, bid: "2,100", trend: "-5%", up: false },
    { kw: "클라우드 솔루션", adv: 7, bid: "6,700", trend: "+41%", up: true },
    { kw: "호텔 특가 예약", adv: 15, bid: "1,900", trend: "+8%", up: true },
  ];
  return (
    <BrowserFrame url="adscope.kr/keyword-analysis/reverse">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-semibold text-gray-800">
              키워드 역추적 분석
            </p>
            <p className="text-xs text-gray-400">
              경쟁사가 집행 중인 키워드 파악
            </p>
          </div>
          <div className="flex gap-2">
            <span className="text-xs bg-green-50 text-green-700 px-2.5 py-1 rounded-full border border-green-200">
              네이버
            </span>
            <span className="text-xs bg-sky-50 text-sky-700 px-2.5 py-1 rounded-full border border-sky-200">
              구글
            </span>
          </div>
        </div>
        <div className="rounded-xl border border-gray-100 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                <th className="text-left px-3 py-2.5 text-gray-500 font-medium">
                  키워드
                </th>
                <th className="text-center px-3 py-2.5 text-gray-500 font-medium">
                  광고주
                </th>
                <th className="text-right px-3 py-2.5 text-gray-500 font-medium">
                  입찰가
                </th>
                <th className="text-right px-3 py-2.5 text-gray-500 font-medium">
                  변동
                </th>
              </tr>
            </thead>
            <tbody>
              {keywords.map((k, i) => (
                <tr
                  key={i}
                  className="border-b border-gray-50 hover:bg-indigo-50/30"
                >
                  <td className="px-3 py-2.5 font-medium text-gray-800">
                    {k.kw}
                  </td>
                  <td className="px-3 py-2.5 text-center">
                    <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full font-semibold">
                      {k.adv}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right text-gray-700 font-mono">
                    ₩{k.bid}
                  </td>
                  <td
                    className={`px-3 py-2.5 text-right font-semibold ${k.up ? "text-emerald-600" : "text-red-500"}`}
                  >
                    {k.trend}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </BrowserFrame>
  );
}

// ─── SOV 시장 분석 목업 ───────────────────────────────────────────
function SOVMockup() {
  const brands = [
    { name: "삼성전자", pct: 28, color: "bg-indigo-500" },
    { name: "LG전자", pct: 19, color: "bg-violet-500" },
    { name: "현대자동차", pct: 15, color: "bg-cyan-500" },
    { name: "카카오", pct: 12, color: "bg-amber-500" },
    { name: "쿠팡", pct: 11, color: "bg-emerald-500" },
    { name: "기타", pct: 15, color: "bg-gray-300" },
  ];
  return (
    <BrowserFrame url="adscope.kr/analytics/sov">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-semibold text-gray-800">
              SOV 광고 점유율 분석
            </p>
            <p className="text-xs text-gray-400">
              가전/전자 카테고리 · 최근 30일
            </p>
          </div>
          <span className="text-xs bg-violet-50 text-violet-700 px-2.5 py-1 rounded-full border border-violet-200">
            가전/전자
          </span>
        </div>
        <div className="space-y-2.5">
          {brands.map((b, i) => (
            <div key={i} className="flex items-center gap-3">
              <span className="text-xs text-gray-600 w-20 text-right flex-shrink-0">
                {b.name}
              </span>
              <div className="flex-1 bg-gray-100 rounded-full h-3">
                <div
                  className={`${b.color} h-3 rounded-full`}
                  style={{ width: `${b.pct}%` }}
                />
              </div>
              <span className="text-xs font-bold text-gray-700 w-8 flex-shrink-0">
                {b.pct}%
              </span>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-gray-100 grid grid-cols-3 gap-3">
          {[
            ["분석 광고주", "47개"],
            ["업종 점유율", "TOP 6"],
            ["데이터 기간", "30일"],
          ].map(([l, v]) => (
            <div key={l} className="bg-gray-50 rounded-xl p-3 text-center">
              <p className="text-[10px] text-gray-400 mb-0.5">{l}</p>
              <p className="text-sm font-bold text-gray-800">{v}</p>
            </div>
          ))}
        </div>
      </div>
    </BrowserFrame>
  );
}

// ─── 소셜 인사이트 목업 ───────────────────────────────────────────
function SocialMockup() {
  const dataPoints = [30, 38, 35, 50, 48, 65, 62, 75, 80, 88, 84, 96];
  const w = 260,
    h = 70;
  const maxV = Math.max(...dataPoints);
  const minV = Math.min(...dataPoints);
  const toX = (i: number) => (i / (dataPoints.length - 1)) * w;
  const toY = (v: number) =>
    h - ((v - minV) / (maxV - minV)) * (h - 10) - 5;
  const pointsStr = dataPoints
    .map((v, i) => `${toX(i)},${toY(v)}`)
    .join(" ");
  const areaStr = `0,${h} ${pointsStr} ${w},${h}`;

  const contentCards = [
    {
      platform: "인스타",
      brand: "삼성전자",
      engagement: "8.4K",
      bg: "from-pink-400 to-purple-600",
    },
    {
      platform: "유튜브",
      brand: "현대자동차",
      engagement: "124K",
      bg: "from-red-400 to-red-600",
    },
    {
      platform: "인스타",
      brand: "LG전자",
      engagement: "5.2K",
      bg: "from-orange-400 to-pink-500",
    },
  ];

  return (
    <BrowserFrame url="adscope.kr/social-gallery">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-sm font-semibold text-gray-800">소셜 인사이트</p>
            <p className="text-xs text-gray-400">
              팔로워 성장 · 콘텐츠 참여율 분석
            </p>
          </div>
          <span className="text-xs bg-pink-50 text-pink-700 px-2.5 py-1 rounded-full border border-pink-200">
            삼성전자
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2 mb-4">
          {[
            ["팔로워", "3.2M", "+12.4%"],
            ["게시물", "284건", "이번 달"],
            ["참여율", "4.8%", "평균"],
          ].map(([l, v, sub]) => (
            <div
              key={l}
              className="bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl p-3 text-center"
            >
              <p className="text-[10px] text-gray-400">{l}</p>
              <p className="text-sm font-bold text-gray-800">{v}</p>
              <p className="text-[10px] text-indigo-500">{sub}</p>
            </div>
          ))}
        </div>
        <div className="bg-gray-50 rounded-xl p-3 mb-4">
          <p className="text-[10px] text-gray-400 mb-2">팔로워 증가 추이 (12주)</p>
          <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-16">
            <defs>
              <linearGradient id="socGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#818cf8" stopOpacity="0.4" />
                <stop offset="100%" stopColor="#818cf8" stopOpacity="0.02" />
              </linearGradient>
            </defs>
            <polygon points={areaStr} fill="url(#socGrad)" />
            <polyline
              points={pointsStr}
              stroke="#6366f1"
              strokeWidth="2"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <p className="text-xs font-medium text-gray-700 mb-2">최근 소셜 콘텐츠</p>
        <div className="grid grid-cols-3 gap-2">
          {contentCards.map((c, i) => (
            <div
              key={i}
              className="rounded-lg overflow-hidden border border-gray-100"
            >
              <div
                className={`h-14 bg-gradient-to-br ${c.bg} flex items-end p-1.5`}
              >
                <span className="text-white text-[9px] font-semibold">
                  {c.platform}
                </span>
              </div>
              <div className="p-1.5 bg-white">
                <p className="text-[9px] font-medium text-gray-700">{c.brand}</p>
                <p className="text-[8px] text-emerald-600">
                  &#9825; {c.engagement}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </BrowserFrame>
  );
}

// ─── 체크 아이콘 ─────────────────────────────────────────────────
function CheckIcon({ color }: { color: string }) {
  return (
    <span
      className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${color}`}
    >
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="w-3 h-3 text-white"
      >
        <path
          fillRule="evenodd"
          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
          clipRule="evenodd"
        />
      </svg>
    </span>
  );
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────
export function GuestLanding() {
  const { data: stats, isLoading } = useQuery<PublicStats>({
    queryKey: ["publicStats"],
    queryFn: () => api.getPublicStats(),
    staleTime: 5 * 60_000,
  });

  return (
    <div className="min-h-screen bg-white">
      {/* ── 히어로 ── */}
      <div className="bg-gradient-to-br from-indigo-700 via-violet-700 to-purple-800 text-white">
        <div className="max-w-6xl mx-auto px-6 py-20 text-center">
          <p className="text-sm font-semibold tracking-widest uppercase text-indigo-200 mb-3">
            한국 디지털 광고 인텔리전스 플랫폼
          </p>
          <h1 className="text-4xl sm:text-6xl font-extrabold leading-tight mb-5">
            경쟁사 광고 전략을
            <br className="hidden sm:block" /> 한눈에 파악하세요
          </h1>
          <p className="text-lg text-indigo-200 max-w-2xl mx-auto mb-10 leading-relaxed">
            네이버·구글·유튜브·메타·카카오·틱톡 등 9개 채널의 광고 소재,
            집행 현황, 추정 광고비를 실시간으로 모니터링합니다.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center mb-14">
            <Link
              href="/pricing"
              className="inline-block px-8 py-4 bg-white text-indigo-700 font-bold rounded-xl shadow-lg hover:bg-indigo-50 transition-colors"
            >
              무료 체험 시작 →
            </Link>
            <Link
              href="/login"
              className="inline-block px-8 py-4 border border-white/40 text-white font-medium rounded-xl hover:bg-white/10 transition-colors"
            >
              로그인
            </Link>
          </div>
          {/* 통계 수치 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 max-w-3xl mx-auto">
            {[
              [
                "광고 소재",
                isLoading ? "..." : (stats?.total_ads ?? 0).toLocaleString(),
                "누적 수집",
              ],
              [
                "광고주",
                isLoading
                  ? "..."
                  : (stats?.total_advertisers ?? 0).toLocaleString(),
                "브랜드·기업",
              ],
              [
                "7일 활성",
                isLoading ? "..." : (stats?.active_7d ?? 0).toLocaleString(),
                "최근 7일 기준",
              ],
              ["모니터링 채널", "9개", "네이버·구글 외"],
            ].map(([label, value, sub]) => (
              <div
                key={label}
                className="bg-white/10 backdrop-blur rounded-xl p-4 text-center border border-white/20"
              >
                <p className="text-2xl font-extrabold text-white">{value}</p>
                <p className="text-xs text-indigo-200 mt-0.5">{label}</p>
                <p className="text-[10px] text-indigo-300">{sub}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── 피처 쇼케이스 ── */}
      <div className="max-w-6xl mx-auto px-6 py-20 space-y-28">
        {/* ① 광고 소재 갤러리 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 items-center">
          <div>
            <span className="text-xs font-semibold text-indigo-600 tracking-widest uppercase">
              광고 소재 갤러리
            </span>
            <h2 className="text-3xl font-extrabold text-gray-900 mt-2 mb-4 leading-tight">
              경쟁사의 실제 광고를
              <br />
              채널별로 모아보세요
            </h2>
            <p className="text-gray-500 leading-relaxed mb-6">
              네이버, 유튜브, 메타, 카카오, 구글, 틱톡 등 9개 채널에서 수집한
              실제 광고 소재를 광고주·채널·날짜별로 분류해 한눈에 확인할 수
              있습니다.
            </p>
            <ul className="space-y-3">
              {[
                "광고주별 소재 히스토리 추적",
                "채널별·형식별 필터링",
                "실제 광고 이미지·영상 원본 보기",
                "소재 변경 이력 타임라인",
              ].map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-3 text-sm text-gray-700"
                >
                  <CheckIcon color="bg-indigo-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <AdGalleryMockup />
          </div>
        </div>

        {/* ② 캠페인 리포트 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 items-center">
          <div className="order-2 lg:order-1">
            <CampaignMockup />
          </div>
          <div className="order-1 lg:order-2">
            <span className="text-xs font-semibold text-violet-600 tracking-widest uppercase">
              캠페인 리포트
            </span>
            <h2 className="text-3xl font-extrabold text-gray-900 mt-2 mb-4 leading-tight">
              추정 광고비와 캠페인
              <br />
              집행 현황을 분석하세요
            </h2>
            <p className="text-gray-500 leading-relaxed mb-6">
              채널별 광고 노출 빈도를 바탕으로 경쟁사의 캠페인별 추정 광고비를
              산출합니다. 어떤 캠페인에 얼마나 투자하는지 파악하세요.
            </p>
            <ul className="space-y-3">
              {[
                "캠페인별 추정 광고비 분석",
                "채널별 집행 비중 시각화",
                "기간별 광고비 추이 추적",
                "경쟁사 대비 상대적 투자 분석",
              ].map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-3 text-sm text-gray-700"
                >
                  <CheckIcon color="bg-violet-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* ③ 키워드 분석 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 items-center">
          <div>
            <span className="text-xs font-semibold text-emerald-600 tracking-widest uppercase">
              키워드 분석
            </span>
            <h2 className="text-3xl font-extrabold text-gray-900 mt-2 mb-4 leading-tight">
              경쟁사가 집행 중인
              <br />
              키워드를 역추적하세요
            </h2>
            <p className="text-gray-500 leading-relaxed mb-6">
              검색광고 키워드를 역추적해 경쟁사가 어떤 키워드에 얼마의
              입찰가를 쓰는지 파악합니다. 키워드 경쟁 강도와 광고 트렌드를
              분석하세요.
            </p>
            <ul className="space-y-3">
              {[
                "경쟁사 타겟 키워드 역추적",
                "키워드별 입찰가 추정",
                "검색광고 랜드스케이프 분석",
                "키워드 광고비 추이 트래킹",
              ].map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-3 text-sm text-gray-700"
                >
                  <CheckIcon color="bg-emerald-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <KeywordMockup />
          </div>
        </div>

        {/* ④ 시장 분석 SOV */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 items-center">
          <div className="order-2 lg:order-1">
            <SOVMockup />
          </div>
          <div className="order-1 lg:order-2">
            <span className="text-xs font-semibold text-amber-600 tracking-widest uppercase">
              시장 분석
            </span>
            <h2 className="text-3xl font-extrabold text-gray-900 mt-2 mb-4 leading-tight">
              산업별 광고 점유율로
              <br />
              시장 위치를 확인하세요
            </h2>
            <p className="text-gray-500 leading-relaxed mb-6">
              업종별 SOV(Share of Voice) 분석으로 시장 내 광고 경쟁 구도를
              파악합니다. 우리 브랜드의 광고 점유율을 경쟁사와 비교하세요.
            </p>
            <ul className="space-y-3">
              {[
                "산업별 SOV 점유율 분석",
                "경쟁사 대비 포지셔닝 파악",
                "채널별 시장 점유율 비교",
                "시계열 광고 점유율 변화 추적",
              ].map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-3 text-sm text-gray-700"
                >
                  <CheckIcon color="bg-amber-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* ⑤ 소셜 인사이트 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-14 items-center">
          <div>
            <span className="text-xs font-semibold text-pink-600 tracking-widest uppercase">
              소셜 인사이트
            </span>
            <h2 className="text-3xl font-extrabold text-gray-900 mt-2 mb-4 leading-tight">
              경쟁사의 소셜 콘텐츠와
              <br />
              팔로워 성장을 추적하세요
            </h2>
            <p className="text-gray-500 leading-relaxed mb-6">
              인스타그램, 유튜브, 틱톡 등 소셜 채널에서 경쟁사가 발행하는
              콘텐츠와 팔로워 성장, 참여율을 실시간으로 모니터링합니다.
            </p>
            <ul className="space-y-3">
              {[
                "팔로워 성장 추이 분석",
                "콘텐츠 참여율·조회수 추적",
                "소셜 채널별 비교 분석",
                "브랜드 버즈 및 언급 모니터링",
              ].map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-3 text-sm text-gray-700"
                >
                  <CheckIcon color="bg-pink-500" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div>
            <SocialMockup />
          </div>
        </div>

        {/* ── 하단 CTA ── */}
        <div className="bg-gradient-to-br from-indigo-600 to-violet-700 rounded-3xl p-12 text-center text-white shadow-2xl">
          <h2 className="text-3xl font-extrabold mb-3">지금 바로 시작하세요</h2>
          <p className="text-indigo-200 text-base mb-8 max-w-md mx-auto">
            7일 무료 체험으로 AdScope의 모든 기능을 제한 없이 사용해보세요.
            신용카드 없이 바로 시작 가능합니다.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/pricing"
              className="px-10 py-4 bg-white text-indigo-700 font-bold rounded-xl shadow hover:bg-indigo-50 transition-colors"
            >
              무료 체험 신청 →
            </Link>
            <Link
              href="/login"
              className="px-10 py-4 border border-white/40 text-white font-medium rounded-xl hover:bg-white/10 transition-colors"
            >
              이미 계정이 있으신가요?
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
