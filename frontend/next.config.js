/** @type {import('next').NextConfig} */
const nextConfig = {
  // dev 서버에 접근 허용할 외부 오리진 (Tailscale, 커스텀 도메인)
  allowedDevOrigins: [
    'jinxus.js-96.com',
    '100.75.83.105',
    '192.168.0.102',
  ],
  async headers() {
    return [
      {
        source: '/((?!_next/static|_next/image).*)',
        headers: [
          { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
          { key: 'Pragma', value: 'no-cache' },
          { key: 'Expires', value: '0' },
        ],
      },
      {
        source: '/_next/static/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
      {
        source: '/api/:path*',
        headers: [
          { key: 'Cache-Control', value: 'no-store, no-cache, must-revalidate, max-age=0' },
        ],
      },
    ];
  },
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:19000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/:path*`,
      },
      {
        source: '/_matrix/:path*',
        destination: 'http://localhost:8008/_matrix/:path*',
      },
    ];
  },
};

module.exports = nextConfig;
