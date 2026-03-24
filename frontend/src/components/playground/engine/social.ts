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
