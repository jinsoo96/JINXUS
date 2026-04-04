'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import {
  agentApi, logsApi, taskApi, improveApi, systemApi,
  AgentRuntimeStatus, TaskLog, ActiveTask, ImproveHistoryItem, PromptVersion,
  ConfigGroup,
} from '@/lib/api';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import { formatTime, getAgentStatusColor, getAgentStatusText } from '@/lib/utils';
import { getDisplayName, getPersona } from '@/lib/personas';
import toast from 'react-hot-toast';
import {
  Activity, CheckCircle2, XCircle, Clock, Cpu, Database, Zap, RefreshCw,
  Play, Pause, AlertCircle, ListTodo, ChevronDown, ChevronUp, Terminal,
  Settings, Server, Sparkles, History, ArrowDownToLine, Loader2, Sliders,
  Save, RotateCcw,
} from 'lucide-react';
import { StatCardSkeleton, ListSkeleton } from '@/components/Skeleton';

// 가동 시간 포맷
function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}일 ${hours}시간`;
  if (hours > 0) return `${hours}시간 ${minutes}분`;
  return `${minutes}분`;
}

// 접을 수 있는 섹션 헤더
function SectionHeader({
  icon: Icon,
  title,
  open,
  onToggle,
  extra,
}: {
  icon: React.ComponentType<{ size?: number | string }>;
  title: string;
  open: boolean;
  onToggle: () => void;
  extra?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between mb-4">
      <button onClick={onToggle} className="flex items-center gap-2 text-lg font-semibold hover:text-primary transition-colors">
        <Icon size={20} />
        {title}
        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      {extra}
    </div>
  );
}

export default function SettingsTab({ isActive = true }: { isActive?: boolean }) {
  const { systemStatus, loadSystemStatus, clearMessages, agents, hrAgents } = useAppStore();

  // 섹션 접기/펼치기
  const [showMonitor, setShowMonitor] = useState(true);
  const [showBgTasks, setShowBgTasks] = useState(true);
  const [showImprove, setShowImprove] = useState(false);
  const [showSettings, setShowSettings] = useState(true);

  // --- 시스템 모니터링 상태 (DashboardTab에서 가져옴) ---
  const [agentStatuses, setAgentStatuses] = useState<AgentRuntimeStatus[]>([]);
  const [recentLogs, setRecentLogs] = useState<TaskLog[]>([]);
  const [activeTasks, setActiveTasks] = useState<ActiveTask[]>([]);
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [liveTaskLogs, setLiveTaskLogs] = useState<{ time: string; msg: string }[]>([]);
  const taskEsRef = useRef<EventSource | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [performanceData, setPerformanceData] = useState<Record<string, { success_rate: number; avg_duration_ms: number; total_tasks: number }>>({});
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [synapseConnected, setSynapseConnected] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // --- 자가 강화 상태 ---
  const [improveHistory, setImproveHistory] = useState<ImproveHistoryItem[]>([]);
  const [improveLoading, setImproveLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [promptVersions, setPromptVersions] = useState<PromptVersion[]>([]);
  const [promptAgent, setPromptAgent] = useState<string>('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [activePromptVersion, setActivePromptVersion] = useState('');
  const [rollingBack, setRollingBack] = useState(false);

  // --- 동적 설정 ---
  const [configGroups, setConfigGroups] = useState<ConfigGroup[]>([]);
  const [configEdits, setConfigEdits] = useState<Record<string, unknown>>({});
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [showConfig, setShowConfig] = useState(false);

  // --- 버전 ---
  const [jinxusVersion, setJinxusVersion] = useState('');

  useEffect(() => {
    systemApi.getInfo()
      .then(info => setJinxusVersion(info.version))
      .catch(() => setJinxusVersion('unknown'));
  }, []);

  // ============= 시스템 모니터링 데이터 로드 =============
  const loadData = useCallback(async () => {
    try {
      const [statusRes, logsRes, tasksRes, perfRes] = await Promise.all([
        agentApi.getAllRuntimeStatus().catch(() => ({ agents: [] })),
        logsApi.getLogs(undefined, 10, 0).catch(() => ({ logs: [], total: 0 })),
        taskApi.getActiveTasks().catch(() => ({ active_tasks: [], count: 0 })),
        logsApi.getSummary().catch(() => ({ total_tasks: 0, agent_stats: {} })),
      ]);
      setAgentStatuses(statusRes.agents);
      setRecentLogs(logsRes.logs);
      setActiveTasks(tasksRes.active_tasks);
      setPerformanceData(perfRes.agent_stats || {});
      setSynapseConnected(systemStatus?.synapse_connected ?? false);
      setLastUpdate(new Date());
      setLoadError(false);
    } catch (error) {
      console.error('Settings monitor data load error:', error);
      setLoadError(true);
      toast.error('모니터링 데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  }, [systemStatus?.synapse_connected]);

  // 초기 로드 및 자동 갱신
  useEffect(() => {
    if (isActive) loadData();
    if (autoRefresh && isActive) {
      const poll = () => { if (document.visibilityState === 'visible') loadData(); };
      intervalRef.current = setInterval(poll, POLLING_INTERVAL_MS);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, isActive, loadData]);

  // 실시간 로그 자동 스크롤
  const scrollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (scrollTimerRef.current) return;
    scrollTimerRef.current = setTimeout(() => {
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      scrollTimerRef.current = null;
    }, 100);
    return () => {
      if (scrollTimerRef.current) { clearTimeout(scrollTimerRef.current); scrollTimerRef.current = null; }
    };
  }, [liveTaskLogs]);

  // 백그라운드 작업 SSE 구독
  const addLog = useCallback((msg: string) => {
    const time = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: 'Asia/Seoul' });
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
        addLog(`Step ${d.steps_completed ?? '?'}/${d.steps_total ?? '?'} (${d.progress ?? 0}%)`);
        setActiveTasks(prev => prev.map(t =>
          t.id === expandedTaskId
            ? { ...t, progress: d.progress ?? t.progress, steps_completed: d.steps_completed, steps_total: d.steps_total }
            : t
        ));
      } catch { /* ignore */ }
    });
    es.addEventListener('completed', (e: MessageEvent) => {
      try { const d = JSON.parse(e.data); addLog(`완료 (${d.duration_s ?? '?'}초)`); } catch { /* ignore */ }
      es.close();
    });
    es.addEventListener('failed', (e: MessageEvent) => {
      try { const d = JSON.parse(e.data); addLog(`실패: ${d.error ?? ''}`); } catch { /* ignore */ }
      es.close();
    });
    es.onerror = () => { es.close(); };

    return () => { es.close(); taskEsRef.current = null; };
  }, [expandedTaskId, addLog]);

  // ============= 자가 강화 =============
  const loadImproveHistory = async () => {
    setImproveLoading(true);
    try {
      const data = await improveApi.getHistory(undefined, 20);
      setImproveHistory(data.history || []);
    } catch (error) {
      console.error('강화 이력 조회 실패:', error);
      toast.error('강화 이력 조회 실패');
    } finally {
      setImproveLoading(false);
    }
  };

  const handleTriggerImprove = async () => {
    setTriggering(true);
    try {
      await improveApi.trigger(selectedAgent || undefined);
      await loadImproveHistory();
    } catch (error) {
      console.error('자가 강화 실패:', error);
      toast.error('자가 강화 실행 실패');
    } finally {
      setTriggering(false);
    }
  };

  const loadPromptVersions = async (agentName: string) => {
    if (!agentName) return;
    setPromptLoading(true);
    setPromptAgent(agentName);
    try {
      const data = await improveApi.getPromptVersions(agentName);
      setPromptVersions(data.versions || []);
      setActivePromptVersion(data.active_version || '');
    } catch (error) {
      console.error('프롬프트 버전 조회 실패:', error);
      toast.error('프롬프트 버전 조회 실패');
      setPromptVersions([]);
    } finally {
      setPromptLoading(false);
    }
  };

  const handleRollback = async (version: string) => {
    if (!promptAgent) return;
    setRollingBack(true);
    try {
      await improveApi.rollback(promptAgent, version);
      await loadPromptVersions(promptAgent);
    } catch (error) {
      console.error('롤백 실패:', error);
      toast.error('프롬프트 롤백 실패');
    } finally {
      setRollingBack(false);
    }
  };

  useEffect(() => {
    if (showImprove && improveHistory.length === 0) {
      loadImproveHistory();
    }
  }, [showImprove]); // eslint-disable-line react-hooks/exhaustive-deps

  // 설정 스키마 로드
  const loadConfigSchema = async () => {
    setConfigLoading(true);
    try {
      const data = await systemApi.getConfigSchema();
      setConfigGroups(data.groups);
      setConfigEdits({});
    } catch (error) {
      console.error('설정 스키마 로드 실패:', error);
      toast.error('설정 스키마 로드 실패');
    } finally {
      setConfigLoading(false);
    }
  };

  useEffect(() => {
    if (showConfig && configGroups.length === 0) {
      loadConfigSchema();
    }
  }, [showConfig]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleConfigChange = (key: string, value: unknown) => {
    setConfigEdits(prev => ({ ...prev, [key]: value }));
  };

  const handleConfigSave = async () => {
    if (Object.keys(configEdits).length === 0) return;
    setConfigSaving(true);
    try {
      const result = await systemApi.updateConfig(configEdits);
      if (Object.keys(result.applied).length > 0) {
        toast.success(`${Object.keys(result.applied).length}개 설정 반영됨`);
        await loadConfigSchema();
      }
      if (Object.keys(result.rejected).length > 0) {
        toast.error(`거부됨: ${Object.values(result.rejected).join(', ')}`);
      }
    } catch (error) {
      console.error('설정 저장 실패:', error);
      toast.error('설정 저장 실패');
    } finally {
      setConfigSaving(false);
    }
  };

  // ============= 파생 값 =============
  const workingCount = agentStatuses.filter(a => a.status === 'working').length;
  const totalAgents = hrAgents.length;
  const todayStats = {
    totalTasks: systemStatus?.total_tasks_processed ?? 0,
    successRate: recentLogs.length > 0 ? recentLogs.filter(l => l.success).length / recentLogs.length : 0,
  };

  // ============= 로딩 스켈레톤 =============
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 bg-zinc-700/50 rounded animate-pulse" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
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

  if (loadError && agentStatuses.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <AlertCircle size={48} className="text-red-400" />
        <p className="text-zinc-400">데이터를 불러오지 못했습니다</p>
        <button onClick={loadData} className="flex items-center gap-2 px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm transition-colors">
          <RefreshCw size={14} />
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* 상단 헤더 */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">설정</h1>
        <div className="flex items-center gap-4">
          {lastUpdate && (
            <span className="text-sm text-zinc-500">
              마지막 업데이트: {formatTime(lastUpdate)}
            </span>
          )}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-colors ${
              autoRefresh ? 'bg-green-600 text-white' : 'bg-zinc-700 text-zinc-300'
            }`}
          >
            {autoRefresh ? <Play size={14} /> : <Pause size={14} />}
            {autoRefresh ? '자동 갱신 ON' : '자동 갱신 OFF'}
          </button>
          <button onClick={loadData} className="p-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 transition-colors">
            <RefreshCw size={18} />
          </button>
        </div>
      </div>

      {/* ==================== 섹션 1: 시스템 모니터링 ==================== */}
      <div>
        <SectionHeader icon={Cpu} title="시스템 모니터링" open={showMonitor} onToggle={() => setShowMonitor(!showMonitor)} />

        {showMonitor && (
          <div className="space-y-6">
            {/* 통계 카드 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
              {/* 시스템 상태 */}
              <div className="bg-dark-card border border-dark-border border-l-2 border-l-blue-500 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">시스템 상태</span>
                  <div className="p-1.5 bg-blue-500/15 rounded-lg"><Cpu className="w-4 h-4 text-blue-400" /></div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${systemStatus?.status === 'running' ? 'bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.6)]' : 'bg-red-500'}`} />
                  <span className="text-xl font-bold">{systemStatus?.status === 'running' ? '정상' : '점검 필요'}</span>
                </div>
              </div>

              {/* 활성 에이전트 */}
              <div className="bg-dark-card border border-dark-border border-l-2 border-l-green-500 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs font-medium text-zinc-500 uppercase tracking-wide">활성 에이전트</span>
                  <div className="p-1.5 bg-green-500/15 rounded-lg"><Activity className="w-4 h-4 text-green-400" /></div>
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
                  <div className="p-1.5 bg-purple-500/15 rounded-lg"><Zap className="w-4 h-4 text-purple-400" /></div>
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
                  <div className="p-1.5 bg-amber-500/15 rounded-lg"><CheckCircle2 className="w-4 h-4 text-amber-400" /></div>
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

            {/* 에이전트 상태 + 최근 활동 2컬럼 */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* 에이전트 상태 */}
              <div className="bg-dark-card border border-dark-border rounded-xl">
                <div className="p-4 border-b border-dark-border">
                  <h2 className="font-semibold flex items-center gap-2"><Activity size={18} />에이전트 상태</h2>
                </div>
                <div className="p-4 space-y-3 max-h-[400px] overflow-y-auto">
                  {agentStatuses.map((agent) => (
                    <div key={agent.name} className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
                      <div className="flex items-center gap-3">
                        <span className={`w-3 h-3 rounded-full ${getAgentStatusColor(agent.status)}`} />
                        <div>
                          <p className="font-medium">{getPersona(agent.name)?.emoji ?? ''} {getDisplayName(agent.name)}</p>
                          {agent.current_task && (
                            <p className="text-xs text-zinc-400 truncate max-w-xs sm:max-w-sm lg:max-w-md">{agent.current_task}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          agent.status === 'working' ? 'bg-green-500/20 text-green-400' :
                          agent.status === 'error' ? 'bg-red-500/20 text-red-400' :
                          'bg-zinc-600/50 text-zinc-400'
                        }`}>{getAgentStatusText(agent.status)}</span>
                        {agent.current_node && <span className="text-xs text-zinc-500">@ {agent.current_node}</span>}
                      </div>
                    </div>
                  ))}
                  {agentStatuses.length === 0 && (
                    <div className="flex flex-col items-center py-8 gap-3">
                      <p className="text-zinc-500">{loadError ? '에이전트 정보를 불러오지 못했습니다' : '에이전트 정보를 불러오는 중...'}</p>
                      {loadError && (
                        <button onClick={loadData} className="flex items-center gap-2 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm transition-colors">
                          <RefreshCw size={14} />다시 시도
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* 최근 활동 */}
              <div className="bg-dark-card border border-dark-border rounded-xl">
                <div className="p-4 border-b border-dark-border">
                  <h2 className="font-semibold flex items-center gap-2"><Clock size={18} />최근 활동</h2>
                </div>
                <div className="p-4 space-y-3 max-h-[400px] overflow-y-auto">
                  {recentLogs.map((log) => (
                    <div key={log.id} className="flex items-start gap-3 p-3 bg-zinc-800/50 rounded-lg">
                      <div className={`p-2 rounded-lg ${log.success ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                        {log.success ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-medium text-primary">{getPersona(log.agent_name)?.emoji ?? ''} {getDisplayName(log.agent_name)}</span>
                          <span className="text-xs text-zinc-500">{formatTime(log.created_at)}</span>
                        </div>
                        <p className="text-sm text-zinc-300 truncate">{log.instruction}</p>
                        <div className="flex items-center gap-3 mt-1 text-xs text-zinc-500">
                          <span>점수: {(log.success_score * 100).toFixed(0)}%</span>
                          <span>소요: {log.duration_ms}ms</span>
                        </div>
                      </div>
                    </div>
                  ))}
                  {recentLogs.length === 0 && (
                    <div className="flex flex-col items-center py-8 gap-3">
                      <p className="text-zinc-500">{loadError ? '활동 로그를 불러오지 못했습니다' : '최근 활동이 없습니다'}</p>
                      {loadError && (
                        <button onClick={loadData} className="flex items-center gap-2 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm transition-colors">
                          <RefreshCw size={14} />다시 시도
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 에이전트 성능 비교 */}
            {Object.keys(performanceData).length > 0 && (
              <div className="bg-dark-card border border-dark-border rounded-xl">
                <div className="p-4 border-b border-dark-border">
                  <h2 className="font-semibold flex items-center gap-2"><Zap size={18} />에이전트 성능 비교</h2>
                </div>
                <div className="p-4 space-y-3">
                  {Object.entries(performanceData)
                    .sort(([, a], [, b]) => b.total_tasks - a.total_tasks)
                    .slice(0, 8)
                    .map(([name, stats]) => (
                      <div key={name} className="flex items-center gap-3">
                        <span className="text-sm font-medium w-32 truncate text-zinc-300">{getDisplayName(name)}</span>
                        <div className="flex-1 flex items-center gap-2">
                          <div className="flex-1 h-4 bg-zinc-800 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all ${
                                stats.success_rate >= 0.8 ? 'bg-green-500' :
                                stats.success_rate >= 0.5 ? 'bg-yellow-500' : 'bg-red-500'
                              }`}
                              style={{ width: `${stats.success_rate * 100}%` }}
                            />
                          </div>
                          <span className="text-xs text-zinc-400 w-12 text-right">{(stats.success_rate * 100).toFixed(0)}%</span>
                        </div>
                        <span className="text-xs text-zinc-500 w-16 text-right">{stats.total_tasks}건</span>
                        <span className="text-xs text-zinc-600 w-20 text-right">
                          {stats.avg_duration_ms > 0 ? `${(stats.avg_duration_ms / 1000).toFixed(1)}s` : '-'}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}

            {/* 인프라 상태 */}
            <div className="bg-dark-card border border-dark-border rounded-xl">
              <div className="p-4 border-b border-dark-border">
                <h2 className="font-semibold flex items-center gap-2"><Database size={18} />인프라 상태</h2>
              </div>
              <div className="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
                  <span className={`w-3 h-3 rounded-full ${systemStatus?.redis_connected ? 'bg-green-500' : 'bg-red-500'}`} />
                  <div><p className="font-medium">Redis</p><p className="text-xs text-zinc-500">단기 메모리</p></div>
                  <span className={`ml-auto text-xs ${systemStatus?.redis_connected ? 'text-green-400' : 'text-red-400'}`}>
                    {systemStatus?.redis_connected ? '연결됨' : '연결 안됨'}
                  </span>
                </div>
                <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
                  <span className={`w-3 h-3 rounded-full ${systemStatus?.qdrant_connected ? 'bg-green-500' : 'bg-red-500'}`} />
                  <div><p className="font-medium">Qdrant</p><p className="text-xs text-zinc-500">장기 메모리</p></div>
                  <span className={`ml-auto text-xs ${systemStatus?.qdrant_connected ? 'text-green-400' : 'text-red-400'}`}>
                    {systemStatus?.qdrant_connected ? '연결됨' : '연결 안됨'}
                  </span>
                </div>
                <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
                  <span className={`w-3 h-3 rounded-full ${synapseConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                  <div><p className="font-medium">Synapse</p><p className="text-xs text-zinc-500">팀 채팅</p></div>
                  <span className={`ml-auto text-xs ${synapseConnected ? 'text-green-400' : 'text-red-400'}`}>
                    {synapseConnected ? '연결됨' : '연결 안됨'}
                  </span>
                </div>
                <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
                  <span className="w-3 h-3 rounded-full bg-blue-500" />
                  <div><p className="font-medium">가동 시간</p><p className="text-xs text-zinc-500">Uptime</p></div>
                  <span className="ml-auto text-xs text-blue-400">{systemStatus ? formatUptime(systemStatus.uptime_seconds) : '-'}</span>
                </div>
                <div className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
                  <span className="w-3 h-3 rounded-full bg-purple-500" />
                  <div><p className="font-medium">처리 작업</p><p className="text-xs text-zinc-500">Total Processed</p></div>
                  <span className="ml-auto text-xs text-purple-400">{systemStatus?.total_tasks_processed ?? 0}건</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ==================== 섹션 2: 백그라운드 작업 ==================== */}
      <div>
        <SectionHeader
          icon={ListTodo}
          title="백그라운드 작업"
          open={showBgTasks}
          onToggle={() => setShowBgTasks(!showBgTasks)}
          extra={expandedTaskId && showBgTasks ? (
            <span className="flex items-center gap-1 text-xs text-green-400">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              실시간 로그 수신 중
            </span>
          ) : undefined}
        />

        {showBgTasks && (
          <div className="bg-dark-card border border-dark-border rounded-xl">
            <div className="divide-y divide-dark-border/50">
              {activeTasks.length > 0 ? activeTasks.map((task) => (
                <div key={task.id} className="overflow-hidden">
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
                  {expandedTaskId === task.id && (
                    <div className="border-t border-zinc-700/50 bg-zinc-900/70 px-3 py-2">
                      <div className="flex items-center gap-1.5 mb-2 text-xs text-zinc-500">
                        <Terminal size={11} />실시간 실행 로그
                      </div>
                      <div className="max-h-48 overflow-y-auto space-y-0.5 font-mono">
                        {liveTaskLogs.length === 0 ? (
                          <p className="text-xs text-zinc-600 italic">로그 수신 대기 중...</p>
                        ) : (
                          liveTaskLogs.map((log, i) => (
                            <div key={i} className="flex gap-2 text-xs leading-relaxed">
                              <span className="text-zinc-600 shrink-0 text-[11px]">{log.time}</span>
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
                <div className="flex flex-col items-center py-6 gap-2">
                  <ListTodo size={24} className="text-zinc-600" />
                  <p className="text-zinc-500 text-sm">진행 중인 작업 없음</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ==================== 섹션 3: 자기개선 (JinxLoop) ==================== */}
      <div>
        <SectionHeader icon={Sparkles} title="자기개선 (JinxLoop)" open={showImprove} onToggle={() => setShowImprove(!showImprove)} />

        {showImprove && (
          <div className="space-y-4">
            {/* 수동 트리거 */}
            <div className="bg-dark-card border border-dark-border rounded-xl p-4">
              <div className="flex items-center gap-3">
                <select
                  value={selectedAgent}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="flex-1 bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                >
                  <option value="">전체 에이전트</option>
                  {agents.map((a) => (
                    <option key={a.name} value={a.name}>{getDisplayName(a.name)}</option>
                  ))}
                </select>
                <button
                  onClick={handleTriggerImprove}
                  disabled={triggering}
                  className="px-4 py-2 bg-primary text-white rounded-lg text-sm hover:bg-primary/80 disabled:opacity-50 flex items-center gap-2"
                >
                  {triggering ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
                  강화 실행
                </button>
              </div>
            </div>

            {/* 프롬프트 버전 관리 */}
            <div className="bg-dark-card border border-dark-border rounded-xl p-4">
              <h4 className="text-sm font-semibold text-zinc-400 mb-3 flex items-center gap-2">
                <History size={16} />프롬프트 버전 관리
              </h4>
              <div className="flex items-center gap-3 mb-3">
                <select
                  value={promptAgent}
                  onChange={(e) => loadPromptVersions(e.target.value)}
                  className="flex-1 bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                >
                  <option value="">에이전트 선택</option>
                  {agents.map((a) => (
                    <option key={a.name} value={a.name}>{getDisplayName(a.name)}</option>
                  ))}
                </select>
              </div>

              {promptLoading ? (
                <div className="text-center py-4"><Loader2 size={20} className="mx-auto animate-spin text-zinc-500" /></div>
              ) : promptVersions.length > 0 ? (
                <div className="space-y-2">
                  {promptVersions.map((v) => (
                    <div key={v.version} className={`flex items-center justify-between p-3 rounded-lg ${
                      v.version === activePromptVersion ? 'bg-primary/10 border border-primary/30' : 'bg-zinc-800/50'
                    }`}>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-sm">{v.version}</span>
                        {v.version === activePromptVersion && (
                          <span className="px-2 py-0.5 text-xs rounded-full bg-primary/20 text-primary">현재</span>
                        )}
                        <span className="text-xs text-zinc-500">{v.created_at}</span>
                      </div>
                      {v.version !== activePromptVersion && (
                        <button
                          onClick={() => handleRollback(v.version)}
                          disabled={rollingBack}
                          className="flex items-center gap-1 px-3 py-1 text-xs bg-amber-500/20 text-amber-400 rounded-lg hover:bg-amber-500/30 disabled:opacity-50"
                        >
                          <ArrowDownToLine size={12} />롤백
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              ) : promptAgent ? (
                <div className="text-center text-zinc-500 text-sm py-4">버전 이력이 없습니다</div>
              ) : null}
            </div>

            {/* A/B 테스트 이력 */}
            <div className="bg-dark-card border border-dark-border rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-semibold text-zinc-400 flex items-center gap-2">
                  <History size={16} />A/B 테스트 이력
                </h4>
                <button onClick={loadImproveHistory} disabled={improveLoading} className="p-1 rounded hover:bg-zinc-800 disabled:opacity-50">
                  {improveLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                </button>
              </div>
              {improveHistory.length > 0 ? (
                <div className="space-y-2">
                  {improveHistory.map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
                      <div>
                        <span className="font-mono text-sm">{getDisplayName(item.agent_name)}</span>
                        <span className="text-xs text-zinc-500 ml-2">{item.created_at}</span>
                      </div>
                      <div className="flex items-center gap-3 text-sm">
                        <span className="text-zinc-500">{item.old_score.toFixed(2)}</span>
                        <span className="text-zinc-600">&rarr;</span>
                        <span className={item.new_score > item.old_score ? 'text-green-400' : 'text-red-400'}>
                          {item.new_score.toFixed(2)}
                        </span>
                        <span className={`px-2 py-0.5 text-xs rounded-full ${
                          item.winner === 'new' ? 'bg-green-500/20 text-green-400' :
                          item.winner === 'old' ? 'bg-zinc-500/20 text-zinc-400' :
                          'bg-amber-500/20 text-amber-400'
                        }`}>
                          {item.winner === 'new' ? '개선' : item.winner === 'old' ? '유지' : '무승부'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-zinc-500 text-sm py-4">
                  {improveLoading ? '로딩 중...' : 'A/B 테스트 이력이 없습니다'}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ==================== 섹션 4: 시스템 설정 (동적 폼) ==================== */}
      <div>
        <SectionHeader
          icon={Sliders}
          title="시스템 설정"
          open={showConfig}
          onToggle={() => setShowConfig(!showConfig)}
          extra={showConfig && Object.keys(configEdits).length > 0 ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-amber-400">{Object.keys(configEdits).length}개 변경</span>
              <button
                onClick={() => setConfigEdits({})}
                className="p-1 rounded hover:bg-zinc-800 text-zinc-500"
                title="변경 취소"
              >
                <RotateCcw size={14} />
              </button>
              <button
                onClick={handleConfigSave}
                disabled={configSaving}
                className="flex items-center gap-1 px-3 py-1 bg-primary text-black rounded-lg text-xs font-medium hover:bg-primary/80 disabled:opacity-50"
              >
                {configSaving ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />}
                저장
              </button>
            </div>
          ) : undefined}
        />

        {showConfig && (
          <div className="space-y-4">
            {configLoading ? (
              <div className="text-center py-8"><Loader2 size={24} className="mx-auto animate-spin text-zinc-500" /></div>
            ) : configGroups.map((group) => (
              <div key={group.group} className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-dark-border bg-zinc-800/30">
                  <h3 className="text-sm font-semibold text-zinc-300">{group.group}</h3>
                </div>
                <div className="p-4 space-y-3">
                  {group.fields.map((field) => {
                    const editedValue = configEdits[field.key];
                    const currentValue = editedValue !== undefined ? editedValue : field.value;
                    const isEdited = editedValue !== undefined;

                    return (
                      <div key={field.key} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
                        <label className={`text-xs sm:text-sm sm:w-56 flex-shrink-0 ${isEdited ? 'text-amber-400' : 'text-zinc-400'}`}>
                          {field.key}
                        </label>
                        <div className="flex-1">
                          {field.type === 'boolean' ? (
                            <button
                              onClick={() => handleConfigChange(field.key, !currentValue)}
                              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                                currentValue
                                  ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                                  : 'bg-zinc-700 text-zinc-400 hover:bg-zinc-600'
                              }`}
                            >
                              {currentValue ? 'ON' : 'OFF'}
                            </button>
                          ) : field.type === 'number' ? (
                            <input
                              type="number"
                              value={currentValue as number}
                              onChange={(e) => handleConfigChange(field.key, Number(e.target.value))}
                              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-primary"
                            />
                          ) : field.type === 'array' ? (
                            <input
                              type="text"
                              value={Array.isArray(currentValue) ? (currentValue as string[]).join(', ') : String(currentValue ?? '')}
                              onChange={(e) => handleConfigChange(field.key, e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-primary"
                              placeholder="쉼표로 구분"
                            />
                          ) : (
                            <input
                              type="text"
                              value={String(currentValue ?? '')}
                              onChange={(e) => handleConfigChange(field.key, e.target.value)}
                              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-primary"
                            />
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
            <p className="text-[10px] text-zinc-600 text-center">런타임 설정 변경 — 서버 재시작 시 .env 기본값으로 복원됩니다</p>
          </div>
        )}
      </div>

      {/* ==================== 섹션 5: 일반 설정 ==================== */}
      <div>
        <SectionHeader icon={Settings} title="일반" open={showSettings} onToggle={() => setShowSettings(!showSettings)} />

        {showSettings && (
          <div className="space-y-4">
            {/* 채팅 설정 */}
            <div className="bg-dark-card border border-dark-border rounded-xl p-6">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold">대화 기록 초기화</div>
                  <div className="text-zinc-500 text-sm">현재 세션의 모든 대화 내용을 삭제합니다.</div>
                </div>
                <button
                  onClick={clearMessages}
                  className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
                >
                  초기화
                </button>
              </div>
            </div>

            {/* 버전 정보 */}
            <div className="text-center text-zinc-600 text-sm pt-2">
              JINXUS {jinxusVersion ? `v${jinxusVersion}` : ''} | Graph-based Autonomous Agent System | made by JINSOOKIM
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
