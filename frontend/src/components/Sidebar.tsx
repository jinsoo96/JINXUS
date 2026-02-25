'use client';

import Image from 'next/image';
import { useAppStore } from '@/store/useAppStore';
import { MessageSquare, Bot, Brain, Settings } from 'lucide-react';

const tabs = [
  { id: 'chat', label: '채팅', icon: MessageSquare },
  { id: 'agents', label: '에이전트', icon: Bot },
  { id: 'memory', label: '메모리', icon: Brain },
  { id: 'settings', label: '설정', icon: Settings },
] as const;

export default function Sidebar() {
  const { activeTab, setActiveTab, agents } = useAppStore();

  return (
    <aside className="w-64 bg-dark-card border-r border-dark-border flex flex-col">
      {/* 로고 */}
      <div className="p-4 border-b border-dark-border">
        <div className="flex items-center gap-3">
          <Image
            src="/jinxus-mascot.png"
            alt="JINXUS"
            width={72}
            height={72}
            className="rounded-xl"
          />
          <div>
            <h2 className="font-semibold text-lg">JINXUS</h2>
            <p className="text-xs text-zinc-500">v1.1.0</p>
          </div>
        </div>
      </div>

      {/* 네비게이션 */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;

            return (
              <li key={tab.id}>
                <button
                  onClick={() => setActiveTab(tab.id)}
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
          {agents.slice(0, 5).map((agent) => (
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
  );
}
