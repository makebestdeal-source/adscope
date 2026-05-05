import { Metadata } from "next";

export const metadata: Metadata = {
  title: "비밀번호 재설정",
  robots: {
    index: false,
    follow: false,
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
