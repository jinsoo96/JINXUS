'use client';

import { useAppStore } from '@/store/useAppStore';
import { Settings, Server, Database, Zap, RefreshCw } from 'lucide-react';

export default function SettingsTab() {
  const { systemStatus, loadSystemStatus, clearMessages } = useAppStore();

  const handleRefresh = () => {
    loadSystemStatus();
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">설정</h2>

      {/* 시스템 상태 */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Server size={20} />
            시스템 상태
          </h3>
          <button
            onClick={handleRefresh}
            className="p-2 rounded-lg hover:bg-zinc-800 transition-colors"
            title="새로고침"
          >
            <RefreshCw size={18} />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* 상태 */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">상태</div>
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${
                  systemStatus?.status === 'running' ? 'bg-green-400' : 'bg-red-400'
                }`}
              ></span>
              <span className="font-semibold">
                {systemStatus?.status === 'running' ? '정상' : systemStatus?.status || '-'}
              </span>
            </div>
          </div>

          {/* 업타임 */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">업타임</div>
            <div className="font-semibold">
              {systemStatus
                ? `${Math.floor(systemStatus.uptime_seconds / 3600)}h ${Math.floor((systemStatus.uptime_seconds % 3600) / 60)}m`
                : '-'}
            </div>
          </div>

          {/* 처리 작업 */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">처리 작업</div>
            <div className="font-semibold">
              {systemStatus?.total_tasks_processed || 0}
            </div>
          </div>

          {/* 활성 에이전트 */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">활성 에이전트</div>
            <div className="font-semibold">
              {systemStatus?.active_agents?.length || 0}
            </div>
          </div>
        </div>
      </div>

      {/* 인프라 연결 */}
      <div className="mb-8">
        <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
          <Database size={20} />
          인프라 연결
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Redis */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-red-500/20 flex items-center justify-center">
                  <Zap size={20} className="text-red-400" />
                </div>
                <div>
                  <div className="font-semibold">Redis</div>
                  <div className="text-zinc-500 text-sm">단기 메모리</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`w-3 h-3 rounded-full ${
                    systemStatus?.redis_connected ? 'bg-green-400' : 'bg-red-400'
                  }`}
                ></span>
                <span className="text-sm">
                  {systemStatus?.redis_connected ? '연결됨' : '연결 안됨'}
                </span>
              </div>
            </div>
          </div>

          {/* Qdrant */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
                  <Database size={20} className="text-amber-400" />
                </div>
                <div>
                  <div className="font-semibold">Qdrant</div>
                  <div className="text-zinc-500 text-sm">장기 메모리 (벡터 DB)</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`w-3 h-3 rounded-full ${
                    systemStatus?.qdrant_connected ? 'bg-green-400' : 'bg-red-400'
                  }`}
                ></span>
                <span className="text-sm">
                  {systemStatus?.qdrant_connected ? '연결됨' : '연결 안됨'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 채팅 설정 */}
      <div className="mb-8">
        <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
          <Settings size={20} />
          채팅 설정
        </h3>

        <div className="bg-dark-card border border-dark-border rounded-xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold">대화 기록 초기화</div>
              <div className="text-zinc-500 text-sm">
                현재 세션의 모든 대화 내용을 삭제합니다.
              </div>
            </div>
            <button
              onClick={clearMessages}
              className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
            >
              초기화
            </button>
          </div>
        </div>
      </div>

      {/* 버전 정보 */}
      <div className="text-center text-zinc-600 text-sm">
        JINXUS v1.1.0 | 에이전트 실행 로직 적용 | 주인님의 충실한 AI 비서
      </div>
    </div>
  );
}
