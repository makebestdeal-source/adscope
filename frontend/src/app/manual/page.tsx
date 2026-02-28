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
        <p>3. 가입 완료 후 <Link href="/login" className="text-blue-600 hover:underline font-medium">로그인</Link>하면 대시보드가 표시됩니다.</p>
        <p>4. 대시보드에서 실시간 수집 현황, 채널별 통계, 활성 광고주 Top10을 확인할 수 있습니다.</p>
      </div>
    ),
  },
  {
    id: "gallery",
    title: "광고 소재 갤러리",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 광고 소재</p>
        <p>7개 채널(네이버 검색, 네이버 DA, 카카오 DA, Google GDN, YouTube Ads, Facebook, Instagram)에서 수집된 광고 크리에이티브를 카드 형태로 조회합니다.</p>
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
        <p className="text-sm text-amber-600 mt-2">Full 플랜 전용 기능입니다.</p>
      </div>
    ),
  },
  {
    id: "advertisers",
    title: "광고주 리포트",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 광고주 리포트</p>
        <h4 className="font-semibold">목록 페이지</h4>
        <p>기업-브랜드-제품의 계층 구조(트리)로 광고주를 탐색합니다. 광고 수, 웹사이트, 산업 분류가 표시됩니다.</p>
        <h4 className="font-semibold mt-4">상세 페이지</h4>
        <p>광고주를 클릭하면 아래 정보를 확인할 수 있습니다:</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>미디어 브레이크다운:</strong> 채널별 광고 소재 분포</li>
          <li><strong>채널 분포:</strong> 매체별 비율 차트</li>
          <li><strong>경쟁사 목록:</strong> 같은 산업 내 경쟁 관계</li>
          <li><strong>메타시그널:</strong> 종합 활동 점수, 스마트스토어/트래픽/활동 세부 점수, 광고비 보정 배수</li>
          <li><strong>소셜 임팩트:</strong> 뉴스 영향, 소셜 포스팅 변화, 검색량 리프트</li>
          <li><strong>활동 추이:</strong> 일별 활동 점수 타임라인 차트</li>
        </ul>
      </div>
    ),
  },
  {
    id: "spend",
    title: "광고비 분석",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 광고비 분석</p>
        <p>채널별 광고비 요약과 광고주별 지출 랭킹을 제공합니다.</p>
        <h4 className="font-semibold mt-4">추정 방식 (4가지)</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>CPC 기반 추정:</strong> 채널별 평균 CPC/CPV x 노출 빈도에서 산출합니다. Facebook/Instagram 700원, 네이버 SA 500원, YouTube CPV 50원 등 보정된 단가를 사용합니다.</li>
          <li><strong>카탈로그 역추산:</strong> 메타 Ad Library 소재 수 x 포맷별 가중치 x 활성일수 기반으로 역추산합니다.</li>
          <li><strong>메타시그널 보정:</strong> 검색량/채널 활동/스마트스토어 데이터로 0.7~1.5x 보정 배수를 적용합니다.</li>
          <li><strong>실집행 벤치마크:</strong> 실제 미디어 집행 데이터(매체비 대비 총수주액 비율)로 캘리브레이션합니다. META 1.248, 네이버 SA 1.155, GFA 1.163, 카카오 1.182, 구글 1.183 등 채널별 변환 계수를 적용합니다.</li>
        </ul>
        <p className="text-sm text-gray-500 mt-2">기간: 7일/14일/30일 선택 가능</p>
      </div>
    ),
  },
  {
    id: "meta-signal",
    title: "메타시그널 시스템",
    content: (
      <div className="space-y-3">
        <p>메타시그널은 광고 소재 수집 외부의 다양한 신호를 종합하여 광고주의 실제 마케팅 활동 강도를 분석하는 시스템입니다. 4가지 구성요소로 이루어져 있으며, 결합 점수가 광고비 추정 보정에 활용됩니다.</p>

        <h4 className="font-semibold mt-4">1. 스마트스토어 스코어</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>네이버 스마트스토어의 상품 수, 리뷰 수, 판매량 변동을 일별로 추적합니다.</li>
          <li>신규 상품 등록, 리뷰 급증, 프로모션 감지 등을 점수화합니다.</li>
          <li>커머스 활동이 활발할수록 광고비 추정 보정 배수가 높아집니다.</li>
        </ul>

        <h4 className="font-semibold mt-4">2. 트래픽 스코어 (네이버 데이터랩 기반)</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>네이버 데이터랩 검색 트렌드에서 브랜드/키워드 검색량 변화를 분석합니다.</li>
          <li>채널별 조회수(YouTube 구독자 변동, IG 팔로워 증감)를 반영합니다.</li>
          <li>검색량 급등은 광고 집행 증가의 강한 신호로 작용합니다.</li>
        </ul>

        <h4 className="font-semibold mt-4">3. 활동 점수</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>광고 수집 빈도, 새로운 소재 등록 수, 소셜 포스팅 빈도를 종합합니다.</li>
          <li>광고주별 일일 활동 점수를 산출하고, 타임라인 차트로 추이를 시각화합니다.</li>
          <li>경쟁사 대비 활동 강도를 비교할 수 있습니다.</li>
        </ul>

        <h4 className="font-semibold mt-4">4. 패널 보정</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>크롤링 시 자동으로 기록되는 AI 패널 관찰 데이터를 수집합니다.</li>
          <li>인구통계(연령/성별) 페르소나별로 어떤 광고를 접촉했는지 기록됩니다.</li>
          <li>사용자가 직접 광고 목격 정보를 제출할 수 있는 API도 제공됩니다.</li>
          <li>AI 패널 + 사용자 제출 데이터를 결합하여 최종 보정 배수(0.7~1.5x)를 산출합니다.</li>
        </ul>

        <h4 className="font-semibold mt-4">종합 점수</h4>
        <p className="text-sm">위 4가지 구성요소가 결합되어 spend_multiplier(광고비 보정 배수)를 생성합니다. 이 배수는 CPC 기반 추정치에 곱해져 최종 광고비를 산출합니다.</p>
        <p className="text-sm text-gray-500 mt-2">광고주 상세 페이지에서 메타시그널 5개 카드(종합/스마트스토어/트래픽/활동/패널)와 활동 추이 차트를 확인할 수 있습니다.</p>
      </div>
    ),
  },
  {
    id: "smartstore",
    title: "스마트스토어 추적",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 시장 분석 &gt; 쇼핑인사이트</p>
        <p>네이버 스마트스토어의 상품 매출 변동을 추적하여 커머스 활동과 광고 집행의 상관관계를 분석합니다.</p>
        <h4 className="font-semibold mt-4">주요 기능</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li><strong>관심 상품 등록:</strong> 스마트스토어 상품 URL을 등록하면 일별 매출 변화를 자동 모니터링합니다.</li>
          <li><strong>카테고리별 분석:</strong> 상품 카테고리별 광고 분포와 광고비 상관관계를 시각화합니다.</li>
          <li><strong>프로모션 감지:</strong> 가격 변동, 할인 이벤트, 리뷰 급증 등 커머스 이벤트를 자동 감지합니다.</li>
          <li><strong>메타시그널 연동:</strong> 스마트스토어 활동 데이터가 메타시그널 스코어에 자동 반영됩니다.</li>
        </ul>
        <p className="text-sm text-gray-500 mt-2">매일 04:00 KST에 자동 수집되며, 수집 결과는 메타시그널 종합 점수에 반영됩니다.</p>
      </div>
    ),
  },
  {
    id: "panel",
    title: "패널 관찰 시스템",
    content: (
      <div className="space-y-3">
        <p>패널 관찰 시스템은 광고 접촉 데이터를 수집하여 광고비 추정의 정확도를 높이는 보조 시스템입니다.</p>
        <h4 className="font-semibold mt-4">AI 패널 (자동)</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>14개 인구통계 페르소나(12개 연령x성별 + 2개 컨트롤)로 크롤링 시 자동 기록됩니다.</li>
          <li>각 페르소나가 어떤 광고를 접촉했는지 채널/시간/디바이스별로 기록됩니다.</li>
          <li>연령대별 x 성별 히트맵으로 타겟팅 패턴을 분석할 수 있습니다.</li>
        </ul>
        <h4 className="font-semibold mt-4">사용자 제출 (수동)</h4>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>사용자가 직접 목격한 광고 정보를 제출할 수 있습니다.</li>
          <li>플랫폼, 광고주명, 소재 유형, 목격 시간 등을 입력합니다.</li>
          <li>AI 패널과 사용자 제출 데이터가 결합되어 보정 배수를 산출합니다.</li>
        </ul>
        <p className="text-sm text-gray-500 mt-2">패널 데이터는 광고주 상세 페이지의 메타시그널 섹션에서 확인할 수 있습니다.</p>
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
        <p>CPC 범위, 광고주 수 등 산업 카드 목록. 클릭하면 SOV 산점도, 파이 차트, 리더보드를 확인합니다.</p>
        <h4 className="font-semibold mt-3">제품/서비스별 (/products)</h4>
        <p>제품 카테고리 트리 구조로 광고/광고주 수를 조회합니다.</p>
        <h4 className="font-semibold mt-3">경쟁사 비교 (/competitors)</h4>
        <p>광고주 간 친화도 점수, 동시 노출 분석, 산업 내 경쟁 지형을 시각화합니다.</p>
        <h4 className="font-semibold mt-3">소셜 채널 분석 (/social-channels)</h4>
        <p>소셜 채널 KPI 요약, MoM 성장률, 광고주별 소셜 활동 랭킹, 비교 기능을 제공합니다.</p>
        <h4 className="font-semibold mt-3">광고주 트렌드 (/advertiser-trends)</h4>
        <p>상승/하락/신규/이탈 광고주 요약, 개별 광고주 활동 궤적 차트를 제공합니다.</p>
        <h4 className="font-semibold mt-3">쇼핑인사이트 (/shopping-insight)</h4>
        <p>카테고리별 쇼핑 광고 분포와 스마트스토어 매출 추적을 제공합니다. 관심 상품 URL을 등록하면 일별 매출 변화를 모니터링합니다.</p>
      </div>
    ),
  },
  {
    id: "analytics",
    title: "분석 도구",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 분석 도구 그룹</p>
        <h4 className="font-semibold">SOV 분석 (/analytics/sov)</h4>
        <p>키워드 기반 광고 점유율(Share of Voice)을 분석합니다. 수평 막대 차트로 광고주별 비율을 보고, 경쟁 SOV 추이를 추적합니다.</p>
        <h4 className="font-semibold mt-3">페르소나 접촉률 (/analytics/persona-contact)</h4>
        <p>접촉률 분석: 연령대별 x 채널별 광고 접촉 빈도, 네트워크별 광고 분포, 접촉률 기반 광고비 추정. 페르소나 랭킹: 연령 x 성별 히트맵, 페르소나별 광고주 노출 랭킹을 시각화합니다.</p>
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
          <li>광고비 분석</li>
          <li>매체 분석</li>
          <li>광고 소재 (대표 크리에이티브)</li>
          <li>소셜 소재 (Full 플랜)</li>
          <li>경쟁사 비교</li>
          <li>쇼핑인사이트</li>
        </ul>
        <p className="mt-3">기간: 7/14/30/60/90일 선택 가능. 차트와 데이터가 포함된 보고서를 PDF로 내보낼 수 있습니다.</p>
      </div>
    ),
  },
  {
    id: "snapshots",
    title: "스냅샷",
    content: (
      <div className="space-y-3">
        <p><strong>경로:</strong> 사이드바 &gt; 도구 &gt; 스냅샷</p>
        <p>네트워크 캡처를 통해 수집된 광고 원본 데이터를 조회합니다.</p>
        <ul className="list-disc list-inside space-y-1 text-sm">
          <li>채널별/디바이스별 필터링</li>
          <li>개별 스냅샷 클릭 시 해당 수집 세션의 광고 상세 목록 확인</li>
          <li>크롤링 시점, 페르소나, 키워드 등 수집 메타데이터 표시</li>
        </ul>
      </div>
    ),
  },
  {
    id: "plans",
    title: "요금제 안내",
    content: (
      <div className="space-y-3">
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 pr-4">기능</th>
                <th className="text-center py-2 px-4">Lite</th>
                <th className="text-center py-2 px-4">Full</th>
              </tr>
            </thead>
            <tbody className="text-gray-600">
              <tr className="border-b"><td className="py-2 pr-4">광고 소재 갤러리</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">소셜 소재 갤러리</td><td className="text-center text-gray-300">X</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">광고주 리포트</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">광고비 분석</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">시장 분석</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">SOV/접촉률/페르소나</td><td className="text-center text-green-600">O</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">브랜드 채널 분석</td><td className="text-center text-gray-300">X</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">소셜 채널 분석</td><td className="text-center text-gray-300">X</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">보고서 소셜 섹션</td><td className="text-center text-gray-300">X</td><td className="text-center text-green-600">O</td></tr>
              <tr className="border-b"><td className="py-2 pr-4">월 요금</td><td className="text-center font-semibold">49,000원</td><td className="text-center font-semibold">99,000원</td></tr>
              <tr><td className="py-2 pr-4">연간 요금</td><td className="text-center font-semibold">490,000원</td><td className="text-center font-semibold">990,000원</td></tr>
            </tbody>
          </table>
        </div>
        <div className="mt-4 text-center">
          <Link href="/pricing" className="text-sm text-blue-600 hover:text-blue-800 font-medium">
            가입하기 &rarr;
          </Link>
        </div>
      </div>
    ),
  },
];

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

  const expandAll = () => setOpenIds(new Set(SECTIONS.map((s) => s.id)));
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
        {SECTIONS.map((section) => (
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
