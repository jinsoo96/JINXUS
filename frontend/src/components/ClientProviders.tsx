'use client';

import { Toaster } from 'react-hot-toast';

/** layout.tsx는 서버 컴포넌트 — Toaster(클라이언트)는 여기서 분리 처리 */
export default function ClientProviders() {
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        style: { background: '#27272a', color: '#fff', border: '1px solid #3f3f46' },
        error: { iconTheme: { primary: '#ef4444', secondary: '#fff' } },
        success: { iconTheme: { primary: '#22c55e', secondary: '#fff' } },
      }}
    />
  );
}
