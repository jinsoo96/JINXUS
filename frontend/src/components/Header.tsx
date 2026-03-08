'use client';

import { useAppStore } from '@/store/useAppStore';
import { Activity, Wifi, WifiOff } from 'lucide-react';
import TasksDropdown from './TasksDropdown';

export default function Header() {
  const { systemStatus } = useAppStore();

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  return (
    <header className="h-16 bg-dark-card border-b border-dark-border px-4 md:px-6 flex items-center justify-between">
      <div className="pl-10 md:pl-0" />

      <div className="flex items-center gap-3 md:gap-6">
        {/* 연결 상태 - 모바일에서 축약 */}
        <div className="hidden sm:flex items-center gap-2 text-sm">
          {systemStatus?.redis_connected ? (
            <span className="flex items-center gap-1 text-green-400">
              <Wifi size={16} />
              Redis
            </span>
          ) : (
            <span className="flex items-center gap-1 text-red-400">
              <WifiOff size={16} />
              Redis
            </span>
          )}
        </div>

        <div className="hidden sm:flex items-center gap-2 text-sm">
          {systemStatus?.qdrant_connected ? (
            <span className="flex items-center gap-1 text-green-400">
              <Wifi size={16} />
              Qdrant
            </span>
          ) : (
            <span className="flex items-center gap-1 text-red-400">
              <WifiOff size={16} />
              Qdrant
            </span>
          )}
        </div>

        {/* 업타임 - 태블릿 이상 */}
        {systemStatus && (
          <div className="hidden md:flex items-center gap-2 text-sm text-zinc-400">
            <Activity size={16} />
            <span>{formatUptime(systemStatus.uptime_seconds)}</span>
          </div>
        )}

        {/* 활성 작업 드롭다운 - 항상 표시 */}
        <TasksDropdown />

        {/* 처리 작업 수 - 태블릿 이상 */}
        {systemStatus && (
          <div className="hidden md:block text-sm text-zinc-400">
            완료: {systemStatus.total_tasks_processed}
          </div>
        )}
      </div>
    </header>
  );
}
