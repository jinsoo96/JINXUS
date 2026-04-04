'use client';

import { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { aaiApi, type AutonomyConfig, type HeartbeatStatus } from '@/lib/api';
import { getDisplayName, getPersona } from '@/lib/personas';
import { POLLING_INTERVAL_MS } from '@/lib/constants';
import toast from 'react-hot-toast';
import {
  Eye, ClipboardList, CheckCircle, Zap, RefreshCw, Loader2, Power,
  Heart, Mail, AlertTriangle,
} from 'lucide-react';

const AUTONOMY_LEVELS = [
  { level: 0, label: '관찰', icon: Eye, color: 'text-zinc-400', bg: 'bg-zinc-600' },
  { level: 1, label: '계획', icon: ClipboardList, color: 'text-blue-400', bg: 'bg-blue-500' },
  { level: 2, label: '확인 후 실행', icon: CheckCircle, color: 'text-amber-400', bg: 'bg-amber-500' },
  { level: 3, label: '자율 실행', icon: Zap, color: 'text-green-400', bg: 'bg-green-500' },
];

function AutonomyDial({ level, onChange }: { level: number; onChange: (l: number) => void }) {
  return (
    <div className="flex items-center gap-1">
      {AUTONOMY_LEVELS.map((al) => {
        const Icon = al.icon;
        const active = level >= al.level;
        const selected = level === al.level;
        return (
          <button
            key={al.level}
            onClick={() => onChange(al.level)}
            className={`flex flex-col items-center gap-0.5 px-1.5 py-1 sm:px-2 rounded-lg transition-all min-w-[44px] min-h-[44px] justify-center ${
              selected ? 'bg-zinc-700/60 ring-1 ring-primary/30' : 'hover:bg-zinc-800'
            }`}
            title={al.label}
          >
            <div className={`p-1 rounded-full ${active ? al.bg + '/20' : 'bg-zinc-800'}`}>
              <Icon size={14} className={active ? al.color : 'text-zinc-600'} />
            </div>
            <span className={`text-[8px] sm:text-[9px] ${selected ? al.color : 'text-zinc-600'}`}>{al.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function ControlPanel({ isActive }: { isActive: boolean }) {
  const { hrAgents } = useAppStore();
  const [configs, setConfigs] = useState<Record<string, AutonomyConfig>>({});
  const [heartbeats, setHeartbeats] = useState<Record<string, HeartbeatStatus>>({});
  const [unread, setUnread] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [waking, setWaking] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [autonomy, hb, inbox] = await Promise.all([
        aaiApi.getAutonomyConfigs().catch(() => ({ agents: {} })),
        aaiApi.getHeartbeatStatus().catch(() => ({ heartbeats: {} })),
        aaiApi.getAllUnread().catch(() => ({ unread: {} })),
      ]);
      setConfigs(autonomy.agents);
      setHeartbeats(hb.heartbeats);
      setUnread(inbox.unread);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (!isActive) return;
    loadData();
    const id = setInterval(() => {
      if (document.visibilityState === 'visible') loadData();
    }, POLLING_INTERVAL_MS);
    return () => clearInterval(id);
  }, [isActive, loadData]);

  const handleToggle = async (agent: string, enabled: boolean) => {
    const current = configs[agent] || { agent, autopilot_enabled: false, autonomy_level: 0, triggers_enabled: true, heartbeat_interval: 3600, budget_usd: 100 };
    try {
      const result = await aaiApi.setAutonomyConfig({ ...current, agent, autopilot_enabled: enabled });
      setConfigs(prev => ({ ...prev, [agent]: result }));
    } catch { toast.error('설정 저장 실패'); }
  };

  const handleLevelChange = async (agent: string, level: number) => {
    const current = configs[agent] || { agent, autopilot_enabled: true, autonomy_level: 0, triggers_enabled: true, heartbeat_interval: 3600, budget_usd: 100 };
    try {
      const result = await aaiApi.setAutonomyConfig({ ...current, agent, autonomy_level: level, autopilot_enabled: true });
      setConfigs(prev => ({ ...prev, [agent]: result }));
    } catch { toast.error('설정 저장 실패'); }
  };

  const handleWake = async (agent: string) => {
    setWaking(agent);
    try {
      await aaiApi.wakeAgent(agent, 'manual', '수동 깨우기');
      toast.success(`${getDisplayName(agent)} 깨우기 완료`);
    } catch { toast.error('깨우기 실패'); }
    finally { setWaking(null); }
  };

  const handleMasterToggle = async (enabled: boolean) => {
    const agents = hrAgents.map(a => a.name).filter(Boolean);
    for (const agent of agents) {
      await handleToggle(agent, enabled);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={28} className="animate-spin text-zinc-500" />
      </div>
    );
  }

  const agentList = hrAgents.filter(a => (a.name) !== 'JINXUS_CORE');
  const activeCount = Object.values(configs).filter(c => c.autopilot_enabled).length;

  return (
    <div className="space-y-4">
      {/* 마스터 토글 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-dark-card border border-dark-border rounded-xl p-3 sm:p-4">
        <div className="flex items-center gap-3">
          <Power size={18} className={activeCount > 0 ? 'text-green-400' : 'text-zinc-500'} />
          <div>
            <span className="font-semibold text-sm sm:text-base">오토파일럿 마스터</span>
            <span className="text-xs text-zinc-500 ml-2">{activeCount}개 활성</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleMasterToggle(true)}
            className="px-3 py-2 sm:py-1.5 text-xs bg-green-500/20 text-green-400 rounded-lg hover:bg-green-500/30 transition-colors min-h-[44px] sm:min-h-0"
          >
            전체 ON
          </button>
          <button
            onClick={() => handleMasterToggle(false)}
            className="px-3 py-2 sm:py-1.5 text-xs bg-zinc-700 text-zinc-400 rounded-lg hover:bg-zinc-600 transition-colors min-h-[44px] sm:min-h-0"
          >
            전체 OFF
          </button>
          <button onClick={loadData} className="p-2.5 sm:p-1.5 rounded-lg hover:bg-zinc-800 text-zinc-500 min-h-[44px] sm:min-h-0 min-w-[44px] sm:min-w-0 flex items-center justify-center">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* 에이전트 그리드 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {agentList.map((hr) => {
          const agent = hr.name;
          const config = configs[agent] || { agent, autopilot_enabled: false, autonomy_level: 0 };
          const hb = heartbeats[agent];
          const p = getPersona(agent);
          const inboxCount = unread[agent] || 0;
          const isOn = config.autopilot_enabled;

          return (
            <div
              key={agent}
              className={`bg-dark-card border rounded-xl p-4 transition-all ${
                isOn ? 'border-green-500/30 shadow-[0_0_8px_rgba(74,222,128,0.1)]' : 'border-dark-border'
              }`}
            >
              {/* 상단: 에이전트 정보 + 토글 */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{p?.emoji || '🤖'}</span>
                  <div>
                    <div className="font-medium text-sm">{getDisplayName(agent)}</div>
                    <div className="text-[10px] text-zinc-600">{p?.role ?? agent}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {inboxCount > 0 && (
                    <span className="flex items-center gap-0.5 text-[10px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded-full">
                      <Mail size={10} /> {inboxCount}
                    </span>
                  )}
                  <button
                    onClick={() => handleToggle(agent, !isOn)}
                    className={`relative w-12 h-7 sm:w-10 sm:h-5 rounded-full transition-colors ${isOn ? 'bg-green-500' : 'bg-zinc-700'}`}
                  >
                    <span className={`absolute top-0.5 sm:top-0.5 w-6 h-6 sm:w-4 sm:h-4 rounded-full bg-white transition-transform ${isOn ? 'translate-x-5' : 'translate-x-0.5'}`} />
                  </button>
                </div>
              </div>

              {/* Autonomy Dial */}
              <AutonomyDial
                level={config.autonomy_level}
                onChange={(l) => handleLevelChange(agent, l)}
              />

              {/* 하단: 하트비트 + 깨우기 */}
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-dark-border">
                <div className="flex items-center gap-1.5 text-[10px] text-zinc-600">
                  <Heart size={10} className={hb?.last_heartbeat_at ? 'text-red-400' : 'text-zinc-700'} />
                  <span>{hb?.last_heartbeat_at ? new Date(hb.last_heartbeat_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Seoul' }) : '없음'}</span>
                </div>
                <button
                  onClick={() => handleWake(agent)}
                  disabled={waking === agent}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] bg-zinc-800 hover:bg-zinc-700 rounded-lg text-zinc-400 hover:text-white transition-colors disabled:opacity-50"
                >
                  {waking === agent ? <Loader2 size={10} className="animate-spin" /> : <Zap size={10} />}
                  깨우기
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {agentList.length === 0 && (
        <div className="flex flex-col items-center py-12 gap-3 text-zinc-600">
          <AlertTriangle size={32} />
          <p className="text-sm">등록된 에이전트가 없습니다</p>
        </div>
      )}
    </div>
  );
}
