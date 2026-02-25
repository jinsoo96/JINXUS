'use client';

import { useAppStore } from '@/store/useAppStore';
import { Bot, Code, Search, FileText, BarChart, Settings } from 'lucide-react';

const agentIcons: Record<string, React.ElementType> = {
  JX_CODER: Code,
  JX_RESEARCHER: Search,
  JX_WRITER: FileText,
  JX_ANALYST: BarChart,
  JX_OPS: Settings,
};

const agentColors: Record<string, string> = {
  JX_CODER: 'from-amber-500 to-amber-700',
  JX_RESEARCHER: 'from-yellow-600 to-yellow-800',
  JX_WRITER: 'from-orange-500 to-orange-700',
  JX_ANALYST: 'from-amber-600 to-amber-800',
  JX_OPS: 'from-stone-500 to-stone-700',
};

export default function AgentsTab() {
  const { agents } = useAppStore();

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">에이전트</h2>
      <p className="text-zinc-400 mb-8">
        JINXUS의 전문 에이전트들입니다. 각 에이전트는 특정 분야를 담당합니다.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map((agent) => {
          const Icon = agentIcons[agent.name] || Bot;
          const gradient = agentColors[agent.name] || 'from-zinc-500 to-zinc-700';

          return (
            <div
              key={agent.name}
              className="bg-dark-card border border-dark-border rounded-xl p-6 hover:border-primary transition-colors"
            >
              {/* 아이콘 */}
              <div
                className={`w-14 h-14 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center mb-4`}
              >
                <Icon size={28} className="text-white" />
              </div>

              {/* 이름 */}
              <h3 className="text-lg font-semibold mb-2">{agent.name}</h3>

              {/* 설명 */}
              <p className="text-zinc-400 text-sm mb-4">{agent.description}</p>

              {/* 기능 목록 */}
              {agent.capabilities && agent.capabilities.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {agent.capabilities.map((cap) => (
                    <span
                      key={cap}
                      className="px-2 py-1 bg-zinc-800 rounded-md text-xs text-zinc-400"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              )}

              {/* 상태 */}
              <div className="mt-4 pt-4 border-t border-dark-border flex items-center justify-between">
                <span className="flex items-center gap-2 text-sm text-green-400">
                  <span className="w-2 h-2 rounded-full bg-green-400"></span>
                  대기 중
                </span>
                <span className="text-xs text-zinc-500">LangGraph 패턴</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* 에이전트 설명 */}
      <div className="mt-8 p-6 bg-dark-card border border-dark-border rounded-xl">
        <h3 className="font-semibold mb-4">LangGraph 패턴</h3>
        <p className="text-zinc-400 text-sm mb-4">
          모든 에이전트는 다음 패턴을 따릅니다:
        </p>
        <div className="flex items-center gap-2 text-sm text-zinc-300 overflow-x-auto pb-2">
          <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[receive]</span>
          <span className="text-zinc-600">→</span>
          <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[plan]</span>
          <span className="text-zinc-600">→</span>
          <span className="px-3 py-1 bg-blue-900 rounded-md whitespace-nowrap">[execute]</span>
          <span className="text-zinc-600">→</span>
          <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[evaluate]</span>
          <span className="text-zinc-600">→</span>
          <span className="px-3 py-1 bg-amber-900 rounded-md whitespace-nowrap">[reflect]</span>
          <span className="text-zinc-600">→</span>
          <span className="px-3 py-1 bg-zinc-800 rounded-md whitespace-nowrap">[memory_write]</span>
        </div>
        <p className="text-zinc-500 text-xs mt-3">
          * 최대 3회 재시도 (지수 백오프) / 실패 시 반성 후 장기기억 저장
        </p>
      </div>
    </div>
  );
}
