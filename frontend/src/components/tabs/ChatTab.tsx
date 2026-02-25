'use client';

import { useState, useRef, useEffect } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { chatApi, feedbackApi } from '@/lib/api';
import { Send, ThumbsUp, ThumbsDown, Bot, User, Loader2 } from 'lucide-react';
import type { ChatMessage } from '@/types';

export default function ChatTab() {
  const { messages, addMessage, isLoading, setLoading, sessionId, setSessionId } = useAppStore();
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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

      addMessage(assistantMessage);
    } catch (error) {
      const errorMessage: ChatMessage = {
        id: Date.now().toString(),
        role: 'assistant',
        content: `죄송합니다 주인님, 오류가 발생했습니다: ${error instanceof Error ? error.message : '알 수 없는 오류'}`,
        timestamp: new Date(),
        success: false,
      };
      addMessage(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleFeedback = async (taskId: string, score: number) => {
    try {
      await feedbackApi.submit(taskId, score);
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    }
  };

  const renderMessage = (message: ChatMessage) => {
    const isUser = message.role === 'user';

    return (
      <div
        key={message.id}
        className={`flex gap-4 ${isUser ? 'flex-row-reverse' : ''}`}
      >
        {/* 아바타 */}
        <div
          className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
            isUser ? 'bg-primary' : 'bg-zinc-700'
          }`}
        >
          {isUser ? <User size={20} /> : <Bot size={20} />}
        </div>

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
      {/* 메시지 목록 */}
      <div className="flex-1 overflow-y-auto space-y-6 pb-4">
        {messages.length === 0 ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-center">
              <Bot size={64} className="mx-auto text-zinc-600 mb-4" />
              <h2 className="text-xl font-semibold text-zinc-400 mb-2">
                안녕하세요, 주인님
              </h2>
              <p className="text-zinc-500">
                무엇을 도와드릴까요?
              </p>
            </div>
          </div>
        ) : (
          messages.map(renderMessage)
        )}
        {isLoading && (
          <div className="flex gap-4">
            <div className="w-10 h-10 rounded-full bg-zinc-700 flex items-center justify-center">
              <Bot size={20} />
            </div>
            <div className="flex items-center gap-2 text-zinc-400">
              <Loader2 size={20} className="animate-spin" />
              <span>생각 중...</span>
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
          Ctrl+Enter로 전송 | 에이전트가 자동으로 선택됩니다
        </p>
      </form>
    </div>
  );
}
