'use client';

import { useState, useRef, useEffect, memo, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { chatApi, feedbackApi, taskApi, type ChatSession, type SSEEvent } from '@/lib/api';
import { createSmoothStreamer } from '@/lib/smooth-streaming';
import {
  Send, ThumbsUp, ThumbsDown, User, Loader2, Trash2,
  MessageSquare, RefreshCw, ChevronDown, Brain, Terminal,
  PanelBottomClose, PanelBottomOpen,
} from 'lucide-react';
import type { ChatMessage } from '@/types';
import ThinkingPanel, { type ThinkingLog } from '@/components/ThinkingPanel';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import DockerLogPanel from '@/components/DockerLogPanel';
import toast from 'react-hot-toast';

// ── Memo된 메시지 컴포넌트 ──
const ChatMessageItem = memo(function ChatMessageItem({
  message,
  onFeedback,
}: {
  message: ChatMessage;
  onFeedback: (taskId: string, score: number) => void;
}) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* 아바타 */}
      {isUser ? (
        <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 bg-primary">
          <User size={20} />
        </div>
      ) : (
        <div className="w-10 h-10 rounded-full flex-shrink-0 overflow-hidden bg-zinc-700">
          <img
            src="/jinxus-mascot.webp"
            alt="JINXUS"
            width={40}
            height={40}
            className="w-full h-full object-cover object-top scale-150"
          />
        </div>
      )}

      {/* 메시지 내용 */}
      <div className={`flex-1 ${isUser ? 'max-w-[90%] sm:max-w-[80%] lg:max-w-[70%] text-right' : 'max-w-[95%] sm:max-w-[90%] lg:max-w-[85%]'}`}>
        <div
          className={`inline-block p-4 rounded-2xl ${
            isUser
              ? 'bg-primary text-white rounded-tr-none'
              : 'bg-dark-card border border-dark-border rounded-tl-none'
          }`}
        >
          {isUser ? (
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          ) : (
            <div className="break-words">
              <MarkdownRenderer content={message.content} />
            </div>
          )}
        </div>

        {/* 메타 정보 */}
        <div
          className={`mt-2 flex items-center gap-2 text-xs text-zinc-500 ${
            isUser ? 'justify-end' : ''
          }`}
        >
          <span>{message.timestamp.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Seoul' })}</span>
          {message.agentsUsed && message.agentsUsed.length > 0 && (
            <span className="text-primary">
              {message.agentsUsed.join(', ')}
            </span>
          )}
        </div>

        {/* 피드백 버튼 (AI 응답에만) */}
        {!isUser && (
          <div className="mt-2 flex gap-2">
            <button
              onClick={() => onFeedback(message.id, 5)}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-green-400 transition-colors"
              title="좋아요"
            >
              <ThumbsUp size={16} />
            </button>
            <button
              onClick={() => onFeedback(message.id, 1)}
              className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-red-400 transition-colors"
              title="싫어요"
            >
              <ThumbsDown size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
});

export default function ChatTab() {
  const { messages, addMessage, isLoading, setLoading, sessionId, setSessionId, clearMessages } = useAppStore();
  const [input, setInput] = useState('');
  const [streamingContent, setStreamingContent] = useState('');
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // AbortController for SSE cancellation on unmount
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamerRef = useRef<ReturnType<typeof createSmoothStreamer> | null>(null);
  // 백그라운드 태스크 에러 시 폴링 interval 정리용
  const bgPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const bgPollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // SSE abort 유틸 (5곳 중복 제거)
  const abortSSE = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // Thinking Panel 상태
  const [thinkingLogs, setThinkingLogs] = useState<ThinkingLog[]>([]);
  const [showThinking, setShowThinking] = useState(true);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [isBackgroundTask, setIsBackgroundTask] = useState(false);
  const [showDockerLogs, setShowDockerLogs] = useState(false);

  // 하단 패널 상태
  const [bottomPanelOpen, setBottomPanelOpen] = useState(true);
  const [bottomPanelHeight, setBottomPanelHeight] = useState(220);
  const [bottomPanelTab, setBottomPanelTab] = useState<'system' | 'thinking'>('system');
  const isDraggingRef = useRef(false);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(0);

  // 하단 패널 리사이즈 핸들러
  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    dragStartYRef.current = e.clientY;
    dragStartHeightRef.current = bottomPanelHeight;

    const handleMouseMove = (ev: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const delta = dragStartYRef.current - ev.clientY;
      const newHeight = Math.max(120, Math.min(600, dragStartHeightRef.current + delta));
      setBottomPanelHeight(newHeight);
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [bottomPanelHeight]);

  // Thinking 로그 추가 헬퍼
  const addThinkingLog = (step: string, detail?: string, agent?: string, status?: 'running' | 'done' | 'error') => {
    setThinkingLogs(prev => [...prev, {
      id: `${Date.now()}-${Math.random()}`,
      timestamp: new Date(),
      step,
      detail,
      agent,
      status,
    }]);
  };

  // 작업 중지 (SSE 스트리밍 취소) - taskId 없어도 강제 중지 가능
  const handleStopTask = async () => {
    try {
      // 1. 프론트엔드 SSE 연결 즉시 중단 (taskId 유무 무관)
      abortSSE();

      // 2. 백엔드에 취소 알림 (taskId 있을 때만)
      if (currentTaskId) {
        try {
          const result = await chatApi.cancelStream(currentTaskId);
          addThinkingLog('cancelled', result.success ? '사용자가 작업을 중지했습니다' : result.message, undefined, 'error');
        } catch {
          // 백엔드 취소 실패해도 무시
        }
      } else {
        addThinkingLog('cancelled', '작업을 강제 중지했습니다', undefined, 'error');
      }
    } catch (error) {
      console.error('Failed to cancel stream:', error);
    } finally {
      // UI 상태 무조건 초기화
      setLoading(false);
      setStreamingContent('');
      setCurrentAgent(null);
      setCurrentTaskId(null);
    }
  };

  // 세션 목록 로드
  const loadSessions = async () => {
    setLoadingSessions(true);
    try {
      const response = await chatApi.getSessions();
      setSessions(response.sessions);
    } catch (error) {
      console.error('Failed to load sessions:', error);
      toast.error('세션 목록 로드 실패');
    } finally {
      setLoadingSessions(false);
    }
  };

  // 세션 히스토리 로드
  const loadSessionHistory = async (sid: string) => {
    try {
      const response = await chatApi.getHistory(sid);
      clearMessages();

      // 저장된 메시지를 ChatMessage 형식으로 변환
      response.messages.forEach((msg, idx) => {
        const chatMsg: ChatMessage = {
          id: msg.metadata?.task_id || `${sid}-${idx}`,
          role: msg.role,
          content: msg.content,
          timestamp: new Date(msg.timestamp),
          agentsUsed: msg.metadata?.agents_used,
        };
        addMessage(chatMsg);
      });

      setSessionId(sid);
      setShowSessions(false);
    } catch (error) {
      console.error('Failed to load history:', error);
    }
  };

  // 세션 삭제
  const deleteSession = async (sid: string) => {
    if (!confirm('이 세션을 삭제하시겠습니까?')) return;

    try {
      await chatApi.deleteSession(sid);
      setSessions(sessions.filter(s => s.session_id !== sid));
      if (sessionId === sid) {
        clearMessages();
        setSessionId('');
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
      toast.error('세션 삭제 실패');
    }
  };

  const handleClearChat = async () => {
    if (messages.length === 0 && !isLoading) return;

    // 1. 즉시 UI 초기화 (사용자 체감 반응)
    clearMessages();
    setLoading(false);
    setStreamingContent('');
    setCurrentAgent(null);
    setThinkingLogs([]);

    // 2. SSE 연결 중단
    abortSSE();

    // 3. 백엔드 정리 (비동기)
    const sid = sessionId;
    const tid = currentTaskId;
    setSessionId('');
    setCurrentTaskId(null);

    if (tid) {
      chatApi.cancelStream(tid).catch(() => {});
    }
    if (sid) {
      chatApi.deleteSession(sid).then(() => {
        setSessions(prev => prev.filter(s => s.session_id !== sid));
      }).catch((e) => {
        console.warn('Session delete failed:', e);
      });
    }
  };

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  const scrollToBottom = () => {
    // 사용자가 위로 스크롤한 경우 강제 스크롤하지 않음
    if (!isNearBottomRef.current) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    // 하단 100px 이내면 "바닥 근처"로 판정
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  };

  // 컴포넌트 마운트 시 잔여 상태 정리 & 언마운트 시 SSE 정리
  useEffect(() => {
    // 이전 세션의 잔여 상태가 있으면 정리
    if (isLoading && !currentTaskId) {
      console.warn('Cleaning up stale loading state');
      setLoading(false);
      setStreamingContent('');
      setCurrentAgent(null);
    }

    // 컴포넌트 언마운트 시 SSE 연결 + 폴링 정리
    return () => {
      abortSSE();
      if (bgPollRef.current) { clearInterval(bgPollRef.current); bgPollRef.current = null; }
      if (bgPollTimeoutRef.current) { clearTimeout(bgPollTimeoutRef.current); bgPollTimeoutRef.current = null; }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  // 로딩 타임아웃: SSE 채팅만 적용 (background task는 자체 타임아웃 있으므로 제외)
  useEffect(() => {
    if (!isLoading || isBackgroundTask) return;
    const timeout = setTimeout(() => {
      if (isLoading && !isBackgroundTask) {
        addThinkingLog('timeout', '5분 타임아웃 - 작업 자동 중지', undefined, 'error');
        handleStopTask();
        toast.error('응답 타임아웃 (5분)');
      }
    }, 5 * 60 * 1000);
    return () => clearTimeout(timeout);
  }, [isLoading, isBackgroundTask]); // eslint-disable-line react-hooks/exhaustive-deps

  // 메시지가 장기/복잡 작업인지 자동 판단
  const shouldRunBackground = (msg: string): boolean => {
    const BG_KEYWORDS = [
      '구현', '개발', '코딩', '코드 작성', '만들어', '만들어줘', '만들어라', '만들어봐',
      '리팩토링', '리팩터', '테스트 코드', '테스트 작성', '배포', '자동화',
      '스크립트', '파일 생성', '프로젝트', '시스템 구축',
      '조사해', '분석해', '리서치', '연구해', '검색해서',
      '정리해', '요약해줘', '문서 작성', '보고서',
      '자율', '백그라운드', '장기',
    ];
    const lower = msg.toLowerCase();
    const hasKeyword = BG_KEYWORDS.some(k => lower.includes(k));
    const isLong = msg.length > 120;
    return hasKeyword || isLong;
  };

  // 통합 전송 핸들러 — 장기 작업 자동 감지 후 라우팅
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const command = input.trim();

    // 백그라운드 자동 라우팅
    if (shouldRunBackground(command)) {
      await handleBackgroundSubmitInner(command);
      return;
    }

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: command,
      timestamp: new Date(),
    };

    addMessage(userMessage);
    setInput('');
    setLoading(true);
    setStreamingContent('');
    setCurrentAgent(null);

    // Thinking 초기화
    setThinkingLogs([]);
    setCurrentTaskId(null);
    addThinkingLog('start', '작업 시작', undefined, 'running');

    let fullResponse = '';
    let agentsUsed: string[] = [];
    let taskId = '';
    let newSessionId = sessionId;

    // 타이핑 애니메이션 큐 (NextChat 패턴)
    const streamer = createSmoothStreamer((text) => setStreamingContent(text));
    streamerRef.current = streamer;

    // 새 AbortController 생성
    abortControllerRef.current = new AbortController();

    try {
      await chatApi.streamMessage(
        userMessage.content,
        sessionId || undefined,
        (event: SSEEvent) => {
          switch (event.event) {
            case 'start':
              taskId = event.data.task_id || '';
              setCurrentTaskId(taskId);
              if (event.data.session_id && !sessionId) {
                newSessionId = event.data.session_id;
                setSessionId(event.data.session_id);
              }
              addThinkingLog('start', `Task: ${taskId.slice(0, 8)}...`);
              break;

            case 'manager_thinking':
              addThinkingLog(event.data.step || 'thinking', event.data.detail, undefined, 'running');
              break;

            case 'decompose_done':
              addThinkingLog('decompose', `${event.data.subtasks_count}개 서브태스크 (${event.data.mode})`, undefined, 'done');
              break;

            case 'agent_started':
              setCurrentAgent(event.data.agent || null);
              addThinkingLog('agent_started', event.data.instruction || event.data.task_id?.slice(0, 8), event.data.agent, 'running');
              break;

            case 'agent_done':
              if (event.data.agent) {
                agentsUsed.push(event.data.agent);
                const score = event.data.score ? ` (점수: ${event.data.score.toFixed(1)})` : '';
                addThinkingLog('agent_done', event.data.success ? `완료${score}` : '실패', event.data.agent, event.data.success ? 'done' : 'error');
              }
              setCurrentAgent(null);
              break;

            case 'team_progress':
              // JX_CODER 전문가 팀 진행 이벤트
              addThinkingLog(
                'team_progress',
                event.data.detail || event.data.message,
                event.data.specialist || event.data.agent,
                event.data.status === 'done' ? 'done' : event.data.status === 'error' ? 'error' : 'running'
              );
              break;
            case 'message':
              // content 청크 → 타이핑 애니메이션 큐 (NextChat 패턴: rAF + 글자 단위 출력)
              if (event.data.content) {
                fullResponse += event.data.content;
                streamer.push(event.data.content);
              }
              break;
            case 'log':
              // 실제 Python 로거 출력 → 터미널 로그로 표시
              if (event.data.line) {
                addThinkingLog('raw_log', event.data.line, undefined, 'running');
              }
              break;
            case 'done':
              // 타이핑 큐 플러시 — 잔여 텍스트 즉시 출력
              fullResponse = event.data.response || fullResponse;
              streamer.flush();
              agentsUsed = event.data.agents_used || agentsUsed;
              addThinkingLog('done', '응답 완료', undefined, 'done');
              break;
            case 'error':
              addThinkingLog('error', event.data.error, undefined, 'error');
              throw new Error(event.data.error || 'Unknown error');

            case 'routed': {
              // SmartRouter → background/project 라우팅: 즉시 UI 해제
              const route = event.data.route as string;
              if (route === 'background' || route === 'project') {
                const tid = event.data.task_id || event.data.project_id || '';
                addMessage({
                  id: Date.now().toString(),
                  role: 'assistant',
                  content: route === 'project'
                    ? `프로젝트가 시작됐습니다. 백그라운드에서 실행 중이에요. (ID: ${tid.slice(0, 8)})`
                    : `백그라운드에서 작업을 처리하고 있어요. (ID: ${tid.slice(0, 8)})`,
                  timestamp: new Date(),
                  success: true,
                });
                setLoading(false);
                setCurrentTaskId(null);
              }
              break;
            }
            case 'cancelled':
              addThinkingLog('cancelled', event.data.message || '작업 취소됨', undefined, 'error');
              // 취소 시 스트리밍 중지
              setLoading(false);
              setCurrentTaskId(null);
              return; // 이벤트 루프 종료
          }
        },
        (error) => {
          addThinkingLog('error', error.message, undefined, 'error');
          throw error;
        },
        abortControllerRef.current
      );

      // 스트리밍 완료 후 메시지 추가
      const assistantMessage: ChatMessage = {
        id: taskId || Date.now().toString(),
        role: 'assistant',
        content: fullResponse,
        timestamp: new Date(),
        agentsUsed: agentsUsed.length > 0 ? agentsUsed : undefined,
        success: true,
      };

      setStreamingContent('');
      addMessage(assistantMessage);
      setCurrentTaskId(null);

    } catch (error) {
      // 스트리밍 실패 시 동기 API로 폴백
      console.warn('Streaming failed, falling back to sync:', error);
      addThinkingLog('fallback', '동기 API로 재시도', undefined, 'running');

      try {
        const response = await chatApi.sendMessage(userMessage.content, sessionId || undefined);

        if (response.session_id && !sessionId) {
          setSessionId(response.session_id);
        }

        const assistantMessage: ChatMessage = {
          id: response.task_id,
          role: 'assistant',
          content: response.response,
          timestamp: new Date(),
          agentsUsed: response.agents_used,
          success: response.success,
        };

        setStreamingContent('');
        addMessage(assistantMessage);
      } catch (syncError) {
        addThinkingLog('error', syncError instanceof Error ? syncError.message : '알 수 없는 오류', undefined, 'error');
        const errorMessage: ChatMessage = {
          id: Date.now().toString(),
          role: 'assistant',
          content: `죄송합니다 주인님, 오류가 발생했습니다: ${syncError instanceof Error ? syncError.message : '알 수 없는 오류'}`,
          timestamp: new Date(),
          success: false,
        };
        setStreamingContent('');
        addMessage(errorMessage);
        toast.error('메시지 전송 실패');
      }
    } finally {
      setLoading(false);
      setCurrentAgent(null);
      setCurrentTaskId(null);
      abortControllerRef.current = null;
    }
  };

  // 백그라운드 작업 실행 (자율 모드) — 자동 라우팅 시 호출
  const handleBackgroundSubmitInner = async (command: string) => {
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: `[백그라운드] ${command}`,
      timestamp: new Date(),
    };

    addMessage(userMessage);
    setInput('');
    setLoading(true);
    setIsBackgroundTask(true);

    // Thinking 초기화
    setThinkingLogs([]);
    addThinkingLog('start', '백그라운드 작업 제출 중...', undefined, 'running');

    try {
      const result = await taskApi.createTask({
        message: command,
        session_id: sessionId || undefined,
        autonomous: true,
      });

      const bgTaskId = result.task_id;
      setCurrentTaskId(bgTaskId);
      addThinkingLog('start', `백그라운드 작업 시작: ${bgTaskId.slice(0, 8)}`, undefined, 'running');

      // 백그라운드 작업은 제출 즉시 UI 해제 — 팀채널·다른 작업 계속 가능
      setLoading(false);
      setIsBackgroundTask(false);

      // SSE로 진행 상황 구독 (UI 블로킹 없이 백그라운드에서 계속)
      const streamController = taskApi.streamTaskProgress(
        bgTaskId,
        (event) => {
          switch (event.event) {
            case 'status':
              addThinkingLog('raw_log', `상태: ${event.data.status}`, undefined, 'running');
              break;
            case 'started':
              addThinkingLog('raw_log', `작업 시작됨 (autonomous=${event.data.autonomous})`, undefined, 'running');
              break;
            case 'progress':
              addThinkingLog('raw_log', String(event.data.message || '진행 중...'), undefined, 'running');
              break;
            case 'completed': {
              const preview = String(event.data.result_preview || '');
              addThinkingLog('done', `완료 (${event.data.duration_s}초)`, undefined, 'done');

              // 결과를 채팅에 표시
              taskApi.getTaskStatus(bgTaskId).then((detail) => {
                const assistantMessage: ChatMessage = {
                  id: bgTaskId,
                  role: 'assistant',
                  content: detail.result || preview || '작업 완료',
                  timestamp: new Date(),
                  agentsUsed: detail.agents_used,
                  success: true,
                };
                addMessage(assistantMessage);
              }).catch(() => {
                addMessage({
                  id: bgTaskId,
                  role: 'assistant',
                  content: preview || '작업 완료 (결과 조회 실패)',
                  timestamp: new Date(),
                  success: true,
                });
              });

              setLoading(false);
              setIsBackgroundTask(false);
              setCurrentTaskId(null);
              break;
            }
            case 'failed':
              addThinkingLog('error', `실패: ${event.data.error}`, undefined, 'error');
              addMessage({
                id: bgTaskId,
                role: 'assistant',
                content: `작업 실패: ${event.data.error}`,
                timestamp: new Date(),
                success: false,
              });
              setLoading(false);
              setIsBackgroundTask(false);
              setCurrentTaskId(null);
              break;
            case 'done': {
              const status = String(event.data.status || 'unknown');
              if (status !== 'completed' && status !== 'failed' && status !== 'cancelled') {
                addThinkingLog('done', '스트림 종료', undefined, 'done');
              }
              setLoading(false);
              setIsBackgroundTask(false);
              setCurrentTaskId(null);
              break;
            }
          }
        },
        (error) => {
          addThinkingLog('error', error.message, undefined, 'error');
          // 에러 시에도 폴링으로 결과 확인 시도
          // 이전 폴링 정리
          if (bgPollRef.current) clearInterval(bgPollRef.current);
          if (bgPollTimeoutRef.current) clearTimeout(bgPollTimeoutRef.current);

          const poll = setInterval(async () => {
            try {
              const detail = await taskApi.getTaskStatus(bgTaskId);
              if (detail.status === 'completed' || detail.status === 'failed') {
                clearInterval(poll);
                bgPollRef.current = null;
                if (bgPollTimeoutRef.current) { clearTimeout(bgPollTimeoutRef.current); bgPollTimeoutRef.current = null; }
                addMessage({
                  id: bgTaskId,
                  role: 'assistant',
                  content: detail.result || '작업 완료',
                  timestamp: new Date(),
                  success: detail.status === 'completed',
                });
                setLoading(false);
                setCurrentTaskId(null);
              }
            } catch { /* ignore */ }
          }, 5000);
          bgPollRef.current = poll;
          // 최대 30분 폴링
          bgPollTimeoutRef.current = setTimeout(() => {
            clearInterval(poll);
            bgPollRef.current = null;
            bgPollTimeoutRef.current = null;
          }, 30 * 60 * 1000);
        },
        () => {
          // onDone - 스트림 종료
        },
      );

      // abort 시 스트림도 종료
      abortControllerRef.current = new AbortController();
      abortControllerRef.current.signal.addEventListener('abort', () => {
        streamController.abort();
        taskApi.cancelTask(bgTaskId).catch(() => {});
      });

    } catch (error) {
      addThinkingLog('error', error instanceof Error ? error.message : '작업 생성 실패', undefined, 'error');
      addMessage({
        id: Date.now().toString(),
        role: 'assistant',
        content: `백그라운드 작업 생성 실패: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        timestamp: new Date(),
        success: false,
      });
      setLoading(false);
      setIsBackgroundTask(false);
      toast.error('백그라운드 작업 생성 실패');
    }
  };

  const getSessionIcon = (type: string) => {
    switch (type) {
      case 'telegram': return '📱';
      case 'scheduled': return '⏰';
      default: return '💬';
    }
  };

  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();

    if (diff < 60000) return '방금 전';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}분 전`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}시간 전`;
    return date.toLocaleDateString();
  };

  const handleFeedbackCb = useCallback(async (taskId: string, score: number) => {
    try {
      await feedbackApi.submit(taskId, score);
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    }
  }, []);

  return (
    <div className="h-full flex flex-col">
      {/* 채팅 헤더 */}
      <div className="flex items-center justify-between mb-2 sm:mb-4 pb-2 sm:pb-3 border-b border-dark-border">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          {/* 세션 선택 드롭다운 */}
          <div className="relative">
            <button
              onClick={() => {
                setShowSessions(!showSessions);
                if (!showSessions) loadSessions();
              }}
              className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-2 bg-dark-card border border-dark-border rounded-lg hover:border-zinc-600 transition-colors min-h-[44px]"
            >
              <MessageSquare size={16} />
              <span className="text-sm truncate max-w-[100px] sm:max-w-none">
                {sessionId ? `세션: ${sessionId.slice(0, 8)}...` : '새 대화'}
              </span>
              <ChevronDown size={14} className={`transition-transform flex-shrink-0 ${showSessions ? 'rotate-180' : ''}`} />
            </button>

            {showSessions && (
              <div className="absolute top-full left-0 mt-2 w-80 bg-dark-card border border-dark-border rounded-lg shadow-xl z-50 max-h-96 overflow-y-auto">
                <div className="p-2 border-b border-dark-border flex items-center justify-between">
                  <span className="text-sm text-zinc-400">채팅 히스토리</span>
                  <button
                    onClick={loadSessions}
                    className="p-1 hover:bg-zinc-800 rounded"
                    disabled={loadingSessions}
                  >
                    <RefreshCw size={14} className={loadingSessions ? 'animate-spin' : ''} />
                  </button>
                </div>

                {/* 새 대화 버튼 */}
                <button
                  onClick={() => {
                    handleClearChat();
                    setShowSessions(false);
                  }}
                  className="w-full px-3 py-2 text-left hover:bg-zinc-800 flex items-center gap-2 text-sm"
                >
                  <span>+</span>
                  <span>새 대화 시작</span>
                </button>

                {sessions.length === 0 ? (
                  <div className="p-4 text-center text-zinc-500 text-sm">
                    {loadingSessions ? '로딩 중...' : '저장된 대화가 없습니다'}
                  </div>
                ) : (
                  sessions.map((session) => (
                    <div
                      key={session.session_id}
                      className={`px-3 py-2 hover:bg-zinc-800 flex items-start gap-2 group ${
                        sessionId === session.session_id ? 'bg-zinc-800' : ''
                      }`}
                    >
                      <span className="text-lg">{getSessionIcon(session.session_type)}</span>
                      <button
                        onClick={() => loadSessionHistory(session.session_id)}
                        className="flex-1 text-left"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium truncate">
                            {session.session_type === 'telegram'
                              ? `텔레그램 (${session.chat_id})`
                              : session.session_id.slice(0, 12)}
                          </span>
                          <span className="text-xs text-zinc-500">
                            {session.message_count}개
                          </span>
                        </div>
                        <p className="text-xs text-zinc-500 truncate mt-0.5">
                          {session.preview}
                        </p>
                        <p className="text-xs text-zinc-600 mt-0.5">
                          {formatTime(session.last_message_at)}
                        </p>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteSession(session.session_id);
                        }}
                        className="p-1 opacity-0 group-hover:opacity-100 hover:text-red-400 transition-all"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          <div className="text-sm text-zinc-500">
            {messages.length > 0 && `${messages.length}개의 메시지`}
          </div>
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          {messages.length > 0 && (
            <button
              onClick={handleClearChat}
              className="flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-lg text-sm text-zinc-400 hover:text-red-400 hover:bg-red-600/10 active:bg-red-600/20 transition-colors min-h-[44px] min-w-[44px] justify-center"
              title="현재 채팅 삭제"
            >
              <Trash2 size={14} />
              <span className="hidden sm:inline">삭제</span>
            </button>
          )}

          {/* 하단 패널 토글 */}
          <button
            onClick={() => setBottomPanelOpen(!bottomPanelOpen)}
            className={`flex items-center gap-1.5 px-2 sm:px-3 py-1.5 rounded-lg text-sm transition-colors min-h-[44px] min-w-[44px] justify-center ${
              bottomPanelOpen
                ? 'bg-zinc-700 text-zinc-200'
                : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
            }`}
            title={bottomPanelOpen ? '패널 닫기' : '패널 열기'}
          >
            {bottomPanelOpen ? <PanelBottomClose size={14} /> : <PanelBottomOpen size={14} />}
          </button>
        </div>
      </div>

      {/* 채팅 영역 (수직 레이아웃) */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 메시지 목록 */}
        <div ref={scrollContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto space-y-6 pb-4 pr-2">
          {messages.length === 0 && !streamingContent && !isLoading ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center">
                <img
                  src="/jinxus-mascot.webp"
                  alt="JINXUS"
                  width={150}
                  height={150}
                  className="mx-auto mb-4 rounded-2xl"
                  loading="eager"
                  fetchPriority="high"
                />
                <h2 className="text-xl font-semibold text-zinc-400 mb-2">
                  안녕하세요,
                </h2>
                <p className="text-zinc-500">
                  무엇을 도와드릴까요?
                </p>
              </div>
            </div>
          ) : (
            <>
              {messages.map(msg => (
                <ChatMessageItem key={msg.id} message={msg} onFeedback={handleFeedbackCb} />
              ))}

              {/* 스트리밍 중인 메시지 */}
              {streamingContent && (
                <div className="flex gap-4">
                  <div className="w-10 h-10 rounded-full flex-shrink-0 overflow-hidden bg-zinc-700">
                    <img
                      src="/jinxus-mascot.webp"
                      alt="JINXUS"
                      width={40}
                      height={40}
                      className="w-full h-full object-cover object-top scale-150"
                    />
                  </div>
                  <div className="flex-1 max-w-[95%] sm:max-w-[90%] lg:max-w-[85%]">
                    <div className="inline-block p-4 rounded-2xl bg-dark-card border border-dark-border rounded-tl-none">
                      <div className="break-words">
                        <MarkdownRenderer content={streamingContent} />
                      </div>
                      <span className="inline-block w-2 h-4 bg-primary animate-pulse ml-1" />
                    </div>
                    {currentAgent && (
                      <div className="mt-2 text-xs text-primary">
                        {currentAgent} 작업 중...
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 로딩 표시 (스트리밍 시작 전) */}
              {isLoading && !streamingContent && (
                <div className="flex gap-4">
                  <div className="w-10 h-10 rounded-full flex-shrink-0 overflow-hidden bg-zinc-700">
                    <img
                      src="/jinxus-mascot.webp"
                      alt="JINXUS"
                      width={40}
                      height={40}
                      className="w-full h-full object-cover object-top scale-150"
                    />
                  </div>
                  <div className="flex items-center gap-2 text-zinc-400">
                    <Loader2 size={20} className="animate-spin" />
                    <span>{currentAgent ? `${currentAgent} 작업 중...` : '생각 중...'}</span>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* 입력 폼 */}
        <form onSubmit={handleSubmit} className="mt-2 sm:mt-4 flex-shrink-0">
          <div className="flex gap-2 sm:gap-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="메시지를 입력하세요..."
              aria-label="메시지 입력"
              disabled={isLoading}
              rows={1}
              className="flex-1 bg-dark-card border border-dark-border rounded-xl px-3 sm:px-4 py-3 focus:outline-none focus:border-primary transition-colors disabled:opacity-50 resize-none overflow-hidden min-h-[44px] max-h-[160px] text-base sm:text-sm"
              onInput={(e) => {
                const el = e.currentTarget;
                el.style.height = 'auto';
                el.style.height = Math.min(el.scrollHeight, 160) + 'px';
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e as unknown as React.FormEvent);
                }
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="px-4 sm:px-6 py-3 bg-primary hover:bg-primary-hover active:bg-primary/80 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed self-end min-w-[44px] min-h-[44px] flex items-center justify-center"
              title="전송 (Enter)"
              aria-label="메시지 전송"
            >
              <Send size={20} />
            </button>
          </div>
        </form>

        {/* 하단 패널 (VSCode 터미널 스타일) */}
        {bottomPanelOpen && (
          <div className="flex-shrink-0 flex flex-col" style={{ height: bottomPanelHeight }}>
            {/* 리사이즈 핸들 */}
            <div
              className="h-1 bg-dark-border cursor-row-resize hover:bg-primary/40 active:bg-primary/60 transition-colors flex-shrink-0"
              onMouseDown={handleDragStart}
            />

            {/* 탭 바 */}
            <div className="flex items-center justify-between bg-dark-card border-b border-dark-border flex-shrink-0">
              <div className="flex">
                <button
                  onClick={() => {
                    setBottomPanelTab('system');
                    setShowDockerLogs(true);
                    setShowThinking(false);
                  }}
                  className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium border-b-2 transition-colors ${
                    bottomPanelTab === 'system'
                      ? 'border-primary text-zinc-200 bg-dark-bg/50'
                      : 'border-transparent text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  <Terminal size={12} />
                  시스템 로그
                </button>
                <button
                  onClick={() => {
                    setBottomPanelTab('thinking');
                    setShowThinking(true);
                    setShowDockerLogs(false);
                  }}
                  className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium border-b-2 transition-colors ${
                    bottomPanelTab === 'thinking'
                      ? 'border-primary text-zinc-200 bg-dark-bg/50'
                      : 'border-transparent text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  <Brain size={12} />
                  실행 흐름
                  {isLoading && (
                    <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
                  )}
                </button>
              </div>
              <button
                onClick={() => setBottomPanelOpen(false)}
                className="p-1.5 mr-2 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded transition-colors"
                title="패널 닫기"
              >
                <ChevronDown size={14} />
              </button>
            </div>

            {/* 패널 콘텐츠 */}
            <div className="flex-1 overflow-hidden">
              {bottomPanelTab === 'system' && (
                <DockerLogPanel />
              )}
              {bottomPanelTab === 'thinking' && (
                <ThinkingPanel
                  logs={thinkingLogs}
                  isActive={isLoading}
                  taskId={currentTaskId}
                  onStop={handleStopTask}
                  messages={messages}
                  embedded
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
