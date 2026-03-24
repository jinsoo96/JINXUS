'use client';

import { useState } from 'react';
import { Loader2, AlertCircle, Wrench, ScrollText, ChevronDown, ChevronUp, CheckCircle, XCircle, Clock } from 'lucide-react';
import { type AgentRuntimeStatus, logsApi, type TaskLog } from '@/lib/api';
import type { AgentInfo } from '@/types';
import { formatTimeWithSeconds } from '@/lib/utils';
import { getDisplayName, getRole, getPersona } from '@/lib/personas';

interface AgentCardProps {
  agent: AgentInfo;
  runtime?: AgentRuntimeStatus | null;
  onSelect?: () => void;
  selected?: boolean;
}

export default function AgentCard({ agent, runtime, onSelect, selected }: AgentCardProps) {
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  const persona = getPersona(agent.name);

  const getStatusColor = () => {
    if (!runtime) return 'bg-zinc-500';
    switch (runtime.status) {
      case 'working': return 'bg-blue-500';
      case 'error': return 'bg-red-500';
      default: return 'bg-green-500';
    }
  };

  const getStatusBgColor = () => {
    if (!runtime) return 'bg-zinc-500/20';
    switch (runtime.status) {
      case 'working': return 'bg-blue-500/20';
      case 'error': return 'bg-red-500/20';
      default: return 'bg-green-500/20';
    }
  };

  const handleToggleLogs = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (showLogs) { setShowLogs(false); return; }
    setShowLogs(true);
    if (logs.length > 0) return;
    setLogsLoading(true);
    try {
      const res = await logsApi.getLogs(agent.name, 10, 0);
      setLogs(res.logs);
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  return (
    <div
      onClick={onSelect}
      role="button"
      aria-label={`${getDisplayName(agent.name)} 에이전트 상태`}
      className={`rounded-xl border transition-all cursor-pointer ${
        selected
          ? 'bg-primary/10 border-primary'
          : 'bg-dark-card border-dark-border hover:border-zinc-600'
      }`}
    >
      <div className="p-4">
        {/* 헤더 */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className={`w-9 h-9 rounded-lg flex items-center justify-center text-xl ${getStatusBgColor()}`}>
              {persona?.emoji ?? '🤖'}
            </div>
            <div>
              <h3 className="font-semibold text-white text-sm">{getDisplayName(agent.name)}</h3>
              <p className="text-[11px] text-zinc-500">{getRole(agent.name)}</p>
            </div>
          </div>
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${getStatusColor()} ${runtime?.status === 'working' ? 'shadow-[0_0_5px_rgba(59,130,246,0.7)] animate-pulse' : ''}`} />
        </div>

        {/* 작업 중 */}
        {runtime?.status === 'working' && (
          <div className="mb-3 p-2 bg-blue-500/10 rounded-lg border border-blue-500/20">
            <div className="flex items-center gap-1.5 mb-0.5">
              <Loader2 size={10} className="animate-spin text-blue-400 flex-shrink-0" />
              <p className="text-xs text-blue-300 truncate">{runtime.current_task || '작업 중...'}</p>
            </div>
            {runtime.current_node && (
              <p className="text-[10px] text-blue-400/60 pl-4 truncate">단계: {runtime.current_node}</p>
            )}
          </div>
        )}

        {/* 에러 */}
        {runtime?.status === 'error' && (
          <div className="mb-3 p-2 bg-red-500/10 rounded-lg border border-red-500/20">
            <div className="flex items-center gap-1.5">
              <AlertCircle size={10} className="text-red-400 flex-shrink-0" />
              <p className="text-xs text-red-300 truncate">{runtime.error_message || '오류 발생'}</p>
            </div>
          </div>
        )}

        {/* 사용 중 도구 */}
        {runtime?.current_tools && runtime.current_tools.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-1">
            <Wrench size={10} className="text-zinc-500 mt-0.5" />
            {runtime.current_tools.map((tool) => (
              <span key={tool} className="px-1.5 py-0.5 text-[10px] bg-zinc-700/60 rounded text-zinc-300">
                {tool}
              </span>
            ))}
          </div>
        )}

        {/* 성능 지표 */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="p-2 bg-dark-bg/80 rounded-lg">
            <p className="text-zinc-500">성공률</p>
            <p className={`font-semibold ${
              agent.success_rate >= 0.8 ? 'text-green-400' :
              agent.success_rate >= 0.5 ? 'text-amber-400' : 'text-red-400'
            }`}>
              {(agent.success_rate * 100).toFixed(0)}%
            </p>
          </div>
          <div className="p-2 bg-dark-bg/80 rounded-lg">
            <p className="text-zinc-500">총 작업</p>
            <p className="text-white font-semibold">{agent.total_tasks}</p>
          </div>
        </div>
      </div>

      {/* 로그 토글 */}
      <button
        onClick={handleToggleLogs}
        className={`w-full flex items-center justify-between px-4 py-2 text-xs border-t transition-colors ${
          showLogs
            ? 'border-primary/30 text-primary bg-primary/5'
            : 'border-dark-border text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50'
        }`}
      >
        <span className="flex items-center gap-1.5"><ScrollText size={12} />최근 로그</span>
        {showLogs ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {showLogs && (
        <div className="border-t border-dark-border bg-zinc-900/50 rounded-b-xl max-h-48 overflow-y-auto">
          {logsLoading ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 size={16} className="animate-spin text-zinc-500" />
            </div>
          ) : logs.length === 0 ? (
            <p className="text-xs text-zinc-500 text-center py-4">로그 없음</p>
          ) : (
            <div className="divide-y divide-zinc-800/50">
              {logs.map((log) => (
                <div key={log.id} className="px-3 py-2 text-xs">
                  <div className="flex items-center gap-2 mb-0.5">
                    {log.success
                      ? <CheckCircle size={11} className="text-green-400 flex-shrink-0" />
                      : <XCircle size={11} className="text-red-400 flex-shrink-0" />
                    }
                    <span className="text-zinc-400 font-mono">{formatTimeWithSeconds(log.created_at)}</span>
                    <span className="flex items-center gap-1 text-zinc-600 ml-auto">
                      <Clock size={10} />
                      {log.duration_ms < 1000 ? `${log.duration_ms}ms` : `${(log.duration_ms / 1000).toFixed(1)}s`}
                    </span>
                  </div>
                  <p className="text-zinc-400 truncate pl-4">{log.instruction}</p>
                  {log.failure_reason && (
                    <p className="text-red-400/80 truncate pl-4 mt-0.5">{log.failure_reason}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
