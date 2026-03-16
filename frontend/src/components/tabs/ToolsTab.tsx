'use client';

import { useState, useEffect, useMemo } from 'react';
import {
  systemApi, pluginsApi, PluginInfo, MCPStatus, ToolGraphData, ToolsListResponse, NativeTool,
  ToolCallLog, ToolPoliciesResponse, ToolAnalyticsResponse,
} from '@/lib/api';
import toast from 'react-hot-toast';
import {
  Plug, Wrench, RefreshCw, CheckCircle, AlertCircle,
  XCircle, Key, Loader2, ChevronDown, ChevronUp,
  Network, Search, ScrollText, Shield,
  BarChart2, Package, ToggleLeft, ToggleRight, Plus, Trash2,
} from 'lucide-react';

type TabId = 'mcp' | 'native' | 'graph' | 'tool-logs' | 'policies' | 'analytics' | 'plugins';

// ── ToolGraph 시각화 상수 ──
const GRAPH_W = 800, GRAPH_H = 600, GRAPH_CX = 400, GRAPH_CY = 295, GRAPH_R = 215, GRAPH_NR = 24;
const GRAPH_CAT_COLORS: Record<string, { fill: string; stroke: string }> = {
  development: { fill: 'rgba(59,130,246,0.15)',  stroke: '#3b82f6' },
  research:    { fill: 'rgba(139,92,246,0.15)',   stroke: '#8b5cf6' },
  github:      { fill: 'rgba(113,113,122,0.15)',  stroke: '#71717a' },
  filesystem:  { fill: 'rgba(34,197,94,0.15)',    stroke: '#22c55e' },
  automation:  { fill: 'rgba(245,158,11,0.15)',   stroke: '#f59e0b' },
  system:      { fill: 'rgba(239,68,68,0.15)',    stroke: '#ef4444' },
  management:  { fill: 'rgba(6,182,212,0.15)',    stroke: '#06b6d4' },
};
const GRAPH_EDGE_COLORS: Record<string, string> = {
  precedes:       '#3b82f6',
  requires:       '#ef4444',
  similar_to:     '#22c55e',
  complementary:  '#a78bfa',
  conflicts_with: '#f59e0b',
  conflicts:      '#f59e0b',
  belongs_to:     '#71717a',
};

export default function ToolsTab() {
  const [activeTab, setActiveTab] = useState<TabId>('mcp');

  // MCP
  const [mcpStatus, setMcpStatus] = useState<MCPStatus | null>(null);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [reconnecting, setReconnecting] = useState<string | null>(null);
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());

  // 네이티브 도구
  const [toolsList, setToolsList] = useState<ToolsListResponse | null>(null);
  const [toolsLoading, setToolsLoading] = useState(false);

  // ToolGraph
  const [toolGraph, setToolGraph] = useState<ToolGraphData | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResult, setSearchResult] = useState<{ query: string; tools: { name: string; description: string; category: string }[] } | null>(null);
  const [searching, setSearching] = useState(false);

  // 도구 호출 로그
  const [toolLogs, setToolLogs] = useState<ToolCallLog[]>([]);
  const [toolLogsLoading, setToolLogsLoading] = useState(false);

  // 도구 정책
  const [toolPolicies, setToolPolicies] = useState<ToolPoliciesResponse | null>(null);
  const [policiesLoading, setPoliciesLoading] = useState(false);
  const [graphSelectedNode, setGraphSelectedNode] = useState<string | null>(null);

  // 도구 통계 (analytics)
  const [analytics, setAnalytics] = useState<ToolAnalyticsResponse | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  // 플러그인
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [pluginsLoading, setPluginsLoading] = useState(false);
  const [togglingPlugin, setTogglingPlugin] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);

  // MCP 서버 추가 폼
  const [showAddMCP, setShowAddMCP] = useState(false);
  const [newMCP, setNewMCP] = useState({ name: '', args: '', env: '', description: '', allowed_agents: '' });
  const [addingMCP, setAddingMCP] = useState(false);

  const handleAddMCP = async () => {
    if (!newMCP.name || !newMCP.args) { toast.error('이름과 패키지를 입력하세요'); return; }
    setAddingMCP(true);
    try {
      const envObj: Record<string, string> = {};
      if (newMCP.env) {
        newMCP.env.split(',').forEach(kv => {
          const [k, v] = kv.split('=').map(s => s.trim());
          if (k && v) envObj[k] = v;
        });
      }
      const result = await systemApi.addMCPServer({
        name: newMCP.name.trim(),
        args: ['-y', ...newMCP.args.trim().split(/\s+/)],
        env: Object.keys(envObj).length > 0 ? envObj : undefined,
        description: newMCP.description || undefined,
        allowed_agents: newMCP.allowed_agents ? newMCP.allowed_agents.split(',').map(s => s.trim()) : undefined,
      });
      if (result.success) {
        toast.success(`${result.server_name}: ${result.tools_count}개 도구 등록`);
        setNewMCP({ name: '', args: '', env: '', description: '', allowed_agents: '' });
        setShowAddMCP(false);
        loadMCPStatus();
      } else {
        toast.error(result.message || '추가 실패');
      }
    } catch (err) {
      toast.error(`MCP 서버 추가 실패: ${err instanceof Error ? err.message : '알 수 없는 오류'}`);
    } finally {
      setAddingMCP(false);
    }
  };

  const handleRemoveMCP = async (name: string) => {
    if (!confirm(`'${name}' 서버를 제거하시겠습니까?`)) return;
    try {
      const result = await systemApi.removeMCPServer(name);
      if (result.success) {
        toast.success(result.message);
        loadMCPStatus();
      }
    } catch { toast.error('제거 실패'); }
  };

  // 정책 편집
  const [editingPolicy, setEditingPolicy] = useState<string | null>(null);
  const [policyBlacklist, setPolicyBlacklist] = useState('');
  const [policyNewTool, setPolicyNewTool] = useState('');

  const handleSavePolicy = async (agentName: string, blacklist: string[]) => {
    try {
      await systemApi.updateToolPolicy(agentName, { blacklist });
      toast.success(`${agentName} 정책 업데이트 완료`);
      setEditingPolicy(null);
      loadToolPolicies();
    } catch { toast.error('정책 업데이트 실패'); }
  };

  const handleToggleAllowAll = async (agentName: string, currentWhitelist: string[] | null) => {
    try {
      if (currentWhitelist === null) {
        // 모든 도구 허용 → 기본 whitelist로 전환
        await systemApi.updateToolPolicy(agentName, { whitelist: [], allow_all: false });
      } else {
        await systemApi.updateToolPolicy(agentName, { allow_all: true });
      }
      toast.success(`${agentName} 정책 변경됨`);
      loadToolPolicies();
    } catch { toast.error('정책 변경 실패'); }
  };

  // 엣지가 있는 노드만 (MCP 포함 전체 노드 중 연결된 것만 표시)
  const visibleNodes = useMemo(() => {
    if (!toolGraph) return [];
    const connected = new Set<string>();
    toolGraph.edges.forEach(e => { connected.add(e.source); connected.add(e.target); });
    if (connected.size === 0) return toolGraph.nodes.filter(n => !n.name.startsWith('mcp:'));
    return toolGraph.nodes.filter(n => connected.has(n.name));
  }, [toolGraph]);

  // 노드 위치 (원형 레이아웃 — visibleNodes 기준)
  const nodePositions = useMemo<Record<string, { x: number; y: number }>>(() => {
    const pos: Record<string, { x: number; y: number }> = {};
    visibleNodes.forEach((node, i) => {
      const angle = (2 * Math.PI * i / visibleNodes.length) - Math.PI / 2;
      pos[node.name] = {
        x: GRAPH_CX + GRAPH_R * Math.cos(angle),
        y: GRAPH_CY + GRAPH_R * Math.sin(angle),
      };
    });
    return pos;
  }, [visibleNodes]);

  // ── MCP ──
  const loadMCPStatus = async () => {
    setMcpLoading(true);
    try {
      const status = await systemApi.getMCPStatus();
      setMcpStatus(status);
    } catch (error) {
      console.error('MCP 상태 조회 실패:', error);
      toast.error('MCP 상태 조회 실패');
    } finally {
      setMcpLoading(false);
    }
  };

  const handleReconnect = async (serverName: string) => {
    setReconnecting(serverName);
    try {
      await systemApi.reconnectMCP(serverName);
      await loadMCPStatus();
      toast.success(`${serverName} 재연결 성공`);
    } catch (error) {
      console.error('MCP 재연결 실패:', error);
      toast.error('MCP 재연결 실패');
    } finally {
      setReconnecting(null);
    }
  };

  const toggleExpand = (serverName: string) => {
    const newExpanded = new Set(expandedServers);
    if (newExpanded.has(serverName)) {
      newExpanded.delete(serverName);
    } else {
      newExpanded.add(serverName);
    }
    setExpandedServers(newExpanded);
  };

  // ── 네이티브 도구 ──
  const loadTools = async () => {
    setToolsLoading(true);
    try {
      const data = await systemApi.getTools();
      setToolsList(data);
    } catch (error) {
      console.error('도구 목록 조회 실패:', error);
      toast.error('도구 목록 조회 실패');
    } finally {
      setToolsLoading(false);
    }
  };

  // ── ToolGraph ──
  const loadToolGraph = async () => {
    setGraphLoading(true);
    try {
      const data = await systemApi.getToolGraph();
      setToolGraph(data);
    } catch (error) {
      console.error('ToolGraph 조회 실패:', error);
      toast.error('ToolGraph 조회 실패');
    } finally {
      setGraphLoading(false);
    }
  };

  const handleGraphSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const result = await systemApi.retrieveWorkflow(searchQuery.trim());
      setSearchResult({ query: result.query, tools: result.tools });
    } catch (error) {
      console.error('워크플로우 탐색 실패:', error);
      toast.error('워크플로우 탐색 실패');
    } finally {
      setSearching(false);
    }
  };

  // ── 도구 호출 로그 ──
  const loadToolLogs = async () => {
    setToolLogsLoading(true);
    try {
      const data = await systemApi.getToolLogs(50);
      setToolLogs(data.logs);
    } catch (error) {
      console.error('도구 호출 로그 조회 실패:', error);
      toast.error('도구 호출 로그 조회 실패');
    } finally {
      setToolLogsLoading(false);
    }
  };

  // ── 도구 통계 ──
  const loadAnalytics = async () => {
    setAnalyticsLoading(true);
    try {
      const data = await systemApi.getToolAnalytics();
      setAnalytics(data);
    } catch (error) {
      console.error('도구 통계 조회 실패:', error);
      toast.error('도구 통계 조회 실패');
    } finally {
      setAnalyticsLoading(false);
    }
  };

  // ── 플러그인 ──
  const loadPlugins = async () => {
    setPluginsLoading(true);
    try {
      const data = await pluginsApi.getAll();
      setPlugins(data.plugins);
    } catch (error) {
      console.error('플러그인 목록 조회 실패:', error);
      toast.error('플러그인 목록 조회 실패');
    } finally {
      setPluginsLoading(false);
    }
  };

  const handleTogglePlugin = async (name: string, currentEnabled: boolean) => {
    setTogglingPlugin(name);
    try {
      if (currentEnabled) {
        await pluginsApi.disable(name);
        toast.success(`${name} 비활성화됨`);
      } else {
        await pluginsApi.enable(name);
        toast.success(`${name} 활성화됨`);
      }
      await loadPlugins();
    } catch (error) {
      console.error('플러그인 토글 실패:', error);
      toast.error('플러그인 토글 실패');
    } finally {
      setTogglingPlugin(null);
    }
  };

  const handleReloadPlugins = async () => {
    setReloading(true);
    try {
      const result = await pluginsApi.reload();
      toast.success(`플러그인 ${result.loaded_count}개 재로드됨`);
      await loadPlugins();
    } catch (error) {
      console.error('플러그인 재로드 실패:', error);
      toast.error('플러그인 재로드 실패');
    } finally {
      setReloading(false);
    }
  };

  // ── 도구 정책 ──
  const loadToolPolicies = async () => {
    setPoliciesLoading(true);
    try {
      const data = await systemApi.getToolPolicies();
      setToolPolicies(data);
    } catch (error) {
      console.error('도구 정책 조회 실패:', error);
      toast.error('도구 정책 조회 실패');
    } finally {
      setPoliciesLoading(false);
    }
  };

  // ── 초기 로드 ──
  useEffect(() => {
    loadMCPStatus();
  }, []);

  useEffect(() => {
    if (activeTab === 'native' && !toolsList) loadTools();
    if (activeTab === 'graph' && !toolGraph) loadToolGraph();
    if (activeTab === 'tool-logs') loadToolLogs();
    if (activeTab === 'policies' && !toolPolicies) loadToolPolicies();
    if (activeTab === 'analytics') loadAnalytics();
    if (activeTab === 'plugins') loadPlugins();
  }, [activeTab]);

  // 도구 호출 로그 자동 갱신 (5초)
  useEffect(() => {
    if (activeTab !== 'tool-logs') return;
    const interval = setInterval(loadToolLogs, 5000);
    return () => clearInterval(interval);
  }, [activeTab]);

  // ── 헬퍼 ──
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <CheckCircle size={20} className="text-green-400" />;
      case 'api_key_missing':
        return <Key size={20} className="text-amber-400" />;
      case 'disabled':
        return <XCircle size={20} className="text-zinc-500" />;
      default:
        return <AlertCircle size={20} className="text-red-400" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'connected':
        return <span className="px-2 py-1 text-xs rounded-full bg-green-500/20 text-green-400">연결됨</span>;
      case 'api_key_missing':
        return <span className="px-2 py-1 text-xs rounded-full bg-amber-500/20 text-amber-400">API 키 필요</span>;
      case 'disabled':
        return <span className="px-2 py-1 text-xs rounded-full bg-zinc-500/20 text-zinc-400">비활성화</span>;
      default:
        return <span className="px-2 py-1 text-xs rounded-full bg-red-500/20 text-red-400">연결 실패</span>;
    }
  };

  const getStatusBgColor = (status: string) => {
    switch (status) {
      case 'connected': return 'bg-green-500/10';
      case 'api_key_missing': return 'bg-amber-500/10';
      case 'disabled': return 'bg-zinc-500/10';
      default: return 'bg-red-500/10';
    }
  };

  const getCategoryColor = (category: string) => {
    const colors: Record<string, string> = {
      development: 'bg-blue-500/20 text-blue-400',
      research: 'bg-purple-500/20 text-purple-400',
      github: 'bg-zinc-500/20 text-zinc-300',
      filesystem: 'bg-green-500/20 text-green-400',
      automation: 'bg-amber-500/20 text-amber-400',
      system: 'bg-red-500/20 text-red-400',
      management: 'bg-cyan-500/20 text-cyan-400',
    };
    return colors[category] || 'bg-zinc-500/20 text-zinc-400';
  };

  const tabs: { id: TabId; label: string; icon: typeof Plug; count?: number }[] = [
    { id: 'mcp', label: 'MCP 서버', icon: Plug, count: mcpStatus?.connected_count },
    { id: 'native', label: '네이티브 도구', icon: Wrench, count: toolsList?.native_count },
    { id: 'graph', label: 'ToolGraph', icon: Network, count: toolGraph?.nodes.length },
    { id: 'tool-logs', label: '도구 로그', icon: ScrollText, count: toolLogs.length || undefined },
    { id: 'analytics', label: '통계', icon: BarChart2, count: analytics?.total_tools },
    { id: 'plugins', label: '플러그인', icon: Package, count: plugins.length || undefined },
    { id: 'policies', label: '정책', icon: Shield },
  ];

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">도구</h2>

      {/* 탭 네비게이션 */}
      <div className="flex gap-2 mb-6 border-b border-dark-border pb-3">
        {tabs.map(tab => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-colors ${
                activeTab === tab.id
                  ? 'bg-primary text-white'
                  : 'text-zinc-400 hover:bg-zinc-800 hover:text-white'
              }`}
            >
              <Icon size={16} />
              {tab.label}
              {tab.count !== undefined && (
                <span className={`px-1.5 py-0.5 text-xs rounded-full ${
                  activeTab === tab.id ? 'bg-white/20' : 'bg-zinc-700'
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ═══ MCP 서버 탭 ═══ */}
      {activeTab === 'mcp' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4 text-sm text-zinc-500">
              {mcpStatus && (
                <>
                  <span className="flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-green-400"></span>
                    {mcpStatus.connected_count}개 연결
                  </span>
                  <span>전체 {mcpStatus.total_configured}개</span>
                  <span>도구 {mcpStatus.total_tools}개</span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowAddMCP(!showAddMCP)}
                className="flex items-center gap-1 px-3 py-1.5 bg-primary hover:bg-primary/90 text-black rounded-lg text-xs font-medium transition-colors"
              >
                <Plus size={14} />
                서버 추가
              </button>
              <button
                onClick={loadMCPStatus}
                disabled={mcpLoading}
                className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
              >
                {mcpLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
              </button>
            </div>
          </div>

          {/* MCP 서버 추가 폼 */}
          {showAddMCP && (
            <div className="bg-dark-card border border-primary/30 rounded-xl p-4 mb-4">
              <h4 className="text-sm font-semibold text-white mb-3">MCP 서버 추가</h4>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="text-zinc-500 block mb-1">서버 이름 *</label>
                  <input value={newMCP.name} onChange={e => setNewMCP(p => ({...p, name: e.target.value}))}
                    placeholder="예: firecrawl" className="w-full bg-zinc-900 border border-dark-border rounded px-2 py-1.5 text-white" />
                </div>
                <div>
                  <label className="text-zinc-500 block mb-1">npm 패키지 / 명령 *</label>
                  <input value={newMCP.args} onChange={e => setNewMCP(p => ({...p, args: e.target.value}))}
                    placeholder="예: firecrawl-mcp" className="w-full bg-zinc-900 border border-dark-border rounded px-2 py-1.5 text-white" />
                </div>
                <div>
                  <label className="text-zinc-500 block mb-1">환경변수 (KEY=VALUE, 쉼표 구분)</label>
                  <input value={newMCP.env} onChange={e => setNewMCP(p => ({...p, env: e.target.value}))}
                    placeholder="예: API_KEY=sk-xxx" className="w-full bg-zinc-900 border border-dark-border rounded px-2 py-1.5 text-white" />
                </div>
                <div>
                  <label className="text-zinc-500 block mb-1">허용 에이전트 (쉼표 구분, 비우면 전체)</label>
                  <input value={newMCP.allowed_agents} onChange={e => setNewMCP(p => ({...p, allowed_agents: e.target.value}))}
                    placeholder="예: JX_RESEARCHER,JX_OPS" className="w-full bg-zinc-900 border border-dark-border rounded px-2 py-1.5 text-white" />
                </div>
                <div className="col-span-2">
                  <label className="text-zinc-500 block mb-1">설명</label>
                  <input value={newMCP.description} onChange={e => setNewMCP(p => ({...p, description: e.target.value}))}
                    placeholder="예: 웹 크롤링 도구" className="w-full bg-zinc-900 border border-dark-border rounded px-2 py-1.5 text-white" />
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-3">
                <button onClick={() => setShowAddMCP(false)} className="px-3 py-1.5 text-xs text-zinc-400 hover:text-white transition-colors">취소</button>
                <button onClick={handleAddMCP} disabled={addingMCP}
                  className="px-4 py-1.5 bg-primary hover:bg-primary/90 text-black rounded text-xs font-medium disabled:opacity-50 flex items-center gap-1">
                  {addingMCP ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                  연결 및 추가
                </button>
              </div>
            </div>
          )}

          {mcpStatus ? (
            <div className="space-y-3">
              {mcpStatus.servers.length === 0 ? (
                <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center text-zinc-500">
                  <Plug size={32} className="mx-auto mb-2 opacity-50" />
                  <div>설정된 MCP 서버가 없습니다</div>
                </div>
              ) : (
                mcpStatus.servers.map((server) => (
                  <div
                    key={server.name}
                    className={`bg-dark-card border border-dark-border rounded-xl overflow-hidden ${getStatusBgColor(server.status)}`}
                  >
                    <div
                      className="p-4 flex items-center justify-between cursor-pointer hover:bg-zinc-800/30 transition-colors"
                      onClick={() => server.status === 'connected' && toggleExpand(server.name)}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                          server.status === 'connected' ? 'bg-green-500/20' :
                          server.status === 'api_key_missing' ? 'bg-amber-500/20' :
                          server.status === 'disabled' ? 'bg-zinc-500/20' : 'bg-red-500/20'
                        }`}>
                          {getStatusIcon(server.status)}
                        </div>
                        <div>
                          <div className="font-semibold flex items-center gap-2">
                            {server.name}
                            {server.requires_api_key && (
                              <span title={`${server.requires_api_key} 필요`}>
                                <Key size={12} className="text-zinc-500" />
                              </span>
                            )}
                          </div>
                          <div className="text-zinc-500 text-sm">{server.description}</div>
                          {server.status === 'connected' && (
                            <div className="text-zinc-600 text-xs mt-0.5">
                              도구 {server.tools_count}개 사용 가능
                            </div>
                          )}
                          {server.error && server.status !== 'connected' && (
                            <div className="text-red-400/80 text-xs mt-0.5">{server.error}</div>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        {getStatusBadge(server.status)}
                        {server.status === 'disconnected' && server.has_api_key !== false && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleReconnect(server.name); }}
                            disabled={reconnecting === server.name}
                            className="px-3 py-1 text-sm bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors disabled:opacity-50"
                          >
                            {reconnecting === server.name ? <Loader2 size={14} className="animate-spin" /> : '재연결'}
                          </button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); handleRemoveMCP(server.name); }}
                          className="px-2 py-1 text-xs bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition-colors"
                          title="서버 제거"
                        >
                          <Trash2 size={12} />
                        </button>
                        {server.status === 'connected' && server.tools.length > 0 && (
                          expandedServers.has(server.name) ? <ChevronUp size={18} className="text-zinc-500" /> : <ChevronDown size={18} className="text-zinc-500" />
                        )}
                      </div>
                    </div>

                    {server.status === 'connected' && expandedServers.has(server.name) && server.tools.length > 0 && (
                      <div className="px-4 pb-4 pt-0 border-t border-dark-border/50">
                        <div className="flex items-center gap-1 text-zinc-500 text-sm mb-2 mt-3">
                          <Wrench size={14} />
                          사용 가능한 도구
                        </div>
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                          {server.tools.map((tool) => (
                            <div
                              key={tool.name}
                              className="px-3 py-2 text-sm bg-zinc-800/50 rounded-lg text-zinc-300 hover:bg-zinc-700/50 cursor-default"
                              title={tool.description}
                            >
                              <div className="font-medium truncate">{tool.name}</div>
                              <div className="text-xs text-zinc-500 truncate">{tool.description}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          ) : mcpLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
              <div className="text-zinc-500 mt-2">MCP 상태 확인 중...</div>
            </div>
          ) : null}
        </div>
      )}

      {/* ═══ 네이티브 도구 탭 ═══ */}
      {activeTab === 'native' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-500">
              JINXUS 자체 등록 도구 (TOOL_REGISTRY)
            </p>
            <button
              onClick={loadTools}
              disabled={toolsLoading}
              className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              {toolsLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
          </div>

          {toolsList ? (
            <div className="space-y-3">
              {toolsList.native_tools.map((tool) => (
                <div key={tool.name} className="bg-dark-card border border-dark-border rounded-xl p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                        <Wrench size={20} className="text-blue-400" />
                      </div>
                      <div>
                        <div className="font-semibold font-mono">{tool.name}</div>
                        <div className="text-zinc-500 text-sm">{tool.description}</div>
                        {tool.allowed_agents.length > 0 && (
                          <div className="flex gap-1 mt-1">
                            {tool.allowed_agents.map((a: string) => (
                              <span key={a} className="px-1.5 py-0.5 text-xs rounded bg-zinc-700 text-zinc-400">
                                {a}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <span className={`px-2 py-1 text-xs rounded-full ${
                      tool.enabled ? 'bg-green-500/20 text-green-400' : 'bg-zinc-500/20 text-zinc-400'
                    }`}>
                      {tool.enabled ? '활성' : '비활성'}
                    </span>
                  </div>
                </div>
              ))}

              <div className="text-sm text-zinc-600 text-center mt-4">
                네이티브 {toolsList.native_count}개 + MCP {toolsList.mcp_count}개 = 총 {toolsList.total}개
              </div>
            </div>
          ) : toolsLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
            </div>
          ) : null}
        </div>
      )}

      {/* ═══ ToolGraph 탭 ═══ */}
      {activeTab === 'graph' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-500">
              BM25 + wRRF 기반 도구 관계 그래프
            </p>
            <button
              onClick={loadToolGraph}
              disabled={graphLoading}
              className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              {graphLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
          </div>

          {/* 워크플로우 탐색 */}
          <div className="bg-dark-card border border-dark-border rounded-xl p-4 mb-4">
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleGraphSearch()}
                placeholder="쿼리 입력하여 워크플로우 탐색 (예: 코드 짜고 PR 올려줘)"
                className="flex-1 bg-zinc-800 border border-zinc-600 rounded-lg px-4 py-2 text-sm focus:outline-none focus:border-primary"
              />
              <button
                onClick={handleGraphSearch}
                disabled={searching || !searchQuery.trim()}
                className="px-4 py-2 bg-primary text-white rounded-lg text-sm hover:bg-primary/80 disabled:opacity-50 flex items-center gap-2"
              >
                {searching ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                탐색
              </button>
            </div>

            {searchResult && (
              <div className="mt-3 pt-3 border-t border-zinc-700">
                <div className="text-xs text-zinc-500 mb-2">
                  &quot;{searchResult.query}&quot; 워크플로우:
                </div>
                {searchResult.tools.length > 0 ? (
                  <div className="flex items-center gap-2 flex-wrap">
                    {searchResult.tools.map((tool, i) => (
                      <div key={tool.name} className="flex items-center gap-2">
                        <span className={`px-3 py-1.5 rounded-lg text-sm ${getCategoryColor(tool.category)}`}>
                          {tool.name}
                        </span>
                        {i < searchResult.tools.length - 1 && (
                          <span className="text-zinc-600">→</span>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-zinc-500 text-sm">관련 도구를 찾을 수 없습니다</div>
                )}
              </div>
            )}
          </div>

          {/* 그래프 시각화 */}
          {toolGraph ? (
            <div>
              {/* SVG 그래프 */}
              <div className="bg-zinc-900/50 border border-dark-border rounded-xl overflow-hidden mb-4">
                <div className="px-4 py-2 border-b border-dark-border flex items-center justify-between">
                  <span className="text-xs text-zinc-500">
                    {visibleNodes.length}개 노드 · {toolGraph.edges.length}개 엣지
                    {graphSelectedNode ? ` — ${graphSelectedNode} 선택됨` : ' — 노드 클릭으로 연결 하이라이트'}
                  </span>
                  {graphSelectedNode && (
                    <button onClick={() => setGraphSelectedNode(null)} className="text-xs text-zinc-500 hover:text-white underline">
                      선택 해제
                    </button>
                  )}
                </div>
                <div className="overflow-x-auto">
                  <svg
                    width={GRAPH_W} height={GRAPH_H}
                    viewBox={`0 0 ${GRAPH_W} ${GRAPH_H}`}
                    style={{ minWidth: 600, display: 'block' }}
                  >
                    <defs>
                      {Object.entries(GRAPH_EDGE_COLORS).map(([t, c]) => (
                        <marker key={t} id={`garr-${t}`} viewBox="0 0 10 10" refX="9" refY="5"
                          markerWidth="5" markerHeight="5" orient="auto">
                          <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
                        </marker>
                      ))}
                    </defs>

                    {/* Edges */}
                    {toolGraph.edges.map((edge, i) => {
                      const s = nodePositions[edge.source];
                      const tgt = nodePositions[edge.target];
                      if (!s || !tgt) return null;
                      const dx = tgt.x - s.x, dy = tgt.y - s.y;
                      const len = Math.sqrt(dx * dx + dy * dy) || 1;
                      const nx = dx / len, ny = dy / len;
                      const dim = !!(graphSelectedNode &&
                        edge.source !== graphSelectedNode &&
                        edge.target !== graphSelectedNode);
                      const color = GRAPH_EDGE_COLORS[edge.type] ?? '#71717a';
                      return (
                        <line key={i}
                          x1={s.x + nx * GRAPH_NR} y1={s.y + ny * GRAPH_NR}
                          x2={tgt.x - nx * (GRAPH_NR + 6)} y2={tgt.y - ny * (GRAPH_NR + 6)}
                          stroke={color}
                          strokeWidth={dim ? 0.5 : 1.5}
                          opacity={dim ? 0.1 : 0.65}
                          markerEnd={`url(#garr-${edge.type})`}
                        />
                      );
                    })}

                    {/* Nodes */}
                    {visibleNodes.map((node) => {
                      const pos = nodePositions[node.name];
                      if (!pos) return null;
                      const c = GRAPH_CAT_COLORS[node.category] ?? { fill: 'rgba(113,113,122,0.15)', stroke: '#71717a' };
                      const sel = graphSelectedNode === node.name;
                      const conn = graphSelectedNode
                        ? toolGraph.edges.some(e =>
                            (e.source === graphSelectedNode && e.target === node.name) ||
                            (e.target === graphSelectedNode && e.source === node.name))
                        : false;
                      const dim = !!(graphSelectedNode && !sel && !conn);
                      // 2줄 레이블
                      const words = node.name.split('_');
                      const line1 = words[0];
                      const line2 = words.length > 1 ? words.slice(1).join(' ').slice(0, 10) : null;
                      return (
                        <g key={node.name}
                          onClick={() => setGraphSelectedNode(sel ? null : node.name)}
                          style={{ cursor: 'pointer' }}
                          opacity={dim ? 0.2 : 1}
                        >
                          {sel && <circle cx={pos.x} cy={pos.y} r={GRAPH_NR + 9} fill="none" stroke="#ffffff" strokeWidth={1.5} opacity={0.2} />}
                          {conn && <circle cx={pos.x} cy={pos.y} r={GRAPH_NR + 5} fill="none" stroke={c.stroke} strokeWidth={1} opacity={0.4} />}
                          <circle cx={pos.x} cy={pos.y} r={GRAPH_NR} fill={c.fill} stroke={c.stroke} strokeWidth={sel ? 2.5 : 1.5} />
                          <title>{node.name}: {node.description}</title>
                          <text textAnchor="middle" fontSize={8.5} fill="#a1a1aa">
                            <tspan x={pos.x} y={pos.y + GRAPH_NR + 12}>{line1}</tspan>
                            {line2 && <tspan x={pos.x} dy={11}>{line2}</tspan>}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>
                {/* 엣지 범례 (중복 제거) */}
                <div className="px-4 py-2 border-t border-dark-border flex flex-wrap gap-4">
                  {Object.entries(GRAPH_EDGE_COLORS)
                    .filter(([t]) => t !== 'conflicts')
                    .map(([type, color]) => (
                      <div key={type} className="flex items-center gap-1.5 text-xs text-zinc-500">
                        <div className="h-px w-5" style={{ backgroundColor: color }} />
                        {type.replace('_', ' ')}
                      </div>
                    ))}
                </div>
              </div>

              {/* 엣지 상세 */}
              <h4 className="text-sm font-semibold text-zinc-400 mb-3">
                엣지 ({toolGraph.edges.length}개)
              </h4>
              <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-dark-border text-zinc-500">
                      <th className="text-left p-3">출발</th>
                      <th className="text-left p-3">도착</th>
                      <th className="text-left p-3">관계</th>
                      <th className="text-right p-3">가중치</th>
                    </tr>
                  </thead>
                  <tbody>
                    {toolGraph.edges.map((edge, i) => (
                      <tr key={i} className="border-b border-dark-border/50 hover:bg-zinc-800/30"
                        onClick={() => setGraphSelectedNode(
                          graphSelectedNode === edge.source || graphSelectedNode === edge.target
                            ? null : edge.source
                        )}
                        style={{ cursor: 'pointer' }}
                      >
                        <td className="p-3 font-mono text-xs">{edge.source}</td>
                        <td className="p-3 font-mono text-xs">{edge.target}</td>
                        <td className="p-3">
                          <span className="px-2 py-0.5 text-xs rounded-full"
                            style={{
                              backgroundColor: `${GRAPH_EDGE_COLORS[edge.type] ?? '#71717a'}25`,
                              color: GRAPH_EDGE_COLORS[edge.type] ?? '#a1a1aa',
                            }}>
                            {edge.type}
                          </span>
                        </td>
                        <td className={`p-3 text-right font-mono text-xs ${edge.weight !== 1.0 ? 'text-amber-400' : 'text-zinc-500'}`}>
                          {edge.weight.toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : graphLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
            </div>
          ) : null}
        </div>
      )}

      {/* ═══ 도구 호출 로그 탭 ═══ */}
      {activeTab === 'tool-logs' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-500">
              실시간 도구 호출 로그 (최근 100건, 5초 자동 갱신)
            </p>
            <button
              onClick={loadToolLogs}
              disabled={toolLogsLoading}
              className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              {toolLogsLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
          </div>

          {toolLogs.length > 0 ? (
            <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-dark-border text-zinc-500">
                    <th className="text-left p-3">시간 (KST)</th>
                    <th className="text-left p-3">에이전트</th>
                    <th className="text-left p-3">도구</th>
                    <th className="text-left p-3">상태</th>
                    <th className="text-right p-3">소요 시간</th>
                  </tr>
                </thead>
                <tbody>
                  {toolLogs.map((log, i) => (
                    <tr key={i} className="border-b border-dark-border/50 hover:bg-zinc-800/30" title={log.error || undefined}>
                      <td className="p-3 text-zinc-400 font-mono text-xs whitespace-nowrap">
                        {new Date(log.timestamp).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                      </td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 text-xs rounded-full bg-blue-500/20 text-blue-400">
                          {log.agent}
                        </span>
                      </td>
                      <td className="p-3 font-mono text-xs">{log.tool}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${
                          log.status === 'success'
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-red-500/20 text-red-400'
                        }`}>
                          {log.status === 'success' ? '성공' : '실패'}
                        </span>
                      </td>
                      <td className="p-3 text-right font-mono text-xs text-zinc-400">
                        {log.duration_ms !== null ? `${log.duration_ms.toFixed(0)}ms` : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : toolLogsLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
            </div>
          ) : (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center text-zinc-500">
              <ScrollText size={32} className="mx-auto mb-2 opacity-50" />
              <div>도구 호출 로그가 없습니다</div>
            </div>
          )}
        </div>
      )}

      {/* ═══ 통계 탭 ═══ */}
      {activeTab === 'analytics' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-500">
              도구별 호출 횟수 · 성공률 · 평균 응답 시간
            </p>
            <button onClick={loadAnalytics} disabled={analyticsLoading}
              className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50">
              {analyticsLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
          </div>

          {analytics ? (
            analytics.analytics.length === 0 ? (
              <div className="bg-dark-card border border-dark-border rounded-xl p-8 text-center text-zinc-500">
                <BarChart2 size={32} className="mx-auto mb-2 opacity-40" />
                <div>아직 도구 호출 기록이 없습니다</div>
                <div className="text-xs mt-1">에이전트가 도구를 사용하면 여기에 통계가 쌓입니다</div>
              </div>
            ) : (
              <div className="space-y-3">
                {/* 요약 카드 */}
                <div className="grid grid-cols-3 gap-3 mb-4">
                  <div className="bg-dark-card border border-dark-border rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold text-primary">{analytics.total_calls.toLocaleString()}</div>
                    <div className="text-xs text-zinc-500 mt-1">총 호출 횟수</div>
                  </div>
                  <div className="bg-dark-card border border-dark-border rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold text-green-400">{analytics.total_tools}</div>
                    <div className="text-xs text-zinc-500 mt-1">사용된 도구 수</div>
                  </div>
                  <div className="bg-dark-card border border-dark-border rounded-xl p-4 text-center">
                    <div className="text-2xl font-bold text-amber-400">
                      {analytics.analytics.length > 0
                        ? Math.round(analytics.analytics.reduce((s, a) => s + a.success_rate, 0) / analytics.analytics.length)
                        : 0}%
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">평균 성공률</div>
                  </div>
                </div>

                {/* 도구별 상세 테이블 */}
                <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-dark-border text-zinc-500">
                        <th className="text-left p-3">도구</th>
                        <th className="text-right p-3">호출</th>
                        <th className="text-right p-3">성공률</th>
                        <th className="text-right p-3">평균 응답</th>
                        <th className="text-left p-3">사용 에이전트</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...analytics.analytics]
                        .sort((a, b) => b.calls - a.calls)
                        .map((item) => (
                          <tr key={item.tool} className="border-b border-dark-border/50 hover:bg-zinc-800/30">
                            <td className="p-3 font-mono text-xs font-medium">{item.tool}</td>
                            <td className="p-3 text-right font-mono text-xs">{item.calls}</td>
                            <td className="p-3 text-right">
                              <span className={`px-2 py-0.5 text-xs rounded-full font-mono ${
                                item.success_rate >= 80 ? 'bg-green-500/20 text-green-400' :
                                item.success_rate >= 50 ? 'bg-amber-500/20 text-amber-400' :
                                'bg-red-500/20 text-red-400'
                              }`}>
                                {item.success_rate.toFixed(0)}%
                              </span>
                            </td>
                            <td className="p-3 text-right font-mono text-xs text-zinc-400">
                              {item.avg_duration_ms > 0 ? `${item.avg_duration_ms.toFixed(0)}ms` : '-'}
                            </td>
                            <td className="p-3">
                              <div className="flex flex-wrap gap-1">
                                {item.agents.map(a => (
                                  <span key={a} className="px-1.5 py-0.5 text-xs rounded bg-blue-500/10 text-blue-400">{a}</span>
                                ))}
                              </div>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          ) : analyticsLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
            </div>
          ) : null}
        </div>
      )}

      {/* ═══ 플러그인 탭 ═══ */}
      {activeTab === 'plugins' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-500">
              도구 활성화/비활성화 런타임 제어 (재시작 시 초기화)
            </p>
            <div className="flex gap-2">
              <button onClick={handleReloadPlugins} disabled={reloading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-zinc-700 hover:bg-zinc-600 text-zinc-300 transition-colors disabled:opacity-50">
                {reloading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                전체 재로드
              </button>
              <button onClick={loadPlugins} disabled={pluginsLoading}
                className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50">
                {pluginsLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
              </button>
            </div>
          </div>

          {plugins.length > 0 ? (
            <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-dark-border text-zinc-500">
                    <th className="text-left p-3">도구명</th>
                    <th className="text-left p-3">설명</th>
                    <th className="text-center p-3">타입</th>
                    <th className="text-center p-3">상태</th>
                    <th className="text-center p-3">제어</th>
                  </tr>
                </thead>
                <tbody>
                  {plugins.map((plugin) => (
                    <tr key={plugin.name} className="border-b border-dark-border/50 hover:bg-zinc-800/20">
                      <td className="p-3 font-mono text-xs font-medium">{plugin.name}</td>
                      <td className="p-3 text-xs text-zinc-400 max-w-xs truncate">{plugin.description}</td>
                      <td className="p-3 text-center">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${
                          plugin.is_mcp ? 'bg-violet-500/20 text-violet-400' : 'bg-blue-500/20 text-blue-400'
                        }`}>
                          {plugin.is_mcp ? 'MCP' : '네이티브'}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        <span className={`px-2 py-0.5 text-xs rounded-full ${
                          plugin.enabled ? 'bg-green-500/20 text-green-400' : 'bg-zinc-500/20 text-zinc-500'
                        }`}>
                          {plugin.enabled ? '활성' : '비활성'}
                        </span>
                      </td>
                      <td className="p-3 text-center">
                        <button
                          onClick={() => handleTogglePlugin(plugin.name, plugin.enabled)}
                          disabled={togglingPlugin === plugin.name}
                          className="p-1.5 rounded hover:bg-zinc-700 transition-colors disabled:opacity-50"
                          title={plugin.enabled ? '비활성화' : '활성화'}
                        >
                          {togglingPlugin === plugin.name
                            ? <Loader2 size={16} className="animate-spin text-zinc-400" />
                            : plugin.enabled
                              ? <ToggleRight size={18} className="text-green-400" />
                              : <ToggleLeft size={18} className="text-zinc-500" />
                          }
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : pluginsLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
            </div>
          ) : (
            <div className="bg-dark-card border border-dark-border rounded-xl p-8 text-center text-zinc-500">
              <Package size={32} className="mx-auto mb-2 opacity-40" />
              <div>등록된 플러그인이 없습니다</div>
            </div>
          )}
        </div>
      )}

      {/* ═══ 정책 탭 ═══ */}
      {activeTab === 'policies' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-500">
              에이전트별 도구 접근 정책 (Tool Policy Engine)
            </p>
            <button
              onClick={loadToolPolicies}
              disabled={policiesLoading}
              className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              {policiesLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
          </div>

          {toolPolicies ? (
            <div className="space-y-4">
              {Object.entries(toolPolicies.policies).map(([agentName, policy]) => (
                <div key={agentName} className="bg-dark-card border border-dark-border rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Shield size={18} className="text-blue-400" />
                      <span className="font-semibold">{agentName}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      {policy.max_rounds && (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-400">
                          최대 {policy.max_rounds}회
                        </span>
                      )}
                      <button
                        onClick={() => handleToggleAllowAll(agentName, policy.whitelist)}
                        className={`px-2 py-0.5 text-[10px] rounded transition-colors ${
                          policy.whitelist === null
                            ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                            : 'bg-zinc-700 text-zinc-400 hover:bg-zinc-600'
                        }`}
                        title={policy.whitelist === null ? '도구 제한으로 전환' : '모든 도구 허용으로 전환'}
                      >
                        {policy.whitelist === null ? '전체 허용' : '제한됨'}
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {/* 허용 목록 */}
                    <div>
                      <div className="text-xs text-zinc-500 mb-1.5 flex items-center gap-1">
                        <CheckCircle size={12} className="text-green-400" />
                        허용 도구 (whitelist)
                      </div>
                      {policy.whitelist === null ? (
                        <span className="text-xs text-green-400/70">모든 도구 허용</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {policy.whitelist.map((tool: string) => (
                            <span key={tool} className="px-2 py-0.5 text-xs rounded bg-green-500/10 text-green-400 font-mono">
                              {tool}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* 차단 목록 */}
                    <div>
                      <div className="text-xs text-zinc-500 mb-1.5 flex items-center gap-1">
                        <XCircle size={12} className="text-red-400" />
                        차단 도구 (blacklist)
                      </div>
                      {policy.blacklist.length === 0 ? (
                        <span className="text-xs text-zinc-500">없음</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {policy.blacklist.map((tool: string) => (
                            <span key={tool} className="px-2 py-0.5 text-xs rounded bg-red-500/10 text-red-400 font-mono flex items-center gap-1">
                              {tool}
                              <button
                                onClick={() => handleSavePolicy(agentName, policy.blacklist.filter((t: string) => t !== tool))}
                                className="hover:text-red-300 ml-0.5"
                                title="차단 해제"
                              >×</button>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : policiesLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
