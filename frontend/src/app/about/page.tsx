"use client";

import Link from "next/link";

const FEATURES = [
  {
    title: "광고 소재 갤러리",
    desc: "네이버, 카카오, 구글, 유튜브, 메타(페이스북/인스타그램), 틱톡, 네이버 쇼핑 등 9개 채널에서 광고 소재를 자동 수집하고 AI 기반 제품 카테고리 분류, 크리에이티브 해시 중복 제거까지 수행합니다.",
    icon: "gallery",
  },
  {
    title: "소셜 소재 분석",
    desc: "유튜브, 인스타그램 등 브랜드 공식 채널의 콘텐츠, 조회수, 팔로워, 구독자 변화를 추적하고 인게이지먼트 기반 소셜 트렌드를 분석합니다.",
    icon: "social",
  },
  {
    title: "광고주 리포트",
    desc: "캠페인 상세(저니/리프트), 광고 모델 정보, 메타시그널 종합 점수, 미디어 브레이크다운을 포함한 광고주별 종합 인텔리전스 리포트를 제공합니다.",
    icon: "advertiser",
  },
  {
    title: "광고비 분석",
    desc: "CPC 기반 추정, 카탈로그 역추산, 메타시그널 보정, 실집행 벤치마크 캘리브레이션 등 다층 방식으로 채널별 광고비를 역추정합니다. 실집행 대비 99~101% 일치율을 달성합니다.",
    icon: "spend",
  },
  {
    title: "시장 분석",
    desc: "산업별 현황, 제품/서비스별, 경쟁사 비교, SOV(점유율), 접촉률, 페르소나별 분석 등 시장 전체를 조망하는 심층 분석 도구를 제공합니다.",
    icon: "landscape",
  },
  {
    title: "캠페인 & 임팩트 분석",
    desc: "캠페인별 고객 저니(노출-관심-고려-전환) 추적, 전후 리프트 효과 측정, 신제품 출시 임팩트(LII) 스코어 산출, 마케팅 스케줄 추적을 수행합니다.",
    icon: "campaign",
  },
];

const CHANNELS = [
  { name: "네이버 검색", desc: "SA / 파워링크" },
  { name: "네이버 DA", desc: "디스플레이 광고" },
  { name: "네이버 쇼핑", desc: "쇼핑 파워링크" },
  { name: "카카오", desc: "DA / 비즈보드" },
  { name: "구글 GDN", desc: "디스플레이 네트워크" },
  { name: "유튜브", desc: "투명성 센터 / 영상" },
  { name: "메타", desc: "Facebook / Instagram" },
  { name: "틱톡", desc: "Creative Center" },
];

const STATS = [
  { value: "9", label: "수집 채널" },
  { value: "4,300+", label: "광고 소재" },
  { value: "780+", label: "모니터링 광고주" },
  { value: "2.98억+", label: "월 추정 광고비" },
];

function FeatureIcon({ name }: { name: string }) {
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
    case "advertiser":
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
    case "landscape":
      return (
        <svg {...props}>
          <path d="M2 20L8.5 8 13 16l4-6 5 10" />
          <path d="M2 20h20" />
        </svg>
      );
    case "campaign":
      return (
        <svg {...props}>
          <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
          <path d="M22 4L12 14.01l-3-3" />
        </svg>
      );
    default:
      return null;
  }
}

export default function AboutPage() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      {/* Hero */}
      <section className="text-center mb-16">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">AdScope</h1>
        <p className="text-xl text-adscope-600 font-medium mb-3">
          한국 디지털 광고 통합 모니터링 인텔리전스 플랫폼
        </p>
        <p className="text-gray-500 max-w-2xl mx-auto leading-relaxed">
          AdScope는 국내 주요 디지털 광고 매체 9개 채널의 광고 소재, 집행 현황, 광고비를 통합
          모니터링하여 마케팅 의사결정에 필요한 경쟁 인텔리전스를 제공합니다.
          캠페인 분석, 소셜 채널 추적, 신제품 임팩트 측정, AI 기반 자동 분류까지
          종합적인 광고 인텔리전스를 경험하세요.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-4">
          <Link
            href="/pricing"
            className="px-6 py-3 bg-adscope-600 text-white font-semibold rounded-lg hover:bg-adscope-700 transition-colors"
          >
            요금제 보기
          </Link>
          <a
            href="/AdScope_서비스소개.pdf"
            download
            className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold rounded-lg hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200"
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
            className="px-6 py-3 border border-gray-300 text-gray-700 font-semibold rounded-lg hover:border-adscope-400 hover:text-adscope-600 transition-colors"
          >
            대시보드
          </Link>
        </div>
      </section>

      {/* Key Stats */}
      <section className="mb-16">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {STATS.map((s) => (
            <div
              key={s.label}
              className="bg-gradient-to-br from-adscope-50 to-blue-50 rounded-xl p-5 text-center"
            >
              <p className="text-2xl font-bold text-adscope-600">{s.value}</p>
              <p className="text-xs mt-1 text-gray-500">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Key Features */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
          주요 기능
        </h2>
        <p className="text-gray-500 text-center mb-10">
          광고 모니터링에 필요한 핵심 기능을 제공합니다.
        </p>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="bg-white border border-gray-200 rounded-xl p-6 hover:shadow-md transition-shadow"
            >
              <div className="w-12 h-12 bg-adscope-50 rounded-lg flex items-center justify-center text-adscope-600 mb-4">
                <FeatureIcon name={f.icon} />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">
                {f.title}
              </h3>
              <p className="text-sm text-gray-500 leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Data Coverage */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
          데이터 커버리지
        </h2>
        <p className="text-gray-500 text-center mb-10">
          국내 주요 디지털 광고 매체 9개 채널을 폭넓게 지원합니다.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {CHANNELS.map((ch) => (
            <div
              key={ch.name}
              className="bg-white border border-gray-200 rounded-xl p-5 text-center hover:border-adscope-300 transition-colors"
            >
              <p className="text-lg font-bold text-gray-900">{ch.name}</p>
              <p className="text-xs mt-1 text-gray-400">{ch.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing Summary */}
      <section className="mb-16">
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
            <p className="text-3xl font-bold text-gray-900">49,000<span className="text-sm font-normal text-gray-400">원/월</span></p>
            <p className="text-xs text-gray-400 mt-1">연간 490,000원 (17% 할인)</p>
            <ul className="mt-4 space-y-1.5 text-sm text-gray-600">
              <li>9개 채널 광고 소재 열람</li>
              <li>광고주 리포트 / 광고비 분석</li>
              <li>시장 분석 / 경쟁사 비교</li>
              <li>캠페인 분석 / 임팩트 측정</li>
              <li>보고서 생성 (광고 정보)</li>
            </ul>
          </div>
          <div className="bg-adscope-600 text-white rounded-xl p-6">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold">Full</h3>
              <span className="text-[10px] bg-white/20 px-2 py-0.5 rounded-full font-semibold">추천</span>
            </div>
            <p className="text-sm text-adscope-100 mb-3">광고 + 소셜 통합 분석</p>
            <p className="text-3xl font-bold">99,000<span className="text-sm font-normal text-adscope-200">원/월</span></p>
            <p className="text-xs text-adscope-200 mt-1">연간 990,000원 (17% 할인)</p>
            <ul className="mt-4 space-y-1.5 text-sm text-adscope-50">
              <li>Lite 전체 기능 포함</li>
              <li>소셜 소재 갤러리 (YouTube/Instagram)</li>
              <li>소셜 채널 분석 (구독자/인게이지먼트)</li>
              <li>브랜드 채널 분석</li>
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

      {/* Terms & Privacy Links */}
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

      {/* Footer */}
      <div className="text-center text-sm text-gray-400 py-6 border-t border-gray-100">
        <p>AdScope | 광고 인텔리전스 플랫폼</p>
        <p className="mt-1">문의: support@adscope.kr</p>
      </div>
    </div>
  );
}
