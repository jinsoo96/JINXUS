'use client';

import { useState, useEffect } from 'react';
import { agentApi, type AgentGraph as AgentGraphType } from '@/lib/api';

interface AgentGraphProps {
  agentName: string;
}

export default function AgentGraph({ agentName }: AgentGraphProps) {
  const [graph, setGraph] = useState<AgentGraphType | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchGraph = async () => {
      try {
        setLoading(true);
        const data = await agentApi.getGraph(agentName);
        setGraph(data);
      } catch (err) {
        console.error('Failed to fetch graph:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchGraph();

    // 현재 노드 업데이트를 위한 폴링
    const interval = setInterval(fetchGraph, 2000);
    return () => clearInterval(interval);
  }, [agentName]);

  if (loading || !graph) {
    return (
      <div className="h-64 flex items-center justify-center text-zinc-500">
        로딩 중...
      </div>
    );
  }

  // 노드 위치 계산 (간단한 수평 레이아웃)
  const nodePositions: Record<string, { x: number; y: number }> = {
    receive: { x: 50, y: 80 },
    plan: { x: 150, y: 80 },
    execute: { x: 250, y: 80 },
    evaluate: { x: 350, y: 80 },
    reflect: { x: 450, y: 80 },
    memory_write: { x: 550, y: 80 },
    return_result: { x: 650, y: 80 },
  };

  const getNodeColor = (nodeId: string) => {
    if (graph.current_node === nodeId) {
      return 'fill-blue-500';
    }
    return 'fill-zinc-600';
  };

  const getNodeStroke = (nodeId: string) => {
    if (graph.current_node === nodeId) {
      return 'stroke-blue-400';
    }
    return 'stroke-zinc-500';
  };

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-4">
      <h3 className="text-sm font-medium text-white mb-4">
        LangGraph 실행 흐름
      </h3>

      <div className="overflow-x-auto">
        <svg width="720" height="160" className="min-w-full">
          {/* 엣지 (연결선) */}
          {graph.edges.map((edge, idx) => {
            const from = nodePositions[edge.from];
            const to = nodePositions[edge.to];
            if (!from || !to) return null;

            // 재시도 엣지는 곡선으로
            if (edge.from === 'evaluate' && edge.to === 'execute') {
              return (
                <g key={idx}>
                  <path
                    d={`M ${from.x} ${from.y - 15} Q ${(from.x + to.x) / 2} ${from.y - 50} ${to.x} ${to.y - 15}`}
                    fill="none"
                    stroke="#ef4444"
                    strokeWidth="2"
                    strokeDasharray="4"
                    markerEnd="url(#arrowhead-red)"
                  />
                  <text
                    x={(from.x + to.x) / 2}
                    y={from.y - 45}
                    fill="#ef4444"
                    fontSize="10"
                    textAnchor="middle"
                  >
                    재시도
                  </text>
                </g>
              );
            }

            return (
              <line
                key={idx}
                x1={from.x + 25}
                y1={from.y}
                x2={to.x - 25}
                y2={to.y}
                stroke="#52525b"
                strokeWidth="2"
                markerEnd="url(#arrowhead)"
              />
            );
          })}

          {/* 화살표 마커 정의 */}
          <defs>
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="7"
              refX="9"
              refY="3.5"
              orient="auto"
            >
              <polygon points="0 0, 10 3.5, 0 7" fill="#52525b" />
            </marker>
            <marker
              id="arrowhead-red"
              markerWidth="10"
              markerHeight="7"
              refX="9"
              refY="3.5"
              orient="auto"
            >
              <polygon points="0 0, 10 3.5, 0 7" fill="#ef4444" />
            </marker>
          </defs>

          {/* 노드 */}
          {graph.nodes.map((node) => {
            const pos = nodePositions[node.id];
            if (!pos) return null;

            const isActive = graph.current_node === node.id;

            return (
              <g key={node.id}>
                {/* 노드 원 */}
                <circle
                  cx={pos.x}
                  cy={pos.y}
                  r="20"
                  className={`${getNodeColor(node.id)} ${getNodeStroke(node.id)}`}
                  strokeWidth={isActive ? "3" : "2"}
                />
                {/* 활성 노드 애니메이션 */}
                {isActive && (
                  <circle
                    cx={pos.x}
                    cy={pos.y}
                    r="25"
                    fill="none"
                    stroke="#3b82f6"
                    strokeWidth="2"
                    opacity="0.5"
                  >
                    <animate
                      attributeName="r"
                      from="25"
                      to="35"
                      dur="1s"
                      repeatCount="indefinite"
                    />
                    <animate
                      attributeName="opacity"
                      from="0.5"
                      to="0"
                      dur="1s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
                {/* 노드 라벨 */}
                <text
                  x={pos.x}
                  y={pos.y + 4}
                  fill="white"
                  fontSize="10"
                  textAnchor="middle"
                  fontWeight={isActive ? 'bold' : 'normal'}
                >
                  {node.label}
                </text>
                {/* 노드 설명 */}
                <text
                  x={pos.x}
                  y={pos.y + 40}
                  fill="#71717a"
                  fontSize="9"
                  textAnchor="middle"
                >
                  {node.description.slice(0, 8)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {/* 범례 */}
      <div className="mt-4 flex items-center gap-4 text-xs text-zinc-500">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-blue-500" />
          <span>현재 단계</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded-full bg-zinc-600" />
          <span>대기 중</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-4 h-0.5 bg-red-500" style={{ borderStyle: 'dashed' }} />
          <span>재시도</span>
        </div>
      </div>
    </div>
  );
}
