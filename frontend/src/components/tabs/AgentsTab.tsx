'use client';

import { useState, useEffect, useRef } from 'react';
import {
  UserPlus, RotateCcw, Loader2, Bot, Code2, Search, ChevronDown, ChevronUp,
  CheckCircle, XCircle, Clock, Wrench, Send, MessageSquare, Trash2, Users,
} from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import { agentApi, hrApi, logsApi, chatApi, type AgentRuntimeStatus, type HRAgentRecord, type CodingSpecialist, type TaskLog, type SSEEvent } from '@/lib/api';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import { formatTimeWithSeconds } from '@/lib/utils';
import toast from 'react-hot-toast';
import HireAgentModal from '../HireAgentModal';
import AgentCard from '../AgentCard';
import OrgChart from '../OrgChart';

interface DirectMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
  timestamp: Date;
}

export default function AgentsTab({ isActive = true }: { isActive?: boolean }) {
  const { agents, loadAgents } = useAppStore();
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [showHireModal, setShowHireModal] = useState(false);
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});
  const [firedAgents, setFiredAgents] = useState<HRAgentRecord[]>([]);
  const [showFired, setShowFired] = useState(false);
  const [coderTeam, setCoderTeam] = useState<CodingSpecialist[]>([]);
  const [researcherTeam, setResearcherTeam] = useState<CodingSpecialist[]>([]);
  const [logsMap, setLogsMap] = useState<Record<string, TaskLog[]>>({});
  const [logsLoading, setLogsLoading] = useState<Record<string, boolean>>({});

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

  const fetchCoderTeam = async () => {
    try {
      const res = await agentApi.getCoderTeam();
      setCoderTeam(res.team);
    } catch { /* 무시 */ }
  };

  const fetchResearcherTeam = async () => {
    try {
      const res = await agentApi.getResearcherTeam();
      setResearcherTeam(res.team);
    } catch { /* 무시 */ }
  };

  useEffect(() => {
    if (!isActive) return;
    fetchAllRuntimes();
    fetchFiredAgents();
    fetchCoderTeam();
    fetchResearcherTeam();
    const interval = setInterval(() => {
      fetchAllRuntimes();
      fetchCoderTeam();
      fetchResearcherTeam();
    }, POLLING_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  // 채팅창 자동 스크롤
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
    // 진행 중인 요청 취소
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

    // assistant 메시지 자리 미리 확보
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
          // 마지막 메시지만 교체 (전체 배열 복사 방지)
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
  const shortName = (name: string) => name.replace('JX_', '').replace('JINXUS_', '').replace('JS_', '');

  return (
    <div className="flex gap-4 h-full min-h-0">

      {/* ── 왼쪽 패널: 에이전트 목록 ── */}
      <div className="w-64 flex-shrink-0 flex flex-col gap-3">

        {/* 헤더 */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-zinc-300">에이전트 ({agents.length})</span>
          <button
            onClick={() => setShowHireModal(true)}
            className="flex items-center gap-1 px-2 py-1 bg-primary hover:bg-primary/90 text-black rounded text-[11px] font-medium transition-colors"
          >
            <UserPlus size={11} />
            고용
          </button>
        </div>

        {/* 주요 에이전트 */}
        <div className="border border-dark-border rounded-xl overflow-hidden">
          {agents.map((agent) => {
            const runtime = runtimeMap[agent.name] || null;
            const isExpanded = expandedAgent === agent.name;
            const isSelected = chatAgent === agent.name;
            const logs = logsMap[agent.name] || [];
            const loading = logsLoading[agent.name] || false;

            return (
              <div key={agent.name} className="border-b border-dark-border last:border-0">
                {/* 에이전트 행 */}
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
                      <span className="text-sm font-medium text-white truncate">{shortName(agent.name)}</span>
                      {getStatusBadge(runtime?.status)}
                    </div>
                    {runtime?.status === 'working' && runtime.current_task && (
                      <p className="text-[10px] text-blue-300/70 truncate">{runtime.current_task}</p>
                    )}
                  </div>
                  {/* 성공률 */}
                  <span className={`text-[11px] font-mono flex-shrink-0 ${
                    agent.success_rate >= 0.8 ? 'text-green-400' :
                    agent.success_rate >= 0.5 ? 'text-amber-400' : 'text-red-400'
                  }`}>
                    {(agent.success_rate * 100).toFixed(0)}%
                  </span>
                  {/* 로그 토글 */}
                  <button
                    onClick={(e) => handleToggleLogs(agent.name, e)}
                    className="p-0.5 hover:text-zinc-300 text-zinc-600 transition-colors"
                    title="작업 로그"
                  >
                    {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                </div>

                {/* 도구 사용 중 표시 */}
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

                {/* 인라인 로그 */}
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
            <div className="px-3 py-6 text-center text-zinc-500 text-xs">로딩 중...</div>
          )}
        </div>

        {/* JX_CODER 전문가 팀 */}
        {coderTeam.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-1.5">
              <Code2 size={11} className="text-primary" />
              <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wide">코더 팀</span>
            </div>
            <div className="border border-dark-border rounded-xl overflow-hidden">
              {coderTeam.map((specialist, i) => (
                <div
                  key={specialist.name}
                  className={`flex items-center gap-2 px-3 py-1.5 ${i < coderTeam.length - 1 ? 'border-b border-dark-border' : ''}`}
                >
                  {getStatusDot(specialist.status)}
                  <span className="text-xs text-zinc-300">{specialist.name.replace('JX_', '')}</span>
                  {getStatusBadge(specialist.status)}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* JX_RESEARCHER 전문가 팀 */}
        {researcherTeam.length > 0 && (
          <div>
            <div className="flex items-center gap-1.5 mb-1.5">
              <Search size={11} className="text-blue-400" />
              <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wide">리서치 팀</span>
            </div>
            <div className="border border-dark-border rounded-xl overflow-hidden">
              {researcherTeam.map((specialist, i) => (
                <div
                  key={specialist.name}
                  className={`flex items-center gap-2 px-3 py-1.5 ${i < researcherTeam.length - 1 ? 'border-b border-dark-border' : ''}`}
                >
                  {getStatusDot(specialist.status)}
                  <span className="text-xs text-zinc-300">{specialist.name.replace('JX_', '')}</span>
                  {getStatusBadge(specialist.status)}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 조직도 */}
        <div>
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
          <div>
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
                    <span className="text-xs text-zinc-300 flex-1 truncate">{shortName(agent.name)}</span>
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
      </div>

      {/* ── 오른쪽 패널: 직접 채팅 ── */}
      <div className="flex-1 flex flex-col min-h-0 border border-dark-border rounded-xl overflow-hidden">
        {!chatAgent ? (
          /* 에이전트 미선택 — 카드 그리드로 전체 에이전트 현황 표시 */
          <div className="flex-1 overflow-y-auto p-4">
            <p className="text-xs text-zinc-500 mb-3">에이전트를 선택하면 직접 대화할 수 있습니다</p>
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
              {agents.map((agent) => (
                <AgentCard
                  key={agent.name}
                  agent={agent}
                  runtime={runtimeMap[agent.name] || null}
                  onSelect={() => handleSelectAgent(agent.name)}
                  selected={false}
                />
              ))}
            </div>
          </div>
        ) : (
          <>
            {/* 채팅 헤더 */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border bg-zinc-900/60">
              <div className="flex items-center gap-2">
                {getStatusDot(selectedRuntime?.status)}
                <span className="font-semibold text-white">{shortName(chatAgent)}</span>
                {getStatusBadge(selectedRuntime?.status)}
                <span className="text-xs text-zinc-500 ml-1">직접 대화</span>
              </div>
              <button
                onClick={() => setDirectMessages([])}
                className="p-1.5 hover:bg-zinc-800 rounded text-zinc-500 hover:text-zinc-300 transition-colors"
                title="대화 초기화"
              >
                <Trash2 size={14} />
              </button>
            </div>

            {/* 메시지 목록 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {directMessages.length === 0 && (
                <div className="flex items-center justify-center h-full">
                  <div className="text-center">
                    <MessageSquare size={28} className="mx-auto mb-2 text-zinc-700" />
                    <p className="text-xs text-zinc-500">{shortName(chatAgent)}에게 직접 지시를 내려보세요</p>
                  </div>
                </div>
              )}
              {directMessages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] ${msg.role === 'user' ? 'order-2' : 'order-1'}`}>
                    {/* 도구 호출 배지 */}
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
                  placeholder={`${shortName(chatAgent)}에게 지시...`}
                  disabled={chatLoading}
                  className="flex-1 bg-zinc-900 border border-dark-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={chatLoading || !chatInput.trim()}
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
