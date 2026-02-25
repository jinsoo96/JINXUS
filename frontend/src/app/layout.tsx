import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'JINXUS - AI 비서',
  description: '주인님을 모시는 충실한 AI 비서 시스템',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-dark-bg text-white">
        {children}
      </body>
    </html>
  );
}
