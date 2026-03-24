import type { Metadata } from 'next';
import ClientProviders from '@/components/ClientProviders';
import './globals.css';

export const metadata: Metadata = {
  title: 'JINXUS',
  description: 'Autonomous Multi-Agent System',
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
      </head>
      <body className="min-h-screen bg-dark-bg text-white">
        {children}
        <ClientProviders />
      </body>
    </html>
  );
}
