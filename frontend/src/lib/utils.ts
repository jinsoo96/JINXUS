/** JINXUS 프론트엔드 공통 유틸리티 */

/** 에이전트 상태 → 배경 색상 클래스 */
export function getAgentStatusColor(status: string | undefined): string {
  switch (status) {
    case 'working': return 'bg-green-500';
    case 'error': return 'bg-red-500';
    default: return 'bg-zinc-500';
  }
}

/** 에이전트 상태 → 텍스트 */
export function getAgentStatusText(status: string | undefined): string {
  switch (status) {
    case 'working': return '작업중';
    case 'error': return '오류';
    default: return '대기';
  }
}

/** 작업 상태 → 텍스트 색상 클래스 */
export function getTaskStatusColor(status: string): string {
  switch (status) {
    case 'running':
    case 'in_progress':
      return 'text-blue-400';
    case 'pending':
      return 'text-yellow-400';
    default:
      return 'text-zinc-400';
  }
}

/**
 * 시간 포맷 (HH:MM)
 * @param date - Date 객체, ISO 문자열, 또는 null
 */
export function formatTime(date: Date | string | null): string {
  if (!date) return '';
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  });
}

/**
 * 시간 포맷 (HH:MM:SS)
 * @param date - Date 객체, ISO 문자열, 또는 null
 */
export function formatTimeWithSeconds(date: Date | string | null): string {
  if (!date) return '';
  const d = typeof date === 'string' ? new Date(date) : date;
  if (isNaN(d.getTime())) return '';
  return d.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  });
}

/**
 * 날짜+시간 포맷 (M월 D일 HH:MM)
 * @param date - ISO 문자열 또는 null
 */
export function formatDateTime(date: string | null): string {
  if (!date) return '';
  const d = new Date(date);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString('ko-KR', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Seoul',
  });
}
