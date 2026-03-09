/** JINXUS 프론트엔드 공통 상수 */

/** 폴링 간격 (밀리초) - 비활성 탭에서는 사용하지 않음 */
export const POLLING_INTERVAL_MS = 15000;

/** 사이드바에 표시할 최대 에이전트 수 */
export const MAX_SIDEBAR_AGENTS = 5;

/** 채팅 메시지 최대 보관 수 */
export const MAX_MESSAGES = 300;

/** 메인 탭 목록 */
export const MAIN_TABS = [
  'dashboard', 'chat', 'graph', 'agents', 'memory', 'logs', 'tools', 'settings',
] as const;

export type TabId = typeof MAIN_TABS[number];
