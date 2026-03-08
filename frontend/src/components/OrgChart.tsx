'use client';

import { useState, useEffect } from 'react';
import { Users, User, ChevronDown, ChevronRight } from 'lucide-react';
import { hrApi, type OrgNode, type OrgChartData } from '@/lib/api';

interface OrgNodeProps {
  node: OrgNode;
  depth?: number;
}

function OrgNodeComponent({ node, depth = 0 }: OrgNodeProps) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;

  const getRoleColor = (role: string) => {
    switch (role) {
      case 'ceo':
        return 'bg-yellow-500/20 border-yellow-500 text-yellow-400';
      case 'senior':
        return 'bg-blue-500/20 border-blue-500 text-blue-400';
      case 'junior':
        return 'bg-green-500/20 border-green-500 text-green-400';
      default:
        return 'bg-zinc-500/20 border-zinc-500 text-zinc-400';
    }
  };

  const getRoleLabel = (role: string) => {
    switch (role) {
      case 'ceo':
        return 'CEO';
      case 'senior':
        return 'Senior';
      case 'junior':
        return 'Junior';
      case 'intern':
        return 'Intern';
      default:
        return role;
    }
  };

  return (
    <div className="ml-4">
      <div
        className={`flex items-center gap-2 p-2 rounded-lg cursor-pointer hover:bg-dark-card transition-colors ${
          !node.is_active ? 'opacity-50' : ''
        }`}
        onClick={() => hasChildren && setExpanded(!expanded)}
      >
        {/* 확장 아이콘 */}
        <div className="w-4">
          {hasChildren && (
            expanded ? (
              <ChevronDown size={14} className="text-zinc-500" />
            ) : (
              <ChevronRight size={14} className="text-zinc-500" />
            )
          )}
        </div>

        {/* 노드 아이콘 */}
        <div className={`p-1.5 rounded border ${getRoleColor(node.role)}`}>
          {hasChildren ? <Users size={14} /> : <User size={14} />}
        </div>

        {/* 정보 */}
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-white text-sm">{node.name}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${getRoleColor(node.role)}`}>
              {getRoleLabel(node.role)}
            </span>
          </div>
          <p className="text-xs text-zinc-500">{node.specialty}</p>
        </div>

        {/* 상태 */}
        <div className={`w-2 h-2 rounded-full ${node.is_active ? 'bg-green-500' : 'bg-zinc-500'}`} />
      </div>

      {/* 자식 노드 */}
      {expanded && hasChildren && (
        <div className="border-l border-dark-border ml-4">
          {node.children.map((child) => (
            <OrgNodeComponent key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function OrgChart() {
  const [orgChart, setOrgChart] = useState<OrgChartData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchOrgChart = async () => {
      try {
        setLoading(true);
        const data = await hrApi.getOrgChart();
        setOrgChart(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch org chart');
      } finally {
        setLoading(false);
      }
    };

    fetchOrgChart();
  }, []);

  if (loading) {
    return (
      <div className="p-4 text-center text-zinc-500">
        조직도를 불러오는 중...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center text-red-400">
        {error}
      </div>
    );
  }

  if (!orgChart) {
    return null;
  }

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium text-white">조직도</h3>
        <div className="text-xs text-zinc-500">
          전체 {orgChart.total_agents}명 / 활성 {orgChart.active_agents}명
        </div>
      </div>

      <OrgNodeComponent node={orgChart.root} />
    </div>
  );
}
