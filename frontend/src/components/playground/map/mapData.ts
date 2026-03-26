import type { RoomDef, DeskDef, POIDef } from '../engine/types';
import { MAP_W, MAP_H } from '../engine/constants';
import { TEAM_CONFIG } from '@/lib/personas';

// ═══════════════════════════════════════════════════════════════════════════
// 60x40 맵 레이아웃
// ═══════════════════════════════════════════════════════════════════════════
// y0-3:   [Outdoor: Parking(0-19) | Entrance/Lobby(20-39) | Garden(40-59)]
// y4-5:   [Main Entrance Hallway - full width]
// y6-17:  [경영(0-11) | 개발팀(12-35) | 플랫폼팀(36-47) | CEO Room(48-59)]
// y18-21: [Central Hallway + Break Room(25-35) + Coffee Corner]
// y22-33: [경영지원팀(0-11) | 프로덕트팀(12-35) | 마케팅팀(36-47) | Server Room(48-59)]
// y34-35: [Exit Hallway to Outdoor]
// y36-39: [Outdoor: Smoking Area(0-19) | Terrace(20-39) | Rooftop Garden(40-59)]

export const TEAM_EN: Record<string, string> = {
  ...Object.fromEntries(Object.entries(TEAM_CONFIG).map(([k, v]) => [k, v.labelEn])),
  'CEO Room': 'CEO Room',
  'Server': 'Server Room',
};

export const ROOM_FLOORS: Record<string, { type: string; base: string; accent: string }> = {
  ...Object.fromEntries(Object.entries(TEAM_CONFIG).map(([k, v]) => [k, v.floor])),
  'CEO Room': { type: 'wood', base: '#141014', accent: '#1c141c' },
  'Server': { type: 'tile', base: '#060810', accent: '#0c1018' },
};

// ── Rooms ──
export const ROOMS: RoomDef[] = [
  // Upper floor (y6-17)
  { team: '경영',       x: 0,  y: 6,  w: 12, h: 12, color: '#12100a', wall: '#fbbf2430', label: '#fbbf24' },
  { team: '개발팀',     x: 12, y: 6,  w: 24, h: 12, color: '#0a0e18', wall: '#3b82f630', label: '#3b82f6' },
  { team: '플랫폼팀',   x: 36, y: 6,  w: 12, h: 12, color: '#0a0818', wall: '#8b5cf630', label: '#8b5cf6' },
  // CEO Room (formerly Meeting Room)
  { team: 'CEO Room',   x: 48, y: 6,  w: 12, h: 12, color: '#0c0c14', wall: '#64748b40', label: '#94a3b8' },
  // Lower floor (y22-33)
  { team: '경영지원팀',  x: 0,  y: 22, w: 12, h: 12, color: '#140a04', wall: '#f9731630', label: '#f97316' },
  { team: '프로덕트팀',  x: 12, y: 22, w: 24, h: 12, color: '#0c180c', wall: '#22c55e30', label: '#22c55e' },
  { team: '마케팅팀',    x: 36, y: 22, w: 12, h: 12, color: '#1a0810', wall: '#ec489930', label: '#ec4899' },
  // Server Room
  { team: 'Server',     x: 48, y: 22, w: 12, h: 12, color: '#060810', wall: '#3b82f620', label: '#3b82f6' },
];

// ── Desks ──
export const DESKS: DeskDef[] = [
  // CEO Room (1) — room x48 y6 w12 h12, interior x49-58 y7-16
  // JINXUS_CORE 전용 데스크 (CEO Room 중앙 상단)
  { team: 'CEO Room', dx: 53, dy: 9, sx: 53, sy: 10, dir: 3 },

  // 경영 (4) — room x0 y6 w12 h12, interior x1-10 y7-16
  { team: '경영', dx: 3, dy: 9, sx: 3, sy: 10, dir: 3 },
  { team: '경영', dx: 7, dy: 9, sx: 7, sy: 10, dir: 3 },
  { team: '경영', dx: 3, dy: 13, sx: 3, sy: 12, dir: 0 },
  { team: '경영', dx: 7, dy: 13, sx: 7, sy: 12, dir: 0 },

  // 개발팀 (12) — room x12 y6 w24 h12, interior x13-34 y7-16
  { team: '개발팀', dx: 15, dy: 9,  sx: 15, sy: 10, dir: 3 },
  { team: '개발팀', dx: 18, dy: 9,  sx: 18, sy: 10, dir: 3 },
  { team: '개발팀', dx: 21, dy: 9,  sx: 21, sy: 10, dir: 3 },
  { team: '개발팀', dx: 24, dy: 9,  sx: 24, sy: 10, dir: 3 },
  { team: '개발팀', dx: 27, dy: 9,  sx: 27, sy: 10, dir: 3 },
  { team: '개발팀', dx: 30, dy: 9,  sx: 30, sy: 10, dir: 3 },
  { team: '개발팀', dx: 15, dy: 14, sx: 15, sy: 13, dir: 0 },
  { team: '개발팀', dx: 18, dy: 14, sx: 18, sy: 13, dir: 0 },
  { team: '개발팀', dx: 21, dy: 14, sx: 21, sy: 13, dir: 0 },
  { team: '개발팀', dx: 24, dy: 14, sx: 24, sy: 13, dir: 0 },
  { team: '개발팀', dx: 27, dy: 14, sx: 27, sy: 13, dir: 0 },
  { team: '개발팀', dx: 30, dy: 14, sx: 30, sy: 13, dir: 0 },

  // 플랫폼팀 (6) — room x36 y6 w12 h12, interior x37-46 y7-16
  { team: '플랫폼팀', dx: 39, dy: 9,  sx: 39, sy: 10, dir: 3 },
  { team: '플랫폼팀', dx: 43, dy: 9,  sx: 43, sy: 10, dir: 3 },
  { team: '플랫폼팀', dx: 39, dy: 14, sx: 39, sy: 13, dir: 0 },
  { team: '플랫폼팀', dx: 43, dy: 14, sx: 43, sy: 13, dir: 0 },
  { team: '플랫폼팀', dx: 39, dy: 12, sx: 39, sy: 11, dir: 3 },
  { team: '플랫폼팀', dx: 43, dy: 12, sx: 43, sy: 11, dir: 3 },

  // 경영지원팀 (4) — room x0 y22 w12 h12, interior x1-10 y23-32
  { team: '경영지원팀', dx: 3, dy: 25, sx: 3, sy: 26, dir: 3 },
  { team: '경영지원팀', dx: 7, dy: 25, sx: 7, sy: 26, dir: 3 },
  { team: '경영지원팀', dx: 3, dy: 29, sx: 3, sy: 28, dir: 0 },
  { team: '경영지원팀', dx: 7, dy: 29, sx: 7, sy: 28, dir: 0 },

  // 프로덕트팀 (8) — room x12 y22 w24 h12, interior x13-34 y23-32
  { team: '프로덕트팀', dx: 16, dy: 25, sx: 16, sy: 26, dir: 3 },
  { team: '프로덕트팀', dx: 20, dy: 25, sx: 20, sy: 26, dir: 3 },
  { team: '프로덕트팀', dx: 24, dy: 25, sx: 24, sy: 26, dir: 3 },
  { team: '프로덕트팀', dx: 28, dy: 25, sx: 28, sy: 26, dir: 3 },
  { team: '프로덕트팀', dx: 16, dy: 30, sx: 16, sy: 29, dir: 0 },
  { team: '프로덕트팀', dx: 20, dy: 30, sx: 20, sy: 29, dir: 0 },
  { team: '프로덕트팀', dx: 24, dy: 30, sx: 24, sy: 29, dir: 0 },
  { team: '프로덕트팀', dx: 28, dy: 30, sx: 28, sy: 29, dir: 0 },

  // 마케팅팀 (4) — room x36 y22 w12 h12, interior x37-46 y23-32
  { team: '마케팅팀', dx: 39, dy: 25, sx: 39, sy: 26, dir: 3 },
  { team: '마케팅팀', dx: 43, dy: 25, sx: 43, sy: 26, dir: 3 },
  { team: '마케팅팀', dx: 39, dy: 30, sx: 39, sy: 29, dir: 0 },
  { team: '마케팅팀', dx: 43, dy: 30, sx: 43, sy: 29, dir: 0 },
];

// ── Doors (room ↔ hallway connections) ──
export const DOORS: [number, number][] = [
  // Upper rooms → entrance hallway (y4-5)
  [5, 5], [6, 5],                     // 경영 → hallway
  [22, 5], [23, 5],                   // 개발팀 → hallway
  [41, 5], [42, 5],                   // 플랫폼팀 → hallway
  [53, 5], [54, 5],                   // CEO Room → hallway

  // Upper rooms → central hallway (y18-21)
  [5, 17], [6, 17],                   // 경영 → central
  [22, 17], [23, 17],                 // 개발팀 → central
  [41, 17], [42, 17],                 // 플랫폼팀 → central
  [53, 17], [54, 17],                 // CEO Room → central

  // Lower rooms → central hallway
  [5, 22], [6, 22],                   // 경영지원 → central
  [22, 22], [23, 22],                 // 프로덕트 → central
  [41, 22], [42, 22],                 // 마케팅 → central
  [53, 22], [54, 22],                 // Server → central

  // Lower rooms → exit hallway (y34-35)
  [5, 33], [6, 33],                   // 경영지원 → exit
  [22, 33], [23, 33],                 // 프로덕트 → exit
  [41, 33], [42, 33],                 // 마케팅 → exit
  [53, 33], [54, 33],                 // Server → exit
];

// ── POI (Points of Interest) ──
export const POI_LIST: POIDef[] = [
  // Indoor
  { name: 'coffee',       col: 30, row: 19, action: '커피 타는 중', type: 'indoor' },
  { name: 'water_cooler', col: 25, row: 19, action: '물 마시는 중', type: 'indoor' },
  { name: 'whiteboard',   col: 8,  row: 8,  action: '화이트보드 정리 중', type: 'indoor' },
  { name: 'bookshelf',    col: 33, row: 8,  action: '자료 찾는 중', type: 'indoor' },
  { name: 'server_a',     col: 50, row: 25, action: '서버 확인 중', type: 'indoor' },
  { name: 'server_b',     col: 52, row: 25, action: '로그 분석 중', type: 'indoor' },
  { name: 'printer',      col: 10, row: 19, action: '프린터 사용 중', type: 'indoor' },
  { name: 'vending',      col: 35, row: 20, action: '자판기 사용 중', type: 'indoor' },
  { name: 'fridge',       col: 28, row: 20, action: '간식 꺼내는 중', type: 'indoor' },
  { name: 'breakroom_a',  col: 27, row: 19, action: '쉬는 중', type: 'indoor' },
  { name: 'breakroom_b',  col: 32, row: 20, action: '잠깐 쉬는 중', type: 'indoor' },
  { name: 'meeting_a',    col: 52, row: 10, action: '미팅 중', type: 'indoor' },
  { name: 'meeting_b',    col: 55, row: 10, action: '미팅 중', type: 'indoor' },
  { name: 'ceo_smoking',  col: 53, row: 12, action: '담배 피우는 중', type: 'indoor', capacity: 1 },
  { name: 'sofa',         col: 29, row: 20, action: '소파에서 쉬는 중', type: 'indoor' },
  // Hallway
  { name: 'entrance',     col: 30, row: 4,  action: '로비 통과 중', type: 'indoor' },
  { name: 'hall_walk_a',  col: 15, row: 19, action: '복도 이동 중', type: 'indoor' },
  { name: 'hall_walk_b',  col: 45, row: 19, action: '복도 이동 중', type: 'indoor' },
  // Outdoor
  { name: 'parking',      col: 10, row: 2,  action: '주차장에서', type: 'outdoor' },
  { name: 'smoking_c',    col: 46, row: 35, action: '흡연 중', type: 'outdoor', capacity: 3 },
  { name: 'garden_a',     col: 48, row: 2,  action: '정원 산책 중', type: 'outdoor' },
  { name: 'garden_b',     col: 52, row: 2,  action: '꽃 구경 중', type: 'outdoor' },
  { name: 'smoking',      col: 8,  row: 38, action: '흡연 중', type: 'outdoor', capacity: 3 },
  { name: 'smoking_b',    col: 12, row: 38, action: '바람 쐬는 중', type: 'outdoor', capacity: 3 },
  { name: 'terrace_a',    col: 28, row: 38, action: '테라스에서 쉬는 중', type: 'outdoor' },
  { name: 'terrace_b',    col: 32, row: 37, action: '테라스 산책 중', type: 'outdoor' },
  { name: 'rooftop_a',    col: 48, row: 38, action: '옥상 정원에서', type: 'outdoor' },
  { name: 'rooftop_b',    col: 52, row: 37, action: '하늘 보는 중', type: 'outdoor' },
  { name: 'bench_a',      col: 6,  row: 37, action: '벤치에서 쉬는 중', type: 'outdoor' },
  { name: 'bench_b',      col: 50, row: 1,  action: '벤치에서 책 읽는 중', type: 'outdoor' },
];

// ── Furniture placement data ──
export interface FurniturePlacement {
  type: string;
  x: number;
  y: number;
  w?: number;
  h?: number;
}

export const FURNITURE: FurniturePlacement[] = [
  // Plants (room corners)
  { type: 'plant', x: 10, y: 7 },
  { type: 'plant', x: 34, y: 7 },
  { type: 'plant', x: 46, y: 7 },
  { type: 'plant', x: 10, y: 23 },
  { type: 'plant', x: 34, y: 23 },
  { type: 'plant', x: 46, y: 23 },
  { type: 'plant', x: 58, y: 7 },
  { type: 'plant', x: 58, y: 23 },

  // Coffee + break room area (y18-21, x25-35)
  { type: 'coffee', x: 30, y: 19 },
  { type: 'water', x: 25, y: 19 },
  { type: 'fridge', x: 28, y: 20 },
  { type: 'vending', x: 35, y: 20 },
  { type: 'sofa', x: 29, y: 20 },
  { type: 'printer', x: 10, y: 19 },

  // Whiteboards
  { type: 'wb', x: 8, y: 7, w: 2 },   // Executive room upper-right
  { type: 'wb', x: 50, y: 7 },

  // CEO Room ashtray (indoor)
  { type: 'ashtray', x: 54, y: 12 },

  // Bookshelves
  { type: 'book', x: 33, y: 8 },
  { type: 'book', x: 14, y: 24 },

  // Server racks
  { type: 'server', x: 50, y: 24 },
  { type: 'server', x: 52, y: 24 },
  { type: 'server', x: 54, y: 24 },

  // Outdoor furniture
  { type: 'tree', x: 46, y: 1 },
  { type: 'tree', x: 50, y: 0 },
  { type: 'tree', x: 54, y: 1 },
  { type: 'tree', x: 56, y: 0 },
  { type: 'tree', x: 44, y: 36 },
  { type: 'tree', x: 48, y: 36 },
  { type: 'tree', x: 52, y: 36 },
  { type: 'tree', x: 56, y: 37 },

  // Smoking area
  { type: 'ashtray', x: 8, y: 37 },
  { type: 'bench', x: 6, y: 37 },
  { type: 'bench', x: 12, y: 38 },

  // Terrace
  { type: 'umbrella', x: 26, y: 37 },
  { type: 'umbrella', x: 30, y: 37 },
  { type: 'umbrella', x: 34, y: 37 },
  { type: 'bench', x: 28, y: 38 },
  { type: 'bench', x: 32, y: 38 },

  // Smoking area near server room (exit hallway)
  { type: 'ashtray', x: 46, y: 34 },
  { type: 'bench', x: 48, y: 35 },

  // Garden
  { type: 'bench', x: 50, y: 1 },
  { type: 'bench', x: 54, y: 2 },
];

// ── Build walkable grid ──
export function buildGrid(): boolean[][] {
  const g: boolean[][] = Array.from({ length: MAP_H }, () => Array(MAP_W).fill(false));
  const deskSet = new Set(DESKS.map(d => `${d.dx},${d.dy}`));

  // Room interiors
  for (const r of ROOMS) {
    for (let y = r.y + 1; y < r.y + r.h - 1; y++)
      for (let x = r.x + 1; x < r.x + r.w - 1; x++)
        g[y][x] = true;
  }

  // Entrance hallway (y4-5, full width)
  for (let y = 4; y <= 5; y++)
    for (let x = 0; x < MAP_W; x++) g[y][x] = true;

  // Central hallway (y18-21, full width)
  for (let y = 18; y <= 21; y++)
    for (let x = 0; x < MAP_W; x++) g[y][x] = true;

  // Exit hallway (y34-35, full width)
  for (let y = 34; y <= 35; y++)
    for (let x = 0; x < MAP_W; x++) g[y][x] = true;

  // Outdoor areas (y0-3 and y36-39)
  for (let y = 0; y <= 3; y++)
    for (let x = 0; x < MAP_W; x++) g[y][x] = true;
  for (let y = 36; y <= 39; y++)
    for (let x = 0; x < MAP_W; x++) g[y][x] = true;

  // Doors
  for (const [dx, dy] of DOORS) g[dy][dx] = true;

  // Block desk tiles
  for (const d of DESKS) g[d.dy][d.dx] = false;

  // Block furniture tiles (approximate — trees, racks, etc.)
  for (const f of FURNITURE) {
    const fw = f.w ?? 1;
    const fh = f.h ?? 1;
    for (let fy = 0; fy < fh; fy++)
      for (let fx = 0; fx < fw; fx++)
        if (g[f.y + fy]?.[f.x + fx] !== undefined) g[f.y + fy][f.x + fx] = false;
  }

  return g;
}
