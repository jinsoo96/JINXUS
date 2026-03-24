'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { agentApi, type AgentRuntimeStatus, type MissionSSEEvent } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import PixelOffice, { type ActivityLogEntry } from '@/components/playground/PixelOffice';
import MissionConsole from '@/components/MissionConsole';
import { MessageSquare, Coffee, Briefcase, MapPin, VolumeX, Volume2, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { getFirstName, getPersona } from '@/lib/personas';

interface MissionTabProps {
  isActive?: boolean;
}

const CONSOLE_MIN_H = 56;
const CONSOLE_MAX_H = 600;
const CONSOLE_DEFAULT_H = CONSOLE_MIN_H;
const MAX_FEED_ENTRIES = 80;

// 피드 아이콘
function FeedIcon({ type }: { type: ActivityLogEntry['type'] }) {
  switch (type) {
    case 'chat': return <MessageSquare size={10} className="text-blue-400 flex-shrink-0" />;
    case 'move': return <MapPin size={10} className="text-amber-400 flex-shrink-0" />;
    case 'work': return <Briefcase size={10} className="text-green-400 flex-shrink-0" />;
    case 'arrive': return <Coffee size={10} className="text-purple-400 flex-shrink-0" />;
    default: return null;
  }
}

export default function MissionTab({ isActive = true }: MissionTabProps) {
  const { hrAgents, personasVersion } = useAppStore();
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});
  const [activityFeed, setActivityFeed] = useState<ActivityLogEntry[]>([]);
  const [consoleHeight, setConsoleHeight] = useState<number>(() => {
    try {
      const saved = typeof window !== 'undefined' ? localStorage.getItem('mission-console-height') : null;
      return saved ? Number(saved) : CONSOLE_DEFAULT_H;
    } catch { return CONSOLE_DEFAULT_H; }
  });

  const { muteChat, setMuteChat } = useAppStore();
  const [feedOpen, setFeedOpen] = useState(true);
  const missionEventRef = useRef<MissionSSEEvent | null>(null);
  const feedEndRef = useRef<HTMLDivElement>(null);

  const hiredSet = useMemo(() => {
    const set = new Set<string>();
    hrAgents.forEach(a => { if (a.is_active) set.add(a.name); });
    return set;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hrAgents, personasVersion]);

  useEffect(() => {
    if (!isActive) return;
    const poll = async () => {
      try {
        const res = await agentApi.getAllRuntimeStatus();
        const map: Record<string, AgentRuntimeStatus> = {};
        res.agents.forEach((s: AgentRuntimeStatus) => { map[s.name] = s; });
        setRuntimeMap(map);
      } catch { /* ignore */ }
    };
    poll();
    const id = setInterval(poll, POLLING_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isActive]);

  const handleSelectAgent = useCallback((_code: string) => {}, []);

  const handleMissionEvent = useCallback((event: MissionSSEEvent) => {
    missionEventRef.current = event;
    const d = event.data as Record<string, unknown>;

    // 미션 이벤트 → runtimeMap 즉시 반영 (폴링 안 기다림)
    if (event.event === 'mission_agent_activity') {
      const agent = d.agent as string;
      const action = d.action as string;
      if (agent) {
        setRuntimeMap(prev => ({
          ...prev,
          [agent]: {
            ...prev[agent],
            name: agent,
            status: action === 'done' ? 'idle' : 'working',
            current_task: (d.instruction as string) || prev[agent]?.current_task || '',
          } as AgentRuntimeStatus,
        }));
      }
    }

    // 미션 이벤트 → OFFICE FEED에 표시
    const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    if (event.event === 'agent_dm') {
      const from = (d.from as string) || '';
      const to = (d.to as string) || '';
      const msg = (d.message as string) || '';
      if (from && msg) {
        const pA = getPersona(from), pB = to ? getPersona(to) : null;
        setActivityFeed(prev => [...prev, {
          id: Date.now(), time: now, type: 'work' as const,
          agentA: pA ? getFirstName(from) : from,
          emojiA: pA?.emoji || '🤖',
          agentB: pB ? getFirstName(to) : to || undefined,
          emojiB: pB?.emoji || undefined,
          message: msg.length > 50 ? msg.slice(0, 48) + '..' : msg,
        }].slice(-MAX_FEED_ENTRIES));
      }
    } else if (event.event === 'agent_report') {
      const from = (d.from as string) || '';
      const msg = (d.message as string) || '';
      if (from && msg) {
        const p = getPersona(from);
        setActivityFeed(prev => [...prev, {
          id: Date.now(), time: now, type: 'work' as const,
          agentA: p ? getFirstName(from) : from,
          emojiA: p?.emoji || '🤖',
          message: `보고: ${msg.length > 40 ? msg.slice(0, 38) + '..' : msg}`,
        }].slice(-MAX_FEED_ENTRIES));
      }
    } else if (event.event === 'mission_agent_activity') {
      const agent = (d.agent as string) || '';
      const action = (d.action as string) || '';
      if (agent) {
        const p = getPersona(agent);
        const label = action === 'working' ? '작업 시작' : action === 'done' ? '작업 완료' : action;
        setActivityFeed(prev => [...prev, {
          id: Date.now(), time: now, type: 'work' as const,
          agentA: p ? getFirstName(agent) : agent,
          emojiA: p?.emoji || '🤖',
          message: label,
        }].slice(-MAX_FEED_ENTRIES));
      }
    } else if (event.event === 'mission_thinking') {
      const step = (d.step as string) || '';
      const detail = (d.detail as string) || '';
      const from = (d.from as string) || 'JINXUS_CORE';
      // 도구 호출 관련만 피드에 표시
      if (step === 'agent_progress' && /🔧|✅|❌|도구|tool/i.test(detail)) {
        const p = getPersona(from);
        // [에이전트명] 접두사 제거
        const cleanMsg = detail.replace(/^\[[\w_]+\]\s*/, '');
        setActivityFeed(prev => [...prev, {
          id: Date.now(), time: now, type: 'work' as const,
          agentA: p ? getFirstName(from) : from,
          emojiA: p?.emoji || '🤖',
          message: cleanMsg.length > 50 ? cleanMsg.slice(0, 48) + '..' : cleanMsg,
        }].slice(-MAX_FEED_ENTRIES));
      }
    } else if (event.event === 'mission_tool_calls') {
      const agent = (d.agent as string) || '';
      const tools = (d.tools as string[]) || [];
      if (agent && tools.length > 0) {
        const p = getPersona(agent);
        const toolList = tools.slice(0, 5).join(', ');
        setActivityFeed(prev => [...prev, {
          id: Date.now(), time: now, type: 'work' as const,
          agentA: p ? getFirstName(agent) : agent,
          emojiA: p?.emoji || '🤖',
          message: `🔧 도구 호출: ${toolList.length > 40 ? toolList.slice(0, 38) + '..' : toolList}`,
        }].slice(-MAX_FEED_ENTRIES));
      }
    } else if (event.event === 'mission_approval_required') {
      const msg = (d.message as string) || '승인 대기';
      const agents = (d.agents as string[]) || [];
      const names = agents.map(a => { const p = getPersona(a); return p ? getFirstName(a) : a; }).join(', ');
      setActivityFeed(prev => [...prev, {
        id: Date.now(), time: now, type: 'work' as const,
        agentA: 'SYSTEM',
        emojiA: '🛡️',
        message: `승인 대기: ${names || msg}`,
      }].slice(-MAX_FEED_ENTRIES));
    } else if (event.event === 'mission_complete') {
      const title = (d.title as string) || '미션';
      setActivityFeed(prev => [...prev, {
        id: Date.now(), time: now, type: 'work' as const,
        agentA: 'SYSTEM',
        emojiA: '✅',
        message: `미션 완료: ${title.length > 30 ? title.slice(0, 28) + '..' : title}`,
      }].slice(-MAX_FEED_ENTRIES));
    } else if (event.event === 'mission_failed') {
      const err = (d.error as string) || '실패';
      setActivityFeed(prev => [...prev, {
        id: Date.now(), time: now, type: 'work' as const,
        agentA: 'SYSTEM',
        emojiA: '❌',
        message: `미션 실패: ${err.length > 30 ? err.slice(0, 28) + '..' : err}`,
      }].slice(-MAX_FEED_ENTRIES));
    }
  }, []);

  // 활동 로그 수신
  const handleActivityLog = useCallback((entry: ActivityLogEntry) => {
    setActivityFeed(prev => {
      const next = [...prev, entry];
      return next.length > MAX_FEED_ENTRIES ? next.slice(-MAX_FEED_ENTRIES) : next;
    });
  }, []);

  // 피드 자동 스크롤
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activityFeed]);

  // 드래그 리사이즈
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);
  const consoleHeightRef = useRef(consoleHeight);
  consoleHeightRef.current = consoleHeight;

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startY: e.clientY, startH: consoleHeightRef.current };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = dragRef.current.startY - ev.clientY;
      const newH = Math.max(CONSOLE_MIN_H, Math.min(CONSOLE_MAX_H, dragRef.current.startH + delta));
      setConsoleHeight(newH);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      try { localStorage.setItem('mission-console-height', String(consoleHeightRef.current)); } catch { /* ok */ }
      dragRef.current = null;
    };
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 상단: 플레이그라운드 + 사이드 피드 */}
      <div className="flex-1 min-h-0 overflow-hidden flex">
        {/* 좌: PixelOffice */}
        <div className="flex-1 min-w-0 overflow-hidden">
          <PixelOffice
            runtimeMap={runtimeMap}
            hiredSet={hiredSet}
            onSelectAgent={handleSelectAgent}
            onActivityLog={handleActivityLog}
            muteChat={muteChat}
          />
        </div>

        {/* 우: 사이드 활동 피드 (토글 가능) */}
        <div className={`flex-shrink-0 border-l border-zinc-800/50 flex flex-col transition-all duration-200 ${feedOpen ? 'w-64' : 'w-8'}`}
          style={{ background: '#08080d' }}>
          {/* 헤더: 토글 + 뮤트 */}
          <div className="px-1.5 py-2 border-b border-zinc-800/50 flex items-center gap-1">
            <button
              onClick={() => setFeedOpen(o => !o)}
              className="p-1 rounded transition-colors text-zinc-500 hover:bg-zinc-700/30 hover:text-zinc-300"
              title={feedOpen ? '피드 접기' : '피드 펼치기'}
            >
              {feedOpen ? <PanelRightClose size={12} /> : <PanelRightOpen size={12} />}
            </button>
            {feedOpen && (
              <>
                <MessageSquare size={11} className="text-zinc-500" />
                <span className="text-[10px] font-bold text-zinc-400 tracking-wider">OFFICE FEED</span>
                <button
                  onClick={() => setMuteChat(!muteChat)}
                  className={`ml-auto p-1 rounded transition-colors ${muteChat ? 'text-red-400 hover:bg-red-500/10' : 'text-zinc-600 hover:bg-zinc-700/30 hover:text-zinc-400'}`}
                  title={muteChat ? '잡담 켜기' : '입닥시키기'}
                >
                  {muteChat ? <VolumeX size={12} /> : <Volume2 size={12} />}
                </button>
              </>
            )}
          </div>
          {/* 피드 본문 */}
          {feedOpen && (
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {activityFeed.length === 0 && (
                <p className="text-[10px] text-zinc-600 text-center py-8">
                  에이전트 활동이 여기에 표시됩니다
                </p>
              )}
              {activityFeed.map(entry => (
                <div key={entry.id} className="px-2.5 py-1.5 border-b border-zinc-800/20 hover:bg-white/[0.02] transition-colors">
                  <div className="flex items-start gap-1.5">
                    <FeedIcon type={entry.type} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <span className="text-[10px]">{entry.emojiA}</span>
                        <span className="text-[10px] font-semibold text-zinc-300">{entry.agentA}</span>
                        {entry.agentB && (
                          <>
                            <span className="text-[9px] text-zinc-600">×</span>
                            <span className="text-[10px]">{entry.emojiB}</span>
                            <span className="text-[10px] font-semibold text-zinc-300">{entry.agentB}</span>
                          </>
                        )}
                        <span className="text-[8px] text-zinc-600 ml-auto flex-shrink-0">{entry.time}</span>
                      </div>
                      {entry.type === 'chat' ? (
                        <p className="text-[10px] text-blue-300/80 mt-0.5 leading-relaxed">{entry.message}</p>
                      ) : (
                        <p className="text-[10px] text-zinc-500 mt-0.5">{entry.message}</p>
                      )}
                    </div>
                  </div>
                </div>
              ))}
              <div ref={feedEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* 리사이즈 핸들 */}
      <div
        onMouseDown={onDragStart}
        className="flex-shrink-0 h-1.5 cursor-row-resize flex items-center justify-center group hover:bg-zinc-700/30 transition-colors"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(63,63,70,0.3), transparent)' }}
      >
        <div className="w-8 h-0.5 rounded-full bg-zinc-700 group-hover:bg-zinc-500 transition-colors" />
      </div>

      {/* 하단: 미션 콘솔 */}
      <div className="flex-shrink-0 overflow-hidden border-t border-zinc-800/50"
        style={{ height: consoleHeight }}>
        <MissionConsole onMissionEvent={handleMissionEvent} />
      </div>
    </div>
  );
}
