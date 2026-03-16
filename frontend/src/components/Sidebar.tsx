'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';
import { useAppStore } from '@/store/useAppStore';
import { systemApi, agentApi, type AgentRuntimeStatus } from '@/lib/api';
import { LayoutDashboard, MessageSquare, GitBranch, Bot, Brain, ScrollText, Wrench, Settings, Menu, X, ChevronLeft, ChevronRight, BookOpen, FolderKanban } from 'lucide-react';
import { MAX_SIDEBAR_AGENTS } from '@/lib/constants';

const tabs = [
  { id: 'dashboard', label: '대시보드', icon: LayoutDashboard },
  { id: 'chat', label: '채팅', icon: MessageSquare },
  { id: 'projects', label: '프로젝트', icon: FolderKanban },
  { id: 'graph', label: '그래프', icon: GitBranch },
  { id: 'agents', label: '에이전트', icon: Bot },
  { id: 'memory', label: '메모리', icon: Brain },
  { id: 'logs', label: '로그', icon: ScrollText },
  { id: 'tools', label: '도구', icon: Wrench },
  { id: 'notes', label: '개발 노트', icon: BookOpen },
  { id: 'settings', label: '설정', icon: Settings },
] as const;

export default function Sidebar() {
  const { activeTab, setActiveTab, setLogsAgentFilter, agents } = useAppStore();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [version, setVersion] = useState('');
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});

  useEffect(() => {
    systemApi.getInfo().then(info => setVersion(info.version)).catch(() => {});
    const saved = localStorage.getItem('sidebar-collapsed');
    if (saved === 'true') setCollapsed(true);
  }, []);

  // 에이전트 런타임 상태 폴링 (5초)
  useEffect(() => {
    const poll = async () => {
      try {
        const res = await agentApi.getAllRuntimeStatus();
        const map: Record<string, AgentRuntimeStatus> = {};
        for (const a of res.agents) map[a.name] = a;
        setRuntimeMap(map);
      } catch { /* 무시 */ }
    };
    poll();
    const iv = setInterval(poll, 20000);  // 20초 간격 (불필요한 API 호출 절감)
    return () => clearInterval(iv);
  }, []);

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      localStorage.setItem('sidebar-collapsed', String(!prev));
      return !prev;
    });
  };

  const handleTabClick = (tabId: typeof tabs[number]['id']) => {
    setActiveTab(tabId);
    setMobileOpen(false);
  };

  return (
    <>
      {/* 모바일 햄버거 버튼 */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-3 left-3 z-50 p-2 rounded-lg bg-dark-card border border-dark-border md:hidden"
        aria-label="메뉴 열기"
      >
        <Menu size={20} />
      </button>

      {/* 모바일 오버레이 */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* 사이드바 */}
      <aside className={`
        bg-dark-card border-r border-dark-border flex flex-col
        fixed inset-y-0 left-0 z-50 transition-all duration-200
        md:relative md:translate-x-0
        ${mobileOpen ? 'translate-x-0 w-64' : '-translate-x-full'}
        ${collapsed ? 'md:w-16' : 'md:w-64'}
      `}>
        {/* 로고 */}
        <div className={`border-b border-dark-border flex items-center ${collapsed ? 'p-3 justify-center' : 'p-4'}`}>
          {collapsed ? (
            <Image src="/jinxus-mascot.png" alt="JINXUS" width={36} height={36} className="rounded-lg" />
          ) : (
            <div className="flex items-center justify-between w-full">
              <div className="flex items-center gap-3">
                <Image src="/jinxus-mascot.png" alt="JINXUS" width={40} height={40} className="rounded-xl" />
                <div>
                  <h2 className="font-bold text-base text-primary">JINXUS</h2>
                  {version && <p className="text-xs text-zinc-500">v{version}</p>}
                </div>
              </div>
              <button
                onClick={() => setMobileOpen(false)}
                className="p-1 rounded hover:bg-zinc-800 md:hidden"
                aria-label="메뉴 닫기"
              >
                <X size={18} />
              </button>
            </div>
          )}
        </div>

        {/* 네비게이션 */}
        <nav className={`flex-1 ${collapsed ? 'p-2' : 'p-3'}`} aria-label="메인 네비게이션">
          <ul className="space-y-1">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;

              return (
                <li key={tab.id}>
                  <button
                    onClick={() => handleTabClick(tab.id)}
                    aria-current={isActive ? 'page' : undefined}
                    title={collapsed ? tab.label : undefined}
                    className={`w-full flex items-center rounded-lg transition-colors ${
                      collapsed ? 'justify-center p-3' : 'gap-3 px-3 py-2.5'
                    } ${
                      isActive
                        ? 'bg-primary/20 text-primary border border-primary/30'
                        : 'text-zinc-400 hover:bg-zinc-800 hover:text-white border border-transparent'
                    }`}
                  >
                    <Icon size={20} className="flex-shrink-0" />
                    {!collapsed && <span className="text-sm font-medium">{tab.label}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* 에이전트 상태 패널 */}
        {!collapsed && agents.length > 0 && (
          <div className="px-3 pb-3 border-t border-dark-border pt-2">
            {/* 통계 요약 (Geny 패턴) */}
            {(() => {
              const workingCount = Object.values(runtimeMap).filter(r => r.status === 'working').length;
              const errorCount = Object.values(runtimeMap).filter(r => r.status === 'error').length;
              return (
                <div className="flex items-center gap-3 mb-2">
                  <div className="flex-1 text-center">
                    <p className="text-base font-bold text-white leading-none">{agents.length}</p>
                    <p className="text-[9px] text-zinc-600 uppercase mt-0.5">Total</p>
                  </div>
                  <div className="flex-1 text-center">
                    <p className="text-base font-bold text-green-400 leading-none">{workingCount}</p>
                    <p className="text-[9px] text-zinc-600 uppercase mt-0.5">Running</p>
                  </div>
                  <div className="flex-1 text-center">
                    <p className={`text-base font-bold leading-none ${errorCount > 0 ? 'text-red-400' : 'text-zinc-600'}`}>{errorCount}</p>
                    <p className="text-[9px] text-zinc-600 uppercase mt-0.5">Errors</p>
                  </div>
                </div>
              );
            })()}
            {/* 에이전트 목록 — 클릭 시 로그탭으로 이동 */}
            <div className="space-y-0.5">
              {agents.slice(0, MAX_SIDEBAR_AGENTS).map((agent) => {
                const runtime = runtimeMap[agent.name];
                const isWorking = runtime?.status === 'working';
                const isError = runtime?.status === 'error';
                return (
                  <button
                    key={agent.name}
                    onClick={() => { setLogsAgentFilter(agent.name); setActiveTab('logs'); setMobileOpen(false); }}
                    className="w-full flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 py-0.5 rounded transition-colors"
                  >
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                      isWorking ? 'bg-blue-400 shadow-[0_0_4px_rgba(96,165,250,0.8)]' :
                      isError ? 'bg-red-400' : 'bg-zinc-600'
                    }`} />
                    <span className="truncate">{agent.name.replace('JX_', '').replace('JINXUS_', '')}</span>
                    {isWorking && <span className="ml-auto text-[9px] text-blue-400/70">실행중</span>}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* 접기/펼치기 버튼 (데스크톱만) */}
        <button
          onClick={toggleCollapsed}
          className="hidden md:flex items-center justify-center p-3 border-t border-dark-border text-zinc-500 hover:text-white hover:bg-zinc-800 transition-colors"
          title={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </aside>
    </>
  );
}
