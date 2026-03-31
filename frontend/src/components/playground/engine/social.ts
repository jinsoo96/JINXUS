import { hash } from '../sprites/colors';

// ═══════════════════════════════════════════════════════════════════════════
// Generative Agents: 사회적 행동 시스템
// ═══════════════════════════════════════════════════════════════════════════

// 현재 활동 텍스트 (idle 에이전트용)
export const IDLE_ACTIVITIES = [
  '문서 검토 중', '코드 리뷰 중', '이메일 확인 중', '회의록 작성 중',
  '슬랙 확인 중', '메모 정리 중', '일정 확인 중', '보고서 작성 중',
];

// 자발적 대화 템플릿 [질문, 대답]
export const CHAT_TEMPLATES: [string, string][] = [
  // 업무
  ['요즘 프로젝트 어때?', '순조로워~ 이번 주 안에 끝낼 듯'],
  ['이거 리뷰 좀 봐줄 수 있어?', '응 바로 볼게!'],
  ['새 기능 어디까지?', '거의 다 됐어 테스트만 남음'],
  ['이번 스프린트 무거운데', '같이 나눠서 하자~'],
  ['API 응답이 좀 느린데', '인덱스 추가하면 해결될 듯'],
  ['배포 언제 하지?', '내일 오전에 합시다'],
  ['어제 이슈 해결했어?', '응 캐시 문제였어ㅋ'],
  ['테스트 돌려봤어?', '방금 돌렸는데 다 통과!'],
  ['이거 왜 에러 나지?', '아 타입 빠진 거 같은데'],
  ['PR 올렸어?', '응 방금 올림! 확인 부탁~'],
  ['이 구조 좀 이상하지 않아?', '맞아 리팩토링 하자'],
  ['DB 스키마 변경해야 할 듯', '마이그레이션 스크립트 짤게'],
  // 일상
  ['커피 한잔 할래?', '좋지! 잠깐 쉬자'],
  ['점심 뭐 먹을까?', '배고프다 치킨 ㄱㄱ'],
  ['오늘 날씨 좋다', '진짜 산책 가고 싶네'],
  ['주말에 뭐 했어?', '그냥 집에서 쉬었어ㅋ'],
  ['요즘 뭐 재밌는 거 있어?', '넷플릭스 새 시리즈 봤는데 꿀잼'],
  ['아 졸리다', 'ㅋㅋ 커피 더 마셔'],
  ['퇴근하고 뭐 해?', '오늘은 운동 가야지'],
  ['회의 언제야?', '3시에 있어 잊지 마~'],
  // 기술
  ['새 프레임워크 써봤어?', '아직 안 써봤는데 괜찮아?'],
  ['이거 최적화 어떻게 하지?', '메모이제이션 걸면 될 듯'],
  ['타입스크립트 진짜 편하다', '맞아 런타임 에러 줄어들었어'],
  ['도커 이미지 너무 큰데', '멀티스테이지 빌드 쓰자'],
  ['로그 왜 이렇게 많아', '디버그 레벨 낮추자ㅋ'],
  ['모니터링 대시보드 봤어?', '응 레이턴시 좀 올라갔더라'],
  ['CI 왜 이렇게 느려', '캐시 안 맞아서 그런 듯'],
  ['코드 컨벤션 정하자', '좋아 린터 설정부터 하자'],
];

export function getIdleActivity(code: string): string {
  return IDLE_ACTIVITIES[hash(code + String(Math.floor(Date.now() / 30000))) % IDLE_ACTIVITIES.length];
}

/** 시간대별 행동 확률 (KST) */
export function getIdleBehavior(kstHour: number): 'wander' | 'poi' | 'social' | 'desk' {
  if (kstHour >= 6 && kstHour < 9) return Math.random() < 0.5 ? 'poi' : 'desk';
  if (kstHour >= 9 && kstHour < 12) return Math.random() < 0.15 ? 'poi' : Math.random() < 0.1 ? 'social' : 'wander';
  if (kstHour >= 12 && kstHour < 13) return Math.random() < 0.6 ? 'poi' : 'social';
  if (kstHour >= 13 && kstHour < 18) return Math.random() < 0.2 ? 'social' : Math.random() < 0.15 ? 'poi' : 'wander';
  if (kstHour >= 18 && kstHour < 22) return Math.random() < 0.3 ? 'poi' : 'wander';
  return 'wander';
}

// ═══════════════════════════════════════════════════════════════════════════
// SOTOPIA-inspired Social Dynamics
// 에이전트 간 관계, 에피소드 이벤트, 5가지 행동 타입
// ═══════════════════════════════════════════════════════════════════════════

/** SOTOPIA 5가지 행동 타입 */
export type ActionType = 'speak' | 'non_verbal' | 'physical' | 'none' | 'leave';

/** 관계 상태 */
export interface Relationship {
  agentA: string;
  agentB: string;
  score: number;        // -1.0 ~ 1.0 (적대 ~ 친밀)
  interactions: number;  // 상호작용 횟수
  lastInteraction: number; // timestamp
}

/** 에피소드 이벤트 */
export interface EpisodeEvent {
  id: string;
  type: 'meeting' | 'conflict' | 'collaboration' | 'celebration' | 'crisis';
  participants: string[];
  description: string;
  timestamp: number;
  duration: number; // ms
  impact: Record<string, number>; // agent → relationship delta
}

/** 소셜 액션 */
export interface SocialAction {
  agent: string;
  target?: string;
  actionType: ActionType;
  content: string;
  emoji?: string;
}

// ── 관계 관리 ─────────────────────────────────────────────────────

const relationships = new Map<string, Relationship>();

function relationshipKey(a: string, b: string): string {
  return [a, b].sort().join(':');
}

export function getRelationship(agentA: string, agentB: string): Relationship {
  const key = relationshipKey(agentA, agentB);
  if (!relationships.has(key)) {
    relationships.set(key, {
      agentA: agentA < agentB ? agentA : agentB,
      agentB: agentA < agentB ? agentB : agentA,
      score: 0.1, // 초기 약한 호감
      interactions: 0,
      lastInteraction: Date.now(),
    });
  }
  return relationships.get(key)!;
}

export function updateRelationship(
  agentA: string,
  agentB: string,
  delta: number,
): void {
  const rel = getRelationship(agentA, agentB);
  rel.score = Math.max(-1, Math.min(1, rel.score + delta));
  rel.interactions += 1;
  rel.lastInteraction = Date.now();
}

export function getAllRelationships(): Relationship[] {
  return Array.from(relationships.values());
}

// ── 에피소드 이벤트 생성 ──────────────────────────────────────────

const EPISODE_TEMPLATES: Omit<EpisodeEvent, 'id' | 'timestamp' | 'participants' | 'impact'>[] = [
  {
    type: 'meeting',
    description: '팀 스탠드업 미팅이 시작됩니다',
    duration: 30000,
  },
  {
    type: 'collaboration',
    description: '페어 프로그래밍 세션이 시작됩니다',
    duration: 60000,
  },
  {
    type: 'conflict',
    description: '코드 리뷰에서 의견 충돌이 발생했습니다',
    duration: 20000,
  },
  {
    type: 'celebration',
    description: '배포 성공! 팀이 축하합니다',
    duration: 15000,
  },
  {
    type: 'crisis',
    description: '긴급 버그 발생! 핫픽스가 필요합니다',
    duration: 45000,
  },
  {
    type: 'meeting',
    description: '스프린트 회고가 시작됩니다',
    duration: 25000,
  },
  {
    type: 'collaboration',
    description: '기술 문서 공동 작성 중입니다',
    duration: 40000,
  },
  {
    type: 'conflict',
    description: '아키텍처 설계 방향에 대해 논쟁이 벌어졌습니다',
    duration: 25000,
  },
  {
    type: 'celebration',
    description: '새 기능 출시를 축하하는 중입니다',
    duration: 10000,
  },
  {
    type: 'crisis',
    description: '서버 장애 발생! 복구 작업 중입니다',
    duration: 50000,
  },
];

/** 에피소드 이벤트 랜덤 생성 */
export function generateEpisodeEvent(agentCodes: string[]): EpisodeEvent | null {
  if (agentCodes.length < 2) return null;

  // 20% 확률로 이벤트 발생
  if (Math.random() > 0.2) return null;

  const template = EPISODE_TEMPLATES[Math.floor(Math.random() * EPISODE_TEMPLATES.length)];

  // 참가자 2-3명 랜덤 선택
  const count = Math.min(agentCodes.length, Math.random() < 0.6 ? 2 : 3);
  const shuffled = [...agentCodes].sort(() => Math.random() - 0.5);
  const participants = shuffled.slice(0, count);

  // 이벤트별 관계 영향
  const impact: Record<string, number> = {};
  for (const p of participants) {
    switch (template.type) {
      case 'collaboration': impact[p] = 0.05; break;
      case 'celebration': impact[p] = 0.08; break;
      case 'conflict': impact[p] = -0.03; break;
      case 'crisis': impact[p] = 0.03; break; // 위기 극복 → 유대감
      default: impact[p] = 0.02; break;
    }
  }

  // 관계 업데이트
  for (let i = 0; i < participants.length; i++) {
    for (let j = i + 1; j < participants.length; j++) {
      const avgDelta = (impact[participants[i]] + impact[participants[j]]) / 2;
      updateRelationship(participants[i], participants[j], avgDelta);
    }
  }

  return {
    id: `ep_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    ...template,
    participants,
    timestamp: Date.now(),
    impact,
  };
}

// ── 5가지 행동 타입 선택 ──────────────────────────────────────────

/** 관계 기반 행동 선택 */
export function selectAction(
  agent: string,
  target: string,
  kstHour: number,
): SocialAction {
  const rel = getRelationship(agent, target);

  // 행동 확률 (관계 점수에 따라 변동)
  const speakProb = 0.3 + rel.score * 0.2;    // 호감↑ → 대화↑
  const nonVerbalProb = 0.2;
  const physicalProb = rel.score > 0.5 ? 0.1 : 0.02; // 친밀해야 physical
  const leaveProb = rel.score < -0.3 ? 0.15 : 0.03;  // 적대 → 떠남↑

  const roll = Math.random();
  let actionType: ActionType;
  let content: string;
  let emoji: string | undefined;

  if (roll < leaveProb) {
    actionType = 'leave';
    content = rel.score < -0.3 ? '(조용히 자리를 피한다)' : '(다른 곳으로 이동한다)';
  } else if (roll < leaveProb + physicalProb) {
    actionType = 'physical';
    const physicalActions = ['(하이파이브를 한다)', '(어깨를 두드린다)', '(커피를 건넨다)'];
    content = physicalActions[Math.floor(Math.random() * physicalActions.length)];
    emoji = '🤜';
  } else if (roll < leaveProb + physicalProb + nonVerbalProb) {
    actionType = 'non_verbal';
    const nonVerbalActions = ['(고개를 끄덕인다)', '(미소 짓는다)', '(생각에 잠긴다)', '(화면을 가리킨다)'];
    content = nonVerbalActions[Math.floor(Math.random() * nonVerbalActions.length)];
  } else if (roll < leaveProb + physicalProb + nonVerbalProb + speakProb) {
    actionType = 'speak';
    // 관계에 따른 대화 선택
    content = selectDialogue(rel);
  } else {
    actionType = 'none';
    content = '';
  }

  return { agent, target, actionType, content, emoji };
}

/** 관계 점수에 따른 대화 내용 선택 */
function selectDialogue(rel: Relationship): string {
  const score = rel.score;

  // 관계가 좋으면 친근한 대화
  if (score > 0.5) {
    const friendly = [
      '오늘 뭐 재밌는 거 있어?', '커피 한잔 하자!', '요즘 진짜 잘하고 있어~',
      '같이 점심 먹을래?', '고생했어 오늘도!', '이거 같이 해보자!',
    ];
    return friendly[Math.floor(Math.random() * friendly.length)];
  }

  // 보통 관계
  if (score > 0) {
    const idx = Math.floor(Math.random() * CHAT_TEMPLATES.length);
    return CHAT_TEMPLATES[idx][0]; // 질문만
  }

  // 관계가 안 좋으면 형식적 대화
  const formal = [
    '이거 확인 부탁드립니다.', '진행 상황 공유해주세요.', '회의 시간 맞죠?',
  ];
  return formal[Math.floor(Math.random() * formal.length)];
}

/** 대화 응답 생성 (질문에 대한 답변) */
export function generateResponse(
  question: string,
  responder: string,
  asker: string,
): string {
  const rel = getRelationship(responder, asker);

  // 기존 템플릿에서 매칭 시도
  for (const [q, a] of CHAT_TEMPLATES) {
    if (question === q) {
      return a;
    }
  }

  // 관계 기반 기본 응답
  if (rel.score > 0.5) {
    const responses = ['ㅋㅋ 그래!', '좋아 좋아~', '오키!', '당근이지!'];
    return responses[Math.floor(Math.random() * responses.length)];
  }

  const responses = ['네 알겠습니다.', '확인하겠습니다.', '네.'];
  return responses[Math.floor(Math.random() * responses.length)];
}
