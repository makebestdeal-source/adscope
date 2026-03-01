/** AdScope 공용 상수 및 유틸리티. */

export const CHANNEL_LABELS: Record<string, string> = {
  naver_search: "네이버 검색",
  naver_da: "네이버 DA",
  google_gdn: "Google GDN",
  youtube_ads: "유튜브",
  youtube_surf: "유튜브",
  kakao_da: "카카오 DA",
  meta: "Meta",
  naver_shopping: "네이버 쇼핑",
  google_search_ads: "Google 검색",
  tiktok_ads: "TikTok",
};

export const CHANNEL_COLORS: Record<string, string> = {
  naver_search: "#03C75A",
  naver_da: "#1EC800",
  google_gdn: "#4285F4",
  youtube_ads: "#FF0000",
  youtube_surf: "#FF4444",
  kakao_da: "#FEE500",
  meta: "#0081FB",
  naver_shopping: "#03C75A",
  google_search_ads: "#4285F4",
  tiktok_ads: "#010101",
};

export const CHANNEL_BADGE_COLORS: Record<string, string> = {
  naver_search: "bg-green-100 text-green-800",
  naver_da: "bg-green-50 text-green-700",
  google_gdn: "bg-blue-100 text-blue-800",
  youtube_ads: "bg-red-100 text-red-800",
  youtube_surf: "bg-red-50 text-red-700",
  kakao_da: "bg-yellow-100 text-yellow-800",
  meta: "bg-blue-100 text-blue-700",
  naver_shopping: "bg-green-100 text-green-700",
  google_search_ads: "bg-blue-50 text-blue-700",
  tiktok_ads: "bg-gray-100 text-gray-800",
};

export const AGE_GROUPS = ["10대", "20대", "30대", "40대", "50대", "60대"] as const;

export const PERIOD_OPTIONS = [
  { label: "7일", value: 7 },
  { label: "14일", value: 14 },
  { label: "30일", value: 30 },
] as const;

export function formatChannel(channel: string): string {
  return CHANNEL_LABELS[channel] ?? channel;
}

export function formatSpend(amount: number): string {
  if (amount >= 100_000_000) {
    return `약 ${(amount / 100_000_000).toFixed(1)}억원`;
  }
  if (amount >= 10_000) {
    return `약 ${Math.round(amount / 10_000).toLocaleString()}만원`;
  }
  if (amount > 0) {
    return `약 ${amount.toLocaleString()}원`;
  }
  return "0원";
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatRevenue(amount: number): string {
  if (amount >= 1_000_000_000_000) {
    return `${(amount / 1_000_000_000_000).toFixed(1)}조원`;
  }
  if (amount >= 100_000_000) {
    return `${(amount / 100_000_000).toFixed(0)}억원`;
  }
  if (amount >= 10_000) {
    return `${(amount / 10_000).toFixed(0)}만원`;
  }
  return `${amount.toLocaleString()}원`;
}

export const INDUSTRIES: Record<number, string> = {
  1: "기타",
  2: "IT/통신",
  3: "자동차",
  4: "금융/보험",
  5: "식품/음료",
  6: "뷰티/화장품",
  7: "패션/의류",
  8: "유통/이커머스",
  9: "제약/헬스케어",
  10: "가전/전자",
  11: "건설/부동산",
  12: "게임",
  13: "엔터테인먼트",
  14: "여행/항공",
  15: "교육",
  16: "스포츠/아웃도어",
  17: "가구/인테리어",
  18: "주류",
  19: "공공기관",
  20: "반려동물",
};

export const INDUSTRY_COLORS: Record<number, string> = {
  1: "#94A3B8",
  2: "#06B6D4",
  3: "#64748B",
  4: "#3B82F6",
  5: "#F97316",
  6: "#EC4899",
  7: "#8B5CF6",
  8: "#10B981",
  9: "#14B8A6",
  10: "#6366F1",
  11: "#F59E0B",
  12: "#EF4444",
  13: "#A855F7",
  14: "#0EA5E9",
  15: "#84CC16",
  16: "#22C55E",
  17: "#D97706",
  18: "#DC2626",
  19: "#2563EB",
  20: "#FB923C",
};

export const AFFINITY_COLORS = {
  high: "#10b981",
  medium: "#f59e0b",
  low: "#ef4444",
};

export const PERSONA_CODES = [
  "M10", "F10", "M20", "F20", "M30", "F30",
  "M40", "F40", "M50", "F50", "M60", "F60",
  "CTRL_CLEAN", "CTRL_RETARGET",
] as const;

export const PERSONA_LABELS: Record<string, string> = {
  M10: "10대 남성", F10: "10대 여성",
  M20: "20대 남성", F20: "20대 여성",
  M30: "30대 남성", F30: "30대 여성",
  M40: "40대 남성", F40: "40대 여성",
  M50: "50대 남성", F50: "50대 여성",
  M60: "60대 남성", F60: "60대 여성",
  CTRL_CLEAN: "Clean Control",
  CTRL_RETARGET: "Retarget Control",
};

export const HEATMAP_COLORS = [
  "bg-blue-50", "bg-blue-100", "bg-blue-200", "bg-blue-300",
  "bg-blue-400", "bg-blue-500", "bg-blue-600", "bg-blue-700",
];
