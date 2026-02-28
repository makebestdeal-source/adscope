"use client";

import Link from "next/link";

const FEATURES = [
  {
    title: "광고 소재 갤러리",
    href: "/gallery",
    description:
      "네이버(검색/DA/쇼핑), 카카오, 구글(GDN/검색광고), 유튜브, 페이스북, 인스타그램, 틱톡 등 10개 채널에서 수집한 광고 크리에이티브를 한눈에 비교합니다. 채널/광고주/기간별 필터, AI 제품 카테고리 분류, 랜딩 페이지 분석, 크리에이티브 해시 기반 중복 제거를 제공합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="M21 15l-5-5L5 21" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "소셜 소재 분석",
    href: "/social-gallery",
    description:
      "광고주의 유튜브 채널 영상과 인스타그램 공식 포스트를 모니터링합니다. 조회수, 좋아요, 댓글, 게시일 등 콘텐츠 성과 지표를 추적하고 브랜드 채널별 콘텐츠 전략을 분석합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 01-3.46 0" />
        <circle cx="18" cy="3" r="2" fill="currentColor" />
      </svg>
    ),
    plan: "Full",
  },
  {
    title: "광고주 리포트",
    href: "/advertisers",
    description:
      "기업-브랜드-제품 계층 구조로 광고주를 관리합니다. 미디어 브레이크다운, 채널 분포, 캠페인 상세(저니/리프트), 광고모델 정보, 메타시그널 종합 점수, 활동 추이를 분석합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <circle cx="9" cy="7" r="3" />
        <path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
        <circle cx="17" cy="8" r="2" />
        <path d="M21 21v-1a3 3 0 0 0-2-2.8" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "광고비 분석",
    href: "/spend",
    description:
      "CPC 기반 추정, 카탈로그 역추산, 메타시그널 보정, 실집행 벤치마크 캘리브레이션의 4가지 방식을 결합하여 광고주별 광고비를 산출합니다. 채널별 시장 보정 계수(META x10.1, GDN x13.9 등)를 적용하여 실집행 수준의 정확도를 제공합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <rect x="2" y="6" width="20" height="12" rx="2" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "시장 분석",
    href: "/industries",
    description:
      "산업별 현황, 제품/서비스 카테고리, 경쟁사 비교, 소셜 채널 분석, 광고주 트렌드를 통해 시장 전체를 조망합니다. SOV(점유율), 접촉률, 페르소나별 광고 노출 랭킹 등 심층 분석 도구를 함께 제공합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <path d="M2 20L8.5 8 13 16l4-6 5 10" />
        <path d="M2 20h20" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "소셜 채널 분석",
    href: "/social-channels",
    description:
      "브랜드 공식 YouTube/Instagram 채널의 구독자, 팔로워, 인게이지먼트 변화를 추적합니다. 채널별 콘텐츠 성과와 성장 추이를 비교 분석합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
        <path d="M22 12A10 10 0 0 0 12 2v10z" />
      </svg>
    ),
    plan: "Full",
  },
  {
    title: "캠페인 분석",
    href: "/campaigns",
    description:
      "캠페인별 소재 매핑, 고객 저니(노출-관심-고려-전환) 추적, 캠페인 전후 리프트 효과(검색량/소셜/매출)를 분석합니다. 캠페인 목적, 프로모션 카피, 광고 모델 정보까지 체계적으로 관리합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
        <path d="M22 4L12 14.01l-3-3" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "신제품 출시 임팩트",
    href: "/launch-impact",
    description:
      "신제품/신규 캠페인 런칭 전후의 광고 집행, 검색 트렌드, 소셜 반응을 종합하여 LII(Launch Impact Index) 스코어를 산출합니다. 출시 효과를 정량적으로 평가합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <path d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "마케팅 스케줄 추적",
    href: "/marketing-schedule",
    description:
      "광고주별 마케팅 캠페인 일정을 타임라인으로 시각화합니다. 프로모션 기간, 광고 집중 시기, 시즌 캠페인 패턴을 파악하여 경쟁사 마케팅 플랜을 예측합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "쇼핑인사이트",
    href: "/shopping-insight",
    description:
      "네이버 쇼핑 파워링크 광고를 추적하고, 카테고리별 광고 분포와 프로모션 트렌드를 분석합니다. 커머스 광고 전략 수립에 필요한 인사이트를 제공합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z" />
        <path d="M3 6h18" />
        <path d="M16 10a4 4 0 01-8 0" />
      </svg>
    ),
    plan: "Lite+",
  },
  {
    title: "보고서 생성",
    href: "/reports",
    description:
      "광고 소재와 소셜 소재를 독립적으로 선택하여 맞춤형 보고서를 생성합니다. 매체 태그, 광고주별 요약, 채널 분석 등 다양한 포맷을 지원합니다.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-8 h-8">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
        <path d="M14 2v6h6" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
    plan: "Lite+",
  },
];

const CHANNELS = [
  { name: "네이버 검색", color: "bg-green-100 text-green-700" },
  { name: "네이버 DA", color: "bg-emerald-100 text-emerald-700" },
  { name: "네이버 쇼핑", color: "bg-lime-100 text-lime-700" },
  { name: "카카오 DA", color: "bg-yellow-100 text-yellow-700" },
  { name: "Google GDN", color: "bg-sky-100 text-sky-700" },
  { name: "Google 검색광고", color: "bg-cyan-100 text-cyan-700" },
  { name: "YouTube Ads", color: "bg-red-100 text-red-700" },
  { name: "Facebook", color: "bg-blue-100 text-blue-700" },
  { name: "Instagram", color: "bg-pink-100 text-pink-700" },
  { name: "TikTok", color: "bg-gray-100 text-gray-600" },
];

export default function GuidePage() {
  return (
    <div className="p-6 lg:p-8 max-w-5xl">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold text-gray-900">AdScope 서비스 소개</h1>
        <p className="text-base text-gray-500 mt-2">
          한국 디지털 광고 통합 모니터링 인텔리전스 플랫폼
        </p>
        <a
          href="/AdScope_서비스소개.pdf"
          download
          className="inline-flex items-center gap-2 mt-4 px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-semibold rounded-xl hover:shadow-lg hover:shadow-indigo-200/50 transition-all duration-200 active:scale-[0.98] text-sm"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4.5 h-4.5">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M7 10l5 5 5-5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          서비스 소개서 다운로드
        </a>
      </div>

      {/* What is AdScope */}
      <section className="mb-12 bg-gradient-to-br from-slate-50 to-blue-50 rounded-2xl p-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">AdScope란?</h2>
        <p className="text-gray-700 leading-relaxed">
          AdScope는 국내 주요 디지털 광고 채널(네이버, 카카오, 구글, 유튜브, 페이스북, 인스타그램, 틱톡 등 10개 채널)의
          광고 소재를 자동 수집하고, AI 기반으로 광고주/산업/제품 카테고리를 분류하며,
          광고비를 역추산하여 시장 인텔리전스를 제공하는 B2B SaaS 플랫폼입니다.
          캠페인 분석, 고객 저니 추적, 신제품 출시 임팩트 측정, 소셜 채널 모니터링,
          스마트스토어 카테고리 분석까지 마케팅 의사결정에 필요한 종합 경쟁 인텔리전스를 제공합니다.
        </p>
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <p className="text-2xl font-bold text-blue-600">10</p>
            <p className="text-xs text-gray-500 mt-1">수집 채널</p>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <p className="text-2xl font-bold text-blue-600">6,200+</p>
            <p className="text-xs text-gray-500 mt-1">수집 광고 소재</p>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <p className="text-2xl font-bold text-blue-600">630+</p>
            <p className="text-xs text-gray-500 mt-1">모니터링 광고주</p>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm">
            <p className="text-2xl font-bold text-blue-600">24/7</p>
            <p className="text-xs text-gray-500 mt-1">자동 수집</p>
          </div>
        </div>
      </section>

      {/* Meta-Signal System */}
      <section className="mb-12 bg-gradient-to-br from-indigo-50 to-purple-50 rounded-2xl p-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">메타시그널 시스템</h2>
        <p className="text-gray-700 leading-relaxed mb-6">
          광고 소재 수집 외에도 다양한 외부 신호를 종합하여 광고주의 실제 마케팅 활동 강도를 분석합니다.
          4가지 구성요소가 결합되어 광고비 추정의 정확도를 높입니다.
        </p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="bg-white rounded-xl p-5 shadow-sm">
            <h4 className="font-semibold text-gray-900 mb-1">스마트스토어 추적</h4>
            <p className="text-sm text-gray-500">네이버 스마트스토어의 상품 변동, 리뷰 수, 판매량 추이를 추적하여 커머스 활동 지표를 생성합니다.</p>
          </div>
          <div className="bg-white rounded-xl p-5 shadow-sm">
            <h4 className="font-semibold text-gray-900 mb-1">트래픽 분석</h4>
            <p className="text-sm text-gray-500">네이버 데이터랩 검색 트렌드와 채널 조회수를 분석하여 브랜드 관심도 변화를 수치화합니다.</p>
          </div>
          <div className="bg-white rounded-xl p-5 shadow-sm">
            <h4 className="font-semibold text-gray-900 mb-1">활동 점수</h4>
            <p className="text-sm text-gray-500">광고 수집 빈도, 소셜 포스팅, 채널 활동 등을 종합하여 광고주별 일일 활동 점수를 산출합니다.</p>
          </div>
          <div className="bg-white rounded-xl p-5 shadow-sm">
            <h4 className="font-semibold text-gray-900 mb-1">패널 보정</h4>
            <p className="text-sm text-gray-500">크롤링 시 자동 기록되는 AI 패널 관찰 데이터와 사용자 제출 데이터를 결합하여 추정치를 보정합니다.</p>
          </div>
        </div>
      </section>

      {/* Spend Estimation */}
      <section className="mb-12 bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">광고비 역추산 (4가지 방식)</h2>
        <p className="text-gray-700 leading-relaxed mb-6">
          단일 방법론의 한계를 극복하기 위해 4가지 독립적인 역추산 방식을 결합합니다.
          실집행 데이터 기반 채널별 보정 계수를 적용하여 실제 광고비 대비 99~101% 일치율을 달성합니다.
        </p>
        <div className="space-y-3">
          <div className="bg-white rounded-xl p-4 shadow-sm flex items-start gap-3">
            <span className="flex-shrink-0 w-7 h-7 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center text-sm font-bold">1</span>
            <div>
              <h4 className="font-semibold text-gray-900">CPC 기반 추정</h4>
              <p className="text-sm text-gray-500">채널별 평균 CPC/CPV에 노출 빈도를 곱하여 기본 광고비를 산출합니다.</p>
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm flex items-start gap-3">
            <span className="flex-shrink-0 w-7 h-7 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center text-sm font-bold">2</span>
            <div>
              <h4 className="font-semibold text-gray-900">카탈로그 역추산</h4>
              <p className="text-sm text-gray-500">메타 Ad Library 등 카탈로그의 소재 수, 포맷, 활성일수를 기반으로 역추산합니다.</p>
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm flex items-start gap-3">
            <span className="flex-shrink-0 w-7 h-7 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center text-sm font-bold">3</span>
            <div>
              <h4 className="font-semibold text-gray-900">메타시그널 보정</h4>
              <p className="text-sm text-gray-500">검색량, 채널 활동, 스마트스토어 데이터로 0.7~1.5x 보정 배수를 적용합니다.</p>
            </div>
          </div>
          <div className="bg-white rounded-xl p-4 shadow-sm flex items-start gap-3">
            <span className="flex-shrink-0 w-7 h-7 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center text-sm font-bold">4</span>
            <div>
              <h4 className="font-semibold text-gray-900">실집행 벤치마크</h4>
              <p className="text-sm text-gray-500">실제 미디어 집행 데이터로 채널별 매체비 대비 총수주액 비율을 캘리브레이션합니다. (META x10.1, GDN x13.9 등)</p>
            </div>
          </div>
        </div>
      </section>

      {/* Core Features */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-gray-900 mb-6">핵심 기능</h2>
        <div className="space-y-4">
          {FEATURES.map((f) => (
            <Link
              key={f.href}
              href={f.href}
              className="flex items-start gap-4 p-5 bg-white rounded-xl border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all group"
            >
              <div className="flex-shrink-0 w-12 h-12 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center group-hover:bg-blue-100 transition-colors">
                {f.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-gray-900 group-hover:text-blue-600 transition-colors">
                    {f.title}
                  </h3>
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                    f.plan === "Full" ? "bg-green-100 text-green-700" :
                    f.plan === "Lite+" ? "bg-blue-100 text-blue-700" :
                    "bg-gray-100 text-gray-500"
                  }`}>
                    {f.plan}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mt-1 leading-relaxed">{f.description}</p>
              </div>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-5 h-5 text-gray-300 group-hover:text-blue-400 flex-shrink-0 mt-1 transition-colors">
                <path d="M9 18l6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          ))}
        </div>
      </section>

      {/* Supported Channels */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-gray-900 mb-4">지원 채널 (10개)</h2>
        <div className="flex flex-wrap gap-2">
          {CHANNELS.map((ch) => (
            <span key={ch.name} className={`px-3 py-1.5 rounded-full text-sm font-medium ${ch.color}`}>
              {ch.name}
            </span>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-3">
          * 네이버 검색/DA/쇼핑 각각 독립 수집, YouTube는 투명성 센터 + 영상 접촉 방식 병행
        </p>
      </section>

      {/* AI Enrichment */}
      <section className="mb-12 bg-gradient-to-br from-teal-50 to-cyan-50 rounded-2xl p-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">AI 기반 자동 분석</h2>
        <p className="text-gray-700 leading-relaxed mb-6">
          매일 새벽 AI 모델이 수집된 광고 소재를 자동 분석하여 부가 정보를 생성합니다.
        </p>
        <div className="grid sm:grid-cols-3 gap-4">
          <div className="bg-white rounded-xl p-5 shadow-sm">
            <h4 className="font-semibold text-gray-900 mb-1">제품 카테고리 분류</h4>
            <p className="text-sm text-gray-500">DeepSeek + OpenRouter Vision 모델로 광고 소재의 제품/서비스 카테고리를 자동 분류합니다.</p>
          </div>
          <div className="bg-white rounded-xl p-5 shadow-sm">
            <h4 className="font-semibold text-gray-900 mb-1">랜딩 페이지 분석</h4>
            <p className="text-sm text-gray-500">광고 클릭 후 도달하는 랜딩 페이지를 자동 분석하여 도메인-브랜드 매핑 캐시를 구축합니다.</p>
          </div>
          <div className="bg-white rounded-xl p-5 shadow-sm">
            <h4 className="font-semibold text-gray-900 mb-1">크리에이티브 중복 제거</h4>
            <p className="text-sm text-gray-500">SHA-256 해시 기반으로 채널 간 동일 소재를 감지하여 중복 없는 깨끗한 데이터를 유지합니다.</p>
          </div>
        </div>
      </section>

      {/* Plans */}
      <section className="mb-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">요금제</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="bg-white border border-gray-200 rounded-xl p-6">
            <h3 className="font-bold text-lg text-gray-900">Lite</h3>
            <p className="text-3xl font-bold text-gray-900 mt-2">49,000<span className="text-base font-normal text-gray-400">/월</span></p>
            <p className="text-sm text-gray-400">연간 490,000원</p>
            <ul className="mt-4 space-y-2 text-sm text-gray-600">
              <li className="flex items-center gap-2"><span className="text-green-500">&#10003;</span> 광고 소재 갤러리 (10개 채널)</li>
              <li className="flex items-center gap-2"><span className="text-green-500">&#10003;</span> 광고주 리포트 (캠페인/모델/메타시그널)</li>
              <li className="flex items-center gap-2"><span className="text-green-500">&#10003;</span> 광고비 분석 (4가지 역추산)</li>
              <li className="flex items-center gap-2"><span className="text-green-500">&#10003;</span> 시장 분석 (산업/경쟁사/SOV/접촉률)</li>
              <li className="flex items-center gap-2"><span className="text-green-500">&#10003;</span> 신제품 출시 임팩트 (LII)</li>
              <li className="flex items-center gap-2"><span className="text-green-500">&#10003;</span> 마케팅 스케줄 / 쇼핑인사이트</li>
              <li className="flex items-center gap-2"><span className="text-green-500">&#10003;</span> 보고서 생성 (광고 정보)</li>
              <li className="flex items-center gap-2 text-gray-300"><span>&#10007;</span> 소셜 소재 갤러리</li>
              <li className="flex items-center gap-2 text-gray-300"><span>&#10007;</span> 소셜 채널 / 브랜드 채널 분석</li>
            </ul>
          </div>
          <div className="bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-xl p-6">
            <h3 className="font-bold text-lg">Full <span className="text-xs bg-blue-500 px-2 py-0.5 rounded-full ml-2">추천</span></h3>
            <p className="text-3xl font-bold mt-2">99,000<span className="text-base font-normal text-blue-200">/월</span></p>
            <p className="text-sm text-blue-200">연간 990,000원</p>
            <ul className="mt-4 space-y-2 text-sm text-blue-50">
              <li className="flex items-center gap-2"><span>&#10003;</span> Lite 전체 기능 포함</li>
              <li className="flex items-center gap-2"><span>&#10003;</span> 소셜 소재 갤러리 (YouTube/Instagram)</li>
              <li className="flex items-center gap-2"><span>&#10003;</span> 브랜드 채널 분석</li>
              <li className="flex items-center gap-2"><span>&#10003;</span> 소셜 채널 분석 (구독자/인게이지먼트)</li>
              <li className="flex items-center gap-2"><span>&#10003;</span> 보고서 소셜 섹션 포함</li>
            </ul>
          </div>
        </div>
        <div className="mt-4 text-center">
          <Link href="/pricing" className="text-sm text-blue-600 hover:text-blue-800 font-medium">
            상세 요금 안내 보기 &rarr;
          </Link>
        </div>
      </section>
    </div>
  );
}
