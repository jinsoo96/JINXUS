'use client';

import { useState, useEffect, useCallback } from 'react';
import { agentApi, AgentRuntimeStatus, AgentGraph, GraphNode, GraphEdge } from '@/lib/api';
import {
  GitBranch,
  RefreshCw,
  ChevronDown,
  Play,
  Pause,
  Circle,
  ArrowRight,
  CheckCircle2,
  AlertCircle,
  Clock,
} from 'lucide-react';

// JINXUS_CORE 기본 그래프 구조
const JINXUS_CORE_GRAPH: AgentGraph = {
  agent_name: 'JINXUS_CORE',
  nodes: [
    { id: 'intake', label: 'intake', description: '입력 수신 및 컨텍스트 로드' },
    { id: 'decompose', label: 'decompose', description: '명령 분해 및 서브태스크 생성' },
    { id: 'dispatch', label: 'dispatch', description: '에이전트 할당 및 실행' },
    { id: 'aggregate', label: 'aggregate', description: '결과 취합' },
    { id: 'reflect', label: 'reflect', description: '작업 반성' },
    { id: 'memory_write', label: 'memory_write', description: '메모리 저장' },
    { id: 'respond', label: 'respond', description: '최종 응답' },
  ],
  edges: [
    { from: 'intake', to: 'decompose' },
    { from: 'decompose', to: 'dispatch' },
    { from: 'dispatch', to: 'aggregate' },
    { from: 'aggregate', to: 'reflect' },
    { from: 'reflect', to: 'memory_write' },
    { from: 'memory_write', to: 'respond' },
  ],
  current_node: null,
};

// 노드 색상
const nodeColors = {
  idle: 'bg-zinc-700 border-zinc-600',
  current: 'bg-blue-600 border-blue-400 animate-pulse',
  completed: 'bg-green-600 border-green-400',
  error: 'bg-red-600 border-red-400',
};

export default function GraphTab() {
  // 상태
  const [selectedAgent, setSelectedAgent] = useState<string>('JINXUS_CORE');
  const [agentStatuses, setAgentStatuses] = useState<AgentRuntimeStatus[]>([]);
  const [graph, setGraph] = useState<AgentGraph>(JINXUS_CORE_GRAPH);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // 사용 가능한 에이전트 목록
  const agents = ['JINXUS_CORE', 'JX_CODER', 'JX_RESEARCHER', 'JX_WRITER', 'JX_ANALYST', 'JX_OPS', 'JS_PERSONA'];

  // 데이터 로드
  const loadData = useCallback(async () => {
    try {
      // 에이전트 런타임 상태 로드
      const statusRes = await agentApi.getAllRuntimeStatus();
      setAgentStatuses(statusRes.agents);

      // 선택된 에이전트의 그래프 로드 시도
      try {
        const graphRes = await agentApi.getGraph(selectedAgent);
        setGraph(graphRes);
      } catch {
        // API 실패 시 기본 그래프 사용
        if (selectedAgent === 'JINXUS_CORE') {
          setGraph(JINXUS_CORE_GRAPH);
        } else {
          // 일반 에이전트용 기본 그래프
          setGraph({
            agent_name: selectedAgent,
            nodes: [
              { id: 'receive', label: 'receive', description: '작업 수신' },
              { id: 'plan', label: 'plan', description: '실행 계획 수립' },
              { id: 'execute', label: 'execute', description: '실행' },
              { id: 'evaluate', label: 'evaluate', description: '평가' },
              { id: 'reflect', label: 'reflect', description: '반성' },
              { id: 'memory_write', label: 'memory_write', description: '메모리 저장' },
              { id: 'return', label: 'return', description: '결과 반환' },
            ],
            edges: [
              { from: 'receive', to: 'plan' },
              { from: 'plan', to: 'execute' },
              { from: 'execute', to: 'evaluate' },
              { from: 'evaluate', to: 'reflect' },
              { from: 'reflect', to: 'memory_write' },
              { from: 'memory_write', to: 'return' },
            ],
            current_node: statusRes.agents.find(a => a.name === selectedAgent)?.current_node || null,
          });
        }
      }
    } catch (error) {
      console.error('Graph data load error:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedAgent]);

  // 초기 로드 및 자동 갱신
  useEffect(() => {
    loadData();

    if (autoRefresh) {
      const interval = setInterval(loadData, 3000); // 3초마다 갱신
      return () => clearInterval(interval);
    }
  }, [loadData, autoRefresh]);

  // 현재 에이전트 상태
  const currentAgentStatus = agentStatuses.find(a => a.name === selectedAgent);

  // 현재 노드 찾기
  const currentNode = currentAgentStatus?.current_node || graph.current_node;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <GitBranch className="w-6 h-6" />
            워크플로우 그래프
          </h1>

          {/* 에이전트 선택 */}
          <div className="relative">
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              className="appearance-none bg-zinc-800 border border-zinc-600 rounded-lg px-4 py-2 pr-8 text-sm focus:outline-none focus:border-primary"
            >
              {agents.map(agent => (
                <option key={agent} value={agent}>{agent}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 pointer-events-none text-zinc-400" />
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* 현재 상태 표시 */}
          {currentAgentStatus && (
            <div className="flex items-center gap-2 text-sm">
              <span className={`w-2 h-2 rounded-full ${
                currentAgentStatus.status === 'working' ? 'bg-green-500 animate-pulse' :
                currentAgentStatus.status === 'error' ? 'bg-red-500' :
                'bg-zinc-500'
              }`} />
              <span className="text-zinc-400">
                {currentAgentStatus.status === 'working' ? '작업 중' :
                 currentAgentStatus.status === 'error' ? '오류' : '대기'}
              </span>
              {currentNode && (
                <span className="text-primary">@ {currentNode}</span>
              )}
            </div>
          )}

          {/* 자동 갱신 토글 */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
              autoRefresh
                ? 'bg-green-600 text-white'
                : 'bg-zinc-700 text-zinc-300'
            }`}
          >
            {autoRefresh ? <Play size={14} /> : <Pause size={14} />}
            {autoRefresh ? '실시간' : '정지'}
          </button>

          {/* 새로고침 */}
          <button
            onClick={loadData}
            className="p-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 transition-colors"
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </div>

      {/* 그래프 영역 */}
      <div className="flex-1 flex gap-6">
        {/* 그래프 캔버스 */}
        <div className="flex-1 bg-dark-card border border-dark-border rounded-xl p-6 overflow-auto">
          <div className="min-h-full flex flex-col items-center justify-center">
            {/* 노드 체인 */}
            <div className="flex flex-wrap items-center justify-center gap-4">
              {graph.nodes.map((node, index) => {
                const isCurrentNode = currentNode === node.id;
                const nodeIndex = graph.nodes.findIndex(n => n.id === currentNode);
                const isCompleted = nodeIndex > -1 && index < nodeIndex;

                return (
                  <div key={node.id} className="flex items-center">
                    {/* 노드 */}
                    <button
                      onClick={() => setSelectedNode(node)}
                      className={`
                        relative px-6 py-4 rounded-xl border-2 transition-all cursor-pointer
                        hover:scale-105 min-w-[120px]
                        ${isCurrentNode ? nodeColors.current :
                          isCompleted ? nodeColors.completed :
                          nodeColors.idle}
                        ${selectedNode?.id === node.id ? 'ring-2 ring-primary ring-offset-2 ring-offset-dark-card' : ''}
                      `}
                    >
                      {/* 상태 아이콘 */}
                      <div className="absolute -top-2 -right-2">
                        {isCurrentNode && (
                          <div className="bg-blue-500 rounded-full p-1">
                            <Clock className="w-3 h-3 text-white" />
                          </div>
                        )}
                        {isCompleted && (
                          <div className="bg-green-500 rounded-full p-1">
                            <CheckCircle2 className="w-3 h-3 text-white" />
                          </div>
                        )}
                      </div>

                      <p className="font-mono text-sm font-medium">{node.label}</p>
                    </button>

                    {/* 화살표 (마지막 노드 제외) */}
                    {index < graph.nodes.length - 1 && (
                      <ArrowRight className={`w-6 h-6 mx-2 ${
                        isCompleted ? 'text-green-400' : 'text-zinc-600'
                      }`} />
                    )}
                  </div>
                );
              })}
            </div>

            {/* 에이전트 분기 표시 (dispatch 노드일 때) */}
            {selectedAgent === 'JINXUS_CORE' && (
              <div className="mt-8 pt-8 border-t border-zinc-700 w-full">
                <p className="text-center text-sm text-zinc-500 mb-4">서브 에이전트</p>
                <div className="flex flex-wrap justify-center gap-4">
                  {['JX_CODER', 'JX_RESEARCHER', 'JX_WRITER', 'JX_ANALYST', 'JX_OPS'].map(agent => {
                    const status = agentStatuses.find(a => a.name === agent);
                    return (
                      <button
                        key={agent}
                        onClick={() => setSelectedAgent(agent)}
                        className={`
                          px-4 py-2 rounded-lg border transition-all hover:scale-105
                          ${status?.status === 'working'
                            ? 'bg-green-600/20 border-green-500 text-green-400'
                            : 'bg-zinc-800 border-zinc-600 text-zinc-400'}
                        `}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${
                            status?.status === 'working' ? 'bg-green-500 animate-pulse' :
                            status?.status === 'error' ? 'bg-red-500' :
                            'bg-zinc-500'
                          }`} />
                          <span className="text-sm font-mono">{agent}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 속성 패널 */}
        <div className="w-80 bg-dark-card border border-dark-border rounded-xl overflow-hidden">
          <div className="p-4 border-b border-dark-border">
            <h2 className="font-semibold">노드 정보</h2>
          </div>

          <div className="p-4">
            {selectedNode ? (
              <div className="space-y-4">
                {/* 노드 ID */}
                <div>
                  <label className="text-xs text-zinc-500 uppercase">ID</label>
                  <p className="font-mono text-lg">{selectedNode.id}</p>
                </div>

                {/* 라벨 */}
                <div>
                  <label className="text-xs text-zinc-500 uppercase">라벨</label>
                  <p className="text-lg">{selectedNode.label}</p>
                </div>

                {/* 설명 */}
                <div>
                  <label className="text-xs text-zinc-500 uppercase">설명</label>
                  <p className="text-sm text-zinc-300">{selectedNode.description}</p>
                </div>

                {/* 상태 */}
                <div>
                  <label className="text-xs text-zinc-500 uppercase">상태</label>
                  <div className="flex items-center gap-2 mt-1">
                    {currentNode === selectedNode.id ? (
                      <>
                        <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                        <span className="text-blue-400">실행 중</span>
                      </>
                    ) : (
                      <>
                        <div className="w-2 h-2 rounded-full bg-zinc-500" />
                        <span className="text-zinc-400">대기</span>
                      </>
                    )}
                  </div>
                </div>

                {/* 연결 */}
                <div>
                  <label className="text-xs text-zinc-500 uppercase">연결</label>
                  <div className="space-y-2 mt-1">
                    {graph.edges
                      .filter(e => e.from === selectedNode.id || e.to === selectedNode.id)
                      .map((edge, i) => (
                        <div key={i} className="flex items-center gap-2 text-sm">
                          <span className="text-zinc-400">{edge.from}</span>
                          <ArrowRight className="w-4 h-4 text-zinc-600" />
                          <span className="text-zinc-400">{edge.to}</span>
                        </div>
                      ))
                    }
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center text-zinc-500 py-8">
                <Circle className="w-12 h-12 mx-auto mb-3 text-zinc-600" />
                <p>노드를 클릭하여</p>
                <p>상세 정보를 확인하세요</p>
              </div>
            )}
          </div>

          {/* 현재 작업 정보 */}
          {currentAgentStatus?.current_task && (
            <div className="p-4 border-t border-dark-border bg-zinc-800/50">
              <label className="text-xs text-zinc-500 uppercase">현재 작업</label>
              <p className="text-sm text-zinc-300 mt-1 line-clamp-3">
                {currentAgentStatus.current_task}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* 범례 */}
      <div className="mt-4 flex items-center justify-center gap-6 text-sm text-zinc-400">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-zinc-700 border border-zinc-600" />
          <span>대기</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-blue-600 border border-blue-400 animate-pulse" />
          <span>실행 중</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-green-600 border border-green-400" />
          <span>완료</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded bg-red-600 border border-red-400" />
          <span>오류</span>
        </div>
      </div>
    </div>
  );
}
