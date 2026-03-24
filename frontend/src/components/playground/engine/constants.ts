// ═══════════════════════════════════════════════════════════════════════════
// 상수 — PixelOffice 엔진 핵심 수치
// ═══════════════════════════════════════════════════════════════════════════

export const SCALE = 4;             // 스프라이트 확대 배율 (16x24 기준 4배)
export const TILE = 16 * SCALE;     // 64px per tile
export const SW = 16;               // 스프라이트 소스 폭 (16x24)
export const SH = 24;               // 스프라이트 소스 높이 (16x24)
export const DSW = SW * SCALE;      // 64 — 화면에 그릴 스프라이트 폭
export const DSH = SH * SCALE;      // 96 — 화면에 그릴 스프라이트 높이

// ── 맵 크기 (60x40 확장) ──
export const MAP_W = 60;
export const MAP_H = 40;
export const CW = MAP_W * TILE;     // 3840
export const CH = MAP_H * TILE;     // 2560

export const WALK_SPEED = 48 * SCALE; // px/sec

// ── 프레임 듀레이션 ──
export const WALK_FRAME_DUR = 0.15;
export const TYPE_FRAME_DUR = 0.3;
export const READ_FRAME_DUR = 0.5;
export const THINK_FRAME_DUR = 0.6;
export const SEARCH_FRAME_DUR = 0.35;

// ── 걷기 시퀀스 ──
export const WALK_SEQ = [0, 1, 0, 2]; // stand→stepA→stand→stepB

// ── 말풍선 ──
export const SPEECH_BUBBLE_DURATION = 3.0; // 초
