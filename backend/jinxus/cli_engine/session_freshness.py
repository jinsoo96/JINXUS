"""Session Freshness — 세션 수명 관리 시스템

5단계 상태 전이로 유휴 세션의 자동 정리/부활/컴팩션을 관리한다.

상태 전이:
    FRESH → STALE_WARN → STALE_IDLE → STALE_COMPACT → STALE_RESET

각 단계별로 타이머 기반 전이가 이루어지며,
STALE_COMPACT에서는 ContextWindowGuard와 연동해 컨텍스트 컴팩션을 트리거한다.

사용:
    tracker = FreshnessTracker()
    tracker.touch(session_id)  # 활동 시 갱신
    state = tracker.check(session_id)  # 현재 상태 조회
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Freshness State
# ============================================================================

class FreshnessState(str, Enum):
    """세션 프레시니스 5단계 상태"""
    FRESH = "fresh"                  # 활성 상태 (최근 활동 있음)
    STALE_WARN = "stale_warn"        # 경고 (유휴 진입 직전)
    STALE_IDLE = "stale_idle"        # 유휴 상태
    STALE_COMPACT = "stale_compact"  # 컴팩션 필요
    STALE_RESET = "stale_reset"      # 리셋 대상 (세션 종료 예정)


# 상태 전이 순서
_STATE_ORDER: List[FreshnessState] = [
    FreshnessState.FRESH,
    FreshnessState.STALE_WARN,
    FreshnessState.STALE_IDLE,
    FreshnessState.STALE_COMPACT,
    FreshnessState.STALE_RESET,
]


@dataclass
class FreshnessThresholds:
    """상태 전이 타이머 임계값 (초 단위)

    마지막 활동 이후 경과 시간 기준:
    - stale_warn: FRESH → STALE_WARN
    - stale_idle: FRESH → STALE_IDLE
    - stale_compact: FRESH → STALE_COMPACT
    - stale_reset: FRESH → STALE_RESET
    """
    stale_warn: float = 300.0        # 5분 — idle 경고
    stale_idle: float = 600.0        # 10분 — IDLE 전환 (죽이지 않음, 자동 부활 대상)
    stale_compact: float = 43200.0   # 12시간 — 컨텍스트 압축
    stale_reset: float = 86400.0     # 24시간 — 하드 리셋 (Geny 철학)

    def __post_init__(self):
        if not (self.stale_warn < self.stale_idle
                < self.stale_compact < self.stale_reset):
            raise ValueError(
                "Thresholds must be strictly increasing: "
                f"warn={self.stale_warn} < idle={self.stale_idle} "
                f"< compact={self.stale_compact} < reset={self.stale_reset}"
            )


# ============================================================================
# Session Freshness Entry
# ============================================================================

@dataclass
class FreshnessEntry:
    """개별 세션의 프레시니스 상태"""
    session_id: str
    state: FreshnessState = FreshnessState.FRESH
    last_activity: float = field(default_factory=time.monotonic)
    revive_count: int = 0
    max_revives: int = 3
    compaction_triggered: bool = False
    created_at: float = field(default_factory=time.monotonic)

    def idle_seconds(self) -> float:
        """마지막 활동 이후 경과 시간 (초)"""
        return time.monotonic() - self.last_activity

    def touch(self):
        """활동 기록 — 상태를 FRESH로 리셋"""
        self.last_activity = time.monotonic()
        self.state = FreshnessState.FRESH
        self.compaction_triggered = False

    def can_revive(self) -> bool:
        """부활 가능 여부 (최대 횟수 초과 체크)"""
        return self.revive_count < self.max_revives

    def record_revive(self) -> bool:
        """부활 기록. 성공 시 True, 한도 초과 시 False"""
        if not self.can_revive():
            return False
        self.revive_count += 1
        self.touch()
        logger.info(
            "[Freshness] Session %s revived (%d/%d)",
            self.session_id, self.revive_count, self.max_revives,
        )
        return True

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "state": self.state.value,
            "idle_seconds": round(self.idle_seconds(), 1),
            "revive_count": self.revive_count,
            "max_revives": self.max_revives,
            "compaction_triggered": self.compaction_triggered,
        }


# ============================================================================
# Freshness Tracker
# ============================================================================

class FreshnessTracker:
    """세션 프레시니스 중앙 추적기

    모든 세션의 프레시니스 상태를 관리하고,
    타이머 기반 상태 전이를 수행한다.
    """

    def __init__(
        self,
        thresholds: Optional[FreshnessThresholds] = None,
        compact_message_threshold: int = 30,
    ):
        self._entries: Dict[str, FreshnessEntry] = {}
        self._thresholds = thresholds or FreshnessThresholds()
        self._compact_message_threshold = compact_message_threshold
        self._monitor_task: Optional[asyncio.Task] = None

        # 콜백: 상태 전이 시 호출
        self._on_state_change: Optional[
            Callable[[str, FreshnessState, FreshnessState], None]
        ] = None
        # 콜백: 컴팩션 트리거 시 호출
        self._on_compact: Optional[Callable[[str], None]] = None
        # 콜백: 세션 리셋(종료) 시 호출
        self._on_reset: Optional[Callable[[str], None]] = None

    def set_callbacks(
        self,
        on_state_change: Optional[
            Callable[[str, FreshnessState, FreshnessState], None]
        ] = None,
        on_compact: Optional[Callable[[str], None]] = None,
        on_reset: Optional[Callable[[str], None]] = None,
    ):
        """이벤트 콜백 설정"""
        if on_state_change is not None:
            self._on_state_change = on_state_change
        if on_compact is not None:
            self._on_compact = on_compact
        if on_reset is not None:
            self._on_reset = on_reset

    # ── Registration ──────────────────────────────────────────────

    def register(self, session_id: str, max_revives: int = 3) -> FreshnessEntry:
        """새 세션 등록"""
        entry = FreshnessEntry(
            session_id=session_id,
            max_revives=max_revives,
        )
        self._entries[session_id] = entry
        logger.info("[Freshness] Registered session %s", session_id)
        return entry

    def unregister(self, session_id: str) -> bool:
        """세션 등록 해제"""
        if session_id in self._entries:
            del self._entries[session_id]
            logger.info("[Freshness] Unregistered session %s", session_id)
            return True
        return False

    # ── State queries ─────────────────────────────────────────────

    def get(self, session_id: str) -> Optional[FreshnessEntry]:
        """세션의 프레시니스 엔트리 조회"""
        return self._entries.get(session_id)

    def get_state(self, session_id: str) -> Optional[FreshnessState]:
        """세션의 현재 프레시니스 상태"""
        entry = self._entries.get(session_id)
        return entry.state if entry else None

    def touch(self, session_id: str):
        """세션 활동 기록 — FRESH로 리셋"""
        entry = self._entries.get(session_id)
        if entry:
            old_state = entry.state
            entry.touch()
            if old_state != FreshnessState.FRESH:
                logger.info(
                    "[Freshness] Session %s: %s -> FRESH (activity detected)",
                    session_id, old_state.value,
                )
                if self._on_state_change:
                    self._on_state_change(
                        session_id, old_state, FreshnessState.FRESH,
                    )

    def list_entries(self) -> List[FreshnessEntry]:
        """모든 엔트리 반환"""
        return list(self._entries.values())

    def list_by_state(self, state: FreshnessState) -> List[FreshnessEntry]:
        """특정 상태의 엔트리만 반환"""
        return [e for e in self._entries.values() if e.state == state]

    # ── State evaluation ──────────────────────────────────────────

    def evaluate(self, session_id: str) -> Optional[FreshnessState]:
        """세션의 프레시니스 상태를 재평가하고 전이 수행

        Returns:
            새로운 상태. 세션이 없으면 None.
        """
        entry = self._entries.get(session_id)
        if not entry:
            return None

        old_state = entry.state
        idle_secs = entry.idle_seconds()
        th = self._thresholds

        # 경과 시간에 따른 새 상태 결정
        if idle_secs >= th.stale_reset:
            new_state = FreshnessState.STALE_RESET
        elif idle_secs >= th.stale_compact:
            new_state = FreshnessState.STALE_COMPACT
        elif idle_secs >= th.stale_idle:
            new_state = FreshnessState.STALE_IDLE
        elif idle_secs >= th.stale_warn:
            new_state = FreshnessState.STALE_WARN
        else:
            new_state = FreshnessState.FRESH

        if new_state != old_state:
            entry.state = new_state
            logger.info(
                "[Freshness] Session %s: %s -> %s (idle %.0fs)",
                session_id, old_state.value, new_state.value, idle_secs,
            )

            if self._on_state_change:
                self._on_state_change(session_id, old_state, new_state)

            # 컴팩션 트리거
            if (new_state == FreshnessState.STALE_COMPACT
                    and not entry.compaction_triggered):
                entry.compaction_triggered = True
                if self._on_compact:
                    self._on_compact(session_id)

            # 리셋 트리거
            if new_state == FreshnessState.STALE_RESET:
                if self._on_reset:
                    self._on_reset(session_id)

        return new_state

    def evaluate_all(self) -> Dict[str, FreshnessState]:
        """모든 세션의 프레시니스 재평가

        Returns:
            session_id → 새 상태 맵
        """
        results = {}
        for session_id in list(self._entries.keys()):
            state = self.evaluate(session_id)
            if state is not None:
                results[session_id] = state
        return results

    # ── Auto-revive ───────────────────────────────────────────────

    def try_revive(self, session_id: str) -> bool:
        """세션 자동 부활 시도

        Returns:
            True: 부활 가능 (카운트 증가), False: 한도 초과
        """
        entry = self._entries.get(session_id)
        if not entry:
            logger.warning("[Freshness] Cannot revive unknown session %s", session_id)
            return False

        if entry.record_revive():
            return True

        logger.warning(
            "[Freshness] Session %s exceeded max revives (%d/%d), marking for reset",
            session_id, entry.revive_count, entry.max_revives,
        )
        entry.state = FreshnessState.STALE_RESET
        if self._on_reset:
            self._on_reset(session_id)
        return False

    # ── Compaction integration ────────────────────────────────────

    def should_compact(
        self,
        session_id: str,
        message_count: int,
    ) -> bool:
        """컴팩션 필요 여부 판단

        STALE_COMPACT 상태이고 메시지 수가 임계값 초과 시 True.

        Args:
            session_id: 세션 ID
            message_count: 현재 메시지 수
        """
        entry = self._entries.get(session_id)
        if not entry:
            return False

        return (
            entry.state == FreshnessState.STALE_COMPACT
            and message_count > self._compact_message_threshold
            and not entry.compaction_triggered
        )

    def compact_with_guard(
        self,
        session_id: str,
        messages: list,
        model: str = "default",
    ) -> list:
        """ContextWindowGuard와 연동해 컴팩션 수행

        Args:
            session_id: 세션 ID
            messages: 현재 메시지 리스트
            model: 모델 ID (토큰 한도 결정)

        Returns:
            컴팩션된 메시지 리스트
        """
        entry = self._entries.get(session_id)
        if not entry:
            return messages

        from jinxus.core.context_guard import ContextWindowGuard

        guard = ContextWindowGuard(model=model)
        compacted, budget = guard.check_and_compact(messages, auto_compact=True)

        if len(compacted) < len(messages):
            entry.compaction_triggered = True
            logger.info(
                "[Freshness] Session %s compacted: %d -> %d messages "
                "(usage: %.1f%%)",
                session_id, len(messages), len(compacted),
                budget.usage_percent,
            )

        return compacted

    # ── Monitor loop ──────────────────────────────────────────────

    def start_monitor(self, interval: float = 30.0):
        """프레시니스 모니터 시작 (주기적 evaluate_all)"""
        if self._monitor_task is not None:
            return
        self._monitor_task = asyncio.ensure_future(self._monitor_loop(interval))
        logger.info(
            "[Freshness] Monitor started (interval=%.0fs, thresholds: "
            "warn=%.0f, idle=%.0f, compact=%.0f, reset=%.0f)",
            interval,
            self._thresholds.stale_warn,
            self._thresholds.stale_idle,
            self._thresholds.stale_compact,
            self._thresholds.stale_reset,
        )

    async def stop_monitor(self):
        """프레시니스 모니터 중지"""
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            logger.info("[Freshness] Monitor stopped")

    async def _monitor_loop(self, interval: float):
        """모니터 루프 — 주기적으로 모든 세션 평가"""
        while True:
            try:
                await asyncio.sleep(interval)
                states = self.evaluate_all()
                stale_count = sum(
                    1 for s in states.values()
                    if s != FreshnessState.FRESH
                )
                if stale_count:
                    logger.debug(
                        "[Freshness] Monitor tick: %d total, %d stale",
                        len(states), stale_count,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.debug("[Freshness] Monitor tick error", exc_info=True)

    # ── Summary ───────────────────────────────────────────────────

    def summary(self) -> dict:
        """전체 프레시니스 요약"""
        by_state: Dict[str, int] = {}
        for entry in self._entries.values():
            key = entry.state.value
            by_state[key] = by_state.get(key, 0) + 1

        return {
            "total_sessions": len(self._entries),
            "by_state": by_state,
            "total_revives": sum(e.revive_count for e in self._entries.values()),
            "entries": [e.to_dict() for e in self._entries.values()],
        }


# ============================================================================
# Singleton
# ============================================================================

_tracker: Optional[FreshnessTracker] = None


def get_freshness_tracker(
    thresholds: Optional[FreshnessThresholds] = None,
) -> FreshnessTracker:
    """전역 FreshnessTracker 인스턴스 반환"""
    global _tracker
    if _tracker is None:
        _tracker = FreshnessTracker(thresholds=thresholds)
    return _tracker


def reset_freshness_tracker():
    """테스트용 리셋"""
    global _tracker
    _tracker = None
