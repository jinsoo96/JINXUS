/** JINXUS 프론트엔드 공통 상수 */

/** 폴링 간격 (밀리초) - 비활성 탭에서는 사용하지 않음 */
export const POLLING_INTERVAL_MS = 15000;

/** 사이드바 에이전트 상태 폴링 간격 (밀리초) */
export const SIDEBAR_POLLING_MS = 20000;

/** 로그 탭 활성 폴링 간격 (밀리초) */
export const LOGS_ACTIVE_POLLING_MS = 2000;

/** 로그 탭 유휴 폴링 간격 (밀리초) */
export const LOGS_IDLE_POLLING_MS = 5000;

/** 채팅 메시지 최대 보관 수 */
export const MAX_MESSAGES = 300;

/** 메인 탭 목록 */
export const MAIN_TABS = [
  'chat', 'projects', 'agents', 'memory', 'logs', 'tools', 'notes', 'settings', 'channel',
] as const;
