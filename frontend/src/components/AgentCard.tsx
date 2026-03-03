'use client';

import { useState, useEffect } from 'react';
import { Bot, Loader2, AlertCircle, Wrench, Play, Pause } from 'lucide-react';
import { agentApi, type AgentRuntimeStatus } from '@/lib/api';
import type { AgentInfo } from '@/types';

interface AgentCardProps {
  agent: AgentInfo;
  onSelect?: () => void;
  selected?: boolean;
}

export default function AgentCard({ agent, onSelect, selected }: AgentCardProps) {
  const [runtime, setRuntime] = useState<AgentRuntimeStatus | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchRuntime = async () => {
      try {
        setLoading(true);
        const status = await agentApi.getRuntimeStatus(agent.name);
        setRuntime(status);
      } catch (err) {
        console.error('Failed to fetch runtime status:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchRuntime();

    // 3초 간격 자동 새로고침
    const interval = setInterval(fetchRuntime, 3000);
    return () => clearInterval(interval);
  }, [agent.name]);

  const getStatusColor = () => {
    if (!runtime) return 'bg-zinc-500';
    switch (runtime.status) {
      case 'working':
        return 'bg-blue-500';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-green-500';
    }
  };

  const getStatusIcon = () => {
    if (!runtime) return <Bot size={16} />;
    switch (runtime.status) {
      case 'working':
        return <Loader2 size={16} className="animate-spin" />;
      case 'error':
        return <AlertCircle size={16} />;
      default:
        return <Bot size={16} />;
    }
  };

  const formatAgentName = (name: string) => {
    return name.replace('JX_', '').replace('JINXUS_', '');
  };

  const getAgentRole = (name: string) => {
    const roles: Record<string, string> = {
      'JINXUS_CORE': '총괄 지휘관',
      'JX_CODER': '코딩 전문가',
      'JX_RESEARCHER': '리서치 전문가',
      'JX_WRITER': '작문 전문가',
      'JX_ANALYST': '데이터 분석가',
      'JX_OPS': '운영 전문가',
    };
    return roles[name] || '에이전트';
  };

  return (
    <div
      onClick={onSelect}
      className={`p-4 rounded-lg border transition-all cursor-pointer ${
        selected
          ? 'bg-primary/10 border-primary'
          : 'bg-dark-card border-dark-border hover:border-zinc-600'
      }`}
    >
      {/* 헤더 */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`p-1.5 rounded-md ${getStatusColor()}/20`}>
            {getStatusIcon()}
          </div>
          <div>
            <h3 className="font-medium text-white">{formatAgentName(agent.name)}</h3>
            <p className="text-xs text-zinc-500">{getAgentRole(agent.name)}</p>
          </div>
        </div>
        <div className={`w-2 h-2 rounded-full ${getStatusColor()}`} />
      </div>

      {/* 현재 상태 */}
      {runtime && runtime.status === 'working' && (
        <div className="mb-3 p-2 bg-blue-500/10 rounded-md">
          <p className="text-xs text-blue-300 truncate">
            {runtime.current_task || '작업 중...'}
          </p>
          {runtime.current_node && (
            <p className="text-xs text-blue-400 mt-1">
              단계: {runtime.current_node}
            </p>
          )}
        </div>
      )}

      {/* 에러 상태 */}
      {runtime && runtime.status === 'error' && (
        <div className="mb-3 p-2 bg-red-500/10 rounded-md">
          <p className="text-xs text-red-300 truncate">
            {runtime.error_message || '오류 발생'}
          </p>
        </div>
      )}

      {/* 현재 도구 */}
      {runtime && runtime.current_tools && runtime.current_tools.length > 0 && (
        <div className="mb-3">
          <p className="text-xs text-zinc-500 mb-1 flex items-center gap-1">
            <Wrench size={10} /> 사용 중인 도구
          </p>
          <div className="flex flex-wrap gap-1">
            {runtime.current_tools.map((tool) => (
              <span
                key={tool}
                className="px-1.5 py-0.5 text-xs bg-zinc-700 rounded text-zinc-300"
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 성능 지표 */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="p-2 bg-dark-bg rounded">
          <p className="text-zinc-500">성공률</p>
          <p className="text-white font-medium">
            {(agent.success_rate * 100).toFixed(0)}%
          </p>
        </div>
        <div className="p-2 bg-dark-bg rounded">
          <p className="text-zinc-500">총 작업</p>
          <p className="text-white font-medium">{agent.total_tasks}</p>
        </div>
      </div>

      {/* 버전 */}
      <div className="mt-2 text-xs text-zinc-600 text-right">
        {agent.prompt_version}
      </div>
    </div>
  );
}
