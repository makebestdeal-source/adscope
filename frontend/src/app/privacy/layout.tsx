import { Metadata } from "next";

export const metadata: Metadata = {
  title: "개인정보처리방침",
  description:
    "AdScope 개인정보처리방침. 서비스 이용 과정에서 처리되는 개인정보 항목, 보관 기간, 이용 목적을 안내합니다.",
  alternates: { canonical: "https://adscope.kr/privacy" },
  openGraph: {
    title: "AdScope 개인정보처리방침",
    description:
      "AdScope 서비스의 개인정보 처리 기준과 이용자 권리를 안내합니다.",
    url: "https://adscope.kr/privacy",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
