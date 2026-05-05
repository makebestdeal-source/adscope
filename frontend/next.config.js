/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  skipTrailingSlashRedirect: true,

  async redirects() {
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: "www.adscope.kr" }],
        destination: "https://adscope.kr/:path*",
        permanent: true,
      },
    ];
  },

  async headers() {
    const noIndex = [
      {
        key: "X-Robots-Tag",
        value: "noindex, nofollow, noarchive, nosnippet, noimageindex",
      },
    ];
    return [
      { source: "/api/:path*", headers: noIndex },
      { source: "/images/:path*", headers: noIndex },
      { source: "/screenshots/:path*", headers: noIndex },
      { source: "/admin/:path*", headers: noIndex },
      { source: "/settings/:path*", headers: noIndex },
      { source: "/reports/:path*", headers: noIndex },
      { source: "/advertisers/:path*", headers: noIndex },
      { source: "/campaigns/:path*", headers: noIndex },
      { source: "/gallery/:path*", headers: noIndex },
      { source: "/analytics/:path*", headers: noIndex },
      { source: "/keyword-analysis/:path*", headers: noIndex },
      { source: "/shopping-insight/:path*", headers: noIndex },
      { source: "/shopping-keyword/:path*", headers: noIndex },
      { source: "/shopping-ranking/:path*", headers: noIndex },
      { source: "/shopping-sales/:path*", headers: noIndex },
      { source: "/social-gallery/:path*", headers: noIndex },
      { source: "/social-content/:path*", headers: noIndex },
      { source: "/social-channels/:path*", headers: noIndex },
      { source: "/competitors/:path*", headers: noIndex },
      { source: "/industries/:path*", headers: noIndex },
      { source: "/products/:path*", headers: noIndex },
      { source: "/master-index/:path*", headers: noIndex },
      { source: "/spend/:path*", headers: noIndex },
      { source: "/buzz-dashboard/:path*", headers: noIndex },
      { source: "/target-audience/:path*", headers: noIndex },
      { source: "/consumer-insights/:path*", headers: noIndex },
      { source: "/launch-impact/:path*", headers: noIndex },
      { source: "/marketing-schedule/:path*", headers: noIndex },
      { source: "/campaign-effect/:path*", headers: noIndex },
      { source: "/advertiser-trends/:path*", headers: noIndex },
      { source: "/payment/:path*", headers: noIndex },
      { source: "/login", headers: noIndex },
      { source: "/signup", headers: noIndex },
      { source: "/forgot-password", headers: noIndex },
    ];
  },

  async rewrites() {
    const apiUrl = process.env.API_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
      {
        source: "/images/:path*",
        destination: `${apiUrl}/images/:path*`,
      },
      {
        source: "/screenshots/:path*",
        destination: `${apiUrl}/screenshots/:path*`,
      },
    ];
  },

  // Production optimizations
  poweredByHeader: false,
  compress: true,

  // Image optimization
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**" },
    ],
    unoptimized: true, // stored_images are local
  },
};

module.exports = nextConfig;
