'use client';

import { useRef, useEffect, useCallback, useState } from 'react';
import type { ToolGraphVizNode, ToolGraphVizEdge } from '@/lib/api';

// ── 물리 상수 ──
const REPULSION = 8000;
const ATTRACTION = 0.004;
const DAMPING = 0.92;
const MIN_VELOCITY = 0.01;
const CENTER_GRAVITY = 0.002;

// ── 색상 ──
const CAT_COLORS: Record<string, { fill: string; stroke: string }> = {
  development: { fill: '#3b82f620', stroke: '#3b82f6' },
  research:    { fill: '#8b5cf620', stroke: '#8b5cf6' },
  github:      { fill: '#71717a20', stroke: '#a1a1aa' },
  filesystem:  { fill: '#22c55e20', stroke: '#22c55e' },
  automation:  { fill: '#f59e0b20', stroke: '#f59e0b' },
  system:      { fill: '#ef444420', stroke: '#ef4444' },
  management:  { fill: '#06b6d420', stroke: '#06b6d4' },
  general:     { fill: '#71717a20', stroke: '#71717a' },
};
const MCP_COLOR = { fill: '#10b98120', stroke: '#10b981' };

const EDGE_COLORS: Record<string, string> = {
  precedes:      '#3b82f6',
  requires:      '#ef4444',
  similar_to:    '#22c55e',
  complementary: '#a78bfa',
  conflicts:     '#f59e0b',
  belongs_to:    '#71717a',
};

interface PhysicsNode {
  id: string;
  label: string;
  description: string;
  category: string;
  weight: number;
  source: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
}

interface Props {
  nodes: ToolGraphVizNode[];
  edges: ToolGraphVizEdge[];
  width?: number;
  height?: number;
}

export default function ToolGraphViz({ nodes, edges, width = 900, height = 600 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const physicsRef = useRef<PhysicsNode[]>([]);
  const edgesRef = useRef<ToolGraphVizEdge[]>(edges);
  const rafRef = useRef<number>(0);
  const dragRef = useRef<{ nodeIdx: number; offsetX: number; offsetY: number } | null>(null);
  const hoverRef = useRef<number>(-1);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; node: PhysicsNode } | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const scaleRef = useRef(1);
  const panRef = useRef({ x: 0, y: 0 });
  const settledRef = useRef(false);
  const frameCountRef = useRef(0);

  // 초기화: 노드 물리 객체 생성
  useEffect(() => {
    // 엣지가 있는 노드만 표시 (연결된 노드)
    const connected = new Set<string>();
    edges.forEach(e => { connected.add(e.source); connected.add(e.target); });
    const visibleNodes = connected.size > 0
      ? nodes.filter(n => connected.has(n.id))
      : nodes.filter(n => !n.id.startsWith('mcp:'));

    const cx = width / 2, cy = height / 2;
    physicsRef.current = visibleNodes.map((n, i) => {
      const angle = (2 * Math.PI * i) / visibleNodes.length;
      const r = Math.min(width, height) * 0.35;
      return {
        id: n.id,
        label: n.label,
        description: n.description,
        category: n.category,
        weight: n.weight,
        source: n.source,
        x: cx + r * Math.cos(angle) + (Math.random() - 0.5) * 20,
        y: cy + r * Math.sin(angle) + (Math.random() - 0.5) * 20,
        vx: 0,
        vy: 0,
        radius: Math.max(12, Math.min(24, n.weight * 14)),
      };
    });
    edgesRef.current = edges;
    settledRef.current = false;
    frameCountRef.current = 0;
  }, [nodes, edges, width, height]);

  // 물리 시뮬레이션 + 렌더링
  const simulate = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const pNodes = physicsRef.current;
    const pEdges = edgesRef.current;
    const cx = width / 2, cy = height / 2;

    // 물리 업데이트 (정착 후 스킵)
    if (!settledRef.current) {
      // 반발력 (Coulomb)
      for (let i = 0; i < pNodes.length; i++) {
        for (let j = i + 1; j < pNodes.length; j++) {
          const dx = pNodes[j].x - pNodes[i].x;
          const dy = pNodes[j].y - pNodes[i].y;
          const dist2 = dx * dx + dy * dy + 1;
          const dist = Math.sqrt(dist2);
          const force = REPULSION / dist2;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          pNodes[i].vx -= fx;
          pNodes[i].vy -= fy;
          pNodes[j].vx += fx;
          pNodes[j].vy += fy;
        }
      }

      // 인력 (Hooke) — 엣지 기반
      const nodeMap = new Map(pNodes.map((n, i) => [n.id, i]));
      for (const edge of pEdges) {
        const si = nodeMap.get(edge.source);
        const ti = nodeMap.get(edge.target);
        if (si === undefined || ti === undefined) continue;
        const dx = pNodes[ti].x - pNodes[si].x;
        const dy = pNodes[ti].y - pNodes[si].y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 1;
        const force = ATTRACTION * dist * edge.weight;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        pNodes[si].vx += fx;
        pNodes[si].vy += fy;
        pNodes[ti].vx -= fx;
        pNodes[ti].vy -= fy;
      }

      // 중심 인력
      let totalKinetic = 0;
      for (const node of pNodes) {
        if (dragRef.current && pNodes[dragRef.current.nodeIdx] === node) continue;
        node.vx += (cx - node.x) * CENTER_GRAVITY;
        node.vy += (cy - node.y) * CENTER_GRAVITY;
        node.vx *= DAMPING;
        node.vy *= DAMPING;
        node.x += node.vx;
        node.y += node.vy;
        totalKinetic += node.vx * node.vx + node.vy * node.vy;
      }

      frameCountRef.current++;
      if (frameCountRef.current > 300 && totalKinetic / pNodes.length < MIN_VELOCITY * MIN_VELOCITY) {
        settledRef.current = true;
      }
    }

    // ── 렌더링 ──
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    ctx.save();
    ctx.translate(panRef.current.x, panRef.current.y);
    ctx.scale(scaleRef.current, scaleRef.current);

    const nodeMap = new Map(pNodes.map((n, i) => [n.id, i]));

    // 엣지 렌더링
    for (const edge of pEdges) {
      const si = nodeMap.get(edge.source);
      const ti = nodeMap.get(edge.target);
      if (si === undefined || ti === undefined) continue;
      const s = pNodes[si], t = pNodes[ti];

      const dim = selectedNode && edge.source !== selectedNode && edge.target !== selectedNode;

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(t.x, t.y);
      ctx.strokeStyle = EDGE_COLORS[edge.type] || '#71717a';
      ctx.globalAlpha = dim ? 0.06 : 0.4;
      ctx.lineWidth = dim ? 0.5 : 1.2;
      ctx.stroke();

      // 화살표 (direction indicators)
      if (!dim && edge.type !== 'similar_to' && edge.type !== 'complementary') {
        const dx = t.x - s.x, dy = t.y - s.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > 0) {
          const nx = dx / dist, ny = dy / dist;
          const ax = t.x - nx * (t.radius + 4), ay = t.y - ny * (t.radius + 4);
          const arrowSize = 5;
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(ax - nx * arrowSize + ny * arrowSize * 0.5, ay - ny * arrowSize - nx * arrowSize * 0.5);
          ctx.lineTo(ax - nx * arrowSize - ny * arrowSize * 0.5, ay - ny * arrowSize + nx * arrowSize * 0.5);
          ctx.closePath();
          ctx.fillStyle = EDGE_COLORS[edge.type] || '#71717a';
          ctx.globalAlpha = 0.6;
          ctx.fill();
        }
      }
    }

    ctx.globalAlpha = 1;

    // 노드 렌더링
    for (let i = 0; i < pNodes.length; i++) {
      const node = pNodes[i];
      const isHovered = hoverRef.current === i;
      const isSelected = selectedNode === node.id;
      const isConnected = selectedNode
        ? pEdges.some(e =>
            (e.source === selectedNode && e.target === node.id) ||
            (e.target === selectedNode && e.source === node.id))
        : false;
      const dim = selectedNode && !isSelected && !isConnected;

      const colors = node.source === 'mcp'
        ? MCP_COLOR
        : (CAT_COLORS[node.category] || CAT_COLORS.general);

      ctx.globalAlpha = dim ? 0.15 : 1;

      // 선택/호버 하이라이트 원
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius + 6, 0, Math.PI * 2);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.globalAlpha = 0.25;
        ctx.stroke();
        ctx.globalAlpha = dim ? 0.15 : 1;
      }
      if (isConnected && !isSelected) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius + 4, 0, Math.PI * 2);
        ctx.strokeStyle = colors.stroke;
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.35;
        ctx.stroke();
        ctx.globalAlpha = dim ? 0.15 : 1;
      }

      // 노드 원
      ctx.beginPath();
      ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
      ctx.fillStyle = colors.fill;
      ctx.fill();
      ctx.strokeStyle = colors.stroke;
      ctx.lineWidth = isSelected ? 2.5 : isHovered ? 2 : 1.2;
      ctx.stroke();

      // 레이블
      ctx.fillStyle = '#d4d4d8';
      ctx.font = '9px system-ui, sans-serif';
      ctx.textAlign = 'center';
      const shortLabel = node.label.replace(/^mcp:/, '').split(':').pop() || node.label;
      const parts = shortLabel.split('_');
      if (parts.length > 1 && !dim) {
        ctx.fillText(parts[0], node.x, node.y + node.radius + 11);
        ctx.fillText(parts.slice(1).join('_').slice(0, 12), node.x, node.y + node.radius + 21);
      } else {
        ctx.fillText(shortLabel.slice(0, 14), node.x, node.y + node.radius + 11);
      }
    }

    ctx.restore();
    ctx.globalAlpha = 1;

    rafRef.current = requestAnimationFrame(simulate);
  }, [width, height, selectedNode]);

  useEffect(() => {
    rafRef.current = requestAnimationFrame(simulate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [simulate]);

  // 마우스 → 물리 좌표 변환
  const toPhysics = useCallback((clientX: number, clientY: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const x = (clientX - rect.left - panRef.current.x) / scaleRef.current;
    const y = (clientY - rect.top - panRef.current.y) / scaleRef.current;
    return { x, y };
  }, []);

  const findNodeAt = useCallback((px: number, py: number): number => {
    const pNodes = physicsRef.current;
    for (let i = pNodes.length - 1; i >= 0; i--) {
      const dx = px - pNodes[i].x, dy = py - pNodes[i].y;
      if (dx * dx + dy * dy <= pNodes[i].radius * pNodes[i].radius) return i;
    }
    return -1;
  }, []);

  // 이벤트 핸들러
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    const { x, y } = toPhysics(e.clientX, e.clientY);
    const idx = findNodeAt(x, y);
    if (idx >= 0) {
      dragRef.current = { nodeIdx: idx, offsetX: x - physicsRef.current[idx].x, offsetY: y - physicsRef.current[idx].y };
      settledRef.current = false;
    }
  }, [toPhysics, findNodeAt]);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    const { x, y } = toPhysics(e.clientX, e.clientY);
    if (dragRef.current) {
      const node = physicsRef.current[dragRef.current.nodeIdx];
      node.x = x - dragRef.current.offsetX;
      node.y = y - dragRef.current.offsetY;
      node.vx = 0;
      node.vy = 0;
    }
    const idx = findNodeAt(x, y);
    hoverRef.current = idx;
    if (idx >= 0) {
      const canvas = canvasRef.current;
      if (canvas) {
        const rect = canvas.getBoundingClientRect();
        setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, node: physicsRef.current[idx] });
      }
    } else {
      setTooltip(null);
    }
  }, [toPhysics, findNodeAt]);

  const onMouseUp = useCallback(() => {
    if (dragRef.current) {
      const idx = dragRef.current.nodeIdx;
      setSelectedNode(prev => prev === physicsRef.current[idx].id ? null : physicsRef.current[idx].id);
      dragRef.current = null;
    }
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.3, Math.min(3, scaleRef.current * delta));
    scaleRef.current = newScale;
    settledRef.current = false;
  }, []);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        style={{ width, height, cursor: hoverRef.current >= 0 ? 'grab' : 'default' }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => { dragRef.current = null; hoverRef.current = -1; setTooltip(null); }}
        onWheel={onWheel}
      />
      {tooltip && (
        <div
          className="absolute pointer-events-none bg-zinc-900/95 border border-zinc-700 rounded-lg px-3 py-2 text-xs max-w-xs z-10"
          style={{ left: tooltip.x + 12, top: tooltip.y - 8 }}
        >
          <div className="font-semibold text-white font-mono">{tooltip.node.label}</div>
          <div className="text-zinc-400 mt-0.5">{tooltip.node.description.slice(0, 100)}</div>
          <div className="flex items-center gap-2 mt-1 text-zinc-500">
            <span className="px-1.5 py-0.5 rounded bg-zinc-800">{tooltip.node.category}</span>
            <span>{tooltip.node.source === 'mcp' ? 'MCP' : 'Native'}</span>
            {tooltip.node.weight !== 1.0 && <span>w={tooltip.node.weight.toFixed(1)}</span>}
          </div>
        </div>
      )}
      {/* 범례 */}
      <div className="absolute bottom-2 left-2 flex flex-wrap gap-3 text-[10px] text-zinc-500 bg-zinc-900/80 rounded-lg px-3 py-1.5">
        {Object.entries(EDGE_COLORS)
          .filter(([t]) => t !== 'belongs_to')
          .map(([type, color]) => (
            <div key={type} className="flex items-center gap-1">
              <div className="h-px w-4" style={{ backgroundColor: color }} />
              {type.replace('_', ' ')}
            </div>
          ))}
      </div>
      {selectedNode && (
        <button
          onClick={() => setSelectedNode(null)}
          className="absolute top-2 right-2 text-xs text-zinc-500 hover:text-white bg-zinc-800/80 rounded px-2 py-1"
        >
          선택 해제
        </button>
      )}
    </div>
  );
}
