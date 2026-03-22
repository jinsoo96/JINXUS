'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  UserPlus, RotateCcw, Loader2, ChevronDown, ChevronUp,
  CheckCircle, XCircle, Clock, Wrench, Send, MessageSquare, Trash2, Users,
  Building2, RefreshCw, Hash,
} from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import { agentApi, hrApi, logsApi, chatApi, type AgentRuntimeStatus, type HRAgentRecord, type TaskLog, type SSEEvent } from '@/lib/api';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import { formatTimeWithSeconds } from '@/lib/utils';
import { PERSONA_MAP, TEAM_ORDER, getDisplayName, getRole, getPersona, getTeamGroups, sortByRank } from '@/lib/personas';
import toast from 'react-hot-toast';
import HireAgentModal from '../HireAgentModal';
import AgentCard from '../AgentCard';
import OrgChart from '../OrgChart';
import PixelOffice from '../playground/PixelOffice';

// ── 직원 현황 (부서 그리드) ──────────────────────────────────────

const TEAM_COLOR: Record<string, string> = {
  '임원':       'border-amber-500/30 bg-amber-500/5',
  '엔지니어링': 'border-blue-500/30 bg-blue-500/5',
  '리서치':     'border-green-500/30 bg-green-500/5',
  '운영':       'border-orange-500/30 bg-orange-500/5',
  '마케팅':     'border-pink-500/30 bg-pink-500/5',
  '기획':       'border-cyan-500/30 bg-cyan-500/5',
};

const TEAM_LABEL_COLOR: Record<string, string> = {
  '임원':       'text-amber-400',
  '엔지니어링': 'text-blue-400',
  '리서치':     'text-green-400',
  '운영':       'text-orange-400',
  '마케팅':     'text-pink-400',
  '기획':       'text-cyan-400',
};

interface EmployeeCardProps {
  agentCode: string;
  runtime: AgentRuntimeStatus | undefined;
  onSelect: (code: string) => void;
  onGoChannel: () => void;
}

function EmployeeCard({ agentCode, runtime, onSelect, onGoChannel }: EmployeeCardProps) {
  const persona = PERSONA_MAP[agentCode];
  if (!persona) return null;

  const isWorking = runtime?.status === 'working';
  const isError = runtime?.status === 'error';

  return (
    <div
      onClick={() => onSelect(agentCode)}
      className="bg-dark-card border border-dark-border rounded-xl p-3 flex flex-col gap-2 hover:border-zinc-600 transition-colors cursor-pointer"
    >
      {/* 상단: 아바타 + 이름 + 상태 */}
      <div className="flex items-start gap-2.5">
        <div className="relative flex-shrink-0">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center text-xl
            ${isWorking ? 'bg-blue-500/15 ring-1 ring-blue-500/40' : 'bg-dark-bg border border-dark-border'}`}>
            {persona.emoji}
          </div>
          <span className={`absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full border-2 border-dark-card
            ${isWorking ? 'bg-blue-500 shadow-[0_0_6px_rgba(59,130,246,0.8)]' :
              isError ? 'bg-red-500' : 'bg-green-500/70'}`} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm text-white leading-tight">{getDisplayName(agentCode)}</p>
          <p className="text-[11px] text-zinc-500 leading-tight">{getRole(agentCode)}</p>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onGoChannel(); }}
          className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-500 hover:text-zinc-300 text-[10px] transition-colors flex-shrink-0"
          title={`#${persona.channel} 채널로 이동`}
        >
          <Hash size={9} />
          {persona.team === '엔지니어링' ? '개발' : persona.team === '리서치' ? '리서치' : persona.team}
        </button>
      </div>
      {isWorking && runtime?.current_task && (
        <div className="px-2 py-1.5 bg-blue-500/10 rounded-lg border border-blue-500/20">
          <p className="text-[11px] text-blue-300 truncate">💬 {runtime.current_task}</p>
        </div>
      )}
      {isError && (
        <div className="px-2 py-1.5 bg-red-500/10 rounded-lg border border-red-500/20">
          <p className="text-[11px] text-red-300 truncate">⚠ {runtime?.error_message || '오류 발생'}</p>
        </div>
      )}
      {/* 인격 뱃지 */}
      {persona.personalityLabel && (
        <div className="flex items-center gap-1">
          <span className="text-[10px]">{persona.personalityEmoji}</span>
          <span className="text-[10px] text-zinc-500">{persona.personalityLabel}</span>
          {persona.mbti && (
            <span className="text-[9px] text-zinc-700 font-mono ml-auto">{persona.mbti}</span>
          )}
        </div>
      )}
      {!isWorking && !isError && !persona.personalityLabel && (
        <p className="text-[10px] text-zinc-600 px-0.5">대기 중</p>
      )}
    </div>
  );
}

// ── 메인 탭 ──────────────────────────────────────────────────────

interface DirectMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
  timestamp: Date;
}

export default function AgentsTab({ isActive = true }: { isActive?: boolean }) {
  const { agents, hrAgents, loadAgents, setActiveTab, personasVersion } = useAppStore();
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [showHireModal, setShowHireModal] = useState(false);
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});
  const [firedAgents, setFiredAgents] = useState<HRAgentRecord[]>([]);
  const [showFired, setShowFired] = useState(false);
  const [logsMap, setLogsMap] = useState<Record<string, TaskLog[]>>({});
  const [logsLoading, setLogsLoading] = useState<Record<string, boolean>>({});

  // 서브탭: 직원현황 vs 플레이그라운드
  const [subTab, setSubTab] = useState<'status' | 'playground'>('status');

  // 직접 채팅
  const [chatAgent, setChatAgent] = useState<string | null>(null);
  const [directMessages, setDirectMessages] = useState<DirectMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [showOrgChart, setShowOrgChart] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchAllRuntimes = async () => {
    try {
      const res = await agentApi.getAllRuntimeStatus();
      const map: Record<string, AgentRuntimeStatus> = {};
      for (const agent of res.agents) map[agent.name] = agent;
      setRuntimeMap(map);
    } catch (err) {
      console.error('Failed to fetch runtime statuses:', err);
    }
  };

  const fetchFiredAgents = async () => {
    try {
      const res = await hrApi.getFiredAgents();
      setFiredAgents(res.agents);
    } catch { /* 없으면 무시 */ }
  };

  // 플레이그라운드 SSE 연결 (실시간 상태 업데이트)
  useEffect(() => {
    if (subTab !== 'playground' || !isActive) return;

    const es = new EventSource('/api/agents/runtime/stream');

    es.addEventListener('init', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setRuntimeMap(prev => ({...prev, [data.agent]: {
          name: data.agent, status: data.status, current_node: data.node,
          current_task: data.task, current_tools: data.tools || [],
          last_update: null, error_message: null,
        }}));
      } catch { /* 파싱 실패 무시 */ }
    });

    es.addEventListener('state_change', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setRuntimeMap(prev => ({...prev, [data.agent]: {
          ...prev[data.agent], name: data.agent, status: data.status,
          current_task: data.task || prev[data.agent]?.current_task || null,
          current_node: prev[data.agent]?.current_node || null,
          current_tools: prev[data.agent]?.current_tools || [],
          last_update: null,
          error_message: data.error || null,
        }}));
      } catch { /* 파싱 실패 무시 */ }
    });

    es.addEventListener('node_change', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setRuntimeMap(prev => {
          const existing = prev[data.agent];
          if (!existing) return prev;
          return {...prev, [data.agent]: { ...existing, current_node: data.node }};
        });
      } catch { /* 파싱 실패 무시 */ }
    });

    es.addEventListener('tools_change', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setRuntimeMap(prev => {
          const existing = prev[data.agent];
          if (!existing) return prev;
          return {...prev, [data.agent]: { ...existing, current_tools: data.tools || [] }};
        });
      } catch { /* 파싱 실패 무시 */ }
    });

    es.onerror = () => {
      // SSE 오류 시 자동 재연결됨 (EventSource 기본 동작)
      // 연결 불가 시 폴링 fallback은 아래 useEffect에서 처리
    };

    return () => es.close();
  }, [subTab, isActive]);

  // 폴링 (직원 현황 탭 또는 SSE fallback)
  useEffect(() => {
    if (!isActive) return;
    fetchAllRuntimes();
    fetchFiredAgents();
    // 플레이그라운드 탭에서는 SSE 사용, 직원 현황에서만 폴링
    if (subTab === 'playground') return;
    const interval = setInterval(fetchAllRuntimes, POLLING_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isActive, subTab]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [directMessages]);

  const handleToggleLogs = async (agentName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (expandedAgent === agentName) {
      setExpandedAgent(null);
      return;
    }
    setExpandedAgent(agentName);
    if (logsMap[agentName]) return;
    setLogsLoading((prev) => ({ ...prev, [agentName]: true }));
    try {
      const res = await logsApi.getLogs(agentName, 10, 0);
      setLogsMap((prev) => ({ ...prev, [agentName]: res.logs }));
    } catch {
      setLogsMap((prev) => ({ ...prev, [agentName]: [] }));
    } finally {
      setLogsLoading((prev) => ({ ...prev, [agentName]: false }));
    }
  };

  const handleSelectAgent = (agentName: string) => {
    if (chatAgent === agentName) return;
    abortRef.current?.abort();
    setChatAgent(agentName);
    setDirectMessages([]);
    setChatInput('');
  };

  const handleSendDirect = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!chatAgent || !chatInput.trim() || chatLoading) return;

    const userMsg: DirectMessage = {
      role: 'user',
      content: chatInput.trim(),
      timestamp: new Date(),
    };
    setDirectMessages((prev) => [...prev, userMsg]);
    const inputSnapshot = chatInput.trim();
    setChatInput('');
    setChatLoading(true);

    const abort = new AbortController();
    abortRef.current = abort;

    const assistantMsg: DirectMessage = {
      role: 'assistant',
      content: '',
      toolCalls: [],
      timestamp: new Date(),
    };
    setDirectMessages((prev) => [...prev, assistantMsg]);

    await chatApi.streamAgentDirect(
      chatAgent,
      inputSnapshot,
      undefined,
      (event: SSEEvent) => {
        if (event.event === 'message' && event.data.content) {
          setDirectMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === 'assistant') {
              const updated = prev.slice(0, -1);
              updated.push({ ...last, content: event.data.content! });
              return updated;
            }
            return prev;
          });
        } else if (event.event === 'tool_call' && event.data.tool) {
          setDirectMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === 'assistant') {
              const tool = `${event.data.tool} (${event.data.status ?? 'done'})`;
              const updated = prev.slice(0, -1);
              updated.push({
                ...last,
                toolCalls: [...(last.toolCalls || []), tool],
              });
              return updated;
            }
            return prev;
          });
        } else if (event.event === 'error') {
          setDirectMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = {
                ...last,
                content: `오류: ${event.data.error || '알 수 없는 오류'}`,
              };
            }
            return updated;
          });
        }
      },
      (error) => {
        toast.error(`에이전트 오류: ${error.message}`);
        setDirectMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last && last.role === 'assistant' && !last.content) {
            updated[updated.length - 1] = { ...last, content: `오류: ${error.message}` };
          }
          return updated;
        });
      },
      abort,
    );

    setChatLoading(false);
  };

  const handleAgentHired = () => {
    loadAgents();
    fetchFiredAgents();
  };

  const handleRehire = async (agentId: string) => {
    try {
      const res = await hrApi.rehireAgent(agentId);
      toast.success(res.message);
      loadAgents();
      fetchFiredAgents();
    } catch {
      toast.error('재고용 실패');
    }
  };

  const handleGoChannel = useCallback(() => {
    setActiveTab('channel');
  }, [setActiveTab]);

  const getStatusDot = (status?: string) => {
    if (status === 'working')
      return <span className="w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_6px_rgba(59,130,246,0.8)] animate-pulse flex-shrink-0" />;
    if (status === 'error')
      return <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />;
    return <span className="w-2 h-2 rounded-full bg-green-500/60 flex-shrink-0" />;
  };

  const getStatusBadge = (status?: string) => {
    if (status === 'working')
      return <span className="px-1.5 py-0.5 text-[10px] rounded bg-blue-500/20 text-blue-400">작업 중</span>;
    if (status === 'error')
      return <span className="px-1.5 py-0.5 text-[10px] rounded bg-red-500/20 text-red-400">오류</span>;
    return <span className="px-1.5 py-0.5 text-[10px] rounded bg-zinc-700/60 text-zinc-500">대기</span>;
  };

  const selectedRuntime = chatAgent ? runtimeMap[chatAgent] : null;
  const hiredSet = new Set(hrAgents.map(a => a.name));
  const workingCount = Object.values(runtimeMap).filter(r => r.status === 'working').length;
  // 동적 페르소나 맵 기반 팀 그룹 (personasVersion 갱신 시 자동 재계산)
  const teamAgents = useMemo(() => getTeamGroups(), [personasVersion]);
  // 직급순 정렬된 에이전트 목록
  const sortedHrAgents = useMemo(
    () => [...hrAgents].sort((a, b) => sortByRank(a.name, b.name)),
    [hrAgents],
  );

  return (
    <div className="flex gap-4 h-full min-h-0">

      {/* ── 왼쪽 패널: 에이전트 목록 + 관리 ── */}
      <div className="w-48 md:w-64 flex-shrink-0 flex flex-col gap-3 min-h-0">

        {/* 헤더 */}
        <div className="flex items-center justify-between flex-shrink-0">
          <span className="text-sm font-semibold text-zinc-300">에이전트 ({hiredSet.size})</span>
          <button
            onClick={() => setShowHireModal(true)}
            aria-label="에이전트 고용"
            className="flex items-center gap-1 px-2.5 py-1.5 bg-primary hover:bg-primary/90 text-black rounded text-xs font-medium transition-colors"
          >
            <UserPlus size={11} />
            고용
          </button>
        </div>

        {/* 스크롤 가능한 영역 */}
        <div className="flex-1 flex flex-col gap-3 min-h-0 overflow-hidden pr-0.5">

        {/* 주요 에이전트 목록 — 직급순 정렬, 자체 스크롤 */}
        <div className="flex-1 min-h-0 overflow-y-auto border border-dark-border rounded-xl">
          {sortedHrAgents.map((agent) => {
            const runtime = runtimeMap[agent.name] || null;
            const isExpanded = expandedAgent === agent.name;
            const isSelected = chatAgent === agent.name;
            const logs = logsMap[agent.name] || [];
            const loading = logsLoading[agent.name] || false;

            return (
              <div key={agent.name} className="border-b border-dark-border last:border-0">
                <div
                  onClick={() => handleSelectAgent(agent.name)}
                  className={`flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors ${
                    isSelected
                      ? 'bg-primary/10 border-l-2 border-primary'
                      : 'hover:bg-zinc-800/40 border-l-2 border-transparent'
                  }`}
                >
                  {getStatusDot(runtime?.status)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium text-white truncate">{getDisplayName(agent.name)}</span>
                      {getStatusBadge(runtime?.status)}
                    </div>
                    <p className="text-[10px] text-zinc-600 truncate">{getRole(agent.name)}</p>
                    {runtime?.status === 'working' && runtime.current_task && (
                      <p className="text-[10px] text-blue-300/70 truncate">{runtime.current_task}</p>
                    )}
                  </div>
                  <span className={`text-[11px] font-mono flex-shrink-0 ${
                    agent.success_rate >= 0.8 ? 'text-green-400' :
                    agent.success_rate >= 0.5 ? 'text-amber-400' : 'text-red-400'
                  }`}>
                    {(agent.success_rate * 100).toFixed(0)}%
                  </span>
                  <button
                    onClick={(e) => handleToggleLogs(agent.name, e)}
                    className="p-0.5 hover:text-zinc-300 text-zinc-600 transition-colors"
                    title="작업 로그"
                  >
                    {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                </div>

                {runtime?.status === 'working' && runtime.current_tools && runtime.current_tools.length > 0 && (
                  <div className="px-3 pb-1.5 flex items-center gap-1 flex-wrap">
                    <Wrench size={9} className="text-zinc-600" />
                    {runtime.current_tools.map((tool) => (
                      <span key={tool} className="px-1 py-0.5 text-[9px] bg-zinc-700/50 rounded text-zinc-400">
                        {tool}
                      </span>
                    ))}
                  </div>
                )}

                {isExpanded && (
                  <div className="border-t border-dark-border bg-zinc-900/60 px-3 py-2">
                    <p className="text-[9px] text-zinc-500 uppercase tracking-wide mb-1.5">최근 로그</p>
                    {loading ? (
                      <Loader2 size={12} className="animate-spin text-zinc-500" />
                    ) : logs.length === 0 ? (
                      <p className="text-[10px] text-zinc-600">기록 없음</p>
                    ) : (
                      <div className="space-y-1">
                        {logs.map((log) => (
                          <div key={log.id} className="flex items-center gap-1.5 text-[10px]">
                            {log.success
                              ? <CheckCircle size={9} className="text-green-400 flex-shrink-0" />
                              : <XCircle size={9} className="text-red-400 flex-shrink-0" />
                            }
                            <span className="text-zinc-400 truncate flex-1">{log.instruction}</span>
                            <span className="text-zinc-600 flex-shrink-0 flex items-center gap-0.5">
                              <Clock size={8} />
                              {log.duration_ms < 1000 ? `${log.duration_ms}ms` : `${(log.duration_ms / 1000).toFixed(1)}s`}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {agents.length === 0 && (
            <div className="px-3 py-6 text-center text-zinc-500 text-xs flex flex-col items-center gap-2">
              <Loader2 size={16} className="animate-spin" />
              <span>에이전트 로딩 중...</span>
            </div>
          )}
        </div>

        {/* 조직도 */}
        <div className="flex-shrink-0">
          <button
            onClick={() => setShowOrgChart(!showOrgChart)}
            className="flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 mb-1.5 transition-colors"
          >
            <Users size={11} />
            조직도 {showOrgChart ? '▲' : '▼'}
          </button>
          {showOrgChart && <OrgChart />}
        </div>

        {/* 해고된 에이전트 */}
        {firedAgents.length > 0 && (
          <div className="flex-shrink-0">
            <button
              onClick={() => setShowFired(!showFired)}
              className="flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 mb-1.5 transition-colors"
            >
              <RotateCcw size={11} />
              해고됨 ({firedAgents.length}) {showFired ? '▲' : '▼'}
            </button>
            {showFired && (
              <div className="border border-dark-border rounded-xl overflow-hidden">
                {firedAgents.map((agent, i) => (
                  <div
                    key={agent.id}
                    className={`flex items-center gap-2 px-3 py-2 opacity-60 ${i < firedAgents.length - 1 ? 'border-b border-dark-border' : ''}`}
                  >
                    <span className="w-2 h-2 rounded-full bg-zinc-600 flex-shrink-0" />
                    <span className="text-xs text-zinc-300 flex-1 truncate">{getDisplayName(agent.name)}</span>
                    <button
                      onClick={() => handleRehire(agent.id)}
                      className="flex items-center gap-0.5 px-1.5 py-0.5 bg-blue-600/20 hover:bg-blue-600/40 text-blue-400 rounded text-[10px] transition-colors"
                    >
                      <RotateCcw size={9} />
                      재고용
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        </div>{/* end scrollable */}
      </div>

      {/* ── 오른쪽 패널 ── */}
      <div className="flex-1 flex flex-col min-h-0 border border-dark-border rounded-xl overflow-hidden">
        {!chatAgent ? (
          <>
            {/* 서브탭 헤더 */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-dark-border bg-zinc-900/60 flex-shrink-0">
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setSubTab('status')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    subTab === 'status'
                      ? 'bg-zinc-700/60 text-white'
                      : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
                  }`}
                >
                  <Building2 size={13} />
                  직원 현황
                </button>
                <button
                  onClick={() => setSubTab('playground')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    subTab === 'playground'
                      ? 'bg-zinc-700/60 text-white'
                      : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
                  }`}
                >
                  <span style={{ fontSize: 13 }}>🏢</span>
                  플레이그라운드
                </button>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span className="px-2 py-0.5 bg-zinc-800 rounded-full">전체 {hiredSet.size}명</span>
                  {workingCount > 0 && (
                    <span className="px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded-full flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
                      {workingCount}명 작업 중
                    </span>
                  )}
                </div>
                <button
                  onClick={fetchAllRuntimes}
                  className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors"
                  title="새로고침"
                >
                  <RefreshCw size={14} />
                </button>
              </div>
            </div>

            {subTab === 'status' ? (
              /* 부서별 직원 현황 그리드 */
              <div className="flex-1 overflow-y-auto p-4">
                <p className="text-xs text-zinc-500 mb-4">에이전트 카드를 클릭하면 직접 대화할 수 있습니다</p>

                {/* 부서별 그리드 */}
                <div className="space-y-5">
                  {TEAM_ORDER.map(team => {
                    const members = (teamAgents[team] || []).filter(code => hiredSet.has(code)).sort(sortByRank);
                    if (members.length === 0) return null;
                    return (
                      <div key={team}>
                        <div className={`flex items-center gap-2 mb-2.5 pb-1.5 border-b ${TEAM_COLOR[team] ?? 'border-zinc-700/30 bg-zinc-700/5'}`}>
                          <span className={`text-xs font-bold uppercase tracking-wider ${TEAM_LABEL_COLOR[team] ?? 'text-zinc-400'}`}>
                            {team}
                          </span>
                          <span className="text-[10px] text-zinc-600">{members.length}명</span>
                        </div>
                        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2.5">
                          {members.map(code => (
                            <EmployeeCard
                              key={code}
                              agentCode={code}
                              runtime={runtimeMap[code]}
                              onSelect={handleSelectAgent}
                              onGoChannel={handleGoChannel}
                            />
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {agents.length === 0 && (
                  <div className="flex items-center justify-center h-40">
                    <div className="text-center text-zinc-600">
                      <Building2 size={32} className="mx-auto mb-2" />
                      <p className="text-sm">에이전트를 고용해주세요</p>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              /* 플레이그라운드 — 픽셀 오피스 */
              <PixelOffice
                runtimeMap={runtimeMap}
                hiredSet={hiredSet}
                onSelectAgent={handleSelectAgent}
              />
            )}
          </>
        ) : (
          <>
            {/* 채팅 헤더 */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border bg-zinc-900/60">
              <div className="flex items-center gap-2">
                {getStatusDot(selectedRuntime?.status)}
                <span className="text-lg">{getPersona(chatAgent)?.emoji ?? '🤖'}</span>
                <span className="font-semibold text-white">{getDisplayName(chatAgent)}</span>
                <span className="text-xs text-zinc-500">{getRole(chatAgent)}</span>
                {getStatusBadge(selectedRuntime?.status)}
                <span className="text-xs text-zinc-500 ml-1">직접 대화</span>
              </div>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setChatAgent(null)}
                  className="flex items-center gap-1 px-2 py-1.5 hover:bg-zinc-800 rounded text-zinc-500 hover:text-zinc-300 transition-colors text-xs"
                  title="직원 현황으로"
                >
                  <Building2 size={12} />
                  현황
                </button>
                <button
                  onClick={() => setDirectMessages([])}
                  className="p-1.5 hover:bg-zinc-800 rounded text-zinc-500 hover:text-zinc-300 transition-colors"
                  title="대화 초기화"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>

            {/* 메시지 목록 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {directMessages.length === 0 && (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <MessageSquare size={28} className="mx-auto mb-2 text-zinc-700" />
                    <p className="text-xs text-zinc-500">{getDisplayName(chatAgent)}에게 직접 지시를 내려보세요</p>
                  </div>
                </div>
              )}
              {directMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] ${msg.role === 'user' ? 'order-2' : 'order-1'}`}>
                    {msg.role === 'assistant' && msg.toolCalls && msg.toolCalls.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1.5">
                        {msg.toolCalls.map((tc, j) => (
                          <span key={j} className="flex items-center gap-1 px-1.5 py-0.5 text-[10px] bg-zinc-700/60 rounded text-zinc-400">
                            <Wrench size={8} />
                            {tc}
                          </span>
                        ))}
                      </div>
                    )}
                    <div className={`px-3 py-2 rounded-xl text-sm whitespace-pre-wrap break-words ${
                      msg.role === 'user'
                        ? 'bg-primary/20 text-zinc-100'
                        : 'bg-zinc-800 text-zinc-200'
                    }`}>
                      {msg.role === 'assistant' && !msg.content && chatLoading && i === directMessages.length - 1 ? (
                        <Loader2 size={14} className="animate-spin text-zinc-500" />
                      ) : (
                        msg.content || <span className="text-zinc-600 italic">응답 없음</span>
                      )}
                    </div>
                    <p className="text-[10px] text-zinc-600 mt-1 px-1">
                      {formatTimeWithSeconds(msg.timestamp.toISOString())}
                    </p>
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            {/* 입력창 */}
            <form onSubmit={handleSendDirect} className="px-4 py-3 border-t border-dark-border">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder={`${getDisplayName(chatAgent)}에게 지시...`}
                  disabled={chatLoading}
                  aria-label="에이전트 직접 지시 입력"
                  className="flex-1 bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-colors disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={chatLoading || !chatInput.trim()}
                  aria-label="메시지 전송"
                  className="px-3 py-2 bg-primary hover:bg-primary/90 text-black rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {chatLoading
                    ? <Loader2 size={16} className="animate-spin" />
                    : <Send size={16} />
                  }
                </button>
              </div>
            </form>
          </>
        )}
      </div>

      <HireAgentModal
        isOpen={showHireModal}
        onClose={() => setShowHireModal(false)}
        onHired={handleAgentHired}
      />
    </div>
  );
}
