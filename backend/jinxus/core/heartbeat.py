"""Heartbeat 프로토콜 (Paperclip 패턴)

에이전트 주기적 깨어남 + 체크리스트 기반 자율 실행.
상시 LLM 호출 대신 깨어남→확인→작업→보고→종료 사이클.
AAI 트리거 엔진의 실행 방식.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Callable, Awaitable

import redis.asyncio as aioredis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# Redis 키
_HEARTBEAT_KEY = "jinxus:heartbeat:{agent}"
_HEARTBEAT_SCHEDULE_KEY = "jinxus:heartbeat_schedule"
_WAKE_REASON_KEY = "jinxus:wake_reason:{agent}"


class WakeReason(str, Enum):
    SCHEDULED = "scheduled"       # 정기 스케줄
    MENTION = "mention"           # @멘션
    INBOX = "inbox"               # 새 inbox 메시지
    TRIGGER = "trigger"           # 화이트보드 트리거
    MANUAL = "manual"             # 수동 호출
    TASK_ASSIGNED = "task_assigned"  # 작업 할당


@dataclass
class HeartbeatResult:
    """Heartbeat 실행 결과"""
    agent: str
    wake_reason: str
    steps_executed: list[str] = field(default_factory=list)
    tasks_found: int = 0
    tasks_completed: int = 0
    messages_processed: int = 0
    duration_s: float = 0.0
    next_heartbeat_at: float = 0.0


@dataclass
class HeartbeatConfig:
    """에이전트별 Heartbeat 설정"""
    agent: str
    enabled: bool = True
    interval_seconds: int = 3600  # 기본 1시간
    checklist: list[str] = field(default_factory=lambda: [
        "check_inbox",
        "check_assigned_tasks",
        "check_whiteboard",
        "report_findings",
    ])


class HeartbeatEngine:
    """Heartbeat 엔진

    에이전트를 주기적으로 깨우고 체크리스트를 실행한다.
    """

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._running_heartbeats: dict[str, bool] = {}
        self._configs: dict[str, HeartbeatConfig] = {}
        self._task: Optional[asyncio.Task] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            settings = get_settings()
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password or None,
                decode_responses=True,
            )
        return self._redis

    def register(self, config: HeartbeatConfig) -> None:
        """에이전트 heartbeat 등록"""
        self._configs[config.agent] = config
        logger.info(
            f"[Heartbeat] 등록: {config.agent} "
            f"(interval={config.interval_seconds}s, steps={len(config.checklist)})"
        )

    def unregister(self, agent: str) -> None:
        """에이전트 heartbeat 해제"""
        self._configs.pop(agent, None)

    async def wake(
        self,
        agent: str,
        reason: str = WakeReason.MANUAL.value,
        context: str = "",
        on_step: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> HeartbeatResult:
        """에이전트 깨우기 (즉시 heartbeat 실행)

        Args:
            agent: 에이전트 이름
            reason: 깨우는 이유
            context: 추가 컨텍스트
            on_step: 스텝별 콜백

        Returns:
            HeartbeatResult
        """
        if self._running_heartbeats.get(agent):
            logger.info(f"[Heartbeat] {agent} 이미 실행 중, inbox에 저장")
            # 바쁘면 wake reason만 저장
            r = await self._get_redis()
            wake_data = json.dumps({
                "reason": reason,
                "context": context,
                "timestamp": time.time(),
            }, ensure_ascii=False)
            await r.rpush(_WAKE_REASON_KEY.format(agent=agent), wake_data)
            return HeartbeatResult(agent=agent, wake_reason=reason)

        self._running_heartbeats[agent] = True
        start = time.time()
        result = HeartbeatResult(agent=agent, wake_reason=reason)

        try:
            config = self._configs.get(agent, HeartbeatConfig(agent=agent))

            # 체크리스트 실행
            for step in config.checklist:
                step_result = await self._execute_step(agent, step, reason, context, on_step)
                result.steps_executed.append(f"{step}: {step_result}")

                if step == "check_inbox":
                    result.messages_processed = int(step_result) if step_result.isdigit() else 0
                elif step == "check_assigned_tasks":
                    result.tasks_found = int(step_result) if step_result.isdigit() else 0

            # 다음 heartbeat 시간 기록
            r = await self._get_redis()
            next_at = time.time() + config.interval_seconds
            await r.set(
                _HEARTBEAT_KEY.format(agent=agent),
                json.dumps({
                    "last_heartbeat": time.time(),
                    "next_heartbeat": next_at,
                    "last_reason": reason,
                }, ensure_ascii=False),
            )
            result.next_heartbeat_at = next_at

        except Exception as e:
            logger.error(f"[Heartbeat] {agent} 실행 오류: {e}")
        finally:
            self._running_heartbeats[agent] = False
            result.duration_s = time.time() - start

        logger.info(
            f"[Heartbeat] {agent} 완료: reason={reason}, "
            f"steps={len(result.steps_executed)}, "
            f"duration={result.duration_s:.1f}s"
        )
        return result

    async def _execute_step(
        self,
        agent: str,
        step: str,
        reason: str,
        context: str,
        on_step: Optional[Callable] = None,
    ) -> str:
        """개별 체크리스트 스텝 실행"""
        if on_step:
            await on_step(agent, step)

        if step == "check_inbox":
            from jinxus.core.inbox import get_inbox
            inbox = get_inbox()
            messages = await inbox.read(agent, unread_only=True)
            if messages:
                await inbox.mark_all_read(agent)
            return str(len(messages))

        elif step == "check_assigned_tasks":
            # TODO: TaskStore에서 에이전트 할당 작업 확인
            return "0"

        elif step == "check_whiteboard":
            # TODO: 화이트보드 새 항목 확인
            return "0"

        elif step == "report_findings":
            # TODO: 발견사항 CORE에게 보고
            return "done"

        return "skip"

    async def mention_wake(self, agent: str, from_agent: str, message: str) -> HeartbeatResult:
        """@멘션으로 에이전트 깨우기"""
        return await self.wake(
            agent=agent,
            reason=WakeReason.MENTION.value,
            context=f"@멘션 from {from_agent}: {message}",
        )

    async def get_status(self, agent: str) -> Optional[dict]:
        """에이전트 heartbeat 상태"""
        r = await self._get_redis()
        data = await r.get(_HEARTBEAT_KEY.format(agent=agent))
        if data:
            return json.loads(data)
        return None

    async def get_all_status(self) -> dict[str, dict]:
        """전체 에이전트 heartbeat 상태"""
        r = await self._get_redis()
        result = {}
        async for key in r.scan_iter(match="jinxus:heartbeat:*"):
            agent = key.split(":")[-1]
            data = await r.get(key)
            if data:
                result[agent] = json.loads(data)
        return result

    async def close(self):
        if self._task:
            self._task.cancel()
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_heartbeat: Optional[HeartbeatEngine] = None


def get_heartbeat() -> HeartbeatEngine:
    global _heartbeat
    if _heartbeat is None:
        _heartbeat = HeartbeatEngine()
    return _heartbeat
