'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { agentApi, type AgentRuntimeStatus, type MissionSSEEvent } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import PixelOffice, { type ActivityLogEntry } from '@/components/playground/PixelOffice';
import MissionConsole from '@/components/MissionConsole';
import { MessageSquare, Coffee, Briefcase, MapPin, VolumeX, Volume2, PanelRightClose, PanelRightOpen, Building2, ClipboardList, Terminal, Users, Brain } from 'lucide-react';
import DockerLogPanel from '@/components/DockerLogPanel';
import AgentsTab from '@/components/tabs/AgentsTab';
import PersonalityTab from '@/components/tabs/PersonalityTab';
import { getFirstName, getPersona } from '@/lib/personas';

interface MissionTabProps {
  isActive?: boolean;
}

type OfficeSubTab = 'office' | 'work' | 'members' | 'personality';

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
  const [subTab, setSubTab] = useState<OfficeSubTab>('office');
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});
  const [activityFeed, setActivityFeed] = useState<ActivityLogEntry[]>([]);
  const { muteChat, setMuteChat } = useAppStore();
  const [feedOpen, setFeedOpen] = useState(true);
  const [logPanelOpen, setLogPanelOpen] = useState(false);
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

  // 이벤트 → 피드 엔트리 변환 (setState 없이 순수 함수)
  const eventToFeedEntry = useCallback((event: MissionSSEEvent): ActivityLogEntry | null => {
    const d = event.data as Record<string, unknown>;
    const now = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    const base = { id: Date.now() + Math.random(), time: now, type: 'work' as const };

    switch (event.event) {
      case 'agent_dm': {
        const from = (d.from as string) || '', to = (d.to as string) || '', msg = (d.message as string) || '';
        if (!from || !msg) return null;
        const pA = getPersona(from), pB = to ? getPersona(to) : null;
        return { ...base, agentA: pA ? getFirstName(from) : from, emojiA: pA?.emoji || '🤖',
          agentB: pB ? getFirstName(to) : to || undefined, emojiB: pB?.emoji || undefined,
          message: msg.length > 50 ? msg.slice(0, 48) + '..' : msg };
      }
      case 'agent_report': {
        const from = (d.from as string) || '', msg = (d.message as string) || '';
        if (!from || !msg) return null;
        const p = getPersona(from);
        return { ...base, agentA: p ? getFirstName(from) : from, emojiA: p?.emoji || '🤖',
          message: `보고: ${msg.length > 40 ? msg.slice(0, 38) + '..' : msg}` };
      }
      case 'mission_agent_activity': {
        const agent = (d.agent as string) || '', action = (d.action as string) || '';
        if (!agent) return null;
        const p = getPersona(agent);
        return { ...base, agentA: p ? getFirstName(agent) : agent, emojiA: p?.emoji || '🤖',
          message: action === 'working' ? '작업 시작' : action === 'done' ? '작업 완료' : action };
      }
      case 'mission_thinking': {
        const step = (d.step as string) || '', detail = (d.detail as string) || '';
        const from = (d.from as string) || 'JINXUS_CORE';
        if (step !== 'agent_progress' || !/🔧|✅|❌|도구|tool/i.test(detail)) return null;
        const p = getPersona(from);
        const cleanMsg = detail.replace(/^\[[\w_]+\]\s*/, '');
        return { ...base, agentA: p ? getFirstName(from) : from, emojiA: p?.emoji || '🤖',
          message: cleanMsg.length > 50 ? cleanMsg.slice(0, 48) + '..' : cleanMsg };
      }
      case 'mission_tool_calls': {
        const agent = (d.agent as string) || '', tools = (d.tools as string[]) || [];
        if (!agent || !tools.length) return null;
        const p = getPersona(agent), toolList = tools.slice(0, 5).join(', ');
        return { ...base, agentA: p ? getFirstName(agent) : agent, emojiA: p?.emoji || '🤖',
          message: `🔧 도구 호출: ${toolList.length > 40 ? toolList.slice(0, 38) + '..' : toolList}` };
      }
      case 'mission_approval_required': {
        const msg = (d.message as string) || '승인 대기', agents = (d.agents as string[]) || [];
        const names = agents.map(a => { const p = getPersona(a); return p ? getFirstName(a) : a; }).join(', ');
        return { ...base, agentA: 'SYSTEM', emojiA: '🛡️', message: `승인 대기: ${names || msg}` };
      }
      case 'mission_complete': {
        const title = (d.title as string) || '업무';
        return { ...base, agentA: 'SYSTEM', emojiA: '✅',
          message: `업무 완료: ${title.length > 30 ? title.slice(0, 28) + '..' : title}` };
      }
      case 'mission_failed': {
        const err = (d.error as string) || '실패';
        return { ...base, agentA: 'SYSTEM', emojiA: '❌',
          message: `업무 실패: ${err.length > 30 ? err.slice(0, 28) + '..' : err}` };
      }
      default: return null;
    }
  }, []);

  // 업무 이벤트 → runtimeMap + OFFICE FEED (단일 setState로 통합)
  const handleMissionEvent = useCallback((event: MissionSSEEvent) => {
    const d = event.data as Record<string, unknown>;

    // runtimeMap 업데이트 (agent_activity만)
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

    // 피드 업데이트 (단일 setState)
    const entry = eventToFeedEntry(event);
    if (entry) {
      setActivityFeed(prev => {
        const next = [...prev, entry];
        return next.length > MAX_FEED_ENTRIES ? next.slice(-MAX_FEED_ENTRIES) : next;
      });
    }
  }, [eventToFeedEntry]);

  const handleActivityLog = useCallback((entry: ActivityLogEntry) => {
    setActivityFeed(prev => {
      const next = [...prev, entry];
      return next.length > MAX_FEED_ENTRIES ? next.slice(-MAX_FEED_ENTRIES) : next;
    });
  }, []);

  // 피드 스크롤 — 쓰로틀링 (100ms) + behavior: auto (jank 방지)
  const scrollThrottleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (scrollThrottleRef.current) return;
    scrollThrottleRef.current = setTimeout(() => {
      feedEndRef.current?.scrollIntoView({ behavior: 'auto' });
      scrollThrottleRef.current = null;
    }, 100);
  }, [activityFeed]);

  // 작업중 에이전트 수 (메모이제이션)
  const workingCount = useMemo(
    () => Object.values(runtimeMap).filter(r => r.status === 'working').length,
    [runtimeMap],
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 상단 서브탭: 근무 환경 | 업무 */}
      <div className="flex-shrink-0 flex items-center gap-1 px-4 py-1.5 border-b border-zinc-800/50"
        style={{ background: '#0a0a12' }}>
        <span className="text-[11px] font-bold text-zinc-400 tracking-wider mr-3">JINXUS CORP.</span>

        <button
          onClick={() => setSubTab('office')}
          className={`flex items-center gap-1.5 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded-lg text-xs font-medium transition-colors active:bg-zinc-700/80 ${
            subTab === 'office'
              ? 'bg-zinc-700/60 text-white'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
          }`}
          style={{ minHeight: 44 }}
        >
          <Building2 size={13} />
          Office View
        </button>

        <button
          onClick={() => setSubTab('work')}
          className={`flex items-center gap-1.5 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded-lg text-xs font-medium transition-colors active:bg-zinc-700/80 ${
            subTab === 'work'
              ? 'bg-zinc-700/60 text-white'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
          }`}
          style={{ minHeight: 44 }}
        >
          <ClipboardList size={13} />
          Task
          {workingCount > 0 && (
            <span className="text-[9px] text-blue-400 bg-blue-500/15 px-1.5 py-0.5 rounded-full ml-1">
              {workingCount}
            </span>
          )}
        </button>

        <button
          onClick={() => setSubTab('members')}
          className={`flex items-center gap-1.5 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded-lg text-xs font-medium transition-colors active:bg-zinc-700/80 ${
            subTab === 'members'
              ? 'bg-zinc-700/60 text-white'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
          }`}
          style={{ minHeight: 44 }}
        >
          <Users size={13} />
          Members
          <span className="text-[9px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded-full ml-1">
            {hrAgents.filter(a => a.is_active).length}
          </span>
        </button>

        <button
          onClick={() => setSubTab('personality')}
          className={`flex items-center gap-1.5 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded-lg text-xs font-medium transition-colors active:bg-zinc-700/80 ${
            subTab === 'personality'
              ? 'bg-zinc-700/60 text-white'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
          }`}
          style={{ minHeight: 44 }}
        >
          <Brain size={13} />
          Personality
        </button>

        <button
          onClick={() => setLogPanelOpen(o => !o)}
          className={`ml-auto flex items-center gap-1.5 px-4 sm:px-3 py-2.5 sm:py-1.5 rounded-lg text-xs font-medium transition-colors active:bg-zinc-700/80 ${
            logPanelOpen
              ? 'bg-zinc-700/60 text-white'
              : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
          }`}
          style={{ minHeight: 44 }}
        >
          <Terminal size={13} />
          Log
        </button>
      </div>

      {/* 서브탭 컨텐츠 */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {/* 근무 환경: PixelOffice + FEED */}
        <div className={subTab === 'office' ? 'h-full flex flex-col sm:flex-row' : 'hidden'}>
          {/* 좌: PixelOffice */}
          <div className="flex-1 min-w-0 min-h-0 overflow-hidden">
            <PixelOffice
              runtimeMap={runtimeMap}
              hiredSet={hiredSet}
              onSelectAgent={handleSelectAgent}
              onActivityLog={handleActivityLog}
              muteChat={muteChat}
            />
          </div>

          {/* 우: 사이드 활동 피드 — 모바일: 하단 바, 데스크톱: 사이드 패널 */}
          <div className={`flex-shrink-0 border-l-0 sm:border-l border-t sm:border-t-0 border-zinc-800/50 flex flex-col transition-all duration-200 ${
            feedOpen ? 'h-48 sm:h-auto sm:w-64' : 'h-8 sm:h-auto sm:w-8'
          }`}
            style={{ background: '#08080d' }}>
            <div className="px-1.5 py-2 border-b border-zinc-800/50 flex items-center gap-1">
              <button
                onClick={() => setFeedOpen(o => !o)}
                className="p-2 sm:p-1 rounded transition-colors text-zinc-500 hover:bg-zinc-700/30 hover:text-zinc-300 active:bg-zinc-700/50"
                title={feedOpen ? '피드 접기' : '피드 펼치기'}
                style={{ minWidth: 36, minHeight: 36 }}
              >
                {feedOpen ? <PanelRightClose size={14} className="sm:w-3 sm:h-3" /> : <PanelRightOpen size={14} className="sm:w-3 sm:h-3" />}
              </button>
              {feedOpen && (
                <>
                  <MessageSquare size={11} className="text-zinc-500" />
                  <span className="text-[10px] font-bold text-zinc-400 tracking-wider">OFFICE FEED</span>
                  <button
                    onClick={() => setMuteChat(!muteChat)}
                    className={`ml-auto p-2 sm:p-1 rounded transition-colors ${muteChat ? 'text-red-400 hover:bg-red-500/10' : 'text-zinc-600 hover:bg-zinc-700/30 hover:text-zinc-400'}`}
                    title={muteChat ? '잡담 켜기' : '입닥시키기'}
                    style={{ minWidth: 36, minHeight: 36 }}
                  >
                    {muteChat ? <VolumeX size={14} className="sm:w-3 sm:h-3" /> : <Volume2 size={14} className="sm:w-3 sm:h-3" />}
                  </button>
                </>
              )}
            </div>
            {feedOpen && (
              <div className="flex-1 overflow-y-auto custom-scrollbar mobile-scroll">
                {activityFeed.length === 0 && (
                  <p className="text-[10px] text-zinc-600 text-center py-8">
                    에이전트 활동이 여기에 표시됩니다
                  </p>
                )}
                {activityFeed.map(entry => (
                  <div key={entry.id} className="px-2.5 py-1.5 border-b border-zinc-800/20 hover:bg-white/[0.02] active:bg-white/[0.04] transition-colors">
                    <div className="flex items-start gap-1.5">
                      <FeedIcon type={entry.type} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1">
                          <span className="text-[10px]">{entry.emojiA}</span>
                          <span className="text-[10px] font-semibold text-zinc-300">{entry.agentA}</span>
                          {entry.agentB && (
                            <>
                              <span className="text-[9px] text-zinc-600">&times;</span>
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

        {/* 업무: MissionConsole 전체 화면 */}
        <div className={subTab === 'work' ? 'h-full' : 'hidden'}>
          <MissionConsole onMissionEvent={handleMissionEvent} runtimeMap={runtimeMap} />
        </div>

        {/* 직원 현황: AgentsTab */}
        {subTab === 'members' && (
          <div className="h-full overflow-auto p-3 sm:p-4 md:p-6">
            <AgentsTab isActive={subTab === 'members'} forcedSubTab="status" />
          </div>
        )}

        {/* 에이전트 인격: PersonalityTab */}
        {subTab === 'personality' && (
          <div className="h-full overflow-auto p-3 sm:p-4 md:p-6">
            <PersonalityTab isActive={subTab === 'personality'} />
          </div>
        )}
      </div>

      {/* 시스템 로그 패널 (하단 슬라이드) */}
      {logPanelOpen && (
        <div className="flex-shrink-0 border-t border-zinc-800/50" style={{ height: 280 }}>
          <DockerLogPanel />
        </div>
      )}
    </div>
  );
}
