'use client';

import { useState, useEffect, useCallback } from 'react';
import { aaiApi, type BudgetReport } from '@/lib/api';
import { getDisplayName, getPersona } from '@/lib/personas';
import toast from 'react-hot-toast';
import {
  DollarSign, Loader2, RefreshCw, ChevronLeft, ChevronRight,
  AlertTriangle, CheckCircle, XOctagon, Edit3,
} from 'lucide-react';

function getMonthStr(offset: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export default function BudgetPanel({ isActive }: { isActive: boolean }) {
  const [reports, setReports] = useState<BudgetReport[]>([]);
  const [totalCost, setTotalCost] = useState(0);
  const [loading, setLoading] = useState(true);
  const [monthOffset, setMonthOffset] = useState(0);
  const [editingAgent, setEditingAgent] = useState<string | null>(null);
  const [editBudget, setEditBudget] = useState('');

  const month = getMonthStr(monthOffset);

  const loadData = useCallback(async () => {
    try {
      const data = await aaiApi.getAllBudgets(month);
      setReports(data.reports || []);
      setTotalCost(data.total_cost_usd || 0);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [month]);

  useEffect(() => {
    if (isActive) { setLoading(true); loadData(); }
  }, [isActive, loadData]);

  const handleSetBudget = async (agent: string) => {
    const value = parseFloat(editBudget);
    if (isNaN(value) || value < 0) { toast.error('올바른 금액을 입력하세요'); return; }
    try {
      await aaiApi.setBudget(agent, value);
      toast.success('예산 설정 완료');
      setEditingAgent(null);
      loadData();
    } catch { toast.error('예산 설정 실패'); }
  };

  const statusIcon = (status: string) => {
    if (status === 'hard_stop') return <XOctagon size={14} className="text-red-400" />;
    if (status === 'warning') return <AlertTriangle size={14} className="text-amber-400" />;
    return <CheckCircle size={14} className="text-green-400" />;
  };

  const statusColor = (pct: number) => {
    if (pct >= 95) return 'bg-red-500';
    if (pct >= 75) return 'bg-amber-500';
    if (pct >= 50) return 'bg-blue-500';
    return 'bg-green-500';
  };

  return (
    <div className="space-y-4">
      {/* 월 선택 + 총 비용 */}
      <div className="flex items-center justify-between bg-dark-card border border-dark-border rounded-xl p-4">
        <div className="flex items-center gap-3">
          <DollarSign size={18} className="text-primary" />
          <div>
            <div className="font-semibold">이번 달 총 비용</div>
            <div className="text-2xl font-bold text-primary">${totalCost.toFixed(2)}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setMonthOffset(o => o - 1)}
            disabled={getMonthStr(monthOffset - 1) < '2026-04'}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 disabled:opacity-30"><ChevronLeft size={16} /></button>
          <span className="text-sm text-zinc-400 font-mono w-20 text-center">{month}</span>
          <button onClick={() => setMonthOffset(o => Math.min(0, o + 1))} disabled={monthOffset >= 0}
            className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 disabled:opacity-30"><ChevronRight size={16} /></button>
          <button onClick={loadData} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 ml-2">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* 에이전트별 예산 카드 */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 size={24} className="animate-spin text-zinc-500" /></div>
      ) : reports.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {reports.map(r => {
            const p = getPersona(r.agent);
            const pct = Math.min(100, r.usage_percent || 0);
            return (
              <div key={r.agent} className="bg-dark-card border border-dark-border rounded-xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span>{p?.emoji ?? '🤖'}</span>
                    <span className="font-medium text-sm">{getDisplayName(r.agent)}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    {statusIcon(r.status)}
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                      r.status === 'hard_stop' ? 'bg-red-500/20 text-red-400' :
                      r.status === 'warning' ? 'bg-amber-500/20 text-amber-400' :
                      'bg-green-500/20 text-green-400'
                    }`}>
                      {r.status === 'hard_stop' ? '중지' : r.status === 'warning' ? '경고' : '정상'}
                    </span>
                  </div>
                </div>

                {/* 프로그레스 바 */}
                <div className="w-full h-2 bg-zinc-800 rounded-full overflow-hidden mb-1">
                  <div className={`h-full rounded-full transition-all ${statusColor(pct)}`} style={{ width: `${pct}%` }} />
                </div>
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-zinc-400">${r.total_cost_usd.toFixed(2)} / ${r.budget_usd.toFixed(0)}</span>
                  <span className="text-zinc-500 font-mono">{pct.toFixed(0)}%</span>
                </div>

                {/* 모델별 분포 */}
                {r.top_models && Object.keys(r.top_models).length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {Object.entries(r.top_models).slice(0, 3).map(([model, cost]) => (
                      <span key={model} className="text-[9px] px-1.5 py-0.5 bg-zinc-800 text-zinc-500 rounded">
                        {model.split('-').pop()} ${(cost as number).toFixed(2)}
                      </span>
                    ))}
                  </div>
                )}

                {/* 예산 수정 */}
                <div className="mt-2 pt-2 border-t border-dark-border">
                  {editingAgent === r.agent ? (
                    <div className="flex gap-1">
                      <input type="number" value={editBudget}
                        onChange={e => setEditBudget(e.target.value)}
                        className="flex-1 bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs focus:outline-none focus:border-primary"
                        placeholder="$" />
                      <button onClick={() => handleSetBudget(r.agent)}
                        className="px-2 py-1 bg-primary text-black rounded text-[10px] font-medium">저장</button>
                      <button onClick={() => setEditingAgent(null)}
                        className="px-2 py-1 bg-zinc-700 text-zinc-400 rounded text-[10px]">취소</button>
                    </div>
                  ) : (
                    <button onClick={() => { setEditingAgent(r.agent); setEditBudget(String(r.budget_usd)); }}
                      className="flex items-center gap-1 text-[10px] text-zinc-600 hover:text-zinc-400 transition-colors">
                      <Edit3 size={10} /> 예산 수정
                    </button>
                  )}
                </div>

                <div className="text-[9px] text-zinc-700 mt-1">호출 {r.event_count}건</div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col items-center py-12 gap-3 text-zinc-600">
          <DollarSign size={32} />
          <p className="text-sm">이번 달 비용 기록이 없습니다</p>
        </div>
      )}
    </div>
  );
}
