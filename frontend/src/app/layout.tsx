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

const siteDescription =
  "AdScope는 네이버, 구글, 유튜브, 메타, 카카오 등 국내 주요 디지털 광고 채널의 광고 소재, 집행 현황, 광고비를 통합 모니터링하는 광고 인텔리전스 플랫폼입니다.";

const structuredData = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      name: "AdScope",
      legalName: "더블이스튜디오",
      url: "https://adscope.kr",
      logo: "https://adscope.kr/apple-touch-icon.png",
      description: siteDescription,
      parentOrganization: {
        "@type": "Organization",
        name: "DoubleE Studio",
        url: "https://doubleestudio.com",
      },
      address: {
        "@type": "PostalAddress",
        addressCountry: "KR",
      },
      contactPoint: {
        "@type": "ContactPoint",
        email: "support@adscope.kr",
        contactType: "customer service",
        availableLanguage: "Korean",
      },
      sameAs: ["https://doubleestudio.com"],
    },
    {
      "@type": "WebSite",
      name: "AdScope",
      url: "https://adscope.kr",
      description: siteDescription,
      inLanguage: "ko-KR",
    },
    {
      "@type": "SoftwareApplication",
      name: "AdScope",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      url: "https://adscope.kr",
      description: "국내 주요 디지털 광고 채널을 통합 모니터링하는 광고 인텔리전스 플랫폼",
      offers: {
        "@type": "AggregateOffer",
        priceCurrency: "KRW",
        availability: "https://schema.org/InStock",
      },
    },
  ],
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  userScalable: true,
  themeColor: "#0f172a",
};

export const metadata: Metadata = {
  title: {
    default: "AdScope | 광고 인텔리전스 플랫폼",
    template: "%s | AdScope",
  },
  description: siteDescription,
  keywords: [
    "광고 모니터링",
    "경쟁사 광고 분석",
    "디지털 광고비",
    "광고 인텔리전스",
    "SOV 분석",
    "네이버 광고",
    "구글 광고",
    "메타 광고",
    "유튜브 광고",
    "광고 소재 갤러리",
  ],
  applicationName: "AdScope",
  manifest: "/manifest.json",
  metadataBase: new URL("https://adscope.kr"),
  alternates: {
    canonical: "https://adscope.kr",
  },
  openGraph: {
    title: "AdScope | 광고 인텔리전스 플랫폼",
    description: siteDescription,
    url: "https://adscope.kr",
    siteName: "AdScope",
    locale: "ko_KR",
    type: "website",
    images: [
      {
        url: "https://adscope.kr/icons/icon-512x512.png",
        width: 512,
        height: 512,
        alt: "AdScope 광고 인텔리전스 플랫폼",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "AdScope | 광고 인텔리전스 플랫폼",
    description: siteDescription,
    images: ["https://adscope.kr/icons/icon-512x512.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AdScope",
  },
  other: {
    "mobile-web-app-capable": "yes",
    ...(process.env.NEXT_PUBLIC_NAVER_VERIFICATION
      ? { "naver-site-verification": process.env.NEXT_PUBLIC_NAVER_VERIFICATION }
      : {}),
    ...(process.env.NEXT_PUBLIC_GOOGLE_VERIFICATION
      ? { "google-site-verification": process.env.NEXT_PUBLIC_GOOGLE_VERIFICATION }
      : {}),
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
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(structuredData),
          }}
        />
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
