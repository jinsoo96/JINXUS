'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { agentApi, logsApi, systemApi, taskApi, AgentRuntimeStatus, TaskLog, DelegationEvent, ActiveTask } from '@/lib/api';
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
  AlertCircle,
  ArrowRight,
  ListTodo,
  ChevronDown,
  Terminal,
} from 'lucide-react';
import { StatCardSkeleton, ListSkeleton } from '@/components/Skeleton';

// 상태 색상/텍스트는 lib/utils.ts의 getAgentStatusColor, getAgentStatusText 사용

export default function DashboardTab({ isActive = true }: { isActive?: boolean }) {
  const { systemStatus } = useAppStore();

  // 상태
  const [agentStatuses, setAgentStatuses] = useState<AgentRuntimeStatus[]>([]);
  const [recentLogs, setRecentLogs] = useState<TaskLog[]>([]);
  const [delegationEvents, setDelegationEvents] = useState<DelegationEvent[]>([]);
  const [activeTasks, setActiveTasks] = useState<ActiveTask[]>([]);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [liveTaskLogs, setLiveTaskLogs] = useState<{ time: string; msg: string }[]>([]);
  const taskEsRef = useRef<EventSource | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [performanceData, setPerformanceData] = useState<Record<string, { success_rate: number; avg_duration_ms: number; total_tasks: number }>>({});
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 데이터 로드
  const loadData = async () => {
    try {
      const [statusRes, logsRes, delegationRes, tasksRes, perfRes] = await Promise.all([
        agentApi.getAllRuntimeStatus().catch(() => ({ agents: [] })),
        logsApi.getLogs(undefined, 10, 0).catch(() => ({ logs: [], total: 0 })),
        systemApi.getDelegationEvents(20).catch(() => ({ events: [], total: 0 })),
        taskApi.getActiveTasks().catch(() => ({ active_tasks: [], count: 0 })),
        logsApi.getSummary().catch(() => ({ total_tasks: 0, agent_stats: {} })),
      ]);

      setAgentStatuses(statusRes.agents);
      setRecentLogs(logsRes.logs);
      setDelegationEvents(delegationRes.events);
      setActiveTasks(tasksRes.active_tasks);
      setPerformanceData(perfRes.agent_stats || {});
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
    if (isActive) loadData();

    if (autoRefresh && isActive) {
      const poll = () => {
        if (document.visibilityState === 'visible') loadData();
      };
      intervalRef.current = setInterval(poll, POLLING_INTERVAL_MS);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  // 실시간 로그 자동 스크롤 (100ms 디바운싱 — 빠른 로그 유입 시 GPU 부하 방지)
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (scrollTimerRef.current) return;
    scrollTimerRef.current = setTimeout(() => {
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      scrollTimerRef.current = null;
    }, 100);
    return () => {
      if (scrollTimerRef.current) {
        clearTimeout(scrollTimerRef.current);
        scrollTimerRef.current = null;
      }
    };
  }, [liveTaskLogs]);

  // 백그라운드 작업 SSE 구독
  const addLog = useCallback((msg: string) => {
    const time = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    setLiveTaskLogs(prev => [...prev.slice(-99), { time, msg }]);
  }, []);

  useEffect(() => {
    if (taskEsRef.current) { taskEsRef.current.close(); taskEsRef.current = null; }
    setLiveTaskLogs([]);
    if (!expandedTaskId) return;

    const es = new EventSource(`/api/task/${expandedTaskId}/stream`);
    taskEsRef.current = es;

    es.addEventListener('progress', (e: MessageEvent) => {
      try { const d = JSON.parse(e.data); if (d.message) addLog(d.message); } catch { /* ignore */ }
    });
    es.addEventListener('step_progress', (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        addLog(`📍 Step ${d.steps_completed ?? '?'}/${d.steps_total ?? '?'} (${d.progress ?? 0}%)`);
        setActiveTasks(prev => prev.map(t =>
          t.id === expandedTaskId
            ? { ...t, progress: d.progress ?? t.progress, steps_completed: d.steps_completed, steps_total: d.steps_total }
            : t
        ));
      } catch { /* ignore */ }
    });
    es.addEventListener('completed', (e: MessageEvent) => {
      try { const d = JSON.parse(e.data); addLog(`✅ 완료 (${d.duration_s ?? '?'}초)`); } catch { /* ignore */ }
      es.close();
    });
    es.addEventListener('failed', (e: MessageEvent) => {
      try { const d = JSON.parse(e.data); addLog(`❌ 실패: ${d.error ?? ''}`); } catch { /* ignore */ }
      es.close();
    });
    es.onerror = () => { es.close(); };

    return () => { es.close(); taskEsRef.current = null; };
  }, [expandedTaskId, addLog]);

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
        <div className="bg-dark-card border border-dark-border border-l-2 border-l-blue-500 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">시스템 상태</span>
            <div className="p-1.5 bg-blue-500/15 rounded-lg">
              <Cpu className="w-4 h-4 text-blue-400" />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${systemStatus?.status === 'running' ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]' : 'bg-red-500'}`} />
            <span className="text-xl font-bold">
              {systemStatus?.status === 'running' ? '정상' : '점검 필요'}
            </span>
          </div>
        </div>

        {/* 활성 에이전트 */}
        <div className="bg-dark-card border border-dark-border border-l-2 border-l-green-500 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">활성 에이전트</span>
            <div className="p-1.5 bg-green-500/15 rounded-lg">
              <Activity className="w-4 h-4 text-green-400" />
            </div>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-bold text-green-400">{workingCount}</span>
            <span className="text-zinc-500 text-sm">/ {totalAgents} 에이전트</span>
          </div>
        </div>

        {/* 전체 작업 */}
        <div className="bg-dark-card border border-dark-border border-l-2 border-l-purple-500 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">전체 작업</span>
            <div className="p-1.5 bg-purple-500/15 rounded-lg">
              <Zap className="w-4 h-4 text-purple-400" />
            </div>
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-bold text-purple-400">{todayStats.totalTasks}</span>
            <span className="text-zinc-500 text-sm">건 처리</span>
          </div>
        </div>

        {/* 성공률 */}
        <div className="bg-dark-card border border-dark-border border-l-2 border-l-amber-500 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">평균 성공률</span>
            <div className="p-1.5 bg-amber-500/15 rounded-lg">
              <CheckCircle2 className="w-4 h-4 text-amber-400" />
            </div>
          </div>
          <div className="flex items-baseline gap-0.5">
            <span className={`text-3xl font-bold ${
              todayStats.successRate >= 0.8 ? 'text-green-400' :
              todayStats.successRate >= 0.5 ? 'text-amber-400' : 'text-red-400'
            }`}>{(todayStats.successRate * 100).toFixed(0)}</span>
            <span className="text-zinc-500 text-sm">%</span>
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

      {/* 에이전트 성능 비교 */}
      {Object.keys(performanceData).length > 0 && (
        <div className="bg-dark-card border border-dark-border rounded-xl">
          <div className="p-4 border-b border-dark-border">
            <h2 className="font-semibold flex items-center gap-2">
              <Zap size={18} />
              에이전트 성능 비교
            </h2>
          </div>
          <div className="p-4 space-y-3">
            {Object.entries(performanceData)
              .sort(([, a], [, b]) => b.total_tasks - a.total_tasks)
              .slice(0, 8)
              .map(([name, stats]) => (
                <div key={name} className="flex items-center gap-3">
                  <span className="text-sm font-medium w-32 truncate text-zinc-300">{name}</span>
                  <div className="flex-1 flex items-center gap-2">
                    {/* 성공률 바 */}
                    <div className="flex-1 h-4 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          stats.success_rate >= 0.8 ? 'bg-green-500' :
                          stats.success_rate >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${stats.success_rate * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-zinc-400 w-12 text-right">
                      {(stats.success_rate * 100).toFixed(0)}%
                    </span>
                  </div>
                  <span className="text-xs text-zinc-500 w-16 text-right">
                    {stats.total_tasks}건
                  </span>
                  <span className="text-xs text-zinc-600 w-20 text-right">
                    {stats.avg_duration_ms > 0 ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : '-'}
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* 2행: 위임 타임라인 + 백그라운드 작업 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 위임 이벤트 타임라인 */}
        <div className="bg-dark-card border border-dark-border rounded-xl">
          <div className="p-4 border-b border-dark-border">
            <h2 className="font-semibold flex items-center gap-2">
              <ArrowRight size={18} />
              위임 타임라인
            </h2>
          </div>
          <div className="p-4 space-y-2 max-h-[300px] overflow-y-auto">
            {delegationEvents.length > 0 ? delegationEvents.map((evt, i) => (
              <div key={i} className="flex items-start gap-2 p-2 bg-zinc-800/30 rounded-lg text-sm">
                {evt.type === 'delegate' ? (
                  <>
                    <ArrowRight size={14} className="text-blue-400 mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-blue-400 font-medium">{evt.from}</span>
                        <ArrowRight size={10} className="text-zinc-600" />
                        <span className="text-primary font-medium">{evt.to}</span>
                        <span className="text-xs text-zinc-600 ml-auto">
                          {formatTime(evt.timestamp)}
                        </span>
                      </div>
                      {evt.instruction && (
                        <p className="text-xs text-zinc-500 truncate mt-0.5">{evt.instruction}</p>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    {evt.success ? (
                      <CheckCircle2 size={14} className="text-green-400 mt-0.5 shrink-0" />
                    ) : (
                      <XCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
                    )}
                    <div className="flex items-center gap-2 flex-1">
                      <span className={`font-medium ${evt.success ? 'text-green-400' : 'text-red-400'}`}>
                        {evt.agent}
                      </span>
                      <span className="text-xs text-zinc-500">완료</span>
                      {evt.duration_ms != null && (
                        <span className="text-xs text-zinc-600">{evt.duration_ms}ms</span>
                      )}
                      <span className="text-xs text-zinc-600 ml-auto">
                        {formatTime(evt.timestamp)}
                      </span>
                    </div>
                  </>
                )}
              </div>
            )) : (
              <p className="text-center text-zinc-500 py-6 text-sm">위임 이벤트 없음</p>
            )}
          </div>
        </div>

        {/* 백그라운드 작업 진행 */}
        <div className="bg-dark-card border border-dark-border rounded-xl">
          <div className="p-4 border-b border-dark-border flex items-center justify-between">
            <h2 className="font-semibold flex items-center gap-2">
              <ListTodo size={18} />
              백그라운드 작업
            </h2>
            {expandedTaskId && (
              <span className="flex items-center gap-1 text-xs text-green-400">
                <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                실시간 로그 수신 중
              </span>
            )}
          </div>
          <div className="divide-y divide-dark-border/50">
            {activeTasks.length > 0 ? activeTasks.map((task) => (
              <div key={task.id} className="overflow-hidden">
                {/* 작업 헤더 — 클릭으로 로그 패널 토글 */}
                <div
                  className="p-3 cursor-pointer hover:bg-zinc-800/40 transition-colors"
                  onClick={() => {
                    if (expandedTaskId === task.id) { setExpandedTaskId(null); }
                    else { setExpandedTaskId(task.id); setLiveTaskLogs([]); }
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm font-medium truncate max-w-[220px]">{task.description}</p>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        task.status === 'running' || task.status === 'in_progress'
                          ? 'bg-blue-500/20 text-blue-400'
                          : task.status === 'paused'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-zinc-600/50 text-zinc-400'
                      }`}>
                        {task.status === 'running' || task.status === 'in_progress' ? '실행 중' :
                         task.status === 'paused' ? '일시정지' : '대기'}
                      </span>
                      <ChevronDown size={14} className={`text-zinc-500 transition-transform duration-200 ${expandedTaskId === task.id ? 'rotate-180' : ''}`} />
                    </div>
                  </div>
                  <div className="w-full h-1.5 bg-zinc-700 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 rounded-full transition-all" style={{ width: `${task.progress}%` }} />
                  </div>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-xs text-zinc-500">
                      {task.steps_completed != null && task.steps_total != null
                        ? `${task.steps_completed}/${task.steps_total} 스텝`
                        : `${task.progress}%`}
                    </span>
                    <span className="text-xs text-zinc-600 font-mono">{task.id.slice(0, 8)}</span>
                  </div>
                </div>
                {/* 실시간 로그 패널 */}
                {expandedTaskId === task.id && (
                  <div className="border-t border-zinc-700/50 bg-zinc-900/70 px-3 py-2">
                    <div className="flex items-center gap-1.5 mb-2 text-xs text-zinc-500">
                      <Terminal size={11} />
                      실시간 실행 로그
                    </div>
                    <div className="max-h-48 overflow-y-auto space-y-0.5 font-mono">
                      {liveTaskLogs.length === 0 ? (
                        <p className="text-xs text-zinc-600 italic">로그 수신 대기 중...</p>
                      ) : (
                        liveTaskLogs.map((log, i) => (
                          <div key={i} className="flex gap-2 text-xs leading-relaxed">
                            <span className="text-zinc-600 shrink-0 text-[10px]">{log.time}</span>
                            <span className="text-zinc-400 break-all">{log.msg}</span>
                          </div>
                        ))
                      )}
                      <div ref={logEndRef} />
                    </div>
                  </div>
                )}
              </div>
            )) : (
              <p className="text-center text-zinc-500 py-6 text-sm">진행 중인 작업 없음</p>
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
