'use client';

import { useState, useEffect, useRef } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { memoryApi } from '@/lib/api';
import { getDisplayName, getPersona } from '@/lib/personas';
import { Search, Brain, Clock, CheckCircle, XCircle, RefreshCw, Loader2, Database, ChevronDown } from 'lucide-react';
import type { MemorySearchResult } from '@/types';

interface CollectionStat {
  vectors_count: number;
  status?: string;
  error?: string;
}

interface MemoryStats {
  total_tasks_logged: number;
  collections: Record<string, CollectionStat>;
  health?: Record<string, boolean>;
}

export default function MemoryTab() {
  const { agents } = useAppStore();
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MemorySearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [stats, setStats] = useState<MemoryStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // 드롭다운 바깥 클릭 시 닫기
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 메모리 통계 로드
  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const res = await memoryApi.getStats();
      setStats(res as MemoryStats);
    } catch { /* 무시 */ }
    finally { setStatsLoading(false); }
  };

  useEffect(() => { loadStats(); }, []);

  const doSearch = async () => {
    if (!selectedAgent || !query.trim()) return;
    setIsSearching(true);
    setError(null);
    try {
      const response = await memoryApi.search(selectedAgent, query.trim());
      setResults(response.results);
      setHasSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : '검색 중 오류가 발생했습니다.');
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    doSearch();
  };

  // 에이전트 코드명 → 표시이름 + 이모지
  const agentLabel = (code: string) => {
    const p = getPersona(code);
    return p ? `${p.emoji} ${getDisplayName(code)}` : getDisplayName(code);
  };

  // 컬렉션 통계에서 에이전트 코드 → 메모리 수
  const getMemoryCount = (agentCode: string): number => {
    if (!stats?.collections) return 0;
    return stats.collections[agentCode]?.vectors_count ?? 0;
  };

  const totalMemories = Object.values(stats?.collections ?? {}).reduce(
    (sum, s) => sum + (s.vectors_count ?? 0), 0
  );

  return (
    <div className="h-full flex flex-col gap-4 min-h-0">

      {/* 헤더 */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <Brain size={20} className="text-primary" />
          <h2 className="text-lg font-bold">장기 메모리</h2>
          <span className="text-xs text-zinc-500">Qdrant 벡터 DB</span>
        </div>
        <button
          onClick={loadStats}
          className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors"
          title="새로고침"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 flex-shrink-0">
        {/* 총 장기기억 */}
        <div className="bg-dark-card border border-dark-border rounded-xl p-3">
          <div className="flex items-center gap-2 mb-1">
            <Database size={14} className="text-primary" />
            <span className="text-[11px] text-zinc-500 uppercase">장기기억</span>
          </div>
          {statsLoading ? (
            <Loader2 size={14} className="animate-spin text-zinc-500" />
          ) : (
            <p className="text-2xl font-bold text-white">{totalMemories}</p>
          )}
          <p className="text-[10px] text-zinc-600 mt-0.5">Qdrant 벡터</p>
        </div>

        {/* 총 작업 로그 */}
        <div className="bg-dark-card border border-dark-border rounded-xl p-3">
          <div className="flex items-center gap-2 mb-1">
            <Clock size={14} className="text-blue-400" />
            <span className="text-[11px] text-zinc-500 uppercase">작업 로그</span>
          </div>
          {statsLoading ? (
            <Loader2 size={14} className="animate-spin text-zinc-500" />
          ) : (
            <p className="text-2xl font-bold text-white">{stats?.total_tasks_logged ?? 0}</p>
          )}
          <p className="text-[10px] text-zinc-600 mt-0.5">단기 Redis</p>
        </div>

        {/* Qdrant 연결 상태 */}
        <div className="bg-dark-card border border-dark-border rounded-xl p-3 col-span-2">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[11px] text-zinc-500 uppercase">에이전트별 기억</span>
          </div>
          {statsLoading ? (
            <Loader2 size={14} className="animate-spin text-zinc-500" />
          ) : (
            <div className="flex flex-wrap gap-2">
              {stats?.collections && Object.entries(stats.collections).map(([code, s]) => {
                const count = s.vectors_count ?? 0;
                const p = getPersona(code);
                return (
                  <div key={code} className="flex items-center gap-1 text-[11px]">
                    <span>{p?.emoji ?? '🤖'}</span>
                    <span className="text-zinc-400">{getDisplayName(code)}</span>
                    <span className={`font-mono font-bold ${count > 0 ? 'text-primary' : 'text-zinc-600'}`}>{count}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* 검색 폼 */}
      <form onSubmit={handleSearch} className="flex-shrink-0">
        <div className="flex gap-3">
          {/* 커스텀 드롭다운 — 스크롤 지원 */}
          <div ref={dropdownRef} className="relative min-w-[200px]">
            <button
              type="button"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              aria-label="에이전트 선택"
              className="w-full bg-dark-card border border-dark-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-primary transition-colors flex items-center justify-between gap-2 text-left"
            >
              <span className={selectedAgent ? 'text-white' : 'text-zinc-500'}>
                {selectedAgent ? agentLabel(selectedAgent) : '에이전트 선택'}
              </span>
              <ChevronDown size={14} className={`text-zinc-500 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>
            {dropdownOpen && (
              <div className="absolute z-50 top-full mt-1 w-full bg-dark-card border border-dark-border rounded-xl shadow-lg max-h-[300px] overflow-y-auto">
                {/* 선택 해제 */}
                <button
                  type="button"
                  onClick={() => { setSelectedAgent(''); setResults([]); setHasSearched(false); setDropdownOpen(false); }}
                  className={`w-full text-left px-4 py-2.5 text-sm hover:bg-zinc-800 transition-colors rounded-t-xl ${!selectedAgent ? 'text-primary' : 'text-zinc-400'}`}
                >
                  에이전트 선택
                </button>
                {/* JINXUS_CORE */}
                <button
                  type="button"
                  onClick={() => { setSelectedAgent('JINXUS_CORE'); setResults([]); setHasSearched(false); setDropdownOpen(false); }}
                  className={`w-full text-left px-4 py-2.5 text-sm hover:bg-zinc-800 transition-colors ${selectedAgent === 'JINXUS_CORE' ? 'text-primary bg-zinc-800/50' : 'text-white'}`}
                >
                  {getPersona('JINXUS_CORE')?.emoji ?? '🧠'} {getDisplayName('JINXUS_CORE')}
                </button>
                {/* 고용된 에이전트 */}
                {agents.map((agent, idx) => (
                  <button
                    type="button"
                    key={agent.name}
                    onClick={() => { setSelectedAgent(agent.name); setResults([]); setHasSearched(false); setDropdownOpen(false); }}
                    className={`w-full text-left px-4 py-2.5 text-sm hover:bg-zinc-800 transition-colors ${idx === agents.length - 1 ? 'rounded-b-xl' : ''} ${selectedAgent === agent.name ? 'text-primary bg-zinc-800/50' : 'text-white'}`}
                  >
                    {agentLabel(agent.name)}
                  </button>
                ))}
              </div>
            )}
          </div>

          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="기억 검색 (예: 코드 리뷰, 에러 수정...)"
            aria-label="메모리 검색어"
            className="flex-1 bg-dark-card border border-dark-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-primary transition-colors"
          />

          <button
            type="submit"
            disabled={!selectedAgent || !query.trim() || isSearching}
            className="px-5 py-2.5 bg-primary hover:bg-primary/90 text-black rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium"
          >
            {isSearching ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
            검색
          </button>
        </div>
      </form>

      {/* 에러 */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400 text-sm flex-shrink-0 flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={doSearch}
            className="ml-3 flex items-center gap-1 px-2.5 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded-lg text-xs font-medium transition-colors"
          >
            <RefreshCw size={12} />
            재시도
          </button>
        </div>
      )}

      {/* 결과 영역 */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {results.length > 0 ? (
          <div className="space-y-3">
            <p className="text-xs text-zinc-500">검색 결과 {results.length}건</p>
            {results.map((result, index) => (
              <div
                key={index}
                className="bg-dark-card border border-dark-border rounded-xl p-4"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{getPersona(result.agent_name)?.emoji ?? '🤖'}</span>
                    <span className="font-semibold text-sm">{getDisplayName(result.agent_name)}</span>
                    <span className="text-[10px] text-zinc-500 bg-zinc-800 px-1.5 py-0.5 rounded">장기기억</span>
                  </div>
                  <div className="flex items-center gap-2">
                    {result.outcome === 'success' || result.success_score >= 0.5 ? (
                      <CheckCircle size={14} className="text-green-400" />
                    ) : (
                      <XCircle size={14} className="text-red-400" />
                    )}
                    <span className="text-xs text-zinc-400 font-mono">
                      {(result.success_score * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                <div className="space-y-2">
                  <div>
                    <span className="text-[10px] text-zinc-500 uppercase tracking-wide">지시</span>
                    <p className="text-sm text-zinc-300 mt-0.5">{result.instruction}</p>
                  </div>
                  {result.summary && (
                    <div>
                      <span className="text-[10px] text-zinc-500 uppercase tracking-wide">요약</span>
                      <p className="text-xs text-zinc-400 mt-0.5">{result.summary}</p>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-4 text-[10px] text-zinc-600 mt-3 pt-2 border-t border-dark-border">
                  <span className="flex items-center gap-1">
                    <Clock size={10} />
                    {result.timestamp
                      ? new Date(result.timestamp).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })
                      : '-'}
                  </span>
                  <span className="font-mono">ID: {result.task_id?.slice(0, 8)}...</span>
                </div>
              </div>
            ))}
          </div>
        ) : isSearching ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={24} className="animate-spin text-zinc-500" />
          </div>
        ) : hasSearched && !isSearching ? (
          /* 검색 완료 후 결과 없음 */
          <div className="flex flex-col items-center justify-center h-40 gap-2 text-zinc-600">
            <Search size={32} />
            <p className="text-sm">
              {`${getDisplayName(selectedAgent) || selectedAgent}의 기억에서 "${query}" 검색 결과가 없습니다`}
            </p>
            {getMemoryCount(selectedAgent) === 0 && (
              <p className="text-xs text-zinc-700">이 에이전트의 장기기억이 아직 없습니다 (작업 후 자동 저장됨)</p>
            )}
          </div>
        ) : selectedAgent && !query ? (
          /* 에이전트 선택됨, 검색어 미입력 */
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-zinc-600">
            <Brain size={36} />
            <div className="text-center">
              <p className="text-sm font-medium text-zinc-500">검색어를 입력하세요</p>
              <p className="text-xs mt-1">
                {getDisplayName(selectedAgent)}의 장기기억 {getMemoryCount(selectedAgent)}건 저장됨
              </p>
              {getMemoryCount(selectedAgent) === 0 && (
                <p className="text-xs text-zinc-700 mt-1">저장된 메모리가 없습니다 — 작업 완료 시 자동 저장됩니다</p>
              )}
            </div>
          </div>
        ) : (
          /* 초기 상태 — 에이전트 미선택 */
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-zinc-600">
            <Brain size={40} />
            <div className="text-center">
              <p className="text-sm font-medium text-zinc-500">에이전트를 선택해주세요</p>
              <p className="text-xs mt-1">Qdrant 벡터 DB에 저장된 에이전트 장기기억을 의미 기반으로 검색합니다</p>
              {totalMemories === 0 && !statsLoading && (
                <p className="text-xs text-amber-500/70 mt-2">⚠ 장기기억 0건 — 에이전트가 작업을 완료하면 자동 저장됩니다</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
