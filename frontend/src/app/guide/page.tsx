"use client";

import Link from "next/link";

/* ── Feature Sections ── */
const GUIDE_SECTIONS = [
  {
    id: "overview",
    title: "서비스 개요",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4" strokeLinecap="round" />
        <path d="M12 8h.01" strokeLinecap="round" />
      </svg>
    ),
    content: (
      <div className="space-y-3">
        <p>
          AdScope는 국내 주요 9개 디지털 광고 채널의 소재, 집행 현황, 광고비를
          통합 모니터링하여 마케팅 의사결정에 필요한 경쟁 인텔리전스를 제공하는 B2B SaaS 플랫폼입니다.
        </p>
        <p>
          현재 공개 메뉴는 광고주, 캠페인, 광고 소재, 키워드, 시장 분석,
          소셜 공개 메뉴를 중심으로 제공됩니다.
        </p>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100">
            <p className="text-xl font-bold text-adscope-600">9</p>
            <p className="text-xs text-gray-500">수집 채널</p>
          </div>
          <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100">
            <p className="text-xl font-bold text-adscope-600">39,000+</p>
            <p className="text-xs text-gray-500">광고 소재</p>
          </div>
          <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100">
            <p className="text-xl font-bold text-adscope-600">6,000+</p>
            <p className="text-xs text-gray-500">광고주</p>
          </div>
          <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100">
            <p className="text-xl font-bold text-adscope-600">11,000+</p>
            <p className="text-xs text-gray-500">캠페인</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "channels",
    title: "지원 채널 (9개)",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <path d="M21.21 15.89A10 10 0 1 1 8 2.83" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M22 12A10 10 0 0 0 12 2v10z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    content: (
      <div className="space-y-3">
        <p>공개 광고 카탈로그와 채널별 검색/디스플레이 수집 데이터를 함께 정리합니다.</p>
        <div className="grid sm:grid-cols-3 gap-2">
          {[
            { name: "네이버 검색", tag: "SA/파워링크", color: "bg-green-100 text-green-700" },
            { name: "네이버 DA", tag: "디스플레이", color: "bg-emerald-100 text-emerald-700" },
            { name: "네이버 쇼핑", tag: "쇼핑 파워링크", color: "bg-lime-100 text-lime-700" },
            { name: "카카오 DA", tag: "비즈보드/DA", color: "bg-yellow-100 text-yellow-700" },
            { name: "구글 GDN", tag: "디스플레이 네트워크", color: "bg-sky-100 text-sky-700" },
            { name: "구글 검색광고", tag: "Search Ads", color: "bg-cyan-100 text-cyan-700" },
            { name: "유튜브", tag: "투명성 센터", color: "bg-red-100 text-red-700" },
            { name: "메타(FB/IG)", tag: "Ad Library", color: "bg-blue-100 text-blue-700" },
            { name: "틱톡", tag: "Creative Center", color: "bg-purple-100 text-purple-700" },
          ].map((ch) => (
            <div key={ch.name} className="flex items-center gap-2 p-2 bg-gray-50 rounded-lg">
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${ch.color}`}>{ch.tag}</span>
              <span className="text-sm font-medium text-gray-800">{ch.name}</span>
            </div>
          ))}
        </div>
      </div>
    ),
  },
  {
    id: "main-menu",
    title: "메인 메뉴",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="M21 15l-5-5L5 21" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    content: (
      <div className="space-y-4">
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="p-3 bg-gray-50 rounded-lg">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">보고서</h4>
            <p className="text-xs text-gray-500">광고주별 공개 데이터를 기준으로 보고서와 자료를 확인합니다.</p>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">나의광고주</h4>
            <p className="text-xs text-gray-500">관심 광고주를 등록하고 관리합니다. 등록된 광고주의 최신 광고 활동을 우선적으로 모니터링합니다.</p>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">광고주</h4>
            <p className="text-xs text-gray-500">기업-브랜드-제품 계층 구조로 광고주를 관리합니다. 광고주별 미디어 브레이크다운, 채널 분포, 활동 추이를 분석합니다.</p>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">캠페인</h4>
            <p className="text-xs text-gray-500">캠페인 단위로 광고 소재를 매핑하고, 캠페인별 집행 현황과 성과를 추적합니다.</p>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">광고소재 / 소셜소재</h4>
            <p className="text-xs text-gray-500">수집된 광고 크리에이티브와 소셜 콘텐츠를 갤러리 형태로 열람합니다. 채널/광고주/기간별 필터를 지원합니다.</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "keyword",
    title: "키워드분석",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <circle cx="11" cy="11" r="8" />
        <path d="M21 21l-4.35-4.35" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    content: (
      <div className="space-y-4">
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="p-3 bg-amber-50 rounded-lg border border-amber-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">키워드역추적</h4>
            <p className="text-xs text-gray-500">특정 광고주가 입찰하고 있는 검색 키워드를 역추적합니다. 경쟁사의 검색 광고 전략을 파악할 수 있습니다.</p>
          </div>
          <div className="p-3 bg-amber-50 rounded-lg border border-amber-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">광고랜드스케이프</h4>
            <p className="text-xs text-gray-500">키워드별 광고 분포를 시각화합니다. 어떤 광고주가 어떤 키워드에서 경쟁하고 있는지 한눈에 파악합니다.</p>
          </div>
          <div className="p-3 bg-amber-50 rounded-lg border border-amber-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">광고비추이</h4>
            <p className="text-xs text-gray-500">광고주별, 매체별 광고비 추이를 시계열로 분석합니다. 시장 투자 변화와 경쟁 역학을 추적합니다.</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "market",
    title: "시장분석",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <path d="M2 20L8.5 8 13 16l4-6 5 10" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M2 20h20" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    content: (
      <div className="space-y-4">
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">산업별현황</h4>
            <p className="text-xs text-gray-500">산업/업종별 광고 시장 규모, 주요 플레이어, 매체별 분포를 분석합니다.</p>
          </div>
          <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">제품서비스현황</h4>
            <p className="text-xs text-gray-500">제품/서비스 카테고리별 광고 현황과 트렌드를 파악합니다.</p>
          </div>
          <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">경쟁사비교</h4>
            <p className="text-xs text-gray-500">특정 광고주와 경쟁사의 광고 활동, 매체 믹스, 광고비를 비교 분석합니다.</p>
          </div>
          <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">광고주트렌드</h4>
            <p className="text-xs text-gray-500">광고주의 시간별 활동 변화, 신규 진입/이탈 광고주, 시장 점유율 변동을 추적합니다.</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "social",
    title: "소셜인사이트",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M13.73 21a2 2 0 01-3.46 0" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    content: (
      <div className="space-y-4">
        <p className="text-sm text-gray-500">현재 공개 메뉴 기준으로 제공되는 소셜 분석 기능입니다.</p>
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="p-3 bg-rose-50 rounded-lg border border-rose-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">소셜채널분석</h4>
            <p className="text-xs text-gray-500">브랜드 공식 YouTube/Instagram 채널의 구독자, 팔로워, 인게이지먼트 변화를 추적합니다.</p>
          </div>
          <div className="p-3 bg-rose-50 rounded-lg border border-rose-100">
            <h4 className="font-semibold text-gray-900 text-sm mb-1">브랜드버즈</h4>
            <p className="text-xs text-gray-500">브랜드 관련 소셜 미디어 언급량, 감성 분석, 화제성 변화를 모니터링합니다.</p>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: "data-collection",
    title: "데이터 수집 방식",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <rect x="2" y="3" width="20" height="14" rx="2" ry="2" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="8" y1="21" x2="16" y2="21" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="12" y1="17" x2="12" y2="21" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    content: (
      <div className="space-y-4">
        <p>AdScope는 두 가지 방식을 병행하여 광고 데이터를 수집합니다.</p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
            <h4 className="font-semibold text-gray-900 mb-2">카탈로그 수집</h4>
            <p className="text-sm text-gray-500 mb-2">
              광고 플랫폼이 제공하는 공개 카탈로그/API를 통해 대량의 광고 소재를 수집합니다.
            </p>
            <ul className="text-xs text-gray-400 space-y-1">
              <li>YouTube Ads - 투명성 센터</li>
              <li>Meta - Ad Library</li>
              <li>TikTok - Creative Center</li>
              <li>네이버 쇼핑 - 쇼핑탭 파워링크</li>
            </ul>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-100">
            <h4 className="font-semibold text-gray-900 mb-2">채널별 수집</h4>
            <p className="text-sm text-gray-500 mb-2">
              검색 키워드, 디스플레이 지면, 공개 광고 라이브러리에서 확인되는 광고 소재를 수집합니다.
            </p>
            <ul className="text-xs text-gray-400 space-y-1">
              <li>네이버 검색광고 - 키워드별 수집</li>
              <li>네이버 DA - 메인/서비스 지면</li>
              <li>카카오 DA - 비즈보드/DA</li>
              <li>구글 GDN - 언론사 기사면</li>
            </ul>
          </div>
        </div>
        <p className="text-xs text-gray-400">
          * 매일 자동 스케줄러가 수집을 수행하며, AI 모델이 제품 카테고리 분류, 광고주 매칭, 중복 제거를 자동 처리합니다.
        </p>
      </div>
    ),
  },
  {
    id: "export",
    title: "데이터 내보내기 / 보고서",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-6 h-6">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M14 2v6h6" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="16" y1="13" x2="8" y2="13" strokeLinecap="round" strokeLinejoin="round" />
        <line x1="16" y1="17" x2="8" y2="17" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
    content: (
      <div className="space-y-3">
        <ul className="space-y-2 text-sm text-gray-600">
          <li className="flex items-start gap-2">
            <span className="text-adscope-500 font-bold mt-0.5">PDF</span>
            <span>광고주와 광고 소재 중심의 공개 데이터를 보고서로 확인합니다.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-adscope-500 font-bold mt-0.5">CSV</span>
            <span>광고 소재 목록, 광고비 분석 결과, 키워드 데이터 등을 CSV로 다운로드할 수 있습니다.</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-adscope-500 font-bold mt-0.5">Excel</span>
            <span>시장 분석, 경쟁사 비교 등 공개 메뉴의 테이블 데이터를 확인합니다.</span>
          </li>
        </ul>
      </div>
    ),
  },
];

const CURRENT_GUIDE_SECTION_IDS = new Set([
  "overview",
  "channels",
  "main-menu",
  "keyword",
  "market",
  "social",
  "data-collection",
  "export",
]);

const CURRENT_GUIDE_SECTIONS = GUIDE_SECTIONS.filter((section) =>
  CURRENT_GUIDE_SECTION_IDS.has(section.id)
);

export default function GuidePage() {
  return (
    <div className="p-6 lg:p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-gray-900">이용 매뉴얼</h1>
        <p className="text-base text-gray-500 mt-2">
          AdScope의 주요 기능과 활용 방법을 안내합니다.
        </p>
        <div className="flex flex-wrap gap-3 mt-4">
          <a
            href="/AdScope_서비스소개.pdf"
            download
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98] text-sm"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M7 10l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            서비스 소개서 다운로드
          </a>
          <Link
            href="/faq"
            className="inline-flex items-center gap-2 px-5 py-2.5 border border-gray-300 text-gray-700 font-semibold rounded-xl hover:border-adscope-400 hover:text-adscope-600 transition-colors text-sm"
          >
            FAQ 바로가기
          </Link>
        </div>
      </div>

      {/* Table of Contents */}
      <nav className="mb-10 bg-gray-50 rounded-2xl p-6">
        <h2 className="text-sm font-bold text-gray-900 mb-3 uppercase tracking-wide">목차</h2>
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-2">
          {CURRENT_GUIDE_SECTIONS.map((s, i) => (
            <a
              key={s.id}
              href={`#${s.id}`}
              className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-white hover:shadow-sm transition-all text-sm text-gray-600 hover:text-adscope-600"
            >
              <span className="text-xs font-bold text-adscope-400 w-5">{String(i + 1).padStart(2, "0")}</span>
              {s.title}
            </a>
          ))}
        </div>
      </nav>

      {/* Sections */}
      <div className="space-y-8">
        {CURRENT_GUIDE_SECTIONS.map((section, i) => (
          <section
            key={section.id}
            id={section.id}
            className="bg-white border border-gray-200 rounded-2xl p-6 md:p-8 scroll-mt-6"
          >
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-lg bg-adscope-50 text-adscope-600 flex items-center justify-center flex-shrink-0">
                {section.icon}
              </div>
              <div>
                <span className="text-xs font-bold text-adscope-400">{String(i + 1).padStart(2, "0")}</span>
                <h2 className="text-lg font-bold text-gray-900">{section.title}</h2>
              </div>
            </div>
            <div className="text-sm text-gray-700 leading-relaxed">
              {section.content}
            </div>
          </section>
        ))}
      </div>

      {/* Plans Quick Ref */}
      <section className="mt-10 mb-8">
        <div className="bg-gradient-to-br from-adscope-50 to-blue-50 rounded-2xl p-6 md:p-8 border border-adscope-100/50">
          <h2 className="text-lg font-bold text-gray-900 mb-4">요금제 안내</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="bg-white rounded-xl p-5 shadow-sm">
              <h3 className="font-bold text-gray-900">Lite</h3>
              <p className="text-2xl font-bold text-gray-900 mt-1">49,000<span className="text-sm font-normal text-gray-400">/월</span></p>
              <p className="text-xs text-gray-400">연간 490,000원 (17% 할인)</p>
              <ul className="mt-3 space-y-1 text-xs text-gray-500">
                <li>광고주 / 캠페인 / 광고 소재</li>
                <li>키워드 / 시장 / 소셜 공개 메뉴</li>
                <li>보고서와 즐겨찾기 등 기본 기능</li>
              </ul>
            </div>
            <div className="bg-adscope-600 text-white rounded-xl p-5 shadow-sm">
              <div className="flex items-center gap-2">
                <h3 className="font-bold">Full</h3>
                <span className="text-[10px] bg-white/20 px-2 py-0.5 rounded-full font-semibold">추천</span>
              </div>
              <p className="text-2xl font-bold mt-1">99,000<span className="text-sm font-normal text-adscope-200">/월</span></p>
              <p className="text-xs text-adscope-200">연간 990,000원 (17% 할인)</p>
              <ul className="mt-3 space-y-1 text-xs text-adscope-100">
                <li>현재는 공개 메뉴 기준으로 제공</li>
                <li>추가 기능은 업데이트 후 순차 오픈</li>
                <li>오픈 전 기능은 안내에서 제외</li>
              </ul>
            </div>
          </div>
          <div className="mt-4 text-center">
            <Link href="/pricing" className="text-sm text-adscope-600 hover:text-adscope-700 font-medium">
              상세 요금 안내 보기 &rarr;
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
