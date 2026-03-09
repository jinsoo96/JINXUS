'use client';

import { useState, useEffect } from 'react';
import {
  systemApi, MCPStatus, ToolGraphData, ToolsListResponse, NativeTool,
  pluginsApi, PluginInfo,
  ToolCallLog, ToolPoliciesResponse,
} from '@/lib/api';
import toast from 'react-hot-toast';
import {
  Plug, Wrench, RefreshCw, CheckCircle, AlertCircle,
  XCircle, Key, Loader2, ChevronDown, ChevronUp,
  Network, Box, Search, ToggleLeft, ToggleRight,
  ScrollText, Shield,
} from 'lucide-react';

type TabId = 'mcp' | 'native' | 'graph' | 'plugins' | 'tool-logs' | 'policies';

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

  // 플러그인
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [pluginsLoading, setPluginsLoading] = useState(false);
  const [togglingPlugin, setTogglingPlugin] = useState<string | null>(null);

  // 도구 호출 로그
  const [toolLogs, setToolLogs] = useState<ToolCallLog[]>([]);
  const [toolLogsLoading, setToolLogsLoading] = useState(false);

  // 도구 정책
  const [toolPolicies, setToolPolicies] = useState<ToolPoliciesResponse | null>(null);
  const [policiesLoading, setPoliciesLoading] = useState(false);

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

  // ── 플러그인 (네이티브 도구 기반) ──
  const loadPlugins = async () => {
    setPluginsLoading(true);
    try {
      // plugin_loader 시도, 빈 목록이면 status/tools에서 가져옴
      const data = await pluginsApi.getAll();
      if (data.plugins && data.plugins.length > 0) {
        setPlugins(data.plugins);
      } else {
        // TOOL_REGISTRY 기반 native tools를 플러그인으로 표시
        const tools = await systemApi.getTools();
        setPlugins(tools.native_tools.map((t: NativeTool) => ({
          name: t.name,
          description: t.description,
          allowed_agents: t.allowed_agents,
          enabled: t.enabled,
        })));
      }
    } catch (error) {
      console.error('플러그인 조회 실패:', error);
      toast.error('플러그인 조회 실패');
    } finally {
      setPluginsLoading(false);
    }
  };

  const handleTogglePlugin = async (name: string, currentEnabled: boolean) => {
    setTogglingPlugin(name);
    try {
      if (currentEnabled) {
        await pluginsApi.disable(name);
      } else {
        await pluginsApi.enable(name);
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
    setPluginsLoading(true);
    try {
      await pluginsApi.reload();
      await loadPlugins();
    } catch (error) {
      console.error('플러그인 재로드 실패:', error);
      toast.error('플러그인 재로드 실패');
    } finally {
      setPluginsLoading(false);
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
    if (activeTab === 'plugins' && plugins.length === 0) loadPlugins();
    if (activeTab === 'tool-logs') loadToolLogs();
    if (activeTab === 'policies' && !toolPolicies) loadToolPolicies();
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
    { id: 'plugins', label: '플러그인', icon: Box, count: plugins.length || undefined },
    { id: 'tool-logs', label: '도구 호출 로그', icon: ScrollText, count: toolLogs.length || undefined },
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
            <button
              onClick={loadMCPStatus}
              disabled={mcpLoading}
              className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
            >
              {mcpLoading ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            </button>
          </div>

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

          {/* 그래프 노드 */}
          {toolGraph ? (
            <div>
              <h4 className="text-sm font-semibold text-zinc-400 mb-3">
                노드 ({toolGraph.nodes.length}개)
              </h4>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
                {toolGraph.nodes.map((node) => (
                  <div key={node.name} className="bg-dark-card border border-dark-border rounded-xl p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono font-semibold text-sm">{node.name}</span>
                      <span className={`px-2 py-0.5 text-xs rounded-full ${getCategoryColor(node.category)}`}>
                        {node.category}
                      </span>
                    </div>
                    <p className="text-zinc-500 text-xs mb-2">{node.description}</p>
                    <div className="flex items-center justify-between text-xs">
                      <div className="flex gap-1 flex-wrap">
                        {node.keywords.slice(0, 4).map((kw: string) => (
                          <span key={kw} className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">
                            {kw}
                          </span>
                        ))}
                        {node.keywords.length > 4 && (
                          <span className="text-zinc-600">+{node.keywords.length - 4}</span>
                        )}
                      </div>
                      <span className={`font-mono ${node.weight !== 1.0 ? 'text-amber-400' : 'text-zinc-600'}`}>
                        w:{node.weight.toFixed(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

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
                      <tr key={i} className="border-b border-dark-border/50 hover:bg-zinc-800/30">
                        <td className="p-3 font-mono">{edge.source}</td>
                        <td className="p-3 font-mono">{edge.target}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 text-xs rounded-full ${
                            edge.type === 'precedes' ? 'bg-blue-500/20 text-blue-400' :
                            edge.type === 'requires' ? 'bg-red-500/20 text-red-400' :
                            edge.type === 'similar_to' ? 'bg-green-500/20 text-green-400' :
                            edge.type === 'complementary' ? 'bg-purple-500/20 text-purple-400' :
                            edge.type === 'conflicts' ? 'bg-amber-500/20 text-amber-400' :
                            'bg-zinc-500/20 text-zinc-400'
                          }`}>
                            {edge.type}
                          </span>
                        </td>
                        <td className={`p-3 text-right font-mono ${edge.weight !== 1.0 ? 'text-amber-400' : 'text-zinc-500'}`}>
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

      {/* ═══ 플러그인 탭 ═══ */}
      {activeTab === 'plugins' && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-zinc-500">
              도구 플러그인 활성화/비활성화
            </p>
            <button
              onClick={handleReloadPlugins}
              disabled={pluginsLoading}
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm transition-colors disabled:opacity-50"
            >
              {pluginsLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              전체 재스캔
            </button>
          </div>

          {plugins.length > 0 ? (
            <div className="space-y-3">
              {plugins.map((plugin) => (
                <div key={plugin.name} className="bg-dark-card border border-dark-border rounded-xl p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        plugin.enabled ? 'bg-green-500/20' : 'bg-zinc-500/20'
                      }`}>
                        <Box size={20} className={plugin.enabled ? 'text-green-400' : 'text-zinc-500'} />
                      </div>
                      <div>
                        <div className="font-semibold font-mono">{plugin.name}</div>
                        <div className="text-zinc-500 text-sm">{plugin.description}</div>
                        {plugin.allowed_agents.length > 0 && (
                          <div className="flex gap-1 mt-1">
                            {plugin.allowed_agents.map((a: string) => (
                              <span key={a} className="px-1.5 py-0.5 text-xs rounded bg-zinc-700 text-zinc-400">{a}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleTogglePlugin(plugin.name, plugin.enabled)}
                      disabled={togglingPlugin === plugin.name}
                      className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
                      title={plugin.enabled ? '비활성화' : '활성화'}
                    >
                      {togglingPlugin === plugin.name ? (
                        <Loader2 size={24} className="animate-spin text-zinc-500" />
                      ) : plugin.enabled ? (
                        <ToggleRight size={24} className="text-green-400" />
                      ) : (
                        <ToggleLeft size={24} className="text-zinc-500" />
                      )}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : pluginsLoading ? (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center">
              <Loader2 size={24} className="mx-auto animate-spin text-zinc-500" />
            </div>
          ) : (
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center text-zinc-500">
              <Box size={32} className="mx-auto mb-2 opacity-50" />
              <div>등록된 플러그인이 없습니다</div>
            </div>
          )}
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
                    {policy.max_rounds && (
                      <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-400">
                        최대 {policy.max_rounds}회
                      </span>
                    )}
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
                            <span key={tool} className="px-2 py-0.5 text-xs rounded bg-red-500/10 text-red-400 font-mono">
                              {tool}
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
