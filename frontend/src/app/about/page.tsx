"use client";

import Link from "next/link";

/* ── Stats ── */
const STATS = [
  { value: "9", label: "수집 채널", sub: "국내 주요 디지털 매체" },
  { value: "39,000+", label: "광고 소재", sub: "일별 자동 수집" },
  { value: "6,000+", label: "모니터링 광고주", sub: "기업/브랜드/제품" },
  { value: "11,000+", label: "캠페인", sub: "캠페인 단위 추적" },
];

/* ── Channels ── */
const CHANNELS = [
  { name: "네이버 검색", desc: "SA / 파워링크", color: "from-green-400 to-emerald-500" },
  { name: "네이버 DA", desc: "디스플레이 광고", color: "from-emerald-400 to-teal-500" },
  { name: "네이버 쇼핑", desc: "쇼핑 파워링크", color: "from-lime-400 to-green-500" },
  { name: "카카오 DA", desc: "비즈보드/DA", color: "from-yellow-400 to-amber-500" },
  { name: "구글 GDN", desc: "디스플레이 네트워크", color: "from-sky-400 to-blue-500" },
  { name: "구글 검색광고", desc: "Google Search Ads", color: "from-cyan-400 to-sky-500" },
  { name: "유튜브", desc: "투명성 센터 기반", color: "from-red-400 to-rose-500" },
  { name: "메타", desc: "Facebook / Instagram", color: "from-blue-400 to-indigo-500" },
  { name: "틱톡", desc: "Creative Center", color: "from-purple-400 to-fuchsia-500" },
];

/* ── Core Capabilities ── */
const CAPABILITIES = [
  {
    title: "광고 소재 모니터링",
    desc: "9개 디지털 광고 채널에서 광고 크리에이티브를 매일 자동 수집합니다. 페르소나 기반 접촉 측정과 카탈로그 수집을 병행하여 실제 소비자가 접하는 광고를 포착합니다.",
    icon: "gallery",
    color: "bg-indigo-50 text-indigo-600",
  },
  {
    title: "경쟁사 분석",
    desc: "산업별 현황, 제품/서비스 카테고리, 경쟁사 비교, 광고주 트렌드를 통해 시장 전체를 조망합니다. SOV(점유율) 분석과 페르소나 접촉률로 경쟁 포지션을 파악합니다.",
    icon: "landscape",
    color: "bg-emerald-50 text-emerald-600",
  },
  {
    title: "키워드 분석",
    desc: "키워드 역추적으로 경쟁사의 검색 광고 전략을 파악하고, 광고 랜드스케이프로 키워드별 광고 분포를 시각화합니다. 광고비 추이로 시장 투자 변화를 추적합니다.",
    icon: "keyword",
    color: "bg-amber-50 text-amber-600",
  },
  {
    title: "소셜 인사이트",
    desc: "브랜드 공식 YouTube/Instagram 채널의 콘텐츠, 구독자, 인게이지먼트를 추적합니다. 소셜 채널 분석, 브랜드 버즈, 캠페인 효과를 종합적으로 분석합니다.",
    icon: "social",
    color: "bg-rose-50 text-rose-600",
  },
  {
    title: "쇼핑 분석",
    desc: "네이버 쇼핑 파워링크 광고를 추적하고, 카테고리별 광고 분포와 프로모션 트렌드를 분석합니다. 커머스 광고 전략 수립에 필요한 쇼핑 인사이트를 제공합니다.",
    icon: "shopping",
    color: "bg-violet-50 text-violet-600",
  },
  {
    title: "매체별 광고비 추정",
    desc: "CPC 기반 추정, 카탈로그 역추산, 메타시그널 보정, 실집행 벤치마크의 다층 방식으로 채널별 광고비를 역추정합니다. 광고비 추이와 매체 믹스를 분석합니다.",
    icon: "spend",
    color: "bg-sky-50 text-sky-600",
  },
];

/* ── Menu Structure ── */
const MENU_GROUPS = [
  {
    group: "메인",
    items: ["보고서", "나의광고주", "대시보드", "광고주", "캠페인", "광고소재", "소셜소재", "매체별광고비"],
  },
  {
    group: "키워드분석",
    items: ["키워드역추적", "광고랜드스케이프", "광고비추이"],
  },
  {
    group: "시장분석",
    items: ["산업별현황", "제품서비스현황", "경쟁사비교", "광고주트렌드"],
  },
  {
    group: "쇼핑분석",
    items: ["쇼핑인사이트"],
  },
  {
    group: "소셜인사이트",
    items: ["소셜채널분석", "브랜드버즈", "캠페인효과"],
  },
  {
    group: "분석도구",
    items: ["SOV분석", "페르소나접촉률", "타겟오디언스"],
  },
];

function CapabilityIcon({ name }: { name: string }) {
  const props = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.5,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className: "w-7 h-7",
  };
  switch (name) {
    case "gallery":
      return (
        <svg {...props}>
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
      );
    case "social":
      return (
        <svg {...props}>
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 01-3.46 0" />
        </svg>
      );
    case "landscape":
      return (
        <svg {...props}>
          <path d="M2 20L8.5 8 13 16l4-6 5 10" />
          <path d="M2 20h20" />
        </svg>
      );
    case "keyword":
      return (
        <svg {...props}>
          <circle cx="11" cy="11" r="8" />
          <path d="M21 21l-4.35-4.35" />
        </svg>
      );
    case "shopping":
      return (
        <svg {...props}>
          <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
          <line x1="3" y1="6" x2="21" y2="6" />
          <path d="M16 10a4 4 0 0 1-8 0" />
        </svg>
      );
    case "spend":
      return (
        <svg {...props}>
          <rect x="2" y="6" width="20" height="12" rx="2" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    default:
      return null;
  }
}

export default function AboutPage() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      {/* ── Hero ── */}
      <section className="text-center mb-20">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 bg-adscope-50 rounded-full text-sm font-medium text-adscope-600 mb-6">
          <span className="w-2 h-2 bg-adscope-500 rounded-full animate-pulse-dot" />
          9개 채널 실시간 수집 중
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-5 leading-tight">
          한국 디지털 광고<br className="hidden sm:block" /> 통합 인텔리전스 플랫폼
        </h1>
        <p className="text-lg text-gray-500 max-w-2xl mx-auto leading-relaxed mb-3">
          AdScope는 국내 주요 9개 디지털 광고 매체의 소재, 집행 현황, 광고비를 통합 모니터링하여
          마케팅 의사결정에 필요한 경쟁 인텔리전스를 제공합니다.
        </p>
        <p className="text-base text-gray-400 max-w-xl mx-auto">
          광고 분석 + 소셜 분석 + 쇼핑 분석, 3축 통합 분석으로
          디지털 마케팅 시장의 전체 그림을 파악하세요.
        </p>
        <div className="mt-10 flex flex-wrap justify-center gap-4">
          <Link
            href="/pricing"
            className="px-7 py-3.5 bg-adscope-600 text-white font-semibold rounded-xl hover:bg-adscope-700 transition-colors shadow-lg shadow-adscope-200/40"
          >
            요금제 보기
          </Link>
          <a
            href="/AdScope_서비스소개.pdf"
            download
            className="inline-flex items-center gap-2 px-7 py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 flex-shrink-0">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M7 10l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            서비스 소개서 다운로드
          </a>
          <Link
            href="/"
            className="px-7 py-3.5 border border-gray-300 text-gray-700 font-semibold rounded-xl hover:border-adscope-400 hover:text-adscope-600 transition-colors"
          >
            대시보드
          </Link>
        </div>
      </section>

      {/* ── Key Stats ── */}
      <section className="mb-20">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {STATS.map((s) => (
            <div
              key={s.label}
              className="bg-gradient-to-br from-adscope-50 to-blue-50 rounded-2xl p-6 text-center border border-adscope-100/50"
            >
              <p className="text-3xl font-bold text-adscope-600">{s.value}</p>
              <p className="text-sm font-medium mt-1 text-gray-700">{s.label}</p>
              <p className="text-xs mt-0.5 text-gray-400">{s.sub}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Data Coverage (9 Channels) ── */}
      <section className="mb-20">
        <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
          데이터 커버리지
        </h2>
        <p className="text-gray-500 text-center mb-10">
          국내 주요 디지털 광고 매체 9개 채널을 매일 자동 수집합니다.
        </p>
        <div className="grid grid-cols-3 md:grid-cols-3 gap-3">
          {CHANNELS.map((ch) => (
            <div
              key={ch.name}
              className="relative overflow-hidden bg-white border border-gray-200 rounded-xl p-5 text-center hover:border-adscope-300 hover:shadow-md transition-all group"
            >
              <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${ch.color} opacity-60 group-hover:opacity-100 transition-opacity`} />
              <p className="text-base font-bold text-gray-900 mt-1">{ch.name}</p>
              <p className="text-xs mt-1 text-gray-400">{ch.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-4 text-center">
          * 페르소나 기반 접촉 측정 + 카탈로그 수집 병행으로 실제 소비자가 접하는 광고를 포착합니다.
        </p>
      </section>

      {/* ── Core Capabilities ── */}
      <section className="mb-20">
        <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
          주요 기능
        </h2>
        <p className="text-gray-500 text-center mb-10">
          광고/소셜/쇼핑 3축 통합 분석으로 디지털 마케팅 인텔리전스를 제공합니다.
        </p>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {CAPABILITIES.map((f) => (
            <div
              key={f.title}
              className="bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md hover:border-adscope-200 transition-all"
            >
              <div className={`w-12 h-12 ${f.color} rounded-lg flex items-center justify-center mb-4`}>
                <CapabilityIcon name={f.icon} />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                {f.title}
              </h3>
              <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── 3-Axis Analysis ── */}
      <section className="mb-20">
        <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
          3축 통합 분석
        </h2>
        <p className="text-gray-500 text-center mb-10">
          광고, 소셜, 쇼핑 데이터를 결합하여 마케팅 시장의 전체 그림을 제공합니다.
        </p>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="bg-gradient-to-br from-indigo-50 to-blue-50 rounded-2xl p-6 border border-indigo-100/50">
            <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center text-indigo-600 mb-4">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" strokeLinecap="round" strokeLinejoin="round" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="M21 15l-5-5L5 21" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-gray-900 mb-2">광고 분석</h3>
            <ul className="space-y-1.5 text-sm text-gray-600">
              <li>9개 채널 광고 소재 수집/분류</li>
              <li>광고주/캠페인/소재 3단계 분석</li>
              <li>키워드 역추적 / 광고 랜드스케이프</li>
              <li>매체별 광고비 추정 / SOV 분석</li>
              <li>경쟁사 비교 / 산업별 현황</li>
            </ul>
          </div>
          <div className="bg-gradient-to-br from-rose-50 to-pink-50 rounded-2xl p-6 border border-rose-100/50">
            <div className="w-10 h-10 bg-rose-100 rounded-lg flex items-center justify-center text-rose-600 mb-4">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6">
                <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M13.73 21a2 2 0 01-3.46 0" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-gray-900 mb-2">소셜 분석</h3>
            <ul className="space-y-1.5 text-sm text-gray-600">
              <li>브랜드 YouTube/Instagram 모니터링</li>
              <li>소셜 소재 갤러리 / 콘텐츠 분석</li>
              <li>소셜 채널 분석 / 구독자 추적</li>
              <li>브랜드 버즈 / 인게이지먼트 분석</li>
              <li>캠페인 효과 측정</li>
            </ul>
          </div>
          <div className="bg-gradient-to-br from-violet-50 to-purple-50 rounded-2xl p-6 border border-violet-100/50">
            <div className="w-10 h-10 bg-violet-100 rounded-lg flex items-center justify-center text-violet-600 mb-4">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6">
                <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" strokeLinecap="round" strokeLinejoin="round" />
                <line x1="3" y1="6" x2="21" y2="6" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M16 10a4 4 0 0 1-8 0" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-gray-900 mb-2">쇼핑 분석</h3>
            <ul className="space-y-1.5 text-sm text-gray-600">
              <li>네이버 쇼핑 파워링크 추적</li>
              <li>카테고리별 광고 분포 분석</li>
              <li>쇼핑 키워드 경쟁 분석</li>
              <li>프로모션 트렌드 파악</li>
              <li>커머스 광고 전략 인사이트</li>
            </ul>
          </div>
        </div>
      </section>

      {/* ── Full Menu Structure ── */}
      <section className="mb-20">
        <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
          서비스 메뉴 구성
        </h2>
        <p className="text-gray-500 text-center mb-10">
          목적에 따라 체계적으로 구성된 분석 메뉴를 제공합니다.
        </p>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {MENU_GROUPS.map((g) => (
            <div key={g.group} className="bg-white border border-gray-200 rounded-xl p-5">
              <h3 className="text-sm font-bold text-adscope-600 mb-3 uppercase tracking-wide">
                {g.group}
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {g.items.map((item) => (
                  <span
                    key={item}
                    className="px-2.5 py-1 bg-gray-50 text-gray-600 text-xs rounded-lg border border-gray-100"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Pricing Summary ── */}
      <section className="mb-20">
        <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
          요금제
        </h2>
        <p className="text-gray-500 text-center mb-10">
          기업 규모와 필요에 맞는 플랜을 선택하세요.
        </p>
        <div className="grid md:grid-cols-2 gap-6 max-w-3xl mx-auto">
          <div className="bg-white border border-gray-200 rounded-xl p-6">
            <h3 className="text-lg font-bold text-gray-900">Lite</h3>
            <p className="text-sm text-gray-500 mb-3">광고 정보 중심 분석</p>
            <p className="text-3xl font-bold text-gray-900">
              49,000<span className="text-sm font-normal text-gray-400">원/월</span>
            </p>
            <p className="text-xs text-gray-400 mt-1">연간 490,000원 (17% 할인)</p>
            <ul className="mt-4 space-y-1.5 text-sm text-gray-600">
              <li>9개 채널 광고 소재 열람</li>
              <li>광고주 리포트 / 광고비 분석</li>
              <li>시장 분석 / 경쟁사 비교</li>
              <li>키워드 역추적 / 랜드스케이프</li>
              <li>쇼핑 인사이트</li>
              <li>SOV 분석 / 페르소나 접촉률</li>
              <li>보고서 생성 (광고 정보)</li>
            </ul>
          </div>
          <div className="bg-adscope-600 text-white rounded-xl p-6">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold">Full</h3>
              <span className="text-[10px] bg-white/20 px-2 py-0.5 rounded-full font-semibold">
                추천
              </span>
            </div>
            <p className="text-sm text-adscope-100 mb-3">광고 + 소셜 + 쇼핑 통합 분석</p>
            <p className="text-3xl font-bold">
              99,000<span className="text-sm font-normal text-adscope-200">원/월</span>
            </p>
            <p className="text-xs text-adscope-200 mt-1">연간 990,000원 (17% 할인)</p>
            <ul className="mt-4 space-y-1.5 text-sm text-adscope-50">
              <li>Lite 전체 기능 포함</li>
              <li>소셜 소재 갤러리 (YouTube/Instagram)</li>
              <li>소셜 채널 분석 (구독자/인게이지먼트)</li>
              <li>브랜드 버즈 / 캠페인 효과 분석</li>
              <li>소셜 콘텐츠 성과 분석</li>
              <li>보고서 소셜 섹션 포함</li>
            </ul>
          </div>
        </div>
        <div className="text-center mt-6">
          <Link
            href="/pricing"
            className="text-sm text-adscope-600 hover:text-adscope-700 font-medium"
          >
            상세 요금 및 회원가입 &rarr;
          </Link>
        </div>
      </section>

      {/* ── Terms & Privacy ── */}
      <section className="mb-10">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="font-semibold text-gray-900 mb-4">법적 고지</h3>
          <div className="flex flex-col sm:flex-row gap-4">
            <Link
              href="/terms"
              className="flex-1 flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:border-adscope-300 hover:bg-gray-50 transition-colors group"
            >
              <div>
                <p className="font-medium text-gray-900 group-hover:text-adscope-600">이용약관</p>
                <p className="text-xs text-gray-400 mt-0.5">시행일: 2025년 1월 1일</p>
              </div>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5 text-gray-300 group-hover:text-adscope-400">
                <path d="M9 18l6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
            <Link
              href="/privacy"
              className="flex-1 flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:border-adscope-300 hover:bg-gray-50 transition-colors group"
            >
              <div>
                <p className="font-medium text-gray-900 group-hover:text-adscope-600">개인정보처리방침</p>
                <p className="text-xs text-gray-400 mt-0.5">시행일: 2025년 1월 1일</p>
              </div>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5 text-gray-300 group-hover:text-adscope-400">
                <path d="M9 18l6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <div className="text-center text-sm text-gray-400 py-6 border-t border-gray-100">
        <p>
          AdScope | 광고 인텔리전스 플랫폼 by{" "}
          <a
            href="https://doubleestudio.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-adscope-500 hover:text-adscope-600 transition-colors"
          >
            DoubleE Studio
          </a>
        </p>
        <p className="mt-1">문의: support@adscope.kr</p>
      </div>
    </div>
  );
}
