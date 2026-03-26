"""Mission System v1.0.0 — 미션 모델 + Redis MissionStore

모든 사용자 입력은 미션으로 변환되어 처리된다.
미션 타입: QUICK / STANDARD / EPIC / RAID
미션 상태: BRIEFING → IN_PROGRESS → REVIEW → COMPLETE / FAILED / CANCELLED
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any

import redis.asyncio as aioredis
from jinxus.config import get_settings

logger = logging.getLogger(__name__)


class MissionType(str, Enum):
    """미션 유형"""
    QUICK = "quick"           # 30초 이내, 간단 질문/인사
    STANDARD = "standard"     # 1-10분, 일반 작업
    EPIC = "epic"             # 10분+, 대규모 프로젝트
    RAID = "raid"             # 멀티에이전트 협업 필수


class MissionStatus(str, Enum):
    """미션 상태"""
    BRIEFING = "briefing"         # 미션 분석 + 에이전트 소집
    IN_PROGRESS = "in_progress"   # 에이전트들 작업 중
    REVIEW = "review"             # 결과 리뷰
    COMPLETE = "complete"         # 미션 완료
    FAILED = "failed"             # 미션 실패
    CANCELLED = "cancelled"       # 미션 취소


@dataclass
class MissionSubtask:
    """미션 하위 작업"""
    id: str
    instruction: str
    assigned_agent: str
    status: str = "pending"  # pending / working / done / failed
    result: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Mission:
    """미션 데이터"""
    id: str
    title: str
    description: str
    type: MissionType
    status: MissionStatus = MissionStatus.BRIEFING
    assigned_agents: List[str] = field(default_factory=list)
    subtasks: List[MissionSubtask] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    # 타임스탬프
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # 메타
    session_id: Optional[str] = None
    original_input: str = ""
    # 에이전트 대화 로그
    agent_conversations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "type": self.type.value if isinstance(self.type, MissionType) else self.type,
            "status": self.status.value if isinstance(self.status, MissionStatus) else self.status,
            "assigned_agents": self.assigned_agents,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "session_id": self.session_id,
            "original_input": self.original_input,
            "agent_conversations": self.agent_conversations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Mission":
        subtasks = [
            MissionSubtask(**s) if isinstance(s, dict) else s
            for s in data.get("subtasks", [])
        ]
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            type=MissionType(data["type"]),
            status=MissionStatus(data["status"]),
            assigned_agents=data.get("assigned_agents", []),
            subtasks=subtasks,
            result=data.get("result"),
            error=data.get("error"),
            created_at=data.get("created_at", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            session_id=data.get("session_id"),
            original_input=data.get("original_input", ""),
            agent_conversations=data.get("agent_conversations", []),
        )

    @property
    def duration_ms(self) -> Optional[int]:
        if self.started_at and self.completed_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            return int((end - start).total_seconds() * 1000)
        return None

    @property
    def progress(self) -> float:
        """미션 진행률 (0.0 ~ 1.0)"""
        if self.status == MissionStatus.COMPLETE:
            return 1.0
        if not self.subtasks:
            if self.status == MissionStatus.BRIEFING:
                return 0.1
            if self.status == MissionStatus.IN_PROGRESS:
                return 0.5
            if self.status == MissionStatus.REVIEW:
                return 0.9
            return 0.0
        done = sum(1 for s in self.subtasks if s.status == "done")
        return done / len(self.subtasks)


class MissionStore:
    """Redis 기반 미션 저장소"""

    _PREFIX = "jinxus:mission"
    _INDEX_KEY = "jinxus:missions:index"
    _TTL = 7 * 24 * 3600  # 7일

    def __init__(self):
        settings = get_settings()
        self._redis: Optional[aioredis.Redis] = None
        self._host = settings.redis_host
        self._port = settings.redis_port
        self._password = settings.redis_password if settings.redis_password else None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=self._host, port=self._port, password=self._password,
                decode_responses=True,
            )
        return self._redis

    async def save(self, mission: Mission) -> None:
        """미션 저장"""
        r = await self._get_redis()
        key = f"{self._PREFIX}:{mission.id}"
        data = json.dumps(mission.to_dict(), ensure_ascii=False)
        pipe = r.pipeline()
        pipe.set(key, data, ex=self._TTL)
        pipe.zadd(self._INDEX_KEY, {mission.id: time.time()})
        await pipe.execute()

    async def get(self, mission_id: str) -> Optional[Mission]:
        """미션 조회"""
        r = await self._get_redis()
        data = await r.get(f"{self._PREFIX}:{mission_id}")
        if not data:
            return None
        return Mission.from_dict(json.loads(data))

    async def list_recent(self, limit: int = 20) -> List[Mission]:
        """최근 미션 목록 (최신순)"""
        r = await self._get_redis()
        ids = await r.zrevrange(self._INDEX_KEY, 0, limit - 1)
        if not ids:
            return []
        pipe = r.pipeline()
        for mid in ids:
            pipe.get(f"{self._PREFIX}:{mid}")
        results = await pipe.execute()
        missions = []
        for raw in results:
            if raw:
                missions.append(Mission.from_dict(json.loads(raw)))
        return missions

    async def list_by_status(self, status: MissionStatus, limit: int = 20) -> List[Mission]:
        """상태별 미션 목록"""
        all_missions = await self.list_recent(limit=100)
        filtered = [m for m in all_missions if m.status == status]
        return filtered[:limit]

    async def delete(self, mission_id: str) -> bool:
        """미션 삭제"""
        r = await self._get_redis()
        pipe = r.pipeline()
        pipe.delete(f"{self._PREFIX}:{mission_id}")
        pipe.zrem(self._INDEX_KEY, mission_id)
        results = await pipe.execute()
        return results[0] > 0

    async def add_conversation(
        self, mission_id: str,
        from_agent: str, to_agent: Optional[str],
        message: str, msg_type: str = "dm",
    ) -> None:
        """미션에 에이전트 대화 로그 추가"""
        mission = await self.get(mission_id)
        if not mission:
            return
        mission.agent_conversations.append({
            "from": from_agent,
            "to": to_agent,
            "message": message,
            "type": msg_type,  # dm / huddle / broadcast / report
            "timestamp": datetime.now().isoformat(),
        })
        # 최대 200개 대화만 유지 (도구 사용 로그 포함)
        if len(mission.agent_conversations) > 200:
            mission.agent_conversations = mission.agent_conversations[-200:]
        await self.save(mission)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._redis = None


# 싱글톤
_store: Optional[MissionStore] = None


def get_mission_store() -> MissionStore:
    global _store
    if _store is None:
        _store = MissionStore()
    return _store
