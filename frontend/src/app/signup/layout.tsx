import { Metadata } from "next";

export const metadata: Metadata = {
  title: "회원가입",
  robots: {
    index: false,
    follow: false,
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
