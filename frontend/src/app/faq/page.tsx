"use client";

import { useState } from "react";

type FAQ = {
  id: string;
  question: string;
  answer: React.ReactNode;
};

const FAQS: FAQ[] = [
  {
    id: "channels",
    question: "AdScope는 어떤 매체를 지원하나요?",
    answer: (
      <div className="space-y-2">
        <p>현재 7개 주요 디지털 광고 채널을 지원합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>네이버 검색광고:</strong> 키워드 기반 검색 광고 수집</li>
          <li><strong>네이버 DA:</strong> 디스플레이 광고 수집</li>
          <li><strong>카카오 DA:</strong> 카카오 디스플레이/비즈보드 광고 수집</li>
          <li><strong>Google GDN:</strong> 구글 디스플레이 네트워크 광고 수집</li>
          <li><strong>YouTube Ads:</strong> 유튜브 투명성 센터 기반 광고 수집</li>
          <li><strong>Facebook:</strong> 메타 Ad Library 기반 광고 수집</li>
          <li><strong>Instagram:</strong> 메타 Ad Library 기반 광고 수집</li>
        </ul>
        <p className="text-xs text-gray-400 mt-2">* TikTok은 현재 준비 중입니다.</p>
      </div>
    ),
  },
  {
    id: "update",
    question: "데이터는 얼마나 자주 업데이트되나요?",
    answer: (
      <div className="space-y-2">
        <p>광고 소재는 <strong>매일 자동으로 수집</strong>됩니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>광고 소재 수집:</strong> 7개 채널 병렬 수집 (회당 약 10분, 하루 복수 회차)</li>
          <li><strong>AI 분류:</strong> 매일 03:00 KST에 DeepSeek 텍스트 + OpenRouter Vision으로 자동 분류</li>
          <li><strong>메타시그널:</strong> 04:00~05:30 KST에 스마트스토어, 트래픽, 활동점수, 통합집계 순차 갱신</li>
          <li><strong>광고비 추정:</strong> AI 분류 후 자동으로 재계산</li>
        </ul>
        <p className="text-sm mt-2">기본 조회 기간은 30일이며, 최대 90일까지 선택할 수 있습니다.</p>
      </div>
    ),
  },
  {
    id: "meta-signal",
    question: "메타시그널이란 무엇인가요?",
    answer: (
      <div className="space-y-2">
        <p>메타시그널은 광고 소재 수집 외부의 다양한 신호를 종합하여 광고주의 실제 마케팅 활동 강도를 분석하는 시스템입니다. 4가지 구성요소로 이루어져 있습니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>스마트스토어 스코어:</strong> 네이버 스마트스토어의 상품 변동, 리뷰 수, 판매량 추이를 추적합니다.</li>
          <li><strong>트래픽 스코어:</strong> 네이버 데이터랩 검색 트렌드와 채널 조회수 변화를 분석합니다.</li>
          <li><strong>활동 점수:</strong> 광고 수집 빈도, 소셜 포스팅, 채널 활동 등을 종합합니다.</li>
          <li><strong>패널 보정:</strong> AI 패널 관찰 + 사용자 제출 데이터를 결합하여 보정합니다.</li>
        </ul>
        <p className="text-sm mt-2">이 4가지가 결합되어 광고비 추정 보정 배수(0.7~1.5x)를 산출하며, 광고주 상세 페이지에서 확인할 수 있습니다.</p>
      </div>
    ),
  },
  {
    id: "spend",
    question: "광고비 추정은 어떻게 하나요?",
    answer: (
      <div className="space-y-2">
        <p>AdScope는 4가지 독립적인 방법론을 결합하여 광고비를 추정합니다.</p>
        <ol className="list-decimal list-inside space-y-1 text-sm">
          <li><strong>CPC 기반 추정:</strong> 채널별 평균 CPC/CPV에 노출 빈도를 곱하여 기본 광고비를 산출합니다.</li>
          <li><strong>카탈로그 역추산:</strong> 메타 Ad Library 등 카탈로그의 소재 수, 포맷, 활성일수를 기반으로 역추산합니다.</li>
          <li><strong>메타시그널 보정:</strong> 검색량, 채널 활동, 스마트스토어 데이터로 보정 배수를 적용합니다.</li>
          <li><strong>실집행 벤치마크:</strong> 실제 미디어 집행 데이터로 채널별 매체비 대비 총수주액 비율을 캘리브레이션합니다.</li>
        </ol>
        <p className="text-sm mt-2">단일 방법론의 한계를 극복하기 위해 복수의 방법론을 교차 검증합니다.</p>
      </div>
    ),
  },
  {
    id: "plans",
    question: "Lite와 Full 플랜의 차이는 무엇인가요?",
    answer: (
      <div className="space-y-2">
        <p>두 플랜의 핵심 차이는 <strong>소셜 관련 기능의 포함 여부</strong>입니다.</p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 pr-4">기능</th>
                <th className="text-center py-2 px-3">Lite (49,000원/월)</th>
                <th className="text-center py-2 px-3">Full (99,000원/월)</th>
              </tr>
            </thead>
            <tbody className="text-gray-600">
              <tr className="border-b"><td className="py-1.5 pr-4">광고 소재 갤러리 (7채널)</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-1.5 pr-4">광고주 리포트 / 광고비 분석</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-1.5 pr-4">시장 분석 / 경쟁사 비교</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-1.5 pr-4">소셜 소재 갤러리</td><td className="text-center text-gray-300">X</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-1.5 pr-4">브랜드/소셜 채널 분석</td><td className="text-center text-gray-300">X</td><td className="text-center text-green-600">O</td></tr>
              <tr><td className="py-1.5 pr-4">보고서 소셜 섹션</td><td className="text-center text-gray-300">X</td><td className="text-center text-green-600">O</td></tr>
            </tbody>
          </table>
        </div>
        <p className="text-sm mt-2">연간 결제 시 할인이 적용됩니다. (Lite 490,000원/년, Full 990,000원/년)</p>
      </div>
    ),
  },
  {
    id: "export",
    question: "데이터 내보내기가 가능한가요?",
    answer: (
      <div className="space-y-2">
        <p>네, 다양한 형식으로 데이터를 내보낼 수 있습니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>보고서:</strong> 광고주별 맞춤 보고서를 PDF로 내보낼 수 있습니다.</li>
          <li><strong>데이터:</strong> 광고 소재 목록, 광고비 분석 결과 등을 CSV로 다운로드할 수 있습니다.</li>
        </ul>
        <p className="text-sm mt-2">보고서에는 차트, 광고 소재 이미지, 분석 데이터가 포함됩니다.</p>
      </div>
    ),
  },
  {
    id: "concurrent",
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
    question: "무료 체험이 가능한가요?",
    answer: (
      <div className="space-y-2">
        <p>현재 별도의 무료 체험 기간은 제공되지 않습니다.</p>
        <p className="text-sm">다만, 도입을 검토 중이시라면 <strong>샘플 리포트</strong>를 요청하실 수 있습니다. <a href="/pricing" className="text-blue-600 hover:underline">요금제 페이지</a> 하단의 문의 양식을 통해 신청해 주세요.</p>
        <p className="text-sm mt-2">맞춤 상담도 가능합니다. support@adscope.kr로 연락해 주세요.</p>
      </div>
    ),
  },
  {
    id: "browser",
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
    question: "고객 지원은 어떻게 받나요?",
    answer: (
      <div className="space-y-2">
        <p>아래 채널을 통해 고객 지원을 받으실 수 있습니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>이메일:</strong> <a href="mailto:support@adscope.kr" className="text-blue-600 hover:underline">support@adscope.kr</a></li>
          <li><strong>응대 시간:</strong> 평일 09:00 ~ 18:00 (KST)</li>
          <li><strong>문의 양식:</strong> <a href="/pricing" className="text-blue-600 hover:underline">요금제 페이지</a> 하단 문의 양식</li>
        </ul>
        <p className="text-sm mt-2">기술적 문의, 기능 요청, 결제 관련 문의 등 모든 문의를 접수합니다.</p>
      </div>
    ),
  },
];

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

  const toggle = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => setOpenIds(new Set(FAQS.map((f) => f.id)));
  const collapseAll = () => setOpenIds(new Set());

  return (
    <div className="p-6 lg:p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">자주 묻는 질문</h1>
        <p className="text-sm text-gray-500 mt-1">
          AdScope 서비스에 대해 자주 묻는 질문과 답변입니다.
        </p>
      </div>

      <div className="flex gap-2 mb-6">
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

      <div className="space-y-3">
        {FAQS.map((faq) => (
          <FAQItem
            key={faq.id}
            faq={faq}
            isOpen={openIds.has(faq.id)}
            onToggle={() => toggle(faq.id)}
          />
        ))}
      </div>

      <div className="mt-10 p-5 bg-blue-50 rounded-xl text-center">
        <p className="text-sm text-blue-800">
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
