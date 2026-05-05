"use client";

import { useState } from "react";

type FAQ = {
  id: string;
  category: string;
  question: string;
  answer: React.ReactNode;
};

const FAQS: FAQ[] = [
  /* ── 서비스 일반 ── */
  {
    id: "what-is",
    category: "서비스 일반",
    question: "AdScope는 어떤 서비스인가요?",
    answer: (
      <div className="space-y-2">
        <p>
          AdScope는 국내 주요 9개 디지털 광고 채널의 소재, 집행 현황, 광고비를 통합 모니터링하여
          마케팅 의사결정에 필요한 경쟁 인텔리전스를 제공하는 B2B SaaS 플랫폼입니다.
        </p>
        <p className="text-sm">
          현재 공개 메뉴는 광고주, 캠페인, 광고 소재, 키워드, 시장 분석,
          소셜 공개 메뉴를 중심으로 제공합니다.
          현재 6,000개 이상의 광고주, 39,000건 이상의 광고 소재, 11,000건 이상의 캠페인을 모니터링하고 있습니다.
        </p>
      </div>
    ),
  },
  {
    id: "channels",
    category: "서비스 일반",
    question: "AdScope는 어떤 매체를 지원하나요?",
    answer: (
      <div className="space-y-2">
        <p>현재 <strong>9개</strong> 주요 디지털 광고 채널을 지원합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>네이버 검색광고:</strong> 키워드 기반 검색 광고 (SA/파워링크) 수집</li>
          <li><strong>네이버 DA:</strong> 네이버 디스플레이 광고 수집</li>
          <li><strong>네이버 쇼핑:</strong> 쇼핑탭 파워링크 광고 수집</li>
          <li><strong>카카오 DA:</strong> 카카오 디스플레이/비즈보드 광고 수집</li>
          <li><strong>Google GDN:</strong> 구글 디스플레이 네트워크 광고 수집</li>
          <li><strong>Google 검색광고:</strong> 구글 검색 광고 수집</li>
          <li><strong>YouTube Ads:</strong> 유튜브 투명성 센터 기반 광고 수집</li>
          <li><strong>Meta (Facebook/Instagram):</strong> 메타 Ad Library 기반 광고 수집</li>
          <li><strong>TikTok:</strong> Creative Center Top Ads 기반 광고 수집</li>
        </ul>
      </div>
    ),
  },
  {
    id: "update",
    category: "서비스 일반",
    question: "데이터는 얼마나 자주 업데이트되나요?",
    answer: (
      <div className="space-y-2">
        <p>광고 소재는 <strong>매일 자동으로 수집</strong>됩니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>광고 소재 수집:</strong> 9개 채널 병렬 수집 (매일 여러 차례 자동 실행)</li>
          <li><strong>AI 분류:</strong> 수집 후 자동으로 제품 카테고리 분류, 광고주 매칭, 중복 제거</li>
          <li><strong>공개 메뉴 데이터:</strong> 수집 데이터 기반으로 광고주, 캠페인, 소재 화면 갱신</li>
        </ul>
        <p className="text-sm mt-2">기본 조회 기간은 30일이며, 최대 90일까지 선택할 수 있습니다.</p>
      </div>
    ),
  },
  {
    id: "collection-method",
    category: "서비스 일반",
    question: "광고 데이터는 어떤 방식으로 수집하나요?",
    answer: (
      <div className="space-y-2">
        <p>AdScope는 두 가지 방식을 병행하여 광고 데이터를 수집합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>카탈로그 수집:</strong> YouTube 투명성 센터, Meta Ad Library, TikTok Creative Center 등 플랫폼 공개 데이터를 수집합니다.</li>
          <li><strong>채널별 수집:</strong> 네이버 검색/DA, 카카오 DA, 구글 GDN 등에서 확인되는 광고 소재를 정리합니다.</li>
        </ul>
        <p className="text-sm mt-2">두 방식을 결합하여 공개 메뉴에서 확인할 수 있는 광고 데이터를 구성합니다.</p>
      </div>
    ),
  },

  /* ── 기능 ── */
  {
    id: "features-keyword",
    category: "기능",
    question: "키워드분석에서는 어떤 분석이 가능한가요?",
    answer: (
      <div className="space-y-2">
        <p>키워드분석 메뉴에서 3가지 분석 기능을 제공합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>키워드역추적:</strong> 특정 광고주가 입찰하고 있는 검색 키워드를 역추적합니다. 경쟁사의 검색 광고 전략을 파악할 수 있습니다.</li>
          <li><strong>광고랜드스케이프:</strong> 키워드별 광고 분포를 시각화합니다. 어떤 광고주가 어떤 키워드에서 경쟁하는지 한눈에 파악합니다.</li>
          <li><strong>광고비추이:</strong> 광고주별, 매체별 광고비 추이를 시계열로 분석합니다. 시장 투자 변화와 경쟁 역학을 추적합니다.</li>
        </ul>
      </div>
    ),
  },
  {
    id: "features-market",
    category: "기능",
    question: "시장분석에서는 무엇을 볼 수 있나요?",
    answer: (
      <div className="space-y-2">
        <p>시장분석 메뉴에서 4가지 분석 기능을 제공합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>산업별현황:</strong> 산업/업종별 광고 시장 규모, 주요 플레이어, 매체별 분포를 분석합니다.</li>
          <li><strong>제품서비스현황:</strong> 제품/서비스 카테고리별 광고 현황과 트렌드를 파악합니다.</li>
          <li><strong>경쟁사비교:</strong> 특정 광고주와 경쟁사의 광고 활동, 매체 믹스, 광고비를 비교 분석합니다.</li>
          <li><strong>광고주트렌드:</strong> 광고주의 시간별 활동 변화, 신규 진입/이탈 광고주, 시장 점유율 변동을 추적합니다.</li>
        </ul>
      </div>
    ),
  },
  {
    id: "features-social",
    category: "기능",
    question: "소셜인사이트는 어떤 기능인가요?",
    answer: (
      <div className="space-y-2">
        <p>소셜인사이트는 브랜드의 소셜 미디어 활동을 확인하는 공개 메뉴입니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>소셜채널분석:</strong> 브랜드 공식 YouTube/Instagram 채널의 구독자, 팔로워, 인게이지먼트 변화를 추적합니다.</li>
          <li><strong>브랜드버즈:</strong> 브랜드 관련 소셜 미디어 언급량, 감성 분석, 화제성 변화를 모니터링합니다.</li>
        </ul>
      </div>
    ),
  },
  /* ── 데이터 ── */
  {
    id: "export",
    category: "광고비/데이터",
    question: "데이터 내보내기가 가능한가요?",
    answer: (
      <div className="space-y-2">
        <p>네, 다양한 형식으로 데이터를 내보낼 수 있습니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>보고서 (PDF):</strong> 광고주와 광고 소재 중심의 공개 데이터를 보고서로 확인합니다.</li>
          <li><strong>데이터 (CSV/Excel):</strong> 광고 소재 목록과 키워드 데이터 등 공개 메뉴 데이터를 확인합니다.</li>
        </ul>
      </div>
    ),
  },

  /* ── 요금/계정 ── */
  {
    id: "concurrent",
    category: "요금/계정",
    question: "동시 접속이 가능한가요?",
    answer: (
      <div className="space-y-2">
        <p><strong>1개 계정당 1개 기기</strong>에서만 동시 접속이 가능합니다.</p>
        <p className="text-sm">다른 기기에서 로그인하면 기존 세션이 자동으로 종료됩니다. 이는 데이터 보안을 위한 정책이며, 디바이스 핑거프린트 기반으로 관리됩니다.</p>
        <p className="text-sm mt-2">추가 계정이 필요하시면 별도로 문의해 주세요.</p>
      </div>
    ),
  },
  {
    id: "trial",
    category: "요금/계정",
    question: "무료 체험이 가능한가요?",
    answer: (
      <div className="space-y-2">
        <p>현재 별도의 무료 체험 기간은 제공되지 않습니다.</p>
        <p className="text-sm">다만, 도입을 검토 중이시라면 <strong>샘플 리포트</strong>를 요청하실 수 있습니다. <a href="/pricing" className="text-adscope-600 hover:underline">요금제 페이지</a> 하단의 문의 양식을 통해 신청해 주세요.</p>
        <p className="text-sm mt-2">맞춤 상담도 가능합니다. support@adscope.kr로 연락해 주세요.</p>
      </div>
    ),
  },
  {
    id: "payment",
    category: "요금/계정",
    question: "결제는 어떤 방식을 지원하나요?",
    answer: (
      <div className="space-y-2">
        <p>Toss Payments를 통해 안전하게 결제됩니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>카드 결제:</strong> 신용/체크카드 결제 지원</li>
          <li><strong>결제 주기:</strong> 월간 또는 연간 선택 가능</li>
          <li><strong>연간 할인:</strong> 연간 결제 시 17% 할인 적용</li>
        </ul>
        <p className="text-sm mt-2">결제 관련 문의는 support@adscope.kr로 연락해 주세요.</p>
      </div>
    ),
  },

  /* ── 이용 안내 ── */
  {
    id: "browser",
    category: "이용 안내",
    question: "어떤 브라우저를 지원하나요?",
    answer: (
      <div className="space-y-2">
        <p>AdScope는 최신 웹 브라우저를 지원합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>Google Chrome</strong> (권장)</li>
          <li><strong>Microsoft Edge</strong></li>
          <li><strong>Safari</strong></li>
        </ul>
        <p className="text-sm mt-2">최적의 사용 경험을 위해 Chrome 최신 버전을 권장합니다. Internet Explorer는 지원하지 않습니다.</p>
      </div>
    ),
  },
  {
    id: "support",
    category: "이용 안내",
    question: "고객 지원은 어떻게 받나요?",
    answer: (
      <div className="space-y-2">
        <p>아래 채널을 통해 고객 지원을 받으실 수 있습니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>이메일:</strong> <a href="mailto:support@adscope.kr" className="text-adscope-600 hover:underline">support@adscope.kr</a></li>
          <li><strong>응대 시간:</strong> 평일 09:00 ~ 18:00 (KST)</li>
          <li><strong>문의 양식:</strong> <a href="/pricing" className="text-adscope-600 hover:underline">요금제 페이지</a> 하단 문의 양식</li>
        </ul>
        <p className="text-sm mt-2">기술적 문의, 기능 요청, 결제 관련 문의 등 모든 문의를 접수합니다.</p>
      </div>
    ),
  },
  {
    id: "content-protection",
    category: "이용 안내",
    question: "데이터의 복사/저장이 제한되나요?",
    answer: (
      <div className="space-y-2">
        <p>AdScope는 <strong>콘텐츠 보호 정책</strong>을 적용하고 있습니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>화면 텍스트 선택/복사 제한</li>
          <li>인쇄(Ctrl+P) 제한</li>
          <li>워터마크 표시</li>
        </ul>
        <p className="text-sm mt-2">
          공개 메뉴의 보고서와 다운로드 기능을 통해 필요한 데이터를 안전하게 활용하실 수 있습니다.
        </p>
      </div>
    ),
  },
];

/* ── Category grouping ── */
const CURRENT_FAQ_IDS = new Set([
  "what-is",
  "channels",
  "update",
  "collection-method",
  "features-keyword",
  "features-market",
  "features-social",
  "export",
  "concurrent",
  "trial",
  "payment",
  "browser",
  "support",
  "content-protection",
]);

const CURRENT_FAQS = FAQS.filter((faq) => CURRENT_FAQ_IDS.has(faq.id));
const CATEGORIES = [...new Set(CURRENT_FAQS.map((f) => f.category))];

function FAQItem({ faq, isOpen, onToggle }: { faq: FAQ; isOpen: boolean; onToggle: () => void }) {
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-5 py-4 bg-white hover:bg-gray-50 transition-colors text-left"
      >
        <span className="font-semibold text-gray-900">{faq.question}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className={`w-5 h-5 text-gray-400 transition-transform flex-shrink-0 ml-3 ${isOpen ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {isOpen && (
        <div className="px-5 pb-5 text-sm text-gray-700 leading-relaxed border-t border-gray-100 bg-gray-50/50">
          <div className="pt-4">{faq.answer}</div>
        </div>
      )}
    </div>
  );
}

export default function FAQPage() {
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  const toggle = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => setOpenIds(new Set(filteredFaqs.map((f) => f.id)));
  const collapseAll = () => setOpenIds(new Set());

  const filteredFaqs = activeCategory
    ? CURRENT_FAQS.filter((f) => f.category === activeCategory)
    : CURRENT_FAQS;

  return (
    <div className="p-6 lg:p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">자주 묻는 질문</h1>
        <p className="text-sm text-gray-500 mt-1">
          AdScope 서비스에 대해 자주 묻는 질문과 답변입니다.
        </p>
      </div>

      {/* Category Filter */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={() => setActiveCategory(null)}
          className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
            activeCategory === null
              ? "bg-adscope-600 text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          전체
        </button>
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(cat)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              activeCategory === cat
                ? "bg-adscope-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            {cat}
          </button>
        ))}
        <div className="flex-1" />
        <button
          onClick={expandAll}
          className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
        >
          모두 펼치기
        </button>
        <button
          onClick={collapseAll}
          className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
        >
          모두 접기
        </button>
      </div>

      {/* FAQ Items grouped by category */}
      {activeCategory === null ? (
        <div className="space-y-8">
          {CATEGORIES.map((cat) => {
            const catFaqs = CURRENT_FAQS.filter((f) => f.category === cat);
            return (
              <div key={cat}>
                <h2 className="text-sm font-bold text-adscope-600 mb-3 uppercase tracking-wide">{cat}</h2>
                <div className="space-y-3">
                  {catFaqs.map((faq) => (
                    <FAQItem
                      key={faq.id}
                      faq={faq}
                      isOpen={openIds.has(faq.id)}
                      onToggle={() => toggle(faq.id)}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredFaqs.map((faq) => (
            <FAQItem
              key={faq.id}
              faq={faq}
              isOpen={openIds.has(faq.id)}
              onToggle={() => toggle(faq.id)}
            />
          ))}
        </div>
      )}

      <div className="mt-10 p-5 bg-adscope-50 rounded-xl text-center">
        <p className="text-sm text-adscope-800">
          찾으시는 답변이 없으신가요?{" "}
          <a href="mailto:support@adscope.kr" className="font-medium underline">
            support@adscope.kr
          </a>
          로 문의해 주세요.
        </p>
      </div>
    </div>
  );
}
