export type BillingCycle = "monthly" | "yearly";
export type PlanId = "lite" | "full" | "enterprise";

type UsageValue = number | "custom";

export interface PlanPolicy {
  id: PlanId;
  name: string;
  audience: string;
  description: string;
  monthly: number | null;
  yearly: number | null;
  originalMonthly?: number;
  originalYearly?: number;
  checkoutEnabled: boolean;
  badge?: string;
  usage: {
    users: UsageValue;
    trackedAdvertisers: UsageValue;
    reportExports: UsageValue;
    creativeDownloads: UsageValue;
    apiCalls: UsageValue;
    historyMonths: UsageValue;
  };
  features: string[];
  excluded?: string[];
  paymentNote: string;
}

export const PLAN_CATALOG: Record<PlanId, PlanPolicy> = {
  lite: {
    id: "lite",
    name: "Lite",
    audience: "소규모 마케터 / 단일 광고주",
    description: "광고주와 캠페인을 가볍게 모니터링하는 입문형 플랜",
    originalMonthly: 79000,
    originalYearly: 790000,
    monthly: 49000,
    yearly: 490000,
    checkoutEnabled: true,
    usage: {
      users: 1,
      trackedAdvertisers: 30,
      reportExports: 20,
      creativeDownloads: 100,
      apiCalls: 0,
      historyMonths: 12,
    },
    features: [
      "국내 주요 디지털 광고 소재 열람",
      "광고주별 캠페인/소재/랜딩 모니터링",
      "광고비 추정 및 경쟁사 비교",
      "키워드/시장 분석",
      "PDF/CSV 리포트 생성",
    ],
    excluded: ["소셜 소재/채널 심화 분석", "대량 API/Export", "전담 보강 요청"],
    paymentNote: "카드 또는 PayPal 온라인 결제",
  },
  full: {
    id: "full",
    name: "Full",
    audience: "대행사 / 미디어렙 / 다중 광고주",
    description: "광고와 소셜 신호를 함께 보는 실무형 플랜",
    originalMonthly: 149000,
    originalYearly: 1490000,
    monthly: 99000,
    yearly: 990000,
    checkoutEnabled: true,
    badge: "추천",
    usage: {
      users: 3,
      trackedAdvertisers: 150,
      reportExports: 100,
      creativeDownloads: 1000,
      apiCalls: 0,
      historyMonths: 24,
    },
    features: [
      "Lite 전체 기능",
      "소셜 소재 갤러리 및 소셜 인사이트",
      "브랜드 채널/버즈/캠페인 효과 분석",
      "다중 광고주 비교 리포트",
      "우선 데이터 보강 요청",
    ],
    paymentNote: "카드 또는 PayPal 온라인 결제",
  },
  enterprise: {
    id: "enterprise",
    name: "Enterprise",
    audience: "대형 대행사 / 미디어렙 / 브랜드 본사",
    description: "계정 수, API, 광고주 커버리지, 정산 방식을 맞춤 설계",
    monthly: null,
    yearly: null,
    checkoutEnabled: false,
    badge: "맞춤",
    usage: {
      users: "custom",
      trackedAdvertisers: "custom",
      reportExports: "custom",
      creativeDownloads: "custom",
      apiCalls: "custom",
      historyMonths: "custom",
    },
    features: [
      "맞춤 광고주/업종 커버리지 보강",
      "전용 API 및 대량 Export",
      "팀 계정과 권한 관리",
      "세금계산서/계약서/월 정산",
      "전담 온보딩 및 SLA 협의",
    ],
    paymentNote: "견적서 발행 후 세금계산서/계좌이체",
  },
};

export const BILLABLE_PLAN_IDS: Array<Exclude<PlanId, "enterprise">> = ["lite", "full"];

export function formatKrw(value: number) {
  return value.toLocaleString("ko-KR");
}

export function usageLabel(value: UsageValue, suffix = "") {
  if (value === "custom") return "협의";
  return `${formatKrw(value)}${suffix}`;
}

export function priceFor(planId: PlanId, cycle: BillingCycle) {
  const plan = PLAN_CATALOG[planId];
  return cycle === "monthly" ? plan.monthly : plan.yearly;
}
