"""Goal Hierarchy 시스템 (Paperclip 패턴)

company → team → agent → task 4계층 목표 관리.
미션에 "왜 하는지"를 연결하면 에이전트가 자율적으로 우선순위 판단 가능.
AAI 화이트보드의 데이터 구조 기반.
"""
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
_GOALS_KEY = "jinxus:goals"
_GOAL_KEY = "jinxus:goal:{goal_id}"
_MISSION_GOAL_KEY = "jinxus:mission_goal:{mission_id}"


class GoalLevel(str, Enum):
    COMPANY = "company"   # 회사 전체 목표
    TEAM = "team"         # 팀 목표
    AGENT = "agent"       # 에이전트 개인 목표
    TASK = "task"         # 작업 단위 목표


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    PAUSED = "paused"


@dataclass
class Goal:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    description: str = ""
    level: str = GoalLevel.TASK.value
    status: str = GoalStatus.ACTIVE.value
    parent_id: Optional[str] = None  # 상위 목표 ID
    owner: str = ""  # 에이전트/팀 이름
    priority: int = 0  # 0=normal, 1=high, 2=critical
    progress: int = 0  # 0~100
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class GoalManager:
    """Goal Hierarchy 관리자"""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

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
        title: str,
        description: str = "",
        level: str = GoalLevel.TASK.value,
        parent_id: Optional[str] = None,
        owner: str = "",
        priority: int = 0,
        metadata: Optional[dict] = None,
    ) -> Goal:
        """목표 생성"""
        goal = Goal(
            title=title,
            description=description,
            level=level,
            parent_id=parent_id,
            owner=owner,
            priority=priority,
            metadata=metadata or {},
        )

        r = await self._get_redis()
        key = _GOAL_KEY.format(goal_id=goal.id)
        await r.set(key, json.dumps(asdict(goal), ensure_ascii=False))
        await r.sadd(_GOALS_KEY, goal.id)

        logger.info(f"[Goals] 목표 생성: {goal.id} ({level}) {title}")
        return goal

    async def get(self, goal_id: str) -> Optional[Goal]:
        """목표 조회"""
        r = await self._get_redis()
        key = _GOAL_KEY.format(goal_id=goal_id)
        data = await r.get(key)
        if not data:
            return None
        return Goal(**json.loads(data))

    async def update(self, goal_id: str, **kwargs) -> Optional[Goal]:
        """목표 업데이트"""
        goal = await self.get(goal_id)
        if not goal:
            return None

        for k, v in kwargs.items():
            if hasattr(goal, k):
                setattr(goal, k, v)
        goal.updated_at = time.time()

        r = await self._get_redis()
        key = _GOAL_KEY.format(goal_id=goal_id)
        await r.set(key, json.dumps(asdict(goal), ensure_ascii=False))
        return goal

    async def delete(self, goal_id: str) -> bool:
        """목표 삭제"""
        r = await self._get_redis()
        key = _GOAL_KEY.format(goal_id=goal_id)
        deleted = await r.delete(key)
        await r.srem(_GOALS_KEY, goal_id)
        return deleted > 0

    async def list_all(self, level: Optional[str] = None, status: Optional[str] = None) -> list[Goal]:
        """목표 목록 조회"""
        r = await self._get_redis()
        goal_ids = await r.smembers(_GOALS_KEY)

        goals = []
        for gid in goal_ids:
            goal = await self.get(gid)
            if goal:
                if level and goal.level != level:
                    continue
                if status and goal.status != status:
                    continue
                goals.append(goal)

        # 우선순위 내림차순 → 생성일 오름차순
        goals.sort(key=lambda g: (-g.priority, g.created_at))
        return goals

    async def get_children(self, parent_id: str) -> list[Goal]:
        """하위 목표 조회"""
        all_goals = await self.list_all()
        return [g for g in all_goals if g.parent_id == parent_id]

    async def get_hierarchy(self, goal_id: str) -> list[Goal]:
        """목표 계층 추적 (하위 → 상위)"""
        chain = []
        current_id = goal_id
        visited = set()

        while current_id and current_id not in visited:
            visited.add(current_id)
            goal = await self.get(current_id)
            if not goal:
                break
            chain.append(goal)
            current_id = goal.parent_id

        return chain

    async def link_mission(self, mission_id: str, goal_id: str) -> None:
        """미션을 목표에 연결"""
        r = await self._get_redis()
        key = _MISSION_GOAL_KEY.format(mission_id=mission_id)
        await r.set(key, goal_id)

    async def get_mission_goal(self, mission_id: str) -> Optional[Goal]:
        """미션에 연결된 목표 조회"""
        r = await self._get_redis()
        key = _MISSION_GOAL_KEY.format(mission_id=mission_id)
        goal_id = await r.get(key)
        if not goal_id:
            return None
        return await self.get(goal_id)

    async def get_goal_context(self, mission_id: str) -> str:
        """미션의 목표 컨텍스트 문자열 생성 (프롬프트 주입용)"""
        goal = await self.get_mission_goal(mission_id)
        if not goal:
            return ""

        hierarchy = await self.get_hierarchy(goal.id)
        if not hierarchy:
            return ""

        parts = ["[목표 컨텍스트]"]
        for g in reversed(hierarchy):
            parts.append(f"- [{g.level}] {g.title}: {g.description}")

        return "\n".join(parts)

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_goal_manager: Optional[GoalManager] = None


def get_goal_manager() -> GoalManager:
    global _goal_manager
    if _goal_manager is None:
        _goal_manager = GoalManager()
    return _goal_manager
