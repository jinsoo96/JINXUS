'use client';

import { useState, useEffect, useRef } from 'react';
import { Loader2, X, ChevronDown, Clock, AlertCircle } from 'lucide-react';
import { taskApi, type ActiveTask } from '@/lib/api';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import { formatTime, getTaskStatusColor } from '@/lib/utils';

export default function TasksDropdown() {
  const [isOpen, setIsOpen] = useState(false);
  const [tasks, setTasks] = useState<ActiveTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 활성 작업 조회
  const fetchTasks = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await taskApi.getActiveTasks();
      setTasks(response.active_tasks);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch tasks');
    } finally {
      setLoading(false);
    }
  };

  // 작업 취소
  const handleCancel = async (taskId: string) => {
    try {
      await taskApi.cancelTask(taskId);
      // 취소 후 목록 새로고침
      fetchTasks();
    } catch (err) {
      console.error('Failed to cancel task:', err);
    }
  };

  // 드롭다운 열릴 때 조회
  useEffect(() => {
    if (isOpen) {
      fetchTasks();
    }
  }, [isOpen]);

  // 5초 간격 자동 새로고침 (드롭다운 열려있을 때만)
  useEffect(() => {
    if (!isOpen) return;

    const interval = setInterval(fetchTasks, POLLING_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isOpen]);

  // 외부 클릭 시 닫기
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const activeCount = tasks.length;

  // 상태 색상은 lib/utils.ts의 getTaskStatusColor 사용

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 트리거 버튼 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
          activeCount > 0
            ? 'bg-blue-500/20 text-blue-400 hover:bg-blue-500/30'
            : 'bg-dark-card text-zinc-400 hover:bg-dark-border'
        }`}
      >
        {activeCount > 0 && <Loader2 size={14} className="animate-spin" />}
        <span>작업중 ({activeCount})</span>
        <ChevronDown size={14} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {/* 드롭다운 메뉴 */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-dark-card border border-dark-border rounded-lg shadow-xl z-50">
          <div className="p-3 border-b border-dark-border">
            <h3 className="font-medium text-white">활성 작업</h3>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {loading && tasks.length === 0 ? (
              <div className="p-4 text-center text-zinc-400">
                <Loader2 size={20} className="animate-spin mx-auto mb-2" />
                <span>불러오는 중...</span>
              </div>
            ) : error ? (
              <div className="p-4 text-center text-red-400">
                <AlertCircle size={20} className="mx-auto mb-2" />
                <span>{error}</span>
              </div>
            ) : tasks.length === 0 ? (
              <div className="p-4 text-center text-zinc-500">
                현재 실행 중인 작업이 없습니다.
              </div>
            ) : (
              <ul className="divide-y divide-dark-border">
                {tasks.map((task) => (
                  <li key={task.id} className="p-3 hover:bg-dark-bg/50">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-white truncate">{task.description}</p>
                        <div className="flex items-center gap-3 mt-1 text-xs">
                          <span className={getTaskStatusColor(task.status)}>
                            {task.status === 'running' || task.status === 'in_progress' ? 'running' : task.status}
                          </span>
                          <span className="text-zinc-500 flex items-center gap-1">
                            <Clock size={10} />
                            {formatTime(task.started_at || task.created_at) || '-'}
                          </span>
                        </div>
                        {/* 진행률 바 */}
                        {(task.status === 'running' || task.status === 'in_progress') && task.progress > 0 && (
                          <div className="mt-2 h-1 bg-dark-border rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 transition-all"
                              style={{ width: `${task.progress}%` }}
                            />
                          </div>
                        )}
                      </div>
                      {/* 취소 버튼 */}
                      <button
                        onClick={() => handleCancel(task.id)}
                        className="p-1 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                        title="작업 취소"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* 푸터 */}
          {tasks.length > 0 && (
            <div className="p-2 border-t border-dark-border text-center">
              <button
                onClick={fetchTasks}
                className="text-xs text-zinc-400 hover:text-white transition-colors"
              >
                새로고침
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
