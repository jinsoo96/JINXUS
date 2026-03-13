'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { agentApi, AgentRuntimeStatus, AgentGraph, GraphNode } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import toast from 'react-hot-toast';
import {
  GitBranch, RefreshCw, ChevronDown, Play, Pause,
  Plus, Trash2, Link, Unlink, Edit3, Check, X,
} from 'lucide-react';

// ─── 타입 ──────────────────────────────────────────────────────────────
interface Pos { x: number; y: number }
interface LocalNode extends GraphNode { pos: Pos }
interface LocalEdge { from: string; to: string }
interface LocalGraph { agent_name: string; nodes: LocalNode[]; edges: LocalEdge[]; current_node: string | null }

// ─── 기본 그래프 ────────────────────────────────────────────────────────
const DEFAULT_GRAPHS: Record<string, { nodes: GraphNode[]; edges: { from: string; to: string }[] }> = {
  JINXUS_CORE: {
    nodes: [
      { id: 'intake',       label: 'intake',       description: '입력 수신 및 컨텍스트 로드' },
      { id: 'decompose',    label: 'decompose',     description: '명령 분해 및 서브태스크 생성' },
      { id: 'dispatch',     label: 'dispatch',      description: '에이전트 할당 및 실행' },
      { id: 'aggregate',    label: 'aggregate',     description: '결과 취합' },
      { id: 'reflect',      label: 'reflect',       description: '작업 반성 및 품질 평가' },
      { id: 'memory_write', label: 'memory_write',  description: '메모리 저장' },
      { id: 'respond',      label: 'respond',       description: '최종 응답 생성' },
    ],
    edges: [
      { from: 'intake', to: 'decompose' },
      { from: 'decompose', to: 'dispatch' },
      { from: 'dispatch', to: 'aggregate' },
      { from: 'aggregate', to: 'reflect' },
      { from: 'reflect', to: 'memory_write' },
      { from: 'memory_write', to: 'respond' },
      { from: 'reflect', to: 'dispatch' },  // 재시도 루프
    ],
  },
  DEFAULT: {
    nodes: [
      { id: 'receive',      label: 'receive',      description: '작업 수신' },
      { id: 'plan',         label: 'plan',         description: '실행 계획 수립' },
      { id: 'execute',      label: 'execute',      description: '도구 실행' },
      { id: 'evaluate',     label: 'evaluate',     description: '결과 평가' },
      { id: 'reflect',      label: 'reflect',      description: '반성' },
      { id: 'memory_write', label: 'memory_write', description: '메모리 저장' },
      { id: 'return',       label: 'return',       description: '결과 반환' },
    ],
    edges: [
      { from: 'receive', to: 'plan' },
      { from: 'plan', to: 'execute' },
      { from: 'execute', to: 'evaluate' },
      { from: 'evaluate', to: 'reflect' },
      { from: 'reflect', to: 'memory_write' },
      { from: 'memory_write', to: 'return' },
      { from: 'evaluate', to: 'execute' },  // 재실행 루프
    ],
  },
};

// ─── 초기 레이아웃 계산 (위상정렬 기반 DAG 레이아웃) ────────────────────
function computeLayout(nodes: GraphNode[], edges: { from: string; to: string }[]): Record<string, Pos> {
  const W = 760, NODE_W = 110, NODE_H = 44, H_GAP = 50, V_GAP = 80;

  // 진입 차수 계산
  const inDegree: Record<string, number> = {};
  const adjOut: Record<string, string[]> = {};
  for (const n of nodes) { inDegree[n.id] = 0; adjOut[n.id] = []; }
  for (const e of edges) {
    inDegree[e.to] = (inDegree[e.to] || 0) + 1;
    adjOut[e.from].push(e.to);
  }

  // BFS 레이어 계산
  const layers: string[][] = [];
  let queue = nodes.filter(n => inDegree[n.id] === 0).map(n => n.id);
  const visited = new Set<string>();
  while (queue.length > 0) {
    layers.push([...queue]);
    queue.forEach(id => visited.add(id));
    const next: string[] = [];
    for (const id of queue) {
      for (const to of (adjOut[id] || [])) {
        if (!visited.has(to)) {
          inDegree[to]--;
          if (inDegree[to] === 0) next.push(to);
        }
      }
    }
    queue = next;
  }
  // 방문 안 된 노드 (사이클) 마지막 레이어에 추가
  const remaining = nodes.filter(n => !visited.has(n.id)).map(n => n.id);
  if (remaining.length > 0) layers.push(remaining);

  const pos: Record<string, Pos> = {};
  layers.forEach((layer, li) => {
    const y = 60 + li * (NODE_H + V_GAP);
    const totalW = layer.length * NODE_W + (layer.length - 1) * H_GAP;
    const startX = Math.max(60, (W - totalW) / 2);
    layer.forEach((id, ni) => {
      pos[id] = { x: startX + ni * (NODE_W + H_GAP), y };
    });
  });
  return pos;
}

// ─── 엣지 베지어 곡선 경로 계산 ───────────────────────────────────────
function edgePath(sx: number, sy: number, tx: number, ty: number, nw: number, nh: number): string {
  const x1 = sx + nw / 2, y1 = sy + nh;
  const x2 = tx + nw / 2, y2 = ty;
  const cy = (y1 + y2) / 2;
  if (y2 <= y1) {
    // 역방향 엣지 (루프) — 오른쪽 우회
    const mx = Math.max(sx, tx) + nw + 40;
    return `M ${x1} ${y1} C ${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`;
  }
  return `M ${x1} ${y1} C ${x1} ${cy} ${x2} ${cy} ${x2} ${y2}`;
}

// ─── 메인 컴포넌트 ─────────────────────────────────────────────────────
export default function GraphTab() {
  const { agents: registeredAgents, loadAgents } = useAppStore();
  const [selectedAgent, setSelectedAgent] = useState('JINXUS_CORE');
  const [agentStatuses, setAgentStatuses] = useState<AgentRuntimeStatus[]>([]);
  const [graph, setGraph] = useState<LocalGraph | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // 편집 모드
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);          // 노드 설명 편집
  const [editLabel, setEditLabel] = useState('');
  const [editDesc, setEditDesc] = useState('');
  const [addEdgeMode, setAddEdgeMode] = useState(false);    // 엣지 추가 모드
  const [edgeSource, setEdgeSource] = useState<string | null>(null);

  // 드래그
  const dragRef = useRef<{ id: string; ox: number; oy: number; mx: number; my: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const graphRef = useRef<LocalGraph | null>(null); // stale closure 방지용
  const agentList = registeredAgents.length > 0 ? registeredAgents.map(a => a.name) : ['JINXUS_CORE'];

  // graph state → ref 동기화 (onSVGMouseUp 등 stale closure 방지)
  useEffect(() => { graphRef.current = graph; }, [graph]);

  useEffect(() => { if (registeredAgents.length === 0) loadAgents(); }, []);

  // ── 로컬스토리지 레이아웃 저장/복원 ──
  const layoutKey = `jinxus:graph:layout:${selectedAgent}`;
  const loadSavedPositions = (): Record<string, Pos> | null => {
    try { return JSON.parse(localStorage.getItem(layoutKey) || 'null'); } catch { return null; }
  };
  const savePositions = (nodes: LocalNode[]) => {
    const pos: Record<string, Pos> = {};
    nodes.forEach(n => { pos[n.id] = n.pos; });
    localStorage.setItem(layoutKey, JSON.stringify(pos));
  };

  // ── API 로드 ──
  const buildGraph = useCallback((raw: AgentGraph | null, currentNode: string | null): LocalGraph => {
    const template = DEFAULT_GRAPHS[selectedAgent] ?? DEFAULT_GRAPHS.DEFAULT;
    const nodes: GraphNode[] = raw?.nodes?.length ? raw.nodes : template.nodes;
    const edges = raw?.edges?.length ? raw.edges : template.edges;

    const savedPos = loadSavedPositions();
    const computedPos = computeLayout(nodes, edges);

    return {
      agent_name: selectedAgent,
      current_node: currentNode,
      nodes: nodes.map(n => ({
        ...n,
        pos: savedPos?.[n.id] ?? computedPos[n.id] ?? { x: 100, y: 100 },
      })),
      edges,
    };
  }, [selectedAgent]); // eslint-disable-line react-hooks/exhaustive-deps

  const isFirstLoad = useRef(true);

  const loadData = useCallback(async () => {
    try {
      const statusRes = await agentApi.getAllRuntimeStatus();
      setAgentStatuses(statusRes.agents);
      const currentNode = statusRes.agents.find(a => a.name === selectedAgent)?.current_node ?? null;

      try {
        const graphRes = await agentApi.getGraph(selectedAgent);
        setGraph(prev => prev ? { ...buildGraph(graphRes, currentNode), nodes: prev.nodes } : buildGraph(graphRes, currentNode));
      } catch {
        setGraph(prev => prev ? { ...prev, current_node: currentNode } : buildGraph(null, currentNode));
      }
      isFirstLoad.current = false;
    } catch {
      // 최초 로드 실패만 토스트. 폴링 실패는 무시 (스팸 방지)
      if (isFirstLoad.current) toast.error('그래프 데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  }, [selectedAgent, buildGraph]);

  useEffect(() => {
    setLoading(true);
    setGraph(null);
    setSelectedNodeId(null);
    isFirstLoad.current = true;
    setTimeout(() => setGraph(buildGraph(null, null)), 0); // 즉시 기본 그래프 표시
    loadData();

    if (intervalRef.current) clearInterval(intervalRef.current);
    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        if (document.visibilityState === 'visible') loadData();
      }, POLLING_INTERVAL_MS);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [selectedAgent, autoRefresh]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── 드래그 핸들러 ──
  const onNodeMouseDown = (e: React.MouseEvent, id: string) => {
    if (addEdgeMode) return;
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const sp = pt.matrixTransform(ctm.inverse());
    const node = graphRef.current?.nodes.find(n => n.id === id);
    if (!node) return;
    dragRef.current = { id, ox: node.pos.x, oy: node.pos.y, mx: sp.x, my: sp.y };
  };

  const onSVGMouseMove = (e: React.MouseEvent) => {
    if (!dragRef.current || !graph) return;
    const svg = svgRef.current;
    if (!svg) return;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const sp = pt.matrixTransform(ctm.inverse());
    const dx = sp.x - dragRef.current.mx;
    const dy = sp.y - dragRef.current.my;
    setGraph(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: prev.nodes.map(n =>
          n.id === dragRef.current!.id
            ? { ...n, pos: { x: dragRef.current!.ox + dx, y: dragRef.current!.oy + dy } }
            : n
        ),
      };
    });
  };

  const onSVGMouseUp = () => {
    if (dragRef.current && graphRef.current) savePositions(graphRef.current.nodes);
    dragRef.current = null;
  };

  // ── 노드 클릭 ──
  const onNodeClick = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (addEdgeMode) {
      if (!edgeSource) {
        setEdgeSource(id);
      } else if (edgeSource !== id) {
        // 엣지 추가
        const exists = graph!.edges.some(e => e.from === edgeSource && e.to === id);
        if (!exists) {
          setGraph(prev => prev ? { ...prev, edges: [...prev.edges, { from: edgeSource!, to: id }] } : prev);
          setAutoRefresh(false);
          toast.success(`${edgeSource} → ${id} 연결됨 (자동 갱신 정지됨)`);
        }
        setEdgeSource(null);
        setAddEdgeMode(false);
      }
      return;
    }
    if (selectedNodeId === id) return;
    const node = graph!.nodes.find(n => n.id === id)!;
    setSelectedNodeId(id);
    setEditLabel(node.label);
    setEditDesc(node.description || '');
    setEditMode(false);
  };

  // ── 노드 편집 저장 ──
  const saveNodeEdit = () => {
    setGraph(prev => {
      if (!prev) return prev;
      return { ...prev, nodes: prev.nodes.map(n => n.id === selectedNodeId ? { ...n, label: editLabel, description: editDesc } : n) };
    });
    setEditMode(false);
    // 편집 시 자동 새로고침 일시 중지 (덮어쓰기 방지)
    setAutoRefresh(false);
    toast.success('변경됨 — 자동 갱신 정지됨 (새로고침 시 초기화)');
  };

  // ── 노드 삭제 ──
  const deleteNode = (id: string) => {
    setGraph(prev => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: prev.nodes.filter(n => n.id !== id),
        edges: prev.edges.filter(e => e.from !== id && e.to !== id),
      };
    });
    setSelectedNodeId(null);
    setAutoRefresh(false);
  };

  // ── 엣지 삭제 ──
  const deleteEdge = (from: string, to: string) => {
    setGraph(prev => prev ? { ...prev, edges: prev.edges.filter(e => !(e.from === from && e.to === to)) } : prev);
    setAutoRefresh(false);
  };

  // ── 노드 추가 ──
  const addNode = () => {
    const id = `node_${Date.now()}`;
    const newNode: LocalNode = { id, label: id, description: '새 노드', pos: { x: 200, y: 200 } };
    setGraph(prev => prev ? { ...prev, nodes: [...prev.nodes, newNode] } : prev);
    setSelectedNodeId(id);
    setEditLabel(id);
    setEditDesc('새 노드');
    setEditMode(true);
    setAutoRefresh(false);
  };

  // ── 레이아웃 리셋 ──
  const resetLayout = () => {
    if (!graph) return;
    localStorage.removeItem(layoutKey);
    const pos = computeLayout(graph.nodes, graph.edges);
    setGraph(prev => prev ? { ...prev, nodes: prev.nodes.map(n => ({ ...n, pos: pos[n.id] ?? n.pos })) } : prev);
  };

  if (loading && !graph) {
    return <div className="flex items-center justify-center h-full"><RefreshCw className="w-8 h-8 animate-spin text-primary" /></div>;
  }

  const NODE_W = 110, NODE_H = 44;
  const currentNode = graph?.current_node;

  // SVG viewBox: 고정 (드래그 중 CTM 변화 방지). computeLayout의 W=760 기준, 최대 10레이어 기준 높이 1000
  const svgViewBox = '0 0 760 1000';
  const selectedNode = graph?.nodes.find(n => n.id === selectedNodeId) ?? null;
  const currentAgentStatus = agentStatuses.find(a => a.name === selectedAgent);

  return (
    <div className="h-full flex flex-col gap-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <GitBranch className="w-6 h-6" />워크플로우 그래프
          </h1>
          <div className="relative">
            <select
              value={selectedAgent}
              onChange={e => setSelectedAgent(e.target.value)}
              className="appearance-none bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-1.5 pr-8 text-sm focus:outline-none focus:border-primary"
            >
              {agentList.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none text-zinc-400" />
          </div>
          {currentAgentStatus && (
            <div className="flex items-center gap-1.5 text-sm">
              <span className={`w-2 h-2 rounded-full ${currentAgentStatus.status === 'working' ? 'bg-green-500 animate-pulse' : currentAgentStatus.status === 'error' ? 'bg-red-500' : 'bg-zinc-500'}`} />
              <span className="text-zinc-400">{currentAgentStatus.status === 'working' ? '작업 중' : currentAgentStatus.status === 'error' ? '오류' : '대기'}</span>
              {currentNode && <span className="text-primary font-mono text-xs">@ {currentNode}</span>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* 엣지 추가 모드 */}
          <button
            onClick={() => { setAddEdgeMode(!addEdgeMode); setEdgeSource(null); }}
            title="노드 클릭 → 클릭으로 엣지 연결"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${addEdgeMode ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40' : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'}`}
          >
            <Link size={14} />
            {addEdgeMode ? (edgeSource ? `${edgeSource} →` : '출발 노드 클릭') : '엣지 추가'}
          </button>
          <button onClick={addNode} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-zinc-700 text-zinc-300 hover:bg-zinc-600 transition-colors">
            <Plus size={14} />노드 추가
          </button>
          <button onClick={resetLayout} title="레이아웃 초기화" className="px-3 py-1.5 rounded-lg text-sm bg-zinc-700 text-zinc-300 hover:bg-zinc-600 transition-colors">
            초기화
          </button>
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${autoRefresh ? 'bg-green-600/20 text-green-400 border border-green-500/30' : 'bg-zinc-700 text-zinc-300'}`}
          >
            {autoRefresh ? <Play size={14} /> : <Pause size={14} />}
            {autoRefresh ? '실시간' : '정지'}
          </button>
          <button onClick={loadData} className="p-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 transition-colors">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* 본문 */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* SVG 그래프 캔버스 */}
        <div className="flex-1 bg-zinc-900/60 border border-dark-border rounded-xl overflow-hidden relative">
          <svg
            ref={svgRef}
            className="w-full h-full"
            viewBox={svgViewBox}
            preserveAspectRatio="xMidYMid meet"
            style={{ minHeight: 400, cursor: addEdgeMode ? 'crosshair' : dragRef.current ? 'grabbing' : 'default' }}
            onMouseMove={onSVGMouseMove}
            onMouseUp={onSVGMouseUp}
            onMouseLeave={onSVGMouseUp}
          >
            <defs>
              <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#52525b" />
              </marker>
              <marker id="arrowhead-active" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#3b82f6" />
              </marker>
              <marker id="arrowhead-sel" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                <polygon points="0 0, 8 3, 0 6" fill="#a78bfa" />
              </marker>
            </defs>

            {/* 엣지 */}
            {graph?.edges.map((edge, i) => {
              const src = graph.nodes.find(n => n.id === edge.from);
              const tgt = graph.nodes.find(n => n.id === edge.to);
              if (!src || !tgt) return null;
              const isSel = selectedNodeId === edge.from || selectedNodeId === edge.to;
              const isActive = currentNode === edge.from || currentNode === edge.to;
              const d = edgePath(src.pos.x, src.pos.y, tgt.pos.x, tgt.pos.y, NODE_W, NODE_H);
              const color = isActive ? '#3b82f6' : isSel ? '#a78bfa' : '#3f3f46';
              const marker = isActive ? 'arrowhead-active' : isSel ? 'arrowhead-sel' : 'arrowhead';
              return (
                <g key={i}>
                  {/* 클릭 가능 넓은 투명 영역 */}
                  <path d={d} fill="none" stroke="transparent" strokeWidth={12}
                    style={{ cursor: 'pointer' }}
                    onClick={() => deleteEdge(edge.from, edge.to)}
                  />
                  <path d={d} fill="none" stroke={color} strokeWidth={isSel || isActive ? 2 : 1.5}
                    opacity={isSel || isActive ? 1 : 0.55}
                    markerEnd={`url(#${marker})`}
                    strokeDasharray={edge.from === edge.to ? '4,3' : undefined}
                  />
                </g>
              );
            })}

            {/* 노드 */}
            {graph?.nodes.map(node => {
              const isActive = currentNode === node.id;
              const isSel = selectedNodeId === node.id;
              const isEdgeSrc = addEdgeMode && edgeSource === node.id;
              let fill = 'rgba(39,39,42,0.9)';
              let stroke = '#52525b';
              let strokeW = 1.5;
              if (isActive) { fill = 'rgba(37,99,235,0.25)'; stroke = '#3b82f6'; strokeW = 2; }
              else if (isSel) { fill = 'rgba(124,58,237,0.2)'; stroke = '#a78bfa'; strokeW = 2; }
              else if (isEdgeSrc) { fill = 'rgba(245,158,11,0.2)'; stroke = '#f59e0b'; strokeW = 2; }

              return (
                <g key={node.id}
                  onMouseDown={e => onNodeMouseDown(e, node.id)}
                  onClick={e => onNodeClick(e, node.id)}
                  style={{ cursor: addEdgeMode ? 'crosshair' : 'grab', userSelect: 'none' }}
                >
                  {/* 활성 노드 글로우 */}
                  {isActive && <rect x={node.pos.x - 4} y={node.pos.y - 4} width={NODE_W + 8} height={NODE_H + 8} rx={10} fill="rgba(59,130,246,0.12)" />}
                  <rect x={node.pos.x} y={node.pos.y} width={NODE_W} height={NODE_H} rx={8}
                    fill={fill} stroke={stroke} strokeWidth={strokeW}
                  />
                  <text
                    x={node.pos.x + NODE_W / 2} y={node.pos.y + NODE_H / 2 + 1}
                    textAnchor="middle" dominantBaseline="middle"
                    fontSize={11} fill={isActive ? '#93c5fd' : isSel ? '#c4b5fd' : '#d4d4d8'}
                    fontFamily="monospace"
                  >
                    {node.label.length > 13 ? node.label.slice(0, 12) + '…' : node.label}
                  </text>
                  {isActive && (
                    <circle cx={node.pos.x + NODE_W - 8} cy={node.pos.y + 8} r={4} fill="#3b82f6">
                      <animate attributeName="opacity" values="1;0.3;1" dur="1.2s" repeatCount="indefinite" />
                    </circle>
                  )}
                </g>
              );
            })}
          </svg>

          {/* 힌트 */}
          <div className="absolute bottom-3 left-3 flex gap-4 text-xs text-zinc-600 pointer-events-none">
            <span>드래그: 노드 이동 (위치 저장됨)</span>
            <span>클릭: 선택/편집</span>
            <span>엣지 클릭: 삭제</span>
            <span className="text-zinc-700">편집은 시각화 전용 — 백엔드 미반영</span>
          </div>

          {/* 범례 */}
          <div className="absolute top-3 right-3 flex flex-col gap-1.5 text-xs text-zinc-500">
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded border border-zinc-600 bg-zinc-800/90 inline-block" />대기</div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded border border-blue-400 bg-blue-600/25 inline-block" />실행 중</div>
            <div className="flex items-center gap-1.5"><span className="w-3 h-3 rounded border border-violet-400 bg-violet-600/20 inline-block" />선택됨</div>
          </div>
        </div>

        {/* 속성 패널 */}
        <div className="w-72 bg-dark-card border border-dark-border rounded-xl flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-dark-border flex items-center justify-between">
            <span className="font-semibold text-sm">
              {selectedNode ? selectedNode.label : '노드 정보'}
            </span>
            {selectedNode && !editMode && (
              <div className="flex gap-1">
                <button onClick={() => setEditMode(true)} className="p-1.5 rounded hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors" title="편집">
                  <Edit3 size={14} />
                </button>
                <button onClick={() => deleteNode(selectedNode.id)} className="p-1.5 rounded hover:bg-red-500/20 text-zinc-400 hover:text-red-400 transition-colors" title="삭제">
                  <Trash2 size={14} />
                </button>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4">
            {selectedNode ? (
              editMode ? (
                /* 편집 폼 */
                <div className="space-y-3">
                  <div>
                    <label className="text-xs text-zinc-500 uppercase mb-1 block">라벨</label>
                    <input
                      value={editLabel}
                      onChange={e => setEditLabel(e.target.value)}
                      className="w-full bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm font-mono focus:outline-none focus:border-primary"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-zinc-500 uppercase mb-1 block">설명</label>
                    <textarea
                      value={editDesc}
                      onChange={e => setEditDesc(e.target.value)}
                      rows={4}
                      className="w-full bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-1.5 text-sm resize-none focus:outline-none focus:border-primary"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button onClick={saveNodeEdit} className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-primary/80 hover:bg-primary rounded-lg text-sm transition-colors">
                      <Check size={13} />저장
                    </button>
                    <button onClick={() => setEditMode(false)} className="px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm transition-colors">
                      <X size={13} />
                    </button>
                  </div>
                </div>
              ) : (
                /* 노드 상세 */
                <div className="space-y-4">
                  <div>
                    <label className="text-xs text-zinc-500 uppercase">ID</label>
                    <p className="font-mono text-sm mt-0.5">{selectedNode.id}</p>
                  </div>
                  <div>
                    <label className="text-xs text-zinc-500 uppercase">설명</label>
                    <p className="text-sm text-zinc-300 mt-0.5">{selectedNode.description || '—'}</p>
                  </div>
                  <div>
                    <label className="text-xs text-zinc-500 uppercase">상태</label>
                    <div className="flex items-center gap-2 mt-0.5">
                      {currentNode === selectedNode.id ? (
                        <><span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" /><span className="text-blue-400 text-sm">실행 중</span></>
                      ) : (
                        <><span className="w-2 h-2 rounded-full bg-zinc-500" /><span className="text-zinc-400 text-sm">대기</span></>
                      )}
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-zinc-500 uppercase mb-1.5 block">연결된 엣지</label>
                    <div className="space-y-1">
                      {graph?.edges.filter(e => e.from === selectedNode.id || e.to === selectedNode.id).map((e, i) => (
                        <div key={i} className="flex items-center justify-between text-xs bg-zinc-800 rounded-lg px-2.5 py-1.5 group">
                          <span className="font-mono text-zinc-400">
                            <span className={e.from === selectedNode.id ? 'text-violet-400' : 'text-zinc-500'}>{e.from}</span>
                            <span className="text-zinc-600 mx-1">→</span>
                            <span className={e.to === selectedNode.id ? 'text-violet-400' : 'text-zinc-500'}>{e.to}</span>
                          </span>
                          <button onClick={() => deleteEdge(e.from, e.to)} className="opacity-0 group-hover:opacity-100 text-red-400/70 hover:text-red-400 transition-all">
                            <Unlink size={11} />
                          </button>
                        </div>
                      ))}
                      {graph?.edges.filter(e => e.from === selectedNode.id || e.to === selectedNode.id).length === 0 && (
                        <p className="text-xs text-zinc-600">연결 없음</p>
                      )}
                    </div>
                  </div>
                </div>
              )
            ) : (
              <div className="text-center text-zinc-600 py-12 text-sm">
                노드를 클릭하면<br />상세 정보와<br />편집 옵션이 표시됩니다
              </div>
            )}
          </div>

          {/* 현재 작업 */}
          {currentAgentStatus?.current_task && (
            <div className="px-4 py-3 border-t border-dark-border bg-zinc-800/40">
              <label className="text-xs text-zinc-500 uppercase">현재 작업</label>
              <p className="text-xs text-zinc-300 mt-1 line-clamp-3">{currentAgentStatus.current_task}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
