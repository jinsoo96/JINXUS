'use client';

import { useState, useEffect } from 'react';
import { systemApi, MCPStatus } from '@/lib/api';
import {
  Plug, Wrench, RefreshCw, CheckCircle, AlertCircle,
  XCircle, Key, Loader2, ChevronDown, ChevronUp
} from 'lucide-react';

export default function ToolsTab() {
  const [mcpStatus, setMcpStatus] = useState<MCPStatus | null>(null);
  const [mcpLoading, setMcpLoading] = useState(false);
  const [reconnecting, setReconnecting] = useState<string | null>(null);
  const [expandedServers, setExpandedServers] = useState<Set<string>>(new Set());

  const loadMCPStatus = async () => {
    setMcpLoading(true);
    try {
      const status = await systemApi.getMCPStatus();
      setMcpStatus(status);
    } catch (error) {
      console.error('MCP 상태 조회 실패:', error);
    } finally {
      setMcpLoading(false);
    }
  };

  const handleReconnect = async (serverName: string) => {
    setReconnecting(serverName);
    try {
      await systemApi.reconnectMCP(serverName);
      await loadMCPStatus();
    } catch (error) {
      console.error('MCP 재연결 실패:', error);
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

  useEffect(() => {
    loadMCPStatus();
  }, []);

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
      case 'connected':
        return 'bg-green-500/10';
      case 'api_key_missing':
        return 'bg-amber-500/10';
      case 'disabled':
        return 'bg-zinc-500/10';
      default:
        return 'bg-red-500/10';
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">도구</h2>

      {/* MCP 서버 상태 */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Plug size={20} />
            MCP 서버 연결
          </h3>
          <div className="flex items-center gap-3">
            {mcpStatus && (
              <div className="flex items-center gap-4 text-sm text-zinc-500">
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-green-400"></span>
                  {mcpStatus.connected_count}개 연결
                </span>
                <span>전체 {mcpStatus.total_configured}개</span>
                <span>도구 {mcpStatus.total_tools}개</span>
              </div>
            )}
            <button
              onClick={loadMCPStatus}
              disabled={mcpLoading}
              className="p-2 rounded-lg hover:bg-zinc-800 transition-colors disabled:opacity-50"
              title="새로고침"
            >
              {mcpLoading ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                <RefreshCw size={18} />
              )}
            </button>
          </div>
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
                  {/* 서버 헤더 */}
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
                        <div className="text-zinc-500 text-sm">
                          {server.description}
                        </div>
                        {server.status === 'connected' && (
                          <div className="text-zinc-600 text-xs mt-0.5">
                            도구 {server.tools_count}개 사용 가능
                          </div>
                        )}
                        {server.error && server.status !== 'connected' && (
                          <div className="text-red-400/80 text-xs mt-0.5">
                            {server.error}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {getStatusBadge(server.status)}
                      {server.status === 'disconnected' && server.has_api_key !== false && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleReconnect(server.name);
                          }}
                          disabled={reconnecting === server.name}
                          className="px-3 py-1 text-sm bg-blue-500/20 text-blue-400 rounded-lg hover:bg-blue-500/30 transition-colors disabled:opacity-50"
                        >
                          {reconnecting === server.name ? (
                            <Loader2 size={14} className="animate-spin" />
                          ) : (
                            '재연결'
                          )}
                        </button>
                      )}
                      {server.status === 'connected' && server.tools.length > 0 && (
                        expandedServers.has(server.name) ? (
                          <ChevronUp size={18} className="text-zinc-500" />
                        ) : (
                          <ChevronDown size={18} className="text-zinc-500" />
                        )
                      )}
                    </div>
                  </div>

                  {/* 도구 목록 (확장 시) */}
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
        ) : (
          <div className="bg-dark-card border border-dark-border rounded-xl p-6 text-center text-zinc-500">
            <AlertCircle size={32} className="mx-auto mb-2 opacity-50" />
            <div>MCP 상태를 불러올 수 없습니다</div>
          </div>
        )}
      </div>

      {/* 상태 설명 */}
      <div className="bg-dark-card border border-dark-border rounded-xl p-4">
        <h4 className="font-semibold mb-3">상태 설명</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <div className="flex items-center gap-2">
            <CheckCircle size={16} className="text-green-400" />
            <span className="text-zinc-400">연결됨 - 사용 가능</span>
          </div>
          <div className="flex items-center gap-2">
            <Key size={16} className="text-amber-400" />
            <span className="text-zinc-400">API 키 필요</span>
          </div>
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-red-400" />
            <span className="text-zinc-400">연결 실패</span>
          </div>
          <div className="flex items-center gap-2">
            <XCircle size={16} className="text-zinc-500" />
            <span className="text-zinc-400">비활성화</span>
          </div>
        </div>
      </div>
    </div>
  );
}
