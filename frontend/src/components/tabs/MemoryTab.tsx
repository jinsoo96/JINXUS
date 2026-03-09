'use client';

import { useState } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { memoryApi } from '@/lib/api';
import { Search, Brain, Clock, CheckCircle, XCircle } from 'lucide-react';
import type { MemorySearchResult } from '@/types';

export default function MemoryTab() {
  const { agents } = useAppStore();
  const [selectedAgent, setSelectedAgent] = useState<string>('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<MemorySearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAgent || !query.trim()) return;

    setIsSearching(true);
    setError(null);

    try {
      const response = await memoryApi.search(selectedAgent, query.trim());
      setResults(response.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : '검색 중 오류가 발생했습니다.');
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">장기 메모리</h2>
      <p className="text-zinc-400 mb-8">
        에이전트별 장기 메모리를 검색합니다. 과거 작업 기록과 학습 내용을 확인할 수 있습니다.
      </p>

      {/* 검색 폼 */}
      <form onSubmit={handleSearch} className="mb-8">
        <div className="flex gap-4">
          {/* 에이전트 선택 */}
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            aria-label="에이전트 선택"
            className="bg-dark-card border border-dark-border rounded-xl px-4 py-3 focus:outline-none focus:border-primary transition-colors"
          >
            <option value="">에이전트 선택</option>
            {agents.map((agent) => (
              <option key={agent.name} value={agent.name}>
                {agent.name}
              </option>
            ))}
          </select>

          {/* 검색어 입력 */}
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="검색어를 입력하세요..."
            aria-label="메모리 검색어"
            className="flex-1 bg-dark-card border border-dark-border rounded-xl px-4 py-3 focus:outline-none focus:border-primary transition-colors"
          />

          {/* 검색 버튼 */}
          <button
            type="submit"
            disabled={!selectedAgent || !query.trim() || isSearching}
            className="px-6 py-3 bg-primary hover:bg-primary-hover rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Search size={20} />
            <span>검색</span>
          </button>
        </div>
      </form>

      {/* 에러 메시지 */}
      {error && (
        <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400">
          {error}
        </div>
      )}

      {/* 검색 결과 */}
      {results.length > 0 ? (
        <div className="space-y-4">
          <h3 className="text-lg font-semibold">
            검색 결과 ({results.length}건)
          </h3>
          {results.map((result, index) => (
            <div
              key={index}
              className="bg-dark-card border border-dark-border rounded-xl p-6"
            >
              {/* 헤더 */}
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Brain size={20} className="text-primary" />
                  <span className="font-semibold">{result.agent_name}</span>
                </div>
                <div className="flex items-center gap-2">
                  {result.outcome === 'success' ? (
                    <CheckCircle size={16} className="text-green-400" />
                  ) : (
                    <XCircle size={16} className="text-red-400" />
                  )}
                  <span className="text-sm text-zinc-400">
                    {(result.success_score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* 지시 내용 */}
              <div className="mb-3">
                <span className="text-xs text-zinc-500 uppercase">지시</span>
                <p className="text-zinc-300 mt-1">{result.instruction}</p>
              </div>

              {/* 요약 */}
              <div className="mb-3">
                <span className="text-xs text-zinc-500 uppercase">요약</span>
                <p className="text-zinc-400 mt-1 text-sm">{result.summary}</p>
              </div>

              {/* 메타 정보 */}
              <div className="flex items-center gap-4 text-xs text-zinc-500">
                <span className="flex items-center gap-1">
                  <Clock size={12} />
                  {result.timestamp ? new Date(result.timestamp).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false }) : '-'}
                </span>
                <span>Task ID: {result.task_id?.slice(0, 8)}...</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        !isSearching && query && (
          <div className="text-center py-12">
            <Brain size={48} className="mx-auto text-zinc-600 mb-4" />
            <p className="text-zinc-500">검색 결과가 없습니다.</p>
          </div>
        )
      )}

      {/* 초기 상태 */}
      {!query && results.length === 0 && (
        <div className="text-center py-12">
          <Brain size={64} className="mx-auto text-zinc-600 mb-4" />
          <h3 className="text-lg font-semibold text-zinc-400 mb-2">
            메모리 검색
          </h3>
          <p className="text-zinc-500">
            에이전트를 선택하고 검색어를 입력하세요.
          </p>
        </div>
      )}
    </div>
  );
}
