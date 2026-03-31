import type { Metadata, Viewport } from 'next';
import ClientProviders from '@/components/ClientProviders';
import './globals.css';

export const metadata: Metadata = {
  title: 'JINXUS',
  description: 'Autonomous Multi-Agent System',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  // maximumScale/userScalable 제거 — WCAG 2.1 SC 1.4.4 위반 방지 (줌 차단 금지)
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <head>
        {/* 마스코트 이미지 선제 로드 — 채팅 화면 즉시 표시 */}
        <link rel="preload" href="/jinxus-mascot.webp" as="image" type="image/webp" />
        {/* Google Fonts FOIT 방지 — preconnect + font-display: swap */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="min-h-dvh bg-dark-bg text-white">
        {/* Skip link — 키보드/스크린리더 사용자가 네비게이션 건너뛰기 */}
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:px-4 focus:py-2 focus:bg-primary focus:text-black focus:rounded-lg focus:text-sm focus:font-medium"
        >
          본문으로 건너뛰기
        </a>
        {children}
        <ClientProviders />
      </body>
    </html>
  );
}
