'use client';

import { useState, useEffect, useRef } from 'react';
import { Brain, X, StopCircle, ChevronRight, ChevronDown } from 'lucide-react';

export interface ThinkingLog {
  id: string;
  timestamp: Date;
  step: string;
  detail?: string;
  agent?: string;
  status?: 'running' | 'done' | 'error';
}

interface ThinkingPanelProps {
  logs: ThinkingLog[];
  isActive: boolean;
  taskId: string | null;
  onStop: () => void;
  onClose: () => void;
}

export default function ThinkingPanel({
  logs,
  isActive,
  taskId,
  onStop,
  onClose,
}: ThinkingPanelProps) {
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [isMinimized, setIsMinimized] = useState(false);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('ko-KR', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const getStepIcon = (step: string, status?: string) => {
    if (status === 'error') return '❌';
    if (status === 'done') return '✅';

    switch (step) {
      case 'start': return '🚀';
      case 'intake': return '📥';
      case 'decompose': return '🔍';
      case 'dispatch': return '📤';
      case 'agent_started': return '🤖';
      case 'agent_done': return '✓';
      case 'aggregate': return '📊';
      case 'memory_write': return '💾';
      case 'check': return '🔎';
      case 'web_search': return '🌐';
      case 'thinking': return '🧠';
      case 'fallback': return '🔄';
      case 'cancelled': return '⛔';
      default: return '💭';
    }
  };

  const getStepLabel = (step: string) => {
    switch (step) {
      case 'start': return '작업 시작';
      case 'intake': return '입력 분석';
      case 'decompose': return '작업 분해';
      case 'dispatch': return '에이전트 배정';
      case 'agent_started': return '에이전트 시작';
      case 'agent_done': return '에이전트 완료';
      case 'aggregate': return '결과 취합';
      case 'memory_write': return '메모리 저장';
      case 'check': return '확인 중';
      case 'web_search': return '웹 검색';
      case 'thinking': return '분석 중';
      case 'fallback': return '대체 처리';
      case 'cancelled': return '취소됨';
      case 'done': return '완료';
      case 'error': return '오류';
      default: return step;
    }
  };

  if (logs.length === 0 && !isActive) {
    return null;
  }

  return (
    <div className="w-72 border-l border-dark-border bg-dark-card flex flex-col h-full">
      {/* 헤더 */}
      <div className="flex items-center justify-between p-3 border-b border-dark-border">
        <div className="flex items-center gap-2">
          <Brain size={18} className={isActive ? 'text-primary animate-pulse' : 'text-zinc-400'} />
          <span className="font-medium text-sm">Thinking Log</span>
          {isActive && (
            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsMinimized(!isMinimized)}
            className="p-1 hover:bg-zinc-800 rounded transition-colors"
          >
            {isMinimized ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
          </button>
          <button
            onClick={onClose}
            className="p-1 hover:bg-zinc-800 rounded transition-colors text-zinc-400 hover:text-white"
          >
            <X size={16} />
          </button>
        </div>
      </div>

      {/* 로그 영역 */}
      {!isMinimized && (
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {logs.map((log) => (
            <div
              key={log.id}
              className={`text-xs p-2 rounded-lg ${
                log.status === 'running'
                  ? 'bg-primary/10 border border-primary/30'
                  : log.status === 'error'
                  ? 'bg-red-500/10 border border-red-500/30'
                  : 'bg-zinc-800/50'
              }`}
            >
              <div className="flex items-center gap-2 text-zinc-400 mb-1">
                <span>{getStepIcon(log.step, log.status)}</span>
                <span className="text-zinc-500">{formatTime(log.timestamp)}</span>
              </div>
              <div className="text-zinc-200">
                {log.agent ? (
                  <span className="text-primary">{log.agent}</span>
                ) : (
                  getStepLabel(log.step)
                )}
                {log.detail && (
                  <span className="text-zinc-400 ml-1">- {log.detail}</span>
                )}
              </div>
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      )}

      {/* 중지 버튼 */}
      {isActive && taskId && (
        <div className="p-3 border-t border-dark-border">
          <button
            onClick={onStop}
            className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors text-sm font-medium"
          >
            <StopCircle size={16} />
            작업 중지
          </button>
        </div>
      )}

      {/* 완료/에러 상태 */}
      {!isActive && logs.length > 0 && (
        <div className="p-3 border-t border-dark-border text-center text-xs text-zinc-500">
          {logs[logs.length - 1]?.status === 'error' ? '작업 실패' : '작업 완료'}
        </div>
      )}
    </div>
  );
}
