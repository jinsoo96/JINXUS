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

        {/* 업타임 — tabular-nums로 숫자 정렬 흔들림 방지 */}
        {systemStatus && (
          <div className="hidden md:flex items-center gap-1.5 text-sm text-zinc-400">
            <Activity size={14} />
            <span className="tabular-nums">{formatUptime(systemStatus.uptime_seconds)}</span>
          </div>
        )}

        {/* 활성 작업 드롭다운 */}
        <TasksDropdown />

        {/* 완료 작업 수 + 리셋 */}
        {systemStatus && (
          <div className="hidden md:flex items-center gap-1.5 text-sm text-zinc-400">
            <span className="tabular-nums">완료: {systemStatus.total_tasks_processed}</span>
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

      {/* ── 오른쪽: 인프라 상태 (aria-live로 상태 변경 알림) ── */}
      <div className="flex items-center gap-3 md:gap-4" role="status" aria-live="polite">
        {[
          { key: 'redis', label: 'Redis', connected: systemStatus?.redis_connected },
          { key: 'qdrant', label: 'Qdrant', connected: systemStatus?.qdrant_connected },
          { key: 'synapse', label: 'Synapse', connected: systemStatus?.synapse_connected },
        ].map(({ key, label, connected }) => (
          <div key={key} className="flex items-center gap-1.5 sm:gap-2 text-sm" aria-label={`${label} ${connected ? '연결됨' : '연결 끊김'}`}>
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${connected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className={`hidden sm:inline ${connected ? 'text-green-400' : 'text-red-400'}`}>{label}</span>
            {/* 색상 외 텍스트 보조 — 모바일에서 색상만으로 구분 방지 */}
            <span className="sr-only">{connected ? '연결됨' : '연결 끊김'}</span>
          </div>
        ))}
      </div>
    </header>
  );
}
