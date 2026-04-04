"""TriggerEngine — ���리거 레��스트리 (cron/event/idle/interaction/threshold)

다양한 유형의 트리거를 관리하고, 조건 충�� 시 에이���트를 깨우거나 미션을 생성한���.
Redis 영속화로 서버 재���작 시에도 설정 유지.
"""
import json
import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, List

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class TriggerType(str, Enum):
    CRON = "cron"
    EVENT = "event"
    IDLE = "idle"
    INTERACTION = "interaction"
    THRESHOLD = "threshold"


@dataclass
class TriggerConfig:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    type: str = "cron"
    agent: str = ""
    enabled: bool = True
    config: dict = field(default_factory=dict)
    description: str = ""
    fire_count: int = 0
    last_fired_at: float = 0.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TriggerConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class AutonomyConfig:
    """에이전트별 자율 설정"""
    agent: str = ""
    autopilot_enabled: bool = False
    autonomy_level: int = 0  # 0=관찰, 1=계획, 2=확인후실행, 3=자율실행
    triggers_enabled: bool = True
    heartbeat_interval: int = 3600
    budget_usd: float = 100.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AutonomyConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class TriggerEngine:
    """트리거 레지스트리 — 비동기 Redis 영속화"""

    _TRIGGERS_SET = "jinxus:triggers"
    _TRIGGER_PREFIX = "jinxus:trigger:"
    _AUTONOMY_PREFIX = "jinxus:autonomy:"
    _USER_ACTIVE_KEY = "jinxus:user:last_active"

    def __init__(self, redis_client: aioredis.Redis):
        self._r = redis_client

    # ── ���리거 CRUD ─────────────────────────────

    async def create_trigger(self, config: TriggerConfig) -> TriggerConfig:
        key = f"{self._TRIGGER_PREFIX}{config.id}"
        await self._r.set(key, json.dumps(config.to_dict()))
        await self._r.sadd(self._TRIGGERS_SET, config.id)
        logger.info(f"[TriggerEngine] 트리거 생성: {config.name} ({config.type})")
        return config

    async def list_triggers(self, trigger_type: Optional[str] = None) -> List[TriggerConfig]:
        ids = await self._r.smembers(self._TRIGGERS_SET)
        triggers = []
        for tid in ids:
            tid_str = tid.decode() if isinstance(tid, bytes) else tid
            raw = await self._r.get(f"{self._TRIGGER_PREFIX}{tid_str}")
            if raw:
                data = json.loads(raw)
                if trigger_type and data.get("type") != trigger_type:
                    continue
                triggers.append(TriggerConfig.from_dict(data))
        return sorted(triggers, key=lambda t: t.created_at, reverse=True)

    async def get_trigger(self, trigger_id: str) -> Optional[TriggerConfig]:
        raw = await self._r.get(f"{self._TRIGGER_PREFIX}{trigger_id}")
        if not raw:
            return None
        return TriggerConfig.from_dict(json.loads(raw))

    async def delete_trigger(self, trigger_id: str) -> bool:
        key = f"{self._TRIGGER_PREFIX}{trigger_id}"
        deleted = await self._r.delete(key)
        await self._r.srem(self._TRIGGERS_SET, trigger_id)
        return deleted > 0

    async def toggle_trigger(self, trigger_id: str, enabled: bool) -> bool:
        trigger = await self.get_trigger(trigger_id)
        if not trigger:
            return False
        trigger.enabled = enabled
        await self._r.set(f"{self._TRIGGER_PREFIX}{trigger_id}", json.dumps(trigger.to_dict()))
        return True

    async def record_fire(self, trigger_id: str):
        """트리거 발동 기��"""
        trigger = await self.get_trigger(trigger_id)
        if trigger:
            trigger.fire_count += 1
            trigger.last_fired_at = time.time()
            await self._r.set(f"{self._TRIGGER_PREFIX}{trigger_id}", json.dumps(trigger.to_dict()))

    # ── Autonomy Config ─────────────────────────

    async def get_autonomy_config(self, agent: str) -> AutonomyConfig:
        raw = await self._r.get(f"{self._AUTONOMY_PREFIX}{agent}")
        if raw:
            return AutonomyConfig.from_dict(json.loads(raw))
        return AutonomyConfig(agent=agent)

    async def set_autonomy_config(self, config: AutonomyConfig) -> AutonomyConfig:
        await self._r.set(f"{self._AUTONOMY_PREFIX}{config.agent}", json.dumps(config.to_dict()))
        logger.info(f"[TriggerEngine] ���율 설정: {config.agent} level={config.autonomy_level} enabled={config.autopilot_enabled}")
        return config

    async def get_all_autonomy_configs(self) -> Dict[str, AutonomyConfig]:
        """모든 에이���트 자율 설정 조��"""
        from jinxus.agents.personas import get_all_personas
        personas = get_all_personas()
        configs = {}
        for code in personas:
            configs[code] = await self.get_autonomy_config(code)
        return configs

    # ── 유저 활동 추적 ──��───────────────────────

    async def touch_user_activity(self):
        """유저 활동 기록 (채팅/미션 생성 시 호출)"""
        await self._r.set(self._USER_ACTIVE_KEY, str(time.time()))

    async def get_user_idle_seconds(self) -> float:
        """���저 유휴 시간 (���)"""
        raw = await self._r.get(self._USER_ACTIVE_KEY)
        if not raw:
            return float("inf")
        last = float(raw.decode() if isinstance(raw, bytes) else raw)
        return time.time() - last

    # ── 트리거 체크 루프 ────────────────────────

    async def check_cron_triggers(self):
        """Cron 트리거 체크 — 실행 시점 도달 시 에이전트 깨우기"""
        now = time.time()
        triggers = await self.list_triggers("cron")

        for trigger in triggers:
            if not trigger.enabled or not trigger.agent:
                continue

            cron_expr = trigger.config.get("cron_expr", "")
            if not cron_expr:
                continue

            # 다음 실행 시점 계산
            from jinxus.core.routine import cron_next_run
            # last_fired_at 기준 다음 실행 시점이 현재보다 과거면 발동
            next_run = cron_next_run(cron_expr, trigger.last_fired_at or trigger.created_at)
            if next_run <= 0 or next_run > now:
                continue

            await self._fire_trigger(trigger)

    async def check_idle_triggers(self):
        """유휴 ��리거 체크 — ��저 비활��� 시 에이전트 깨우기"""
        idle_seconds = await self.get_user_idle_seconds()
        triggers = await self.list_triggers("idle")

        for trigger in triggers:
            if not trigger.enabled:
                continue
            threshold = trigger.config.get("idle_minutes", 30) * 60
            if idle_seconds >= threshold:
                # 중복 발동 방지: 마지막 발동 후 threshold 시간이 지나야 재발동
                if trigger.last_fired_at and (time.time() - trigger.last_fired_at) < threshold:
                    continue
                await self._fire_trigger(trigger)

    async def check_threshold_triggers(self):
        """임계치 트리거 체크"""
        triggers = await self.list_triggers("threshold")
        for trigger in triggers:
            if not trigger.enabled:
                continue
            metric = trigger.config.get("metric", "")
            operator = trigger.config.get("operator", ">")
            threshold_value = trigger.config.get("value", 0)

            current_value = await self._get_metric_value(metric, trigger.agent)
            if current_value is None:
                continue

            triggered = False
            if operator == ">" and current_value > threshold_value:
                triggered = True
            elif operator == "<" and current_value < threshold_value:
                triggered = True
            elif operator == ">=" and current_value >= threshold_value:
                triggered = True

            if triggered:
                # 중복 발동 방지: 10분 쿨다운
                if trigger.last_fired_at and (time.time() - trigger.last_fired_at) < 600:
                    continue
                await self._fire_trigger(trigger)

    async def _get_metric_value(self, metric: str, agent: str) -> Optional[float]:
        """메트릭 ���재값 조회"""
        if metric == "budget_usage":
            from jinxus.core.budget import get_budget_manager
            bm = get_budget_manager()
            report = await bm.get_report(agent)
            return report.usage_percent if report else None
        return None

    async def _fire_trigger(self, trigger: TriggerConfig):
        """트리거 발동 — autonomy 레벨에 따라 미션 생성/실행

        autonomy_level:
            0 (관찰): 트리거 스킵, 로그만
            1 (계획): 트리거 발동 로그만 (미션 미생성)
            2 (확인후실행): 미션 생성, approval 필요 표시
            3 (자율실행): 미션 생성 후 바로 실행
        """
        # autopilot / autonomy 레벨 체크
        autonomy = await self.get_autonomy_config(trigger.agent)
        if not autonomy.autopilot_enabled:
            logger.info(f"[TriggerEngine] 트리거 스킵 (autopilot 비활성): {trigger.name} → {trigger.agent}")
            return
        if autonomy.autonomy_level <= 0:
            logger.info(f"[TriggerEngine] 트리거 스킵 (level 0 관찰): {trigger.name} → {trigger.agent}")
            return
        if autonomy.autonomy_level == 1:
            logger.info(f"[TriggerEngine] 트리거 감지 (level 1 계획만): {trigger.name} → {trigger.agent}")
            await self.record_fire(trigger.id)
            return

        # level 2, 3 → 미션 생성
        context = trigger.config.get("mission_template", trigger.description or trigger.name)
        try:
            from jinxus.core.mission_executor_v4 import get_mission_executor_v4
            from jinxus.core.mission_router import get_mission_router

            mission_router = get_mission_router()
            executor = get_mission_executor_v4()

            mission = await mission_router.create_mission(
                context,
                session_id=f"trigger:{trigger.id}",
            )

            # level 2: 미션 생성 + 실행 (오케스트레이터 approval 게이트 활성)
            # level 3: 미션 생성 + 실행 (approval 스킵)
            executor.start_mission(mission)
            level_label = "승인 대기" if autonomy.autonomy_level == 2 else "자율 실행"
            logger.info(f"[TriggerEngine] 트리거 발동 (level {autonomy.autonomy_level} {level_label}): {trigger.name} → mission {mission.id}")

            await self.record_fire(trigger.id)

        except Exception as e:
            logger.error(f"[TriggerEngine] 트리거 미션 생성 실패 {trigger.name}: {e}", exc_info=True)


# 싱글톤
_engine: Optional[TriggerEngine] = None


def get_trigger_engine() -> TriggerEngine:
    global _engine
    if _engine is None:
        from jinxus.config import get_settings
        settings = get_settings()
        r = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            decode_responses=False,
        )
        _engine = TriggerEngine(r)
    return _engine
