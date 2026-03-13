'use client';

import { useState, useEffect, useRef } from 'react';
import { CheckCircle, XCircle, Clock, RefreshCw, Filter, Trash2, CheckSquare, Square, AlertTriangle, ChevronDown, ChevronUp, Wrench } from 'lucide-react';
import toast from 'react-hot-toast';
import { logsApi, type TaskLog } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { formatTimeWithSeconds, formatDateTime } from '@/lib/utils';

export default function LogsTab() {
  const { agents, loadAgents, logsAgentFilter, setLogsAgentFilter } = useAppStore();
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>(logsAgentFilter || 'all');
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'failure'>('all');
  const [toolFilter, setToolFilter] = useState<'all' | 'with_tools' | 'no_tools'>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showCleanupModal, setShowCleanupModal] = useState(false);
  const [cleanupDays, setCleanupDays] = useState(7);
  const [keepFailures, setKeepFailures] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastActivityRef = useRef<number>(Date.now());

  useEffect(() => {
    if (agents.length === 0) loadAgents();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // store logsAgentFilter 변경 시 동기화 (Sidebar 클릭 등)
  useEffect(() => {
    if (logsAgentFilter && logsAgentFilter !== filter) {
      setFilter(logsAgentFilter);
    }
  }, [logsAgentFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const startPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    // 활성(최근 30초 내 로그 갱신): 500ms, 유휴: 5s
    const tick = async () => {
      if (document.visibilityState !== 'visible') return;
      const idle = Date.now() - lastActivityRef.current > 30_000;
      await fetchLogs(false);
      pollRef.current = setTimeout(tick, idle ? 5000 : 2000);
    };
    pollRef.current = setTimeout(tick, 2000);
  };

  useEffect(() => {
    startPolling();
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchLogs = async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    try {
      const agentName = filter !== 'all' ? filter : undefined;
      const data = await logsApi.getLogs(agentName, 50);
      setLogs(prev => {
        // 새 로그 감지 시 활성 타이머 리셋
        if (prev.length === 0 || prev[0]?.id !== data.logs[0]?.id) {
          lastActivityRef.current = Date.now();
        }
        return data.logs;
      });
      setTotal(data.total);
      if (showSpinner) setSelectedIds(new Set());
    } catch (error) {
      console.error('Failed to fetch logs:', error);
    } finally {
      if (showSpinner) setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  // 개별 삭제
  const handleDeleteOne = async (logId: string) => {
    if (!confirm('이 로그를 삭제하시겠습니까?')) return;

    try {
      await logsApi.deleteLog(logId);
      await fetchLogs();
    } catch (error) {
      console.error('Failed to delete log:', error);
    }
  };

  // 선택 삭제
  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`선택한 ${selectedIds.size}개 로그를 삭제하시겠습니까?`)) return;

    try {
      await logsApi.deleteLogs(Array.from(selectedIds));
      await fetchLogs();
    } catch (error) {
      console.error('Failed to delete logs:', error);
    }
  };

  // 오래된 로그 정리
  const handleCleanup = async () => {
    try {
      const data = await logsApi.cleanup(cleanupDays, keepFailures);
      toast.success(`${data.deleted_count}개의 로그가 정리되었습니다.`);
      setShowCleanupModal(false);
      await fetchLogs();
    } catch (error) {
      console.error('Failed to cleanup logs:', error);
    }
  };

  // 전체 선택/해제
  const handleSelectAll = () => {
    if (selectedIds.size === displayedLogs.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(displayedLogs.map((log) => log.id)));
    }
  };

  // 개별 선택
  const toggleSelect = (logId: string) => {
    const newSet = new Set(selectedIds);
    if (newSet.has(logId)) {
      newSet.delete(logId);
    } else {
      newSet.add(logId);
    }
    setSelectedIds(newSet);
  };

  const toggleExpand = (id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const agentNames = ['all', ...agents.map(a => a.name)];

  const handleFilterChange = (val: string) => {
    setFilter(val);
    setLogsAgentFilter(val);
  };

  const displayedLogs = logs
    .filter(l => statusFilter === 'all' ? true : statusFilter === 'success' ? l.success : !l.success)
    .filter(l => toolFilter === 'all' ? true : toolFilter === 'with_tools' ? (l.tool_calls && l.tool_calls.length > 0) : !(l.tool_calls && l.tool_calls.length > 0));

  return (
    <div className="h-full flex flex-col">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold">작업 로그</h2>
          <p className="text-sm text-zinc-500">총 {total}개의 작업 기록</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap justify-end">
          {/* 상태 필터 토글 */}
          <div className="flex bg-zinc-900 rounded-lg p-0.5 text-xs">
            {([
              { id: 'all', label: '전체' },
              { id: 'success', label: '✓ 성공' },
              { id: 'failure', label: '✗ 실패' },
            ] as const).map(s => (
              <button
                key={s.id}
                onClick={() => setStatusFilter(s.id)}
                className={`px-3 py-1.5 rounded-md transition-colors ${
                  statusFilter === s.id
                    ? s.id === 'success' ? 'bg-green-600/30 text-green-400'
                      : s.id === 'failure' ? 'bg-red-600/30 text-red-400'
                      : 'bg-zinc-700 text-white'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* 도구 필터 */}
          <div className="flex bg-zinc-900 rounded-lg p-0.5 text-xs">
            {([
              { id: 'all', label: '전체' },
              { id: 'with_tools', label: '🔧 도구 사용' },
              { id: 'no_tools', label: '💬 직접 응답' },
            ] as const).map(t => (
              <button
                key={t.id}
                onClick={() => setToolFilter(t.id)}
                className={`px-2.5 py-1.5 rounded-md transition-colors ${
                  toolFilter === t.id ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* 에이전트 필터 */}
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-zinc-500" />
            <select
              value={filter}
              onChange={(e) => handleFilterChange(e.target.value)}
              className="bg-dark-card border border-dark-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-primary"
            >
              {agentNames.map((agent) => (
                <option key={agent} value={agent}>
                  {agent === 'all' ? '전체 에이전트' : agent}
                </option>
              ))}
            </select>
          </div>

          {/* 정리 버튼 */}
          <button
            onClick={() => setShowCleanupModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-yellow-600/20 text-yellow-400 hover:bg-yellow-600/30 transition-colors text-sm"
            title="오래된 로그 정리"
          >
            <AlertTriangle size={14} />
            정리
          </button>

          {/* 선택 삭제 버튼 */}
          {selectedIds.size > 0 && (
            <button
              onClick={handleDeleteSelected}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-600/20 text-red-400 hover:bg-red-600/30 transition-colors text-sm"
            >
              <Trash2 size={14} />
              {selectedIds.size}개 삭제
            </button>
          )}

          {/* 새로고침 */}
          <button
            onClick={() => fetchLogs()}
            disabled={loading}
            className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
            title="새로고침"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* 전체 선택 */}
      {displayedLogs.length > 0 && (
        <div className="flex items-center gap-2 mb-3 text-sm text-zinc-400">
          <button
            onClick={handleSelectAll}
            className="flex items-center gap-1.5 hover:text-zinc-200 transition-colors"
          >
            {selectedIds.size === displayedLogs.length ? (
              <CheckSquare size={16} className="text-primary" />
            ) : (
              <Square size={16} />
            )}
            전체 선택
          </button>
          {selectedIds.size > 0 && (
            <span className="text-zinc-500">({selectedIds.size}개 선택됨)</span>
          )}
        </div>
      )}

      {/* 로그 목록 */}
      <div className="flex-1 overflow-y-auto space-y-3">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <RefreshCw size={24} className="animate-spin text-zinc-500" />
          </div>
        ) : displayedLogs.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-zinc-500">
            {logs.length > 0 ? '해당 조건의 로그가 없습니다' : '작업 기록이 없습니다'}
          </div>
        ) : (
          displayedLogs.map((log) => {
            const isExpanded = expandedIds.has(log.id);
            const hasDetails = (log.tool_calls && log.tool_calls.length > 0) || log.output;

            return (
              <div
                key={log.id}
                className={`bg-dark-card border rounded-xl transition-colors ${
                  selectedIds.has(log.id)
                    ? 'border-primary bg-primary/5'
                    : 'border-dark-border hover:border-zinc-600'
                }`}
              >
                <div className="flex items-start justify-between gap-4 p-4">
                  {/* 체크박스 */}
                  <button
                    onClick={() => toggleSelect(log.id)}
                    className="flex-shrink-0 mt-0.5 text-zinc-500 hover:text-zinc-300"
                  >
                    {selectedIds.has(log.id) ? (
                      <CheckSquare size={18} className="text-primary" />
                    ) : (
                      <Square size={18} />
                    )}
                  </button>

                  {/* 상태 아이콘 */}
                  <div className="flex-shrink-0 mt-0.5">
                    {log.success ? (
                      <CheckCircle size={20} className="text-green-400" />
                    ) : (
                      <XCircle size={20} className="text-red-400" />
                    )}
                  </div>

                  {/* 내용 */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-medium px-2 py-0.5 rounded bg-violet-600/20 text-violet-400">
                        {log.agent_name}
                      </span>
                      <span
                        className="text-xs text-zinc-500 font-mono"
                        title={formatDateTime(log.created_at)}
                      >
                        {formatTimeWithSeconds(log.created_at)}
                      </span>
                      {log.tool_calls && log.tool_calls.length > 0 && (
                        <span className="flex items-center gap-1 text-xs text-blue-400">
                          <Wrench size={11} />
                          {log.tool_calls.length}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-zinc-300 line-clamp-2">
                      {log.instruction}
                    </p>
                    {log.failure_reason && (
                      <p className="mt-1 text-xs text-red-400 line-clamp-1">
                        실패: {log.failure_reason}
                      </p>
                    )}
                  </div>

                  {/* 메타 정보 + 삭제 */}
                  <div className="flex-shrink-0 text-right">
                    <div className="flex items-center justify-end gap-1.5 flex-wrap mb-1">
                      <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
                        <Clock size={11} />
                        {formatDuration(log.duration_ms)}
                      </span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        log.success_score >= 0.8
                          ? 'bg-green-600/15 text-green-400'
                          : log.success_score >= 0.5
                          ? 'bg-yellow-600/15 text-yellow-400'
                          : 'bg-red-600/15 text-red-400'
                      }`}>
                        {(log.success_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="flex items-center justify-end gap-1 mt-1">
                      {hasDetails && (
                        <button
                          onClick={() => toggleExpand(log.id)}
                          className="p-1 rounded hover:bg-zinc-700 text-zinc-500 hover:text-zinc-300 transition-colors"
                          title="상세 보기"
                        >
                          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                      )}
                      <button
                        onClick={() => handleDeleteOne(log.id)}
                        className="p-1 rounded hover:bg-red-600/20 text-zinc-500 hover:text-red-400 transition-colors"
                        title="삭제"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                </div>

                {/* 상세 패널 */}
                {isExpanded && hasDetails && (
                  <div className="px-4 pb-4 pt-0 border-t border-dark-border mt-0">
                    <div className="pt-3 space-y-3">
                      {/* 도구 호출 이력 */}
                      {log.tool_calls && log.tool_calls.length > 0 && (
                        <div>
                          <p className="text-xs font-medium text-zinc-500 uppercase mb-2 flex items-center gap-1.5">
                            <Wrench size={12} />
                            호출된 도구 ({log.tool_calls.length})
                          </p>
                          <div className="flex flex-wrap gap-1.5">
                            {log.tool_calls.map((tool, i) => (
                              <span
                                key={i}
                                className={`text-xs px-2 py-1 rounded-md font-mono ${
                                  tool.startsWith('mcp__')
                                    ? 'bg-blue-600/15 text-blue-400 border border-blue-600/30'
                                    : 'bg-zinc-700/50 text-zinc-300 border border-zinc-600/30'
                                }`}
                              >
                                {tool}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* 출력 내용 */}
                      {log.output && (
                        <div>
                          <p className="text-xs font-medium text-zinc-500 uppercase mb-2">출력</p>
                          <pre className="text-xs text-zinc-400 bg-zinc-900/50 rounded-lg p-3 whitespace-pre-wrap break-words max-h-40 overflow-y-auto border border-zinc-700/50">
                            {log.output}
                          </pre>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* 정리 모달 */}
      {showCleanupModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-dark-card border border-dark-border rounded-2xl p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold mb-4">오래된 로그 정리</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-zinc-400 mb-2">
                  며칠 이전 로그 삭제?
                </label>
                <input
                  type="number"
                  value={cleanupDays}
                  onChange={(e) => setCleanupDays(Number(e.target.value))}
                  min={1}
                  max={365}
                  className="w-full bg-dark-bg border border-dark-border rounded-lg px-3 py-2 focus:outline-none focus:border-primary"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="keepFailures"
                  checked={keepFailures}
                  onChange={(e) => setKeepFailures(e.target.checked)}
                  className="w-4 h-4 rounded border-dark-border"
                />
                <label htmlFor="keepFailures" className="text-sm text-zinc-400">
                  실패 로그는 유지 (JinxLoop 학습용)
                </label>
              </div>

              <p className="text-xs text-zinc-500">
                실패 로그를 유지하면 JinxLoop이 에이전트 개선에 활용할 수 있습니다.
              </p>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowCleanupModal(false)}
                className="flex-1 px-4 py-2 rounded-lg border border-dark-border hover:bg-zinc-800 transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleCleanup}
                className="flex-1 px-4 py-2 rounded-lg bg-yellow-600 hover:bg-yellow-700 transition-colors"
              >
                정리하기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
