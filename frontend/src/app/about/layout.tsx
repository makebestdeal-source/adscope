import { Metadata } from "next";

export const metadata: Metadata = {
  title: "서비스 소개 - 9개 채널 광고 인텔리전스",
  description:
    "AdScope는 네이버, 구글, 유튜브, 메타, 카카오, 틱톡 등 9개 디지털 광고 채널의 소재, 집행 현황, 광고비를 통합 모니터링하는 광고 인텔리전스 플랫폼입니다.",
  alternates: { canonical: "https://adscope.kr/about" },
  openGraph: {
    title: "AdScope 서비스 소개",
    description:
      "9개 디지털 광고 채널 통합 모니터링. 경쟁사 광고 전략을 한눈에 파악하세요.",
    url: "https://adscope.kr/about",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
