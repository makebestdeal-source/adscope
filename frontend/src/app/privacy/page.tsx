export default function PrivacyPage() {
  return (
    <div className="p-6 lg:p-8 max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">개인정보처리방침</h1>
      <div className="prose prose-slate max-w-none space-y-6 text-sm leading-relaxed text-gray-700">

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">1. 개인정보의 수집 및 이용 목적</h2>
          <p>AdScope(이하 &quot;서비스&quot;)는 다음의 목적으로 개인정보를 수집 및 이용합니다.</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li>회원가입 및 서비스 이용 계정 관리</li>
            <li>서비스 제공 및 맞춤형 콘텐츠 제공</li>
            <li>요금 결제 및 정산</li>
            <li>서비스 개선 및 통계 분석</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">2. 수집하는 개인정보 항목</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li><strong>필수:</strong> 이메일, 비밀번호, 이름, 회사명, 연락처</li>
            <li><strong>자동 수집:</strong> 접속 IP, 기기 정보, 브라우저 종류, 서비스 이용 기록</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">3. 개인정보의 보유 및 이용기간</h2>
          <p>회원 탈퇴 시까지 보유하며, 관계 법령에 따라 보존이 필요한 경우 해당 기간 동안 보관합니다.</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li>계약 또는 청약철회 등에 관한 기록: 5년</li>
            <li>대금결제 및 재화 등의 공급에 관한 기록: 5년</li>
            <li>소비자 불만 또는 분쟁 처리에 관한 기록: 3년</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">4. 개인정보의 제3자 제공</h2>
          <p>서비스는 원칙적으로 이용자의 개인정보를 제3자에게 제공하지 않습니다. 다만, 다음의 경우에는 예외로 합니다.</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li>이용자가 사전에 동의한 경우</li>
            <li>법령의 규정에 의거하거나, 수사 목적으로 법령에 정해진 절차와 방법에 따라 수사기관의 요구가 있는 경우</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">5. 개인정보의 파기</h2>
          <p>보유기간이 경과하거나 처리 목적이 달성된 경우, 해당 개인정보를 지체없이 파기합니다.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">6. 이용자의 권리</h2>
          <p>이용자는 언제든지 자신의 개인정보에 대해 열람, 수정, 삭제, 처리정지를 요청할 수 있습니다.</p>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">7. 개인정보 보호책임자</h2>
          <ul className="list-disc pl-5 space-y-1">
            <li>담당자: AdScope 개인정보보호팀</li>
            <li>이메일: privacy@adscope.kr</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">8. 데이터 보안</h2>
          <p>서비스는 개인정보의 안전성 확보를 위해 다음과 같은 조치를 취하고 있습니다.</p>
          <ul className="list-disc pl-5 space-y-1 mt-2">
            <li>전송 구간 암호화 (HTTPS/TLS)</li>
            <li>비밀번호 암호화 저장</li>
            <li>동시접속 제한 및 디바이스 핑거프린트 기반 보안</li>
            <li>접근 권한 제한 및 로그 관리</li>
          </ul>
        </section>

        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-2">9. 데이터 삭제 요청</h2>
          <p>이용자는 privacy@adscope.kr로 이메일을 보내 자신의 계정 및 모든 관련 데이터의 삭제를 요청할 수 있습니다. 요청 접수 후 30일 이내에 처리됩니다.</p>
        </section>

        <p className="text-xs text-gray-400 pt-4 border-t">
          시행일: 2026년 2월 18일 | 최종 수정: 2026년 2월 18일
        </p>
      </div>
    </div>
  );
}
