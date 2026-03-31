// ═══════════════════════════════════════════════════════════════════════════
// PNG 스프라이트 로더 — pixel-agents 에셋을 Canvas 프레임으로 변환
// 모든 이미지를 병렬 로딩하여 속도 최적화
// ═══════════════════════════════════════════════════════════════════════════

const CHAR_FRAME_W = 16;
const CHAR_FRAME_H = 32;
const CHAR_FRAMES_PER_ROW = 7; // walk0,walk1,walk2, type0,type1, read0,read1
const CHAR_DIRECTIONS = 3;     // down, up, right (left = mirrored right)
const CHAR_COUNT = 6;

// ── Types ──
export interface CharFrames {
  walk: HTMLCanvasElement[][]; // [dir][step 0-3]
  type: HTMLCanvasElement[][]; // [dir][frame 0-1]
  read: HTMLCanvasElement[][]; // [dir][frame 0-1]
}

// ── Module state ──
let _characters: CharFrames[] = [];
let _coreSprite: CharFrames | null = null; // JINXUS_CORE 전용 (안경 + 백발)
let _furniture: Map<string, HTMLCanvasElement> = new Map();
let _grassTile: HTMLCanvasElement | null = null;
let _stoneTile: HTMLCanvasElement | null = null;
let _loaded = false;
let _loadPromise: Promise<void> | null = null;

// ── Helpers ──
function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load: ${src}`));
    img.src = src;
  });
}

function sliceFrame(img: HTMLImageElement, x: number, y: number, w: number, h: number): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, x, y, w, h, 0, 0, w, h);
  return c;
}

function mirrorCanvas(src: HTMLCanvasElement): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = src.width; c.height = src.height;
  const ctx = c.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  ctx.translate(c.width, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(src, 0, 0);
  return c;
}

function imgToCanvas(img: HTMLImageElement): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const ctx = c.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0);
  return c;
}

/** 스프라이트시트 이미지 → CharFrames 변환 */
function parseCharSheet(img: HTMLImageElement): CharFrames {
  const frames: HTMLCanvasElement[][] = [];
  for (let dir = 0; dir < CHAR_DIRECTIONS; dir++) {
    const row: HTMLCanvasElement[] = [];
    for (let frame = 0; frame < CHAR_FRAMES_PER_ROW; frame++) {
      row.push(sliceFrame(img, frame * CHAR_FRAME_W, dir * CHAR_FRAME_H, CHAR_FRAME_W, CHAR_FRAME_H));
    }
    frames.push(row);
  }
  const down = frames[0], up = frames[1], right = frames[2];
  const left = right.map(mirrorCanvas);
  return {
    walk: [
      [down[0], down[1], down[0], down[2]],
      [left[0], left[1], left[0], left[2]],
      [right[0], right[1], right[0], right[2]],
      [up[0], up[1], up[0], up[2]],
    ],
    type: [
      [down[3], down[4]], [left[3], left[4]],
      [right[3], right[4]], [up[3], up[4]],
    ],
    read: [
      [down[5], down[6]], [left[5], left[6]],
      [right[5], right[6]], [up[5], up[6]],
    ],
  };
}

// ── Furniture files ──
const FURNITURE_FILES: Record<string, string> = {
  desk: 'DESK_FRONT.png', plant: 'LARGE_PLANT.png', coffee: 'COFFEE.png',
  wb: 'WHITEBOARD.png', book: 'BOOKSHELF.png', sofa: 'SOFA_FRONT.png',
  bench: 'WOODEN_BENCH.png', tree: 'PLANT.png', ashtray: 'BIN.png',
  pc_on: 'PC_FRONT_ON_1.png', pc_off: 'PC_FRONT_OFF.png',
  chair: 'WOODEN_CHAIR_FRONT.png', clock: 'CLOCK.png',
  cactus: 'CACTUS.png', bookshelf2: 'DOUBLE_BOOKSHELF.png',
  painting: 'LARGE_PAINTING.png',
};

// ── Public API ──

export function isLoaded(): boolean { return _loaded; }

export function loadAssets(): Promise<void> {
  if (_loadPromise) return _loadPromise;
  _loadPromise = (async () => {
    try {
      // 모든 이미지를 한번에 병렬 로딩
      const charPromises = Array.from({ length: CHAR_COUNT }, (_, i) =>
        loadImage(`/pixel-agents/characters/char_${i}.png`)
      );
      const corePromise = loadImage('/pixel-agents/characters/char_core.png').catch(() => null);
      const grassPromise = loadImage('/pixel-agents/floors/grass.png').catch(() => null);
      const stonePromise = loadImage('/pixel-agents/floors/stone.png').catch(() => null);
      const furnPromises = Object.entries(FURNITURE_FILES).map(([key, file]) =>
        loadImage(`/pixel-agents/furniture/${file}`)
          .then(img => [key, imgToCanvas(img)] as [string, HTMLCanvasElement])
          .catch(() => null)
      );

      // 전부 동시에 대기
      const [charImgs, coreImg, grassImg, stoneImg, ...furnResults] = await Promise.all([
        Promise.all(charPromises),
        corePromise,
        grassPromise,
        stonePromise,
        ...furnPromises,
      ]);

      // Characters
      _characters = (charImgs as HTMLImageElement[]).map(parseCharSheet);

      // CORE 전용 스프라이트 (안경 + 백발)
      if (coreImg) _coreSprite = parseCharSheet(coreImg);

      // Tiles
      if (grassImg) _grassTile = imgToCanvas(grassImg);
      if (stoneImg) _stoneTile = imgToCanvas(stoneImg);

      // Furniture
      _furniture = new Map();
      for (const r of furnResults) {
        if (r) _furniture.set(r[0], r[1]);
      }

      _loaded = true;
      console.log(`[PixelOffice] Assets loaded: ${_characters.length} chars, ${_furniture.size} furniture, core=${!!_coreSprite}`);
    } catch (e) {
      console.error('[PixelOffice] Asset loading failed:', e);
    }
  })();
  return _loadPromise;
}

/** Get character sprite index from agent code (deterministic hash) */
function charIndex(agentCode: string): number {
  let h = 0;
  for (let i = 0; i < agentCode.length; i++) h = ((h << 5) - h + agentCode.charCodeAt(i)) | 0;
  return Math.abs(h) % CHAR_COUNT;
}

/** 에이전트별 CharFrames 반환 (CORE는 전용 스프라이트) */
function getCharFrames(agentCode: string): CharFrames | null {
  if (!_loaded) return null;
  if (agentCode === 'JINXUS_CORE' && _coreSprite) return _coreSprite;
  return _characters[charIndex(agentCode)] ?? null;
}

export function getWalkFrame(agentCode: string, dir: number, step: number): HTMLCanvasElement | null {
  return getCharFrames(agentCode)?.walk[dir]?.[step % 4] ?? null;
}

export function getTypeFrame(agentCode: string, dir: number, frame: number): HTMLCanvasElement | null {
  return getCharFrames(agentCode)?.type[dir]?.[frame % 2] ?? null;
}

export function getReadFrame(agentCode: string, dir: number, frame: number): HTMLCanvasElement | null {
  return getCharFrames(agentCode)?.read[dir]?.[frame % 2] ?? null;
}

export function getGrassTile(): HTMLCanvasElement | null { return _grassTile; }
export function getStoneTile(): HTMLCanvasElement | null { return _stoneTile; }

export function getFloorTile(index: number): HTMLCanvasElement | null { return null; }
export function getFloorCount(): number { return 0; }

export function getFurniture(type: string): HTMLCanvasElement | null {
  if (!_loaded) return null;
  return _furniture.get(type) ?? null;
}
