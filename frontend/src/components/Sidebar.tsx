'use client';

import { useState } from 'react';
import Image from 'next/image';
import { useAppStore } from '@/store/useAppStore';
import { LayoutDashboard, MessageSquare, GitBranch, Bot, Brain, ScrollText, Wrench, Settings, Menu, X } from 'lucide-react';
import { MAX_SIDEBAR_AGENTS } from '@/lib/constants';

const tabs = [
  { id: 'dashboard', label: '대시보드', icon: LayoutDashboard },
  { id: 'chat', label: '채팅', icon: MessageSquare },
  { id: 'graph', label: '그래프', icon: GitBranch },
  { id: 'agents', label: '에이전트', icon: Bot },
  { id: 'memory', label: '메모리', icon: Brain },
  { id: 'logs', label: '로그', icon: ScrollText },
  { id: 'tools', label: '도구', icon: Wrench },
  { id: 'settings', label: '설정', icon: Settings },
] as const;

export default function Sidebar() {
  const { activeTab, setActiveTab, agents } = useAppStore();
  const [mobileOpen, setMobileOpen] = useState(false);

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
        w-64 bg-dark-card border-r border-dark-border flex flex-col
        fixed inset-y-0 left-0 z-50 transition-transform duration-200
        md:relative md:translate-x-0
        ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        {/* 로고 */}
        <div className="p-4 border-b border-dark-border">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Image
                src="/jinxus-mascot.png"
                alt="JINXUS"
                width={72}
                height={72}
                className="rounded-xl"
              />
              <div>
                <h2 className="font-bold text-lg text-primary">JINXUS</h2>
                <p className="text-xs text-zinc-500">v1.5.0</p>
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
        </div>

        {/* 네비게이션 */}
        <nav className="flex-1 p-4" aria-label="메인 네비게이션">
          <ul className="space-y-2">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;

              return (
                <li key={tab.id}>
                  <button
                    onClick={() => handleTabClick(tab.id)}
                    aria-current={isActive ? 'page' : undefined}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-primary text-white'
                        : 'text-zinc-400 hover:bg-zinc-800 hover:text-white'
                    }`}
                  >
                    <Icon size={20} />
                    <span>{tab.label}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        {/* 에이전트 상태 */}
        <div className="p-4 border-t border-dark-border">
          <h3 className="text-xs font-semibold text-zinc-500 uppercase mb-3">
            에이전트 ({agents.length})
          </h3>
          <div className="space-y-2">
            {agents.slice(0, MAX_SIDEBAR_AGENTS).map((agent) => (
              <div
                key={agent.name}
                className="flex items-center gap-2 text-sm text-zinc-400"
              >
                <span className="w-2 h-2 rounded-full bg-green-400"></span>
                <span className="truncate">{agent.name}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </>
  );
}
