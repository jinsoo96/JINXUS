'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { getFirstName, getDisplayName, getRole, getPersona, sortByRank, TEAM_CONFIG } from '@/lib/personas';
import type { AgentRuntimeStatus } from '@/lib/api';

// ── Module imports ──
import type { CharState, GameState, DeskDef, Frame } from './engine/types';
import {
  SCALE, TILE, SW, SH, DSW, DSH, MAP_W, MAP_H, CW, CH,
  WALK_SPEED, WALK_FRAME_DUR, TYPE_FRAME_DUR, READ_FRAME_DUR,
  THINK_FRAME_DUR, SEARCH_FRAME_DUR, SPEECH_BUBBLE_DURATION,
} from './engine/constants';
import { walkFrame, typeFrame, readFrame, thinkFrame } from './sprites/character';
import { SHIRT, hash } from './sprites/colors';
import { TOOL_ICONS, getToolIcon, getWorkState } from './sprites/icons';
import { sprite } from './sprites/cache';
import {
  makeDeskSprite, makePlantSprite, makeCoffeeMachine, makeWhiteboard,
  makeBookshelf, makeServerRack, makePrinterSprite, makeVendingMachine,
  makeFridgeSprite, makeSofaSprite, makeWaterCooler, makeBenchSprite,
  makeTreeSprite, makeAshtraySprite, makeUmbrellaTable,
} from './sprites/furniture';
import {
  ROOMS, DESKS, DOORS, POI_LIST, FURNITURE, TEAM_EN, ROOM_FLOORS,
  buildGrid,
} from './map/mapData';
import { bfs, setGrid, getGrid } from './engine/pathfinding';
import { CHAT_TEMPLATES, getIdleActivity, getIdleBehavior } from './engine/social';
import { drawActivityEmoji } from './render/emoji';
import type { Camera } from './engine/camera';
import { createCamera, screenToWorld, clampCamera, centerOn, applyZoom, startDrag, updateDrag, endDrag } from './engine/camera';
import { initPOIStates } from './poi/poiManager';

// ── Re-exports for consumers (AgentsTab, MissionTab) ──
export type { ActivityLogEntry } from './engine/types';
export type { PixelOfficeProps } from './engine/types';

// ═══════════════════════════════════════════════════════════════════════════
// Helper functions
// ═══════════════════════════════════════════════════════════════════════════

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
  for (const d of DESKS) { if (!byTeam[d.team]) byTeam[d.team] = []; byTeam[d.team].push(d); }
  const agents: Record<string, string[]> = {};
  Array.from(hired).forEach(code => {
    const p = getPersona(code); if (!p) return;
    if (!agents[p.team]) agents[p.team] = [];
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
// Character lifecycle
// ═══════════════════════════════════════════════════════════════════════════

function initChar(code: string, desk: DeskDef): CharState {
  const p = getPersona(code);
  const team = p?.team || '';
  // Spawn at desk position directly (not entrance)
  const startCol = desk.dx;
  const startRow = desk.dy;
  const [x, y] = tileCenter(startCol, startRow);
  return {
    code, team, col: startCol, row: startRow, x, y,
    path: [], pathIdx: 0, dir: 0, walkStep: 0, animT: 0,
    state: 'idle', deskCol: desk.sx, deskRow: desk.sy, deskDir: desk.dir,
    idleTimer: 0.5 + Math.random() * 2, typeFrame: 0,
    speechBubble: null, speechBubbleTimer: 0,
    prevStatus: null,
    activity: '출근 중', poiTarget: null, socialTarget: null, socialTimer: 0,
  };
}

function updateChar(c: CharState, runtime: AgentRuntimeStatus | undefined, dt: number) {
  const status = runtime?.status || 'idle';

  // Speech bubble timer
  if (c.speechBubble) {
    c.speechBubbleTimer -= dt;
    if (c.speechBubbleTimer <= 0) { c.speechBubble = null; c.speechBubbleTimer = 0; }
  }

  // Status transition detection
  if (c.prevStatus !== status) {
    if (status === 'working' && c.prevStatus !== 'working') {
      const taskText = runtime?.current_task;
      if (taskText) {
        c.speechBubble = taskText.length > 20 ? taskText.slice(0, 18) + '..' : taskText;
        c.speechBubbleTimer = SPEECH_BUBBLE_DURATION;
      }
      c.activity = taskText ? (taskText.length > 14 ? taskText.slice(0, 12) + '..' : taskText) : '작업 중';
      c.socialTarget = null; c.socialTimer = 0;
    } else if (status !== 'working' && c.prevStatus === 'working') {
      c.activity = getIdleActivity(c.code);
    }
    c.prevStatus = status;
  }

  const workState = getWorkState(runtime);

  // Working state
  if (status === 'working') {
    if (c.state === 'type' || c.state === 'read' || c.state === 'think' || c.state === 'search') {
      if (c.state !== workState) { c.state = workState; c.animT = 0; c.typeFrame = 0; }
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

  // Walking
  if (c.state === 'walk') {
    if (c.pathIdx >= c.path.length) {
      c.state = 'idle'; c.walkStep = 0;
      if (c.poiTarget) {
        const poi = POI_LIST.find(p => p.name === c.poiTarget);
        if (poi) c.activity = poi.action;
        c.idleTimer = 5 + Math.random() * 8;
        c.poiTarget = null;
      } else {
        c.idleTimer = 2 + Math.random() * 5;
      }
      return;
    }
    const [nx, ny] = c.path[c.pathIdx];
    c.dir = dirBetween(c.col, c.row, nx, ny);
    const [tx, ty] = tileCenter(nx, ny);
    const ddx = tx - c.x, ddy = ty - c.y;
    const dist = Math.sqrt(ddx * ddx + ddy * ddy);
    const spd = WALK_SPEED * dt;
    if (dist <= spd) { c.x = tx; c.y = ty; c.col = nx; c.row = ny; c.pathIdx++; }
    else { c.x += (ddx / dist) * spd; c.y += (ddy / dist) * spd; }
    c.animT += dt;
    if (c.animT >= WALK_FRAME_DUR) { c.animT -= WALK_FRAME_DUR; c.walkStep = (c.walkStep + 1) % 4; }
    return;
  }

  // Social interaction
  if (c.socialTimer > 0) {
    c.socialTimer -= dt;
    if (c.socialTimer <= 0) {
      c.socialTarget = null;
      c.activity = getIdleActivity(c.code);
      c.idleTimer = 2 + Math.random() * 4;
    }
    return;
  }

  // Idle behavior
  if (c.state === 'idle') {
    c.idleTimer -= dt;
    if (c.idleTimer <= 0) {
      const kstHour = new Date(Date.now() + 9 * 3600000).getUTCHours();
      const behavior = getIdleBehavior(kstHour);

      if (behavior === 'poi') {
        const poi = POI_LIST[Math.floor(Math.random() * POI_LIST.length)];
        const p = bfs(c.col, c.row, poi.col, poi.row);
        if (p.length > 0 && p.length <= 30) {
          c.path = p; c.pathIdx = 0; c.state = 'walk'; c.walkStep = 0; c.animT = 0;
          c.poiTarget = poi.name; c.activity = poi.action;
          c.idleTimer = 6 + Math.random() * 8;
          return;
        }
      }

      if (behavior === 'desk') {
        const p = bfs(c.col, c.row, c.deskCol, c.deskRow);
        if (p.length > 0) {
          c.path = p; c.pathIdx = 0; c.state = 'walk'; c.walkStep = 0; c.animT = 0;
          c.activity = '자리로 돌아가는 중';
          c.idleTimer = 3 + Math.random() * 5;
          return;
        }
      }

      // Default: wander nearby
      c.idleTimer = 4 + Math.random() * 8;
      c.activity = getIdleActivity(c.code);
      for (let i = 0; i < 8; i++) {
        const tx = c.col + Math.floor(Math.random() * 9) - 4;
        const ty = c.row + Math.floor(Math.random() * 9) - 4;
        const grid = getGrid();
        if (tx >= 0 && tx < MAP_W && ty >= 0 && ty < MAP_H && grid[ty]?.[tx]) {
          const p = bfs(c.col, c.row, tx, ty);
          if (p.length > 0 && p.length <= 12) {
            c.path = p; c.pathIdx = 0; c.state = 'walk'; c.walkStep = 0; c.animT = 0;
            break;
          }
        }
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// Rendering
// ═══════════════════════════════════════════════════════════════════════════

const _floorCache = new Map<string, HTMLCanvasElement>();

function makeFloorTile(type: string, base: string, accent: string): HTMLCanvasElement {
  const key = `${type}:${base}`;
  if (_floorCache.has(key)) return _floorCache.get(key)!;
  const c = document.createElement('canvas'); c.width = 16; c.height = 16;
  const x2 = c.getContext('2d')!;
  x2.fillStyle = base; x2.fillRect(0, 0, 16, 16);
  x2.fillStyle = accent;
  if (type === 'wood') {
    for (let y = 0; y < 16; y += 4) { x2.fillRect(0, y, 16, 1); for (let x = 0; x < 16; x++) if ((x + y * 3) % 7 === 0) { x2.globalAlpha = 0.15; x2.fillRect(x, y + 1, 1, 2); x2.globalAlpha = 1; } }
    x2.fillRect(8, 0, 1, 4); x2.fillRect(4, 4, 1, 4); x2.fillRect(12, 8, 1, 4); x2.fillRect(6, 12, 1, 4);
  } else if (type === 'carpet') {
    for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) if ((x + y) % 2 === 0) { x2.globalAlpha = 0.08; x2.fillRect(x, y, 1, 1); } x2.globalAlpha = 1;
  } else if (type === 'tile') {
    x2.fillRect(0, 0, 16, 1); x2.fillRect(0, 0, 1, 16);
    x2.globalAlpha = 0.05; for (let y = 2; y < 16; y += 4) for (let x = 2; x < 16; x += 4) x2.fillRect(x, y, 1, 1); x2.globalAlpha = 1;
  } else {
    for (let i = 0; i < 12; i++) { x2.globalAlpha = 0.1; x2.fillRect((i * 7 + 3) % 16, (i * 11 + 5) % 16, 1, 1); } x2.globalAlpha = 1;
  }
  _floorCache.set(key, c); return c;
}

function drawToolIcon(ctx: CanvasRenderingContext2D, iconName: string, ix: number, iy: number, color: string) {
  const icon = TOOL_ICONS[iconName];
  if (!icon) return;
  for (let y = 0; y < icon.length; y++)
    for (let x = 0; x < icon[y].length; x++)
      if (icon[y][x]) { ctx.fillStyle = color; ctx.fillRect(ix + x * SCALE, iy + y * SCALE, SCALE, SCALE); }
}

function drawSpeechBubble(ctx: CanvasRenderingContext2D, text: string, cx: number, cy: number, alpha: number) {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.font = `${6 * SCALE}px monospace`;
  const textWidth = ctx.measureText(text).width;
  const bw = textWidth + 8 * SCALE;
  const bh = 11 * SCALE;
  const bx = Math.round(cx - bw / 2);
  const by = Math.round(cy - DSH - bh - 2 * SCALE);
  ctx.fillStyle = '#1e1e2e'; ctx.fillRect(bx, by, bw, bh);
  ctx.strokeStyle = '#3f3f46'; ctx.lineWidth = 0.5 * SCALE; ctx.strokeRect(bx, by, bw, bh);
  ctx.fillStyle = '#1e1e2e';
  ctx.beginPath(); ctx.moveTo(cx - 3 * SCALE, by + bh); ctx.lineTo(cx + 3 * SCALE, by + bh); ctx.lineTo(cx, by + bh + 4 * SCALE); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#e4e4e7'; ctx.textAlign = 'center';
  ctx.fillText(text, Math.round(cx), by + 7.5 * SCALE);
  ctx.textAlign = 'left';
  ctx.restore();
}

const FURN_MAKERS: Record<string, () => HTMLCanvasElement> = {
  plant: makePlantSprite, coffee: makeCoffeeMachine, wb: makeWhiteboard,
  book: makeBookshelf, server: makeServerRack, printer: makePrinterSprite,
  vending: makeVendingMachine, fridge: makeFridgeSprite, sofa: makeSofaSprite,
  water: makeWaterCooler, bench: makeBenchSprite, tree: makeTreeSprite,
  ashtray: makeAshtraySprite, umbrella: makeUmbrellaTable,
};

function render(game: GameState, ctx: CanvasRenderingContext2D, runtimeMap: Record<string, AgentRuntimeStatus>, camera: Camera) {
  ctx.imageSmoothingEnabled = false;

  // Apply camera transform
  ctx.save();
  ctx.scale(camera.zoom, camera.zoom);
  ctx.translate(-camera.x, -camera.y);

  // LAYER 0: Background
  ctx.fillStyle = '#06060a';
  ctx.fillRect(0, 0, CW, CH);

  // Outdoor ground (y0-3 and y36-39)
  const outdoorTile = makeFloorTile('concrete', '#0a120a', '#101a10');
  for (let y = 0; y <= 3; y++)
    for (let x = 0; x < MAP_W; x++)
      ctx.drawImage(outdoorTile, 0, 0, 16, 16, x * TILE, y * TILE, TILE, TILE);
  for (let y = 36; y <= 39; y++)
    for (let x = 0; x < MAP_W; x++)
      ctx.drawImage(outdoorTile, 0, 0, 16, 16, x * TILE, y * TILE, TILE, TILE);

  // LAYER 1: Room floors
  for (const r of ROOMS) {
    const cfg = ROOM_FLOORS[r.team] || ROOM_FLOORS['경영지원팀'] || { type: 'tile', base: '#0c0c14', accent: '#141420' };
    const tile = makeFloorTile(cfg.type, cfg.base, cfg.accent);
    for (let y = r.y + 1; y < r.y + r.h - 1; y++)
      for (let x = r.x + 1; x < r.x + r.w - 1; x++)
        ctx.drawImage(tile, 0, 0, 16, 16, x * TILE, y * TILE, TILE, TILE);
  }
  // Hallway floors
  const hallTile = makeFloorTile('concrete', '#0c0c12', '#14141c');
  for (let x = 0; x < MAP_W; x++) {
    for (let y = 4; y <= 5; y++) ctx.drawImage(hallTile, 0, 0, 16, 16, x * TILE, y * TILE, TILE, TILE);
    for (let y = 18; y <= 21; y++) ctx.drawImage(hallTile, 0, 0, 16, 16, x * TILE, y * TILE, TILE, TILE);
    for (let y = 34; y <= 35; y++) ctx.drawImage(hallTile, 0, 0, 16, 16, x * TILE, y * TILE, TILE, TILE);
  }

  // LAYER 2: Grid lines (subtle)
  ctx.strokeStyle = 'rgba(255,255,255,0.012)'; ctx.lineWidth = 0.5 * SCALE;
  for (let x = 0; x <= CW; x += TILE) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CH); ctx.stroke(); }
  for (let y = 0; y <= CH; y += TILE) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CW, y); ctx.stroke(); }

  // LAYER 3: Room lighting
  for (const r of ROOMS) {
    const cx = (r.x + r.w / 2) * TILE, cy = (r.y + r.h / 2) * TILE;
    const radius = Math.max(r.w, r.h) * TILE * 0.6;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    grad.addColorStop(0, 'rgba(255, 240, 200, 0.04)'); grad.addColorStop(0.6, 'rgba(255, 240, 200, 0.015)'); grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = grad; ctx.fillRect(r.x * TILE, r.y * TILE, r.w * TILE, r.h * TILE);
  }

  // LAYER 4: Walls
  for (const r of ROOMS) {
    ctx.strokeStyle = r.wall; ctx.lineWidth = 2.5 * SCALE;
    ctx.strokeRect(r.x * TILE + 1 * SCALE, r.y * TILE + 1 * SCALE, r.w * TILE - 2 * SCALE, r.h * TILE - 2 * SCALE);
    ctx.strokeStyle = 'rgba(255,255,255,0.02)'; ctx.lineWidth = 1 * SCALE;
    ctx.strokeRect(r.x * TILE + 3 * SCALE, r.y * TILE + 3 * SCALE, r.w * TILE - 6 * SCALE, r.h * TILE - 6 * SCALE);
  }

  // Doors
  for (const [dx, dy] of DOORS) {
    ctx.fillStyle = '#0c0c12'; ctx.fillRect(dx * TILE - 1 * SCALE, dy * TILE, TILE + 2 * SCALE, TILE);
    ctx.fillStyle = 'rgba(255,255,255,0.04)';
    ctx.fillRect(dx * TILE, dy * TILE, 1 * SCALE, TILE);
    ctx.fillRect(dx * TILE + TILE - 1 * SCALE, dy * TILE, 1 * SCALE, TILE);
  }

  // LAYER 5: Room labels
  ctx.imageSmoothingEnabled = true; ctx.textAlign = 'left';
  for (const r of ROOMS) {
    const labelText = TEAM_EN[r.team] || r.team;
    ctx.font = `bold ${7 * SCALE}px monospace`;
    const tw = ctx.measureText(labelText).width;
    ctx.fillStyle = 'rgba(0,0,0,0.4)'; ctx.fillRect((r.x + 1) * TILE, r.y * TILE + 1 * SCALE, tw + 4 * SCALE, 10 * SCALE);
    ctx.fillStyle = r.label; ctx.globalAlpha = 0.7;
    ctx.fillText(labelText, (r.x + 1) * TILE + 2 * SCALE, r.y * TILE + 9 * SCALE);
    ctx.globalAlpha = 1;
  }
  // Hallway labels
  ctx.fillStyle = '#27272a'; ctx.font = `${5 * SCALE}px monospace`; ctx.textAlign = 'center';
  ctx.fillText('ENTRANCE', CW / 2, 4 * TILE + TILE + 4 * SCALE);
  ctx.fillText('— MAIN HALLWAY —', CW / 2, 19 * TILE + TILE + 4 * SCALE);
  ctx.fillText('EXIT', CW / 2, 34 * TILE + TILE + 4 * SCALE);
  // Outdoor labels
  ctx.fillStyle = '#1a3a1a'; ctx.globalAlpha = 0.6;
  ctx.fillText('PARKING', 10 * TILE, 1 * TILE + 4 * SCALE);
  ctx.fillText('GARDEN', 50 * TILE, 1 * TILE + 4 * SCALE);
  ctx.fillText('SMOKING AREA', 10 * TILE, 37 * TILE + 4 * SCALE);
  ctx.fillText('TERRACE', 30 * TILE, 37 * TILE + 4 * SCALE);
  ctx.fillText('ROOFTOP GARDEN', 50 * TILE, 37 * TILE + 4 * SCALE);
  ctx.globalAlpha = 1;
  ctx.textAlign = 'left'; ctx.imageSmoothingEnabled = false;

  // LAYER 6: Desks
  for (const d of DESKS) {
    const active = Array.from(game.chars.values()).some(ch =>
      ch.deskCol === d.sx && ch.deskRow === d.sy && ['type', 'read', 'think', 'search'].includes(ch.state)
    );
    ctx.fillStyle = 'rgba(0,0,0,0.12)'; ctx.fillRect(d.dx * TILE + 3 * SCALE, d.dy * TILE + 3 * SCALE, TILE - 4 * SCALE, TILE - 4 * SCALE);
    const desk = makeDeskSprite(active);
    ctx.drawImage(desk, 0, 0, 16, 16, d.dx * TILE, d.dy * TILE, TILE, TILE);
    if (active) {
      const cx = d.dx * TILE + TILE / 2, cy = d.dy * TILE + TILE / 4;
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, TILE * 1.2);
      grad.addColorStop(0, 'rgba(59, 130, 246, 0.06)'); grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = grad; ctx.fillRect(cx - TILE * 1.2, cy - TILE * 1.2, TILE * 2.4, TILE * 2.4);
    }
  }

  // LAYER 6b: Furniture
  for (const f of FURNITURE) {
    const maker = FURN_MAKERS[f.type];
    if (!maker) continue;
    const spr = maker();
    const fw = f.w ?? 1;
    ctx.drawImage(spr, 0, 0, 16, 16, f.x * TILE, f.y * TILE, TILE * fw, TILE);
  }

  // Coffee steam
  const steamT = Date.now() / 600;
  ctx.fillStyle = 'rgba(255,255,255,0.12)';
  for (let i = 0; i < 3; i++) {
    const sy = 19 * TILE - (2 + i * 3) * SCALE - ((steamT + i * 2) % 5) * SCALE;
    const sx = 30 * TILE + 6 * SCALE + Math.sin(steamT + i) * 1.5 * SCALE;
    ctx.fillRect(sx, sy, 2 * SCALE, 1 * SCALE);
  }

  // LAYER 7: Characters (Y-sorted)
  const sorted = Array.from(game.chars.values()).sort((a, b) => a.y - b.y);
  for (const c of sorted) {
    let f: Frame;
    if (c.state === 'type') f = typeFrame(c.typeFrame);
    else if (c.state === 'read' || c.state === 'search') f = readFrame(c.typeFrame);
    else if (c.state === 'think') f = thinkFrame(c.typeFrame);
    else if (c.state === 'walk') f = walkFrame(c.dir, c.walkStep);
    else f = walkFrame(c.dir, 0);

    const s = sprite(c.code, c.team, f);
    const dx = Math.round(c.x - DSW / 2);
    const dy = Math.round(c.y - DSH / 2);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(s, dx, dy, DSW, DSH);
    ctx.imageSmoothingEnabled = true;

    // Status indicator
    const runtime = runtimeMap[c.code];
    const isWorking = runtime?.status === 'working';
    const isError = runtime?.status === 'error';
    if (isWorking) {
      ctx.fillStyle = '#3b82f6'; ctx.globalAlpha = 0.6 + 0.4 * Math.sin(Date.now() / 300);
      ctx.beginPath(); ctx.arc(dx + DSW + 1 * SCALE, dy + 2 * SCALE, 2 * SCALE, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
      const iconName = getToolIcon(runtime?.current_tools || [], runtime?.current_node || null);
      if (iconName) {
        const shirtColor = SHIRT[c.team] || '#6b7280';
        drawToolIcon(ctx, iconName, Math.round(c.x + DSW / 2 + 2 * SCALE), Math.round(c.y - DSH / 2 - 2 * SCALE), shirtColor);
      }
    }
    if (isError) {
      ctx.fillStyle = '#ef4444'; ctx.globalAlpha = 0.6 + 0.4 * Math.sin(Date.now() / 200);
      ctx.font = `${6 * SCALE}px sans-serif`; ctx.fillText('!', dx + DSW - 1 * SCALE, dy);
      ctx.globalAlpha = 1;
    }

    // Speech bubble
    if (c.speechBubble && c.speechBubbleTimer > 0) {
      const alpha = c.speechBubbleTimer < 0.5 ? c.speechBubbleTimer / 0.5
        : Math.min(1, (SPEECH_BUBBLE_DURATION - c.speechBubbleTimer + 0.3) / 0.3);
      drawSpeechBubble(ctx, c.speechBubble, Math.round(c.x), dy, alpha);
    }

    // Emoji above head (when no speech bubble)
    if (!c.speechBubble && c.activity) {
      drawActivityEmoji(ctx, c.activity, c.x, c.y, DSH);
    }

    // Name + activity
    ctx.textAlign = 'center';
    ctx.fillStyle = isWorking ? '#93c5fd' : isError ? '#fca5a5' : '#d4d4d8';
    ctx.font = `bold ${5 * SCALE}px monospace`;
    ctx.fillText(getFirstName(c.code), Math.round(c.x), Math.round(c.y + DSH / 2 + 6 * SCALE));
    const activityText = isWorking
      ? (runtime?.current_task ? (runtime.current_task.length > 14 ? runtime.current_task.slice(0, 12) + '..' : runtime.current_task) : '작업 중')
      : c.activity || '';
    if (activityText) {
      ctx.fillStyle = isWorking ? '#93c5fd' : '#a1a1aa';
      ctx.font = `${3.5 * SCALE}px monospace`;
      ctx.fillText(activityText, Math.round(c.x), Math.round(c.y + DSH / 2 + 12 * SCALE));
    }
    ctx.textAlign = 'left';
  }

  // LAYER 8: Day/Night overlay
  const kstHour = new Date(Date.now() + 9 * 3600000).getUTCHours();
  let nightAlpha = 0;
  if (kstHour >= 22 || kstHour < 5) nightAlpha = 0.35;
  else if (kstHour >= 19) nightAlpha = (kstHour - 19) / 3 * 0.35;
  else if (kstHour < 7) nightAlpha = (7 - kstHour) / 2 * 0.35;
  if (nightAlpha > 0) {
    ctx.globalCompositeOperation = 'multiply';
    ctx.fillStyle = `rgba(25, 35, 70, ${nightAlpha})`; ctx.fillRect(0, 0, CW, CH);
    ctx.globalCompositeOperation = 'source-over';
    const vig = ctx.createRadialGradient(CW / 2, CH / 2, CW * 0.3, CW / 2, CH / 2, CW * 0.7);
    vig.addColorStop(0, 'rgba(0,0,0,0)'); vig.addColorStop(1, `rgba(0,0,0,${nightAlpha * 0.25})`);
    ctx.fillStyle = vig; ctx.fillRect(0, 0, CW, CH);
  }

  // LAYER 9: Dust particles
  if (nightAlpha < 0.1) {
    ctx.fillStyle = 'rgba(255, 248, 220, 0.06)';
    const t = Date.now() / 3000;
    for (let i = 0; i < 15; i++) {
      const px = ((t * 15 + i * 260) % CW);
      const py = ((Math.sin(t * 0.7 + i * 1.7) + 1) * 0.5 * CH);
      ctx.beginPath(); ctx.arc(px, py, (1 + Math.sin(t + i) * 0.5) * SCALE, 0, Math.PI * 2); ctx.fill();
    }
  }

  // LAYER 10: Clock (KST)
  ctx.imageSmoothingEnabled = true;
  const clkX = CW - 3 * TILE, clkY = 1 * SCALE;
  ctx.fillStyle = '#1e1e2e'; ctx.fillRect(clkX, clkY, 11 * SCALE, 7 * SCALE);
  ctx.strokeStyle = '#3f3f46'; ctx.lineWidth = 0.5 * SCALE; ctx.strokeRect(clkX, clkY, 11 * SCALE, 7 * SCALE);
  const kstMin = new Date(Date.now() + 9 * 3600000).getUTCMinutes();
  ctx.fillStyle = nightAlpha > 0.1 ? '#60a5fa' : '#a1a1aa';
  ctx.font = `${3.5 * SCALE}px monospace`;
  ctx.fillText(`${String(kstHour).padStart(2, '0')}:${String(kstMin).padStart(2, '0')}`, clkX + 1.5 * SCALE, clkY + 5 * SCALE);
  ctx.imageSmoothingEnabled = false;

  ctx.restore(); // pop camera transform
}

// ═══════════════════════════════════════════════════════════════════════════
// React Component
// ═══════════════════════════════════════════════════════════════════════════

import type { ActivityLogEntry, PixelOfficeProps } from './engine/types';

let _actLogId = 0;

export default function PixelOffice({ runtimeMap, hiredSet, onSelectAgent, agentBubbles, onActivityLog, muteChat }: PixelOfficeProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const gameRef = useRef<GameState | null>(null);
  const cameraRef = useRef<Camera>(createCamera(800, 600));
  const propsRef = useRef({ runtimeMap, hiredSet, onSelectAgent, agentBubbles, onActivityLog, muteChat });
  const [hovered, setHovered] = useState<string | null>(null);
  const [tipPos, setTipPos] = useState({ x: 0, y: 0 });

  propsRef.current = { runtimeMap, hiredSet, onSelectAgent, agentBubbles, onActivityLog, muteChat };

  // Build grid + init POIs once
  useEffect(() => {
    const grid = buildGrid();
    setGrid(grid);
    initPOIStates(POI_LIST);
  }, []);

  // Canvas resize
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const resize = () => {
      const rect = container.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = rect.width;
      const h = rect.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${Math.round(w)}px`;
      canvas.style.height = `${Math.round(h)}px`;
      const ctx = canvas.getContext('2d');
      if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      cameraRef.current.viewportW = w;
      cameraRef.current.viewportH = h;
      clampCamera(cameraRef.current);
    };
    resize();
    // Center on office area (rooms are y6-17, center around y=12 x=30)
    centerOn(cameraRef.current, 30 * TILE, 12 * TILE);
    const ro = new ResizeObserver(resize);
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // Game loop
  useEffect(() => {
    const game: GameState = { chars: new Map(), lastT: 0, rafId: 0, deskMap: new Map() };
    gameRef.current = game;

    const loop = (ts: number) => {
      const dt = game.lastT ? Math.min((ts - game.lastT) / 1000, 0.1) : 0.016;
      game.lastT = ts;
      const { runtimeMap: rm, hiredSet: hs, agentBubbles: bubbles } = propsRef.current;

      // Sync agents
      const newDeskMap = assignDesks(hs);
      Array.from(hs).forEach(code => {
        if (!game.chars.has(code)) {
          const desk = newDeskMap.get(code);
          if (desk) game.chars.set(code, initChar(code, desk));
        }
      });
      Array.from(game.chars.keys()).forEach(code => {
        if (!hs.has(code)) game.chars.delete(code);
      });
      game.deskMap = newDeskMap;

      // Update
      game.chars.forEach((ch, code) => {
        updateChar(ch, rm[code], dt);
        const bubble = bubbles?.[code];
        if (bubble && Date.now() - bubble.ts < 5000 && (!ch.speechBubble || ch.speechBubble !== bubble.text)) {
          ch.speechBubble = bubble.text.length > 22 ? bubble.text.slice(0, 20) + '..' : bubble.text;
          ch.speechBubbleTimer = SPEECH_BUBBLE_DURATION;
        }
      });

      // Spontaneous chat
      const { onActivityLog: emitLog, muteChat: muted } = propsRef.current;
      const chars = Array.from(game.chars.values());
      if (!muted) for (let i = 0; i < chars.length; i++) {
        const a = chars[i];
        if (a.state !== 'idle' || a.socialTimer > 0 || rm[a.code]?.status === 'working') continue;
        for (let j = i + 1; j < chars.length; j++) {
          const b = chars[j];
          if (b.state !== 'idle' || b.socialTimer > 0 || rm[b.code]?.status === 'working') continue;
          const dist = Math.abs(a.col - b.col) + Math.abs(a.row - b.row);
          if (dist <= 2 && Math.random() < 0.002) {
            a.dir = dirBetween(a.x, a.y, b.x, b.y);
            b.dir = dirBetween(b.x, b.y, a.x, a.y);
            a.socialTarget = b.code; b.socialTarget = a.code;
            const chatDur = 3 + Math.random() * 4;
            a.socialTimer = chatDur; b.socialTimer = chatDur;
            const nameA = getFirstName(a.code), nameB = getFirstName(b.code);
            a.activity = `${nameB}와 대화 중`; b.activity = `${nameA}와 대화 중`;
            const tpl = CHAT_TEMPLATES[Math.floor(Math.random() * CHAT_TEMPLATES.length)];
            a.speechBubble = tpl[0]; a.speechBubbleTimer = chatDur;
            b.speechBubble = tpl[1]; b.speechBubbleTimer = chatDur;
            const pA = getPersona(a.code), pB = getPersona(b.code);
            const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
            emitLog?.({
              id: ++_actLogId, time: now, type: 'chat',
              agentA: nameA, emojiA: pA?.emoji || '🤖',
              agentB: nameB, emojiB: pB?.emoji || '🤖',
              message: `"${tpl[0]}" — "${tpl[1]}"`,
            });
          }
        }
      }

      // POI arrival log
      game.chars.forEach(ch => {
        if (ch.state === 'idle' && ch.poiTarget) {
          const poi = POI_LIST.find(p => p.name === ch.poiTarget);
          if (poi) {
            const p = getPersona(ch.code);
            const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
            emitLog?.({
              id: ++_actLogId, time: now, type: 'move',
              agentA: getFirstName(ch.code), emojiA: p?.emoji || '🤖',
              message: poi.action,
            });
          }
        }
      });

      // Render
      const ctx = canvasRef.current?.getContext('2d');
      if (ctx) render(game, ctx, rm, cameraRef.current);

      game.rafId = requestAnimationFrame(loop);
    };
    game.rafId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(game.rafId);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Mouse handlers
  const getCanvasCoords = useCallback((e: React.MouseEvent): [number, number] => {
    const canvas = canvasRef.current;
    if (!canvas) return [0, 0];
    const rect = canvas.getBoundingClientRect();
    return [e.clientX - rect.left, e.clientY - rect.top];
  }, []);

  const findChar = useCallback((e: React.MouseEvent) => {
    const [sx, sy] = getCanvasCoords(e);
    const cam = cameraRef.current;
    const [wx, wy] = screenToWorld(cam, sx, sy);
    const game = gameRef.current;
    if (!game) return null;
    let found: string | null = null;
    game.chars.forEach((ch, code) => {
      if (!found && Math.abs(wx - ch.x) < 8 * SCALE && Math.abs(wy - ch.y) < 10 * SCALE) found = code;
    });
    return found;
  }, [getCanvasCoords]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button === 0) {
      const [sx, sy] = getCanvasCoords(e);
      startDrag(cameraRef.current, sx, sy);
    }
  }, [getCanvasCoords]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    const cam = cameraRef.current;
    if (cam.isDragging) {
      const [sx, sy] = getCanvasCoords(e);
      updateDrag(cam, sx, sy);
      setHovered(null);
    } else {
      const code = findChar(e);
      setHovered(code);
      if (code) setTipPos({ x: e.clientX, y: e.clientY });
    }
  }, [getCanvasCoords, findChar]);

  const handleMouseUp = useCallback((e: React.MouseEvent) => {
    const cam = cameraRef.current;
    const wasDragging = cam.isDragging;
    const dragDist = Math.abs(e.clientX - cam.dragStartX - (canvasRef.current?.getBoundingClientRect().left ?? 0)) +
                     Math.abs(e.clientY - cam.dragStartY - (canvasRef.current?.getBoundingClientRect().top ?? 0));
    endDrag(cam);
    // Only click if didn't drag significantly
    if (!wasDragging || dragDist < 5) {
      const code = findChar(e);
      if (code) propsRef.current.onSelectAgent(code);
    }
  }, [findChar]);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const [sx, sy] = getCanvasCoords(e);
    applyZoom(cameraRef.current, e.deltaY, sx, sy);
  }, [getCanvasCoords]);

  const hp = hovered ? getPersona(hovered) : null;
  const hr = hovered ? runtimeMap[hovered] : undefined;

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
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-1.5"
        style={{ background: 'linear-gradient(90deg,#0f0f14,#16161d,#0f0f14)', borderBottom: '2px solid #1e1e26' }}>
        <span style={{ fontSize: 11, fontFamily: 'monospace', fontWeight: 800, color: '#e4e4e7', letterSpacing: 2 }}>
          JINXUS CORP.
        </span>
        <div className="flex gap-2" style={{ fontSize: 9, fontFamily: 'monospace' }}>
          <span style={{ color: '#a1a1aa' }}>{hiredSet.size}명</span>
          {Object.values(runtimeMap).filter(r => r.status === 'working').length > 0 && (
            <span style={{ color: '#93c5fd' }}>{Object.values(runtimeMap).filter(r => r.status === 'working').length}명 작업중</span>
          )}
        </div>
      </div>

      {/* Canvas */}
      <div ref={containerRef} className="flex-1 min-h-0 flex items-center justify-center bg-[#08080c] overflow-hidden">
        <canvas
          ref={canvasRef}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => { setHovered(null); endDrag(cameraRef.current); }}
          onWheel={handleWheel}
          style={{ cursor: cameraRef.current?.isDragging ? 'grabbing' : hovered ? 'pointer' : 'grab' }}
        />
      </div>

      {/* Tooltip */}
      {hovered && hp && (
        <div className="fixed z-50 pointer-events-none"
          style={{
            left: tipPos.x + 12, top: tipPos.y - 10, padding: '6px 10px',
            background: '#1e1e2e', border: '1px solid #3f3f46', borderRadius: 6,
            boxShadow: '0 4px 16px rgba(0,0,0,0.6)', maxWidth: 200,
          }}>
          <p style={{ fontSize: 11, color: '#fff', fontWeight: 600 }}>{hp.emoji} {getDisplayName(hovered)}</p>
          <p style={{ fontSize: 9, color: '#a1a1aa', marginBottom: 3 }}>{getRole(hovered)}</p>
          <div className="flex items-center gap-1" style={{ fontSize: 9 }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
              background: hr?.status === 'working' ? '#3b82f6' : hr?.status === 'error' ? '#ef4444' : '#22c55e',
            }} />
            <span style={{ color: hr?.status === 'working' ? '#93c5fd' : hr?.status === 'error' ? '#fca5a5' : '#86efac' }}>
              {hr?.status === 'working' ? getWorkLabel(hr) : hr?.status === 'error' ? '오류' : '대기'}
            </span>
          </div>
          {hr?.status === 'working' && hr.current_task && (
            <p style={{ fontSize: 8, color: '#93c5fd', marginTop: 3, wordBreak: 'break-all' }}>작업: {hr.current_task}</p>
          )}
          {hr?.current_tools && hr.current_tools.length > 0 && (
            <p style={{ fontSize: 7, color: '#71717a', marginTop: 2 }}>도구: {hr.current_tools.join(', ')}</p>
          )}
          {hr?.current_node && (
            <p style={{ fontSize: 7, color: '#52525b', marginTop: 1 }}>노드: {hr.current_node}</p>
          )}
          <p style={{ fontSize: 7, color: '#52525b', marginTop: 3 }}>클릭하여 대화</p>
        </div>
      )}

      {/* Footer */}
      <div className="flex-shrink-0 px-3 py-1 text-center"
        style={{ fontSize: 8, color: '#3f3f46', fontFamily: 'monospace', background: '#0a0a0e', borderTop: '1px solid #1e1e26' }}>
        드래그로 이동 · 스크롤로 줌 · 캐릭터 클릭으로 대화
      </div>
    </div>
  );
}
