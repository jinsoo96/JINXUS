import type { POIDef } from '../engine/types';

// ═══════════════════════════════════════════════════════════════════════════
// POI State Manager — tracks who's using each POI, capacity, queue
// ═══════════════════════════════════════════════════════════════════════════

interface POIState {
  users: Set<string>;       // agent codes currently using this POI
  capacity: number;         // max simultaneous users
}

const poiStates = new Map<string, POIState>();

/** Initialize POI states from POI definitions */
export function initPOIStates(pois: POIDef[]): void {
  poiStates.clear();
  for (const poi of pois) {
    poiStates.set(poi.name, {
      users: new Set(),
      capacity: poi.capacity ?? 2,
    });
  }
}

/** Check if a POI has available capacity */
export function isPOIAvailable(poiName: string): boolean {
  const state = poiStates.get(poiName);
  if (!state) return true;
  return state.users.size < state.capacity;
}

/** Register an agent as using a POI */
export function occupyPOI(poiName: string, agentCode: string): boolean {
  const state = poiStates.get(poiName);
  if (!state) return true; // unknown POI, allow anyway
  if (state.users.size >= state.capacity) return false;
  state.users.add(agentCode);
  return true;
}

/** Release an agent from a POI */
export function releasePOI(poiName: string, agentCode: string): void {
  const state = poiStates.get(poiName);
  if (state) state.users.delete(agentCode);
}

/** Release an agent from all POIs */
export function releaseAllPOIs(agentCode: string): void {
  Array.from(poiStates.values()).forEach(state => {
    state.users.delete(agentCode);
  });
}

/** Get list of agents at a POI */
export function getPOIUsers(poiName: string): string[] {
  return Array.from(poiStates.get(poiName)?.users ?? []);
}
