import { Metadata } from "next";

export const metadata: Metadata = {
  title: "서비스 가이드 - 주요 기능 안내",
  description:
    "AdScope 서비스 가이드. 광고 소재 갤러리, 광고비 분석, 경쟁사 비교, SOV 분석 등 주요 기능의 활용법을 안내합니다.",
  alternates: { canonical: "https://adscope.kr/guide" },
  openGraph: {
    title: "AdScope 서비스 가이드",
    description: "광고 모니터링 플랫폼의 주요 기능 활용법을 안내합니다.",
    url: "https://adscope.kr/guide",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
