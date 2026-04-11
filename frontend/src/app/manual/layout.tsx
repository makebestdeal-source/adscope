import { Metadata } from "next";

export const metadata: Metadata = {
  title: "이용 매뉴얼 - 사용법 안내",
  description:
    "AdScope 이용 매뉴얼. 대시보드, 광고주 분석, 캠페인 추적, 보고서 다운로드 등 상세 사용법을 안내합니다.",
  alternates: { canonical: "https://adscope.kr/manual" },
  openGraph: {
    title: "AdScope 이용 매뉴얼",
    description: "광고 인텔리전스 플랫폼 상세 사용법 안내.",
    url: "https://adscope.kr/manual",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
