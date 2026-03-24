'use client';

import { useState, useEffect, useRef } from 'react';
import { Brain, X, StopCircle, ChevronRight, ChevronDown, Wrench, Loader2, Terminal, Eye } from 'lucide-react';
import { formatTimeWithSeconds } from '@/lib/utils';
import { logsApi, type TaskLog } from '@/lib/api';
import type { ChatMessage } from '@/types';

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
  onClose?: () => void;
  messages: ChatMessage[];
  embedded?: boolean;
}

export default function ThinkingPanel({
  logs,
  isActive,
  taskId,
  onStop,
  onClose,
  messages,
  embedded = false,
}: ThinkingPanelProps) {
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [isMinimized, setIsMinimized] = useState(false);
  // 뷰 모드: 'summary' (기존 이모지 뷰) vs 'terminal' (raw 로그 뷰)
  const [viewMode, setViewMode] = useState<'summary' | 'terminal'>('terminal');

  // 메시지별 실행 흐름 상태
  const [expandedMsgId, setExpandedMsgId] = useState<string | null>(null);
  const [msgLogs, setMsgLogs] = useState<Record<string, TaskLog[]>>({});
  const [loadingMsgId, setLoadingMsgId] = useState<string | null>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // 메시지별 실행 흐름 조회
  const toggleMsgLogs = async (msgId: string) => {
    if (expandedMsgId === msgId) {
      setExpandedMsgId(null);
      return;
    }
    setExpandedMsgId(msgId);

    // 이미 캐시된 데이터가 있으면 재사용
    if (msgLogs[msgId]) return;

    setLoadingMsgId(msgId);
    try {
      const res = await logsApi.getLogsByTaskId(msgId);
      setMsgLogs(prev => ({ ...prev, [msgId]: res.logs }));
    } catch {
      setMsgLogs(prev => ({ ...prev, [msgId]: [] }));
    } finally {
      setLoadingMsgId(null);
    }
  };

  const getStepIcon = (step: string, status?: string) => {
    if (status === 'error') return '❌';
    if (step === 'agent_done' && status === 'done') return '✅';

    switch (step) {
      case 'start': return '🚀';
      case 'intake': return '📥';
      case 'classify': return '🏷️';
      case 'decompose': return '🔍';
      case 'decompose_done': return '📋';
      case 'dispatch': return '📤';
      case 'agent_started': return '🤖';
      case 'agent_done': return '✅';
      case 'agent_progress': return '🔧';
      case 'tool_graph': return '🔗';
      case 'aggregate': return '📊';
      case 'memory_write': return '💾';
      case 'check': return '🔎';
      case 'web_search': return '🌐';
      case 'thinking': return '🧠';
      case 'fallback': return '🔄';
      case 'team_progress': return '👥';
      case 'cancelled': return '⛔';
      case 'done': return '✅';
      case 'raw_log': return '>';
      default: return '💭';
    }
  };

  const getStepLabel = (step: string) => {
    switch (step) {
      case 'start': return '작업 시작';
      case 'intake': return '입력 분석';
      case 'classify': return '입력 분류';
      case 'decompose': return '작업 분해';
      case 'decompose_done': return '분해 완료';
      case 'dispatch': return '에이전트 배정';
      case 'agent_started': return '실행 중';
      case 'agent_done': return '완료';
      case 'agent_progress': return '진행 중';
      case 'tool_graph': return '도구 탐색';
      case 'aggregate': return '결과 취합';
      case 'memory_write': return '메모리 저장';
      case 'check': return '확인 중';
      case 'web_search': return '웹 검색';
      case 'thinking': return '분석 중';
      case 'fallback': return '대체 처리';
      case 'team_progress': return '전문가 팀';
      case 'cancelled': return '취소됨';
      case 'done': return '완료';
      case 'error': return '오류';
      default: return step;
    }
  };

  // assistant 메시지만 필터
  const assistantMessages = messages.filter(m => m.role === 'assistant');

  // 실시간 로그가 있거나 히스토리 메시지가 있으면 패널 표시
  const hasContent = logs.length > 0 || isActive || assistantMessages.length > 0;

  const containerClass = embedded
    ? 'w-full bg-dark-card flex flex-col h-full'
    : 'w-96 border-l border-dark-border bg-dark-card flex flex-col h-full';

  if (!hasContent) {
    return (
      <div className={containerClass}>
        {!embedded && (
          <div className="flex items-center justify-between p-3 border-b border-dark-border">
            <div className="flex items-center gap-2">
              <Brain size={18} className="text-zinc-400" />
              <span className="font-medium text-sm">실행 로그</span>
            </div>
            <button
              onClick={onClose}
              className="p-1 hover:bg-zinc-800 rounded transition-colors text-zinc-400 hover:text-white"
            >
              <X size={16} />
            </button>
          </div>
        )}
        <div className="flex-1 flex items-center justify-center p-4">
          <p className="text-xs text-zinc-500 text-center">대화를 시작하면 실행 흐름이 여기에 표시됩니다</p>
        </div>
      </div>
    );
  }

  return (
    <div className={containerClass}>
      {/* 헤더 — embedded 모드에서는 간소화 */}
      {embedded ? (
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-dark-border">
          {isActive && <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />}
          <button
            onClick={() => setViewMode(viewMode === 'terminal' ? 'summary' : 'terminal')}
            className={`p-1 rounded transition-colors text-xs ${viewMode === 'terminal' ? 'bg-zinc-700 text-green-400' : 'hover:bg-zinc-800 text-zinc-400'}`}
            title={viewMode === 'terminal' ? '요약 뷰' : '터미널 뷰'}
          >
            {viewMode === 'terminal' ? <Terminal size={12} /> : <Eye size={12} />}
          </button>
          <span className="text-[10px] text-zinc-500">{logs.length}개 이벤트</span>
        </div>
      ) : (
        <div className="flex items-center justify-between p-3 border-b border-dark-border">
          <div className="flex items-center gap-2">
            <Brain size={18} className={isActive ? 'text-primary animate-pulse' : 'text-zinc-400'} />
            <span className="font-medium text-sm">실행 로그</span>
            {isActive && (
              <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setViewMode(viewMode === 'terminal' ? 'summary' : 'terminal')}
              className={`p-1 rounded transition-colors ${viewMode === 'terminal' ? 'bg-zinc-700 text-green-400' : 'hover:bg-zinc-800 text-zinc-400'}`}
              title={viewMode === 'terminal' ? '요약 뷰' : '터미널 뷰'}
            >
              {viewMode === 'terminal' ? <Terminal size={14} /> : <Eye size={14} />}
            </button>
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
      )}

      {/* 로그 영역 */}
      {!isMinimized && (
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {/* 실시간 로그 */}
          {logs.length > 0 && (
            <>
              <div className="text-xs font-medium text-zinc-400 mb-2">
                {isActive ? '실시간' : '최근 작업'}
              </div>

              {viewMode === 'terminal' ? (
                /* 터미널 모드: raw 로그를 모노스페이스로 표시 */
                <div className="bg-black/80 rounded-lg border border-zinc-800 p-2 font-mono text-[11px] leading-relaxed max-h-[60vh] overflow-y-auto">
                  {logs.map((log) => {
                    if (log.step === 'raw_log') {
                      // Python 로거 출력 그대로
                      const line = log.detail || '';
                      const isError = line.includes('ERROR') || line.includes('FAIL');
                      const isWarn = line.includes('WARN');
                      const isToolCall = line.includes('TOOL_CALL');
                      const isToolResult = line.includes('TOOL_RESULT');
                      return (
                        <div
                          key={log.id}
                          className={`whitespace-pre-wrap break-all ${
                            isError ? 'text-red-400' :
                            isWarn ? 'text-yellow-400' :
                            isToolCall ? 'text-cyan-400' :
                            isToolResult ? 'text-blue-300' :
                            'text-green-300/80'
                          }`}
                        >
                          {line}
                        </div>
                      );
                    }
                    // manager_thinking 등 → 요약 라인으로 표시
                    const ts = log.timestamp.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
                    const prefix = log.step === 'error' ? '❌' : log.step === 'done' ? '✅' : '→';
                    const agentTag = log.agent ? `[${log.agent}] ` : '';
                    return (
                      <div
                        key={log.id}
                        className={`${
                          log.status === 'error' ? 'text-red-400' :
                          log.step === 'done' ? 'text-green-400' :
                          'text-zinc-400'
                        }`}
                      >
                        <span className="text-zinc-600">{ts}</span> {prefix} {agentTag}{getStepLabel(log.step)}{log.detail ? ` | ${log.detail}` : ''}
                      </div>
                    );
                  })}
                  {isActive && <span className="text-green-400 animate-pulse">▌</span>}
                </div>
              ) : (
                /* 요약 모드: 기존 카드 형태 (raw_log 제외) */
                <>
                  {logs.filter(l => l.step !== 'raw_log').map((log) => (
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
                        <span className="text-zinc-500">{formatTimeWithSeconds(log.timestamp)}</span>
                      </div>
                      <div className="text-zinc-200">
                        {log.agent && (
                          <span className="text-primary font-medium">{log.agent} </span>
                        )}
                        <span>{getStepLabel(log.step)}</span>
                        {log.detail && (
                          <p className="text-zinc-400 mt-0.5 break-words">{log.detail}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </>
              )}
            </>
          )}

          {/* 메시지별 실행 흐름 히스토리 */}
          {assistantMessages.length > 0 && (
            <>
              {(logs.length > 0 || isActive) && (
                <div className="border-t border-dark-border my-2" />
              )}
              <div className="text-xs font-medium text-zinc-400 mb-2">대화 이력</div>
              {assistantMessages.map((msg, idx) => (
                <div key={msg.id} className="text-xs">
                  {/* 메시지 요약 (클릭하여 펼치기) */}
                  <button
                    onClick={() => toggleMsgLogs(msg.id)}
                    className={`w-full text-left p-2 rounded-lg transition-colors ${
                      expandedMsgId === msg.id
                        ? 'bg-primary/10 border border-primary/30'
                        : 'bg-zinc-800/50 hover:bg-zinc-800'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <ChevronRight
                        size={12}
                        className={`transition-transform flex-shrink-0 ${
                          expandedMsgId === msg.id ? 'rotate-90' : ''
                        }`}
                      />
                      <span className="text-zinc-300 truncate flex-1">
                        #{assistantMessages.length - idx} {msg.content.slice(0, 40)}{msg.content.length > 40 ? '...' : ''}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-1 ml-5">
                      <span className="text-zinc-500">
                        {msg.timestamp.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Seoul' })}
                      </span>
                      {msg.agentsUsed && msg.agentsUsed.length > 0 && (
                        <span className="text-primary">{msg.agentsUsed.join(', ')}</span>
                      )}
                    </div>
                  </button>

                  {/* 실행 흐름 상세 */}
                  {expandedMsgId === msg.id && (
                    <div className="mt-1 ml-3 pl-2 border-l-2 border-zinc-700 space-y-1.5">
                      {loadingMsgId === msg.id ? (
                        <div className="flex items-center gap-2 text-zinc-400 p-1">
                          <Loader2 size={12} className="animate-spin" />
                          <span>조회 중...</span>
                        </div>
                      ) : !msgLogs[msg.id] || msgLogs[msg.id].length === 0 ? (
                        <div className="text-zinc-500 p-1">로그 없음</div>
                      ) : (
                        <>
                          {msgLogs[msg.id].map((log) => (
                            <div key={log.id} className="p-1.5 rounded bg-zinc-900/50">
                              <div className="flex items-center gap-1.5">
                                <span>{log.success ? '✅' : '❌'}</span>
                                <span className="text-primary font-medium">{log.agent_name}</span>
                                <span className="text-zinc-500">
                                  {(log.duration_ms / 1000).toFixed(1)}s
                                </span>
                                <span className={`${
                                  log.success_score >= 0.7 ? 'text-green-400' : log.success_score >= 0.4 ? 'text-yellow-400' : 'text-red-400'
                                }`}>
                                  {log.success_score.toFixed(1)}
                                </span>
                              </div>
                              <div className="text-zinc-400 mt-0.5 truncate">
                                {log.instruction}
                              </div>
                              {log.tool_calls && log.tool_calls.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-1">
                                  {log.tool_calls.map((tool, ti) => (
                                    <span
                                      key={ti}
                                      className={`inline-flex items-center gap-0.5 px-1 py-0.5 rounded ${
                                        tool.startsWith('mcp_')
                                          ? 'bg-blue-500/10 text-blue-400'
                                          : 'bg-zinc-800 text-zinc-400'
                                      }`}
                                    >
                                      <Wrench size={9} />
                                      {tool}
                                    </span>
                                  ))}
                                </div>
                              )}
                              {log.failure_reason && (
                                <div className="text-red-400 mt-0.5">{log.failure_reason}</div>
                              )}
                            </div>
                          ))}
                          <div className="text-zinc-500 p-1 border-t border-zinc-800">
                            총 {(msgLogs[msg.id].reduce((s, l) => s + l.duration_ms, 0) / 1000).toFixed(1)}s | {msgLogs[msg.id].length}개 에이전트
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </>
          )}

          <div ref={logsEndRef} />
        </div>
      )}

      {/* 중지 버튼 - taskId 없어도 isActive면 표시 */}
      {isActive && (
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
