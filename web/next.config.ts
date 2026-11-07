import type { NextConfig } from 'next';
const config: NextConfig = {
  distDir: process.env.LEDGERCREW_NEXT_DIST || '.next',
  compress: false, // Preserve incremental SSE frames through the same-origin proxy.
  devIndicators: false, trailingSlash: true, images: { unoptimized: true },
  // Dev-only cross-origin guard: Next refuses to serve /_next dev assets to a
  // hostname other than the one it started on, so a tunnel shows the page with
  // every script/CSS blocked (403). List tunnel hostnames here — hostnames
  // only, no scheme or port; `*` matches one label, `**` one or more. Add more
  // comma-separated via LEDGERCREW_ALLOWED_DEV_ORIGINS (e.g. "myhost.example.com").
  allowedDevOrigins: [
    'cnb.cool', '*.cnb.cool', '**.cnb.cool',
    ...(process.env.LEDGERCREW_ALLOWED_DEV_ORIGINS || '')
      .split(',').map((origin) => origin.trim()).filter(Boolean),
  ],
  async redirects() {
    return [
      { source: '/owner/index.html', destination: '/owner/', permanent: false },
      { source: '/owner/dashboard.html', destination: '/owner/dashboard/', permanent: false },
      { source: '/workspace/index.html', destination: '/owner/', permanent: false },
      { source: '/workspace/dashboard.html', destination: '/owner/dashboard/', permanent: false },
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
