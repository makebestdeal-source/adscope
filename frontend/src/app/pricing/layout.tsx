import { Metadata } from "next";

export const metadata: Metadata = {
  title: "요금제 - Lite / Full 플랜 비교",
  description:
    "AdScope 요금제 안내. Lite 플랜과 Full 플랜의 기능 비교, 무료 체험으로 광고 모니터링을 시작하세요.",
  alternates: { canonical: "https://adscope.kr/pricing" },
  openGraph: {
    title: "AdScope 요금제",
    description: "Lite / Full 플랜 비교. 무료 체험으로 시작하세요.",
    url: "https://adscope.kr/pricing",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
