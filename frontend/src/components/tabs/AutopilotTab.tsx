'use client';

import { useState } from 'react';
import { Zap, Radio, DollarSign, Clock } from 'lucide-react';
import ControlPanel from './autopilot/ControlPanel';
import TriggerPanel from './autopilot/TriggerPanel';
import BudgetPanel from './autopilot/BudgetPanel';
import RoutinePanel from './autopilot/RoutinePanel';

type SubTab = 'control' | 'triggers' | 'budget' | 'routines';

const SUB_TABS: { id: SubTab; label: string; icon: typeof Zap }[] = [
  { id: 'control', label: '컨트롤 센터', icon: Zap },
  { id: 'triggers', label: '트리거', icon: Radio },
  { id: 'budget', label: '예산', icon: DollarSign },
  { id: 'routines', label: '루틴', icon: Clock },
];

export default function AutopilotTab({ isActive = true }: { isActive?: boolean }) {
  const [subTab, setSubTab] = useState<SubTab>('control');

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-2 sm:gap-3">
        <Zap size={20} className="text-primary sm:w-[22px] sm:h-[22px]" />
        <h1 className="text-base sm:text-xl font-bold">오토파일럿</h1>
        <span className="text-[10px] sm:text-xs text-zinc-500 hidden sm:inline">에이전트 자율 행동 관리</span>
      </div>

      {/* 서브탭 바 */}
      <div className="flex gap-1 p-1 bg-zinc-800/50 rounded-xl overflow-x-auto">
        {SUB_TABS.map(tab => {
          const Icon = tab.icon;
          const active = subTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setSubTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${
                active
                  ? 'bg-primary/15 text-primary shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50'
              }`}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 서브탭 콘텐츠 */}
      {subTab === 'control' && <ControlPanel isActive={isActive} />}
      {subTab === 'triggers' && <TriggerPanel isActive={isActive} />}
      {subTab === 'budget' && <BudgetPanel isActive={isActive} />}
      {subTab === 'routines' && <RoutinePanel isActive={isActive} />}
    </div>
  );
}
