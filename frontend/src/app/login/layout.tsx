import { Metadata } from "next";

export const metadata: Metadata = {
  title: "로그인",
  robots: {
    index: false,
    follow: false,
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
