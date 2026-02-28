"use client";

import { useState } from "react";
import Link from "next/link";

export default function TermsPage() {
  const [activeTab, setActiveTab] = useState<"terms" | "privacy">("terms");

  return (
    <div className="p-6 lg:p-8 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">이용약관 및 개인정보처리방침</h1>
        <p className="text-sm text-gray-500 mt-1">
          AdScope 서비스 이용에 관한 법적 고지 사항입니다.
        </p>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        {/* Tab Header */}
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => setActiveTab("terms")}
            className={`flex-1 py-4 text-sm font-semibold transition-colors ${
              activeTab === "terms"
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            이용약관
          </button>
          <button
            onClick={() => setActiveTab("privacy")}
            className={`flex-1 py-4 text-sm font-semibold transition-colors ${
              activeTab === "privacy"
                ? "text-blue-600 border-b-2 border-blue-600 bg-blue-50/50"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            개인정보처리방침
          </button>
        </div>

        {/* Tab Content */}
        <div className="p-6 max-h-[700px] overflow-y-auto text-sm text-gray-600 leading-relaxed space-y-4">
          {activeTab === "terms" ? <TermsContent /> : <PrivacyContent />}
        </div>
      </div>

      <div className="mt-6 text-center">
        <Link href="/about" className="text-sm text-blue-600 hover:text-blue-800 font-medium">
          &larr; 서비스 소개로 돌아가기
        </Link>
      </div>
    </div>
  );
}

function TermsContent() {
  return (
    <>
      <h3 className="text-base font-bold text-gray-900">AdScope 서비스 이용약관</h3>
      <p className="text-xs text-gray-400">시행일: 2025년 1월 1일</p>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제1조 (목적)</h4>
        <p>
          본 약관은 AdScope(이하 &quot;서비스&quot;)를 제공하는 회사(이하 &quot;회사&quot;)와
          이를 이용하는 회원(이하 &quot;회원&quot;) 간의 권리, 의무 및 책임사항을 규정함을
          목적으로 합니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제2조 (정의)</h4>
        <p>
          1. &quot;서비스&quot;란 회사가 제공하는 디지털 광고 모니터링 및 분석 플랫폼을 말합니다.
          <br />
          2. &quot;회원&quot;이란 본 약관에 동의하고 회사와 이용계약을 체결한 자를 말합니다.
          <br />
          3. &quot;유료 서비스&quot;란 회사가 유료로 제공하는 Lite, Full 등의 요금제를 말합니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제3조 (약관의 효력 및 변경)</h4>
        <p>
          1. 본 약관은 서비스 화면에 게시하거나 기타 방법으로 회원에게 공지함으로써 효력을
          발생합니다.
          <br />
          2. 회사는 관련 법령에 위배되지 않는 범위 내에서 약관을 변경할 수 있으며, 변경 시
          시행일 7일 전부터 서비스 내 공지합니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제4조 (이용계약의 체결)</h4>
        <p>
          1. 이용계약은 회원이 약관에 동의하고 회원가입을 완료함으로써 체결됩니다.
          <br />
          2. 회사는 다음 각 호에 해당하는 경우 가입을 제한할 수 있습니다.
          <br />
          &nbsp;&nbsp;- 타인의 정보를 사용한 경우
          <br />
          &nbsp;&nbsp;- 허위 정보를 기재한 경우
          <br />
          &nbsp;&nbsp;- 기타 회사가 정한 요건을 충족하지 못한 경우
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제5조 (서비스의 제공 및 변경)</h4>
        <p>
          1. 회사는 회원에게 광고 소재 수집, 광고비 분석, 경쟁사 비교 등의 서비스를 제공합니다.
          <br />
          2. 서비스의 내용은 회원의 요금제에 따라 차등 제공됩니다.
          <br />
          3. 회사는 운영상, 기술상의 필요에 의해 서비스 내용을 변경할 수 있습니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제6조 (요금 및 결제)</h4>
        <p>
          1. 유료 서비스의 요금은 서비스 내 요금제 페이지에 게시된 바에 따릅니다.
          <br />
          2. 회원은 선택한 요금제에 따라 월간 또는 연간 단위로 요금을 결제합니다.
          <br />
          3. 결제 취소 및 환불은 관련 법령 및 회사 정책에 따릅니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제7조 (회원의 의무)</h4>
        <p>
          1. 회원은 서비스를 통해 수집된 데이터를 제3자에게 무단으로 제공하거나 상업적으로
          재판매할 수 없습니다.
          <br />
          2. 회원은 서비스 이용 시 관련 법령과 본 약관을 준수해야 합니다.
          <br />
          3. 계정의 관리 책임은 회원에게 있으며, 동시 접속은 제한됩니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제8조 (면책조항)</h4>
        <p>
          1. 회사는 천재지변, 전쟁, 기간통신사업자의 서비스 중지 등 불가항력으로 인한 서비스
          중단에 대해 책임을 지지 않습니다.
          <br />
          2. 수집된 광고 데이터의 정확성 및 완전성에 대해 회사는 보증하지 않으며, 이를 기반으로
          한 의사결정에 대한 책임은 회원에게 있습니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제9조 (계약 해지)</h4>
        <p>
          1. 회원은 언제든지 서비스 내 설정 또는 고객센터를 통해 이용계약 해지를 신청할 수
          있습니다.
          <br />
          2. 회사는 회원이 본 약관을 위반한 경우 사전 통지 후 이용계약을 해지할 수 있습니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">제10조 (분쟁 해결)</h4>
        <p>
          본 약관과 관련된 분쟁은 대한민국 법령에 따르며, 관할 법원은 회사의 본점 소재지를
          관할하는 법원으로 합니다.
        </p>
      </div>
    </>
  );
}

function PrivacyContent() {
  return (
    <>
      <h3 className="text-base font-bold text-gray-900">AdScope 개인정보처리방침</h3>
      <p className="text-xs text-gray-400">시행일: 2025년 1월 1일</p>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">1. 개인정보의 수집 항목 및 수집 방법</h4>
        <p>
          회사는 서비스 제공을 위해 다음과 같은 개인정보를 수집합니다.
          <br />
          <br />
          <strong>필수 수집 항목:</strong> 이메일 주소, 비밀번호, 회사명, 담당자명, 연락처
          <br />
          <strong>자동 수집 항목:</strong> 접속 IP, 접속 일시, 브라우저 정보, 디바이스 핑거프린트
          <br />
          <strong>수집 방법:</strong> 회원가입 시 직접 입력, 서비스 이용 과정에서 자동 생성
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">2. 개인정보의 수집 및 이용 목적</h4>
        <p>
          - 회원 식별 및 서비스 제공
          <br />
          - 요금 결제 및 정산
          <br />
          - 서비스 이용 통계 및 분석
          <br />
          - 고객 문의 응대 및 불만 처리
          <br />
          - 부정 이용 방지 및 동시 접속 관리
          <br />
          - 신규 서비스 개발 및 마케팅 정보 제공 (동의 시)
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">3. 개인정보의 보유 및 이용 기간</h4>
        <p>
          회원 탈퇴 시까지 보유하며, 탈퇴 후 지체 없이 파기합니다. 단, 관련 법령에 의해 보존이
          필요한 경우 해당 기간 동안 보관합니다.
          <br />
          <br />
          - 계약 또는 청약철회에 관한 기록: 5년
          <br />
          - 대금결제 및 재화 등의 공급에 관한 기록: 5년
          <br />
          - 소비자의 불만 또는 분쟁처리에 관한 기록: 3년
          <br />
          - 접속에 관한 기록: 3개월
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">4. 개인정보의 제3자 제공</h4>
        <p>
          회사는 원칙적으로 회원의 개인정보를 제3자에게 제공하지 않습니다. 다만, 다음의 경우에는
          예외로 합니다.
          <br />
          <br />
          - 회원이 사전에 동의한 경우
          <br />
          - 법령의 규정에 의한 경우
          <br />
          - 수사 목적으로 법령에 정해진 절차에 따라 요청이 있는 경우
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">5. 개인정보의 파기 절차 및 방법</h4>
        <p>
          회원 탈퇴 또는 보유 기간 경과 시 전자적 파일 형태의 정보는 복구할 수 없는 방법으로
          영구 삭제하며, 종이에 출력된 개인정보는 분쇄기로 분쇄하거나 소각하여 파기합니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">6. 개인정보 보호를 위한 기술적 대책</h4>
        <p>
          - 비밀번호 암호화 저장 (bcrypt)
          <br />
          - SSL/TLS를 통한 통신 암호화
          <br />
          - 동시 접속 차단 및 디바이스 핑거프린트 기반 보안
          <br />
          - 접근 권한 관리 및 접속 기록 보관
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">7. 이용자의 권리</h4>
        <p>
          회원은 언제든지 자신의 개인정보를 조회하거나 수정할 수 있으며, 가입 해지를 통해
          개인정보의 삭제를 요청할 수 있습니다.
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">8. 개인정보보호 책임자</h4>
        <p>
          개인정보 관련 문의사항은 아래로 연락해 주시기 바랍니다.
          <br />
          <br />
          이메일: privacy@adscope.kr
          <br />
          고객센터: support@adscope.kr
        </p>
      </div>

      <div>
        <h4 className="font-semibold text-gray-800 mb-1">9. 개인정보처리방침의 변경</h4>
        <p>
          본 방침은 시행일로부터 적용되며, 변경 사항이 있을 경우 시행일 7일 전부터 서비스 내
          공지사항을 통해 고지합니다.
        </p>
      </div>
    </>
  );
}
