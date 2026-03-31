'use client';

import { Toaster } from 'react-hot-toast';

/** layout.tsx는 서버 컴포넌트 — Toaster(클라이언트)는 여기서 분리 처리 */
export default function ClientProviders() {
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 4000, // 자동 닫힘 4초 (3-5초 권장 범위)
        style: { background: '#27272a', color: '#fff', border: '1px solid #3f3f46' },
        error: {
          duration: 6000, // 에러는 6초 (확인 시간 여유)
          iconTheme: { primary: '#ef4444', secondary: '#fff' },
          ariaProps: { role: 'alert', 'aria-live': 'assertive' },
        },
        success: {
          duration: 3000,
          iconTheme: { primary: '#22c55e', secondary: '#fff' },
        },
      }}
    />
  );
}
