/**
 * 에이전트 페르소나 — 프론트엔드 단일 소스 오브 트루스
 *
 * ★ 하드코딩 금지 ★
 * 앱 시작 시 GET /api/agents/personas 에서 백엔드 personas.py 데이터를 받아
 * _dynamicMap을 덮어쓴다. 이후 모든 함수는 _dynamicMap을 우선 사용한다.
 *
 * 에이전트 추가/팀 변경 → personas.py만 수정 → 프론트 자동 반영.
 * STATIC_PERSONA_MAP은 백엔드 연결 전 fallback 전용.
 */

export interface PersonaInfo {
  name: string;             // 성+이름 (예: 이민준) / JINXUS_CORE는 'JINXUS'
  firstName: string;        // 채널 from_name 매칭용 (예: 민준 / JINXUS)
  role: string;             // 직함
  team: string;             // 소속팀
  channel: string;          // 기본(홈) 채널 ID
  emoji: string;            // 아바타 이모지
  personalityId?: string;   // personality.py 아키타입 ID
  personalityLabel?: string; // 한국어 인격 라벨 (예: 개척자)
  personalityEmoji?: string; // 인격 이모지 (예: 🔥)
  personalityTagline?: string; // 인격 한 줄 설명
  mbti?: string;            // MBTI 타입
  rank?: number;            // 직급 순위 (0=CEO, 1=C-Suite, 2=팀장, 3=시니어, 4=일반)
}

// ── 정적 Fallback (백엔드 연결 전 사용, 절대 직접 참조 금지) ────────────
const STATIC_PERSONA_MAP: Record<string, PersonaInfo> = {
  // ── 경영 ──────────────────────────────────────────────────────
  JINXUS_CORE:     { name: 'JINXUS',   firstName: 'JINXUS', role: '실장',                     team: '경영',         channel: 'general',     emoji: '🧠' },
  JX_CTO:          { name: '이채영',   firstName: '채영',   role: 'CTO',                      team: '경영',         channel: 'general',     emoji: '🛡️' },
  JX_COO:          { name: '오세준',   firstName: '세준',   role: 'COO',                      team: '경영',         channel: 'general',     emoji: '⚡' },
  JX_CFO:          { name: '윤미래',   firstName: '미래',   role: 'CFO',                      team: '경영',         channel: 'general',     emoji: '💰' },
  // ── 개발팀 ────────────────────────────────────────────────────
  JX_CODER:        { name: '이민준',   firstName: '민준',   role: '개발팀장',                  team: '개발팀',       channel: 'dev',         emoji: '💻' },
  JX_FRONTEND:     { name: '박예린',   firstName: '예린',   role: '프론트엔드 엔지니어',       team: '개발팀',       channel: 'dev',         emoji: '🎨' },
  JX_BACKEND:      { name: '최재원',   firstName: '재원',   role: '백엔드 엔지니어',           team: '개발팀',       channel: 'dev',         emoji: '⚙️' },
  JX_REVIEWER:     { name: '한수빈',   firstName: '수빈',   role: '시니어 엔지니어',           team: '개발팀',       channel: 'dev',         emoji: '🔍' },
  JX_TESTER:       { name: '윤하은',   firstName: '하은',   role: 'QA 엔지니어',               team: '개발팀',       channel: 'dev',         emoji: '🧪' },
  JX_MOBILE:       { name: '최은지',   firstName: '은지',   role: '모바일 엔지니어',           team: '개발팀',       channel: 'dev',         emoji: '📱' },
  // ── 플랫폼팀 ──────────────────────────────────────────────────
  JX_ARCHITECT:    { name: '박민성',   firstName: '민성',   role: '플랫폼팀장',                team: '플랫폼팀',     channel: 'platform',    emoji: '🏛️' },
  JX_INFRA:        { name: '정도현',   firstName: '도현',   role: '인프라 엔지니어',           team: '플랫폼팀',     channel: 'platform',    emoji: '🏗️' },
  JX_AI_ENG:       { name: '정승우',   firstName: '승우',   role: 'ML 엔지니어',               team: '플랫폼팀',     channel: 'platform',    emoji: '🤖' },
  JX_SECURITY:     { name: '김정민',   firstName: '정민',   role: '보안 엔지니어',             team: '플랫폼팀',     channel: 'platform',    emoji: '🔐' },
  JX_DATA_ENG:     { name: '이서준',   firstName: '서준',   role: '데이터 엔지니어',           team: '플랫폼팀',     channel: 'platform',    emoji: '🔧' },
  JX_PROMPT_ENG:   { name: '이지호',   firstName: '지호',   role: 'AI 엔지니어',               team: '플랫폼팀',     channel: 'platform',    emoji: '✨' },
  // ── 프로덕트팀 ────────────────────────────────────────────────
  JX_PRODUCT:      { name: '김서연',   firstName: '서연',   role: 'PM',                       team: '프로덕트팀',   channel: 'product',     emoji: '📐' },
  JX_RESEARCHER:   { name: '김지은',   firstName: '지은',   role: '프로덕트팀장',              team: '프로덕트팀',   channel: 'product',     emoji: '🔬' },
  JX_WEB_SEARCHER: { name: '오유진',   firstName: '유진',   role: '리서치 애널리스트',         team: '프로덕트팀',   channel: 'product',     emoji: '🌐' },
  JX_DEEP_READER:  { name: '장시우',   firstName: '시우',   role: '데이터 리서처',             team: '프로덕트팀',   channel: 'product',     emoji: '📖' },
  JX_FACT_CHECKER: { name: '임나연',   firstName: '나연',   role: '리서치 QA',                 team: '프로덕트팀',   channel: 'product',     emoji: '✅' },
  JX_STRATEGY:     { name: '신준혁',   firstName: '준혁',   role: '사업개발 매니저',           team: '프로덕트팀',   channel: 'product',     emoji: '🎯' },
  // ── 마케팅팀 ──────────────────────────────────────────────────
  JX_MARKETING:    { name: '박지훈',   firstName: '지훈',   role: '마케팅팀장',                team: '마케팅팀',     channel: 'marketing',   emoji: '📣' },
  JX_WRITER:       { name: '강소희',   firstName: '소희',   role: '콘텐츠 마케터',             team: '마케팅팀',     channel: 'marketing',   emoji: '✍️' },
  JS_PERSONA:      { name: '권아름',   firstName: '아름',   role: '브랜드 에디터',             team: '마케팅팀',     channel: 'marketing',   emoji: '🎭' },
  JX_SNS:          { name: '남다현',   firstName: '다현',   role: '퍼포먼스 마케터',           team: '마케팅팀',     channel: 'marketing',   emoji: '📱' },
  // ── 경영지원팀 ────────────────────────────────────────────────
  JX_ANALYST:      { name: '서현수',   firstName: '현수',   role: '비즈니스 애널리스트',       team: '경영지원팀',   channel: 'biz-support', emoji: '📊' },
  JX_OPS:          { name: '배태양',   firstName: '태양',   role: '시스템 운영',               team: '경영지원팀',   channel: 'biz-support', emoji: '🖥️' },
  JX_SECRETARY:    { name: '정소율',   firstName: '소율',   role: '비서',                     team: '경영',         channel: 'general',     emoji: '📋' },
};

// ── 동적 맵 (앱 시작 시 백엔드에서 덮어씀) ───────────────────────────────
let _dynamicMap: Record<string, PersonaInfo> | null = null;

/**
 * 백엔드 /api/agents/personas 응답으로 런타임 페르소나 맵을 덮어쓴다.
 * useAppStore.loadPersonas() 에서 호출.
 */
export function setDynamicPersonaMap(map: Record<string, PersonaInfo>): void {
  _dynamicMap = map;
}

/** 현재 활성 페르소나 맵 (동적 우선, fallback 정적) */
function getMap(): Record<string, PersonaInfo> {
  return _dynamicMap ?? STATIC_PERSONA_MAP;
}

// ── 하위 호환 export (PERSONA_MAP 직접 참조 컴포넌트용 — Proxy로 동적 반영) ──
export const PERSONA_MAP: Record<string, PersonaInfo> = new Proxy({} as Record<string, PersonaInfo>, {
  get(_t, key: string)           { return getMap()[key]; },
  has(_t, key: string)           { return key in getMap(); },
  ownKeys()                      { return Object.keys(getMap()); },
  getOwnPropertyDescriptor(_t, key: string) {
    const v = getMap()[key];
    return v ? { value: v, writable: false, enumerable: true, configurable: true } : undefined;
  },
});

// ── 팀 중앙 설정 (단일 소스 오브 트루스) ────────────────────────────────────
// 팀 추가/변경 시 여기만 수정하면 AgentsTab, PixelOffice, CompanyChat 전부 자동 반영.

export interface TeamConfig {
  priority: number;         // 표시 순서 (낮을수록 먼저)
  labelEn: string;          // 영문 라벨
  labelShort?: string;      // 축약 라벨 (없으면 한글 이름 그대로)
  channelId: string;        // 대표 채널 ID
  channelIcon: string;      // 채널 아이콘
  channelDesc: string;      // 채널 설명
  color: string;            // 대표 hex 색상
  borderBg: string;         // Tailwind border+bg 클래스
  textColor: string;        // Tailwind text 클래스
  shirtColor: string;       // PixelOffice 셔츠 hex
  floor: { type: string; base: string; accent: string };
}

export const TEAM_CONFIG: Record<string, TeamConfig> = {
  '경영': {
    priority: 0, labelEn: 'Executive', channelId: 'general',
    channelIcon: '🏢', channelDesc: '업무 수여 및 전사 보고',
    color: '#fbbf24',
    borderBg: 'border-amber-500/30 bg-amber-500/5',
    textColor: 'text-amber-400',
    shirtColor: '#d4a520',
    floor: { type: 'wood', base: '#1a1510', accent: '#2a2018' },
  },
  '개발팀': {
    priority: 1, labelEn: 'Development', channelId: 'dev',
    channelIcon: '💻', channelDesc: '프로덕트 개발·구현·QA',
    color: '#3b82f6',
    borderBg: 'border-blue-500/30 bg-blue-500/5',
    textColor: 'text-blue-400',
    shirtColor: '#3b7dd8',
    floor: { type: 'tile', base: '#0c1020', accent: '#141830' },
  },
  '플랫폼팀': {
    priority: 2, labelEn: 'Platform', channelId: 'platform',
    channelIcon: '🏗️', channelDesc: '인프라·보안·데이터·AI/ML',
    color: '#8b5cf6',
    borderBg: 'border-violet-500/30 bg-violet-500/5',
    textColor: 'text-violet-400',
    shirtColor: '#7c3aed',
    floor: { type: 'tile', base: '#100820', accent: '#181030' },
  },
  '프로덕트팀': {
    priority: 3, labelEn: 'Product', channelId: 'product',
    channelIcon: '📐', channelDesc: '제품 기획·UX 리서치·전략',
    color: '#22c55e',
    borderBg: 'border-green-500/30 bg-green-500/5',
    textColor: 'text-green-400',
    shirtColor: '#2ea855',
    floor: { type: 'carpet', base: '#0c180c', accent: '#142014' },
  },
  '마케팅팀': {
    priority: 4, labelEn: 'Marketing', channelId: 'marketing',
    channelIcon: '📣', channelDesc: '마케팅·콘텐츠·퍼포먼스',
    color: '#ec4899',
    borderBg: 'border-pink-500/30 bg-pink-500/5',
    textColor: 'text-pink-400',
    shirtColor: '#d4589a',
    floor: { type: 'carpet', base: '#1a0810', accent: '#221018' },
  },
  '경영지원팀': {
    priority: 5, labelEn: 'Biz Support', channelId: 'biz-support',
    channelIcon: '🖥️', channelDesc: '데이터 분석·시스템 운영',
    color: '#f97316',
    borderBg: 'border-orange-500/30 bg-orange-500/5',
    textColor: 'text-orange-400',
    shirtColor: '#d97422',
    floor: { type: 'concrete', base: '#180c06', accent: '#201408' },
  },
};

/** 팀 설정 조회 (없으면 경영지원팀 fallback) */
export function getTeamConfig(teamName: string): TeamConfig {
  return TEAM_CONFIG[teamName] ?? TEAM_CONFIG['경영지원팀'];
}

/** 채널 목록 (general + 각 팀 대표 채널) */
export function getChannelList(): { id: string; label: string; icon: string; description: string }[] {
  const channels: { id: string; label: string; icon: string; description: string }[] = [
    { id: 'general', label: '전사 공지', icon: '🏢', description: '업무 수여 및 전사 보고' },
  ];
  const seen = new Set(['general']);
  for (const [team, cfg] of Object.entries(TEAM_CONFIG)) {
    if (!seen.has(cfg.channelId)) {
      seen.add(cfg.channelId);
      channels.push({ id: cfg.channelId, label: team, icon: cfg.channelIcon, description: cfg.channelDesc });
    }
  }
  return channels;
}

const TEAM_PRIORITY: Record<string, number> = Object.fromEntries(
  Object.entries(TEAM_CONFIG).map(([name, cfg]) => [name, cfg.priority])
);

/** 현재 페르소나 맵에서 팀 목록을 동적 생성 (우선순위순 정렬) */
export function getTeamOrder(): string[] {
  const teams = new Set<string>();
  for (const p of Object.values(getMap())) {
    teams.add(p.team);
  }
  return Array.from(teams).sort((a, b) => (TEAM_PRIORITY[a] ?? 99) - (TEAM_PRIORITY[b] ?? 99));
}

// ── 채널별 에이전트 코드 배열 ─────────────────────────────────────────────

/**
 * 채널 ID → 소속 에이전트 코드 배열
 * - general : 모든 에이전트
 * - planning: planning 소속 + 임원팀
 * - 나머지  : channel 소속 에이전트
 */
export function getChannelAgents(channelId: string): string[] {
  const map = getMap();
  if (channelId === 'general') {
    return Object.keys(map);
  }
  if (channelId === 'planning') {
    return Object.entries(map)
      .filter(([, p]) => p.channel === 'planning' || p.team === '경영')
      .map(([code]) => code);
  }
  return Object.entries(map)
    .filter(([, p]) => p.channel === channelId)
    .map(([code]) => code);
}

// ── 파생 자료구조 ────────────────────────────────────────────────────────

/** firstName → emoji (CompanyChat from_name 매칭용) */
export function getFirstNameEmojiMap(): Record<string, string> {
  return {
    ...Object.fromEntries(Object.values(getMap()).map(p => [p.firstName, p.emoji])),
    '진수': '👤',
  };
}

/**
 * 팀별 에이전트 코드 그룹 (직원 현황 그리드)
 * 동적 맵에서 자동 파생 → 새 에이전트 추가 시 자동 반영
 */
export function getTeamGroups(): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const [code, p] of Object.entries(getMap())) {
    if (!groups[p.team]) groups[p.team] = [];
    groups[p.team].push(code);
  }
  return groups;
}

// ── 직급 순위 (백엔드 personas.py rank 필드 기반, 동적) ────────────────────

/** 에이전트 코드 → 직급 순위 (낮을수록 높은 직급, 기본값 4=일반) */
export function getAgentRank(agentCode: string): number {
  return getMap()[agentCode]?.rank ?? 4;
}

/** 직급순 정렬 비교 함수 (같은 직급이면 이름순) */
export function sortByRank(a: string, b: string): number {
  const rankDiff = getAgentRank(a) - getAgentRank(b);
  if (rankDiff !== 0) return rankDiff;
  return (getDisplayName(a) ?? a).localeCompare(getDisplayName(b) ?? b, 'ko');
}

// ── 헬퍼 함수 ────────────────────────────────────────────────────────────

export function getPersona(agentCode: string): PersonaInfo | undefined {
  return getMap()[agentCode];
}

/** 에이전트 코드 → 성+이름 (없으면 코드 그대로) */
export function getDisplayName(agentCode: string): string {
  return getMap()[agentCode]?.name ?? agentCode;
}

/** 에이전트 코드 → 이름만 (사이드바 등 좁은 공간용) */
export function getFirstName(agentCode: string): string {
  return (
    getMap()[agentCode]?.firstName ??
    agentCode.replace('JX_', '').replace('JINXUS_', '').replace('JS_', '')
  );
}

/** 에이전트 코드 → 직함 */
export function getRole(agentCode: string): string {
  return getMap()[agentCode]?.role ?? '';
}
