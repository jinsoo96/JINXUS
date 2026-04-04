// ═══════════════════════════════════════════════════════════════════════════
// 가구 스프라이트 (16x16 소스 → TILE 크기로 렌더)
// ═══════════════════════════════════════════════════════════════════════════

const _furnCache = new Map<string, HTMLCanvasElement>();

export function makeDeskSprite(active: boolean): HTMLCanvasElement {
  const key = `desk:${active}`;
  if (_furnCache.has(key)) return _furnCache.get(key)!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#5c4a3a'; x.fillRect(1, 5, 14, 8);
  x.fillStyle = '#6d5a48'; x.fillRect(1, 5, 14, 1);
  x.fillStyle = '#4a3a2c'; x.fillRect(1, 12, 14, 1);
  x.fillStyle = '#3d3020'; x.fillRect(2, 13, 2, 3); x.fillRect(12, 13, 2, 3);
  x.fillStyle = '#27272a'; x.fillRect(4, 0, 8, 1); x.fillRect(4, 0, 1, 6); x.fillRect(11, 0, 1, 6);
  x.fillStyle = active ? '#1a2840' : '#111118'; x.fillRect(5, 1, 6, 4);
  if (active) { x.fillStyle = '#3b82f6'; x.fillRect(5, 2, 4, 1); x.fillStyle = '#22c55e'; x.fillRect(5, 3, 3, 1); x.fillStyle = '#64748b'; x.fillRect(5, 4, 4, 1); }
  x.fillStyle = '#27272a'; x.fillRect(7, 6, 2, 1);
  if (active) { x.fillStyle = '#1e1e2e'; x.fillRect(5, 8, 6, 2); x.fillStyle = '#2a2a3e'; x.fillRect(6, 8, 1, 1); x.fillRect(8, 8, 1, 1); x.fillRect(10, 8, 1, 1); }
  _furnCache.set(key, c); return c;
}

export function makePlantSprite(): HTMLCanvasElement {
  if (_furnCache.has('plant')) return _furnCache.get('plant')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#6B3410'; x.fillRect(4, 9, 8, 2); x.fillStyle = '#8B4513'; x.fillRect(5, 10, 6, 4);
  x.fillStyle = '#A0522D'; x.fillRect(5, 10, 6, 1); x.fillStyle = '#3a2a1a'; x.fillRect(5, 9, 6, 1);
  x.fillStyle = '#22c55e'; x.fillRect(6, 3, 4, 6); x.fillRect(4, 5, 2, 3); x.fillRect(10, 5, 2, 3);
  x.fillStyle = '#16a34a'; x.fillRect(7, 1, 2, 3); x.fillRect(5, 4, 1, 2); x.fillRect(10, 6, 1, 2);
  _furnCache.set('plant', c); return c;
}

export function makeCoffeeMachine(): HTMLCanvasElement {
  if (_furnCache.has('coffee')) return _furnCache.get('coffee')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#44403c'; x.fillRect(3, 4, 10, 10); x.fillStyle = '#57534e'; x.fillRect(3, 4, 10, 1);
  x.fillStyle = '#78716c'; x.fillRect(4, 5, 8, 4); x.fillStyle = '#ef4444'; x.fillRect(5, 10, 2, 1);
  x.fillStyle = '#22c55e'; x.fillRect(9, 10, 2, 1); x.fillStyle = '#fbbf24'; x.fillRect(6, 12, 4, 1);
  x.fillStyle = '#292524'; x.fillRect(3, 14, 10, 2);
  _furnCache.set('coffee', c); return c;
}

export function makeWhiteboard(): HTMLCanvasElement {
  if (_furnCache.has('wb')) return _furnCache.get('wb')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#f5f5f4'; x.fillRect(1, 2, 14, 10); x.strokeStyle = '#a8a29e'; x.lineWidth = 1; x.strokeRect(1, 2, 14, 10);
  x.fillStyle = '#3b82f6'; x.fillRect(3, 4, 6, 1); x.fillStyle = '#22c55e'; x.fillRect(3, 6, 4, 1);
  x.fillStyle = '#ef4444'; x.fillRect(3, 8, 5, 1); x.fillStyle = '#fbbf24'; x.fillRect(3, 10, 3, 1);
  x.fillStyle = '#57534e'; x.fillRect(7, 12, 2, 3);
  _furnCache.set('wb', c); return c;
}

export function makeMainWhiteboard(): HTMLCanvasElement {
  if (_furnCache.has('wb_main')) return _furnCache.get('wb_main')!;
  const c = document.createElement('canvas'); c.width = 48; c.height = 16; const x = c.getContext('2d')!;
  // 프레임 (3타일 너비 대형 화이트보드)
  x.fillStyle = '#27272a'; x.fillRect(0, 0, 48, 16); // 뒷판
  x.fillStyle = '#fafaf9'; x.fillRect(1, 1, 46, 12); // 흰색 보드 면
  x.strokeStyle = '#78716c'; x.lineWidth = 1; x.strokeRect(1, 1, 46, 12);
  // 포스트잇/메모 표현
  x.fillStyle = '#fbbf24'; x.fillRect(3, 3, 5, 4);  // 노란 메모
  x.fillStyle = '#fb923c'; x.fillRect(9, 3, 5, 4);  // 주황 메모
  x.fillStyle = '#38bdf8'; x.fillRect(15, 3, 5, 4); // 파란 메모
  x.fillStyle = '#4ade80'; x.fillRect(21, 3, 5, 4); // 초록 메모
  x.fillStyle = '#f472b6'; x.fillRect(27, 3, 5, 4); // 핑크 메모
  x.fillStyle = '#a78bfa'; x.fillRect(33, 3, 5, 4); // 보라 메모
  // 하단 줄 메모
  x.fillStyle = '#fde68a'; x.fillRect(3, 8, 8, 3);
  x.fillStyle = '#bae6fd'; x.fillRect(13, 8, 8, 3);
  x.fillStyle = '#d9f99d'; x.fillRect(23, 8, 8, 3);
  x.fillStyle = '#fecaca'; x.fillRect(33, 8, 8, 3);
  // 다리
  x.fillStyle = '#57534e'; x.fillRect(4, 13, 2, 3); x.fillRect(42, 13, 2, 3);
  _furnCache.set('wb_main', c); return c;
}

export function makeBookshelf(): HTMLCanvasElement {
  if (_furnCache.has('book')) return _furnCache.get('book')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#3d3020'; x.fillRect(1, 0, 14, 16); x.fillStyle = '#4a3a2c'; x.fillRect(1, 0, 14, 1); x.fillRect(1, 5, 14, 1); x.fillRect(1, 10, 14, 1);
  const colors = ['#ef4444','#3b82f6','#22c55e','#fbbf24','#8b5cf6','#ec4899','#06b6d4','#f97316','#6366f1'];
  for (let row = 0; row < 3; row++) for (let i = 0; i < 5; i++) { x.fillStyle = colors[(row * 5 + i) % colors.length]; x.fillRect(2 + i * 2 + (i > 2 ? 1 : 0), 1 + row * 5, 2, 4); }
  _furnCache.set('book', c); return c;
}

export function makeServerRack(): HTMLCanvasElement {
  if (_furnCache.has('server')) return _furnCache.get('server')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#1e1e2e'; x.fillRect(2, 0, 12, 16); x.fillStyle = '#27272a'; x.fillRect(2, 0, 12, 1);
  for (let row = 0; row < 4; row++) { x.fillStyle = '#111118'; x.fillRect(3, 1 + row * 4, 10, 3); x.fillStyle = '#22c55e'; x.fillRect(11, 2 + row * 4, 1, 1); x.fillStyle = '#3b82f6'; x.fillRect(4, 2 + row * 4, 3, 1); }
  _furnCache.set('server', c); return c;
}

export function makePrinterSprite(): HTMLCanvasElement {
  if (_furnCache.has('printer')) return _furnCache.get('printer')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#e5e5e5'; x.fillRect(2, 6, 12, 6);
  x.fillStyle = '#d4d4d4'; x.fillRect(2, 6, 12, 1);
  x.fillStyle = '#fafafa'; x.fillRect(4, 3, 8, 3); // paper tray
  x.fillStyle = '#a3a3a3'; x.fillRect(3, 12, 10, 2); // base
  x.fillStyle = '#22c55e'; x.fillRect(11, 8, 1, 1); // LED
  x.fillStyle = '#f5f5f5'; x.fillRect(5, 13, 6, 2); // output tray
  _furnCache.set('printer', c); return c;
}

export function makeVendingMachine(): HTMLCanvasElement {
  if (_furnCache.has('vending')) return _furnCache.get('vending')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#1e3a5f'; x.fillRect(2, 0, 12, 16);
  x.fillStyle = '#2563eb'; x.fillRect(2, 0, 12, 1);
  x.fillStyle = '#0f172a'; x.fillRect(3, 1, 10, 10); // glass
  // drinks
  const drinkColors = ['#ef4444', '#fbbf24', '#22c55e', '#3b82f6', '#ec4899'];
  for (let r = 0; r < 3; r++) for (let i = 0; i < 4; i++) {
    x.fillStyle = drinkColors[(r * 4 + i) % drinkColors.length];
    x.fillRect(4 + i * 2, 2 + r * 3, 1, 2);
  }
  x.fillStyle = '#fbbf24'; x.fillRect(11, 12, 1, 1); // coin slot
  x.fillStyle = '#0f172a'; x.fillRect(5, 13, 5, 2); // pickup area
  _furnCache.set('vending', c); return c;
}

export function makeFridgeSprite(): HTMLCanvasElement {
  if (_furnCache.has('fridge')) return _furnCache.get('fridge')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#e5e7eb'; x.fillRect(3, 0, 10, 16);
  x.fillStyle = '#f3f4f6'; x.fillRect(3, 0, 10, 1);
  x.fillStyle = '#d1d5db'; x.fillRect(3, 7, 10, 1); // divider
  x.fillStyle = '#9ca3af'; x.fillRect(12, 3, 1, 2); // handle top
  x.fillStyle = '#9ca3af'; x.fillRect(12, 10, 1, 2); // handle bottom
  _furnCache.set('fridge', c); return c;
}

export function makeSofaSprite(): HTMLCanvasElement {
  if (_furnCache.has('sofa')) return _furnCache.get('sofa')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  x.fillStyle = '#7c3aed'; x.fillRect(1, 6, 14, 6);
  x.fillStyle = '#6d28d9'; x.fillRect(1, 6, 2, 6); x.fillRect(13, 6, 2, 6); // armrests
  x.fillStyle = '#8b5cf6'; x.fillRect(3, 5, 10, 2); // backrest
  x.fillStyle = '#a78bfa'; x.fillRect(3, 5, 10, 1); // top highlight
  x.fillStyle = '#1c1917'; x.fillRect(2, 12, 2, 4); x.fillRect(12, 12, 2, 4); // legs
  // cushion details
  x.fillStyle = '#9333ea'; x.fillRect(5, 8, 3, 2); x.fillRect(9, 8, 3, 2);
  _furnCache.set('sofa', c); return c;
}

export function makeWaterCooler(): HTMLCanvasElement {
  if (_furnCache.has('water')) return _furnCache.get('water')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  // bottle
  x.fillStyle = '#93c5fd'; x.fillRect(5, 0, 6, 5);
  x.fillStyle = '#bfdbfe'; x.fillRect(6, 0, 4, 1);
  // body
  x.fillStyle = '#e5e7eb'; x.fillRect(4, 5, 8, 8);
  x.fillStyle = '#d1d5db'; x.fillRect(4, 5, 8, 1);
  // tap
  x.fillStyle = '#3b82f6'; x.fillRect(5, 9, 2, 1);
  x.fillStyle = '#ef4444'; x.fillRect(9, 9, 2, 1);
  // base
  x.fillStyle = '#9ca3af'; x.fillRect(4, 13, 8, 3);
  _furnCache.set('water', c); return c;
}

export function makeBenchSprite(): HTMLCanvasElement {
  if (_furnCache.has('bench')) return _furnCache.get('bench')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  // seat
  x.fillStyle = '#92400e'; x.fillRect(1, 8, 14, 2);
  x.fillStyle = '#a16207'; x.fillRect(1, 8, 14, 1);
  // legs
  x.fillStyle = '#78350f'; x.fillRect(2, 10, 2, 4); x.fillRect(12, 10, 2, 4);
  // backrest
  x.fillStyle = '#92400e'; x.fillRect(1, 5, 14, 1);
  x.fillStyle = '#78350f'; x.fillRect(1, 3, 1, 5); x.fillRect(14, 3, 1, 5);
  _furnCache.set('bench', c); return c;
}

export function makeTreeSprite(): HTMLCanvasElement {
  if (_furnCache.has('tree')) return _furnCache.get('tree')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  // trunk
  x.fillStyle = '#78350f'; x.fillRect(6, 8, 4, 8);
  x.fillStyle = '#92400e'; x.fillRect(7, 8, 2, 8);
  // foliage
  x.fillStyle = '#15803d'; x.fillRect(2, 1, 12, 8);
  x.fillStyle = '#166534'; x.fillRect(4, 0, 8, 2);
  x.fillStyle = '#22c55e'; x.fillRect(3, 2, 4, 3); x.fillRect(8, 3, 4, 2);
  x.fillStyle = '#16a34a'; x.fillRect(5, 1, 3, 2);
  _furnCache.set('tree', c); return c;
}

export function makeAshtraySprite(): HTMLCanvasElement {
  if (_furnCache.has('ashtray')) return _furnCache.get('ashtray')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  // pole
  x.fillStyle = '#71717a'; x.fillRect(7, 2, 2, 10);
  // tray
  x.fillStyle = '#52525b'; x.fillRect(4, 1, 8, 3);
  x.fillStyle = '#3f3f46'; x.fillRect(5, 2, 6, 1);
  // base
  x.fillStyle = '#71717a'; x.fillRect(5, 12, 6, 2);
  x.fillStyle = '#a1a1aa'; x.fillRect(5, 12, 6, 1);
  // smoke
  x.fillStyle = 'rgba(200,200,200,0.3)'; x.fillRect(6, 0, 1, 1); x.fillRect(9, 0, 1, 1);
  _furnCache.set('ashtray', c); return c;
}

export function makeMiniBarSprite(): HTMLCanvasElement {
  if (_furnCache.has('minibar')) return _furnCache.get('minibar')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  // bar counter (dark wood)
  x.fillStyle = '#3d2b1f'; x.fillRect(2, 6, 12, 8);
  x.fillStyle = '#4a3728'; x.fillRect(2, 6, 12, 1); // top highlight
  x.fillStyle = '#2c1e14'; x.fillRect(2, 13, 12, 1); // bottom edge
  // shelves inside
  x.fillStyle = '#332211'; x.fillRect(3, 9, 10, 1);
  // bottles (green soju, brown whiskey, clear sake)
  x.fillStyle = '#22c55e'; x.fillRect(4, 7, 1, 2); // soju
  x.fillStyle = '#16a34a'; x.fillRect(4, 7, 1, 1); // cap
  x.fillStyle = '#92400e'; x.fillRect(6, 7, 1, 2); // whiskey
  x.fillStyle = '#78350f'; x.fillRect(6, 7, 1, 1);
  x.fillStyle = '#e2e8f0'; x.fillRect(8, 7, 1, 2); // sake
  x.fillStyle = '#cbd5e1'; x.fillRect(8, 7, 1, 1);
  x.fillStyle = '#22c55e'; x.fillRect(10, 7, 1, 2); // soju 2
  // glasses on shelf
  x.fillStyle = 'rgba(200,220,255,0.5)'; x.fillRect(4, 10, 1, 2); x.fillRect(7, 10, 1, 2); x.fillRect(10, 10, 1, 2);
  // legs
  x.fillStyle = '#2c1e14'; x.fillRect(3, 14, 2, 2); x.fillRect(11, 14, 2, 2);
  _furnCache.set('minibar', c); return c;
}

export function makeUmbrellaTable(): HTMLCanvasElement {
  if (_furnCache.has('umbrella')) return _furnCache.get('umbrella')!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16; const x = c.getContext('2d')!;
  // umbrella
  x.fillStyle = '#dc2626'; x.fillRect(2, 1, 12, 3);
  x.fillStyle = '#ef4444'; x.fillRect(4, 0, 8, 1);
  x.fillStyle = '#b91c1c'; x.fillRect(2, 3, 12, 1);
  // pole
  x.fillStyle = '#a1a1aa'; x.fillRect(7, 4, 2, 6);
  // table
  x.fillStyle = '#78716c'; x.fillRect(3, 10, 10, 2);
  x.fillStyle = '#57534e'; x.fillRect(3, 11, 10, 1);
  // legs
  x.fillStyle = '#44403c'; x.fillRect(4, 12, 2, 4); x.fillRect(10, 12, 2, 4);
  _furnCache.set('umbrella', c); return c;
}

/** Clear furniture sprite cache (if needed on hot reload) */
export function clearFurnitureCache(): void {
  _furnCache.clear();
}
