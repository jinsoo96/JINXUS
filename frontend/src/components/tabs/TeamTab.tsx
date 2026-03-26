'use client';

import { useState } from 'react';
import { Building2, Users } from 'lucide-react';
import dynamic from 'next/dynamic';

const CompanyChat = dynamic(() => import('./CompanyChat'), { ssr: false });
const AgentsTab = dynamic(() => import('./AgentsTab'), { ssr: false });

type SubTab = 'channel' | 'status';

const SUB_TABS: { id: SubTab; label: string; icon: typeof Building2 }[] = [
  { id: 'channel', label: '팀 채널', icon: Building2 },
  { id: 'status', label: '직원 현황', icon: Users },
];

export default function TeamTab({ isActive = true }: { isActive?: boolean }) {
  const [subTab, setSubTab] = useState<SubTab>('channel');

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 서브탭 네비게이션 */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-dark-border bg-zinc-900/60 flex-shrink-0">
        {SUB_TABS.map(tab => {
          const Icon = tab.icon;
          const active = subTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setSubTab(tab.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                active
                  ? 'bg-zinc-700/60 text-white'
                  : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40'
              }`}
            >
              <Icon size={13} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 서브탭 컨텐츠 */}
      <div className="flex-1 min-h-0 overflow-hidden">
        {/* 팀 채널 */}
        <div className={subTab === 'channel' ? 'h-full' : 'hidden'}>
          <CompanyChat isActive={isActive && subTab === 'channel'} />
        </div>

        {/* 직원 현황 */}
        <div className={subTab === 'status' ? 'h-full' : 'hidden'}>
          <AgentsTab
            isActive={isActive}
            forcedSubTab="status"
          />
        </div>
      </div>
    </div>
  );
}
