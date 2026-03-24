import type { IconGrid, WorkState } from '../engine/types';
import type { AgentRuntimeStatus } from '@/lib/api';

// ═══════════════════════════════════════════════════════════════════════════
// 도구 아이콘 (5x5 픽셀)
// ═══════════════════════════════════════════════════════════════════════════

export const TOOL_ICONS: Record<string, IconGrid> = {
  terminal: [
    [1,0,0,0,0],
    [0,1,0,0,0],
    [1,0,0,0,0],
    [0,0,0,0,0],
    [0,1,1,1,0],
  ],
  magnifier: [
    [0,1,1,0,0],
    [1,0,0,1,0],
    [0,1,1,0,0],
    [0,0,0,1,0],
    [0,0,0,0,1],
  ],
  pencil: [
    [0,0,0,0,1],
    [0,0,0,1,0],
    [0,0,1,0,0],
    [0,1,0,0,0],
    [1,0,0,0,0],
  ],
  brain: [
    [0,1,1,1,0],
    [1,1,0,1,1],
    [1,0,1,0,1],
    [1,1,0,1,1],
    [0,1,1,1,0],
  ],
  globe: [
    [0,1,1,1,0],
    [1,0,1,0,1],
    [1,1,1,1,1],
    [1,0,1,0,1],
    [0,1,1,1,0],
  ],
};

/** Map active tools + node → icon name */
export function getToolIcon(tools: string[], node: string | null): string | null {
  const toolStr = (tools.join(' ') + ' ' + (node || '')).toLowerCase();
  if (toolStr.match(/plan|reflect|evaluate|think/)) return 'brain';
  if (toolStr.match(/code_executor|bash|execute/)) return 'terminal';
  if (toolStr.match(/write|edit|self_modifier/)) return 'pencil';
  if (toolStr.match(/read|grep|glob|pdf|rss/)) return 'magnifier';
  if (toolStr.match(/web_searcher|fetch|brave|searcher|naver|search/)) return 'globe';
  if (tools.length > 0) return 'terminal';
  return null;
}

/** Determine work animation state from runtime */
export function getWorkState(runtime: AgentRuntimeStatus | undefined): WorkState {
  const tools = runtime?.current_tools || [];
  const node = runtime?.current_node || '';

  if (node === 'plan' || node === 'reflect' || node === 'evaluate') return 'think';

  const toolStr = tools.join(' ').toLowerCase();
  if (toolStr.match(/read|grep|glob|pdf|rss/)) return 'read';
  if (toolStr.match(/web_searcher|fetch|brave|searcher|naver|search/)) return 'search';
  return 'type';
}
