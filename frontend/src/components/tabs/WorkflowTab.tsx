'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { agentApi, type AgentGraph, type GraphNode, type GraphEdge } from '@/lib/api';
import { getDisplayName, getPersona } from '@/lib/personas';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  MarkerType,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Loader2, RefreshCw, GitBranch, ChevronDown } from 'lucide-react';

// ---------- 노드 색상 매핑 ----------
const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  intake: { bg: '#1e3a5f', border: '#3b82f6', text: '#93c5fd' },
  classify: { bg: '#3b1f4e', border: '#8b5cf6', text: '#c4b5fd' },
  decompose: { bg: '#3b2f1e', border: '#f59e0b', text: '#fcd34d' },
  execute: { bg: '#1e3b2f', border: '#10b981', text: '#6ee7b7' },
  aggregate: { bg: '#3b1e1e', border: '#ef4444', text: '#fca5a5' },
  thinking: { bg: '#1e2e3e', border: '#06b6d4', text: '#67e8f9' },
  default: { bg: '#27272a', border: '#52525b', text: '#a1a1aa' },
};

function getNodeColor(id: string) {
  for (const [key, val] of Object.entries(NODE_COLORS)) {
    if (id.toLowerCase().includes(key)) return val;
  }
  return NODE_COLORS.default;
}

// ---------- 그래프 → React Flow 변환 ----------
function graphToFlow(
  graph: AgentGraph,
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];

  // 노드 레이아웃 (자동 계층 배치)
  const nodeMap = new Map<string, GraphNode>();
  graph.nodes.forEach(n => nodeMap.set(n.id, n));

  // 인접 리스트로 레벨 계산 (BFS)
  const adj = new Map<string, string[]>();
  const inDegree = new Map<string, number>();
  graph.nodes.forEach(n => {
    adj.set(n.id, []);
    inDegree.set(n.id, 0);
  });
  graph.edges.forEach(e => {
    adj.get(e.from)?.push(e.to);
    inDegree.set(e.to, (inDegree.get(e.to) ?? 0) + 1);
  });

  // BFS 레벨
  const levels = new Map<string, number>();
  const queue: string[] = [];
  graph.nodes.forEach(n => {
    if ((inDegree.get(n.id) ?? 0) === 0) {
      queue.push(n.id);
      levels.set(n.id, 0);
    }
  });

  while (queue.length > 0) {
    const curr = queue.shift()!;
    const currLevel = levels.get(curr) ?? 0;
    for (const next of (adj.get(curr) ?? [])) {
      const existing = levels.get(next);
      if (existing === undefined || existing < currLevel + 1) {
        levels.set(next, currLevel + 1);
      }
      // 간단 BFS: 아직 방문 안한 경우만 큐에
      if (existing === undefined) {
        queue.push(next);
      }
    }
  }

  // 레벨별 노드 그룹화
  const levelGroups = new Map<number, string[]>();
  graph.nodes.forEach(n => {
    const lvl = levels.get(n.id) ?? 0;
    if (!levelGroups.has(lvl)) levelGroups.set(lvl, []);
    levelGroups.get(lvl)!.push(n.id);
  });

  const X_GAP = 300;
  const Y_GAP = 120;

  levelGroups.forEach((nodeIds, level) => {
    const startY = -(nodeIds.length - 1) * Y_GAP / 2;
    nodeIds.forEach((id, idx) => {
      const gNode = nodeMap.get(id)!;
      const colors = getNodeColor(id);
      const isCurrent = graph.current_node === id;

      nodes.push({
        id,
        position: { x: level * X_GAP, y: startY + idx * Y_GAP },
        data: { label: gNode.label || id },
        type: 'default',
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          background: colors.bg,
          border: `2px solid ${isCurrent ? '#22c55e' : colors.border}`,
          borderRadius: '12px',
          padding: '12px 16px',
          color: colors.text,
          fontSize: '13px',
          fontWeight: 600,
          minWidth: '140px',
          textAlign: 'center' as const,
          boxShadow: isCurrent ? '0 0 16px rgba(34,197,94,0.4)' : `0 2px 8px ${colors.border}20`,
        },
      });
    });
  });

  graph.edges.forEach((e, i) => {
    edges.push({
      id: `e-${i}`,
      source: e.from,
      target: e.to,
      label: e.label || '',
      animated: graph.current_node === e.from,
      style: { stroke: '#52525b', strokeWidth: 2 },
      labelStyle: { fontSize: 10, fill: '#71717a' },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#52525b', width: 16, height: 16 },
    });
  });

  return { nodes, edges };
}

// ---------- 메인 컴포넌트 ----------
export default function WorkflowTab({ isActive = true }: { isActive?: boolean }) {
  const { agents } = useAppStore();
  const [selectedAgent, setSelectedAgent] = useState<string>('JINXUS_CORE');
  const [graph, setGraph] = useState<AgentGraph | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const [flowNodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  const loadGraph = useCallback(async (agentName: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await agentApi.getGraph(agentName);
      setGraph(data);
      const { nodes, edges } = graphToFlow(data);
      setNodes(nodes);
      setEdges(edges);
    } catch (err) {
      setError(err instanceof Error ? err.message : '그래프 로드 실패');
      setGraph(null);
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  useEffect(() => {
    if (isActive && selectedAgent) {
      loadGraph(selectedAgent);
    }
  }, [isActive, selectedAgent, loadGraph]);

  const allAgents = useMemo(() => {
    const list = [{ name: 'JINXUS_CORE' }, ...agents];
    return list;
  }, [agents]);

  return (
    <div className="h-full flex flex-col gap-4 min-h-0">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <GitBranch size={20} className="text-primary" />
          <h2 className="text-lg font-bold">워크플로우 에디터</h2>
          <span className="text-xs text-zinc-500">에이전트 실행 그래프 시각화</span>
        </div>
        <div className="flex items-center gap-2">
          {/* 에이전트 선택 */}
          <div className="relative">
            <button
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2 px-3 py-1.5 bg-dark-card border border-dark-border rounded-lg text-sm hover:border-zinc-600 transition-colors"
            >
              <span>{getPersona(selectedAgent)?.emoji ?? '🤖'}</span>
              <span>{getDisplayName(selectedAgent)}</span>
              <ChevronDown size={14} className={`text-zinc-500 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>
            {dropdownOpen && (
              <div className="absolute right-0 top-full mt-1 z-50 w-48 bg-dark-card border border-dark-border rounded-xl shadow-lg max-h-[300px] overflow-y-auto">
                {allAgents.map((a) => (
                  <button
                    key={a.name}
                    onClick={() => { setSelectedAgent(a.name); setDropdownOpen(false); }}
                    className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-800 transition-colors ${
                      selectedAgent === a.name ? 'text-primary bg-zinc-800/50' : 'text-zinc-300'
                    }`}
                  >
                    {getPersona(a.name)?.emoji ?? '🤖'} {getDisplayName(a.name)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={() => selectedAgent && loadGraph(selectedAgent)}
            className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors"
            title="새로고침"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* 그래프 노드 정보 */}
      {graph && (
        <div className="flex items-center gap-4 text-xs text-zinc-500 flex-shrink-0">
          <span>노드 {graph.nodes.length}개</span>
          <span>엣지 {graph.edges.length}개</span>
          {graph.current_node && (
            <span className="text-green-400">현재: {graph.current_node}</span>
          )}
        </div>
      )}

      {/* React Flow 캔버스 */}
      <div className="flex-1 min-h-0 bg-dark-card border border-dark-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={32} className="animate-spin text-zinc-500" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-500">
            <p className="text-sm">{error}</p>
            <button
              onClick={() => selectedAgent && loadGraph(selectedAgent)}
              className="flex items-center gap-1 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-xs transition-colors"
            >
              <RefreshCw size={12} />
              재시도
            </button>
          </div>
        ) : flowNodes.length > 0 ? (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            proOptions={{ hideAttribution: true }}
            minZoom={0.3}
            maxZoom={2}
          >
            <Background color="#333" gap={20} />
            <Controls
              style={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: '8px' }}
            />
            <MiniMap
              nodeColor={(n) => {
                const colors = getNodeColor(n.id);
                return colors.border;
              }}
              maskColor="rgba(0,0,0,0.7)"
              style={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: '8px' }}
            />
          </ReactFlow>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-600">
            <GitBranch size={40} />
            <p className="text-sm">에이전트를 선택하면 실행 그래프가 표시됩니다</p>
          </div>
        )}
      </div>
    </div>
  );
}
