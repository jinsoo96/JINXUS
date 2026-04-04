"""Routine — 반복 작업 엔진 (Paperclip 패턴)

Cron 기반 반복 미션 자동 생성.
"매일 아침 브리핑", "주간 리포트" 같은 반복 작업을 자동화.
AAI 시간 트리거 구현체.
"""
import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import redis.asyncio as aioredis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# Redis 키
_ROUTINES_KEY = "jinxus:routines"
_ROUTINE_KEY = "jinxus:routine:{routine_id}"
_ROUTINE_RUNS_KEY = "jinxus:routine_runs:{routine_id}"


class ConcurrencyPolicy(str, Enum):
    SKIP_IF_ACTIVE = "skip_if_active"       # 이전 실행 중이면 건너뜀
    COALESCE = "coalesce"                    # 이전 실행 중이면 합침
    ALWAYS_ENQUEUE = "always_enqueue"        # 항상 큐에 추가


class RoutineStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


@dataclass
class Routine:
    """반복 작업 정의"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    description: str = ""
    cron_expr: str = ""  # Cron 표현식 (예: "0 9 * * *" = 매일 9시)
    mission_template: str = ""  # 미션 생성 템플릿
    assigned_agent: str = ""  # 담당 에이전트 (비우면 CORE 판단)
    concurrency_policy: str = ConcurrencyPolicy.SKIP_IF_ACTIVE.value
    status: str = RoutineStatus.ACTIVE.value
    last_run_at: float = 0.0
    next_run_at: float = 0.0
    run_count: int = 0
    goal_id: str = ""  # 연결된 Goal ID
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


@dataclass
class RoutineRun:
    """반복 작업 실행 기록"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    routine_id: str = ""
    mission_id: str = ""
    status: str = "pending"  # pending / running / completed / failed / skipped
    started_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    result: str = ""


def cron_next_run(cron_expr: str, after: float = 0.0) -> float:
    """다음 실행 시간 계산 (croniter 기반 — 전체 cron 문법 지원)

    지원 형식: "분 시 일 월 요일" (5필드) + 모든 표준 cron 표현식
    예: "0 9 * * *", "*/30 * * * *", "0 9 * * 1-5"
    """
    from datetime import datetime
    try:
        from croniter import croniter
        base = datetime.fromtimestamp(after) if after else datetime.now()
        return croniter(cron_expr, base).get_next(float)
    except Exception as e:
        logger.error(f"[Routine] cron 파싱 실패 ({cron_expr}): {e}")
        return 0.0


class RoutineManager:
    """반복 작업 관리자"""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None
        self._running: dict[str, bool] = {}  # routine_id → is_running

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

    async def create(
        self,
        name: str,
        cron_expr: str,
        mission_template: str,
        description: str = "",
        assigned_agent: str = "",
        concurrency_policy: str = ConcurrencyPolicy.SKIP_IF_ACTIVE.value,
        goal_id: str = "",
        metadata: Optional[dict] = None,
    ) -> Routine:
        """반복 작업 생성"""
        routine = Routine(
            name=name,
            description=description,
            cron_expr=cron_expr,
            mission_template=mission_template,
            assigned_agent=assigned_agent,
            concurrency_policy=concurrency_policy,
            goal_id=goal_id,
            next_run_at=cron_next_run(cron_expr),
            metadata=metadata or {},
        )

        r = await self._get_redis()
        key = _ROUTINE_KEY.format(routine_id=routine.id)
        await r.set(key, json.dumps(asdict(routine), ensure_ascii=False))
        await r.sadd(_ROUTINES_KEY, routine.id)

        logger.info(f"[Routine] 생성: {routine.id} '{name}' cron={cron_expr}")
        return routine

    async def get(self, routine_id: str) -> Optional[Routine]:
        r = await self._get_redis()
        key = _ROUTINE_KEY.format(routine_id=routine_id)
        data = await r.get(key)
        if not data:
            return None
        return Routine(**json.loads(data))

    async def update(self, routine_id: str, **kwargs) -> Optional[Routine]:
        routine = await self.get(routine_id)
        if not routine:
            return None
        for k, v in kwargs.items():
            if hasattr(routine, k):
                setattr(routine, k, v)
        r = await self._get_redis()
        key = _ROUTINE_KEY.format(routine_id=routine_id)
        await r.set(key, json.dumps(asdict(routine), ensure_ascii=False))
        return routine

    async def delete(self, routine_id: str) -> bool:
        r = await self._get_redis()
        key = _ROUTINE_KEY.format(routine_id=routine_id)
        deleted = await r.delete(key)
        await r.srem(_ROUTINES_KEY, routine_id)
        return deleted > 0

    async def list_all(self, status: Optional[str] = None) -> list[Routine]:
        r = await self._get_redis()
        routine_ids = await r.smembers(_ROUTINES_KEY)
        routines = []
        for rid in routine_ids:
            routine = await self.get(rid)
            if routine:
                if status and routine.status != status:
                    continue
                routines.append(routine)
        routines.sort(key=lambda r: r.next_run_at)
        return routines

    async def check_and_trigger(self) -> list[str]:
        """실행 시점이 된 routine들을 트리거 (스케줄러에서 주기적 호출)

        Returns:
            트리거된 routine ID 리스트
        """
        now = time.time()
        triggered = []

        routines = await self.list_all(status=RoutineStatus.ACTIVE.value)
        for routine in routines:
            if routine.next_run_at <= 0 or routine.next_run_at > now:
                continue

            # Autonomy config 체크 — autopilot 꺼져있거나 level 0이면 스킵
            if routine.assigned_agent:
                try:
                    from jinxus.core.trigger_engine import get_trigger_engine
                    autonomy = await get_trigger_engine().get_autonomy_config(routine.assigned_agent)
                    if not autonomy.autopilot_enabled:
                        logger.info(f"[Routine] {routine.name} skip (autopilot 비활성: {routine.assigned_agent})")
                        await self.update(
                            routine.id,
                            next_run_at=cron_next_run(routine.cron_expr, now),
                        )
                        continue
                    if autonomy.autonomy_level <= 0:
                        logger.info(f"[Routine] {routine.name} skip (autonomy_level=0 관찰 모드: {routine.assigned_agent})")
                        await self.update(
                            routine.id,
                            next_run_at=cron_next_run(routine.cron_expr, now),
                        )
                        continue
                except Exception as e:
                    logger.debug(f"[Routine] Autonomy 체크 실패 (무시): {e}")

            # 동시성 정책 체크
            if routine.concurrency_policy == ConcurrencyPolicy.SKIP_IF_ACTIVE.value:
                if self._running.get(routine.id):
                    logger.info(f"[Routine] {routine.name} skip (이전 실행 중)")
                    # 다음 실행 시간 갱신
                    await self.update(
                        routine.id,
                        next_run_at=cron_next_run(routine.cron_expr, now),
                    )
                    continue

            # 트리거
            triggered.append(routine.id)
            self._running[routine.id] = True

            # 다음 실행 시간 갱신
            await self.update(
                routine.id,
                last_run_at=now,
                next_run_at=cron_next_run(routine.cron_expr, now),
                run_count=routine.run_count + 1,
            )

            # 실행 기록
            run = RoutineRun(
                routine_id=routine.id,
                status="pending",
            )
            r = await self._get_redis()
            runs_key = _ROUTINE_RUNS_KEY.format(routine_id=routine.id)
            await r.rpush(runs_key, json.dumps(asdict(run), ensure_ascii=False))
            await r.ltrim(runs_key, -50, -1)  # 최근 50개만 유지

            logger.info(f"[Routine] 트리거: {routine.name} (#{routine.run_count + 1})")

            # 미션 실행 (백그라운드 태스크)
            task = asyncio.create_task(self._fire_mission(routine, run))
            task.add_done_callback(
                lambda t, name=routine.name: logger.error(
                    f"[Routine] {name} 미션 실행 예외: {t.exception()}"
                ) if not t.cancelled() and t.exception() else None
            )

        return triggered

    async def _fire_mission(self, routine: "Routine", run: "RoutineRun") -> None:
        """루틴 → 미션 생성 및 실행"""
        r = await self._get_redis()
        runs_key = _ROUTINE_RUNS_KEY.format(routine_id=routine.id)

        # Budget 체크 — HARD_STOP이면 스킵
        if routine.assigned_agent:
            try:
                from jinxus.core.budget import get_budget_manager
                if await get_budget_manager().should_block(routine.assigned_agent):
                    logger.warning(f"[Routine] {routine.name} 예산 초과 스킵 (agent={routine.assigned_agent})")
                    run.status = "skipped"
                    run.result = "예산 초과로 스킵"
                    run.completed_at = time.time()
                    await r.rpush(runs_key, json.dumps(asdict(run), ensure_ascii=False))
                    self.mark_complete(routine.id)
                    return
            except Exception as e:
                logger.debug(f"[Routine] Budget 체크 실패 (무시): {e}")

        try:
            from jinxus.core.mission_executor_v4 import get_mission_executor_v4
            from jinxus.core.mission_router import get_mission_router
            executor = get_mission_executor_v4()
            mission_router = get_mission_router()
            mission = await mission_router.create_mission(
                routine.mission_template or routine.description,
                session_id=f"routine:{routine.id}",
            )
            run.mission_id = mission.id
            run.status = "running"
            executor.start_mission(mission)
            logger.info(f"[Routine] 미션 생성: {routine.name} → {mission.id}")

            # 완료 대기 (최대 2시간)
            deadline = time.time() + 7200
            while time.time() < deadline:
                await asyncio.sleep(30)
                fresh = await executor._store.get(mission.id)
                if fresh and fresh.status.value in ("complete", "failed", "cancelled"):
                    run.status = "completed" if fresh.status.value == "complete" else "failed"
                    run.result = (fresh.result or fresh.error or "")[:500]
                    break
            else:
                run.status = "failed"
                run.result = "타임아웃"

        except Exception as e:
            logger.error(f"[Routine] 미션 실행 실패 {routine.name}: {e}")
            run.status = "failed"
            run.result = str(e)[:200]
        finally:
            run.completed_at = time.time()
            # run 기록 업데이트
            raw_list = await r.lrange(runs_key, 0, -1)
            updated = False
            for i, raw in enumerate(raw_list):
                try:
                    d = json.loads(raw)
                    if d.get("id") == run.id:
                        await r.lset(runs_key, i, json.dumps(asdict(run), ensure_ascii=False))
                        updated = True
                        break
                except Exception:
                    pass
            if not updated:
                await r.rpush(runs_key, json.dumps(asdict(run), ensure_ascii=False))
            self.mark_complete(routine.id)

    def mark_complete(self, routine_id: str):
        """실행 완료 표시"""
        self._running.pop(routine_id, None)

    async def get_runs(self, routine_id: str, limit: int = 20) -> list[dict]:
        """실행 기록 조회"""
        r = await self._get_redis()
        runs_key = _ROUTINE_RUNS_KEY.format(routine_id=routine_id)
        raw_list = await r.lrange(runs_key, -limit, -1)
        runs = []
        for raw in raw_list:
            try:
                runs.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return list(reversed(runs))

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_routine_manager: Optional[RoutineManager] = None


def get_routine_manager() -> RoutineManager:
    global _routine_manager
    if _routine_manager is None:
        _routine_manager = RoutineManager()
    return _routine_manager
