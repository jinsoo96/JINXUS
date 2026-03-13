/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
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
          { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
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
    ];
  },
};

module.exports = nextConfig;
