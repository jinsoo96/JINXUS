'use client';

import { useState, useEffect, useRef } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { agentApi, logsApi, AgentRuntimeStatus, TaskLog } from '@/lib/api';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import { formatTime, formatDateTime, getAgentStatusColor, getAgentStatusText } from '@/lib/utils';
import toast from 'react-hot-toast';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Cpu,
  Database,
  Zap,
  RefreshCw,
  Play,
  Pause,
  AlertCircle
} from 'lucide-react';
import { StatCardSkeleton, ListSkeleton } from '@/components/Skeleton';

// 상태 색상/텍스트는 lib/utils.ts의 getAgentStatusColor, getAgentStatusText 사용

export default function DashboardTab() {
  const { systemStatus } = useAppStore();

  // 상태
  const [agentStatuses, setAgentStatuses] = useState<AgentRuntimeStatus[]>([]);
  const [recentLogs, setRecentLogs] = useState<TaskLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 데이터 로드
  const loadData = async () => {
    try {
      const [statusRes, logsRes] = await Promise.all([
        agentApi.getAllRuntimeStatus(),
        logsApi.getLogs(undefined, 10, 0),
      ]);

      setAgentStatuses(statusRes.agents);
      setRecentLogs(logsRes.logs);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Dashboard data load error:', error);
      toast.error('대시보드 데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  };

  // 초기 로드 및 자동 갱신 (비활성 탭에서는 폴링 중지)
  useEffect(() => {
    loadData();

    if (autoRefresh) {
      const poll = () => {
        if (document.visibilityState === 'visible') loadData();
      };
      intervalRef.current = setInterval(poll, POLLING_INTERVAL_MS);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh]); // eslint-disable-line react-hooks/exhaustive-deps

  // 작업 중인 에이전트 수
  const workingCount = agentStatuses.filter(a => a.status === 'working').length;
  const totalAgents = agentStatuses.length;

  // 통계 (systemStatus에서 가져옴)
  const todayStats = {
    totalTasks: systemStatus?.total_tasks_processed ?? 0,
    successRate: recentLogs.length > 0
      ? recentLogs.filter(l => l.success).length / recentLogs.length
      : 0,
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="h-8 w-32 bg-zinc-700/50 rounded animate-pulse" />
          <div className="h-8 w-48 bg-zinc-700/50 rounded animate-pulse" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="h-5 w-24 bg-zinc-700/50 rounded animate-pulse mb-4" />
            <ListSkeleton count={4} />
          </div>
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="h-5 w-24 bg-zinc-700/50 rounded animate-pulse mb-4" />
            <ListSkeleton count={4} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">대시보드</h1>
        <div className="flex items-center gap-4">
          {/* 마지막 업데이트 */}
          {lastUpdate && (
            <span className="text-sm text-zinc-500">
              마지막 업데이트: {formatTime(lastUpdate)}
            </span>
          )}

          {/* 자동 갱신 토글 */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
              autoRefresh
                ? 'bg-green-600 text-white'
                : 'bg-zinc-700 text-zinc-300'
            }`}
          >
            {autoRefresh ? <Play size={14} /> : <Pause size={14} />}
            {autoRefresh ? '자동 갱신 ON' : '자동 갱신 OFF'}
          </button>

          {/* 수동 새로고침 */}
          <button
            onClick={loadData}
            className="p-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 transition-colors"
          >
            <RefreshCw size={18} />
          </button>
        </div>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 시스템 상태 */}
        <div className="bg-dark-card border border-dark-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-blue-500/20 rounded-lg">
              <Cpu className="w-5 h-5 text-blue-400" />
            </div>
            <span className="text-sm text-zinc-400">시스템 상태</span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${systemStatus?.status === 'running' ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-lg font-semibold">
              {systemStatus?.status === 'running' ? '정상' : '점검 필요'}
            </span>
          </div>
        </div>

        {/* 활성 에이전트 */}
        <div className="bg-dark-card border border-dark-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-green-500/20 rounded-lg">
              <Activity className="w-5 h-5 text-green-400" />
            </div>
            <span className="text-sm text-zinc-400">활성 에이전트</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold">{workingCount}</span>
            <span className="text-zinc-500">/ {totalAgents}</span>
          </div>
        </div>

        {/* 오늘 작업 */}
        <div className="bg-dark-card border border-dark-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-purple-500/20 rounded-lg">
              <Zap className="w-5 h-5 text-purple-400" />
            </div>
            <span className="text-sm text-zinc-400">전체 작업</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold">{todayStats.totalTasks}</span>
            <span className="text-zinc-500">건</span>
          </div>
        </div>

        {/* 성공률 */}
        <div className="bg-dark-card border border-dark-border rounded-xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-yellow-500/20 rounded-lg">
              <CheckCircle2 className="w-5 h-5 text-yellow-400" />
            </div>
            <span className="text-sm text-zinc-400">평균 성공률</span>
          </div>
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-bold">{(todayStats.successRate * 100).toFixed(0)}</span>
            <span className="text-zinc-500">%</span>
          </div>
        </div>
      </div>

      {/* 메인 컨텐츠 - 2컬럼 레이아웃 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 좌측: 에이전트 상태 */}
        <div className="bg-dark-card border border-dark-border rounded-xl">
          <div className="p-4 border-b border-dark-border">
            <h2 className="font-semibold flex items-center gap-2">
              <Activity size={18} />
              에이전트 상태
            </h2>
          </div>
          <div className="p-4 space-y-3 max-h-[400px] overflow-y-auto">
            {agentStatuses.map((agent) => (
              <div
                key={agent.name}
                className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg"
              >
                <div className="flex items-center gap-3">
                  <span className={`w-3 h-3 rounded-full ${getAgentStatusColor(agent.status)}`} />
                  <div>
                    <p className="font-medium">{agent.name}</p>
                    {agent.current_task && (
                      <p className="text-xs text-zinc-400 truncate max-w-[200px]">
                        {agent.current_task}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 text-xs rounded-full ${
                    agent.status === 'working' ? 'bg-green-500/20 text-green-400' :
                    agent.status === 'error' ? 'bg-red-500/20 text-red-400' :
                    'bg-zinc-600/50 text-zinc-400'
                  }`}>
                    {getAgentStatusText(agent.status)}
                  </span>
                  {agent.current_node && (
                    <span className="text-xs text-zinc-500">
                      @ {agent.current_node}
                    </span>
                  )}
                </div>
              </div>
            ))}

            {agentStatuses.length === 0 && (
              <p className="text-center text-zinc-500 py-8">
                에이전트 정보를 불러오는 중...
              </p>
            )}
          </div>
        </div>

        {/* 우측: 활동 타임라인 */}
        <div className="bg-dark-card border border-dark-border rounded-xl">
          <div className="p-4 border-b border-dark-border">
            <h2 className="font-semibold flex items-center gap-2">
              <Clock size={18} />
              최근 활동
            </h2>
          </div>
          <div className="p-4 space-y-3 max-h-[400px] overflow-y-auto">
            {recentLogs.map((log) => (
              <div
                key={log.id}
                className="flex items-start gap-3 p-3 bg-zinc-800/50 rounded-lg"
              >
                {/* 아이콘 */}
                <div className={`p-2 rounded-lg ${
                  log.success
                    ? 'bg-green-500/20 text-green-400'
                    : 'bg-red-500/20 text-red-400'
                }`}>
                  {log.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                </div>

                {/* 내용 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-primary">
                      {log.agent_name}
                    </span>
                    <span className="text-xs text-zinc-500">
                      {formatTime(log.created_at)}
                    </span>
                  </div>
                  <p className="text-sm text-zinc-300 truncate">
                    {log.instruction}
                  </p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-zinc-500">
                    <span>점수: {(log.success_score * 100).toFixed(0)}%</span>
                    <span>소요: {log.duration_ms}ms</span>
                  </div>
                </div>
              </div>
            ))}

            {recentLogs.length === 0 && (
              <p className="text-center text-zinc-500 py-8">
                최근 활동이 없습니다
              </p>
            )}
          </div>
        </div>
      </div>

      {/* 하단: 인프라 상태 */}
      <div className="bg-dark-card border border-dark-border rounded-xl">
        <div className="p-4 border-b border-dark-border">
          <h2 className="font-semibold flex items-center gap-2">
            <Database size={18} />
            인프라 상태
          </h2>
        </div>
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Redis */}
          <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
            <span className={`w-3 h-3 rounded-full ${
              systemStatus?.redis_connected ? 'bg-green-500' : 'bg-red-500'
            }`} />
            <div>
              <p className="font-medium">Redis</p>
              <p className="text-xs text-zinc-500">단기 메모리</p>
            </div>
            <span className={`ml-auto text-xs ${
              systemStatus?.redis_connected ? 'text-green-400' : 'text-red-400'
            }`}>
              {systemStatus?.redis_connected ? '연결됨' : '연결 안됨'}
            </span>
          </div>

          {/* Qdrant */}
          <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
            <span className={`w-3 h-3 rounded-full ${
              systemStatus?.qdrant_connected ? 'bg-green-500' : 'bg-red-500'
            }`} />
            <div>
              <p className="font-medium">Qdrant</p>
              <p className="text-xs text-zinc-500">장기 메모리</p>
            </div>
            <span className={`ml-auto text-xs ${
              systemStatus?.qdrant_connected ? 'text-green-400' : 'text-red-400'
            }`}>
              {systemStatus?.qdrant_connected ? '연결됨' : '연결 안됨'}
            </span>
          </div>

          {/* 가동 시간 */}
          <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
            <span className="w-3 h-3 rounded-full bg-blue-500" />
            <div>
              <p className="font-medium">가동 시간</p>
              <p className="text-xs text-zinc-500">Uptime</p>
            </div>
            <span className="ml-auto text-xs text-blue-400">
              {systemStatus ? formatUptime(systemStatus.uptime_seconds) : '-'}
            </span>
          </div>

          {/* 처리 작업 */}
          <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
            <span className="w-3 h-3 rounded-full bg-purple-500" />
            <div>
              <p className="font-medium">처리 작업</p>
              <p className="text-xs text-zinc-500">Total Processed</p>
            </div>
            <span className="ml-auto text-xs text-purple-400">
              {systemStatus?.total_tasks_processed ?? 0}건
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// 가동 시간 포맷
function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (days > 0) return `${days}일 ${hours}시간`;
  if (hours > 0) return `${hours}시간 ${minutes}분`;
  return `${minutes}분`;
}
