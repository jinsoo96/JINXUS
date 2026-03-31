import { SW, SH, SCALE } from '../engine/constants';
import type { Frame } from '../engine/types';
import { walkFrame, typeFrame, readFrame, thinkFrame } from './character';
import { colors, CLR } from './colors';

// ═══════════════════════════════════════════════════════════════════════════
// 스프라이트 캐시 — 코드 기반 렌더링 (에이전트별 고유 실루엣)
// ═══════════════════════════════════════════════════════════════════════════

const _cache = new Map<string, HTMLCanvasElement>();

/** Frame(palette matrix) → 16×24 canvas로 렌더링 */
function renderFrame(agentCode: string, team: string, frame: Frame): HTMLCanvasElement {
  const key = `${agentCode}:${team}:${JSON.stringify(frame)}`;
  const hit = _cache.get(key);
  if (hit) return hit;

  const c = document.createElement('canvas');
  c.width = SW;   // 16
  c.height = SH;  // 32 (24px 캐릭터 + 8px 여백을 아래 정렬)
  const ctx = c.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;

  const clr = colors(agentCode, team);
  const offsetY = SH - frame.length; // 하단 정렬

  for (let y = 0; y < frame.length; y++) {
    for (let x = 0; x < frame[y].length; x++) {
      const p = frame[y][x];
      if (p === 0) continue; // transparent

      // palette 10 = accessory (안경/넥타이)
      let color: string;
      if (p === 10) {
        // JINXUS_CORE: 골드 넥타이/안경테
        if (agentCode === 'JINXUS_CORE') {
          color = '#d4a017';
        } else {
          color = '#555555';
        }
      } else {
        const ci = CLR[p];
        color = ci !== undefined ? clr[ci] : '#ff00ff';
      }

      ctx.fillStyle = color;
      ctx.fillRect(x, y + offsetY, 1, 1);
    }
  }

  // 캐시 크기 제한 (최대 2000개)
  if (_cache.size > 2000) {
    const firstKey = _cache.keys().next().value;
    if (firstKey) _cache.delete(firstKey);
  }
  _cache.set(key, c);
  return c;
}

/** PixelOffice.tsx에서 호출하는 메인 API — 에이전트 상태에 맞는 스프라이트 반환 */
export function spriteForState(
  agentCode: string,
  state: string,
  dir: number,
  frame: number,
  team?: string,
): HTMLCanvasElement | null {
  const t = team || '_default';

  let f: Frame;
  switch (state) {
    case 'walk':
      f = walkFrame(dir, frame, agentCode);
      break;
    case 'type':
    case 'search':
      f = typeFrame(frame, agentCode);
      break;
    case 'read':
      f = readFrame(frame, agentCode);
      break;
    case 'think':
      f = thinkFrame(frame, agentCode);
      break;
    case 'idle':
    default:
      f = walkFrame(dir, 0, agentCode);
      break;
  }

  return renderFrame(agentCode, t, f);
}

/** 기존 호환 API — Frame 직접 전달 */
export function sprite(agentCode: string, team: string, frame: Frame): HTMLCanvasElement {
  return renderFrame(agentCode, team, frame);
}

/** Clear sprite cache */
export function clearSpriteCache(): void {
  _cache.clear();
}
