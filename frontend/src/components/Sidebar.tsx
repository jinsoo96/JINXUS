'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Image from 'next/image';
import { useAppStore } from '@/store/useAppStore';
import { systemApi, agentApi, type AgentRuntimeStatus } from '@/lib/api';
import { MessageSquare, Brain, ScrollText, Wrench, Settings, Menu, X, ChevronLeft, ChevronRight, BookOpen, FolderKanban, Building2, Target, GitBranch, Zap } from 'lucide-react';
import { getDisplayName, sortByRank } from '@/lib/personas';
import { SIDEBAR_POLLING_MS } from '@/lib/constants';

const tabs = [
  { id: 'mission', label: 'Office', icon: Target },
  { id: 'team', label: 'Corporation', icon: Building2 },
  { id: 'autopilot', label: 'Autopilot', icon: Zap },
  { id: 'projects', label: 'Projects', icon: FolderKanban },
  { id: 'memory', label: 'Memory', icon: Brain },
  { id: 'logs', label: 'Logs', icon: ScrollText },
  { id: 'tools', label: 'Tools', icon: Wrench },
  { id: 'notes', label: 'Notes', icon: BookOpen },
  { id: 'workflow', label: 'Workflow', icon: GitBranch },
  { id: 'settings', label: 'Settings', icon: Settings },
] as const;

export default function Sidebar() {
  const { activeTab, setActiveTab, setLogsAgentFilter, agents, hrAgents, devMode, setDevMode } = useAppStore();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [version, setVersion] = useState('');
  const [runtimeMap, setRuntimeMap] = useState<Record<string, AgentRuntimeStatus>>({});

  // 에이전트 패널 드래그 리사이즈
  const [panelHeight, setPanelHeight] = useState<number>(() => {
    try {
      const saved = typeof window !== 'undefined' ? localStorage.getItem('sidebar-panel-height') : null;
      return saved ? Number(saved) : 240;
    } catch { return 240; }
  });
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);
  const panelContainerRef = useRef<HTMLDivElement>(null);

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const container = panelContainerRef.current;
    if (!container) return;
    dragRef.current = { startY: e.clientY, startH: container.offsetHeight };

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      // 위로 드래그하면 높이 증가 (핸들이 패널 위에 있으므로)
      const delta = dragRef.current.startY - ev.clientY;
      const newH = Math.max(80, Math.min(600, dragRef.current.startH + delta));
      setPanelHeight(newH);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      // 저장
      const container = panelContainerRef.current;
      try { if (container) localStorage.setItem('sidebar-panel-height', String(container.offsetHeight)); } catch { /* private browsing */ }
      dragRef.current = null;
    };
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, []);

  useEffect(() => {
    systemApi.getInfo().then(info => { if (info?.version) setVersion(info.version); }).catch(e => console.warn('[Sidebar] 버전 로드 실패:', e));
    try {
      const saved = localStorage.getItem('sidebar-collapsed');
      if (saved === 'true') setCollapsed(true);
    } catch { /* private browsing */ }
  }, []);

  // 에이전트 런타임 상태 폴링 (20초, 비활성 탭 시 스킵)
  useEffect(() => {
    const poll = async () => {
      if (document.visibilityState !== 'visible') return;
      try {
        const res = await agentApi.getAllRuntimeStatus();
        const map: Record<string, AgentRuntimeStatus> = {};
        for (const a of res.agents) map[a.name] = a;
        setRuntimeMap(map);
      } catch { /* 무시 */ }
    };
    poll();
    const iv = setInterval(poll, SIDEBAR_POLLING_MS);
    return () => clearInterval(iv);
  }, []);

  const toggleCollapsed = () => {
    setCollapsed(prev => {
      try { localStorage.setItem('sidebar-collapsed', String(!prev)); } catch { /* private browsing */ }
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
        fixed inset-y-0 left-0 z-50 transition-all duration-200 will-change-[width]
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
            {tabs.filter(tab => {
              // Dev Mode가 꺼져있으면 개발용 탭 숨김
              if (!devMode && ['logs', 'tools', 'notes', 'settings'].includes(tab.id)) return false;
              return true;
            }).map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              // Office 탭에 작업중 에이전트 수 뱃지
              const badge = tab.id === 'mission'
                ? Object.values(runtimeMap).filter(r => r.status === 'working').length
                : 0;

              return (
                <li key={tab.id}>
                  <button
                    onClick={() => handleTabClick(tab.id)}
                    aria-current={isActive ? 'page' : undefined}
                    title={collapsed ? tab.label : undefined}
                    className={`w-full flex items-center rounded-lg transition-colors press-feedback focus-ring ${
                      collapsed ? 'justify-center p-3 relative' : 'gap-3 px-3 py-2.5'
                    } ${
                      isActive
                        ? 'bg-primary/20 text-primary border border-primary/30'
                        : 'text-zinc-400 hover:bg-zinc-800 hover:text-white border border-transparent'
                    }`}
                  >
                    <Icon size={20} className="flex-shrink-0" />
                    {!collapsed && (
                      <>
                        <span className="text-sm font-medium">{tab.label}</span>
                        {badge > 0 && (
                          <span className="ml-auto text-[9px] font-bold text-blue-400 bg-blue-500/15 px-1.5 py-0.5 rounded-full">
                            {badge}
                          </span>
                        )}
                      </>
                    )}
                    {collapsed && badge > 0 && (
                      <span className="absolute -top-0.5 -right-0.5 w-4 h-4 text-[8px] font-bold text-white bg-blue-500 rounded-full flex items-center justify-center">
                        {badge}
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* 에이전트 상태 패널 (드래그 리사이즈) */}
        {!collapsed && agents.length > 0 && (
          <>
            {/* 드래그 핸들 */}
            <div
              onMouseDown={onDragStart}
              className="h-1.5 flex-shrink-0 cursor-row-resize group border-t border-dark-border hover:border-blue-500/50 transition-colors"
            >
              <div className="mx-auto mt-0.5 w-8 h-0.5 rounded-full bg-zinc-700 group-hover:bg-blue-500/60 transition-colors" />
            </div>
            <div ref={panelContainerRef} className="px-3 pb-3 pt-1 flex flex-col min-h-0 overflow-hidden" style={{ height: panelHeight }}>
              {/* 통계 요약 */}
              {(() => {
                const workingCount = Object.values(runtimeMap).filter(r => r.status === 'working').length;
                const errorCount = Object.values(runtimeMap).filter(r => r.status === 'error').length;
                return (
                  <div className="flex items-center gap-3 mb-2 flex-shrink-0">
                    <div className="flex-1 text-center">
                      <p className="text-base font-bold text-white leading-none tabular-nums">{hrAgents.length}</p>
                      <p className="text-[9px] text-zinc-600 uppercase mt-0.5">Total</p>
                    </div>
                    <div className="flex-1 text-center">
                      <p className="text-base font-bold text-green-400 leading-none tabular-nums">{workingCount}</p>
                      <p className="text-[9px] text-zinc-600 uppercase mt-0.5">Running</p>
                    </div>
                    <div className="flex-1 text-center">
                      <p className={`text-base font-bold leading-none tabular-nums ${errorCount > 0 ? 'text-red-400' : 'text-zinc-600'}`}>{errorCount}</p>
                      <p className="text-[9px] text-zinc-600 uppercase mt-0.5">Errors</p>
                    </div>
                  </div>
                );
              })()}
              {/* 에이전트 목록 — 클릭 시 로그탭으로 이동 */}
              <div className="space-y-0.5 overflow-y-auto flex-1 min-h-0 pr-0.5">
                {[...hrAgents].sort((a, b) => sortByRank(a.name, b.name)).map((agent) => {
                  const runtime = runtimeMap[agent.name];
                  const isWorking = runtime?.status === 'working';
                  const isError = runtime?.status === 'error';
                  return (
                    <button
                      key={agent.name}
                      onClick={() => { setLogsAgentFilter(agent.name); setActiveTab('logs'); setMobileOpen(false); }}
                      className="w-full flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-300 py-0.5 rounded transition-colors"
                    >
                      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        isWorking ? 'bg-green-400 animate-pulse shadow-[0_0_6px_rgba(74,222,128,0.9)]' :
                        isError ? 'bg-red-400' : 'bg-zinc-600'
                      }`} />
                      <span className="truncate">{getDisplayName(agent.name)}</span>
                      {isWorking && <span className="ml-auto text-[9px] text-green-400/70 flex-shrink-0">실행중</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* Dev Mode 토글 + 접기/펼치기 */}
        <div className="border-t border-dark-border flex items-center">
          {!collapsed && (
            <button
              onClick={() => setDevMode(!devMode)}
              className={`flex-1 flex items-center justify-center gap-1.5 p-2.5 text-[10px] font-medium transition-colors ${
                devMode ? 'text-amber-400 hover:text-amber-300' : 'text-zinc-600 hover:text-zinc-400'
              }`}
              title={devMode ? 'Dev Mode 끄기 (개발탭 숨김)' : 'Dev Mode 켜기 (개발탭 표시)'}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${devMode ? 'bg-amber-400' : 'bg-zinc-700'}`} />
              DEV
            </button>
          )}
          <button
            onClick={toggleCollapsed}
            className="hidden md:flex items-center justify-center p-3 text-zinc-500 hover:text-white hover:bg-zinc-800 transition-colors"
            title={collapsed ? '사이드바 펼치기' : '사이드바 접기'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>
      </aside>
    </>
  );
}
