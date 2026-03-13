"""위임 이벤트 로거

CORE → 서브에이전트 위임 이벤트를 Redis에 기록.
대시보드에서 실시간 위임 타임라인 표시용.
"""
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Redis 키
DELEGATION_LOG_KEY = "jinxus:delegation_log"
MAX_DELEGATION_LOGS = 100


class DelegationLogger:
    """위임 이벤트 로거 (Redis list 기반)"""

    _instance: Optional["DelegationLogger"] = None

    def __init__(self):
        self._redis = None

    @classmethod
    def get_instance(cls) -> "DelegationLogger":
        if cls._instance is None:
            cls._instance = DelegationLogger()
        return cls._instance

    async def initialize(self, redis_client) -> None:
        """Redis 클라이언트 설정"""
        self._redis = redis_client

    async def log_delegation(
        self,
        from_agent: str,
        to_agent: str,
        instruction: str,
        task_id: str = "",
        execution_mode: str = "sequential",
    ) -> None:
        """위임 이벤트 기록"""
        if not self._redis:
            return

        event = {
            "timestamp": datetime.now().isoformat(),
            "from": from_agent,
            "to": to_agent,
            "instruction": instruction[:200],
            "task_id": task_id,
            "execution_mode": execution_mode,
            "type": "delegate",
        }

        try:
            await self._redis.lpush(DELEGATION_LOG_KEY, json.dumps(event, ensure_ascii=False))
            await self._redis.ltrim(DELEGATION_LOG_KEY, 0, MAX_DELEGATION_LOGS - 1)
        except Exception as e:
            logger.warning(f"위임 이벤트 로깅 실패: {e}")

    async def log_completion(
        self,
        agent_name: str,
        task_id: str,
        success: bool,
        duration_ms: int = 0,
        score: float = 0.0,
    ) -> None:
        """에이전트 작업 완료 이벤트 기록"""
        if not self._redis:
            return

        event = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "task_id": task_id,
            "success": success,
            "duration_ms": duration_ms,
            "score": score,
            "type": "complete",
        }

        try:
            await self._redis.lpush(DELEGATION_LOG_KEY, json.dumps(event, ensure_ascii=False))
            await self._redis.ltrim(DELEGATION_LOG_KEY, 0, MAX_DELEGATION_LOGS - 1)
        except Exception as e:
            logger.warning(f"완료 이벤트 로깅 실패: {e}")

    async def get_recent_events(self, limit: int = 30) -> list[dict]:
        """최근 위임 이벤트 조회"""
        if not self._redis:
            return []

        try:
            raw = await self._redis.lrange(DELEGATION_LOG_KEY, 0, limit - 1)
            return [json.loads(item) for item in raw]
        except Exception as e:
            logger.warning(f"위임 이벤트 조회 실패: {e}")
            return []


def get_delegation_logger() -> DelegationLogger:
    """DelegationLogger 싱글톤 반환"""
    return DelegationLogger.get_instance()
