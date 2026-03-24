import { MAP_W, MAP_H, TILE } from './constants';

// ═══════════════════════════════════════════════════════════════════════════
// Camera / Viewport system — drag scroll, zoom, minimap support
// ═══════════════════════════════════════════════════════════════════════════

export interface Camera {
  x: number;
  y: number;
  zoom: number;
  viewportW: number;
  viewportH: number;
  isDragging: boolean;
  dragStartX: number;
  dragStartY: number;
  dragCamStartX: number;
  dragCamStartY: number;
}

export function createCamera(viewportW: number, viewportH: number): Camera {
  return {
    x: 0,
    y: 0,
    zoom: 1,
    viewportW,
    viewportH,
    isDragging: false,
    dragStartX: 0,
    dragStartY: 0,
    dragCamStartX: 0,
    dragCamStartY: 0,
  };
}

/** Convert screen coordinates to world coordinates */
export function screenToWorld(camera: Camera, sx: number, sy: number): [number, number] {
  return [
    camera.x + sx / camera.zoom,
    camera.y + sy / camera.zoom,
  ];
}

/** Convert world coordinates to screen coordinates */
export function worldToScreen(camera: Camera, wx: number, wy: number): [number, number] {
  return [
    (wx - camera.x) * camera.zoom,
    (wy - camera.y) * camera.zoom,
  ];
}

/** Clamp camera position to keep it within map bounds */
export function clampCamera(camera: Camera): void {
  const mapPxW = MAP_W * TILE;
  const mapPxH = MAP_H * TILE;
  const visW = camera.viewportW / camera.zoom;
  const visH = camera.viewportH / camera.zoom;

  // If viewport is larger than map, center
  if (visW >= mapPxW) {
    camera.x = -(visW - mapPxW) / 2;
  } else {
    camera.x = Math.max(0, Math.min(camera.x, mapPxW - visW));
  }

  if (visH >= mapPxH) {
    camera.y = -(visH - mapPxH) / 2;
  } else {
    camera.y = Math.max(0, Math.min(camera.y, mapPxH - visH));
  }
}

/** Center camera on a world position */
export function centerOn(camera: Camera, wx: number, wy: number): void {
  camera.x = wx - (camera.viewportW / camera.zoom) / 2;
  camera.y = wy - (camera.viewportH / camera.zoom) / 2;
  clampCamera(camera);
}

/** Apply zoom (centered on screen point) */
export function applyZoom(camera: Camera, delta: number, sx: number, sy: number): void {
  const [wx, wy] = screenToWorld(camera, sx, sy);
  const minZoom = 0.3;
  const maxZoom = 2.0;
  camera.zoom = Math.max(minZoom, Math.min(maxZoom, camera.zoom * (1 - delta * 0.001)));
  // Keep the world point under the cursor
  camera.x = wx - sx / camera.zoom;
  camera.y = wy - sy / camera.zoom;
  clampCamera(camera);
}

/** Start drag */
export function startDrag(camera: Camera, sx: number, sy: number): void {
  camera.isDragging = true;
  camera.dragStartX = sx;
  camera.dragStartY = sy;
  camera.dragCamStartX = camera.x;
  camera.dragCamStartY = camera.y;
}

/** Update drag */
export function updateDrag(camera: Camera, sx: number, sy: number): void {
  if (!camera.isDragging) return;
  const dx = (sx - camera.dragStartX) / camera.zoom;
  const dy = (sy - camera.dragStartY) / camera.zoom;
  camera.x = camera.dragCamStartX - dx;
  camera.y = camera.dragCamStartY - dy;
  clampCamera(camera);
}

/** End drag */
export function endDrag(camera: Camera): void {
  camera.isDragging = false;
}
