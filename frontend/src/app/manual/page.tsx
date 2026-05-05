"use client";

import { useState } from "react";
import Link from "next/link";

type Section = {
  id: string;
  title: string;
  content: React.ReactNode;
};

const SECTIONS: Section[] = [
  {
    id: "start",
    title: "시작하기",
    content: (
      <div className="space-y-3">
        <p>1. <Link href="/pricing" className="text-blue-600 hover:underline font-medium">요금제 페이지</Link>에서 Lite 또는 Full 플랜을 선택합니다.</p>
        <p>2. <Link href="/signup" className="text-blue-600 hover:underline font-medium">회원가입</Link> 페이지에서 회사명, 이메일, 비밀번호를 입력합니다.</p>
        <p>3. 가입 완료 후 <Link href="/login" className="text-blue-600 hover:underline font-medium">로그인</Link>하면 비로그인 공개 메뉴와 동일한 범위의 메뉴가 표시됩니다.</p>
        <p>4. 추가 기능은 업데이트 후 순차적으로 오픈됩니다.</p>
      </div>
    ),
  },
  {
    id: "gallery",
    title: "광고 소재 갤러리",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 광고소재(이미지) / 광고소재(키워드)</p>
        <p>주요 광고 채널에서 수집된 광고 크리에이티브를 카드 형태로 조회합니다.</p>
        <h4 className="font-semibold mt-4">필터 사용법</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>채널 필터:</strong> 상단 채널 탭에서 특정 매체만 선택</li>
          <li><strong>광고주 검색:</strong> 검색창에 광고주명/브랜드명 입력</li>
          <li><strong>기간 선택:</strong> 7일/14일/30일/60일/90일 중 선택 (기본값 30일)</li>
        </ul>
        <h4 className="font-semibold mt-4">상세 모달</h4>
        <p>카드를 클릭하면 광고 상세 정보가 표시됩니다:</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>광고 이미지/영상 원본</li>
          <li>광고주, 산업, 제품 카테고리</li>
          <li>랜딩 페이지 URL 및 분석 결과</li>
          <li>수집 채널, 시간, 디바이스 정보</li>
        </ul>
        <p className="text-sm text-amber-600 mt-2">Lite 이상 플랜에서 이용 가능합니다.</p>
      </div>
    ),
  },
  {
    id: "social-gallery",
    title: "소셜 소재 갤러리",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 소셜 소재</p>
        <p>광고주의 공식 유튜브 채널 영상과 인스타그램 포스트를 모니터링합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>플랫폼 필터 (YouTube / Instagram)</li>
          <li>광고주 검색으로 특정 브랜드의 소셜 콘텐츠만 조회</li>
          <li>조회수, 좋아요, 게시일 등 콘텐츠 성과 지표 표시</li>
        </ul>
        <p className="text-sm text-amber-600 mt-2">현재 공개 메뉴 기준으로 제공됩니다.</p>
      </div>
    ),
  },
  {
    id: "advertisers",
    title: "광고주 리포트",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 광고주</p>
        <h4 className="font-semibold">목록 페이지</h4>
        <p>기업-브랜드-제품의 계층 구조(트리)로 광고주를 탐색합니다. 광고 수, 웹사이트, 산업 분류가 표시됩니다.</p>
        <h4 className="font-semibold mt-4">상세 페이지</h4>
        <p>광고주를 클릭하면 아래 정보를 확인할 수 있습니다:</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>미디어 브레이크다운:</strong> 채널별 광고 소재 분포</li>
          <li><strong>채널 분포:</strong> 매체별 비율 차트</li>
          <li><strong>경쟁사 목록:</strong> 같은 산업 내 경쟁 관계</li>
          <li><strong>활동 추이:</strong> 일별 활동 점수 타임라인 차트</li>
        </ul>
      </div>
    ),
  },
  {
    id: "market",
    title: "시장 분석",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 시장 분석 그룹</p>
        <h4 className="font-semibold">산업별 현황 (/industries)</h4>
        <p>광고주 수, 소재 수, 주요 플레이어 등 산업 카드 목록과 상세 리더보드를 확인합니다.</p>
        <h4 className="font-semibold mt-3">제품/서비스별 (/products)</h4>
        <p>제품 카테고리 트리 구조로 광고/광고주 수를 조회합니다.</p>
        <h4 className="font-semibold mt-3">경쟁사 비교 (/competitors)</h4>
        <p>광고주 간 친화도 점수, 동시 노출 분석, 산업 내 경쟁 지형을 시각화합니다.</p>
        <h4 className="font-semibold mt-3">광고주 트렌드 (/advertiser-trends)</h4>
        <p>상승/하락/신규/이탈 광고주 요약, 개별 광고주 활동 궤적 차트를 제공합니다.</p>
      </div>
    ),
  },
  {
    id: "reports",
    title: "보고서 생성",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 도구 &gt; 보고서</p>
        <p>광고주를 선택하고 원하는 섹션을 조합하여 맞춤형 보고서를 생성합니다.</p>
        <h4 className="font-semibold mt-4">선택 가능한 섹션</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>개요 (광고 수, 채널, 기간 요약)</li>
          <li>매체 분석</li>
          <li>광고 소재 (대표 크리에이티브)</li>
          <li>소셜 소재</li>
          <li>경쟁사 비교</li>
        </ul>
        <p className="mt-3">기간: 7/14/30/60/90일 선택 가능. 차트와 데이터가 포함된 보고서를 PDF로 내보낼 수 있습니다.</p>
      </div>
    ),
  },
];

const CURRENT_MANUAL_SECTION_IDS = new Set([
  "start",
  "gallery",
  "social-gallery",
  "advertisers",
  "market",
  "reports",
]);

const CURRENT_SECTIONS = SECTIONS.filter((section) =>
  CURRENT_MANUAL_SECTION_IDS.has(section.id)
);

function AccordionItem({ section, isOpen, onToggle }: { section: Section; isOpen: boolean; onToggle: () => void }) {
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-5 py-4 bg-white hover:bg-gray-50 transition-colors text-left"
      >
        <span className="font-semibold text-gray-900">{section.title}</span>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className={`w-5 h-5 text-gray-400 transition-transform ${isOpen ? "rotate-180" : ""}`}
        >
          <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {isOpen && (
        <div className="px-5 pb-5 text-sm text-gray-700 leading-relaxed border-t border-gray-100 bg-gray-50/50">
          <div className="pt-4">{section.content}</div>
        </div>
      )}
    </div>
  );
}

export default function ManualPage() {
  const [openIds, setOpenIds] = useState<Set<string>>(new Set(["start"]));

  const toggle = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => setOpenIds(new Set(CURRENT_SECTIONS.map((s) => s.id)));
  const collapseAll = () => setOpenIds(new Set());

  return (
    <div className="p-6 lg:p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">이용 매뉴얼</h1>
        <p className="text-sm text-gray-500 mt-1">
          AdScope의 각 기능별 사용 방법을 안내합니다.
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
        {CURRENT_SECTIONS.map((section) => (
          <AccordionItem
            key={section.id}
            section={section}
            isOpen={openIds.has(section.id)}
            onToggle={() => toggle(section.id)}
          />
        ))}
      </div>

      <div className="mt-10 p-5 bg-blue-50 rounded-xl text-center">
        <p className="text-sm text-blue-800">
          추가 문의사항이 있으시면{" "}
          <a href="mailto:support@adscope.kr" className="font-medium underline">
            support@adscope.kr
          </a>
          로 연락해 주세요.
        </p>
      </div>
    </div>
  );
}
