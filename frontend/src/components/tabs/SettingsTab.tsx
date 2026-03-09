'use client';

import { useState, useEffect } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { improveApi, ImproveHistoryItem, PromptVersion } from '@/lib/api';
import toast from 'react-hot-toast';
import {
  Settings, Server, Database, Zap, RefreshCw,
  Sparkles, History, ArrowDownToLine, Loader2,
  ChevronDown, ChevronUp,
} from 'lucide-react';

export default function SettingsTab() {
  const { systemStatus, loadSystemStatus, clearMessages, agents } = useAppStore();

  // 자가 강화
  const [improveHistory, setImproveHistory] = useState<ImproveHistoryItem[]>([]);
  const [improveLoading, setImproveLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [promptVersions, setPromptVersions] = useState<PromptVersion[]>([]);
  const [promptAgent, setPromptAgent] = useState<string>('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [activePromptVersion, setActivePromptVersion] = useState('');
  const [rollingBack, setRollingBack] = useState(false);
  const [showImprove, setShowImprove] = useState(false);

  const handleRefresh = () => loadSystemStatus();

  // 자가 강화 이력 로드
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

  // 수동 트리거
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

  // 프롬프트 버전 로드
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

  // 롤백
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
  }, [showImprove]);

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
          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">상태</div>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                systemStatus?.status === 'running' ? 'bg-green-400' : 'bg-red-400'
              }`}></span>
              <span className="font-semibold">
                {systemStatus?.status === 'running' ? '정상' : systemStatus?.status || '-'}
              </span>
            </div>
          </div>

          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">업타임</div>
            <div className="font-semibold">
              {systemStatus
                ? `${Math.floor(systemStatus.uptime_seconds / 3600)}h ${Math.floor((systemStatus.uptime_seconds % 3600) / 60)}m`
                : '-'}
            </div>
          </div>

          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">처리 작업</div>
            <div className="font-semibold">{systemStatus?.total_tasks_processed || 0}</div>
          </div>

          <div className="bg-dark-card border border-dark-border rounded-xl p-4">
            <div className="text-zinc-500 text-sm mb-1">활성 에이전트</div>
            <div className="font-semibold">{systemStatus?.active_agents?.length || 0}</div>
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
                <span className={`w-3 h-3 rounded-full ${
                  systemStatus?.redis_connected ? 'bg-green-400' : 'bg-red-400'
                }`}></span>
                <span className="text-sm">
                  {systemStatus?.redis_connected ? '연결됨' : '연결 안됨'}
                </span>
              </div>
            </div>
          </div>

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
                <span className={`w-3 h-3 rounded-full ${
                  systemStatus?.qdrant_connected ? 'bg-green-400' : 'bg-red-400'
                }`}></span>
                <span className="text-sm">
                  {systemStatus?.qdrant_connected ? '연결됨' : '연결 안됨'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 자가 강화 (JinxLoop) */}
      <div className="mb-8">
        <button
          onClick={() => setShowImprove(!showImprove)}
          className="w-full flex items-center justify-between text-lg font-semibold mb-4"
        >
          <span className="flex items-center gap-2">
            <Sparkles size={20} />
            자가 강화 (JinxLoop)
          </span>
          {showImprove ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
        </button>

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
                    <option key={a.name} value={a.name}>{a.name}</option>
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
                <History size={16} />
                프롬프트 버전 관리
              </h4>
              <div className="flex items-center gap-3 mb-3">
                <select
                  value={promptAgent}
                  onChange={(e) => loadPromptVersions(e.target.value)}
                  className="flex-1 bg-zinc-800 border border-zinc-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                >
                  <option value="">에이전트 선택</option>
                  {agents.map((a) => (
                    <option key={a.name} value={a.name}>{a.name}</option>
                  ))}
                </select>
              </div>

              {promptLoading ? (
                <div className="text-center py-4">
                  <Loader2 size={20} className="mx-auto animate-spin text-zinc-500" />
                </div>
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
                          <ArrowDownToLine size={12} />
                          롤백
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
                  <History size={16} />
                  A/B 테스트 이력
                </h4>
                <button
                  onClick={loadImproveHistory}
                  disabled={improveLoading}
                  className="p-1 rounded hover:bg-zinc-800 disabled:opacity-50"
                >
                  {improveLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                </button>
              </div>

              {improveHistory.length > 0 ? (
                <div className="space-y-2">
                  {improveHistory.map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-3 bg-zinc-800/50 rounded-lg">
                      <div>
                        <span className="font-mono text-sm">{item.agent_name}</span>
                        <span className="text-xs text-zinc-500 ml-2">{item.created_at}</span>
                      </div>
                      <div className="flex items-center gap-3 text-sm">
                        <span className="text-zinc-500">{item.old_score.toFixed(2)}</span>
                        <span className="text-zinc-600">→</span>
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
      </div>

      {/* 버전 정보 */}
      <div className="text-center text-zinc-600 text-sm">
        JINXUS v1.5.0 | Graph-based Autonomous Agent System | made by JINSOOKIM
      </div>
    </div>
  );
}
