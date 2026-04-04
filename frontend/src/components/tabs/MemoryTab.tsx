'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { memoryApi } from '@/lib/api';
import { getDisplayName, getPersona } from '@/lib/personas';
import {
  Search, Brain, Clock, CheckCircle, XCircle, RefreshCw, Loader2, Database,
  ChevronDown, ChevronRight, FolderOpen, Folder, Tag, Star, FileText,
  Lightbulb, Users, Briefcase, Calendar, Filter, X, Hash,
} from 'lucide-react';
import type { MemorySearchResult } from '@/types';

// ---------- 타입 ----------
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

// 메모리 카테고리 (JINXUS 메모리 유형 매핑)
type MemoryCategory = 'all' | 'daily' | 'topics' | 'entities' | 'projects' | 'insights';

const CATEGORIES: { id: MemoryCategory; label: string; icon: typeof Calendar; color: string }[] = [
  { id: 'all', label: '전체', icon: Database, color: 'text-zinc-400' },
  { id: 'daily', label: '일별 기록', icon: Calendar, color: 'text-blue-400' },
  { id: 'topics', label: '주제별', icon: FileText, color: 'text-green-400' },
  { id: 'entities', label: '개체', icon: Users, color: 'text-purple-400' },
  { id: 'projects', label: '프로젝트', icon: Briefcase, color: 'text-amber-400' },
  { id: 'insights', label: '인사이트', icon: Lightbulb, color: 'text-pink-400' },
];

// 중요도 레벨 매핑
function getImportanceDot(score: number): { color: string; label: string } {
  if (score >= 0.9) return { color: 'bg-red-500', label: 'critical' };
  if (score >= 0.7) return { color: 'bg-orange-400', label: 'high' };
  if (score >= 0.4) return { color: 'bg-blue-400', label: 'medium' };
  return { color: 'bg-zinc-500', label: 'low' };
}

// 카테고리 추론 (instruction/summary 기반)
function inferCategory(result: MemorySearchResult): MemoryCategory {
  const text = `${result.instruction} ${result.summary}`.toLowerCase();
  if (/인사이트|분석|결론|패턴|학습/.test(text)) return 'insights';
  if (/프로젝트|빌드|배포|구현/.test(text)) return 'projects';
  if (/사용자|에이전트|팀|이름/.test(text)) return 'entities';
  if (/일일|보고|브리핑|정기/.test(text)) return 'daily';
  return 'topics';
}

// 태그 추출 (키워드 기반)
function extractTags(result: MemorySearchResult): string[] {
  const tags: string[] = [];
  const text = `${result.instruction} ${result.summary}`.toLowerCase();
  if (/코드|개발|프로그래밍|함수|api/.test(text)) tags.push('개발');
  if (/리뷰|검토|피드백/.test(text)) tags.push('리뷰');
  if (/에러|오류|버그|수정|fix/.test(text)) tags.push('버그');
  if (/검색|조사|리서치/.test(text)) tags.push('리서치');
  if (/문서|작성|글/.test(text)) tags.push('문서');
  if (/배포|docker|서버/.test(text)) tags.push('인프라');
  if (/디자인|ui|프론트/.test(text)) tags.push('UI');
  if (/테스트|검증/.test(text)) tags.push('테스트');
  if (result.outcome === 'success' || result.success_score >= 0.8) tags.push('성공');
  if (result.success_score < 0.3) tags.push('실패');
  return tags.length > 0 ? tags : ['일반'];
}

// 간이 마크다운 렌더러
function renderMarkdown(text: string): React.ReactNode {
  if (!text) return null;
  const lines = text.split('\n');
  return lines.map((line, i) => {
    // 볼드
    let processed: React.ReactNode = line.replace(/\*\*(.*?)\*\*/g, '|||BOLD_START|||$1|||BOLD_END|||');
    if (typeof processed === 'string') {
      const parts = processed.split(/(|||BOLD_START|||.*?|||BOLD_END|||)/);
      processed = parts.map((part, j) => {
        if (part.startsWith('|||BOLD_START|||') && part.endsWith('|||BOLD_END|||')) {
          const content = part.replace('|||BOLD_START|||', '').replace('|||BOLD_END|||', '');
          return <strong key={j} className="text-white font-semibold">{content}</strong>;
        }
        // 인라인 코드
        const codeParts = part.split(/`([^`]+)`/);
        return codeParts.map((cp, k) =>
          k % 2 === 1
            ? <code key={`${j}-${k}`} className="px-1 py-0.5 bg-zinc-700 rounded text-xs text-amber-300 font-mono">{cp}</code>
            : <span key={`${j}-${k}`}>{cp}</span>
        );
      });
    }
    // 리스트 아이템
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      return <li key={i} className="ml-4 list-disc text-zinc-300">{processed}</li>;
    }
    // 헤딩
    if (line.startsWith('### ')) return <h4 key={i} className="text-sm font-bold text-white mt-2">{line.slice(4)}</h4>;
    if (line.startsWith('## ')) return <h3 key={i} className="text-base font-bold text-white mt-2">{line.slice(3)}</h3>;
    if (line.startsWith('# ')) return <h2 key={i} className="text-lg font-bold text-white mt-2">{line.slice(2)}</h2>;
    return <p key={i} className={line.trim() === '' ? 'h-2' : ''}>{processed}</p>;
  });
}

// ---------- 태그 필 컴포넌트 ----------
function TagPill({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all ${
        active
          ? 'bg-primary/20 text-primary border border-primary/40'
          : 'bg-zinc-800 text-zinc-400 border border-zinc-700 hover:border-zinc-500 hover:text-zinc-300'
      }`}
    >
      <Hash size={10} />
      {label}
    </button>
  );
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

  // 파일 트리 카테고리
  const [activeCategory, setActiveCategory] = useState<MemoryCategory>('all');
  const [expandedCategories, setExpandedCategories] = useState<Set<MemoryCategory>>(new Set<MemoryCategory>(['all']));
  // 태그 필터
  const [activeTag, setActiveTag] = useState<string | null>(null);
  // 검색 결과 확장
  const [expandedResult, setExpandedResult] = useState<number | null>(null);

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
      const response = await memoryApi.search(selectedAgent, query.trim(), 20);
      setResults(response.results);
      setHasSearched(true);
      setExpandedResult(null);
      setActiveTag(null);
      setActiveCategory('all');
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

  // 에이전트 코드명 -> 표시이름 + 이모지
  const agentLabel = (code: string) => {
    const p = getPersona(code);
    return p ? `${p.emoji} ${getDisplayName(code)}` : getDisplayName(code);
  };

  // 컬렉션 통계에서 에이전트 코드 -> 메모리 수
  const getMemoryCount = (agentCode: string): number => {
    if (!stats?.collections) return 0;
    return stats.collections[agentCode]?.vectors_count ?? 0;
  };

  const totalMemories = Object.values(stats?.collections ?? {}).reduce(
    (sum, s) => sum + (s.vectors_count ?? 0), 0
  );

  // 결과를 카테고리별로 그룹핑
  const categorizedResults = useMemo(() => {
    const map: Record<MemoryCategory, MemorySearchResult[]> = {
      all: results,
      daily: [],
      topics: [],
      entities: [],
      projects: [],
      insights: [],
    };
    results.forEach(r => {
      const cat = inferCategory(r);
      map[cat].push(r);
    });
    return map;
  }, [results]);

  // 모든 태그 수집
  const allTags = useMemo(() => {
    const tagSet = new Map<string, number>();
    results.forEach(r => {
      extractTags(r).forEach(t => tagSet.set(t, (tagSet.get(t) ?? 0) + 1));
    });
    return Array.from(tagSet.entries()).sort((a, b) => b[1] - a[1]);
  }, [results]);

  // 필터링된 결과
  const filteredResults = useMemo(() => {
    let filtered = activeCategory === 'all' ? results : categorizedResults[activeCategory];
    if (activeTag) {
      filtered = filtered.filter(r => extractTags(r).includes(activeTag));
    }
    return filtered;
  }, [results, activeCategory, activeTag, categorizedResults]);

  const toggleCategory = (cat: MemoryCategory) => {
    const next = new Set(expandedCategories);
    if (next.has(cat)) next.delete(cat);
    else next.add(cat);
    setExpandedCategories(next);
  };

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
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3 flex-shrink-0">
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

        {/* 에이전트별 기억 */}
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
                  <button
                    key={code}
                    onClick={() => {
                      setSelectedAgent(code);
                      setResults([]);
                      setHasSearched(false);
                    }}
                    className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded-lg transition-colors ${
                      selectedAgent === code ? 'bg-primary/15 ring-1 ring-primary/40' : 'hover:bg-zinc-800'
                    }`}
                  >
                    <span>{p?.emoji ?? '🤖'}</span>
                    <span className="text-zinc-400">{getDisplayName(code)}</span>
                    <span className={`font-mono font-bold ${count > 0 ? 'text-primary' : 'text-zinc-600'}`}>{count}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* 검색 폼 */}
      <form onSubmit={handleSearch} className="flex-shrink-0">
        <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
          {/* 커스텀 드롭다운 */}
          <div ref={dropdownRef} className="relative w-full sm:min-w-[200px] sm:w-auto">
            <button
              type="button"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              aria-label="에이전트 선택"
              className="w-full bg-dark-card border border-dark-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-primary transition-colors flex items-center justify-between gap-2 text-left min-h-[44px]"
            >
              <span className={selectedAgent ? 'text-white' : 'text-zinc-500'}>
                {selectedAgent ? agentLabel(selectedAgent) : '에이전트 선택'}
              </span>
              <ChevronDown size={14} className={`text-zinc-500 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>
            {dropdownOpen && (
              <div className="absolute z-50 top-full mt-1 w-full bg-dark-card border border-dark-border rounded-xl shadow-lg max-h-[300px] overflow-y-auto">
                <button
                  type="button"
                  onClick={() => { setSelectedAgent(''); setResults([]); setHasSearched(false); setDropdownOpen(false); }}
                  className={`w-full text-left px-4 py-3 sm:py-2.5 text-sm hover:bg-zinc-800 active:bg-zinc-700 transition-colors rounded-t-xl min-h-[44px] ${!selectedAgent ? 'text-primary' : 'text-zinc-400'}`}
                >
                  에이전트 선택
                </button>
                <button
                  type="button"
                  onClick={() => { setSelectedAgent('JINXUS_CORE'); setResults([]); setHasSearched(false); setDropdownOpen(false); }}
                  className={`w-full text-left px-4 py-3 sm:py-2.5 text-sm hover:bg-zinc-800 active:bg-zinc-700 transition-colors min-h-[44px] ${selectedAgent === 'JINXUS_CORE' ? 'text-primary bg-zinc-800/50' : 'text-white'}`}
                >
                  {getPersona('JINXUS_CORE')?.emoji ?? '🧠'} {getDisplayName('JINXUS_CORE')}
                </button>
                {agents.map((agent, idx) => (
                  <button
                    type="button"
                    key={agent.name}
                    onClick={() => { setSelectedAgent(agent.name); setResults([]); setHasSearched(false); setDropdownOpen(false); }}
                    className={`w-full text-left px-4 py-3 sm:py-2.5 text-sm hover:bg-zinc-800 active:bg-zinc-700 transition-colors min-h-[44px] ${idx === agents.length - 1 ? 'rounded-b-xl' : ''} ${selectedAgent === agent.name ? 'text-primary bg-zinc-800/50' : 'text-white'}`}
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
            className="flex-1 bg-dark-card border border-dark-border rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-primary transition-colors min-h-[44px]"
          />

          <button
            type="submit"
            disabled={!selectedAgent || !query.trim() || isSearching}
            className="px-5 py-2.5 bg-primary hover:bg-primary/90 active:bg-primary/80 text-black rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium min-h-[44px]"
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
      <div className="flex-1 overflow-hidden min-h-0">
        {results.length > 0 ? (
          <div className="flex flex-col md:flex-row gap-3 md:gap-4 h-full">
            {/* 파일 트리 카테고리 — 모바일: 가로 스크롤, 데스크톱: 세로 사이드바 */}
            <div className="md:w-56 flex-shrink-0 bg-dark-card border border-dark-border rounded-xl p-3 overflow-y-auto max-h-[200px] md:max-h-none">
              <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-3 px-1">탐색기</div>
              <div className="space-y-0.5">
                {CATEGORIES.map(cat => {
                  const catResults = cat.id === 'all' ? results : categorizedResults[cat.id];
                  const count = catResults.length;
                  if (cat.id !== 'all' && count === 0) return null;
                  const isActive = activeCategory === cat.id;
                  const isExpanded = expandedCategories.has(cat.id);

                  return (
                    <div key={cat.id}>
                      <button
                        onClick={() => {
                          setActiveCategory(cat.id);
                          if (cat.id !== 'all') toggleCategory(cat.id);
                          setActiveTag(null);
                        }}
                        className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-left text-sm transition-colors ${
                          isActive ? 'bg-zinc-700/60 text-white' : 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-300'
                        }`}
                      >
                        {cat.id === 'all' ? (
                          <Database size={14} className={cat.color} />
                        ) : isExpanded ? (
                          <ChevronDown size={14} className={cat.color} />
                        ) : (
                          <ChevronRight size={14} className={cat.color} />
                        )}
                        {cat.id !== 'all' && (
                          isExpanded
                            ? <FolderOpen size={14} className={cat.color} />
                            : <Folder size={14} className={cat.color} />
                        )}
                        <span className="flex-1 truncate">{cat.label}</span>
                        <span className="text-[10px] text-zinc-500 font-mono">{count}</span>
                      </button>

                      {/* 하위 노드: 카테고리가 펼쳐졌을 때 결과 항목 표시 */}
                      {cat.id !== 'all' && isExpanded && catResults.length > 0 && (
                        <div className="ml-4 pl-2 border-l border-zinc-700/50 mt-0.5 space-y-0.5">
                          {catResults.slice(0, 15).map((result, i) => {
                            const imp = getImportanceDot(result.success_score);
                            const globalIdx = results.indexOf(result);
                            const isSelected = expandedResult === globalIdx;
                            return (
                              <button
                                key={i}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setExpandedResult(isSelected ? null : globalIdx);
                                  setActiveCategory(cat.id);
                                }}
                                className={`w-full flex items-center gap-1.5 px-2 py-1 rounded text-left text-[11px] transition-colors ${
                                  isSelected ? 'bg-primary/10 text-primary' : 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300'
                                }`}
                              >
                                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${imp.color}`} />
                                <FileText size={11} className="flex-shrink-0 text-zinc-600" />
                                <span className="flex-1 truncate">{result.instruction.slice(0, 30)}</span>
                              </button>
                            );
                          })}
                          {catResults.length > 15 && (
                            <span className="text-[10px] text-zinc-600 pl-2">+{catResults.length - 15}건 더</span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* 태그 필터 */}
              {allTags.length > 0 && (
                <div className="mt-4 pt-3 border-t border-dark-border">
                  <div className="flex items-center gap-1 text-[10px] text-zinc-500 uppercase tracking-wider mb-2 px-1">
                    <Filter size={10} />
                    태그 필터
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {allTags.slice(0, 10).map(([tag, count]) => (
                      <TagPill
                        key={tag}
                        label={`${tag} ${count}`}
                        active={activeTag === tag}
                        onClick={() => setActiveTag(activeTag === tag ? null : tag)}
                      />
                    ))}
                  </div>
                  {activeTag && (
                    <button
                      onClick={() => setActiveTag(null)}
                      className="mt-2 flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
                    >
                      <X size={10} />
                      필터 초기화
                    </button>
                  )}
                </div>
              )}
            </div>

            {/* 오른쪽: 결과 목록 */}
            <div className="flex-1 overflow-y-auto space-y-3 min-h-0">
              <div className="flex items-center justify-between">
                <p className="text-xs text-zinc-500">
                  {activeTag || activeCategory !== 'all'
                    ? `필터된 결과 ${filteredResults.length}건 / 전체 ${results.length}건`
                    : `검색 결과 ${results.length}건`}
                </p>
                {(activeTag || activeCategory !== 'all') && (
                  <button
                    onClick={() => { setActiveCategory('all'); setActiveTag(null); }}
                    className="text-[11px] text-zinc-500 hover:text-primary transition-colors flex items-center gap-1"
                  >
                    <X size={10} />
                    전체 보기
                  </button>
                )}
              </div>

              {filteredResults.map((result, index) => {
                const importance = getImportanceDot(result.success_score);
                const tags = extractTags(result);
                const category = inferCategory(result);
                const catInfo = CATEGORIES.find(c => c.id === category);
                const isExpanded = expandedResult === index;

                return (
                  <div
                    key={index}
                    className={`bg-dark-card border rounded-xl transition-all cursor-pointer ${
                      isExpanded ? 'border-primary/30 ring-1 ring-primary/10' : 'border-dark-border hover:border-zinc-600'
                    }`}
                    onClick={() => setExpandedResult(isExpanded ? null : index)}
                  >
                    <div className="p-4">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2">
                          {/* 중요도 도트 */}
                          <div className="relative group">
                            <span className={`w-2.5 h-2.5 rounded-full ${importance.color} inline-block`} />
                            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-0.5 bg-zinc-700 text-[10px] text-zinc-300 rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap">
                              {importance.label === 'critical' ? '매우 높음' :
                               importance.label === 'high' ? '높음' :
                               importance.label === 'medium' ? '보통' : '낮음'}
                            </div>
                          </div>
                          <span className="text-lg">{getPersona(result.agent_name)?.emoji ?? '🤖'}</span>
                          <span className="font-semibold text-sm">{getDisplayName(result.agent_name)}</span>
                          {/* 카테고리 배지 */}
                          {catInfo && (
                            <span className={`flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 ${catInfo.color}`}>
                              <catInfo.icon size={9} />
                              {catInfo.label}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {/* 점수 표시 */}
                          <div className="flex items-center gap-1">
                            {result.outcome === 'success' || result.success_score >= 0.5 ? (
                              <CheckCircle size={13} className="text-green-400" />
                            ) : (
                              <XCircle size={13} className="text-red-400" />
                            )}
                            <span className={`text-xs font-mono font-bold ${
                              result.success_score >= 0.8 ? 'text-green-400' :
                              result.success_score >= 0.5 ? 'text-amber-400' : 'text-red-400'
                            }`}>
                              {(result.success_score * 100).toFixed(0)}%
                            </span>
                          </div>
                          <Star size={12} className={result.success_score >= 0.7 ? 'text-amber-400' : 'text-zinc-600'} />
                        </div>
                      </div>

                      {/* 지시 내용 */}
                      <div className="mb-2">
                        <p className={`text-sm text-zinc-300 ${isExpanded ? '' : 'line-clamp-2'}`}>{result.instruction}</p>
                      </div>

                      {/* 태그 필 */}
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {tags.map(tag => (
                          <span
                            key={tag}
                            onClick={(e) => { e.stopPropagation(); setActiveTag(activeTag === tag ? null : tag); }}
                            className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full text-[10px] cursor-pointer transition-colors ${
                              activeTag === tag
                                ? 'bg-primary/20 text-primary border border-primary/30'
                                : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300 border border-zinc-700'
                            }`}
                          >
                            <Tag size={8} />
                            {tag}
                          </span>
                        ))}
                      </div>

                      {/* 확장된 내용: 요약 (마크다운) */}
                      {isExpanded && result.summary && (
                        <div className="mt-3 pt-3 border-t border-dark-border">
                          <span className="text-[10px] text-zinc-500 uppercase tracking-wide">요약</span>
                          <div className="mt-1 text-xs text-zinc-400 leading-relaxed space-y-1">
                            {renderMarkdown(result.summary)}
                          </div>
                        </div>
                      )}

                      {/* 메타 정보 */}
                      <div className="flex items-center gap-4 text-[10px] text-zinc-600 mt-2 pt-2 border-t border-dark-border">
                        <span className="flex items-center gap-1">
                          <Clock size={10} />
                          {result.timestamp
                            ? new Date(result.timestamp).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false })
                            : '-'}
                        </span>
                        <span className="font-mono">ID: {result.task_id?.slice(0, 8)}...</span>
                      </div>
                    </div>
                  </div>
                );
              })}

              {filteredResults.length === 0 && (
                <div className="flex flex-col items-center justify-center h-32 gap-2 text-zinc-600">
                  <Filter size={24} />
                  <p className="text-sm">현재 필터 조건에 맞는 결과가 없습니다</p>
                </div>
              )}
            </div>
          </div>
        ) : isSearching ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={24} className="animate-spin text-zinc-500" />
          </div>
        ) : hasSearched && !isSearching ? (
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
          <div className="flex flex-col items-center justify-center h-40 gap-3 text-zinc-600">
            <Brain size={40} />
            <div className="text-center">
              <p className="text-sm font-medium text-zinc-500">에이전트를 선택해주세요</p>
              <p className="text-xs mt-1">Qdrant 벡터 DB에 저장된 에이전트 장기기억을 의미 기반으로 검색합니다</p>
              {totalMemories === 0 && !statsLoading && (
                <p className="text-xs text-amber-500/70 mt-2">장기기억 0건 — 에이전트가 작업을 완료하면 자동 저장됩니다</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
