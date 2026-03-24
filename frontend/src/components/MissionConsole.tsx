'use client';

import { useState, useRef, useEffect, useCallback, memo } from 'react';
import { missionApi, channelApi, type MissionData, type MissionSSEEvent } from '@/lib/api';
import { getFirstName, getPersona } from '@/lib/personas';
import { useAppStore } from '@/store/useAppStore';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import {
  Send, Loader2, Target, CheckCircle2, XCircle,
  Users, ChevronDown, Zap, Swords, Crown,
  Trash2, Square, Activity, ShieldCheck, Ban, Pencil,
} from 'lucide-react';

// 미션 타입별 아이콘/색상
const MISSION_TYPE_CONFIG: Record<string, { icon: typeof Zap; color: string; label: string; bg: string }> = {
  quick: { icon: Zap, color: '#22c55e', label: 'QUICK', bg: 'rgba(34,197,94,0.1)' },
  standard: { icon: Target, color: '#3b82f6', label: 'STANDARD', bg: 'rgba(59,130,246,0.1)' },
  epic: { icon: Swords, color: '#f59e0b', label: 'EPIC', bg: 'rgba(245,158,11,0.1)' },
  raid: { icon: Crown, color: '#ef4444', label: 'RAID', bg: 'rgba(239,68,68,0.1)' },
};

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  briefing: { color: '#f59e0b', label: '브리핑' },
  in_progress: { color: '#3b82f6', label: '수행중' },
  review: { color: '#8b5cf6', label: '리뷰' },
  complete: { color: '#22c55e', label: '완료' },
  failed: { color: '#ef4444', label: '실패' },
  cancelled: { color: '#6b7280', label: '취소' },
};

// 진행 중인 상태인지 확인
function isActiveStatus(status: string) {
  return ['briefing', 'in_progress', 'review'].includes(status);
}

// 로그 엔트리 타입
interface LogEntry {
  id: number;
  timestamp: string;
  agent: string;
  emoji: string;
  message: string;
  type: 'dm' | 'huddle' | 'report' | 'broadcast' | 'thinking' | 'status' | 'result';
}

// 로그 타입별 색상
function getLogColor(type: LogEntry['type']): string {
  switch (type) {
    case 'dm': return 'text-blue-400';
    case 'huddle': return 'text-amber-400';
    case 'report': return 'text-green-400';
    case 'broadcast': return 'text-purple-400';
    case 'thinking': return 'text-zinc-500';
    case 'status': return 'text-cyan-400';
    case 'result': return 'text-emerald-300';
    default: return 'text-zinc-400';
  }
}

function getLogPrefix(type: LogEntry['type']): string {
  switch (type) {
    case 'dm': return 'DM';
    case 'huddle': return 'MTG';
    case 'report': return 'RPT';
    case 'broadcast': return 'ALL';
    case 'thinking': return '...';
    case 'status': return 'SYS';
    case 'result': return 'OUT';
    default: return '   ';
  }
}

// 미션 히스토리 항목
const MissionHistoryItem = memo(function MissionHistoryItem({
  mission,
  isSelected,
  onClick,
  onCancel,
  onDelete,
}: {
  mission: MissionData;
  isSelected: boolean;
  onClick: () => void;
  onCancel: (e: React.MouseEvent) => void;
  onDelete: (e: React.MouseEvent) => void;
}) {
  const typeConf = MISSION_TYPE_CONFIG[mission.type] || MISSION_TYPE_CONFIG.standard;
  const statusConf = STATUS_CONFIG[mission.status] || STATUS_CONFIG.briefing;
  const TypeIcon = typeConf.icon;
  const active = isActiveStatus(mission.status);

  return (
    <div
      onClick={onClick}
      className={`group relative w-full text-left px-3 py-2 rounded-lg border transition-all cursor-pointer ${
        isSelected
          ? 'bg-white/[0.05] border-zinc-600'
          : 'bg-transparent border-transparent hover:bg-white/[0.03] hover:border-zinc-700/50'
      }`}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <TypeIcon size={10} style={{ color: typeConf.color }} />
        <span className="text-[9px] font-bold" style={{ color: typeConf.color }}>{typeConf.label}</span>
        {/* 상태 뱃지 — 진행중이면 펄스 표시 */}
        {active ? (
          <span className="text-[9px] ml-auto flex items-center gap-1 px-1.5 py-0.5 rounded"
            style={{ color: statusConf.color, background: `${statusConf.color}15` }}>
            <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: statusConf.color }} />
            {statusConf.label}
          </span>
        ) : (
          <span className="text-[9px] ml-auto px-1.5 py-0.5 rounded"
            style={{ color: statusConf.color, background: `${statusConf.color}15` }}>
            {statusConf.label}
          </span>
        )}
      </div>
      <p className="text-xs text-zinc-300 truncate pr-10">{mission.title}</p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-[9px] text-zinc-500">
          {new Date(mission.created_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })}
        </span>
        {mission.assigned_agents.length > 0 && (
          <span className="text-[9px] text-zinc-600">
            <Users size={8} className="inline mr-0.5" />
            {mission.assigned_agents.length}
          </span>
        )}
      </div>

      {/* 액션 버튼 — hover 시 표시 */}
      <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        {active && (
          <button
            onClick={onCancel}
            className="p-1 rounded hover:bg-red-500/20 text-zinc-600 hover:text-red-400 transition-colors"
            title="미션 중지"
          >
            <Square size={12} />
          </button>
        )}
        <button
          onClick={onDelete}
          className="p-1 rounded hover:bg-red-500/20 text-zinc-600 hover:text-red-400 transition-colors"
          title="미션 삭제"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
});

// 실시간 로그 라인 — 터미널 스타일
const LogLine = memo(function LogLine({ entry }: { entry: LogEntry }) {
  const color = getLogColor(entry.type);
  const prefix = getLogPrefix(entry.type);
  const time = new Date(entry.timestamp).toLocaleTimeString('ko-KR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  });

  return (
    <div className="flex items-start gap-0 text-[11px] leading-relaxed font-mono hover:bg-white/[0.02] px-3 py-0.5">
      <span className="text-zinc-600 flex-shrink-0 w-[60px]">{time}</span>
      <span className={`flex-shrink-0 w-[32px] font-bold ${color}`}>{prefix}</span>
      <span className="flex-shrink-0 mr-1">{entry.emoji}</span>
      <span className="text-zinc-500 flex-shrink-0 mr-1.5">{entry.agent}</span>
      <span className="text-zinc-300 break-words min-w-0">{entry.message}</span>
    </div>
  );
});

interface MissionConsoleProps {
  onMissionEvent?: (event: MissionSSEEvent) => void;
}

let _logIdCounter = 0;

export default function MissionConsole({ onMissionEvent }: MissionConsoleProps) {
  const pushAgentBubble = useAppStore(s => s.pushAgentBubble);
  const [input, setInput] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentMission, setCurrentMission] = useState<MissionData | null>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [responseText, setResponseText] = useState('');
  const [missionHistory, setMissionHistory] = useState<MissionData[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  // 승인 게이트
  const [pendingApproval, setPendingApproval] = useState<{
    agents: string[];
    subtasks_count: number;
    message: string;
  } | null>(null);
  const [approvalFeedback, setApprovalFeedback] = useState('');
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);

  const logEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string>(`web-${Date.now()}`);
  const autoScrollRef = useRef(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // 로그 추가 헬퍼
  const pushLog = useCallback((agent: string, message: string, type: LogEntry['type']) => {
    const p = getPersona(agent);
    const entry: LogEntry = {
      id: ++_logIdCounter,
      timestamp: new Date().toISOString(),
      agent: p ? getFirstName(agent) : agent.replace('JINXUS_', '').replace('JX_', ''),
      emoji: p?.emoji || '🤖',
      message,
      type,
    };
    setLogEntries(prev => {
      const next = [...prev, entry];
      // 최대 500줄
      return next.length > 500 ? next.slice(-500) : next;
    });
  }, []);

  // 미션 히스토리 로드
  useEffect(() => {
    missionApi.listMissions(undefined, 30).then(res => {
      setMissionHistory(res.missions);
    }).catch(() => {});
  }, []);

  // 로그 자동 스크롤 (스크롤이 바닥 근처일 때만)
  useEffect(() => {
    if (autoScrollRef.current) {
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logEntries, responseText]);

  // 스크롤 위치 감지 — 바닥에서 벗어나면 자동스크롤 비활성화
  const handleLogScroll = useCallback(() => {
    const el = logContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = atBottom;
  }, []);

  // 미션 실행
  const executeMission = useCallback(async () => {
    if (!input.trim() || isExecuting) return;

    const message = input.trim();
    setInput('');
    setIsExecuting(true);
    setResponseText('');
    setLogEntries([]);
    setCurrentMission(null);
    autoScrollRef.current = true;

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      await missionApi.streamMission(
        message,
        sessionIdRef.current,
        (event) => {
          onMissionEvent?.(event);

          switch (event.event) {
            case 'mission_created': {
              const data = event.data as unknown as MissionData;
              setCurrentMission(data);
              setSelectedMissionId(data.id);
              // 히스토리에 즉시 추가
              setMissionHistory(prev => [data, ...prev.filter(m => m.id !== data.id)]);
              const tc = MISSION_TYPE_CONFIG[data.type];
              pushLog('SYSTEM', `[${tc?.label || data.type}] ${data.title}`, 'status');
              break;
            }
            case 'mission_status': {
              const newStatus = (event.data.status as MissionData['status']);
              const newAgents = (event.data.agents as string[]);
              setCurrentMission(prev => prev ? {
                ...prev,
                status: newStatus || prev.status,
                assigned_agents: newAgents || prev.assigned_agents,
              } : prev);
              // 히스토리의 상태도 갱신
              if (newStatus) {
                setMissionHistory(prev => prev.map(m =>
                  m.id === (event.data.id as string) ? { ...m, status: newStatus } : m
                ));
              }
              break;
            }
            case 'mission_briefing_message':
            case 'agent_dm':
            case 'agent_report': {
              // 에이전트 활동이 시작되면 승인 완료된 것
              if (pendingApproval) setPendingApproval(null);
              const from = (event.data.from || '') as string;
              const msg = (event.data.message || '') as string;
              const type = event.event === 'mission_briefing_message' ? 'huddle'
                : event.event === 'agent_report' ? 'report' : 'dm';
              if (from && msg) {
                pushLog(from, msg, type);
                pushAgentBubble(from, msg);
              }
              break;
            }
            case 'mission_agent_activity': {
              const agent = event.data.agent as string;
              const action = event.data.action as string;
              if (agent) {
                setCurrentMission(prev => prev ? {
                  ...prev,
                  assigned_agents: prev.assigned_agents.includes(agent)
                    ? prev.assigned_agents
                    : [...prev.assigned_agents, agent],
                } : prev);
                if (action === 'working') {
                  pushLog(agent, '작업 시작', 'status');
                } else if (action === 'done') {
                  pushLog(agent, '작업 완료', 'status');
                }
              }
              break;
            }
            case 'mission_thinking': {
              const detail = event.data.detail as string;
              const step = event.data.step as string;
              const from = (event.data.from as string) || 'JINXUS_CORE';
              if (detail) {
                // agent_progress 중 도구 관련은 'dm' 스타일로, 나머지는 'thinking'
                const isToolRelated = /도구|tool|실행|호출|execute/i.test(detail);
                const logType = step === 'agent_progress' && isToolRelated ? 'dm' : 'thinking';
                pushLog(from, detail, logType);
              }
              break;
            }
            case 'mission_message': {
              const chunk = (event.data.chunk as string) || '';
              if (chunk) setResponseText(prev => prev + chunk);
              break;
            }
            case 'mission_complete': {
              const result = event.data as Record<string, unknown>;
              setCurrentMission(prev => prev ? {
                ...prev,
                status: 'complete',
                result: (result.result as string) || prev.result,
              } : prev);
              setPendingApproval(null);
              pushLog('SYSTEM', '미션 완료', 'status');
              // 히스토리 갱신
              missionApi.listMissions(undefined, 30).then(res => {
                setMissionHistory(res.missions);
              }).catch(() => {});
              break;
            }
            case 'mission_failed': {
              setCurrentMission(prev => prev ? {
                ...prev,
                status: 'failed',
                error: (event.data.error as string) || '미션 실패',
              } : prev);
              pushLog('SYSTEM', `실패: ${(event.data.error as string) || '알 수 없는 오류'}`, 'status');
              missionApi.listMissions(undefined, 30).then(res => {
                setMissionHistory(res.missions);
              }).catch(() => {});
              break;
            }
            case 'mission_cancelled': {
              setCurrentMission(prev => prev ? { ...prev, status: 'cancelled' } : prev);
              pushLog('SYSTEM', '미션 취소됨', 'status');
              break;
            }
            case 'mission_approval_required': {
              const agents = (event.data.agents as string[]) || [];
              const count = (event.data.subtasks_count as number) || 0;
              const msg = (event.data.message as string) || '승인 대기';
              setPendingApproval({ agents, subtasks_count: count, message: msg });
              pushLog('SYSTEM', `승인 대기: ${msg} (에이전트 ${count}명)`, 'status');
              break;
            }
            // start, log 등 시스템 내부 이벤트는 무시
            default:
              break;
          }
        },
        (error) => {
          console.error('[MissionConsole] SSE error:', error);
          setCurrentMission(prev => prev ? { ...prev, status: 'failed', error: error.message } : prev);
          pushLog('SYSTEM', `오류: ${error.message}`, 'status');
        },
        abort,
      );
    } finally {
      setIsExecuting(false);
      abortRef.current = null;
    }
  }, [input, isExecuting, onMissionEvent, pushLog, pushAgentBubble]);

  // 히스토리에서 미션 선택 — 대화 로그를 LogEntry로 변환
  const selectMission = useCallback(async (mission: MissionData) => {
    setSelectedMissionId(mission.id);
    setCurrentMission(mission);
    setResponseText(mission.result || '');
    autoScrollRef.current = true;

    try {
      const res = await missionApi.getConversations(mission.id);
      const convs = res.conversations || [];
      const entries: LogEntry[] = convs.map((c) => {
        const p = getPersona(c.from);
        return {
          id: ++_logIdCounter,
          timestamp: c.timestamp,
          agent: p ? getFirstName(c.from) : (c.from || '').replace('JINXUS_', '').replace('JX_', ''),
          emoji: p?.emoji || '🤖',
          message: c.message,
          type: (c.type || 'dm') as LogEntry['type'],
        };
      });
      setLogEntries(entries);
    } catch {
      setLogEntries([]);
    }
  }, []);

  // 미션 취소
  const cancelMission = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    if (currentMission) {
      missionApi.cancelMission(currentMission.id).catch(() => {});
    }
  }, [currentMission]);

  // 승인 게이트 응답
  const handleApproval = useCallback(async (status: 'approved' | 'modified' | 'cancelled') => {
    try {
      // 대기 중인 승인 요청 가져오기
      const { pending } = await channelApi.getPendingApprovals();
      if (pending.length === 0) return;
      const requestId = pending[0].id;
      const feedback = status === 'modified' ? approvalFeedback : '';
      await channelApi.approve(requestId, status, feedback);
      setPendingApproval(null);
      setShowFeedbackInput(false);
      setApprovalFeedback('');
      pushLog('SYSTEM', status === 'approved' ? '승인 완료 — 작업 진행' :
        status === 'modified' ? `수정 요청: ${feedback}` : '작업 취소', 'status');
    } catch (e) {
      console.error('[MissionConsole] 승인 처리 실패:', e);
    }
  }, [approvalFeedback, pushLog]);

  // 히스토리에서 개별 미션 취소
  const handleCancelMission = useCallback(async (e: React.MouseEvent, mission: MissionData) => {
    e.stopPropagation();
    try {
      await missionApi.cancelMission(mission.id);
      setMissionHistory(prev => prev.map(m =>
        m.id === mission.id ? { ...m, status: 'cancelled' as const } : m
      ));
      if (currentMission?.id === mission.id) {
        setCurrentMission(prev => prev ? { ...prev, status: 'cancelled' } : prev);
      }
    } catch { /* ignore */ }
  }, [currentMission]);

  // 히스토리에서 미션 삭제
  const handleDeleteMission = useCallback(async (e: React.MouseEvent, mission: MissionData) => {
    e.stopPropagation();
    try {
      await missionApi.deleteMission(mission.id);
      setMissionHistory(prev => prev.filter(m => m.id !== mission.id));
      if (selectedMissionId === mission.id) {
        setSelectedMissionId(null);
        setCurrentMission(null);
        setLogEntries([]);
        setResponseText('');
      }
    } catch { /* ignore */ }
  }, [selectedMissionId]);

  // Enter 키 처리
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      executeMission();
    }
  }, [executeMission]);

  const statusConf = currentMission ? STATUS_CONFIG[currentMission.status] : null;
  const typeConf = currentMission ? MISSION_TYPE_CONFIG[currentMission.type] : null;

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#0a0a0f]">
      {/* 미션 입력 */}
      <div className="flex-shrink-0 p-2 border-b border-zinc-800/50"
        style={{ background: 'linear-gradient(0deg, #0d0d14, transparent)' }}>
        <div className="flex gap-2">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex-shrink-0 p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
            title={showHistory ? '히스토리 숨기기' : '히스토리 보기'}
          >
            <ChevronDown size={16} className={`transition-transform ${showHistory ? 'rotate-90' : '-rotate-90'}`} />
          </button>
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="미션을 입력하세요... (Shift+Enter: 줄바꿈)"
              rows={1}
              disabled={isExecuting}
              className="w-full px-4 py-2 pr-12 rounded-xl bg-zinc-900/50 border border-zinc-700/50 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 resize-none disabled:opacity-50 transition-colors"
              style={{ minHeight: 36, maxHeight: 120 }}
            />
            {isExecuting ? (
              <button
                onClick={cancelMission}
                className="absolute right-2 top-1/2 -translate-y-1/2 z-10 p-2 rounded-lg bg-red-600/30 text-red-400 hover:bg-red-600/50 active:bg-red-600/60 transition-colors cursor-pointer border border-red-500/30"
                title="미션 취소"
              >
                <XCircle size={18} />
              </button>
            ) : (
              <button
                onClick={executeMission}
                disabled={!input.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-lg bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="미션 실행 (Enter)"
              >
                <Send size={16} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 하단: 히스토리 + 실시간 로그 */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* 좌측: 미션 히스토리 */}
        {showHistory && (
          <div className="w-56 flex-shrink-0 border-r border-zinc-800/50 flex flex-col"
            style={{ background: 'linear-gradient(180deg, #0d0d14, #0a0a0f)' }}>
            <div className="px-3 py-2 border-b border-zinc-800/50 flex items-center justify-between">
              <span className="text-[10px] font-bold text-zinc-400 tracking-wider">MISSIONS</span>
              <span className="text-[9px] text-zinc-600">{missionHistory.length}</span>
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5 custom-scrollbar">
              {missionHistory.map(m => (
                <MissionHistoryItem
                  key={m.id}
                  mission={m}
                  isSelected={selectedMissionId === m.id}
                  onClick={() => selectMission(m)}
                  onCancel={(e) => handleCancelMission(e, m)}
                  onDelete={(e) => handleDeleteMission(e, m)}
                />
              ))}
              {missionHistory.length === 0 && (
                <p className="text-xs text-zinc-600 text-center py-8">아직 미션이 없습니다</p>
              )}
            </div>
          </div>
        )}

        {/* 우측: 실시간 작업 로그 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 미션 헤더 — 선택된 미션 정보 */}
          {currentMission && (
            <div className="flex-shrink-0 px-3 py-1.5 border-b border-zinc-800/50 flex items-center gap-2"
              style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0.3), transparent)' }}>
              {typeConf && <typeConf.icon size={12} style={{ color: typeConf.color }} />}
              <span className="text-xs font-semibold text-zinc-300 truncate flex-1">{currentMission.title}</span>
              {statusConf && (
                <span className="text-[10px] px-2 py-0.5 rounded flex items-center gap-1"
                  style={{ color: statusConf.color, background: `${statusConf.color}20` }}>
                  {isActiveStatus(currentMission.status) && (
                    <Loader2 size={9} className="animate-spin" />
                  )}
                  {statusConf.label}
                </span>
              )}
              {currentMission.assigned_agents.length > 0 && (
                <div className="flex items-center gap-0.5 ml-1">
                  {currentMission.assigned_agents.slice(0, 6).map(a => {
                    const p = getPersona(a);
                    return (
                      <span key={a} className="text-xs" title={a}>{p?.emoji || '🤖'}</span>
                    );
                  })}
                  {currentMission.assigned_agents.length > 6 && (
                    <span className="text-[9px] text-zinc-500">+{currentMission.assigned_agents.length - 6}</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 로그 스트림 */}
          <div
            ref={logContainerRef}
            onScroll={handleLogScroll}
            className="flex-1 overflow-y-auto custom-scrollbar"
            style={{ background: '#07070b' }}
          >
            {/* 로그 엔트리들 */}
            {logEntries.length > 0 && (
              <div className="py-1">
                {logEntries.map(entry => (
                  <LogLine key={entry.id} entry={entry} />
                ))}
              </div>
            )}

            {/* 승인 대기 카드 */}
            {pendingApproval && (
              <div className="mx-3 my-2 p-3 rounded-lg border border-amber-500/30 bg-amber-500/5">
                <div className="flex items-center gap-2 mb-2">
                  <ShieldCheck size={14} className="text-amber-400" />
                  <span className="text-xs font-bold text-amber-300">승인 대기</span>
                  <span className="text-[10px] text-zinc-500 ml-auto">
                    에이전트 {pendingApproval.subtasks_count}명 대기 중
                  </span>
                </div>
                <p className="text-[11px] text-zinc-300 mb-2">{pendingApproval.message}</p>
                {pendingApproval.agents.length > 0 && (
                  <div className="flex gap-1 flex-wrap mb-2">
                    {pendingApproval.agents.map(a => {
                      const p = getPersona(a);
                      return (
                        <span key={a} className="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800/50 text-zinc-400">
                          {p?.emoji || '🤖'} {p ? getFirstName(a) : a}
                        </span>
                      );
                    })}
                  </div>
                )}
                {showFeedbackInput && (
                  <textarea
                    value={approvalFeedback}
                    onChange={(e) => setApprovalFeedback(e.target.value)}
                    placeholder="수정 피드백..."
                    rows={2}
                    className="w-full mb-2 px-2 py-1.5 rounded bg-zinc-900/50 border border-zinc-700/50 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-amber-500/50 resize-none"
                  />
                )}
                <div className="flex gap-1.5">
                  <button
                    onClick={() => handleApproval('approved')}
                    className="flex items-center gap-1 px-3 py-1.5 rounded bg-green-600/20 border border-green-500/30 text-green-400 text-[11px] font-medium hover:bg-green-600/30 transition-colors"
                  >
                    <CheckCircle2 size={12} /> 승인
                  </button>
                  <button
                    onClick={() => {
                      if (showFeedbackInput && approvalFeedback.trim()) {
                        handleApproval('modified');
                      } else {
                        setShowFeedbackInput(true);
                      }
                    }}
                    className="flex items-center gap-1 px-3 py-1.5 rounded bg-amber-600/20 border border-amber-500/30 text-amber-400 text-[11px] font-medium hover:bg-amber-600/30 transition-colors"
                  >
                    <Pencil size={12} /> 수정
                  </button>
                  <button
                    onClick={() => handleApproval('cancelled')}
                    className="flex items-center gap-1 px-3 py-1.5 rounded bg-red-600/20 border border-red-500/30 text-red-400 text-[11px] font-medium hover:bg-red-600/30 transition-colors"
                  >
                    <Ban size={12} /> 취소
                  </button>
                </div>
              </div>
            )}

            {/* 응답 결과 */}
            {responseText && (
              <div className="px-3 py-2 border-t border-zinc-800/30">
                <div className="flex items-center gap-1.5 mb-1.5">
                  {currentMission?.status === 'complete' ? (
                    <CheckCircle2 size={11} className="text-green-500" />
                  ) : currentMission?.status === 'failed' ? (
                    <XCircle size={11} className="text-red-500" />
                  ) : (
                    <Target size={11} className="text-blue-400" />
                  )}
                  <span className="text-[10px] font-bold text-zinc-400 tracking-wider">
                    {currentMission?.status === 'complete' ? 'RESULT' :
                     currentMission?.status === 'failed' ? 'FAILED' : 'OUTPUT'}
                  </span>
                </div>
                <div className="prose prose-invert prose-sm max-w-none text-[12px] leading-relaxed">
                  <MarkdownRenderer content={responseText} />
                </div>
              </div>
            )}

            {/* 에러 */}
            {currentMission?.error && !responseText && (
              <div className="mx-3 my-2 p-2 rounded bg-red-950/20 border border-red-900/30">
                <p className="text-[11px] text-red-400 font-mono">{currentMission.error}</p>
              </div>
            )}

            {/* 빈 상태 */}
            {!currentMission && !isExecuting && logEntries.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full text-center opacity-40">
                <Activity size={24} className="text-zinc-600 mb-2" />
                <p className="text-[11px] text-zinc-600">미션을 실행하면 작업 로그가 여기에 표시됩니다</p>
              </div>
            )}

            {/* 실행 중 스피너 (로그가 아직 없을 때) */}
            {isExecuting && logEntries.length === 0 && (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={18} className="text-blue-400 animate-spin" />
              </div>
            )}

            <div ref={logEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
