import type { AgentRuntimeStatus } from '@/lib/api';

// ── Sprite data types ──
export type Row = number[];
export type Frame = Row[];
export type IconGrid = number[][];

// ── Work state (tool/node based) ──
export type WorkState = 'type' | 'read' | 'think' | 'search';

// ── Character state ──
export interface CharState {
  code: string;
  team: string;
  col: number;
  row: number;       // current tile
  x: number;
  y: number;         // pixel (tile center)
  path: [number, number][];
  pathIdx: number;
  dir: number;       // 0=down 1=left 2=right 3=up
  walkStep: number;
  animT: number;
  state: 'idle' | 'walk' | 'type' | 'read' | 'think' | 'search';
  deskCol: number;
  deskRow: number;
  deskDir: number;
  idleTimer: number;
  typeFrame: number;
  // speech bubble
  speechBubble: string | null;
  speechBubbleTimer: number;
  // previous status tracking
  prevStatus: string | null;
  // Generative Agents: behavior state
  activity: string;
  poiTarget: string | null;
  socialTarget: string | null;
  socialTimer: number;
  // Smoking effect
  smokingTimer: number;  // >0 means currently smoking
  smokeAnchorCol: number;  // 흡연 시작 위치 (서성이기 범위 제한용)
  smokeAnchorRow: number;
}

// ── Map layout types ──
export interface RoomDef {
  team: string;
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  wall: string;
  label: string;
}

export interface DeskDef {
  team: string;
  dx: number;
  dy: number;
  sx: number;
  sy: number;
  dir: number;
}

export interface POIDef {
  name: string;
  col: number;
  row: number;
  action: string;
  capacity?: number;
  type?: 'indoor' | 'outdoor';
}

// ── Activity log entry (exported for MissionTab) ──
export interface ActivityLogEntry {
  id: number;
  time: string;
  agentA: string;
  emojiA: string;
  agentB?: string;
  emojiB?: string;
  message: string;
  type: 'chat' | 'move' | 'work' | 'arrive';
}

// ── PixelOffice props ──
export interface PixelOfficeProps {
  runtimeMap: Record<string, AgentRuntimeStatus>;
  hiredSet: Set<string>;
  onSelectAgent: (code: string) => void;
  agentBubbles?: Record<string, { text: string; ts: number }>;
  onActivityLog?: (entry: ActivityLogEntry) => void;
  muteChat?: boolean;
}

// ── Game state ──
export interface GameState {
  chars: Map<string, CharState>;
  lastT: number;
  rafId: number;
  deskMap: Map<string, DeskDef>;
}
