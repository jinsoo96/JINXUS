'use client';

import React, { useEffect, useRef, useState, useCallback, memo, useMemo } from 'react';
import { channelApi, agentApi, type PendingApproval, type AgentRuntimeStatus } from '@/lib/api';
import { getChannelAgents, getPersona, getDisplayName, getRole, sortByRank } from '@/lib/personas';
import { useAppStore } from '@/store/useAppStore';
import {
  matrixLogin, matrixSync, matrixSend, getMatrixHS,
  resolveAllChannelRooms, loadSession, clearSession,
  senderToName, senderToEmoji, isUserSender,
  type MatrixEvent, type MatrixSession,
} from '@/lib/matrix';
import { Send, CheckCircle, XCircle, Edit2, AlertCircle, ChevronRight, Building2, Users, Wifi, WifiOff, Trash2 } from 'lucide-react';

// ── 채널 설정 (백엔드 ChannelName enum 동기화) ───────────────────────────

const CHANNELS = [
  { id: 'general',     label: '전사 공지',   icon: '🏢', description: '업무 수여 및 전사 보고' },
  { id: 'engineering', label: '개발팀',      icon: '💻', description: '개발·구현·인프라·QA' },
  { id: 'research',    label: '리서치팀',    icon: '🔬', description: '기술 조사·시장 분석·팩트체크' },
  { id: 'marketing',   label: '마케팅팀',    icon: '📣', description: '최신 기법·GitHub 트렌드·아이디어 발굴' },
  { id: 'ops',         label: '운영팀',      icon: '🖥️', description: '시스템 운영·모니터링·배포' },
  { id: 'planning',    label: '전략기획',    icon: '📐', description: '제품 기획·로드맵·전략 수립' },
] as const;

type ChannelId = typeof CHANNELS[number]['id'];
const CHANNEL_IDS = CHANNELS.map(c => c.id) as ChannelId[];

// ── Matrix 메시지 → 내부 메시지 타입 ─────────────────────────────────────

interface ChatMsg {
  id: string;
  fromName: string;
  emoji: string;
  content: string;
  channel: ChannelId;
  createdAt: string;
  isUser: boolean;
}

function matrixEventToChatMsg(ev: MatrixEvent, channel: ChannelId): ChatMsg | null {
  if (ev.type !== 'm.room.message') return null;
  if (ev.content?.msgtype !== 'm.text') return null;
  const body = ev.content.body as string | undefined;
  if (!body) return null;
  // 에이전트 자신의 메시지는 그대로 표시 (포함)
  return {
    id: ev.event_id,
    fromName: senderToName(ev.sender),
    emoji: senderToEmoji(ev.sender),
    content: body,
    channel,
    createdAt: new Date(ev.origin_server_ts).toISOString(),
    isUser: isUserSender(ev.sender),
  };
}

// ── 하위 컴포넌트 ──────────────────────────────────────────────────────

const ChatMessage = memo(({ msg }: { msg: ChatMsg }) => {
  const time = new Date(msg.createdAt).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  return (
    <div className={`flex gap-3 px-4 py-1.5 hover:bg-white/5 group ${msg.isUser ? 'flex-row-reverse' : ''}`}>
      <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-base flex-shrink-0 mt-0.5
        ${msg.isUser ? 'bg-blue-600' : 'bg-dark-card border border-dark-border'}`}>
        {msg.emoji}
      </div>
      <div className={`flex-1 min-w-0 flex flex-col ${msg.isUser ? 'items-end' : ''}`}>
        <div className={`flex items-baseline gap-2 mb-0.5 ${msg.isUser ? 'flex-row-reverse' : ''}`}>
          <span className={`text-sm font-semibold ${msg.isUser ? 'text-blue-400' : 'text-gray-200'}`}>
            {msg.fromName}
          </span>
          <span className="text-xs text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity">
            {time}
          </span>
        </div>
        <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap break-words break-all">
          {msg.content}
        </div>
      </div>
    </div>
  );
});
ChatMessage.displayName = 'ChatMessage';

const ApprovalCard = memo(({ approval, onRespond }: {
  approval: PendingApproval;
  onRespond: (id: string, status: 'approved' | 'modified' | 'cancelled', feedback?: string) => void;
}) => {
  const [feedback, setFeedback] = useState('');
  const [showModify, setShowModify] = useState(false);
  return (
    <div className="mx-4 my-2 bg-amber-500/10 border border-amber-500/40 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertCircle size={16} className="text-amber-400" />
        <span className="text-sm font-semibold text-amber-400">승인 대기 중</span>
        <span className="text-xs text-gray-500 ml-auto">{approval.subtasks_count}개 에이전트</span>
      </div>
      <p className="text-sm text-gray-300 mb-3 leading-relaxed whitespace-pre-wrap">{approval.plan_summary}</p>
      {showModify && (
        <textarea
          value={feedback}
          onChange={e => setFeedback(e.target.value)}
          placeholder="수정 의견을 입력해 주세요..."
          className="w-full bg-dark-card border border-dark-border rounded-lg p-2 text-sm text-gray-300 mb-3 resize-none focus:outline-none focus:border-blue-500"
          rows={2}
        />
      )}
      <div className="flex gap-2">
        <button onClick={() => onRespond(approval.id, 'approved')}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded-lg text-xs font-medium transition-colors">
          <CheckCircle size={13} /> 승인
        </button>
        {!showModify ? (
          <button onClick={() => setShowModify(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600/60 hover:bg-blue-600 rounded-lg text-xs font-medium transition-colors">
            <Edit2 size={13} /> 수정 요청
          </button>
        ) : (
          <button onClick={() => { onRespond(approval.id, 'modified', feedback); setShowModify(false); }}
            disabled={!feedback.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded-lg text-xs font-medium transition-colors">
            <ChevronRight size={13} /> 전송
          </button>
        )}
        <button onClick={() => onRespond(approval.id, 'cancelled')}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-red-700/60 hover:bg-red-600 rounded-lg text-xs font-medium transition-colors ml-auto">
          <XCircle size={13} /> 취소
        </button>
      </div>
    </div>
  );
});
ApprovalCard.displayName = 'ApprovalCard';

const ChannelMembers = memo(({
  channelId,
  personasVersion: _v,
  hiredCodes,
  runtimeMap,
}: {
  channelId: string;
  personasVersion: number;
  hiredCodes: Set<string>;
  runtimeMap: Record<string, AgentRuntimeStatus>;
}) => {
  const allInChannel = getChannelAgents(channelId);
  const members = allInChannel.filter(code => hiredCodes.has(code)).sort(sortByRank);
  if (members.length === 0) return <span className="text-[10px] text-gray-600">없음</span>;
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[9px] text-gray-600 mb-0.5">{members.length}명</span>
      {members.map(code => {
        const p = getPersona(code);
        if (!p) return null;
        const isWorking = runtimeMap[code]?.status === 'working';
        return (
          <div key={code} className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
              isWorking ? 'bg-green-400 animate-pulse shadow-[0_0_5px_rgba(74,222,128,0.8)]' : 'bg-zinc-700'
            }`} />
            <span className="text-xs leading-none flex-shrink-0">{p.emoji}</span>
            <span className={`text-[11px] truncate ${isWorking ? 'text-green-300' : 'text-gray-400'}`}>{getDisplayName(code)}</span>
            <span className="text-[10px] text-gray-600 truncate flex-shrink-0">{getRole(code)}</span>
          </div>
        );
      })}
    </div>
  );
});
ChannelMembers.displayName = 'ChannelMembers';

// ── 메인 컴포넌트 ──────────────────────────────────────────────────────

export default function CompanyChat({ isActive }: { isActive: boolean }) {
  const { personasVersion, hrAgents } = useAppStore();
  const hiredCodes = useMemo(
    () => new Set(hrAgents.map(a => a.name)),
    [hrAgents],
  );

  // 런타임 상태 폴링 (작업 중 에이전트 표시용)
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});
  useEffect(() => {
    if (!isActive) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await agentApi.getAllRuntimeStatus();
        if (cancelled) return;
        const map: Record<string, AgentRuntimeStatus> = {};
        for (const a of res.agents) map[a.name] = a;
        setRuntimeMap(map);
      } catch { /* ignore */ }
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => { cancelled = true; clearInterval(id); };
  }, [isActive]);
  const [activeChannel, setActiveChannel] = useState<ChannelId>('general');
  const [messages, setMessages] = useState<Record<ChannelId, ChatMsg[]>>({
    general: [], planning: [], engineering: [], research: [], ops: [], marketing: [],
  });
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [unread, setUnread] = useState<Record<ChannelId, number>>({
    general: 0, planning: 0, engineering: 0, research: 0, ops: 0, marketing: 0,
  });
  const [matrixStatus, setMatrixStatus] = useState<'connecting' | 'connected' | 'error'>('connecting');
  const [retryCount, setRetryCount] = useState(0);
  // 멤버 패널 리사이즈
  const [memberHeight, setMemberHeight] = useState(200);
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      // 드래그 위로 → 높이 증가 (startY - currentY)
      const delta = dragRef.current.startY - e.clientY;
      const next = Math.max(80, Math.min(window.innerHeight * 0.6, dragRef.current.startH + delta));
      setMemberHeight(next);
    };
    const onUp = () => { dragRef.current = null; };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp); };
  }, []);

  const startMemberDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    dragRef.current = { startY: e.clientY, startH: memberHeight };
  }, [memberHeight]);
  // 채널별 "삭제 시점" — 이 시점 이전 메시지는 Matrix sync에서도 필터링
  const [clearedAt, setClearedAt] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem('channel_cleared_at') || '{}'); } catch { return {}; }
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);
  const activeChannelRef = useRef<ChannelId>(activeChannel);

  // Matrix 세션 + 룸 매핑 refs
  const sessionRef = useRef<MatrixSession | null>(null);
  const channelToRoomRef = useRef<Record<string, string>>({});  // channel → roomId
  const roomToChannelRef = useRef<Record<string, ChannelId>>({});  // roomId → channel
  const sinceRef = useRef<string | undefined>(undefined);
  const syncAbortRef = useRef<AbortController | null>(null);

  // ── 스크롤 ─────────────────────────────────────────────────────────

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    isAtBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  }, []);

  // ── 승인 처리 ───────────────────────────────────────────────────────

  const handleApproval = useCallback(async (
    id: string, status: 'approved' | 'modified' | 'cancelled', feedback = ''
  ) => {
    try {
      await channelApi.approve(id, status, feedback);
      setPendingApprovals(prev => prev.filter(a => a.id !== id));
    } catch (e) {
      console.error('승인 처리 실패', e);
    }
  }, []);

  // ── Matrix 이벤트 처리 ─────────────────────────────────────────────

  const clearedAtRef = useRef(clearedAt);
  useEffect(() => { clearedAtRef.current = clearedAt; }, [clearedAt]);

  const processEvents = useCallback((events: MatrixEvent[]) => {
    const roomToChannel = roomToChannelRef.current;
    const cleared = clearedAtRef.current;
    for (const ev of events) {
      const channel = roomToChannel[ev.room_id] as ChannelId | undefined;
      if (!channel || !CHANNEL_IDS.includes(channel)) continue;
      const msg = matrixEventToChatMsg(ev, channel);
      if (!msg) continue;

      // clearedAt 이전 메시지는 무시
      if (cleared[channel] && msg.createdAt <= cleared[channel]) continue;

      setMessages(prev => {
        const existing = prev[channel] ?? [];
        if (existing.some(m => m.id === msg.id)) return prev;
        return { ...prev, [channel]: [...existing, msg] };
      });

      if (channel !== activeChannelRef.current && !msg.isUser) {
        setUnread(prev => ({ ...prev, [channel]: (prev[channel] ?? 0) + 1 }));
      }
    }
  }, []);

  // ── Matrix sync 루프 ───────────────────────────────────────────────

  const startSync = useCallback(async (session: MatrixSession) => {
    const abort = new AbortController();
    syncAbortRef.current = abort;

    const loop = async () => {
      while (!abort.signal.aborted) {
        try {
          const result = await matrixSync(session.accessToken, sinceRef.current, abort.signal);
          sinceRef.current = result.nextBatch;
          processEvents(result.events);
          if (matrixStatus !== 'connected') setMatrixStatus('connected');
        } catch (e: unknown) {
          if ((e as { name?: string })?.name === 'AbortError') return;
          console.warn('[Matrix] sync 실패, 3초 후 재시도:', e);
          // 토큰 만료 시 세션 초기화
          if ((e as Error)?.message?.includes('토큰 만료')) {
            clearSession();
            sessionRef.current = null;
            setMatrixStatus('error');
            return;
          }
          setMatrixStatus('error');
          await new Promise(r => setTimeout(r, 3000));
          if (!abort.signal.aborted) setMatrixStatus('connecting');
        }
      }
    };

    loop();
    return abort;
  }, [processEvents, matrixStatus]);

  // ── Matrix 초기화 ──────────────────────────────────────────────────

  useEffect(() => {
    if (!isActive) return;

    let cancelled = false;

    const init = async () => {
      setMatrixStatus('connecting');

      try {
        // 1. 세션 로드 또는 로그인 (저장된 토큰 유효성 검증 포함)
        const matrixUser = process.env.NEXT_PUBLIC_MATRIX_USER ?? 'jinsu';
        const matrixPass = process.env.NEXT_PUBLIC_MATRIX_PASSWORD ?? '';
        let session = loadSession();
        if (session) {
          // 저장된 토큰 유효성 검증 — whoami 호출
          const hs = getMatrixHS();
          try {
            const ac = new AbortController();
            const timer = setTimeout(() => ac.abort(), 6000);
            const whoami = await fetch(`${hs}/_matrix/client/v3/account/whoami`, {
              headers: { Authorization: `Bearer ${session.accessToken}` },
              signal: ac.signal,
            }).finally(() => clearTimeout(timer));
            if (!whoami.ok) {
              clearSession();
              session = null;
            }
          } catch {
            clearSession();
            session = null;
          }
        }
        if (!session) {
          session = await matrixLogin(matrixUser, matrixPass);
        }
        if (cancelled) return;
        sessionRef.current = session;

        // 2. 채널 룸 ID 조회
        const channelToRoom = await resolveAllChannelRooms(session.accessToken);
        if (cancelled) return;

        channelToRoomRef.current = channelToRoom;
        const reverseMap: Record<string, ChannelId> = {};
        for (const [ch, roomId] of Object.entries(channelToRoom)) {
          reverseMap[roomId] = ch as ChannelId;
        }
        roomToChannelRef.current = reverseMap;

        // 3. Sync 루프 시작
        if (!cancelled) {
          startSync(session);
          setMatrixStatus('connected');
        }
      } catch (e) {
        if (!cancelled) {
          console.error('[Matrix] 초기화 실패:', e);
          setMatrixStatus('error');
        }
      }

      // 4. 승인 대기 목록 로드 (별도 폴링)
      if (!cancelled) {
        channelApi.getPendingApprovals()
          .then(data => setPendingApprovals(data.pending || []))
          .catch(() => {});
      }
    };

    init();

    return () => {
      cancelled = true;
      syncAbortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, retryCount]);

  // activeChannel ref 동기화
  useEffect(() => {
    activeChannelRef.current = activeChannel;
    setUnread(prev => ({ ...prev, [activeChannel]: 0 }));
  }, [activeChannel]);

  // 스크롤 자동 이동
  useEffect(() => {
    if (isAtBottomRef.current) scrollToBottom();
  }, [messages, activeChannel, scrollToBottom]);

  // ── 메시지 전송 ────────────────────────────────────────────────────

  const handleSend = useCallback(async () => {
    if (!input.trim() || sending) return;
    const text = input.trim();
    setInput('');
    setSending(true);
    try {
      const session = sessionRef.current;
      const roomId = channelToRoomRef.current[activeChannel];
      if (session && roomId) {
        await matrixSend(session.accessToken, roomId, text);
        // Matrix sync가 자신의 메시지를 다시 받아오므로 별도 추가 불필요
      } else {
        // fallback: JINXUS 내부 채널로 전송 (Matrix 룸 아직 없을 때)
        await channelApi.postMessage(text, activeChannel);
      }
    } catch (e) {
      console.error('메시지 전송 실패', e);
    } finally {
      setSending(false);
    }
  }, [input, sending, activeChannel]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // ── 렌더 ───────────────────────────────────────────────────────────

  const currentMessages = messages[activeChannel] ?? [];
  const activeChannelInfo = CHANNELS.find(c => c.id === activeChannel)!;
  const showApprovals = activeChannel === 'planning' || activeChannel === 'general';
  const visibleApprovals = showApprovals ? pendingApprovals : [];

  return (
    <div className="flex h-full bg-dark-bg min-w-0">

      {/* ── 왼쪽: 채널 사이드바 ── */}
      <div className="w-52 flex-shrink-0 bg-dark-card border-r border-dark-border flex flex-col">
        {/* 헤더 */}
        <div className="p-3 border-b border-dark-border flex items-center gap-2">
          <Building2 size={14} className="text-gray-400" />
          <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">팀 채팅</h3>
          {/* Matrix 연결 상태 */}
          <div className="ml-auto flex items-center gap-1" title={
            matrixStatus === 'connected' ? 'Matrix 연결됨' :
            matrixStatus === 'connecting' ? '연결 중...' : 'Matrix 연결 끊김'
          }>
            {matrixStatus === 'connected'
              ? <Wifi size={14} className="text-green-400" />
              : matrixStatus === 'connecting'
              ? <Wifi size={14} className="text-yellow-400 animate-pulse" />
              : <WifiOff size={14} className="text-red-400" />
            }
            <span className={`text-[10px] ${
              matrixStatus === 'connected' ? 'text-green-400' :
              matrixStatus === 'connecting' ? 'text-yellow-400' : 'text-red-400'
            }`}>
              {matrixStatus === 'connected' ? '연결됨' : matrixStatus === 'connecting' ? '연결 중' : '끊김'}
            </span>
          </div>
        </div>

        {/* 채널 목록 */}
        <nav className="flex-1 overflow-y-auto py-2 space-y-0.5">
          {CHANNELS.map(ch => {
            const isActiveItem = activeChannel === ch.id;
            const unreadCount = unread[ch.id] ?? 0;
            return (
              <button
                key={ch.id}
                onClick={() => setActiveChannel(ch.id)}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors text-left
                  ${isActiveItem
                    ? 'bg-blue-600/20 text-blue-400 font-medium border-l-2 border-blue-500'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border-l-2 border-transparent'
                  }`}
              >
                <span className="text-base leading-none flex-shrink-0">{ch.icon}</span>
                <span className="flex-1 truncate">{ch.label}</span>
                {unreadCount > 0 && (
                  <span className="bg-blue-600 text-white text-[10px] font-bold rounded-full px-1.5 py-0.5 leading-none">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* 채널 멤버 — 리사이즈 가능 */}
        <div className="flex flex-col border-t border-dark-border min-h-[80px]" style={{ height: memberHeight }}>
          <div
            className="h-1 bg-dark-border cursor-row-resize hover:bg-primary/40 active:bg-primary/60 transition-colors flex-shrink-0"
            onMouseDown={startMemberDrag}
          />
          <div className="flex items-center gap-1.5 px-3 pt-2 pb-1 flex-shrink-0">
            <Users size={11} className="text-gray-500" />
            <p className="text-[10px] text-gray-500 uppercase tracking-wider">멤버</p>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto px-3 pb-2">
            <ChannelMembers channelId={activeChannel} personasVersion={personasVersion} hiredCodes={hiredCodes} runtimeMap={runtimeMap} />
          </div>
        </div>
      </div>

      {/* ── 오른쪽: 메시지 영역 ── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 채널 헤더 */}
        <div className="px-4 py-2.5 border-b border-dark-border flex items-center gap-2 flex-shrink-0">
          <span className="text-lg leading-none">{activeChannelInfo.icon}</span>
          <div>
            <span className="font-semibold text-gray-200">{activeChannelInfo.label}</span>
            <span className="text-xs text-gray-500 ml-2">{activeChannelInfo.description}</span>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {pendingApprovals.length > 0 && (
              <div className="flex items-center gap-1.5 text-amber-400 text-xs">
                <AlertCircle size={14} />
                승인 대기 {pendingApprovals.length}건
              </div>
            )}
            <button
              onClick={async () => {
                if (!confirm(`#${activeChannelInfo.label} 채널의 모든 대화를 삭제합니다.`)) return;
                try {
                  await channelApi.clearHistory(activeChannel);
                } catch { /* Redis 삭제 실패해도 로컬은 정리 */ }
                // 로컬 메시지 초기화 + clearedAt 기록
                setMessages(prev => ({ ...prev, [activeChannel]: [] }));
                const now = new Date().toISOString();
                setClearedAt(prev => {
                  const next = { ...prev, [activeChannel]: now };
                  localStorage.setItem('channel_cleared_at', JSON.stringify(next));
                  return next;
                });
              }}
              title="현재 채널 대화 전체 삭제"
              className="p-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {/* Matrix 에러 배너 */}
        {matrixStatus === 'error' && (
          <div className="px-4 py-2 bg-red-500/10 border-b border-red-500/20 text-xs text-red-400 flex items-center gap-2">
            <WifiOff size={12} />
            <span>Matrix 실시간 채널 연결 실패 — 메시지 전송은 계속 가능합니다.</span>
            <button
              onClick={() => { setMatrixStatus('connecting'); setRetryCount(c => c + 1); }}
              className="ml-auto px-2 py-0.5 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300 transition-colors"
            >재연결</button>
          </div>
        )}

        {/* 메시지 목록 */}
        <div className="flex-1 overflow-y-auto py-3" onScroll={handleScroll}>
          {currentMessages.length === 0 && matrixStatus === 'connected' ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-600">
              <span className="text-4xl mb-3 opacity-40">{activeChannelInfo.icon}</span>
              <p className="text-sm">{activeChannelInfo.label} 채널입니다.</p>
              <p className="text-xs mt-1">메시지를 입력하면 팀원들이 반응합니다.</p>
            </div>
          ) : currentMessages.length === 0 && matrixStatus === 'connecting' ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-600">
              <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mb-3" />
              <p className="text-sm">Matrix 연결 중...</p>
            </div>
          ) : (
            currentMessages.map(msg => <ChatMessage key={msg.id} msg={msg} />)
          )}

          {visibleApprovals.map(ap => (
            <ApprovalCard key={ap.id} approval={ap} onRespond={handleApproval} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* 입력 창 */}
        <div className="px-4 py-3 border-t border-dark-border flex-shrink-0">
          <div className="flex gap-2 items-end bg-dark-card border border-dark-border rounded-xl px-3 py-2 focus-within:border-blue-500 transition-colors">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`${activeChannelInfo.label}에 메시지 보내기...`}
              aria-label={`${activeChannelInfo.label} 메시지 입력`}
              className="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 resize-none outline-none min-h-[20px] max-h-[120px]"
              rows={1}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || sending}
              aria-label="메시지 전송"
              className="p-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
            >
              <Send size={14} />
            </button>
          </div>
          <p className="text-xs text-gray-600 mt-1.5 px-1">Enter 전송 · Shift+Enter 줄바꿈</p>
        </div>
      </div>
    </div>
  );
}
