'use client';

import { useAppStore } from '@/store/useAppStore';
import { Activity, Trash2 } from 'lucide-react';
import { systemApi } from '@/lib/api';
import TasksDropdown from './TasksDropdown';

export default function Header() {
  const { systemStatus, loadSystemStatus } = useAppStore();

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  return (
    <header className="h-12 md:h-14 bg-dark-card border-b border-dark-border px-4 md:px-6 flex items-center justify-between">
      {/* ── 왼쪽: 업타임 + 작업 현황 ── */}
      <div className="flex items-center gap-3 md:gap-4">
        {/* 모바일 햄버거 영역 */}
        <div className="w-8 md:hidden" />

        {/* 업타임 */}
        {systemStatus && (
          <div className="hidden md:flex items-center gap-1.5 text-sm text-zinc-400">
            <Activity size={14} />
            <span>{formatUptime(systemStatus.uptime_seconds)}</span>
          </div>
        )}

        {/* 활성 작업 드롭다운 */}
        <TasksDropdown />

        {/* 완료 작업 수 + 리셋 */}
        {systemStatus && (
          <div className="hidden md:flex items-center gap-1.5 text-sm text-zinc-400">
            <span>완료: {systemStatus.total_tasks_processed}</span>
            {systemStatus.total_tasks_processed > 0 && (
              <button
                onClick={async () => {
                  if (!confirm('완료된 작업 로그를 전부 삭제합니다.')) return;
                  try {
                    await systemApi.clearCompletedTasks();
                    loadSystemStatus();
                  } catch { /* ignore */ }
                }}
                className="p-0.5 rounded hover:bg-zinc-700 text-zinc-600 hover:text-red-400 transition-colors"
                title="작업 로그 초기화"
              >
                <Trash2 size={12} />
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── 오른쪽: 인프라 상태 ── */}
      <div className="flex items-center gap-3 md:gap-4">
        <div className="flex items-center gap-1.5 sm:gap-2 text-sm" aria-label="Redis 연결 상태">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${systemStatus?.redis_connected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className={`hidden sm:inline ${systemStatus?.redis_connected ? 'text-green-400' : 'text-red-400'}`}>Redis</span>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 text-sm" aria-label="Qdrant 연결 상태">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${systemStatus?.qdrant_connected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className={`hidden sm:inline ${systemStatus?.qdrant_connected ? 'text-green-400' : 'text-red-400'}`}>Qdrant</span>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 text-sm" aria-label="Synapse 연결 상태">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${systemStatus?.synapse_connected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className={`hidden sm:inline ${systemStatus?.synapse_connected ? 'text-green-400' : 'text-red-400'}`}>Synapse</span>
        </div>
      </div>
    </header>
  );
}
