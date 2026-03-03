'use client';

import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Clock, RefreshCw, Filter, Trash2, CheckSquare, Square, AlertTriangle } from 'lucide-react';

interface TaskLog {
  id: string;
  agent_name: string;
  instruction: string;
  success: boolean;
  success_score: number;
  duration_ms: number;
  failure_reason?: string;
  created_at: string;
}

interface LogsResponse {
  logs: TaskLog[];
  total: number;
}

export default function LogsTab() {
  const [logs, setLogs] = useState<TaskLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('all');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showCleanupModal, setShowCleanupModal] = useState(false);
  const [cleanupDays, setCleanupDays] = useState(7);
  const [keepFailures, setKeepFailures] = useState(true);

  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '50' });
      if (filter !== 'all') {
        params.append('agent_name', filter);
      }

      const res = await fetch(`http://localhost:19000/logs?${params}`);
      const data: LogsResponse = await res.json();
      setLogs(data.logs);
      setTotal(data.total);
      setSelectedIds(new Set()); // 선택 초기화
    } catch (error) {
      console.error('Failed to fetch logs:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [filter]);

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString('ko-KR', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  // 개별 삭제
  const handleDeleteOne = async (logId: string) => {
    if (!confirm('이 로그를 삭제하시겠습니까?')) return;

    try {
      const res = await fetch(`http://localhost:19000/logs/${logId}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        fetchLogs();
      }
    } catch (error) {
      console.error('Failed to delete log:', error);
    }
  };

  // 선택 삭제
  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`선택한 ${selectedIds.size}개 로그를 삭제하시겠습니까?`)) return;

    try {
      const res = await fetch('http://localhost:19000/logs', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ log_ids: Array.from(selectedIds) }),
      });
      if (res.ok) {
        fetchLogs();
      }
    } catch (error) {
      console.error('Failed to delete logs:', error);
    }
  };

  // 오래된 로그 정리
  const handleCleanup = async () => {
    try {
      const res = await fetch('http://localhost:19000/logs/cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ days: cleanupDays, keep_failures: keepFailures }),
      });
      if (res.ok) {
        const data = await res.json();
        alert(`${data.deleted_count}개의 로그가 정리되었습니다.`);
        setShowCleanupModal(false);
        fetchLogs();
      }
    } catch (error) {
      console.error('Failed to cleanup logs:', error);
    }
  };

  // 전체 선택/해제
  const handleSelectAll = () => {
    if (selectedIds.size === logs.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(logs.map((log) => log.id)));
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

  const agents = ['all', 'JX_CODER', 'JX_RESEARCHER', 'JX_WRITER', 'JX_ANALYST', 'JX_OPS'];

  return (
    <div className="h-full flex flex-col">
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold">작업 로그</h2>
          <p className="text-sm text-zinc-500">총 {total}개의 작업 기록</p>
        </div>
        <div className="flex items-center gap-3">
          {/* 필터 */}
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-zinc-500" />
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-dark-card border border-dark-border rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-primary"
            >
              {agents.map((agent) => (
                <option key={agent} value={agent}>
                  {agent === 'all' ? '전체' : agent}
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
            onClick={fetchLogs}
            disabled={loading}
            className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
            title="새로고침"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* 전체 선택 */}
      {logs.length > 0 && (
        <div className="flex items-center gap-2 mb-3 text-sm text-zinc-400">
          <button
            onClick={handleSelectAll}
            className="flex items-center gap-1.5 hover:text-zinc-200 transition-colors"
          >
            {selectedIds.size === logs.length ? (
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
        ) : logs.length === 0 ? (
          <div className="flex items-center justify-center h-40 text-zinc-500">
            작업 기록이 없습니다
          </div>
        ) : (
          logs.map((log) => (
            <div
              key={log.id}
              className={`bg-dark-card border rounded-xl p-4 transition-colors ${
                selectedIds.has(log.id)
                  ? 'border-primary bg-primary/5'
                  : 'border-dark-border hover:border-zinc-600'
              }`}
            >
              <div className="flex items-start justify-between gap-4">
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
                    <span className="text-xs text-zinc-500">
                      {formatTime(log.created_at)}
                    </span>
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
                  <div className="flex items-center gap-1 text-xs text-zinc-500">
                    <Clock size={12} />
                    <span>{formatDuration(log.duration_ms)}</span>
                  </div>
                  <div className="text-xs text-zinc-500 mt-1">
                    {(log.success_score * 100).toFixed(0)}%
                  </div>
                  <button
                    onClick={() => handleDeleteOne(log.id)}
                    className="mt-2 p-1 rounded hover:bg-red-600/20 text-zinc-500 hover:text-red-400 transition-colors"
                    title="삭제"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))
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
