import type { Metadata, Viewport } from "next";
import dynamic from "next/dynamic";
import "./globals.css";
import { Providers } from "./providers";
import { AppShell } from "@/components/AppShell";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";
import { SessionTimeout } from "@/components/SessionTimeout";

const ContentProtection = dynamic(
  () => import("@/components/ContentProtection"),
  { ssr: false }
);

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: "#0f172a",
};

export const metadata: Metadata = {
  title: "AdScope - Ad Intelligence Platform",
  description: "한국 디지털 광고 통합 모니터링 인텔리전스 플랫폼",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AdScope",
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <head>
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
      </head>
      <body suppressHydrationWarning>
        <Providers>
          <ErrorBoundary>
            <ServiceWorkerRegister />
            <AppShell>{children}</AppShell>
            <SessionTimeout />
            <ContentProtection />
          </ErrorBoundary>
        </Providers>
      </body>
    </html>
  );
}
