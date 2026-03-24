import { TEAM_CONFIG } from '@/lib/personas';

// ═══════════════════════════════════════════════════════════════════════════
// 색상 시스템
// ═══════════════════════════════════════════════════════════════════════════

export const HAIR = [
  '#1a1a2e', '#3d2b1f', '#5c3317', '#8B4513', '#C68642', '#B22222',
  '#2d3436', '#4a0e0e', '#1b2631', '#4b3621', '#6b3a2e', '#2c1810',
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
  return [
    HAIR[hash(agent) % HAIR.length], // 0: hair
    '#e8b88a',                        // 1: skin
    '#1a1a2e',                        // 2: eye
    '#c96b6b',                        // 3: mouth
    SHIRT[team] || '#6b7280',         // 4: shirt
    '#2d3748',                        // 5: pants
    '#1a1a2e',                        // 6: shoe
    '#d4a070',                        // 7: arm skin
    '#f0a0a0',                        // 8: blush
  ];
}
