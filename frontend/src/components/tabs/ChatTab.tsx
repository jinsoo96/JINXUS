'use client';

import { useState, useRef, useEffect } from 'react';
import Image from 'next/image';
import { useAppStore } from '@/store/useAppStore';
import { chatApi, feedbackApi, type ChatSession, type SSEEvent } from '@/lib/api';
import {
  Send, ThumbsUp, ThumbsDown, User, Loader2, Trash2,
  MessageSquare, Clock, Globe, RefreshCw, ChevronDown
} from 'lucide-react';
import type { ChatMessage } from '@/types';

export default function ChatTab() {
  const { messages, addMessage, isLoading, setLoading, sessionId, setSessionId, clearMessages } = useAppStore();
  const [input, setInput] = useState('');
  const [streamingContent, setStreamingContent] = useState('');
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [showSessions, setShowSessions] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 세션 목록 로드
  const loadSessions = async () => {
    setLoadingSessions(true);
    try {
      const response = await chatApi.getSessions();
      setSessions(response.sessions);
    } catch (error) {
      console.error('Failed to load sessions:', error);
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
    }
  };

  const handleClearChat = () => {
    if (messages.length === 0) return;
    if (confirm('현재 채팅을 삭제하시겠습니까?')) {
      clearMessages();
      setSessionId('');
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent]);

  // SSE 스트리밍 전송
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    addMessage(userMessage);
    setInput('');
    setLoading(true);
    setStreamingContent('');
    setCurrentAgent(null);

    let fullResponse = '';
    let agentsUsed: string[] = [];
    let taskId = '';
    let newSessionId = sessionId;

    try {
      await chatApi.streamMessage(
        userMessage.content,
        sessionId || undefined,
        (event: SSEEvent) => {
          switch (event.event) {
            case 'start':
              taskId = event.data.task_id || '';
              if (event.data.session_id && !sessionId) {
                newSessionId = event.data.session_id;
                setSessionId(event.data.session_id);
              }
              break;
            case 'agent_started':
              setCurrentAgent(event.data.agent || null);
              break;
            case 'agent_done':
              if (event.data.agent) {
                agentsUsed.push(event.data.agent);
              }
              setCurrentAgent(null);
              break;
            case 'message':
              // content 필드에 청크 데이터가 있음
              if (event.data.content) {
                fullResponse += event.data.content;
                setStreamingContent(fullResponse);
              }
              break;
            case 'done':
              fullResponse = event.data.response || fullResponse;
              agentsUsed = event.data.agents_used || agentsUsed;
              break;
            case 'error':
              throw new Error(event.data.error || 'Unknown error');
          }
        },
        (error) => {
          throw error;
        }
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

    } catch (error) {
      // 스트리밍 실패 시 동기 API로 폴백
      console.warn('Streaming failed, falling back to sync:', error);

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
        const errorMessage: ChatMessage = {
          id: Date.now().toString(),
          role: 'assistant',
          content: `죄송합니다 주인님, 오류가 발생했습니다: ${syncError instanceof Error ? syncError.message : '알 수 없는 오류'}`,
          timestamp: new Date(),
          success: false,
        };
        setStreamingContent('');
        addMessage(errorMessage);
      }
    } finally {
      setLoading(false);
      setCurrentAgent(null);
    }
  };

  const handleFeedback = async (taskId: string, score: number) => {
    try {
      await feedbackApi.submit(taskId, score);
    } catch (error) {
      console.error('Failed to submit feedback:', error);
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

  const renderMessage = (message: ChatMessage) => {
    const isUser = message.role === 'user';

    return (
      <div
        key={message.id}
        className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''}`}
      >
        {/* 아바타 */}
        {isUser ? (
          <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 bg-primary">
            <User size={20} />
          </div>
        ) : (
          <div className="w-10 h-10 rounded-full flex-shrink-0 overflow-hidden bg-zinc-700">
            <Image
              src="/jinxus-mascot.png"
              alt="JINXUS"
              width={40}
              height={40}
              className="w-full h-full object-cover object-top scale-150"
            />
          </div>
        )}

        {/* 메시지 내용 */}
        <div
          className={`flex-1 max-w-[80%] ${isUser ? 'text-right' : ''}`}
        >
          <div
            className={`inline-block p-4 rounded-2xl ${
              isUser
                ? 'bg-primary text-white rounded-tr-none'
                : 'bg-dark-card border border-dark-border rounded-tl-none'
            }`}
          >
            <div className="markdown whitespace-pre-wrap">{message.content}</div>
          </div>

          {/* 메타 정보 */}
          <div
            className={`mt-2 flex items-center gap-2 text-xs text-zinc-500 ${
              isUser ? 'justify-end' : ''
            }`}
          >
            <span>{message.timestamp.toLocaleTimeString()}</span>
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
                onClick={() => handleFeedback(message.id, 5)}
                className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 hover:text-green-400 transition-colors"
                title="좋아요"
              >
                <ThumbsUp size={16} />
              </button>
              <button
                onClick={() => handleFeedback(message.id, 1)}
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
  };

  return (
    <div className="h-full flex flex-col">
      {/* 채팅 헤더 */}
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-dark-border">
        <div className="flex items-center gap-3">
          {/* 세션 선택 드롭다운 */}
          <div className="relative">
            <button
              onClick={() => {
                setShowSessions(!showSessions);
                if (!showSessions) loadSessions();
              }}
              className="flex items-center gap-2 px-3 py-2 bg-dark-card border border-dark-border rounded-lg hover:border-zinc-600 transition-colors"
            >
              <MessageSquare size={16} />
              <span className="text-sm">
                {sessionId ? `세션: ${sessionId.slice(0, 8)}...` : '새 대화'}
              </span>
              <ChevronDown size={14} className={`transition-transform ${showSessions ? 'rotate-180' : ''}`} />
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
                    clearMessages();
                    setSessionId('');
                    setShowSessions(false);
                  }}
                  className="w-full px-3 py-2 text-left hover:bg-zinc-800 flex items-center gap-2 text-sm"
                >
                  <span>➕</span>
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

        {messages.length > 0 && (
          <button
            onClick={handleClearChat}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm text-zinc-400 hover:text-red-400 hover:bg-red-600/10 transition-colors"
            title="현재 채팅 삭제"
          >
            <Trash2 size={14} />
            삭제
          </button>
        )}
      </div>

      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto space-y-6 pb-4">
        {messages.length === 0 && !streamingContent ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <Image
                src="/jinxus-mascot.png"
                alt="JINXUS"
                width={150}
                height={150}
                className="mx-auto mb-4 rounded-2xl"
              />
              <h2 className="text-xl font-semibold text-zinc-400 mb-2">
                안녕하세요, 주인님
              </h2>
              <p className="text-zinc-500">
                무엇을 도와드릴까요?
              </p>
            </div>
          </div>
        ) : (
          <>
            {messages.map(renderMessage)}

            {/* 스트리밍 중인 메시지 */}
            {streamingContent && (
              <div className="flex gap-4">
                <div className="w-10 h-10 rounded-full flex-shrink-0 overflow-hidden bg-zinc-700">
                  <Image
                    src="/jinxus-mascot.png"
                    alt="JINXUS"
                    width={40}
                    height={40}
                    className="w-full h-full object-cover object-top scale-150"
                  />
                </div>
                <div className="flex-1 max-w-[80%]">
                  <div className="inline-block p-4 rounded-2xl bg-dark-card border border-dark-border rounded-tl-none">
                    <div className="markdown whitespace-pre-wrap">{streamingContent}</div>
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
          </>
        )}

        {isLoading && !streamingContent && (
          <div className="flex gap-4">
            <div className="w-10 h-10 rounded-full flex-shrink-0 overflow-hidden bg-zinc-700">
              <Image
                src="/jinxus-mascot.png"
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
        <div ref={messagesEndRef} />
      </div>

      {/* 입력 폼 */}
      <form onSubmit={handleSubmit} className="mt-4">
        <div className="flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="메시지를 입력하세요..."
            disabled={isLoading}
            className="flex-1 bg-dark-card border border-dark-border rounded-xl px-4 py-3 focus:outline-none focus:border-primary transition-colors disabled:opacity-50"
            onKeyDown={(e) => {
              if (e.key === 'Enter' && e.ctrlKey) {
                handleSubmit(e);
              }
            }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isLoading}
            className="px-6 py-3 bg-primary hover:bg-primary-hover rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send size={20} />
          </button>
        </div>
        <p className="mt-2 text-xs text-zinc-500 text-center">
          Ctrl+Enter로 전송 | 실시간 스트리밍 | 텔레그램 대화도 여기서 확인
        </p>
      </form>
    </div>
  );
}
