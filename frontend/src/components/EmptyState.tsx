'use client';

import { type ReactNode } from 'react';
import { Inbox, Search, FileText, Database, type LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  /** 아이콘 컴포넌트 (lucide-react) */
  icon?: LucideIcon;
  /** 제목 (굵은 텍스트) */
  title: string;
  /** 설명 (보조 텍스트) */
  description?: string;
  /** 액션 버튼이나 추가 콘텐츠 */
  action?: ReactNode;
  /** 아이콘 색상 클래스 */
  iconColor?: string;
  /** 컴팩트 모드 (패딩 줄임) */
  compact?: boolean;
}

/**
 * 빈 상태 컴포넌트 — 데이터가 없을 때 안내 + 액션 CTA 제공
 *
 * UX 원칙: "빈 상태는 사용자를 안내하는 기회" (helpful empty state with action CTA)
 */
export default function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  iconColor = 'text-zinc-600',
  compact = false,
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center text-center ${compact ? 'py-6 px-4' : 'py-12 px-6'}`}>
      <div className={`${compact ? 'w-10 h-10 mb-3' : 'w-14 h-14 mb-4'} rounded-xl bg-zinc-800/50 flex items-center justify-center`}>
        <Icon className={`${compact ? 'w-5 h-5' : 'w-7 h-7'} ${iconColor}`} />
      </div>
      <p className={`font-medium text-zinc-400 ${compact ? 'text-sm' : 'text-base'}`}>{title}</p>
      {description && (
        <p className={`text-zinc-600 mt-1 max-w-xs ${compact ? 'text-xs' : 'text-sm'}`}>{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

/** 검색 결과 없음 전용 */
export function EmptySearchResult({ query }: { query?: string }) {
  return (
    <EmptyState
      icon={Search}
      title="검색 결과가 없습니다"
      description={query ? `"${query}"에 대한 결과를 찾을 수 없습니다. 다른 키워드로 시도해 보세요.` : '검색어를 입력해 주세요.'}
      compact
    />
  );
}

/** 로그/기록 없음 전용 */
export function EmptyLogs() {
  return (
    <EmptyState
      icon={FileText}
      title="작업 기록이 없습니다"
      description="에이전트가 작업을 수행하면 여기에 로그가 표시됩니다."
      compact
    />
  );
}

/** 메모리 없음 전용 */
export function EmptyMemory() {
  return (
    <EmptyState
      icon={Database}
      title="저장된 메모리가 없습니다"
      description="에이전트가 대화를 통해 학습한 내용이 여기에 축적됩니다."
      compact
    />
  );
}
