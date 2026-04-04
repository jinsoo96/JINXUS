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
        self._last_findings: dict[str, dict] = {}  # 스텝 간 발견사항 공유

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

            # trigger 이유: context를 미션 템플릿으로 직접 실행
            if reason == WakeReason.TRIGGER.value and context:
                step_result = await self._fire_trigger_mission(agent, context, on_step)
                result.steps_executed.append(f"trigger_mission: {step_result}")
                result.tasks_completed = 1 if step_result.startswith("m-") else 0
            else:
                # scheduled/manual: 체크리스트 실행
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
            return await self._step_check_assigned_tasks(agent)

        elif step == "check_whiteboard":
            return await self._step_check_whiteboard(agent)

        elif step == "report_findings":
            return await self._step_report_findings(agent)

        return "skip"

    # ── 체크리스트 스텝 구현 ──

    async def _step_check_assigned_tasks(self, agent: str) -> str:
        """에이전트에게 할당된 미완료 미션 수 확인"""
        try:
            from jinxus.core.mission import get_mission_store, MissionStatus
            store = get_mission_store()
            # briefing + in_progress 상태의 미션 중 이 에이전트가 할당된 것
            count = 0
            for status in (MissionStatus.BRIEFING, MissionStatus.IN_PROGRESS):
                missions = await store.list_by_status(status, limit=50)
                for m in missions:
                    if agent in m.assigned_agents:
                        count += 1
            # _findings에 캐시 (report_findings에서 사용)
            self._last_findings[agent] = self._last_findings.get(agent, {})
            self._last_findings[agent]["pending_tasks"] = count
            return str(count)
        except Exception as e:
            logger.error(f"[Heartbeat] check_assigned_tasks 실패 ({agent}): {e}")
            return "0"

    async def _step_check_whiteboard(self, agent: str) -> str:
        """화이트보드에서 NEW 상태 메모 수 확인"""
        try:
            from jinxus.core.whiteboard import get_whiteboard_store
            wb = get_whiteboard_store()
            new_memos = await wb.list_new_memos()
            count = len(new_memos)
            # 발견한 메모 ID 캐시
            self._last_findings[agent] = self._last_findings.get(agent, {})
            self._last_findings[agent]["new_memo_ids"] = [m.id for m in new_memos]
            self._last_findings[agent]["new_memos"] = count
            # 발견 표시
            for memo in new_memos:
                await wb.mark_discovered(memo.id, agent)
            return str(count)
        except Exception as e:
            logger.error(f"[Heartbeat] check_whiteboard 실패 ({agent}): {e}")
            return "0"

    async def _step_report_findings(self, agent: str) -> str:
        """발견사항이 있으면 미션 자동 생성 및 실행"""
        findings = self._last_findings.pop(agent, {})
        pending_tasks = findings.get("pending_tasks", 0)
        new_memos = findings.get("new_memos", 0)
        new_memo_ids = findings.get("new_memo_ids", [])

        if pending_tasks == 0 and new_memos == 0:
            return "nothing_found"

        try:
            from jinxus.core.mission_router import get_mission_router
            from jinxus.core.mission_executor_v4 import get_mission_executor_v4
            from jinxus.core.whiteboard import get_whiteboard_store

            mission_router = get_mission_router()
            executor = get_mission_executor_v4()
            wb = get_whiteboard_store()
            created_missions = []

            # 새 메모마다 미션 생성
            for memo_id in new_memo_ids:
                memo = await wb.get(memo_id)
                if not memo:
                    continue
                description = f"[화이트보드 메모] {memo.title}\n\n{memo.content}"
                mission = await mission_router.create_mission(
                    description,
                    session_id=f"heartbeat:{agent}",
                )
                # 화이트보드 항목에 미션 연결
                await wb.mark_claimed(memo_id, mission.id)
                executor.start_mission(mission)
                created_missions.append(mission.id)
                logger.info(
                    f"[Heartbeat] {agent} 메모 → 미션 생성: "
                    f"'{memo.title}' → {mission.id}"
                )

            if created_missions:
                return f"missions_created:{','.join(created_missions)}"
            return "nothing_actionable"

        except Exception as e:
            logger.error(f"[Heartbeat] report_findings 실패 ({agent}): {e}")
            return f"error:{str(e)[:100]}"

    async def _fire_trigger_mission(
        self,
        agent: str,
        context: str,
        on_step: Optional[Callable] = None,
    ) -> str:
        """트리거 reason: context를 미션 템플릿으로 직접 미션 생성 및 실행"""
        if on_step:
            await on_step(agent, "trigger_mission")
        try:
            from jinxus.core.mission_router import get_mission_router
            from jinxus.core.mission_executor_v4 import get_mission_executor_v4

            mission_router = get_mission_router()
            executor = get_mission_executor_v4()

            mission = await mission_router.create_mission(
                context,
                session_id=f"trigger:{agent}",
            )
            executor.start_mission(mission)
            logger.info(
                f"[Heartbeat] 트리거 미션 생성: {agent} → {mission.id} "
                f"'{context[:50]}...'"
            )
            return mission.id
        except Exception as e:
            logger.error(f"[Heartbeat] 트리거 미션 생성 실패 ({agent}): {e}")
            return f"error:{str(e)[:100]}"

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
