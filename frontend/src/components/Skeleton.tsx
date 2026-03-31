'use client';

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div className={`animate-pulse motion-reduce:animate-none bg-zinc-700/50 rounded ${className}`} />
  );
}

export function StatCardSkeleton() {
  return (
    <div className="bg-dark-card border border-dark-border rounded-xl p-4">
      <div className="flex items-center gap-3 mb-3">
        <Skeleton className="w-9 h-9 rounded-lg" />
        <Skeleton className="w-20 h-4" />
      </div>
      <Skeleton className="w-16 h-7" />
    </div>
  );
}

export function AgentCardSkeleton() {
  return (
    <div className="p-4 rounded-lg border border-dark-border bg-dark-card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Skeleton className="w-8 h-8 rounded-md" />
          <div>
            <Skeleton className="w-20 h-4 mb-1" />
            <Skeleton className="w-16 h-3" />
          </div>
        </div>
        <Skeleton className="w-2 h-2 rounded-full" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Skeleton className="h-12 rounded" />
        <Skeleton className="h-12 rounded" />
      </div>
    </div>
  );
}

export function LogRowSkeleton() {
  return (
    <div className="bg-dark-card border border-dark-border rounded-xl p-4">
      <div className="flex items-start gap-4">
        <Skeleton className="w-5 h-5 rounded-full flex-shrink-0 mt-1" />
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <Skeleton className="w-20 h-5 rounded" />
            <Skeleton className="w-24 h-4" />
          </div>
          <Skeleton className="w-full h-4 mb-1" />
          <Skeleton className="w-2/3 h-4" />
        </div>
        <Skeleton className="w-12 h-4 flex-shrink-0" />
      </div>
    </div>
  );
}

export function ListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 p-3 bg-zinc-800/50 rounded-lg">
          <Skeleton className="w-3 h-3 rounded-full" />
          <div className="flex-1">
            <Skeleton className="w-32 h-4 mb-1" />
            <Skeleton className="w-48 h-3" />
          </div>
          <Skeleton className="w-16 h-5 rounded-full" />
        </div>
      ))}
    </div>
  );
}
