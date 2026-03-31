"""Atomic Checkout — 미션 잠금 (Paperclip 패턴)

Redis SETNX 기반 미션 잠금. 이중 실행 방지.
에이전트가 미션을 시작하기 전 lock 획득, 완료/실패 시 해제.
"""
import logging
import time
from typing import Optional

import redis.asyncio as aioredis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# Redis 키
_LOCK_KEY = "jinxus:mission_lock:{mission_id}"
_LOCK_TTL = 3600  # 1시간 (안전장치)


class MissionAlreadyLockedError(Exception):
    """미션이 이미 다른 에이전트에 의해 잠겨있음 (409 Conflict 패턴)"""
    def __init__(self, mission_id: str, locked_by: str):
        self.mission_id = mission_id
        self.locked_by = locked_by
        super().__init__(f"Mission {mission_id} already locked by {locked_by}")


class MissionLock:
    """미션 Atomic Checkout 관리자"""

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

    async def checkout(
        self,
        mission_id: str,
        agent_name: str,
        ttl: int = _LOCK_TTL,
    ) -> bool:
        """미션 잠금 획득 (Atomic Checkout)

        Args:
            mission_id: 미션 ID
            agent_name: 잠금 요청 에이전트
            ttl: 잠금 유효 시간 (초)

        Returns:
            True if lock acquired

        Raises:
            MissionAlreadyLockedError: 이미 다른 에이전트가 잠금 보유
        """
        r = await self._get_redis()
        key = _LOCK_KEY.format(mission_id=mission_id)

        # SETNX (Set if Not eXists) — atomic
        lock_value = f"{agent_name}:{time.time()}"
        acquired = await r.set(key, lock_value, nx=True, ex=ttl)

        if acquired:
            logger.info(f"[MissionLock] 잠금 획득: {mission_id} by {agent_name}")
            return True

        # 이미 잠겨있음 — 누가 잠겼는지 확인
        existing = await r.get(key)
        locked_by = existing.split(":")[0] if existing else "unknown"

        if locked_by == agent_name:
            # 같은 에이전트가 재시도 → 갱신
            await r.set(key, lock_value, ex=ttl)
            logger.info(f"[MissionLock] 잠금 갱신: {mission_id} by {agent_name}")
            return True

        raise MissionAlreadyLockedError(mission_id, locked_by)

    async def release(self, mission_id: str, agent_name: str) -> bool:
        """미션 잠금 해제

        Args:
            mission_id: 미션 ID
            agent_name: 잠금 해제 요청 에이전트

        Returns:
            True if released
        """
        r = await self._get_redis()
        key = _LOCK_KEY.format(mission_id=mission_id)

        # 본인이 건 잠금만 해제 가능
        existing = await r.get(key)
        if not existing:
            return True  # 이미 해제됨

        locked_by = existing.split(":")[0]
        if locked_by != agent_name:
            logger.warning(
                f"[MissionLock] 잠금 해제 거부: {mission_id} "
                f"(요청: {agent_name}, 소유: {locked_by})"
            )
            return False

        await r.delete(key)
        logger.info(f"[MissionLock] 잠금 해제: {mission_id} by {agent_name}")
        return True

    async def force_release(self, mission_id: str) -> bool:
        """강제 잠금 해제 (관리자용)"""
        r = await self._get_redis()
        key = _LOCK_KEY.format(mission_id=mission_id)
        deleted = await r.delete(key)
        if deleted:
            logger.warning(f"[MissionLock] 강제 잠금 해제: {mission_id}")
        return deleted > 0

    async def get_lock_info(self, mission_id: str) -> Optional[dict]:
        """잠금 정보 조회"""
        r = await self._get_redis()
        key = _LOCK_KEY.format(mission_id=mission_id)
        existing = await r.get(key)

        if not existing:
            return None

        parts = existing.split(":", 1)
        ttl = await r.ttl(key)

        return {
            "mission_id": mission_id,
            "locked_by": parts[0],
            "locked_at": float(parts[1]) if len(parts) > 1 else 0,
            "ttl_remaining": ttl,
        }

    async def is_locked(self, mission_id: str) -> bool:
        """잠금 여부 확인"""
        r = await self._get_redis()
        key = _LOCK_KEY.format(mission_id=mission_id)
        return await r.exists(key) > 0

    async def get_all_locks(self) -> list[dict]:
        """모든 활성 잠금 목록"""
        r = await self._get_redis()
        locks = []

        async for key in r.scan_iter(match="jinxus:mission_lock:*"):
            mission_id = key.split(":")[-1]
            info = await self.get_lock_info(mission_id)
            if info:
                locks.append(info)

        return locks

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_mission_lock: Optional[MissionLock] = None


def get_mission_lock() -> MissionLock:
    global _mission_lock
    if _mission_lock is None:
        _mission_lock = MissionLock()
    return _mission_lock
