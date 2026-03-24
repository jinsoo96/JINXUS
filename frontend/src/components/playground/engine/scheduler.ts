// ═══════════════════════════════════════════════════════════════════════════
// Per-agent daily schedule system based on rank/team
// ═══════════════════════════════════════════════════════════════════════════

import { getPersona } from '@/lib/personas';

export type SchedulePhase = 'commute' | 'morning' | 'focus' | 'lunch' | 'afternoon' | 'evening' | 'night';

/** Determine current schedule phase from KST hour */
export function getSchedulePhase(kstHour: number): SchedulePhase {
  if (kstHour >= 6 && kstHour < 9) return 'commute';
  if (kstHour >= 9 && kstHour < 10) return 'morning';
  if (kstHour >= 10 && kstHour < 12) return 'focus';
  if (kstHour >= 12 && kstHour < 13) return 'lunch';
  if (kstHour >= 13 && kstHour < 18) return 'afternoon';
  if (kstHour >= 18 && kstHour < 22) return 'evening';
  return 'night';
}

/** Get probability of going to POI vs desk based on rank and phase */
export function getScheduleBias(agentCode: string, phase: SchedulePhase): {
  deskProb: number;
  poiProb: number;
  socialProb: number;
  outdoorProb: number;
} {
  const persona = getPersona(agentCode);
  const rank = persona?.rank ?? 4;

  // Executives move around more, junior staff stay at desk more
  const rankMod = rank <= 1 ? 0.15 : rank === 2 ? 0.1 : 0;

  switch (phase) {
    case 'commute':
      return { deskProb: 0.2, poiProb: 0.4 + rankMod, socialProb: 0.2, outdoorProb: 0.2 };
    case 'morning':
      return { deskProb: 0.5 - rankMod, poiProb: 0.25 + rankMod, socialProb: 0.15, outdoorProb: 0.1 };
    case 'focus':
      return { deskProb: 0.7 - rankMod, poiProb: 0.1, socialProb: 0.1 + rankMod, outdoorProb: 0.1 };
    case 'lunch':
      return { deskProb: 0.05, poiProb: 0.35, socialProb: 0.3, outdoorProb: 0.3 };
    case 'afternoon':
      return { deskProb: 0.5 - rankMod, poiProb: 0.15, socialProb: 0.2 + rankMod, outdoorProb: 0.15 };
    case 'evening':
      return { deskProb: 0.3, poiProb: 0.2, socialProb: 0.2, outdoorProb: 0.3 };
    case 'night':
      return { deskProb: 0.6, poiProb: 0.15, socialProb: 0.1, outdoorProb: 0.15 };
  }
}
