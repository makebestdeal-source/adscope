import { Metadata } from "next";

export const metadata: Metadata = {
  title: "이용약관",
  description:
    "AdScope 이용약관. 서비스 이용 조건, 계정, 결제, 데이터 이용 범위와 책임 기준을 안내합니다.",
  alternates: { canonical: "https://adscope.kr/terms" },
  openGraph: {
    title: "AdScope 이용약관",
    description:
      "AdScope 서비스 이용 조건과 회원의 권리 및 의무를 안내합니다.",
    url: "https://adscope.kr/terms",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
