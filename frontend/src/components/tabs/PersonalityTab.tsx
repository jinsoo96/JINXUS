'use client';

import { useState, useEffect, useCallback } from 'react';
import { personalityApi, ttsApi, type PersonalityProfileData } from '@/lib/api';
import { getAudioManager } from '@/lib/audioManager';
import { useAppStore } from '@/store/useAppStore';
import { getDisplayName, getPersona, getTeamGroups, getTeamConfig } from '@/lib/personas';
import toast from 'react-hot-toast';
import {
  Loader2, Volume2, VolumeX, Square, ChevronRight,
  Brain, Heart, Zap, Shield, AlertTriangle, Sparkles,
  RefreshCw, Play, User,
} from 'lucide-react';

// OCEAN 바 컴포넌트
function OceanBar({ label, short, value, color }: { label: string; short: string; value: number; color: string }) {
  const pct = Math.round(value * 100);
  const level = pct >= 66 ? 'HIGH' : pct >= 33 ? 'MID' : 'LOW';
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-zinc-500 w-6 text-right font-mono">{short}</span>
      <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-[10px] text-zinc-400 w-8 font-mono">{pct}%</span>
      <span className={`text-[8px] px-1 py-0.5 rounded ${
        level === 'HIGH' ? 'bg-green-500/20 text-green-400' :
        level === 'MID' ? 'bg-amber-500/20 text-amber-400' :
        'bg-zinc-700 text-zinc-500'
      }`}>{level}</span>
    </div>
  );
}

// 감정 뱃지
function EmotionBadge({ label }: { label: string }) {
  const config: Record<string, { color: string; icon: typeof Heart }> = {
    joy: { color: 'text-yellow-400 bg-yellow-500/15', icon: Sparkles },
    anger: { color: 'text-red-400 bg-red-500/15', icon: Zap },
    sadness: { color: 'text-blue-400 bg-blue-500/15', icon: Heart },
    fear: { color: 'text-purple-400 bg-purple-500/15', icon: AlertTriangle },
    surprise: { color: 'text-cyan-400 bg-cyan-500/15', icon: Zap },
    excitement: { color: 'text-orange-400 bg-orange-500/15', icon: Sparkles },
    calm: { color: 'text-green-400 bg-green-500/15', icon: Shield },
    neutral: { color: 'text-zinc-400 bg-zinc-700', icon: Brain },
  };
  const c = config[label] || config.neutral;
  const Icon = c.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${c.color}`}>
      <Icon size={10} />
      {label}
    </span>
  );
}

// SVG 아바타 생성 — 에이전트 코드 해시 + OCEAN으로 고유 외형
function AgentAvatar({ agent, ocean, speaking, size = 120 }: {
  agent: string; ocean: PersonalityProfileData['ocean']; speaking: boolean; size?: number;
}) {
  // 에이전트별 결정적 해시로 색상/형태 생성
  const h = Array.from(agent).reduce((a, c) => a + c.charCodeAt(0), 0);
  const hue = h % 360;
  const skinTones = ['#F5D0A9', '#E8C39E', '#D4A574', '#C68642', '#8D5524', '#FFDBB4'];
  const skinIdx = h % skinTones.length;
  const hairColors = ['#1a1a2e', '#2d1810', '#5c3317', '#8B4513', '#D2691E', '#4a0e0e', '#1e3a5f', '#3d1e6d'];
  const hairIdx = (h * 7) % hairColors.length;
  const hairStyles = ['round', 'spiky', 'long', 'bob', 'parted'];
  const hairStyle = hairStyles[(h * 3) % hairStyles.length];
  const hasGlasses = ocean.conscientiousness > 0.7 || ocean.openness > 0.8;
  const eyeSize = 3 + ocean.extraversion * 2;
  const mouthCurve = ocean.agreeableness > 0.5 ? 3 : -1;
  const blushOpacity = ocean.neuroticism > 0.5 ? 0.3 : 0;

  return (
    <svg width={size} height={size} viewBox="0 0 80 80" className={speaking ? 'animate-pulse' : ''}>
      {/* 배경 오라 */}
      <circle cx="40" cy="40" r="38" fill={`hsl(${hue}, 40%, 15%)`} opacity="0.5" />
      {/* 머리카락 (뒷부분) */}
      {hairStyle === 'long' && <ellipse cx="40" cy="38" rx="22" ry="28" fill={hairColors[hairIdx]} />}
      {/* 얼굴 */}
      <ellipse cx="40" cy="42" rx="18" ry="20" fill={skinTones[skinIdx]} />
      {/* 머리카락 */}
      {hairStyle === 'round' && <ellipse cx="40" cy="30" rx="19" ry="14" fill={hairColors[hairIdx]} />}
      {hairStyle === 'spiky' && <>
        <ellipse cx="40" cy="31" rx="18" ry="12" fill={hairColors[hairIdx]} />
        <polygon points="26,28 30,16 34,28" fill={hairColors[hairIdx]} />
        <polygon points="36,26 40,14 44,26" fill={hairColors[hairIdx]} />
        <polygon points="46,28 50,16 54,28" fill={hairColors[hairIdx]} />
      </>}
      {hairStyle === 'bob' && <path d="M22,35 Q22,20 40,18 Q58,20 58,35 L56,42 Q56,44 54,44 L26,44 Q24,44 24,42 Z" fill={hairColors[hairIdx]} />}
      {hairStyle === 'parted' && <>
        <ellipse cx="40" cy="30" rx="19" ry="13" fill={hairColors[hairIdx]} />
        <ellipse cx="35" cy="28" rx="12" ry="8" fill={hairColors[hairIdx]} />
      </>}
      {hairStyle === 'long' && <path d="M22,30 Q22,18 40,16 Q58,18 58,30 L60,50 Q58,52 56,48 L56,35 L24,35 L24,48 Q22,52 20,50 Z" fill={hairColors[hairIdx]} />}
      {/* 눈 */}
      <ellipse cx="33" cy="42" rx={eyeSize} ry={eyeSize + 0.5} fill="white" />
      <ellipse cx="47" cy="42" rx={eyeSize} ry={eyeSize + 0.5} fill="white" />
      <circle cx="33" cy="42" r={eyeSize - 1.2} fill="#1a1a2e" />
      <circle cx="47" cy="42" r={eyeSize - 1.2} fill="#1a1a2e" />
      <circle cx="34" cy="41" r="1" fill="white" />
      <circle cx="48" cy="41" r="1" fill="white" />
      {/* 안경 */}
      {hasGlasses && <>
        <circle cx="33" cy="42" r={eyeSize + 1.5} fill="none" stroke="#555" strokeWidth="0.8" />
        <circle cx="47" cy="42" r={eyeSize + 1.5} fill="none" stroke="#555" strokeWidth="0.8" />
        <line x1={33 + eyeSize + 1.5} y1="42" x2={47 - eyeSize - 1.5} y2="42" stroke="#555" strokeWidth="0.8" />
      </>}
      {/* 볼터치 */}
      {blushOpacity > 0 && <>
        <circle cx="27" cy="48" r="3" fill="#ff6b6b" opacity={blushOpacity} />
        <circle cx="53" cy="48" r="3" fill="#ff6b6b" opacity={blushOpacity} />
      </>}
      {/* 입 */}
      <path d={`M35,52 Q40,${52 + mouthCurve} 45,52`} fill="none" stroke="#333" strokeWidth="1.2" strokeLinecap="round" />
      {/* 말하는 중 — 입 벌림 */}
      {speaking && <ellipse cx="40" cy="53" rx="4" ry="3" fill="#333" opacity="0.8">
        <animate attributeName="ry" values="3;4;2;3" dur="0.4s" repeatCount="indefinite" />
      </ellipse>}
    </svg>
  );
}

// Neural Fingerprint SVG 표시
function NeuralFingerprint({ agent }: { agent: string }) {
  const [svg, setSvg] = useState<string>('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSvg('');
    personalityApi.getFingerprint(agent)
      .then(data => { if (!cancelled) setSvg(data); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [agent]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 size={16} className="animate-spin text-zinc-600" />
      </div>
    );
  }
  if (!svg) return null;

  return (
    <div className="mt-3">
      <span className="text-[10px] text-zinc-600 uppercase tracking-wider">Neural Fingerprint</span>
      <div
        className="mt-1 rounded-xl overflow-hidden bg-white/5 flex items-center justify-center"
        dangerouslySetInnerHTML={{ __html: svg }}
        style={{ maxWidth: '100%' }}
      />
    </div>
  );
}

// 2D 캐릭터 카드
function CharacterCard({ profile, onSpeak, speaking }: {
  profile: PersonalityProfileData;
  onSpeak: () => void;
  speaking: boolean;
}) {
  const p = getPersona(profile.agent);
  const teamConfig = getTeamConfig(profile.team);

  return (
    <div className="bg-dark-card border border-dark-border rounded-2xl overflow-hidden">
      {/* 캐릭터 헤더 — 팀 색상 그라디언트 + SVG 아바타 */}
      <div className="relative h-40 flex items-center justify-center"
        style={{ background: `linear-gradient(135deg, ${teamConfig?.color || '#3b82f6'}15, #0d0d12)` }}>
        <AgentAvatar agent={profile.agent} ocean={profile.ocean} speaking={speaking} size={130} />
        {/* 감정 뱃지 */}
        <div className="absolute top-3 right-3">
          <EmotionBadge label={profile.emotion_label} />
        </div>
        {/* TTS 재생 버튼 */}
        <button
          onClick={onSpeak}
          disabled={speaking}
          className="absolute bottom-3 right-3 flex items-center gap-1 px-3 py-1.5 rounded-lg bg-zinc-900/80 border border-zinc-700 text-xs text-zinc-300 hover:text-white hover:border-zinc-500 transition-all disabled:opacity-50"
        >
          {speaking ? <Loader2 size={12} className="animate-spin" /> : <Volume2 size={12} />}
          {speaking ? '재생중...' : '음성 듣기'}
        </button>
      </div>

      {/* 에이전트 정보 */}
      <div className="p-4 space-y-4">
        <div className="text-center">
          <h3 className="text-lg font-bold">{profile.name || getDisplayName(profile.agent)}</h3>
          <p className="text-xs text-zinc-500">{profile.role}</p>
          <div className="flex items-center justify-center gap-2 mt-1">
            {profile.mbti && (
              <span className="text-[10px] px-2 py-0.5 rounded bg-primary/15 text-primary font-mono">{profile.mbti}</span>
            )}
            <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-500">{profile.team}</span>
          </div>
        </div>

        {/* OCEAN 바 */}
        <div className="space-y-1.5">
          <span className="text-[10px] text-zinc-600 uppercase tracking-wider">OCEAN Personality</span>
          <OceanBar label="Openness" short="O" value={profile.ocean.openness} color="#8b5cf6" />
          <OceanBar label="Conscientiousness" short="C" value={profile.ocean.conscientiousness} color="#3b82f6" />
          <OceanBar label="Extraversion" short="E" value={profile.ocean.extraversion} color="#f59e0b" />
          <OceanBar label="Agreeableness" short="A" value={profile.ocean.agreeableness} color="#22c55e" />
          <OceanBar label="Neuroticism" short="N" value={profile.ocean.neuroticism} color="#ef4444" />
        </div>

        {/* 말투 스타일 */}
        {profile.speech_style && (
          <div>
            <span className="text-[10px] text-zinc-600 uppercase tracking-wider">Speaking Style</span>
            <p className="text-xs text-zinc-400 mt-1 leading-relaxed">{profile.speech_style}</p>
          </div>
        )}

        {/* Neural Fingerprint */}
        <NeuralFingerprint agent={profile.agent} />

        {/* 음성 설정 */}
        <div className="flex items-center justify-between text-[10px] text-zinc-600 pt-2 border-t border-dark-border">
          <span>Voice: {profile.voice_id.replace('ko-KR-', '').replace('Neural', '')}</span>
        </div>
      </div>
    </div>
  );
}

// 멤버 리스트 아이템
function MemberItem({ agent, isSelected, onClick, emotion_label }: {
  agent: string;
  isSelected: boolean;
  onClick: () => void;
  emotion_label: string;
}) {
  const p = getPersona(agent);
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all min-h-[44px] ${
        isSelected ? 'bg-zinc-700/60 text-white' : 'text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200'
      }`}
    >
      <span className="text-base">{p?.emoji || '🤖'}</span>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium truncate">{getDisplayName(agent)}</div>
        <div className="text-[10px] text-zinc-600 truncate">{p?.role || agent}</div>
      </div>
      <EmotionBadge label={emotion_label} />
      <ChevronRight size={12} className="text-zinc-700 flex-shrink-0" />
    </button>
  );
}

export default function PersonalityTab({ isActive = true }: { isActive?: boolean }) {
  const { hrAgents, personasVersion } = useAppStore();
  const [profiles, setProfiles] = useState<Record<string, PersonalityProfileData>>({});
  const [selectedAgent, setSelectedAgent] = useState('');
  const [loading, setLoading] = useState(true);
  const [speaking, setSpeaking] = useState(false);

  const loadProfiles = useCallback(async () => {
    try {
      const data = await personalityApi.getProfiles();
      setProfiles(data.profiles);
      // 첫 에이전트 자동 선택
      if (!selectedAgent && Object.keys(data.profiles).length > 0) {
        const first = hrAgents.find(a => a.is_active && a.name)?.name;
        if (first) setSelectedAgent(first);
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [hrAgents, selectedAgent]);

  useEffect(() => {
    if (isActive) loadProfiles();
    // personasVersion 변경 시 (이름변경/고용/해고) 자동 리로드
  }, [isActive, loadProfiles, personasVersion]);

  const handleSpeak = async () => {
    const profile = profiles[selectedAgent];
    if (!profile) return;
    setSpeaking(true);
    try {
      const greetings = [
        `안녕하세요, ${profile.name || getDisplayName(selectedAgent)}입니다.`,
        `${profile.role}를 맡고 있습니다.`,
      ];
      const text = greetings.join(' ');
      const blob = await ttsApi.speak(text, selectedAgent, profile.emotion_label);
      const mgr = getAudioManager();
      await mgr.playBlob(blob);
    } catch {
      toast.error('음성 재생 실패');
    } finally {
      setSpeaking(false);
    }
  };

  const handleStop = () => {
    getAudioManager().stop();
    setSpeaking(false);
  };

  const selectedProfile = profiles[selectedAgent];
  const agentList = hrAgents.filter(a => a.is_active && a.name);

  // 팀별 그룹핑
  const teamGroups = getTeamGroups();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={28} className="animate-spin text-zinc-500" />
      </div>
    );
  }

  return (
    <div className="flex gap-4 h-full min-h-[500px]">
      {/* 좌측: 멤버 목록 */}
      <div className="w-56 flex-shrink-0 bg-dark-card border border-dark-border rounded-xl overflow-hidden flex flex-col">
        <div className="p-3 border-b border-dark-border flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <User size={13} className="text-zinc-500" />
            <span className="text-xs text-zinc-400">{agentList.length}명</span>
          </div>
          <button onClick={loadProfiles} className="p-1 rounded hover:bg-zinc-800 text-zinc-500">
            <RefreshCw size={12} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5">
          {Object.entries(teamGroups).map(([team, agents]) => {
            const teamAgents = agents.filter(a => agentList.some(hr => hr.name === a));
            if (teamAgents.length === 0) return null;
            return (
              <div key={team}>
                <div className="text-[9px] text-zinc-600 uppercase tracking-wider px-3 py-1 mt-1">{team}</div>
                {teamAgents.map(agent => (
                  <MemberItem
                    key={agent}
                    agent={agent}
                    isSelected={selectedAgent === agent}
                    onClick={() => setSelectedAgent(agent)}
                    emotion_label={profiles[agent]?.emotion_label || 'neutral'}
                  />
                ))}
              </div>
            );
          })}
        </div>
      </div>

      {/* 우측: 캐릭터 카드 */}
      <div className="flex-1 overflow-y-auto">
        {selectedProfile ? (
          <div className="max-w-md mx-auto">
            <CharacterCard
              profile={selectedProfile}
              onSpeak={handleSpeak}
              speaking={speaking}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-zinc-600">
            <Brain size={40} />
            <p className="text-sm">멤버를 선택하세요</p>
          </div>
        )}
      </div>
    </div>
  );
}
