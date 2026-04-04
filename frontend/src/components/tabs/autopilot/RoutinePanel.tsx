'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { aaiApi, type AAIRoutine, type RoutineRun } from '@/lib/api';
import { getDisplayName, getPersona } from '@/lib/personas';
import toast from 'react-hot-toast';
import {
  Clock, Plus, Trash2, Loader2, RefreshCw, ChevronDown, ChevronRight,
  Play, Pause, X, CheckCircle, XCircle,
} from 'lucide-react';

const POLICY_LABELS: Record<string, string> = {
  skip_if_active: '실행 중이면 스킵',
  coalesce: '병합',
  always_enqueue: '항상 큐에 추가',
};

export default function RoutinePanel({ isActive }: { isActive: boolean }) {
  const { hrAgents } = useAppStore();
  const [routines, setRoutines] = useState<AAIRoutine[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [runs, setRuns] = useState<RoutineRun[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);

  // 생성 폼
  const [formName, setFormName] = useState('');
  const [formCron, setFormCron] = useState('0 9 * * *');
  const [formTemplate, setFormTemplate] = useState('');
  const [formAgent, setFormAgent] = useState('');
  const [formPolicy, setFormPolicy] = useState('skip_if_active');
  const [formDesc, setFormDesc] = useState('');
  const [creating, setCreating] = useState(false);

  const loadRoutines = useCallback(async () => {
    try {
      const data = await aaiApi.listRoutines();
      setRoutines(data.routines);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (isActive) loadRoutines();
  }, [isActive, loadRoutines]);

  const handleCreate = async () => {
    if (!formName.trim() || !formCron.trim() || !formTemplate.trim()) {
      toast.error('이름, Cron, 미션 템플릿은 필수입니다'); return;
    }
    setCreating(true);
    try {
      await aaiApi.createRoutine({
        name: formName, cron_expr: formCron, mission_template: formTemplate,
        description: formDesc, assigned_agent: formAgent, concurrency_policy: formPolicy,
      });
      toast.success('루틴 생성 완료');
      setShowCreate(false);
      setFormName(''); setFormCron('0 9 * * *'); setFormTemplate(''); setFormDesc('');
      loadRoutines();
    } catch { toast.error('루틴 생성 실패'); }
    finally { setCreating(false); }
  };

  const handleDelete = async (id: string) => {
    try {
      await aaiApi.deleteRoutine(id);
      setRoutines(prev => prev.filter(r => r.id !== id));
    } catch { toast.error('삭제 실패'); }
  };

  const handleExpand = async (id: string) => {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    setRunsLoading(true);
    try {
      const data = await aaiApi.getRoutineRuns(id);
      setRuns(data.runs);
    } catch { setRuns([]); }
    finally { setRunsLoading(false); }
  };

  const cronToHuman = (expr: string): string => {
    const parts = expr.split(' ');
    if (parts.length !== 5) return expr;
    const [min, hour, dom, mon, dow] = parts;
    if (dom === '*' && mon === '*' && dow === '*') return `매일 ${hour}:${min.padStart(2, '0')}`;
    if (dom === '*' && mon === '*' && dow === '1') return `매주 월요일 ${hour}:${min.padStart(2, '0')}`;
    if (dom === '*' && mon === '*' && dow === '1-5') return `평일 ${hour}:${min.padStart(2, '0')}`;
    if (min === '0' && hour === '*') return '매시간';
    if (min === '*/30') return '30분마다';
    return expr;
  };

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock size={16} className="text-zinc-500" />
          <span className="text-sm text-zinc-400">{routines.length}개 루틴</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadRoutines} className="p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500">
            <RefreshCw size={14} />
          </button>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1 px-3 py-1.5 bg-primary text-black rounded-lg text-xs font-medium hover:bg-primary/80"
          >
            {showCreate ? <X size={12} /> : <Plus size={12} />}
            {showCreate ? '닫기' : '새 루틴'}
          </button>
        </div>
      </div>

      {/* 생성 폼 */}
      {showCreate && (
        <div className="bg-dark-card border border-primary/20 rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input value={formName} onChange={e => setFormName(e.target.value)}
              placeholder="루틴 이름"
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary" />
            <input value={formCron} onChange={e => setFormCron(e.target.value)}
              placeholder="Cron (예: 0 9 * * *)"
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary font-mono" />
            <select value={formAgent} onChange={e => setFormAgent(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary">
              <option value="">에이전트 (CORE 결정)</option>
              {hrAgents.map(a => (
                <option key={a.name} value={a.name}>
                  {getDisplayName(a.name)}
                </option>
              ))}
            </select>
            <select value={formPolicy} onChange={e => setFormPolicy(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary">
              {Object.entries(POLICY_LABELS).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>
          <input value={formDesc} onChange={e => setFormDesc(e.target.value)}
            placeholder="설명 (선택)"
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary" />
          <textarea value={formTemplate} onChange={e => setFormTemplate(e.target.value)}
            placeholder="미션 템플릿 (루틴 실행 시 생성될 미션 내용)"
            rows={3}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary resize-none" />
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-zinc-600">미리보기: {cronToHuman(formCron)}</span>
            <button onClick={handleCreate} disabled={creating}
              className="flex items-center gap-1 px-4 py-2 bg-primary text-black rounded-lg text-sm font-medium disabled:opacity-50">
              {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
              루틴 생성
            </button>
          </div>
        </div>
      )}

      {/* 루틴 목록 */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 size={24} className="animate-spin text-zinc-500" /></div>
      ) : routines.length > 0 ? (
        <div className="space-y-2">
          {routines.map(r => {
            const isExpanded = expandedId === r.id;
            const p = r.assigned_agent ? getPersona(r.assigned_agent) : null;
            return (
              <div key={r.id} className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
                <div className="p-3 flex items-center gap-3 cursor-pointer hover:bg-zinc-800/30" onClick={() => handleExpand(r.id)}>
                  {isExpanded ? <ChevronDown size={14} className="text-zinc-500" /> : <ChevronRight size={14} className="text-zinc-500" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{r.name}</span>
                      <span className={`px-1.5 py-0.5 text-[10px] rounded-full ${
                        r.status === 'active' ? 'bg-green-500/20 text-green-400' :
                        r.status === 'paused' ? 'bg-amber-500/20 text-amber-400' :
                        'bg-zinc-700 text-zinc-500'
                      }`}>
                        {r.status === 'active' ? '활성' : r.status === 'paused' ? '일시정지' : '보관'}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-zinc-600 mt-0.5">
                      <span className="font-mono">{r.cron_expr}</span>
                      <span>({cronToHuman(r.cron_expr)})</span>
                      {r.assigned_agent && <span>{p?.emoji} {getDisplayName(r.assigned_agent)}</span>}
                      <span>실행 {r.run_count}회</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {r.next_run_at > 0 && (
                      <span className="text-[10px] text-zinc-600 mr-2">
                        다음: {new Date(r.next_run_at * 1000).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul' })}
                      </span>
                    )}
                    <button onClick={e => { e.stopPropagation(); handleDelete(r.id); }}
                      className="p-1.5 rounded-lg hover:bg-red-500/20 text-zinc-600 hover:text-red-400 transition-colors">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* 실행 이력 */}
                {isExpanded && (
                  <div className="border-t border-dark-border bg-zinc-900/50 p-3">
                    {r.description && <p className="text-xs text-zinc-500 mb-2">{r.description}</p>}
                    <div className="text-[10px] text-zinc-600 mb-2">실행 이력</div>
                    {runsLoading ? (
                      <div className="flex justify-center py-4"><Loader2 size={14} className="animate-spin text-zinc-600" /></div>
                    ) : runs.length > 0 ? (
                      <div className="space-y-1">
                        {runs.slice(0, 10).map(run => (
                          <div key={run.id} className="flex items-center gap-2 text-[11px] py-1">
                            {run.status === 'completed' ? <CheckCircle size={11} className="text-green-400" /> : <XCircle size={11} className="text-red-400" />}
                            <span className="text-zinc-500">{run.started_at ? new Date(run.started_at * 1000).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : '-'}</span>
                            <span className="text-zinc-600 truncate flex-1">{run.result?.slice(0, 60) || '-'}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[11px] text-zinc-700 py-2">실행 이력이 없습니다</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col items-center py-12 gap-3 text-zinc-600">
          <Clock size={32} />
          <p className="text-sm">등록된 루틴이 없습니다</p>
        </div>
      )}
    </div>
  );
}
