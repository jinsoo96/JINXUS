import { SCALE } from '../engine/constants';

// ═══════════════════════════════════════════════════════════════════════════
// Activity-to-emoji mapping and emoji rendering above character heads
// ═══════════════════════════════════════════════════════════════════════════

const ACTIVITY_EMOJIS: Record<string, string> = {
  // Work states
  '코딩 중': '💻',
  '작업 중': '⚡',
  '분석 중': '📖',
  '사고 중': '💭',
  '검색 중': '🔍',
  // Idle activities
  '문서 검토 중': '📄',
  '코드 리뷰 중': '🔎',
  '이메일 확인 중': '📧',
  '회의록 작성 중': '📝',
  '슬랙 확인 중': '💬',
  '메모 정리 중': '📋',
  '일정 확인 중': '📅',
  '보고서 작성 중': '📊',
  // POI activities
  '커피 타는 중': '☕',
  '물 마시는 중': '💧',
  '화이트보드 정리 중': '📋',
  '자료 찾는 중': '📚',
  '서버 확인 중': '🖥️',
  '로그 분석 중': '📊',
  '프린터 사용 중': '🖨️',
  '자판기 사용 중': '🥤',
  '간식 꺼내는 중': '🍪',
  '쉬는 중': '😌',
  '잠깐 쉬는 중': '😌',
  '미팅 중': '👥',
  '소파에서 쉬는 중': '🛋️',
  '복도 이동 중': '🚶',
  '로비 통과 중': '🚶',
  // Outdoor
  '주차장에서': '🚗',
  '정원 산책 중': '🌿',
  '꽃 구경 중': '🌸',
  '흡연 중': '🚬',
  '바람 쐬는 중': '🌬️',
  '테라스에서 쉬는 중': '☀️',
  '테라스 산책 중': '🌤️',
  '옥상 정원에서': '🌳',
  '하늘 보는 중': '⭐',
  '벤치에서 쉬는 중': '🪑',
  '벤치에서 책 읽는 중': '📖',
  // Social
  '대화 중': '💬',
  '출근 중': '🏃',
  '자리로 돌아가는 중': '🏠',
  '산책 중': '🚶',
};

/** Get emoji for an activity string */
export function getActivityEmoji(activity: string): string | null {
  // Direct match
  if (ACTIVITY_EMOJIS[activity]) return ACTIVITY_EMOJIS[activity];
  // Partial match (for "~와 대화 중" etc.)
  if (activity.includes('대화 중')) return '💬';
  if (activity.includes('산책')) return '🚶';
  if (activity.includes('이동')) return '🚶';
  return null;
}

/** Draw emoji above character head */
export function drawActivityEmoji(
  ctx: CanvasRenderingContext2D,
  activity: string,
  cx: number,
  cy: number,
  dsh: number,
): void {
  const emoji = getActivityEmoji(activity);
  if (!emoji) return;

  ctx.save();
  ctx.font = `${5 * SCALE}px sans-serif`;
  ctx.textAlign = 'center';
  // Slight bobbing animation
  const bobY = Math.sin(Date.now() / 800) * SCALE;
  ctx.fillText(emoji, Math.round(cx), Math.round(cy - dsh / 2 - 4 * SCALE + bobY));
  ctx.restore();
}
