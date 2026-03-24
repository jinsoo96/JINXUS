import { MAP_W, MAP_H } from './constants';

// ═══════════════════════════════════════════════════════════════════════════
// BFS Pathfinding
// ═══════════════════════════════════════════════════════════════════════════

let GRID: boolean[][] = [];

/** Set the walkable grid (must be called after map data is built) */
export function setGrid(grid: boolean[][]): void {
  GRID = grid;
}

/** Get the current grid */
export function getGrid(): boolean[][] {
  return GRID;
}

/** BFS pathfind from (sx,sy) to (ex,ey). Returns path excluding start. */
export function bfs(sx: number, sy: number, ex: number, ey: number): [number, number][] {
  if (sx === ex && sy === ey) return [];
  if (!GRID[ey]?.[ex]) return [];
  const visited = new Set<string>();
  const parent = new Map<string, string>();
  const q: [number, number][] = [[sx, sy]];
  visited.add(`${sx},${sy}`);
  const dirs = [[0, 1], [0, -1], [1, 0], [-1, 0]];
  while (q.length) {
    const [cx, cy] = q.shift()!;
    if (cx === ex && cy === ey) {
      const path: [number, number][] = [];
      let k = `${ex},${ey}`;
      while (k !== `${sx},${sy}`) {
        const [a, b] = k.split(',').map(Number);
        path.unshift([a, b]);
        k = parent.get(k)!;
      }
      return path;
    }
    for (const [ddx, ddy] of dirs) {
      const nx = cx + ddx, ny = cy + ddy;
      const nk = `${nx},${ny}`;
      if (nx >= 0 && nx < MAP_W && ny >= 0 && ny < MAP_H && GRID[ny]?.[nx] && !visited.has(nk)) {
        visited.add(nk);
        parent.set(nk, `${cx},${cy}`);
        q.push([nx, ny]);
      }
    }
  }
  return [];
}
