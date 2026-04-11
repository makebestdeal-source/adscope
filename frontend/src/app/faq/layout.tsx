import { Metadata } from "next";

export const metadata: Metadata = {
  title: "FAQ - 자주 묻는 질문",
  description:
    "AdScope 자주 묻는 질문. 서비스 이용, 요금제, 데이터 수집 방식, 광고비 추정 방법 등에 대한 답변을 확인하세요.",
  alternates: { canonical: "https://adscope.kr/faq" },
  openGraph: {
    title: "AdScope FAQ",
    description: "서비스 이용, 요금제, 데이터 수집 등 자주 묻는 질문과 답변.",
    url: "https://adscope.kr/faq",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
