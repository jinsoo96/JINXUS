'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { getFirstName, getDisplayName, getRole, getPersona, sortByRank } from '@/lib/personas';
import type { AgentRuntimeStatus } from '@/lib/api';

// ═══════════════════════════════════════════════════════════════════════════
// 상수
// ═══════════════════════════════════════════════════════════════════════════
const SCALE = 2; // 스프라이트 확대 배율
const TILE = 16 * SCALE; // 32 (2x 확대)
const SW = 12; // 스프라이트 소스 폭
const SH = 16; // 스프라이트 소스 높이
const DSW = SW * SCALE; // 24 — 화면에 그릴 스프라이트 폭
const DSH = SH * SCALE; // 32 — 화면에 그릴 스프라이트 높이
const MAP_W = 50;
const MAP_H = 30;
const CW = MAP_W * TILE; // 1600
const CH = MAP_H * TILE; // 960
const WALK_SPEED = 48 * SCALE; // px/sec (SCALE 보정)
const WALK_FRAME_DUR = 0.15;
const TYPE_FRAME_DUR = 0.3;
const READ_FRAME_DUR = 0.5;
const THINK_FRAME_DUR = 0.6;
const SEARCH_FRAME_DUR = 0.35;
const WALK_SEQ = [0, 1, 0, 2]; // stand→stepA→stand→stepB
const SPEECH_BUBBLE_DURATION = 3.0; // 초
type Row = number[];
type Frame = Row[];

// ═══════════════════════════════════════════════════════════════════════════
// 스프라이트 파트 (0=투명 1=머리 2=피부 3=눈 4=입 5=셔츠 6=바지 7=신발 8=팔피부)
// ═══════════════════════════════════════════════════════════════════════════

// ── 머리 ──
const HD: Frame = [ // DOWN (정면)
  [0,0,0,0,1,1,1,1,0,0,0,0],[0,0,0,1,1,1,1,1,1,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,0,0],[0,0,1,2,2,2,2,2,2,1,0,0],
  [0,0,2,2,3,2,2,3,2,2,0,0],[0,0,2,2,2,2,2,2,2,2,0,0],
  [0,0,0,2,2,4,4,2,2,0,0,0],
];
const HU: Frame = [ // UP (뒷모습)
  [0,0,0,0,1,1,1,1,0,0,0,0],[0,0,0,1,1,1,1,1,1,0,0,0],
  [0,0,1,1,1,1,1,1,1,1,0,0],[0,0,1,1,1,1,1,1,1,1,0,0],
  [0,0,1,1,1,1,1,1,1,1,0,0],[0,0,0,1,1,1,1,1,1,0,0,0],
  [0,0,0,0,2,2,2,2,0,0,0,0],
];
const HL: Frame = [ // LEFT (측면)
  [0,0,0,0,0,1,1,1,0,0,0,0],[0,0,0,0,1,1,1,1,1,0,0,0],
  [0,0,0,1,1,1,1,1,1,0,0,0],[0,0,0,1,2,2,2,1,0,0,0,0],
  [0,0,0,2,3,2,2,0,0,0,0,0],[0,0,0,2,2,2,0,0,0,0,0,0],
  [0,0,0,0,2,4,0,0,0,0,0,0],
];

// ── 몸통 ──
const TF: Frame = [ // FRONT 몸통
  [0,0,0,0,2,2,2,2,0,0,0,0],[0,0,0,0,5,5,5,5,0,0,0,0],
  [0,0,8,5,5,5,5,5,5,8,0,0],[0,0,8,5,5,5,5,5,5,8,0,0],
];
const TS: Frame = [ // SIDE 몸통
  [0,0,0,0,2,2,0,0,0,0,0,0],[0,0,0,0,5,5,0,0,0,0,0,0],
  [0,0,0,8,5,5,5,5,0,0,0,0],[0,0,0,8,5,5,5,5,0,0,0,0],
];
const TY0: Frame = [ // TYPE 0 (팔 앞으로 — 타이핑)
  [0,0,0,0,2,2,2,2,0,0,0,0],[0,0,0,0,5,5,5,5,0,0,0,0],
  [0,0,0,5,5,5,5,5,5,0,0,0],[0,8,8,5,5,5,5,5,5,8,8,0],
];
const TY1: Frame = [ // TYPE 1 (팔 약간 다르게)
  [0,0,0,0,2,2,2,2,0,0,0,0],[0,0,0,0,5,5,5,5,0,0,0,0],
  [0,8,0,5,5,5,5,5,5,0,8,0],[0,8,0,5,5,5,5,5,5,0,8,0],
];
// ── READ 몸통 (한 팔 위로 — 뭔가 들고 있는 자세) ──
const TR0: Frame = [
  [0,0,0,0,2,2,2,2,0,0,0,0],[0,0,0,0,5,5,5,5,0,0,0,0],
  [0,0,8,5,5,5,5,5,5,0,8,0],[0,0,0,5,5,5,5,5,5,8,0,0],
];
const TR1: Frame = [
  [0,0,0,0,2,2,2,2,0,0,0,0],[0,0,0,0,5,5,5,5,0,0,0,0],
  [0,0,8,5,5,5,5,5,5,8,0,0],[0,0,0,5,5,5,5,5,5,0,8,0],
];
// ── THINK 몸통 (팔짱 — 양팔 교차) ──
const TK0: Frame = [
  [0,0,0,0,2,2,2,2,0,0,0,0],[0,0,0,0,5,5,5,5,0,0,0,0],
  [0,0,0,5,5,5,5,5,5,0,0,0],[0,0,8,5,8,5,5,8,5,8,0,0],
];
const TK1: Frame = [
  [0,0,0,0,2,2,2,2,0,0,0,0],[0,0,0,0,5,5,5,5,0,0,0,0],
  [0,0,0,5,5,5,5,5,5,0,0,0],[0,8,0,5,8,5,5,8,5,0,8,0],
];

// ── 다리 (정면/뒷면 공용) ──
const L0: Frame = [ // 서있기
  [0,0,0,0,5,5,5,5,0,0,0,0],[0,0,0,0,6,6,6,6,0,0,0,0],
  [0,0,0,0,6,0,0,6,0,0,0,0],[0,0,0,0,6,0,0,6,0,0,0,0],
  [0,0,0,7,7,0,0,7,7,0,0,0],
];
const LA: Frame = [ // 왼발 앞으로
  [0,0,0,0,5,5,5,5,0,0,0,0],[0,0,0,0,6,6,6,6,0,0,0,0],
  [0,0,0,6,6,0,0,0,6,0,0,0],[0,0,7,7,0,0,0,0,6,0,0,0],
  [0,0,0,0,0,0,0,7,7,0,0,0],
];
const LB: Frame = [ // 오른발 앞으로
  [0,0,0,0,5,5,5,5,0,0,0,0],[0,0,0,0,6,6,6,6,0,0,0,0],
  [0,0,0,6,0,0,6,6,0,0,0,0],[0,0,0,6,0,0,0,7,7,0,0,0],
  [0,0,7,7,0,0,0,0,0,0,0,0],
];
// ── 다리 (측면) ──
const SL0: Frame = [
  [0,0,0,0,5,5,5,0,0,0,0,0],[0,0,0,0,6,6,6,0,0,0,0,0],
  [0,0,0,0,0,6,6,0,0,0,0,0],[0,0,0,0,0,6,6,0,0,0,0,0],
  [0,0,0,0,7,7,0,0,0,0,0,0],
];
const SLA: Frame = [
  [0,0,0,0,5,5,5,0,0,0,0,0],[0,0,0,0,6,6,6,0,0,0,0,0],
  [0,0,0,6,6,0,6,0,0,0,0,0],[0,0,7,7,0,0,6,0,0,0,0,0],
  [0,0,0,0,0,7,7,0,0,0,0,0],
];
const SLB: Frame = [
  [0,0,0,0,5,5,5,0,0,0,0,0],[0,0,0,0,6,6,6,0,0,0,0,0],
  [0,0,0,0,6,6,0,0,0,0,0,0],[0,0,0,0,6,0,7,7,0,0,0,0],
  [0,0,0,7,7,0,0,0,0,0,0,0],
];

// ── 프레임 조합 ──
const mk = (h: Frame, t: Frame, l: Frame): Frame => [...h, ...t, ...l];
const mirror = (f: Frame): Frame => f.map(r => [...r].reverse());

function walkFrame(dir: number, step: number): Frame {
  const i = WALK_SEQ[step % 4];
  if (dir === 0) return mk(HD, TF, [L0, LA, LB][i]);
  if (dir === 3) return mk(HU, TF, [L0, LA, LB][i]);
  const f = mk(HL, TS, [SL0, SLA, SLB][i]);
  return dir === 2 ? mirror(f) : f;
}
function typeFrame(i: number): Frame { return mk(HD, i === 0 ? TY0 : TY1, L0); }
function readFrame(i: number): Frame { return mk(HD, i === 0 ? TR0 : TR1, L0); }
function thinkFrame(i: number): Frame { return mk(HD, i === 0 ? TK0 : TK1, L0); }

// ═══════════════════════════════════════════════════════════════════════════
// 도구 아이콘 (5x5 픽셀)
// ═══════════════════════════════════════════════════════════════════════════
type IconGrid = number[][];

const TOOL_ICONS: Record<string, IconGrid> = {
  terminal: [ // >_
    [1,0,0,0,0],
    [0,1,0,0,0],
    [1,0,0,0,0],
    [0,0,0,0,0],
    [0,1,1,1,0],
  ],
  magnifier: [ // 돋보기
    [0,1,1,0,0],
    [1,0,0,1,0],
    [0,1,1,0,0],
    [0,0,0,1,0],
    [0,0,0,0,1],
  ],
  pencil: [ // 연필
    [0,0,0,0,1],
    [0,0,0,1,0],
    [0,0,1,0,0],
    [0,1,0,0,0],
    [1,0,0,0,0],
  ],
  brain: [ // 뇌
    [0,1,1,1,0],
    [1,1,0,1,1],
    [1,0,1,0,1],
    [1,1,0,1,1],
    [0,1,1,1,0],
  ],
  globe: [ // 지구
    [0,1,1,1,0],
    [1,0,1,0,1],
    [1,1,1,1,1],
    [1,0,1,0,1],
    [0,1,1,1,0],
  ],
};

// 도구 → 아이콘 매핑
function getToolIcon(tools: string[], node: string | null): string | null {
  const toolStr = (tools.join(' ') + ' ' + (node || '')).toLowerCase();
  if (toolStr.match(/plan|reflect|evaluate|think/)) return 'brain';
  if (toolStr.match(/code_executor|bash|execute/)) return 'terminal';
  if (toolStr.match(/write|edit|self_modifier/)) return 'pencil';
  if (toolStr.match(/read|grep|glob|pdf|rss/)) return 'magnifier';
  if (toolStr.match(/web_searcher|fetch|brave|searcher|naver|search/)) return 'globe';
  if (tools.length > 0) return 'terminal'; // 기본: 터미널
  return null;
}

// ═══════════════════════════════════════════════════════════════════════════
// 작업 상태 판별 (도구/노드 기반)
// ═══════════════════════════════════════════════════════════════════════════
type WorkState = 'type' | 'read' | 'think' | 'search';

function getWorkState(runtime: AgentRuntimeStatus | undefined): WorkState {
  const tools = runtime?.current_tools || [];
  const node = runtime?.current_node || '';

  if (node === 'plan' || node === 'reflect' || node === 'evaluate') return 'think';

  const toolStr = tools.join(' ').toLowerCase();
  if (toolStr.match(/read|grep|glob|pdf|rss/)) return 'read';
  if (toolStr.match(/web_searcher|fetch|brave|searcher|naver|search/)) return 'search';
  return 'type'; // 기본: write/edit/bash/code_executor
}

// ═══════════════════════════════════════════════════════════════════════════
// 색상 시스템
// ═══════════════════════════════════════════════════════════════════════════
const HAIR = ['#1a1a2e','#3d2b1f','#5c3317','#8B4513','#C68642','#B22222','#2d3436','#4a0e0e','#1b2631','#4b3621','#6b3a2e','#2c1810'];
const SHIRT: Record<string,string> = {'임원':'#d4a520','엔지니어링':'#3b7dd8','리서치':'#2ea855','운영':'#d97422','마케팅':'#d4589a','기획':'#1a9eb0'};
const CLR: Record<number,number> = {1:0,2:1,3:2,4:3,5:4,6:5,7:6,8:7};

function hash(s: string) { let h=0; for(let i=0;i<s.length;i++) h=((h<<5)-h+s.charCodeAt(i))|0; return Math.abs(h); }

function colors(agent: string, team: string): string[] {
  return [
    HAIR[hash(agent)%HAIR.length], // 0: hair
    '#e8b88a',                      // 1: skin
    '#1a1a2e',                      // 2: eye
    '#c96b6b',                      // 3: mouth
    SHIRT[team]||'#6b7280',         // 4: shirt
    '#2d3748',                      // 5: pants
    '#1a1a2e',                      // 6: shoe
    '#d4a070',                      // 7: arm skin
  ];
}

// ═══════════════════════════════════════════════════════════════════════════
// 스프라이트 캐시
// ═══════════════════════════════════════════════════════════════════════════
const cache = new Map<string, HTMLCanvasElement>();

function sprite(agent: string, team: string, frame: Frame): HTMLCanvasElement {
  const key = `${agent}:${JSON.stringify(frame)}`;
  let c = cache.get(key);
  if (c) return c;
  c = document.createElement('canvas'); c.width = SW; c.height = SH;
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

// ═══════════════════════════════════════════════════════════════════════════
// 오피스 레이아웃
// ═══════════════════════════════════════════════════════════════════════════
interface RoomDef { team: string; x: number; y: number; w: number; h: number; color: string; wall: string; label: string }
interface DeskDef { team: string; dx: number; dy: number; sx: number; sy: number; dir: number }

const ROOMS: RoomDef[] = [
  { team:'임원',       x:0,  y:0,  w:13, h:12, color:'#12100a', wall:'#fbbf2430', label:'#fbbf24' },
  { team:'엔지니어링', x:13, y:0,  w:24, h:12, color:'#0a0e18', wall:'#3b82f630', label:'#3b82f6' },
  { team:'리서치',     x:37, y:0,  w:13, h:12, color:'#0a140a', wall:'#22c55e30', label:'#22c55e' },
  { team:'운영',       x:0,  y:16, w:13, h:12, color:'#140a04', wall:'#f9731630', label:'#f97316' },
  { team:'마케팅',     x:13, y:16, w:24, h:12, color:'#140610', wall:'#ec489930', label:'#ec4899' },
  { team:'기획',       x:37, y:16, w:13, h:12, color:'#061414', wall:'#06b6d430', label:'#06b6d4' },
];

const TEAM_EN: Record<string,string> = {'임원':'EXEC','엔지니어링':'ENG','리서치':'RESEARCH','운영':'OPS','마케팅':'MARKETING','기획':'PLANNING'};

const DESKS: DeskDef[] = [
  // 임원 (4) — 방: x0 y0 w13 h12, 내부: x1-11 y1-10
  {team:'임원',dx:3,dy:3,sx:3,sy:4,dir:3},{team:'임원',dx:7,dy:3,sx:7,sy:4,dir:3},
  {team:'임원',dx:3,dy:8,sx:3,sy:7,dir:0},{team:'임원',dx:7,dy:8,sx:7,sy:7,dir:0},
  // 엔지니어링 (12) — 방: x13 y0 w24 h12, 내부: x14-35 y1-10
  {team:'엔지니어링',dx:16,dy:3,sx:16,sy:4,dir:3},{team:'엔지니어링',dx:19,dy:3,sx:19,sy:4,dir:3},
  {team:'엔지니어링',dx:22,dy:3,sx:22,sy:4,dir:3},{team:'엔지니어링',dx:25,dy:3,sx:25,sy:4,dir:3},
  {team:'엔지니어링',dx:28,dy:3,sx:28,sy:4,dir:3},{team:'엔지니어링',dx:31,dy:3,sx:31,sy:4,dir:3},
  {team:'엔지니어링',dx:16,dy:9,sx:16,sy:8,dir:0},{team:'엔지니어링',dx:19,dy:9,sx:19,sy:8,dir:0},
  {team:'엔지니어링',dx:22,dy:9,sx:22,sy:8,dir:0},{team:'엔지니어링',dx:25,dy:9,sx:25,sy:8,dir:0},
  {team:'엔지니어링',dx:28,dy:9,sx:28,sy:8,dir:0},{team:'엔지니어링',dx:31,dy:9,sx:31,sy:8,dir:0},
  // 리서치 (4) — 방: x37 y0 w13 h12, 내부: x38-48 y1-10
  {team:'리서치',dx:40,dy:3,sx:40,sy:4,dir:3},{team:'리서치',dx:44,dy:3,sx:44,sy:4,dir:3},
  {team:'리서치',dx:40,dy:8,sx:40,sy:7,dir:0},{team:'리서치',dx:44,dy:8,sx:44,sy:7,dir:0},
  // 운영 (2) — 방: x0 y16 w13 h12, 내부: x1-11 y17-26
  {team:'운영',dx:3,dy:19,sx:3,sy:20,dir:3},{team:'운영',dx:7,dy:19,sx:7,sy:20,dir:3},
  // 마케팅 (4) — 방: x13 y16 w24 h12, 내부: x14-35 y17-26
  {team:'마케팅',dx:19,dy:19,sx:19,sy:20,dir:3},{team:'마케팅',dx:25,dy:19,sx:25,sy:20,dir:3},
  {team:'마케팅',dx:19,dy:24,sx:19,sy:23,dir:0},{team:'마케팅',dx:25,dy:24,sx:25,sy:23,dir:0},
  // 기획 (2) — 방: x37 y16 w13 h12, 내부: x38-48 y17-26
  {team:'기획',dx:40,dy:19,sx:40,sy:20,dir:3},{team:'기획',dx:44,dy:19,sx:44,sy:20,dir:3},
];

// 문 위치 (방↔복도 연결)
const DOORS: [number,number][] = [
  [6,11],[7,11],[24,11],[25,11],[43,11],[44,11],  // 상단 방 → 복도
  [6,16],[7,16],[24,16],[25,16],[43,16],[44,16],  // 복도 → 하단 방
];

// ═══════════════════════════════════════════════════════════════════════════
// 이동 가능 그리드 + BFS
// ═══════════════════════════════════════════════════════════════════════════
const deskSet = new Set(DESKS.map(d => `${d.dx},${d.dy}`));

function buildGrid(): boolean[][] {
  const g: boolean[][] = Array.from({length:MAP_H}, ()=>Array(MAP_W).fill(false));
  // 방 내부
  for (const r of ROOMS) {
    for (let y=r.y+1; y<r.y+r.h-1; y++)
      for (let x=r.x+1; x<r.x+r.w-1; x++)
        g[y][x] = true;
  }
  // 복도 (y=12~15, 4타일 높이)
  for (let y=12; y<=15; y++)
    for (let x=0; x<MAP_W; x++) g[y][x]=true;
  // 문
  for (const [dx,dy] of DOORS) g[dy][dx] = true;
  // 책상 타일 비이동
  for (const d of DESKS) g[d.dy][d.dx] = false;
  return g;
}

const GRID = buildGrid();

function bfs(sx:number,sy:number,ex:number,ey:number): [number,number][] {
  if (sx===ex && sy===ey) return [];
  if (!GRID[ey]?.[ex]) return [];
  const visited = new Set<string>();
  const parent = new Map<string, string>();
  const q: [number,number][] = [[sx,sy]];
  visited.add(`${sx},${sy}`);
  const dirs = [[0,1],[0,-1],[1,0],[-1,0]];
  while (q.length) {
    const [cx,cy] = q.shift()!;
    if (cx===ex && cy===ey) {
      const path: [number,number][] = [];
      let k = `${ex},${ey}`;
      while (k !== `${sx},${sy}`) {
        const [a,b] = k.split(',').map(Number);
        path.unshift([a,b]);
        k = parent.get(k)!;
      }
      return path;
    }
    for (const [ddx,ddy] of dirs) {
      const nx=cx+ddx, ny=cy+ddy;
      const nk = `${nx},${ny}`;
      if (nx>=0 && nx<MAP_W && ny>=0 && ny<MAP_H && GRID[ny][nx] && !visited.has(nk)) {
        visited.add(nk);
        parent.set(nk, `${cx},${cy}`);
        q.push([nx,ny]);
      }
    }
  }
  return [];
}

// ═══════════════════════════════════════════════════════════════════════════
// 게임 상태
// ═══════════════════════════════════════════════════════════════════════════
interface CharState {
  code: string; team: string;
  col: number; row: number; // 현재 타일
  x: number; y: number;     // 픽셀 (타일 중심)
  path: [number,number][];
  pathIdx: number;
  dir: number;              // 0=down 1=left 2=right 3=up
  walkStep: number;
  animT: number;
  state: 'idle' | 'walk' | 'type' | 'read' | 'think' | 'search';
  deskCol: number; deskRow: number; deskDir: number;
  idleTimer: number;
  typeFrame: number;
  // 말풍선
  speechBubble: string | null;
  speechBubbleTimer: number;
  // 이전 상태 추적 (상태 전환 감지)
  prevStatus: string | null;
}

interface GameState {
  chars: Map<string, CharState>;
  lastT: number;
  rafId: number;
  deskMap: Map<string, DeskDef>;
}

function tileCenter(col: number, row: number): [number, number] {
  return [col * TILE + TILE / 2, row * TILE + TILE / 2];
}

function dirBetween(fx: number, fy: number, tx: number, ty: number): number {
  const dx = tx - fx, dy = ty - fy;
  if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? 2 : 1;
  return dy > 0 ? 0 : 3;
}

function assignDesks(hired: Set<string>): Map<string, DeskDef> {
  const m = new Map<string, DeskDef>();
  const byTeam: Record<string, DeskDef[]> = {};
  for (const d of DESKS) { if (!byTeam[d.team]) byTeam[d.team]=[]; byTeam[d.team].push(d); }
  const agents: Record<string, string[]> = {};
  Array.from(hired).forEach(code => {
    const p = getPersona(code); if (!p) return;
    if (!agents[p.team]) agents[p.team]=[];
    agents[p.team].push(code);
  });
  for (const [team, codes] of Object.entries(agents)) {
    codes.sort(sortByRank);
    const desks = byTeam[team] || [];
    for (let i = 0; i < Math.min(codes.length, desks.length); i++) m.set(codes[i], desks[i]);
  }
  return m;
}

// ═══════════════════════════════════════════════════════════════════════════
// 업데이트 로직
// ═══════════════════════════════════════════════════════════════════════════
function initChar(code: string, desk: DeskDef): CharState {
  const p = getPersona(code);
  const team = p?.team || '';
  // 시작 위치: 복도 중앙 (랜덤 x)
  const startCol = 5 + hash(code) % 40;
  const startRow = 12 + (hash(code) % 4);
  const [x, y] = tileCenter(startCol, startRow);
  return {
    code, team, col: startCol, row: startRow, x, y,
    path:[], pathIdx:0, dir:0, walkStep:0, animT:0,
    state:'idle', deskCol:desk.sx, deskRow:desk.sy, deskDir:desk.dir,
    idleTimer: 0.5 + Math.random()*2, typeFrame:0,
    speechBubble: null, speechBubbleTimer: 0,
    prevStatus: null,
  };
}

function updateChar(c: CharState, runtime: AgentRuntimeStatus|undefined, dt: number) {
  const status = runtime?.status || 'idle';

  // 말풍선 타이머 업데이트
  if (c.speechBubble) {
    c.speechBubbleTimer -= dt;
    if (c.speechBubbleTimer <= 0) {
      c.speechBubble = null;
      c.speechBubbleTimer = 0;
    }
  }

  // 상태 전환 감지: idle → working 시 말풍선 표시
  if (c.prevStatus !== status) {
    if (status === 'working' && c.prevStatus !== 'working') {
      const taskText = runtime?.current_task;
      if (taskText) {
        // 작업 내용 축약 (최대 20자)
        c.speechBubble = taskText.length > 20 ? taskText.slice(0, 18) + '..' : taskText;
        c.speechBubbleTimer = SPEECH_BUBBLE_DURATION;
      }
    }
    c.prevStatus = status;
  }

  // 작업 상태별 애니메이션 분기
  const workState = getWorkState(runtime);

  // 상태 전환
  if (status === 'working') {
    // 이미 작업 중 상태 (type/read/think/search)
    if (c.state === 'type' || c.state === 'read' || c.state === 'think' || c.state === 'search') {
      // 도구 변경에 따라 작업 상태 전환
      if (c.state !== workState && (c.state === 'type' || c.state === 'read' || c.state === 'think' || c.state === 'search')) {
        c.state = workState;
        c.animT = 0;
        c.typeFrame = 0;
      }
      // 프레임 애니메이션
      const frameDur = c.state === 'read' ? READ_FRAME_DUR
        : c.state === 'think' ? THINK_FRAME_DUR
        : c.state === 'search' ? SEARCH_FRAME_DUR
        : TYPE_FRAME_DUR;
      c.animT += dt;
      if (c.animT >= frameDur) { c.animT -= frameDur; c.typeFrame = (c.typeFrame + 1) % 2; }
      return;
    }
    if (c.col === c.deskCol && c.row === c.deskRow) {
      c.state = workState; c.dir = c.deskDir; c.animT = 0; c.typeFrame = 0;
      return;
    }
    if (c.state !== 'walk' || c.pathIdx >= c.path.length) {
      const p = bfs(c.col, c.row, c.deskCol, c.deskRow);
      if (p.length) { c.path = p; c.pathIdx = 0; c.state = 'walk'; c.walkStep = 0; c.animT = 0; }
      return;
    }
  } else if (c.state === 'type' || c.state === 'read' || c.state === 'think' || c.state === 'search') {
    c.state = 'idle'; c.idleTimer = 1 + Math.random() * 3;
  }

  // 걷기 처리
  if (c.state === 'walk') {
    if (c.pathIdx >= c.path.length) {
      c.state = 'idle'; c.idleTimer = 2 + Math.random() * 5; c.walkStep = 0;
      return;
    }
    const [nx, ny] = c.path[c.pathIdx];
    c.dir = dirBetween(c.col, c.row, nx, ny);
    const [tx, ty] = tileCenter(nx, ny);
    const ddx = tx - c.x, ddy = ty - c.y;
    const dist = Math.sqrt(ddx*ddx + ddy*ddy);
    const spd = WALK_SPEED * dt;
    if (dist <= spd) {
      c.x = tx; c.y = ty; c.col = nx; c.row = ny; c.pathIdx++;
    } else {
      c.x += (ddx/dist)*spd; c.y += (ddy/dist)*spd;
    }
    c.animT += dt;
    if (c.animT >= WALK_FRAME_DUR) { c.animT -= WALK_FRAME_DUR; c.walkStep = (c.walkStep+1)%4; }
    return;
  }

  // 대기 중: 가끔 배회
  if (c.state === 'idle') {
    c.idleTimer -= dt;
    if (c.idleTimer <= 0) {
      c.idleTimer = 4 + Math.random() * 8;
      // 근처 랜덤 타일로 이동
      const tries = 8;
      for (let i = 0; i < tries; i++) {
        const tx = c.col + Math.floor(Math.random()*7) - 3;
        const ty = c.row + Math.floor(Math.random()*7) - 3;
        if (tx>=0 && tx<MAP_W && ty>=0 && ty<MAP_H && GRID[ty][tx]) {
          const p = bfs(c.col, c.row, tx, ty);
          if (p.length > 0 && p.length <= 10) {
            c.path = p; c.pathIdx = 0; c.state = 'walk'; c.walkStep = 0; c.animT = 0;
            break;
          }
        }
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 렌더링
// ═══════════════════════════════════════════════════════════════════════════
function drawToolIcon(ctx: CanvasRenderingContext2D, iconName: string, ix: number, iy: number, color: string) {
  const icon = TOOL_ICONS[iconName];
  if (!icon) return;
  for (let y = 0; y < icon.length; y++) {
    for (let x = 0; x < icon[y].length; x++) {
      if (icon[y][x]) {
        ctx.fillStyle = color;
        ctx.fillRect(ix + x * SCALE, iy + y * SCALE, SCALE, SCALE);
      }
    }
  }
}

function drawSpeechBubble(ctx: CanvasRenderingContext2D, text: string, cx: number, cy: number, alpha: number) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.font = `${10 * SCALE}px monospace`;
  const textWidth = ctx.measureText(text).width;
  const bw = textWidth + 12 * SCALE;
  const bh = 18 * SCALE;
  const bx = Math.round(cx - bw / 2);
  const by = Math.round(cy - DSH - bh - 4 * SCALE);

  // 말풍선 배경
  ctx.fillStyle = '#1e1e2e';
  ctx.fillRect(bx, by, bw, bh);
  ctx.strokeStyle = '#3f3f46';
  ctx.lineWidth = 1 * SCALE;
  ctx.strokeRect(bx, by, bw, bh);

  // 꼬리 (작은 삼각형)
  ctx.fillStyle = '#1e1e2e';
  ctx.beginPath();
  ctx.moveTo(cx - 4 * SCALE, by + bh);
  ctx.lineTo(cx + 4 * SCALE, by + bh);
  ctx.lineTo(cx, by + bh + 6 * SCALE);
  ctx.closePath();
  ctx.fill();

  // 텍스트
  ctx.fillStyle = '#e4e4e7';
  ctx.textAlign = 'center';
  ctx.fillText(text, Math.round(cx), by + 12 * SCALE);
  ctx.textAlign = 'left';
  ctx.restore();
}

function render(game: GameState, ctx: CanvasRenderingContext2D, runtimeMap: Record<string,AgentRuntimeStatus>) {
  // 배경
  ctx.fillStyle = '#08080c';
  ctx.fillRect(0, 0, CW, CH);

  // 방 바닥
  for (const r of ROOMS) {
    ctx.fillStyle = r.color;
    ctx.fillRect((r.x+1)*TILE, (r.y+1)*TILE, (r.w-2)*TILE, (r.h-2)*TILE);
  }

  // 복도
  ctx.fillStyle = '#0e0e12';
  ctx.fillRect(0, 12*TILE, CW, 4*TILE);

  // 바닥 그리드
  ctx.strokeStyle = 'rgba(255,255,255,0.015)';
  ctx.lineWidth = 0.5 * SCALE;
  for (let x=0; x<=CW; x+=TILE) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,CH); ctx.stroke(); }
  for (let y=0; y<=CH; y+=TILE) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(CW,y); ctx.stroke(); }

  // 방 벽
  for (const r of ROOMS) {
    ctx.strokeStyle = r.wall;
    ctx.lineWidth = 2 * SCALE;
    ctx.strokeRect(r.x*TILE+1*SCALE, r.y*TILE+1*SCALE, r.w*TILE-2*SCALE, r.h*TILE-2*SCALE);
  }

  // 문 표시 (벽 끊기)
  ctx.fillStyle = '#0e0e12';
  for (const [dx,dy] of DOORS) ctx.fillRect(dx*TILE-1*SCALE, dy*TILE, TILE+2*SCALE, TILE);

  // 방 라벨
  ctx.textAlign = 'left';
  for (const r of ROOMS) {
    ctx.fillStyle = r.label;
    ctx.globalAlpha = 0.4;
    ctx.font = `${7 * SCALE}px monospace`;
    ctx.fillText(TEAM_EN[r.team]||r.team, (r.x+1)*TILE+2*SCALE, r.y*TILE+9*SCALE);
    ctx.globalAlpha = 1;
  }

  // 책상 + 모니터
  for (const d of DESKS) {
    const active = Array.from(game.chars.values()).some(ch =>
      ch.deskCol===d.sx && ch.deskRow===d.sy &&
      (ch.state==='type' || ch.state==='read' || ch.state==='think' || ch.state==='search')
    );
    // 책상
    ctx.fillStyle = '#3d3530';
    ctx.fillRect(d.dx*TILE+2*SCALE, d.dy*TILE+4*SCALE, TILE-4*SCALE, TILE-6*SCALE);
    // 모니터
    ctx.fillStyle = active ? '#1e293b' : '#111118';
    ctx.fillRect(d.dx*TILE+4*SCALE, d.dy*TILE+1*SCALE, 8*SCALE, 4*SCALE);
    if (active) {
      ctx.fillStyle = '#3b82f6'; ctx.fillRect(d.dx*TILE+5*SCALE, d.dy*TILE+2*SCALE, 5*SCALE, 1*SCALE);
      ctx.fillStyle = '#22c55e'; ctx.fillRect(d.dx*TILE+5*SCALE, d.dy*TILE+3*SCALE, 3*SCALE, 1*SCALE);
    }
    // 모니터 받침
    ctx.fillStyle = '#27272a';
    ctx.fillRect(d.dx*TILE+7*SCALE, d.dy*TILE+5*SCALE, 2*SCALE, 2*SCALE);
  }

  // 캐릭터 (Y 정렬)
  const sorted = Array.from(game.chars.values()).sort((a,b) => a.y - b.y);
  for (const c of sorted) {
    let f: Frame;
    if (c.state === 'type') f = typeFrame(c.typeFrame);
    else if (c.state === 'read' || c.state === 'search') f = readFrame(c.typeFrame);
    else if (c.state === 'think') f = thinkFrame(c.typeFrame);
    else if (c.state === 'walk') f = walkFrame(c.dir, c.walkStep);
    else f = walkFrame(c.dir, 0); // idle = standing

    const s = sprite(c.code, c.team, f);
    const dx = Math.round(c.x - DSW/2);
    const dy = Math.round(c.y - DSH/2);
    ctx.drawImage(s, dx, dy, DSW, DSH);

    // 상태 인디케이터
    const runtime = runtimeMap[c.code];
    const isWorking = runtime?.status === 'working';
    const isError = runtime?.status === 'error';
    if (isWorking) {
      ctx.fillStyle = '#3b82f6';
      ctx.globalAlpha = 0.6 + 0.4 * Math.sin(Date.now()/300);
      ctx.beginPath(); ctx.arc(dx+DSW+1*SCALE, dy+2*SCALE, 2*SCALE, 0, Math.PI*2); ctx.fill();
      ctx.globalAlpha = 1;

      // 도구 아이콘 그리기 (캐릭터 위)
      const iconName = getToolIcon(runtime?.current_tools || [], runtime?.current_node || null);
      if (iconName) {
        const shirtColor = SHIRT[c.team] || '#6b7280';
        const iconX = Math.round(c.x + DSW/2 + 2*SCALE);
        const iconY = Math.round(c.y - DSH/2 - 2*SCALE);
        drawToolIcon(ctx, iconName, iconX, iconY, shirtColor);
      }
    }
    if (isError) {
      ctx.fillStyle = '#ef4444';
      ctx.globalAlpha = 0.6 + 0.4 * Math.sin(Date.now()/200);
      ctx.font = `${6 * SCALE}px sans-serif`;
      ctx.fillText('!', dx+DSW-1*SCALE, dy);
      ctx.globalAlpha = 1;
    }

    // 말풍선
    if (c.speechBubble && c.speechBubbleTimer > 0) {
      const alpha = c.speechBubbleTimer < 0.5
        ? c.speechBubbleTimer / 0.5 // 페이드아웃
        : Math.min(1, (SPEECH_BUBBLE_DURATION - c.speechBubbleTimer + 0.3) / 0.3); // 페이드인
      drawSpeechBubble(ctx, c.speechBubble, Math.round(c.x), dy, alpha);
    }

    // 이름
    ctx.fillStyle = isWorking ? '#93c5fd' : isError ? '#fca5a5' : '#71717a';
    ctx.font = `${5 * SCALE}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillText(getFirstName(c.code), Math.round(c.x), Math.round(c.y+DSH/2+6*SCALE));
    ctx.textAlign = 'left';
  }

  // 복도 라벨
  ctx.fillStyle = '#27272a';
  ctx.font = `${6 * SCALE}px monospace`;
  ctx.textAlign = 'center';
  ctx.fillText('— HALLWAY —', CW/2, 13*TILE+TILE+4*SCALE);
  ctx.textAlign = 'left';
}

// ═══════════════════════════════════════════════════════════════════════════
// React 컴포넌트
// ═══════════════════════════════════════════════════════════════════════════
interface PixelOfficeProps {
  runtimeMap: Record<string, AgentRuntimeStatus>;
  hiredSet: Set<string>;
  onSelectAgent: (code: string) => void;
}

export default function PixelOffice({ runtimeMap, hiredSet, onSelectAgent }: PixelOfficeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const gameRef = useRef<GameState | null>(null);
  const propsRef = useRef({ runtimeMap, hiredSet, onSelectAgent });
  const [hovered, setHovered] = useState<string|null>(null);
  const [tipPos, setTipPos] = useState({x:0, y:0});

  propsRef.current = { runtimeMap, hiredSet, onSelectAgent };

  // 게임 초기화 + 루프
  useEffect(() => {
    const game: GameState = { chars: new Map(), lastT: 0, rafId: 0, deskMap: new Map() };
    gameRef.current = game;

    const loop = (ts: number) => {
      const dt = game.lastT ? Math.min((ts - game.lastT)/1000, 0.1) : 0.016;
      game.lastT = ts;
      const { runtimeMap: rm, hiredSet: hs } = propsRef.current;

      // 에이전트 동기화
      const newDeskMap = assignDesks(hs);
      // 새 에이전트 추가
      Array.from(hs).forEach(code => {
        if (!game.chars.has(code)) {
          const desk = newDeskMap.get(code);
          if (desk) game.chars.set(code, initChar(code, desk));
        }
      });
      // 해고된 에이전트 제거
      Array.from(game.chars.keys()).forEach(code => {
        if (!hs.has(code)) game.chars.delete(code);
      });
      game.deskMap = newDeskMap;

      // 업데이트
      game.chars.forEach((ch, code) => updateChar(ch, rm[code], dt));

      // 렌더
      const ctx = canvasRef.current?.getContext('2d');
      if (ctx) render(game, ctx, rm);

      game.rafId = requestAnimationFrame(loop);
    };
    game.rafId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(game.rafId);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // 마우스
  const findChar = useCallback((e: React.MouseEvent) => {
    const canvas = canvasRef.current; if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const sx = CW / rect.width, sy = CH / rect.height;
    const px = (e.clientX - rect.left) * sx, py = (e.clientY - rect.top) * sy;
    const game = gameRef.current; if (!game) return null;
    let found: string|null = null;
    game.chars.forEach((ch, code) => {
      if (!found && Math.abs(px - ch.x) < 8 * SCALE && Math.abs(py - ch.y) < 10 * SCALE) found = code;
    });
    return found;
  }, []);

  const handleMove = useCallback((e: React.MouseEvent) => {
    const code = findChar(e);
    setHovered(code);
    if (code) setTipPos({ x: e.clientX, y: e.clientY });
  }, [findChar]);

  const handleClick = useCallback((e: React.MouseEvent) => {
    const code = findChar(e);
    if (code) propsRef.current.onSelectAgent(code);
  }, [findChar]);

  const hp = hovered ? getPersona(hovered) : null;
  const hr = hovered ? runtimeMap[hovered] : undefined;

  // 도구 아이콘/작업 상태 한국어 라벨
  const getWorkLabel = (rt: AgentRuntimeStatus | undefined): string => {
    if (!rt || rt.status !== 'working') return '대기';
    const ws = getWorkState(rt);
    switch (ws) {
      case 'type': return '코딩 중';
      case 'read': return '분석 중';
      case 'think': return '사고 중';
      case 'search': return '검색 중';
      default: return '작업 중';
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 헤더 */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-1.5"
        style={{background:'linear-gradient(90deg,#0f0f14,#16161d,#0f0f14)',borderBottom:'2px solid #1e1e26'}}>
        <span style={{fontSize:11,fontFamily:'monospace',fontWeight:800,color:'#e4e4e7',letterSpacing:2}}>
          JINXUS CORP.
        </span>
        <div className="flex gap-2" style={{fontSize:9,fontFamily:'monospace'}}>
          <span style={{color:'#a1a1aa'}}>{hiredSet.size}명</span>
          {Object.values(runtimeMap).filter(r=>r.status==='working').length > 0 && (
            <span style={{color:'#93c5fd'}}>{Object.values(runtimeMap).filter(r=>r.status==='working').length}명 작업중</span>
          )}
        </div>
      </div>

      {/* 캔버스 */}
      <div className="flex-1 min-h-0 flex items-center justify-center bg-[#08080c] overflow-hidden">
        <canvas
          ref={canvasRef}
          width={CW} height={CH}
          onMouseMove={handleMove}
          onMouseLeave={() => setHovered(null)}
          onClick={handleClick}
          style={{
            maxWidth:'100%', maxHeight:'100%', objectFit:'contain',
            imageRendering:'pixelated', cursor: hovered ? 'pointer' : 'default',
          }}
        />
      </div>

      {/* 툴팁 */}
      {hovered && hp && (
        <div className="fixed z-50 pointer-events-none"
          style={{left:tipPos.x+12,top:tipPos.y-10,padding:'6px 10px',
            background:'#1e1e2e',border:'1px solid #3f3f46',borderRadius:6,
            boxShadow:'0 4px 16px rgba(0,0,0,0.6)',maxWidth:200}}>
          <p style={{fontSize:11,color:'#fff',fontWeight:600}}>{hp.emoji} {getDisplayName(hovered)}</p>
          <p style={{fontSize:9,color:'#a1a1aa',marginBottom:3}}>{getRole(hovered)}</p>
          <div className="flex items-center gap-1" style={{fontSize:9}}>
            <span style={{width:6,height:6,borderRadius:'50%',display:'inline-block',
              background:hr?.status==='working'?'#3b82f6':hr?.status==='error'?'#ef4444':'#22c55e'}} />
            <span style={{color:hr?.status==='working'?'#93c5fd':hr?.status==='error'?'#fca5a5':'#86efac'}}>
              {hr?.status==='working' ? getWorkLabel(hr) : hr?.status==='error' ? '오류' : '대기'}
            </span>
          </div>
          {hr?.status==='working' && hr.current_task && (
            <p style={{fontSize:8,color:'#93c5fd',marginTop:3,wordBreak:'break-all'}}>작업: {hr.current_task}</p>
          )}
          {hr?.current_tools && hr.current_tools.length>0 && (
            <p style={{fontSize:7,color:'#71717a',marginTop:2}}>도구: {hr.current_tools.join(', ')}</p>
          )}
          {hr?.current_node && (
            <p style={{fontSize:7,color:'#52525b',marginTop:1}}>노드: {hr.current_node}</p>
          )}
          <p style={{fontSize:7,color:'#52525b',marginTop:3}}>클릭하여 대화</p>
        </div>
      )}

      {/* 하단 안내 */}
      <div className="flex-shrink-0 px-3 py-1 text-center"
        style={{fontSize:8,color:'#3f3f46',fontFamily:'monospace',background:'#0a0a0e',borderTop:'1px solid #1e1e26'}}>
        캐릭터를 클릭하면 직접 대화할 수 있습니다 · 작업 상태에 따라 애니메이션이 변합니다
      </div>
    </div>
  );
}
