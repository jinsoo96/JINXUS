import { TEAM_CONFIG } from '@/lib/personas';

// ═══════════════════════════════════════════════════════════════════════════
// 색상 시스템 — 에이전트별 독자적 팔레트
// ═══════════════════════════════════════════════════════════════════════════

export const HAIR = [
  '#1a1a2e', '#3d2b1f', '#5c3317', '#8B4513', '#C68642', '#B22222',
  '#2d3436', '#4a0e0e', '#1b2631', '#4b3621', '#6b3a2e', '#2c1810',
];

// 피부 톤 다양화
const SKIN_TONES = [
  '#e8b88a', '#d4a070', '#f0c8a0', '#c49060', '#e0a878', '#f5d0b0',
];
// 바지 색상 다양화
const PANTS = [
  '#2d3748', '#1e293b', '#3f3f46', '#1a1a2e', '#27272a', '#374151',
];
// 신발 색상 다양화
const SHOES = [
  '#1a1a2e', '#3d2b1f', '#1f2937', '#4a5568', '#292524', '#1e1b4b',
];

export const SHIRT: Record<string, string> = Object.fromEntries(
  Object.entries(TEAM_CONFIG).map(([k, v]) => [k, v.shirtColor])
);

/** Palette index → color array index mapping:
 *  0=transparent, 1=hair, 2=skin, 3=eyes, 4=mouth, 5=shirt, 6=pants, 7=shoes, 8=arm skin, 9=blush */
export const CLR: Record<number, number> = {
  1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8,
};

export function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export function colors(agent: string, team: string): string[] {
  // CEO 전용 팔레트
  if (agent === 'JINXUS_CORE') {
    return [
      '#c0c0c0',           // 0: hair (은발)
      '#e8b88a',           // 1: skin
      '#1a1a2e',           // 2: eye
      '#c96b6b',           // 3: mouth
      '#1a1a2e',           // 4: shirt (블랙 수트)
      '#1a1a2e',           // 5: pants (블랙)
      '#0f0f1a',           // 6: shoe (블랙)
      '#d4a070',           // 7: arm skin
      '#f0a0a0',           // 8: blush
    ];
  }

  const h = hash(agent);
  const skinIdx = h % SKIN_TONES.length;
  const skin = SKIN_TONES[skinIdx];
  // arm skin = 살짝 어두운 스킨톤
  const armSkin = SKIN_TONES[(skinIdx + 2) % SKIN_TONES.length];

  return [
    HAIR[h % HAIR.length],                   // 0: hair
    skin,                                     // 1: skin
    '#1a1a2e',                                // 2: eye
    '#c96b6b',                                // 3: mouth
    SHIRT[team] || '#6b7280',                 // 4: shirt
    PANTS[(h >> 4) % PANTS.length],           // 5: pants
    SHOES[(h >> 8) % SHOES.length],           // 6: shoe
    armSkin,                                  // 7: arm skin
    '#f0a0a0',                                // 8: blush
  ];
}
