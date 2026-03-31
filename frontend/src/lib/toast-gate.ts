/**
 * Toast Gating — 이벤트 폭주 시 카테고리별 rate limiting (Paperclip 패턴)
 *
 * 카테고리별 10초 내 최대 3개 토스트 제한.
 * OFFICE FEED 등에서 이벤트가 폭주할 때 UI 과부하 방지.
 */
import toast from 'react-hot-toast';

// 카테고리별 토스트 기록
const _toastLog: Record<string, { count: number; resetAt: number }> = {};

const WINDOW_MS = 10_000; // 10초 윈도우
const MAX_PER_WINDOW = 3; // 윈도우당 최대 3개

/**
 * Rate-limited toast — 카테고리별 10초 내 최대 3개
 *
 * @param message 토스트 메시지
 * @param category 카테고리 (예: 'agent_chat', 'mission', 'system')
 * @param type 'success' | 'error' | 'info' (default: 'info')
 * @returns toast ID or null if rate-limited
 */
export function gatedToast(
  message: string,
  category: string = 'default',
  type: 'success' | 'error' | 'info' = 'info',
): string | null {
  const now = Date.now();
  const entry = _toastLog[category];

  if (entry) {
    if (now < entry.resetAt) {
      // 윈도우 내
      if (entry.count >= MAX_PER_WINDOW) {
        // 초과 — 억제
        return null;
      }
      entry.count++;
    } else {
      // 윈도우 리셋
      _toastLog[category] = { count: 1, resetAt: now + WINDOW_MS };
    }
  } else {
    _toastLog[category] = { count: 1, resetAt: now + WINDOW_MS };
  }

  // 토스트 발행
  switch (type) {
    case 'success':
      return toast.success(message);
    case 'error':
      return toast.error(message);
    default:
      return toast(message);
  }
}

/**
 * 특정 카테고리의 rate limit 리셋
 */
export function resetToastGate(category: string): void {
  delete _toastLog[category];
}

/**
 * 모든 카테고리 리셋
 */
export function resetAllToastGates(): void {
  Object.keys(_toastLog).forEach((k) => delete _toastLog[k]);
}
