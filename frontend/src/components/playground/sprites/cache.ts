import type { Frame } from '../engine/types';
import { SW, SH } from '../engine/constants';
import { colors, CLR } from './colors';

// ═══════════════════════════════════════════════════════════════════════════
// 스프라이트 캐시 — 에이전트+프레임 조합별 캔버스 캐시
// ═══════════════════════════════════════════════════════════════════════════

const cache = new Map<string, HTMLCanvasElement>();

export function sprite(agent: string, team: string, frame: Frame): HTMLCanvasElement {
  const key = `${agent}:${JSON.stringify(frame)}`;
  let c = cache.get(key);
  if (c) return c;
  c = document.createElement('canvas');
  c.width = SW;
  c.height = SH;
  const ctx = c.getContext('2d')!;
  const cl = colors(agent, team);
  for (let y = 0; y < frame.length; y++)
    for (let x = 0; x < frame[y].length; x++) {
      const t = frame[y][x];
      if (!t) continue;
      ctx.fillStyle = cl[CLR[t]];
      ctx.fillRect(x, y, 1, 1);
    }
  cache.set(key, c);
  return c;
}

/** Clear sprite cache (useful on hot reload) */
export function clearSpriteCache(): void {
  cache.clear();
}
