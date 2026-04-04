'use client';

import { useState, useRef, useEffect, useCallback, memo } from 'react';
import { missionApi, channelApi, type MissionData, type MissionSSEEvent, type AgentRuntimeStatus } from '@/lib/api';
import { getFirstName, getPersona } from '@/lib/personas';
import { useAppStore } from '@/store/useAppStore';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import { createSmoothStreamer } from '@/lib/smooth-streaming';
import {
  Send, Loader2, Target, CheckCircle2, XCircle,
  Users, ChevronDown, Zap, Swords, Crown,
  Trash2, Square, Activity, ShieldCheck, Ban, Pencil,
  Menu, X,
} from 'lucide-react';

// 미션 타입별 아이콘/색상
const MISSION_TYPE_CONFIG: Record<string, { icon: typeof Zap; color: string; label: string; bg: string }> = {
  quick: { icon: Zap, color: '#22c55e', label: 'QUICK', bg: 'rgba(34,197,94,0.1)' },
  standard: { icon: Target, color: '#3b82f6', label: 'STANDARD', bg: 'rgba(59,130,246,0.1)' },
  epic: { icon: Swords, color: '#f59e0b', label: 'EPIC', bg: 'rgba(245,158,11,0.1)' },
  raid: { icon: Crown, color: '#ef4444', label: 'RAID', bg: 'rgba(239,68,68,0.1)' },
};

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  briefing: { color: '#f59e0b', label: '작업중' },
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
      className={`group relative w-full text-left px-3 py-2.5 sm:py-2 rounded-lg border transition-all cursor-pointer active:bg-white/[0.06] ${
        isSelected
          ? 'bg-white/[0.05] border-zinc-600'
          : 'bg-transparent border-transparent hover:bg-white/[0.03] hover:border-zinc-700/50'
      }`}
      style={{ minHeight: 44 }}
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
      <p className="text-xs text-zinc-300 pr-10 truncate">{mission.title}</p>
      {/* 원본 질문 — 제목과 다를 때만 표시 */}
      {mission.original_input && mission.original_input !== mission.title && (
        <p className="text-[10px] text-zinc-500 pr-10 truncate mt-0.5 italic">
          &quot;{mission.original_input.length > 80
            ? mission.original_input.slice(0, 80) + '…'
            : mission.original_input}&quot;
        </p>
      )}
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

      {/* 액션 버튼 — 데스크톱: hover 시 표시, 모바일: 항상 표시 */}
      <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex gap-0.5 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
        {active && (
          <button
            onClick={onCancel}
            className="p-2 sm:p-1 rounded hover:bg-red-500/20 active:bg-red-500/30 text-zinc-600 hover:text-red-400 transition-colors"
            title="업무 중지"
          >
            <Square size={14} className="sm:w-3 sm:h-3" />
          </button>
        )}
        <button
          onClick={onDelete}
          className="p-2 sm:p-1 rounded hover:bg-red-500/20 active:bg-red-500/30 text-zinc-600 hover:text-red-400 transition-colors"
          title="업무 삭제"
        >
          <Trash2 size={14} className="sm:w-3 sm:h-3" />
        </button>
      </div>
    </div>
  );
});

// 타임라인 노드 색상 (Geny ExecutionTimeline 패턴)
function getTimelineColor(type: LogEntry['type']): string {
  switch (type) {
    case 'dm': return '#3b82f6';       // 파랑
    case 'huddle': return '#f59e0b';   // 주황
    case 'report': return '#22c55e';   // 초록
    case 'broadcast': return '#8b5cf6'; // 보라
    case 'thinking': return '#52525b'; // 회색
    case 'status': return '#06b6d4';   // 시안
    case 'result': return '#10b981';   // 에메랄드
    default: return '#71717a';
  }
}

// 파일 변경 배지 (Geny FileChangeSummary 패턴)
function FileChangeBadge({ message }: { message: string }) {
  const match = message.match(/📝 파일 (\d+)개 변경: (.+)/);
  if (!match) return null;
  const files = match[2].split(', ').slice(0, 3);
  return (
    <span className="inline-flex items-center gap-1 ml-1.5">
      {files.map((f, i) => {
        const nameMatch = f.match(/(.+)\((.+)\)/);
        if (!nameMatch) return null;
        return (
          <span key={i} className="inline-flex items-center gap-0.5 px-1.5 py-0 rounded text-[9px] font-mono bg-zinc-800 border border-zinc-700/50">
            <span className="text-zinc-400">{nameMatch[1]}</span>
            <span className={nameMatch[2] === 'create' ? 'text-green-400' : nameMatch[2] === 'delete' ? 'text-red-400' : 'text-amber-400'}>
              {nameMatch[2]}
            </span>
          </span>
        );
      })}
    </span>
  );
}

// 실시간 로그 라인 — 타임라인 스타일 (Geny ExecutionTimeline 패턴)
const LogLine = memo(function LogLine({ entry, isLast }: { entry: LogEntry; isLast?: boolean }) {
  const nodeColor = getTimelineColor(entry.type);
  const color = getLogColor(entry.type);
  const prefix = getLogPrefix(entry.type);
  const time = new Date(entry.timestamp).toLocaleTimeString('ko-KR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  });
  const isThinking = entry.type === 'thinking';
  const isFileChange = entry.message.startsWith('📝 파일');
  const isToolUse = entry.message.startsWith('📦 도구');

  return (
    <div className={`flex items-start gap-0 text-[11px] leading-relaxed hover:bg-white/[0.02] active:bg-white/[0.04] pl-1 pr-2 sm:pl-2 sm:pr-3 py-1 sm:py-0.5 ${isThinking ? 'opacity-60' : ''}`}>
      {/* 타임라인 노드 + 수직선 */}
      <div className="flex-shrink-0 w-4 sm:w-5 flex flex-col items-center mr-1 sm:mr-1.5 mt-[5px]">
        <div
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{
            background: nodeColor,
            boxShadow: isLast ? `0 0 6px ${nodeColor}80` : 'none',
          }}
        />
        {!isLast && <div className="w-px flex-1 min-h-[8px] bg-zinc-800" />}
      </div>
      {/* 시간 (24h) */}
      <span className="text-zinc-600 flex-shrink-0 w-[46px] sm:w-[50px] whitespace-nowrap font-mono text-[10px]">{time}</span>
      {/* 타입 배지 */}
      <span
        className="flex-shrink-0 w-[28px] sm:w-[30px] text-center font-bold whitespace-nowrap text-[9px] rounded px-0.5 py-[1px] mr-1.5"
        style={{ color: nodeColor, background: `${nodeColor}15` }}
      >
        {prefix}
      </span>
      {/* 에이전트 */}
      <span className="flex-shrink-0 whitespace-nowrap">{entry.emoji}</span>
      <span className="text-zinc-500 flex-shrink-0 mr-1.5 whitespace-nowrap font-medium">{entry.agent}</span>
      {/* 메시지 */}
      <span className={`text-zinc-300 min-w-0 ${isThinking ? 'whitespace-nowrap text-ellipsis overflow-hidden' : 'whitespace-pre-wrap break-words'}`}>
        {isFileChange ? (
          <>{entry.message.split(':')[0]}:<FileChangeBadge message={entry.message} /></>
        ) : isToolUse ? (
          <span className="text-cyan-400/80">{entry.message}</span>
        ) : (
          entry.message
        )}
      </span>
    </div>
  );
});

interface MissionConsoleProps {
  onMissionEvent?: (event: MissionSSEEvent) => void;
  runtimeMap?: Record<string, AgentRuntimeStatus>;
}

let _logIdCounter = 0;

export default function MissionConsole({ onMissionEvent, runtimeMap = {} }: MissionConsoleProps) {
  const pushAgentBubble = useAppStore(s => s.pushAgentBubble);
  const [input, setInput] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentMission, setCurrentMission] = useState<MissionData | null>(null);
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [responseText, setResponseText] = useState('');
  const [missionHistory, setMissionHistory] = useState<MissionData[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  // 모바일 드로어 (sm 이하에서 히스토리 표시)
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  // 모바일 키보드 높이 보정
  const [keyboardOffset, setKeyboardOffset] = useState(0);
  // 승인 게이트
  const [pendingApproval, setPendingApproval] = useState<{
    agents: string[];
    subtasks_count: number;
    message: string;
  } | null>(null);
  const [approvalFeedback, setApprovalFeedback] = useState('');
  const [showFeedbackInput, setShowFeedbackInput] = useState(false);
  // 실행 단계 추적
  const [executionPhase, setExecutionPhase] = useState<string>('');
  const [pendingTitle, setPendingTitle] = useState<string>('');
  const [titleExpanded, setTitleExpanded] = useState(false);

  const logEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const sessionIdRef = useRef<string>(`web-${Date.now()}`);
  const autoScrollRef = useRef(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const streamerRef = useRef(createSmoothStreamer((text) => setResponseText(text)));

  // visualViewport API — 키보드 올라올 때 레이아웃 조정
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const handleResize = () => {
      const offset = window.innerHeight - vv.height;
      setKeyboardOffset(offset > 50 ? offset : 0);
    };
    vv.addEventListener('resize', handleResize);
    return () => vv.removeEventListener('resize', handleResize);
  }, []);

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

  // 로그 자동 스크롤 — rAF 배치로 jank 방지
  const logScrollRafRef = useRef<number | null>(null);
  useEffect(() => {
    if (!autoScrollRef.current) return;
    if (logScrollRafRef.current) return;
    logScrollRafRef.current = requestAnimationFrame(() => {
      logScrollRafRef.current = null;
      const el = logContainerRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    });
  }, [logEntries, responseText]);

  // 스크롤 위치 감지 — 바닥에서 벗어나면 자동스크롤 비활성화
  const handleLogScroll = useCallback(() => {
    const el = logContainerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    autoScrollRef.current = atBottom;
  }, []);

  // 미션 실행
  const executeMission = useCallback(async (directMessage?: string) => {
    const message = (directMessage || input).trim();
    if (!message) return;

    // 이전 SSE 연결이 열려있으면 취소
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }

    const isFollowup = message.startsWith('[후속]');

    setInput('');
    setIsExecuting(true);

    if (isFollowup) {
      // 후속 지시: 기존 로그/결과 유지, 아래에 이어붙이기
      setExecutionPhase('후속 지시 처리 중...');
      setResponseText(prev => prev ? prev + '\n\n---\n\n' : '');
      // 후속 시 streamer를 현재 텍스트 기준으로 재생성
      streamerRef.current.flush();
      streamerRef.current = createSmoothStreamer((text) => setResponseText(text));
      pushLog('SYSTEM', '─── 후속 지시 ───', 'status');
    } else {
      // 새 미션: 전부 초기화
      setResponseText('');
      streamerRef.current.reset();
      streamerRef.current = createSmoothStreamer((text) => setResponseText(text));
      setLogEntries([]);
      setCurrentMission(null);
      setTitleExpanded(false);
      setExecutionPhase('난이도 분류 중...');
    }

    // pendingTitle: 후속은 유저 입력만, 새 미션은 전체 메시지
    const displayTitle = isFollowup
      ? message.replace(/^\[후속\]\s*/, '').split('\n')[0]
      : message;
    setPendingTitle(displayTitle);
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
              setExecutionPhase('에이전트 배정 중...');
              setPendingTitle('');
              // 히스토리에 즉시 추가
              setMissionHistory(prev => [data, ...prev.filter(m => m.id !== data.id)]);
              const tc = MISSION_TYPE_CONFIG[data.type];
              pushLog('SYSTEM', `[${tc?.label || data.type}] ${data.title}`, 'status');
              break;
            }
            case 'mission_status': {
              const newStatus = (event.data.status as MissionData['status']);
              const newAgents = (event.data.agents as string[]);
              if (newStatus === 'briefing') setExecutionPhase('작업 중...');
              else if (newStatus === 'in_progress') setExecutionPhase('작업 수행 중');
              else if (newStatus === 'review') setExecutionPhase('리뷰 중...');
              else if (newStatus === 'complete' || newStatus === 'failed') setExecutionPhase('');
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
              // v4: agent_report에 도구/파일 변경 정보 포함
              if (event.event === 'agent_report') {
                const toolCalls = event.data.tool_calls as Array<{name: string}> | undefined;
                const fileChanges = event.data.file_changes as Array<{file: string; op: string}> | undefined;
                if (toolCalls?.length) {
                  pushLog(from, `📦 도구 ${toolCalls.length}개: ${toolCalls.map(t => t.name).join(', ')}`, 'thinking');
                }
                if (fileChanges?.length) {
                  pushLog(from, `📝 파일 ${fileChanges.length}개 변경: ${fileChanges.map(f => `${f.file}(${f.op})`).join(', ')}`, 'thinking');
                }
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
                // v4 CLI 엔진: 도구 사용 프리뷰 (🔧로 시작하거나 ✓로 시작)
                const isToolLog = detail.startsWith('🔧') || detail.startsWith('✓');
                const logType = isToolLog ? 'dm' : (step === 'agent_progress' ? 'thinking' : 'thinking');
                pushLog(from, detail, logType);
                // 도구 로그면 Pixel Office 말풍선에도 표시
                if (isToolLog) {
                  pushAgentBubble(from, detail);
                }
              }
              break;
            }
            case 'mission_tool_calls': {
              const agent = event.data.agent as string;
              const tools = event.data.tools as Array<{name: string; input?: Record<string, unknown>}>;
              if (agent && tools?.length) {
                pushLog(agent, `도구 ${tools.length}개 사용: ${tools.map(t => t.name).join(', ')}`, 'dm');
              }
              break;
            }
            case 'huddle_message': {
              // 오케스트레이터 작업 분해/계획 메시지
              const from = (event.data.from || 'JINXUS_CORE') as string;
              const msg = (event.data.message || '') as string;
              if (msg) pushLog(from, msg, 'huddle');
              break;
            }
            case 'mission_message': {
              const chunk = (event.data.chunk as string) || '';
              if (chunk) streamerRef.current.push(chunk);
              break;
            }
            case 'mission_complete': {
              streamerRef.current.flush();
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
              streamerRef.current.flush();
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
              streamerRef.current.flush();
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
          const isNetworkErr = error.message === 'Failed to fetch' || error.message.toLowerCase().includes('network');
          const userMsg = isNetworkErr
            ? '서버 연결 실패 — 서버가 재시작 중일 수 있습니다. 잠시 후 다시 시도해주세요.'
            : error.message;
          setCurrentMission(prev => prev ? { ...prev, status: 'failed', error: userMsg } : prev);
          pushLog('SYSTEM', `오류: ${userMsg}`, 'status');
        },
        abort,
      );
    } finally {
      setIsExecuting(false);
      setExecutionPhase('');
      setPendingTitle('');
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
    <div className="flex flex-col h-full min-h-0 bg-[#0a0a0f] relative">
      {/* 미션 입력 — 모바일: 하단 고정 (sticky), 데스크톱: 상단 */}
      <div
        className="flex-shrink-0 p-2 pt-3 sm:pt-6 border-b sm:border-b border-t sm:border-t-0 border-zinc-800/50 order-first sm:order-first mobile-safe-bottom"
        style={{
          background: 'linear-gradient(0deg, #0d0d14, transparent)',
          ...(keyboardOffset > 0 ? { paddingBottom: keyboardOffset } : {}),
        }}
      >
        <div className="flex gap-2">
          {/* 모바일: 히스토리 드로어 토글 버튼 */}
          <button
            onClick={() => {
              // 모바일에서는 드로어 토글, 데스크톱에서는 히스토리 토글
              if (window.innerWidth < 640) {
                setMobileDrawerOpen(o => !o);
              } else {
                setShowHistory(!showHistory);
              }
            }}
            className="flex-shrink-0 p-2.5 sm:p-2 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 active:bg-zinc-700/50 transition-colors"
            title={showHistory ? '히스토리 숨기기' : '히스토리 보기'}
            style={{ minWidth: 44, minHeight: 44 }}
          >
            <Menu size={18} className="sm:hidden" />
            <ChevronDown size={16} className={`hidden sm:block transition-transform ${showHistory ? 'rotate-90' : '-rotate-90'}`} />
          </button>
          <div className="flex-1 relative">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="업무를 입력하세요..."
              rows={1}
              className="w-full px-4 py-2.5 sm:py-2 pr-14 sm:pr-12 rounded-xl bg-zinc-900/50 border border-zinc-700/50 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-500 resize-none transition-colors"
              style={{ minHeight: 44, maxHeight: 120 }}
            />
            {isExecuting ? (
              <div className="absolute right-2 top-1/2 -translate-y-1/2 z-10 flex items-center gap-2">
                {executionPhase && (
                  <span className="flex items-center gap-1.5 text-[10px] text-blue-400/80 font-mono">
                    <Loader2 size={11} className="animate-spin" />
                    {executionPhase}
                  </span>
                )}
                <button
                  onClick={cancelMission}
                  className="p-2 sm:p-1.5 rounded-lg text-zinc-500 hover:text-red-400 active:text-red-500 transition-colors cursor-pointer"
                  title="업무 취소"
                  style={{ minWidth: 44, minHeight: 44 }}
                >
                  <XCircle size={18} className="sm:w-4 sm:h-4" />
                </button>
              </div>
            ) : (
              <button
                data-mission-execute
                onClick={() => executeMission()}
                disabled={!input.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 sm:p-1.5 rounded-lg bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 active:bg-blue-600/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                title="업무 실행 (Enter)"
                style={{ minWidth: 44, minHeight: 44 }}
              >
                <Send size={18} className="sm:w-4 sm:h-4" />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* 모바일 히스토리 드로어 오버레이 */}
      {mobileDrawerOpen && (
        <div
          className="sm:hidden fixed inset-0 z-40 bg-black/60 drawer-overlay"
          onClick={() => setMobileDrawerOpen(false)}
        />
      )}

      {/* 모바일 히스토리 드로어 */}
      <div className={`sm:hidden fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] flex flex-col transition-transform duration-250 ease-out ${
        mobileDrawerOpen ? 'translate-x-0' : '-translate-x-full'
      }`} style={{ background: 'linear-gradient(180deg, #0d0d14, #0a0a0f)' }}>
        <div className="px-3 py-3 border-b border-zinc-800/50 flex items-center justify-between">
          <span className="text-xs font-bold text-zinc-400 tracking-wider">업무 내역</span>
          <button
            onClick={() => setMobileDrawerOpen(false)}
            className="p-2 rounded-lg text-zinc-500 hover:text-zinc-300 active:bg-zinc-700/50 transition-colors"
            style={{ minWidth: 44, minHeight: 44 }}
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-0.5 mobile-scroll">
          {missionHistory.map(m => (
            <MissionHistoryItem
              key={m.id}
              mission={m}
              isSelected={selectedMissionId === m.id}
              onClick={() => {
                selectMission(m);
                setMobileDrawerOpen(false);
              }}
              onCancel={(e) => handleCancelMission(e, m)}
              onDelete={(e) => handleDeleteMission(e, m)}
            />
          ))}
          {missionHistory.length === 0 && (
            <p className="text-xs text-zinc-600 text-center py-8">아직 업무가 없습니다</p>
          )}
        </div>
      </div>

      {/* 하단: 히스토리 + 실시간 로그 */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* 좌측: 미션 히스토리 (데스크톱만) */}
        {showHistory && (
          <div className="hidden sm:flex w-56 flex-shrink-0 border-r border-zinc-800/50 flex-col"
            style={{ background: 'linear-gradient(180deg, #0d0d14, #0a0a0f)' }}>
            <div className="px-3 py-2 border-b border-zinc-800/50 flex items-center justify-between">
              <span className="text-[10px] font-bold text-zinc-400 tracking-wider">업무 내역</span>
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
                <p className="text-xs text-zinc-600 text-center py-8">아직 업무가 없습니다</p>
              )}
            </div>
          </div>
        )}

        {/* 우측: 실시간 작업 로그 */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* 미션 헤더 — 선택된 미션 정보 또는 대기 중 표시 */}
          {(currentMission || (isExecuting && pendingTitle)) && (
            <div className="flex-shrink-0 px-3 py-1.5 border-b border-zinc-800/50 flex items-start gap-2 cursor-pointer"
              style={{ background: 'linear-gradient(90deg, rgba(0,0,0,0.3), transparent)' }}
              onClick={() => setTitleExpanded(e => !e)}>
              {currentMission ? (
                <>
                  {typeConf && <typeConf.icon size={12} style={{ color: typeConf.color }} className="mt-0.5 flex-shrink-0" />}
                  <span className="text-xs font-semibold text-zinc-300 flex-1 whitespace-pre-wrap break-words">{currentMission.title}</span>
                  {statusConf && (
                    <span className="text-[10px] px-2 py-0.5 rounded flex items-center gap-1"
                      style={{ color: statusConf.color, background: `${statusConf.color}20` }}>
                      {isActiveStatus(currentMission.status) && (
                        <Loader2 size={9} className="animate-spin" />
                      )}
                      {statusConf.label}
                    </span>
                  )}
                  {(() => {
                    const workingAgents = currentMission.assigned_agents
                      .filter(a => a !== 'JINXUS_CORE' && runtimeMap[a]?.status === 'working');
                    return workingAgents.length > 0 && (
                      <div className="flex items-center gap-1 ml-1">
                        {workingAgents.slice(0, 6).map(a => {
                          const p = getPersona(a);
                          const rt = runtimeMap[a];
                          return (
                            <span key={a}
                              className="text-[9px] px-1.5 py-0.5 rounded flex items-center gap-1 bg-blue-500/15 text-blue-300"
                              title={rt?.current_task || a}
                            >
                              {p?.emoji || '🤖'}
                              <span className="hidden sm:inline">{p ? getFirstName(a) : a.replace('JX_', '')}</span>
                              <Loader2 size={8} className="animate-spin" />
                            </span>
                          );
                        })}
                      </div>
                    );
                  })()}
                </>
              ) : (
                <>
                  <span className="text-[10px] px-2 py-0.5 rounded flex items-center gap-1 text-blue-400/80 bg-blue-500/10">
                    <Loader2 size={9} className="animate-spin" />
                    난이도 분류 중
                  </span>
                  <span className="text-xs text-zinc-500 flex-1 whitespace-pre-wrap break-words">{pendingTitle}</span>
                </>
              )}
            </div>
          )}

          {/* 로그 스트림 */}
          <div
            ref={logContainerRef}
            onScroll={handleLogScroll}
            className="flex-1 overflow-y-auto overflow-x-auto custom-scrollbar"
            style={{ background: '#07070b' }}
          >
            {/* 로그 엔트리들 */}
            {logEntries.length > 0 && (
              <div className="py-1">
                {logEntries.map((entry, idx) => (
                  <LogLine key={entry.id} entry={entry} isLast={idx === logEntries.length - 1} />
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
                <div className="flex gap-1.5 sm:gap-1.5 flex-wrap">
                  <button
                    onClick={() => handleApproval('approved')}
                    className="flex items-center gap-1 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded bg-green-600/20 border border-green-500/30 text-green-400 text-xs sm:text-[11px] font-medium hover:bg-green-600/30 active:bg-green-600/40 transition-colors"
                    style={{ minHeight: 44 }}
                  >
                    <CheckCircle2 size={14} className="sm:w-3 sm:h-3" /> 승인
                  </button>
                  <button
                    onClick={() => {
                      if (showFeedbackInput && approvalFeedback.trim()) {
                        handleApproval('modified');
                      } else {
                        setShowFeedbackInput(true);
                      }
                    }}
                    className="flex items-center gap-1 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded bg-amber-600/20 border border-amber-500/30 text-amber-400 text-xs sm:text-[11px] font-medium hover:bg-amber-600/30 active:bg-amber-600/40 transition-colors"
                    style={{ minHeight: 44 }}
                  >
                    <Pencil size={14} className="sm:w-3 sm:h-3" /> 수정
                  </button>
                  <button
                    onClick={() => handleApproval('cancelled')}
                    className="flex items-center gap-1 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded bg-red-600/20 border border-red-500/30 text-red-400 text-xs sm:text-[11px] font-medium hover:bg-red-600/30 active:bg-red-600/40 transition-colors"
                    style={{ minHeight: 44 }}
                  >
                    <Ban size={14} className="sm:w-3 sm:h-3" /> 취소
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

            {/* 후속 지시 입력 — 미션 완료 후 이어서 대화 가능 */}
            {currentMission?.status === 'complete' && responseText && !isExecuting && (
              <div className="px-3 pt-3 pb-5 mb-2 border-t border-zinc-700/50">
                <form onSubmit={(e) => {
                  e.preventDefault();
                  const followupInput = (e.currentTarget.elements.namedItem('followup') as HTMLInputElement);
                  const val = followupInput?.value?.trim();
                  if (!val) return;
                  // 원본 미션 제목 추출 (중첩 방지: "이전 미션 X 결과 참고하여:" 접두어 제거)
                  let origTitle = currentMission.title;
                  const prefixMatch = origTitle.match(/^이전 미션 ["'](.+?)["'] 결과 참고하여/);
                  if (prefixMatch) origTitle = prefixMatch[1];
                  const followupText = `[후속] ${val}\n(참고: 이전 미션 "${origTitle}")`;
                  followupInput.value = '';
                  executeMission(followupText);
                }} className="flex gap-2">
                  <input
                    name="followup"
                    type="text"
                    placeholder="후속 지시..."
                    className="flex-1 bg-zinc-800/50 border border-zinc-700/50 rounded px-3 sm:px-2 py-2.5 sm:py-1.5 text-xs sm:text-[11px] text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-primary/50"
                    style={{ minHeight: 44 }}
                  />
                  <button
                    type="submit"
                    className="px-4 sm:px-3 py-2.5 sm:py-1.5 bg-primary/20 text-primary text-xs sm:text-[10px] font-bold rounded border border-primary/30 hover:bg-primary/30 active:bg-primary/40 transition-colors"
                    style={{ minHeight: 44 }}
                  >
                    이어서 지시
                  </button>
                </form>
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
                <p className="text-[11px] text-zinc-600">업무를 실행하면 작업 로그가 여기에 표시됩니다</p>
              </div>
            )}

            {/* 실행 중 상태 (로그가 아직 없을 때) */}
            {isExecuting && logEntries.length === 0 && (
              <div className="flex flex-col items-center justify-center py-12 gap-3">
                <Loader2 size={20} className="text-blue-400 animate-spin" />
                <span className="text-[11px] text-blue-400/80 font-mono">{executionPhase || '난이도 분류 중...'}</span>
              </div>
            )}

            <div ref={logEndRef} />
          </div>
        </div>
      </div>
    </div>
  );
}
