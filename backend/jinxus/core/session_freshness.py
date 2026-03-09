"""Session Freshness Policy (B-3) — 세션 신선도 평가

세션의 수명, 유휴 시간, 반복 횟수, 메시지 수를 기반으로
4단계 상태(FRESH/STALE_WARN/STALE_COMPACT/STALE_RESET)를 평가한다.

매 그래프 실행 전 evaluate()를 호출하여:
  - STALE_RESET → 세션 리셋 (Redis 단기메모리 클리어)
  - STALE_COMPACT → context_guard 컴팩션 트리거
  - STALE_WARN → 로그 경고
  - FRESH → 정상 진행
"""
import logging
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class FreshnessStatus(Enum):
    """세션 신선도 상태"""
    FRESH = "fresh"                  # 정상
    STALE_WARN = "stale_warn"        # 경고 (수명/유휴 시간 주의)
    STALE_COMPACT = "stale_compact"  # 메시지 과대 → 컴팩션 권장
    STALE_RESET = "stale_reset"      # 세션 종료 및 재생성 필요


@dataclass(frozen=True)
class FreshnessConfig:
    """신선도 판단 임계값"""
    max_session_age_seconds: float = 14400.0   # 4시간 — 세션 최대 수명
    max_idle_seconds: float = 3600.0           # 1시간 — 최대 유휴 허용
    max_iterations: int = 200                  # 최대 반복(그래프 실행) 횟수
    compact_after_messages: int = 80           # 이 수 이상이면 컴팩션 권장
    warn_session_age_seconds: float = 7200.0   # 2시간 — 경고 수명
    warn_idle_seconds: float = 1800.0          # 30분 — 경고 유휴


@dataclass(frozen=True)
class FreshnessResult:
    """신선도 평가 결과"""
    status: FreshnessStatus
    reason: str
    should_compact: bool
    should_reset: bool


class SessionFreshness:
    """세션 신선도 평가기

    evaluate()로 세션 메타데이터를 받아 4단계 상태를 반환한다.
    """

    def __init__(self, config: FreshnessConfig | None = None):
        self._config = config or FreshnessConfig()

    @property
    def config(self) -> FreshnessConfig:
        return self._config

    def evaluate(
        self,
        created_at: datetime | None,
        last_active: datetime | None,
        iteration_count: int,
        message_count: int,
        now: datetime | None = None,
    ) -> FreshnessResult:
        """세션 신선도 4단계 평가

        Args:
            created_at: 세션 생성 시각 (None이면 FRESH 반환)
            last_active: 마지막 활성 시각 (None이면 created_at 사용)
            iteration_count: 그래프 실행 횟수
            message_count: Redis 저장 메시지 수
            now: 현재 시각 (테스트용, 기본 utcnow)

        Returns:
            FreshnessResult
        """
        cfg = self._config

        # 메타데이터가 없으면 새 세션으로 간주
        if created_at is None:
            return FreshnessResult(
                status=FreshnessStatus.FRESH,
                reason="새 세션",
                should_compact=False,
                should_reset=False,
            )

        now = now or datetime.now()
        age = (now - created_at).total_seconds()
        idle = (now - (last_active or created_at)).total_seconds()

        # 1) RESET 조건 (가장 위험 — 먼저 판단)
        if age > cfg.max_session_age_seconds:
            return FreshnessResult(
                status=FreshnessStatus.STALE_RESET,
                reason=f"세션 수명 초과 ({age:.0f}s > {cfg.max_session_age_seconds:.0f}s)",
                should_compact=False,
                should_reset=True,
            )
        if idle > cfg.max_idle_seconds:
            return FreshnessResult(
                status=FreshnessStatus.STALE_RESET,
                reason=f"장시간 유휴 ({idle:.0f}s > {cfg.max_idle_seconds:.0f}s)",
                should_compact=False,
                should_reset=True,
            )
        if iteration_count >= cfg.max_iterations:
            return FreshnessResult(
                status=FreshnessStatus.STALE_RESET,
                reason=f"반복 횟수 초과 ({iteration_count} >= {cfg.max_iterations})",
                should_compact=False,
                should_reset=True,
            )

        # 2) COMPACT 조건
        if message_count >= cfg.compact_after_messages:
            return FreshnessResult(
                status=FreshnessStatus.STALE_COMPACT,
                reason=f"메시지 히스토리 과대 ({message_count} >= {cfg.compact_after_messages})",
                should_compact=True,
                should_reset=False,
            )

        # 3) WARN 조건
        if age > cfg.warn_session_age_seconds:
            return FreshnessResult(
                status=FreshnessStatus.STALE_WARN,
                reason=f"세션 수명 주의 ({age:.0f}s > {cfg.warn_session_age_seconds:.0f}s)",
                should_compact=False,
                should_reset=False,
            )
        if idle > cfg.warn_idle_seconds:
            return FreshnessResult(
                status=FreshnessStatus.STALE_WARN,
                reason=f"유휴 시간 주의 ({idle:.0f}s > {cfg.warn_idle_seconds:.0f}s)",
                should_compact=False,
                should_reset=False,
            )

        # 4) FRESH
        return FreshnessResult(
            status=FreshnessStatus.FRESH,
            reason="정상",
            should_compact=False,
            should_reset=False,
        )
