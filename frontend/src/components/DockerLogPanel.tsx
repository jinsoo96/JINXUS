'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { dockerApi, type DockerContainer } from '@/lib/api';
import {
  ChevronDown, Pause, Play, Trash2,
} from 'lucide-react';

interface LogEntry {
  line: string;
  stream: 'stdout' | 'stderr';
  timestamp: string;
}

const MAX_LOG_LINES = 500;

export default function DockerLogPanel({ onClose }: { onClose?: () => void }) {
  const [containers, setContainers] = useState<DockerContainer[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isFollowing, setIsFollowing] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState('');

  const logEndRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isNearBottomRef = useRef(true);

  // 컨테이너 목록 로드
  useEffect(() => {
    dockerApi.getContainers().then((res) => {
      setContainers(res.containers);
      const backend = res.containers.find((c) => c.name.includes('backend'));
      const first = backend || res.containers[0];
      if (first) setSelectedId(first.id);
    }).catch((e) => setError(e.message));
  }, []);

  // 로그 스트리밍 — 컨테이너 선택 시 자동 시작
  useEffect(() => {
    if (!selectedId) return;

    abortRef.current?.abort();
    setLogs([]);
    setError('');
    setIsConnected(true);

    const controller = dockerApi.streamLogs(
      selectedId,
      200,
      (line, stream, timestamp) => {
        setLogs((prev) => {
          const next = [...prev, { line, stream, timestamp }];
          return next.length > MAX_LOG_LINES ? next.slice(-MAX_LOG_LINES) : next;
        });
      },
      (err) => {
        setError(err.message);
        setIsConnected(false);
      },
    );
    abortRef.current = controller;

    return () => { controller.abort(); };
  }, [selectedId]);

  // 자동 스크롤
  useEffect(() => {
    if (isFollowing && isNearBottomRef.current) {
      logEndRef.current?.scrollIntoView({ behavior: 'auto' });
    }
  }, [logs, isFollowing]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
  }, []);

  return (
    <div className="w-full bg-dark-card flex flex-col h-full">
      {/* 컨테이너 선택 + 컨트롤 (인라인) */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-dark-border">
        <div className="relative flex-1 max-w-[220px]">
          <select
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 appearance-none pr-6 cursor-pointer focus:outline-none focus:border-primary"
          >
            {containers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.state})
              </option>
            ))}
          </select>
          <ChevronDown size={10} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 pointer-events-none" />
        </div>
        <span className="text-[10px] text-zinc-500">{logs.length}줄</span>
        {isConnected && <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />}
        <button
          onClick={() => setIsFollowing(!isFollowing)}
          className={`p-1 rounded transition-colors ${isFollowing ? 'text-green-400 hover:bg-green-400/10' : 'text-zinc-500 hover:bg-zinc-700'}`}
          title={isFollowing ? '자동 스크롤 끄기' : '자동 스크롤 켜기'}
        >
          {isFollowing ? <Play size={12} /> : <Pause size={12} />}
        </button>
        <button
          onClick={() => setLogs([])}
          className="p-1 rounded text-zinc-500 hover:text-zinc-300 hover:bg-zinc-700 transition-colors"
          title="로그 지우기"
        >
          <Trash2 size={12} />
        </button>
      </div>

      {/* 로그 출력 — 실시간 스트리밍 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto overflow-x-hidden bg-black/80 font-mono text-[11px] leading-[1.6] px-3 py-2"
      >
        {error && (
          <div className="text-red-400 py-1">오류: {error}</div>
        )}
        {logs.length === 0 && !error && (
          <div className="text-zinc-600 py-2">로그 대기 중...</div>
        )}
        {logs.map((entry, i) => (
          <div key={i} className="hover:bg-zinc-800/50">
            {entry.timestamp && (
              <span className="text-zinc-600 mr-2 text-[10px] select-none">
                {entry.timestamp.split('T')[1]?.slice(0, 12) || ''}
              </span>
            )}
            <span className={
              /\bERROR\b|Traceback|Exception|CRITICAL/i.test(entry.line) ? 'text-red-400' :
              /\bWARN(ING)?\b/i.test(entry.line) ? 'text-amber-400' :
              /\bDEBUG\b/i.test(entry.line) ? 'text-zinc-500' :
              'text-green-300/80'
            }>
              {entry.line}
            </span>
          </div>
        ))}
        {isConnected && <span className="text-green-400 animate-pulse">▌</span>}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}
