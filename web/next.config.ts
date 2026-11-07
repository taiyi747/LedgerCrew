import type { NextConfig } from 'next';
const config: NextConfig = {
  distDir: process.env.LEDGERCREW_NEXT_DIST || '.next',
  compress: false, // Preserve incremental SSE frames through the same-origin proxy.
  devIndicators: false, trailingSlash: true, images: { unoptimized: true },
  async redirects() {
    return [
      { source: '/owner/index.html', destination: '/owner/', permanent: false },
      { source: '/owner/dashboard.html', destination: '/owner/dashboard/', permanent: false },
    ];
  },
  async rewrites() {
    const backend = process.env.LEDGERCREW_API_ORIGIN || 'http://127.0.0.1:8000';
    return [
      { source: '/api/:path*', destination: `${backend}/api/:path*` },
    ];
  },
};
export default config;
