'use client';

import { useAppStore } from '@/store/useAppStore';
import { Activity, Wifi, WifiOff } from 'lucide-react';

export default function Header() {
  const { systemStatus } = useAppStore();

  const formatUptime = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
  };

  return (
    <header className="h-16 bg-dark-card border-b border-dark-border px-6 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold text-primary">JINXUS</h1>
        <span className="text-zinc-500 text-sm">주인님의 충실한 AI 비서</span>
      </div>

      <div className="flex items-center gap-6">
        {/* 연결 상태 */}
        <div className="flex items-center gap-2 text-sm">
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

        <div className="flex items-center gap-2 text-sm">
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

        {/* 업타임 */}
        {systemStatus && (
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <Activity size={16} />
            <span>{formatUptime(systemStatus.uptime_seconds)}</span>
          </div>
        )}

        {/* 처리 작업 수 */}
        {systemStatus && (
          <div className="text-sm text-zinc-400">
            작업: {systemStatus.total_tasks_processed}
          </div>
        )}
      </div>
    </header>
  );
}
