/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  skipTrailingSlashRedirect: true,

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
