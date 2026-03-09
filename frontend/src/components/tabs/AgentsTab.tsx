'use client';

import { useState, useEffect, useRef } from 'react';
import { UserPlus, RefreshCw } from 'lucide-react';
import { useAppStore } from '@/store/useAppStore';
import { agentApi, type AgentRuntimeStatus } from '@/lib/api';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import AgentCard from '../AgentCard';
import AgentGraph from '../AgentGraph';
import OrgChart from '../OrgChart';
import HireAgentModal from '../HireAgentModal';

export default function AgentsTab() {
  const { agents, loadAgents } = useAppStore();
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [showHireModal, setShowHireModal] = useState(false);
  const [viewMode, setViewMode] = useState<'cards' | 'org'>('cards');
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});

  const fetchAllRuntimes = async () => {
    try {
      const res = await agentApi.getAllRuntimeStatus();
      const map: Record<string, AgentRuntimeStatus> = {};
      for (const agent of res.agents) {
        map[agent.name] = agent;
      }
      setRuntimeMap(map);
    } catch (err) {
      console.error('Failed to fetch runtime statuses:', err);
    }
  };

  useEffect(() => {
    fetchAllRuntimes();
    const interval = setInterval(fetchAllRuntimes, POLLING_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAgentHired = () => {
    loadAgents();
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">에이전트 대시보드</h2>
          <p className="text-zinc-400 text-sm mt-1">
            JINXUS의 전문 에이전트들의 실시간 상태를 확인합니다.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* View Mode Toggle */}
          <div className="flex bg-zinc-900 rounded-lg p-1">
            <button
              onClick={() => setViewMode('cards')}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                viewMode === 'cards'
                  ? 'bg-zinc-700 text-white'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              카드 뷰
            </button>
            <button
              onClick={() => setViewMode('org')}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                viewMode === 'org'
                  ? 'bg-zinc-700 text-white'
                  : 'text-zinc-400 hover:text-white'
              }`}
            >
              조직도
            </button>
          </div>

          {/* Hire Agent Button */}
          <button
            onClick={() => setShowHireModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary/90 text-black rounded-lg text-sm font-medium transition-colors"
          >
            <UserPlus size={16} />
            새 에이전트 고용
          </button>
        </div>
      </div>

      {viewMode === 'cards' ? (
        <>
          {/* 에이전트 카드 그리드 */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
            {agents.map((agent) => (
              <AgentCard
                key={agent.name}
                agent={agent}
                runtime={runtimeMap[agent.name] || null}
                selected={selectedAgent === agent.name}
                onSelect={() => setSelectedAgent(
                  selectedAgent === agent.name ? null : agent.name
                )}
              />
            ))}
          </div>

          {/* 선택된 에이전트의 LangGraph 시각화 */}
          {selectedAgent && (
            <div className="mb-8">
              <AgentGraph agentName={selectedAgent} />
            </div>
          )}

          {/* 에이전트 설명 */}
          <div className="p-6 bg-dark-card border border-dark-border rounded-xl">
            <h3 className="font-semibold mb-4">에이전트 실행 로직</h3>
            <p className="text-zinc-400 text-sm mb-4">
              모든 에이전트는 다음 흐름을 따릅니다. 에이전트 카드를 클릭하면 실시간 실행 흐름을 확인할 수 있습니다.
            </p>
            <div className="flex items-center gap-2 text-sm text-zinc-300 overflow-x-auto pb-2">
              <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[receive]</span>
              <span className="text-zinc-600">-</span>
              <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[plan]</span>
              <span className="text-zinc-600">-</span>
              <span className="px-3 py-1 bg-blue-900 rounded-md whitespace-nowrap">[execute]</span>
              <span className="text-zinc-600">-</span>
              <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[evaluate]</span>
              <span className="text-zinc-600">-</span>
              <span className="px-3 py-1 bg-amber-900 rounded-md whitespace-nowrap">[reflect]</span>
              <span className="text-zinc-600">-</span>
              <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[memory_write]</span>
            </div>
            <p className="text-zinc-500 text-xs mt-3">
              * 최대 3회 재시도 (지수 백오프) / 실패 시 반성 후 장기기억 저장
            </p>
          </div>
        </>
      ) : (
        /* 조직도 뷰 */
        <OrgChart />
      )}

      {/* Hire Agent Modal */}
      <HireAgentModal
        isOpen={showHireModal}
        onClose={() => setShowHireModal(false)}
        onHired={handleAgentHired}
      />
    </div>
  );
}
