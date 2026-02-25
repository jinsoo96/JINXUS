"""Redis 기반 단기기억 시스템"""
import json
import redis.asyncio as redis
from typing import Optional
from datetime import datetime

from config import get_settings


class ShortTermMemory:
    """Redis 기반 세션 단기기억 관리"""

    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._host = settings.redis_host
        self._port = settings.redis_port
        self._password = settings.redis_password
        self._ttl = 86400  # 24시간

    async def connect(self) -> None:
        """Redis 연결"""
        if self._redis is None:
            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password if self._password else None,
                decode_responses=True,
            )

    async def disconnect(self) -> None:
        """Redis 연결 종료"""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def is_connected(self) -> bool:
        """연결 상태 확인"""
        if not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except Exception:
            return False

    def _session_key(self, session_id: str) -> str:
        """세션 키 생성"""
        return f"jinxus:session:{session_id}"

    async def save_message(
        self, session_id: str, role: str, content: str, metadata: Optional[dict] = None
    ) -> None:
        """메시지 저장"""
        await self.connect()
        key = self._session_key(session_id)

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        await self._redis.rpush(key, json.dumps(message))
        await self._redis.expire(key, self._ttl)

    async def get_history(self, session_id: str, limit: int = 10) -> list[dict]:
        """최근 N개 메시지 조회"""
        await self.connect()
        key = self._session_key(session_id)

        messages = await self._redis.lrange(key, -limit, -1)
        return [json.loads(msg) for msg in messages]

    async def get_full_history(self, session_id: str) -> list[dict]:
        """전체 세션 히스토리 조회"""
        await self.connect()
        key = self._session_key(session_id)

        messages = await self._redis.lrange(key, 0, -1)
        return [json.loads(msg) for msg in messages]

    async def clear_session(self, session_id: str) -> None:
        """세션 삭제"""
        await self.connect()
        key = self._session_key(session_id)
        await self._redis.delete(key)

    async def extend_ttl(self, session_id: str) -> None:
        """세션 TTL 연장"""
        await self.connect()
        key = self._session_key(session_id)
        await self._redis.expire(key, self._ttl)


# 싱글톤 인스턴스
_short_term_memory: Optional[ShortTermMemory] = None


def get_short_term_memory() -> ShortTermMemory:
    """단기기억 싱글톤 반환"""
    global _short_term_memory
    if _short_term_memory is None:
        _short_term_memory = ShortTermMemory()
    return _short_term_memory
