'use client';

import { useState, useEffect, useCallback } from 'react';
import { aaiApi, type TriggerConfig } from '@/lib/api';
import { useAppStore } from '@/store/useAppStore';
import { getDisplayName, getPersona } from '@/lib/personas';
import toast from 'react-hot-toast';
import {
  Plus, Trash2, Clock, Webhook, Moon, ArrowRight, TrendingUp,
  Loader2, RefreshCw, X, Radio,
} from 'lucide-react';

const TRIGGER_TYPES = [
  { id: 'all', label: '전체', icon: Radio },
  { id: 'cron', label: '시간', icon: Clock },
  { id: 'event', label: '이벤트', icon: Webhook },
  { id: 'idle', label: '유휴', icon: Moon },
  { id: 'interaction', label: '상호작용', icon: ArrowRight },
  { id: 'threshold', label: '임계값', icon: TrendingUp },
];

const TYPE_COLORS: Record<string, string> = {
  cron: 'bg-blue-500/20 text-blue-400',
  event: 'bg-purple-500/20 text-purple-400',
  idle: 'bg-indigo-500/20 text-indigo-400',
  interaction: 'bg-amber-500/20 text-amber-400',
  threshold: 'bg-red-500/20 text-red-400',
};

export default function TriggerPanel({ isActive }: { isActive: boolean }) {
  const { hrAgents } = useAppStore();
  const [triggers, setTriggers] = useState<TriggerConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('all');
  const [showCreate, setShowCreate] = useState(false);

  // 생성 폼
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState('cron');
  const [formAgent, setFormAgent] = useState('');
  const [formDesc, setFormDesc] = useState('');
  const [formConfig, setFormConfig] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);

  const loadTriggers = useCallback(async () => {
    try {
      const data = await aaiApi.listTriggers(filterType === 'all' ? undefined : filterType);
      setTriggers(data.triggers);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [filterType]);

  useEffect(() => {
    if (isActive) loadTriggers();
  }, [isActive, loadTriggers]);

  const handleCreate = async () => {
    if (!formName.trim()) { toast.error('이름을 입력하세요'); return; }
    setCreating(true);
    try {
      const config: Record<string, unknown> = {};
      if (formType === 'cron') {
        config.cron_expr = formConfig.cron_expr || '0 9 * * *';
        config.mission_template = formConfig.mission_template || '';
      } else if (formType === 'idle') {
        config.idle_minutes = parseInt(formConfig.idle_minutes || '30');
        config.mission_template = formConfig.mission_template || '';
      } else if (formType === 'event') {
        config.event_source = formConfig.event_source || 'mission_complete';
        config.filter = formConfig.filter || '';
      } else if (formType === 'interaction') {
        config.source_agent = formConfig.source_agent || '';
        config.condition = formConfig.condition || 'always';
        config.mission_template = formConfig.mission_template || '';
      } else if (formType === 'threshold') {
        config.metric = formConfig.metric || 'budget_usage';
        config.operator = formConfig.operator || '>';
        config.value = parseFloat(formConfig.value || '80');
      }

      await aaiApi.createTrigger({
        name: formName,
        type: formType,
        agent: formAgent,
        config,
        description: formDesc,
      });
      toast.success('트리거 생성 완료');
      setShowCreate(false);
      setFormName(''); setFormDesc(''); setFormConfig({});
      loadTriggers();
    } catch { toast.error('트리거 생성 실패'); }
    finally { setCreating(false); }
  };

  const handleDelete = async (id: string) => {
    try {
      await aaiApi.deleteTrigger(id);
      setTriggers(prev => prev.filter(t => t.id !== id));
    } catch { toast.error('삭제 실패'); }
  };

  const handleToggle = async (id: string, enabled: boolean) => {
    try {
      await aaiApi.toggleTrigger(id, enabled);
      setTriggers(prev => prev.map(t => t.id === id ? { ...t, enabled } : t));
    } catch { toast.error('변경 실패'); }
  };

  return (
    <div className="space-y-4">
      {/* 필터 탭 + 생성 버튼 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex gap-1 overflow-x-auto pb-1 sm:pb-0 -mx-1 px-1">
          {TRIGGER_TYPES.map(t => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                onClick={() => setFilterType(t.id)}
                className={`flex items-center gap-1 px-3 py-2 sm:py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap min-h-[44px] sm:min-h-0 ${
                  filterType === t.id ? 'bg-zinc-700 text-white' : 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800'
                }`}
              >
                <Icon size={12} /> {t.label}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={loadTriggers} className="p-2.5 sm:p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 min-h-[44px] sm:min-h-0 min-w-[44px] sm:min-w-0 flex items-center justify-center">
            <RefreshCw size={14} />
          </button>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-1 px-3 py-2 sm:py-1.5 bg-primary text-black rounded-lg text-xs font-medium hover:bg-primary/80 min-h-[44px] sm:min-h-0"
          >
            {showCreate ? <X size={12} /> : <Plus size={12} />}
            {showCreate ? '닫기' : '새 트리거'}
          </button>
        </div>
      </div>

      {/* 생성 폼 */}
      {showCreate && (
        <div className="bg-dark-card border border-primary/20 rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input
              value={formName} onChange={e => setFormName(e.target.value)}
              placeholder="트리거 이름"
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
            />
            <select
              value={formType} onChange={e => { setFormType(e.target.value); setFormConfig({}); }}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
            >
              {TRIGGER_TYPES.filter(t => t.id !== 'all').map(t => (
                <option key={t.id} value={t.id}>{t.label}</option>
              ))}
            </select>
            <select
              value={formAgent} onChange={e => setFormAgent(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
            >
              <option value="">에이전트 선택</option>
              {hrAgents.map(a => (
                <option key={a.name} value={a.name}>
                  {getDisplayName(a.name)}
                </option>
              ))}
            </select>
            <input
              value={formDesc} onChange={e => setFormDesc(e.target.value)}
              placeholder="설명 (선택)"
              className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
            />
          </div>

          {/* 타입별 설정 */}
          <div className="space-y-2">
            {formType === 'cron' && (
              <>
                <input
                  value={formConfig.cron_expr || ''} onChange={e => setFormConfig(p => ({ ...p, cron_expr: e.target.value }))}
                  placeholder="Cron 표현식 (예: 0 9 * * * = 매일 9시)"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary font-mono"
                />
                <textarea
                  value={formConfig.mission_template || ''} onChange={e => setFormConfig(p => ({ ...p, mission_template: e.target.value }))}
                  placeholder="미션 템플릿 (실행할 작업 내용)"
                  rows={2}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary resize-none"
                />
              </>
            )}
            {formType === 'idle' && (
              <>
                <input
                  type="number"
                  value={formConfig.idle_minutes || '30'} onChange={e => setFormConfig(p => ({ ...p, idle_minutes: e.target.value }))}
                  placeholder="유휴 임계치 (분)"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                />
                <textarea
                  value={formConfig.mission_template || ''} onChange={e => setFormConfig(p => ({ ...p, mission_template: e.target.value }))}
                  placeholder="유휴 시 실행할 작업"
                  rows={2}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary resize-none"
                />
              </>
            )}
            {formType === 'event' && (
              <>
                <select
                  value={formConfig.event_source || ''} onChange={e => setFormConfig(p => ({ ...p, event_source: e.target.value }))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                >
                  <option value="mission_complete">미션 완료</option>
                  <option value="inbox_message">인박스 메시지</option>
                  <option value="github_pr">GitHub PR</option>
                  <option value="error_spike">에러 급증</option>
                </select>
                <input
                  value={formConfig.filter || ''} onChange={e => setFormConfig(p => ({ ...p, filter: e.target.value }))}
                  placeholder="필터 조건 (선택)"
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                />
              </>
            )}
            {formType === 'interaction' && (
              <>
                <select
                  value={formConfig.source_agent || ''} onChange={e => setFormConfig(p => ({ ...p, source_agent: e.target.value }))}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                >
                  <option value="">소스 에이전트 선택</option>
                  {hrAgents.map(a => (
                    <option key={a.name} value={a.name}>
                      {getDisplayName(a.name)}
                    </option>
                  ))}
                </select>
                <textarea
                  value={formConfig.mission_template || ''} onChange={e => setFormConfig(p => ({ ...p, mission_template: e.target.value }))}
                  placeholder="트리거 시 실행할 미션"
                  rows={2}
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary resize-none"
                />
              </>
            )}
            {formType === 'threshold' && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <select
                  value={formConfig.metric || ''} onChange={e => setFormConfig(p => ({ ...p, metric: e.target.value }))}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                >
                  <option value="budget_usage">예산 사용률 (%)</option>
                  <option value="error_rate">에러율 (%)</option>
                </select>
                <select
                  value={formConfig.operator || '>'} onChange={e => setFormConfig(p => ({ ...p, operator: e.target.value }))}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                >
                  <option value=">">{'>'}</option>
                  <option value=">=">{'>='}</option>
                  <option value="<">{'<'}</option>
                </select>
                <input
                  type="number"
                  value={formConfig.value || '80'} onChange={e => setFormConfig(p => ({ ...p, value: e.target.value }))}
                  placeholder="값"
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                />
              </div>
            )}
          </div>

          <button
            onClick={handleCreate}
            disabled={creating || !formName.trim()}
            className="w-full py-2 bg-primary text-black rounded-lg text-sm font-medium hover:bg-primary/80 disabled:opacity-50 flex items-center justify-center gap-1"
          >
            {creating ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
            트리거 생성
          </button>
        </div>
      )}

      {/* 트리거 목록 */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 size={24} className="animate-spin text-zinc-500" /></div>
      ) : triggers.length > 0 ? (
        <div className="space-y-2">
          {triggers.map(t => {
            const typeInfo = TRIGGER_TYPES.find(tt => tt.id === t.type);
            const TypeIcon = typeInfo?.icon ?? Radio;
            return (
              <div key={t.id} className="bg-dark-card border border-dark-border rounded-xl p-3">
                <div className="flex items-start sm:items-center gap-3">
                  <TypeIcon size={16} className="text-zinc-500 flex-shrink-0 mt-0.5 sm:mt-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm truncate">{t.name}</span>
                      <span className={`px-1.5 py-0.5 text-[10px] rounded-full ${TYPE_COLORS[t.type] || 'bg-zinc-700 text-zinc-400'}`}>
                        {typeInfo?.label ?? t.type}
                      </span>
                      {t.agent && (
                        <span className="text-[10px] text-zinc-500">
                          {getPersona(t.agent)?.emoji} {getDisplayName(t.agent)}
                        </span>
                      )}
                    </div>
                    {t.description && <p className="text-[11px] text-zinc-600 truncate">{t.description}</p>}
                    <div className="flex items-center gap-3 text-[10px] text-zinc-600 mt-0.5">
                      <span>발동 {t.fire_count}회</span>
                      {t.last_fired_at > 0 && (
                        <span>마지막: {new Date(t.last_fired_at * 1000).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => handleToggle(t.id, !t.enabled)}
                      className={`relative w-12 h-7 sm:w-9 sm:h-5 rounded-full transition-colors flex-shrink-0 ${t.enabled ? 'bg-green-500' : 'bg-zinc-700'}`}
                    >
                      <span className={`absolute top-0.5 sm:top-0.5 w-6 h-6 sm:w-4 sm:h-4 rounded-full bg-white transition-transform ${t.enabled ? 'translate-x-5 sm:translate-x-4' : 'translate-x-0.5'}`} />
                    </button>
                    <button
                      onClick={() => handleDelete(t.id)}
                      className="p-2.5 sm:p-1.5 rounded-lg hover:bg-red-500/20 text-zinc-600 hover:text-red-400 transition-colors flex-shrink-0 min-h-[44px] sm:min-h-0 min-w-[44px] sm:min-w-0 flex items-center justify-center"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col items-center py-12 gap-3 text-zinc-600">
          <Radio size={32} />
          <p className="text-sm">등록된 트리거가 없습니다</p>
          <p className="text-xs text-zinc-700">위의 &apos;새 트리거&apos; 버튼으로 추가하세요</p>
        </div>
      )}
    </div>
  );
}
