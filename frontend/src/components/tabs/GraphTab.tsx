'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { agentApi, AgentRuntimeStatus, AgentGraph, GraphNode, logsApi, type TaskLog } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import { formatTimeWithSeconds } from '@/lib/utils';
import toast from 'react-hot-toast';
import {
  GitBranch, RefreshCw, ChevronDown, Play, Pause,
  Activity, Clock, CheckCircle, XCircle, Wrench, Users,
} from 'lucide-react';

// ─── 타입 ──────────────────────────────────────────────────────────────
interface Pos { x: number; y: number }
interface LocalNode extends GraphNode { pos: Pos }
interface LocalEdge { from: string; to: string; label?: string }
interface LocalGraph { agent_name: string; nodes: LocalNode[]; edges: LocalEdge[]; current_node: string | null }

// ─── 기본 그래프 ────────────────────────────────────────────────────────
const DEFAULT_GRAPHS: Record<string, { nodes: GraphNode[]; edges: { from: string; to: string; label?: string }[] }> = {
  JINXUS_CORE: {
    nodes: [
      { id: 'intake', label: '수신', description: '입력 수신 및 컨텍스트 로드' },
      { id: 'decompose', label: '분해', description: '명령 분해 및 서브태스크 생성' },
      { id: 'dispatch', label: '실행', description: '에이전트 할당 및 실행' },
      { id: 'aggregate', label: '취합', description: '결과 취합' },
      { id: 'reflect', label: '반성', description: '작업 반성 및 품질 평가' },
      { id: 'memory_write', label: '기억', description: '메모리 저장' },
      { id: 'respond', label: '응답', description: '최종 응답 생성' },
    ],
    edges: [
      { from: 'intake', to: 'decompose' }, { from: 'decompose', to: 'dispatch' },
      { from: 'dispatch', to: 'aggregate' }, { from: 'aggregate', to: 'reflect' },
      { from: 'reflect', to: 'memory_write' }, { from: 'memory_write', to: 'respond' },
    ],
  },
  DEFAULT: {
    nodes: [
      { id: 'receive', label: '수신', description: '작업 수신 및 초기화' },
      { id: 'plan', label: '계획', description: '실행 계획 수립' },
      { id: 'execute', label: '실행', description: '도구 사용 및 작업 수행' },
      { id: 'evaluate', label: '평가', description: '실행 결과 평가' },
      { id: 'reflect', label: '반성', description: '작업 반성 및 개선점 도출' },
      { id: 'memory_write', label: '기억', description: '장기기억에 저장' },
      { id: 'return_result', label: '완료', description: '결과 반환' },
    ],
    edges: [
      { from: 'receive', to: 'plan' }, { from: 'plan', to: 'execute' },
      { from: 'execute', to: 'evaluate' }, { from: 'evaluate', to: 'reflect', label: '성공' },
      { from: 'evaluate', to: 'execute', label: '재시도' },
      { from: 'reflect', to: 'memory_write' }, { from: 'memory_write', to: 'return_result' },
    ],
  },
};

export default function GraphTab() {
  const { agents } = useAppStore();
  const [selectedAgent, setSelectedAgent] = useState('JINXUS_CORE');
  const [graph, setGraph] = useState<LocalGraph | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<AgentRuntimeStatus[]>([]);
  const [recentLogs, setRecentLogs] = useState<TaskLog[]>([]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(true);

  const agentList = useMemo(() => {
    const names = ['JINXUS_CORE', ...agents.map(a => a.name)];
    return Array.from(new Set(names));
  }, [agents]);

  // ── 그래프 빌드 ──
  const buildGraph = useCallback((raw: AgentGraph | null, currentNode: string | null): LocalGraph => {
    const template = raw?.nodes?.length ? raw : (DEFAULT_GRAPHS[selectedAgent] || DEFAULT_GRAPHS.DEFAULT);
    const nodes: LocalNode[] = template.nodes.map((n, i) => ({
      ...n,
      pos: { x: 60 + i * 100, y: 30 },
    }));
    const edges: LocalEdge[] = (template as { edges: LocalEdge[] }).edges || [];
    return { agent_name: selectedAgent, nodes, edges, current_node: currentNode || (raw as AgentGraph)?.current_node || null };
  }, [selectedAgent]);

  // ── 데이터 로드 ──
  const loadData = useCallback(async () => {
    try {
      const [graphRes, statusRes, logsRes] = await Promise.all([
        agentApi.getGraph(selectedAgent).catch(() => null),
        agentApi.getAllRuntimeStatus().catch(() => ({ agents: [] })),
        logsApi.getLogs(selectedAgent === 'JINXUS_CORE' ? undefined : selectedAgent, 15, 0).catch(() => ({ logs: [], total: 0 })),
      ]);
      const statuses = statusRes.agents || [];
      setAgentStatuses(statuses);
      setRecentLogs(logsRes.logs || []);
      const currentStatus = statuses.find((a: AgentRuntimeStatus) => a.name === selectedAgent);
      setGraph(buildGraph(graphRes, currentStatus?.current_node?.toString() || null));
    } catch {
      setGraph(buildGraph(null, null));
    } finally {
      setLoading(false);
    }
  }, [selectedAgent, buildGraph]);

  useEffect(() => { loadData(); }, [loadData]);

  useEffect(() => {
    if (!autoRefresh) return;
    const iv = setInterval(loadData, POLLING_INTERVAL_MS);
    return () => clearInterval(iv);
  }, [autoRefresh, loadData]);

  if (loading && !graph) {
    return <div className="flex items-center justify-center h-full"><RefreshCw className="w-8 h-8 animate-spin text-primary" /></div>;
  }

  const currentNode = graph?.current_node;
  const currentAgentStatus = agentStatuses.find(a => a.name === selectedAgent);
  const successLogs = recentLogs.filter(l => l.success);
  const failLogs = recentLogs.filter(l => !l.success);
  const avgDuration = recentLogs.length > 0
    ? Math.round(recentLogs.reduce((s, l) => s + l.duration_ms, 0) / recentLogs.length)
    : 0;

  return (
    <div className="h-full flex flex-col gap-3">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <GitBranch className="w-5 h-5" />워크플로우
          </h1>
          <div className="relative">
            <select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)}
              className="appearance-none bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-1.5 pr-8 text-sm focus:outline-none focus:border-primary">
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
          <button onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${autoRefresh ? 'bg-green-600/20 text-green-400 border border-green-500/30' : 'bg-zinc-700 text-zinc-300'}`}>
            {autoRefresh ? <Play size={14} /> : <Pause size={14} />}
            {autoRefresh ? '실시간' : '정지'}
          </button>
          <button onClick={loadData} className="p-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 transition-colors">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* 본문: 3분할 */}
      <div className="flex-1 flex gap-3 min-h-0">

        {/* 왼쪽: 파이프라인 + 서브에이전트 */}
        <div className="w-56 flex-shrink-0 flex flex-col gap-3">
          {/* 파이프라인 노드 (세로 배치) */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-3 flex-1 overflow-y-auto">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wide mb-2">파이프라인</p>
            <div className="space-y-1">
              {graph?.nodes.map((node, i) => {
                const isActive = currentNode === node.id;
                return (
                  <div key={node.id} className="flex items-center gap-2">
                    {/* 연결선 */}
                    {i > 0 && <div className="w-px h-2 bg-zinc-700 ml-3 -mt-3" />}
                    <div className={`flex-1 flex items-center gap-2 px-3 py-2 rounded-lg border transition-all ${
                      isActive
                        ? 'bg-blue-500/15 border-blue-500/40 shadow-[0_0_8px_rgba(59,130,246,0.15)]'
                        : 'bg-zinc-800/60 border-zinc-700/50'
                    }`}>
                      {isActive && <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse flex-shrink-0" />}
                      <span className={`text-xs font-mono ${isActive ? 'text-blue-300' : 'text-zinc-400'}`}>
                        {node.label}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* 재시도 엣지 표시 */}
            {graph?.edges.filter(e => e.label === '재시도').map((e, i) => (
              <div key={i} className="mt-2 px-2 py-1 bg-amber-500/10 rounded text-[10px] text-amber-400 font-mono">
                {e.from} → {e.to} (재시도)
              </div>
            ))}
          </div>

          {/* 서브에이전트 */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-3">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wide mb-2 flex items-center gap-1">
              <Users size={10} />에이전트
            </p>
            <div className="space-y-1">
              {agentStatuses.filter(a => a.name !== 'JINXUS_CORE').map(agent => (
                <button key={agent.name}
                  onClick={() => setSelectedAgent(agent.name)}
                  className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors ${
                    selectedAgent === agent.name ? 'bg-primary/15 text-primary' : 'hover:bg-zinc-800 text-zinc-400'
                  }`}>
                  <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                    agent.status === 'working' ? 'bg-blue-500 animate-pulse' :
                    agent.status === 'error' ? 'bg-red-500' : 'bg-zinc-600'
                  }`} />
                  <span className="font-mono truncate">{agent.name.replace('JX_', '').replace('JINXUS_', '')}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* 중앙: 성능 지표 + 최근 실행 */}
        <div className="flex-1 flex flex-col gap-3 min-w-0">
          {/* 성능 카드 */}
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-dark-card border border-dark-border rounded-xl p-3">
              <div className="flex items-center gap-1.5 text-zinc-500 text-[10px] uppercase mb-1">
                <Activity size={11} />총 작업
              </div>
              <p className="text-xl font-bold">{recentLogs.length}</p>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-xl p-3">
              <div className="flex items-center gap-1.5 text-zinc-500 text-[10px] uppercase mb-1">
                <CheckCircle size={11} className="text-green-400" />성공률
              </div>
              <p className={`text-xl font-bold ${
                recentLogs.length === 0 ? 'text-zinc-500' :
                successLogs.length / recentLogs.length >= 0.8 ? 'text-green-400' :
                successLogs.length / recentLogs.length >= 0.5 ? 'text-amber-400' : 'text-red-400'
              }`}>
                {recentLogs.length > 0 ? `${Math.round(successLogs.length / recentLogs.length * 100)}%` : '—'}
              </p>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-xl p-3">
              <div className="flex items-center gap-1.5 text-zinc-500 text-[10px] uppercase mb-1">
                <Clock size={11} />평균 시간
              </div>
              <p className="text-xl font-bold text-zinc-300">
                {avgDuration > 0 ? (avgDuration < 1000 ? `${avgDuration}ms` : `${(avgDuration/1000).toFixed(1)}s`) : '—'}
              </p>
            </div>
            <div className="bg-dark-card border border-dark-border rounded-xl p-3">
              <div className="flex items-center gap-1.5 text-zinc-500 text-[10px] uppercase mb-1">
                <XCircle size={11} className="text-red-400" />실패
              </div>
              <p className={`text-xl font-bold ${failLogs.length > 0 ? 'text-red-400' : 'text-zinc-500'}`}>
                {failLogs.length}
              </p>
            </div>
          </div>

          {/* 실행 타임라인 */}
          <div className="flex-1 bg-dark-card border border-dark-border rounded-xl overflow-hidden flex flex-col">
            <div className="px-4 py-2.5 border-b border-dark-border flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-400">최근 실행 타임라인</span>
              <span className="text-[10px] text-zinc-600">{selectedAgent}</span>
            </div>
            <div className="flex-1 overflow-y-auto">
              {recentLogs.length === 0 ? (
                <div className="flex items-center justify-center h-full text-zinc-600 text-sm">실행 기록 없음</div>
              ) : (
                <div className="divide-y divide-zinc-800/50">
                  {recentLogs.map(log => {
                    const maxDuration = Math.max(...recentLogs.map(l => l.duration_ms), 1);
                    const barWidth = Math.max(5, (log.duration_ms / maxDuration) * 100);
                    return (
                      <div key={log.id} className="px-4 py-2.5 hover:bg-zinc-800/30 transition-colors">
                        <div className="flex items-center gap-2 mb-1">
                          {log.success
                            ? <CheckCircle size={12} className="text-green-400 flex-shrink-0" />
                            : <XCircle size={12} className="text-red-400 flex-shrink-0" />
                          }
                          <span className="text-xs text-zinc-300 truncate flex-1">{log.instruction}</span>
                          <span className="text-[10px] text-zinc-500 font-mono flex-shrink-0">
                            {log.duration_ms < 1000 ? `${log.duration_ms}ms` : `${(log.duration_ms/1000).toFixed(1)}s`}
                          </span>
                          <span className="text-[10px] text-zinc-600 flex-shrink-0">{formatTimeWithSeconds(log.created_at)}</span>
                        </div>
                        {/* 워터폴 바 */}
                        <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${log.success ? 'bg-green-500/60' : 'bg-red-500/60'}`}
                            style={{ width: `${barWidth}%` }}
                          />
                        </div>
                        {/* 도구 호출 표시 */}
                        {log.tool_calls && log.tool_calls.length > 0 && (
                          <div className="flex items-center gap-1 mt-1 flex-wrap">
                            <Wrench size={9} className="text-zinc-600" />
                            {log.tool_calls.map((tool, i) => (
                              <span key={i} className="px-1 py-0.5 text-[9px] bg-zinc-700/50 rounded text-zinc-500">{tool}</span>
                            ))}
                          </div>
                        )}
                        {log.failure_reason && (
                          <p className="text-[10px] text-red-400/70 mt-1 truncate">{log.failure_reason}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 오른쪽: 현재 상태 패널 */}
        <div className="w-64 flex-shrink-0 bg-dark-card border border-dark-border rounded-xl flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-dark-border">
            <span className="font-semibold text-sm">{selectedAgent.replace('JX_', '').replace('JINXUS_', '')}</span>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* 상태 */}
            <div>
              <label className="text-[10px] text-zinc-500 uppercase">상태</label>
              <div className="flex items-center gap-2 mt-1">
                <span className={`w-2.5 h-2.5 rounded-full ${
                  currentAgentStatus?.status === 'working' ? 'bg-blue-500 animate-pulse' :
                  currentAgentStatus?.status === 'error' ? 'bg-red-500' : 'bg-green-500/60'
                }`} />
                <span className="text-sm">
                  {currentAgentStatus?.status === 'working' ? '작업 중' :
                   currentAgentStatus?.status === 'error' ? '오류' : '대기'}
                </span>
              </div>
            </div>

            {/* 현재 작업 */}
            {currentAgentStatus?.current_task && (
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">현재 작업</label>
                <p className="text-xs text-zinc-300 mt-1">{currentAgentStatus.current_task}</p>
              </div>
            )}

            {/* 현재 노드 */}
            {currentNode && (
              <div>
                <label className="text-[10px] text-zinc-500 uppercase">현재 노드</label>
                <p className="text-sm text-blue-400 font-mono mt-1">{currentNode}</p>
              </div>
            )}

            {/* 사용 중인 도구 */}
            {currentAgentStatus?.current_tools && currentAgentStatus.current_tools.length > 0 && (
              <div>
                <label className="text-[10px] text-zinc-500 uppercase mb-1 block">사용 중 도구</label>
                <div className="flex flex-wrap gap-1">
                  {currentAgentStatus.current_tools.map(tool => (
                    <span key={tool} className="px-1.5 py-0.5 text-[10px] bg-blue-500/15 text-blue-400 rounded font-mono">{tool}</span>
                  ))}
                </div>
              </div>
            )}

            {/* 파이프라인 노드 설명 */}
            <div>
              <label className="text-[10px] text-zinc-500 uppercase mb-1.5 block">파이프라인 노드</label>
              <div className="space-y-1.5">
                {graph?.nodes.map(node => (
                  <div key={node.id} className={`px-2.5 py-1.5 rounded text-xs ${
                    currentNode === node.id ? 'bg-blue-500/15 text-blue-300 border border-blue-500/30' : 'bg-zinc-800/50 text-zinc-500'
                  }`}>
                    <span className="font-mono">{node.label}</span>
                    {node.description && <span className="text-zinc-600 ml-1">— {node.description}</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
