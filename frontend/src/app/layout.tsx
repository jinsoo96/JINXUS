import type { Metadata } from 'next';
import { Toaster } from 'react-hot-toast';
import './globals.css';

export const metadata: Metadata = {
  title: 'JINXUS - AI 비서',
  description: 'Graph-based Autonomous Agent System',
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
        <Toaster
          position="top-right"
          toastOptions={{
            style: { background: '#27272a', color: '#fff', border: '1px solid #3f3f46' },
            error: { iconTheme: { primary: '#ef4444', secondary: '#fff' } },
            success: { iconTheme: { primary: '#22c55e', secondary: '#fff' } },
          }}
        />
      </body>
    </html>
  );
}
