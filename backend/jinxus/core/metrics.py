"""JINXUS 메트릭 수집 - 에이전트/도구/캐시 성능 추적

외부 의존성 없이 인메모리 메트릭 수집.
/status/metrics API로 조회 가능.
"""
import time
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricBucket:
    """단일 메트릭 버킷 (카운터 + 타이밍)"""
    count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    last_at: float = 0.0

    def record(self, duration_ms: float, success: bool = True):
        self.count += 1
        if not success:
            self.error_count += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.last_at = time.time()

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.count if self.count > 0 else 0.0

    @property
    def success_rate(self) -> float:
        return (self.count - self.error_count) / self.count if self.count > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "error_count": self.error_count,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "min_duration_ms": round(self.min_duration_ms, 1) if self.min_duration_ms != float('inf') else 0,
            "max_duration_ms": round(self.max_duration_ms, 1),
        }


class JinxusMetrics:
    """JINXUS 메트릭 수집기"""

    def __init__(self):
        # 에이전트별 실행 메트릭
        self.agent_metrics: dict[str, MetricBucket] = defaultdict(MetricBucket)
        # 도구별 실행 메트릭
        self.tool_metrics: dict[str, MetricBucket] = defaultdict(MetricBucket)
        # API 엔드포인트별 메트릭
        self.api_metrics: dict[str, MetricBucket] = defaultdict(MetricBucket)
        # 캐시 히트/미스
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        # 토큰 사용량
        self.token_usage: dict[str, int] = defaultdict(int)  # model -> total_tokens
        # 시작 시간
        self._start_time = time.time()

    def record_agent_execution(self, agent_name: str, duration_ms: float, success: bool = True):
        """에이전트 실행 기록"""
        self.agent_metrics[agent_name].record(duration_ms, success)

    def record_tool_execution(self, tool_name: str, duration_ms: float, success: bool = True):
        """도구 실행 기록"""
        self.tool_metrics[tool_name].record(duration_ms, success)

    def record_api_call(self, endpoint: str, duration_ms: float, success: bool = True):
        """API 호출 기록"""
        self.api_metrics[endpoint].record(duration_ms, success)

    def record_cache_hit(self):
        self.cache_hits += 1

    def record_cache_miss(self):
        self.cache_misses += 1

    def record_tokens(self, model: str, tokens: int):
        self.token_usage[model] += tokens

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    def get_report(self) -> dict:
        """전체 메트릭 리포트"""
        return {
            "uptime_seconds": int(time.time() - self._start_time),
            "agents": {name: bucket.to_dict() for name, bucket in self.agent_metrics.items()},
            "tools": {
                name: bucket.to_dict()
                for name, bucket in sorted(
                    self.tool_metrics.items(),
                    key=lambda x: x[1].count,
                    reverse=True,
                )
            },
            "api": {
                name: bucket.to_dict()
                for name, bucket in sorted(
                    self.api_metrics.items(),
                    key=lambda x: x[1].count,
                    reverse=True,
                )
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate": round(self.cache_hit_rate, 3),
            },
            "tokens": dict(self.token_usage),
        }

    def reset(self):
        """메트릭 초기화"""
        self.agent_metrics.clear()
        self.tool_metrics.clear()
        self.api_metrics.clear()
        self.cache_hits = 0
        self.cache_misses = 0
        self.token_usage.clear()


# 싱글톤
_metrics: Optional[JinxusMetrics] = None


def get_metrics() -> JinxusMetrics:
    """메트릭 싱글톤 반환"""
    global _metrics
    if _metrics is None:
        _metrics = JinxusMetrics()
    return _metrics
