"""Response Cache — 에이전트 응답 Redis 캐싱

동일한 질문에 대해 LLM 호출을 절약하기 위한 캐시 레이어.
쿼리 해시 → 응답 캐시 (TTL 5분).

사용 시점:
- JINXUS_CORE.run_stream()에서 직접 응답(DIRECT) 전
- 에이전트 실행 전 (동일 instruction 캐시 확인)
"""
import hashlib
import json
import logging
from typing import Optional

import redis.asyncio as redis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# 캐시 TTL (초)
CACHE_TTL = 300  # 5분
CACHE_PREFIX = "jinxus:cache:"


class ResponseCache:
    """Redis 기반 응답 캐시"""

    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._host = settings.redis_host
        self._port = settings.redis_port
        self._password = settings.redis_password

    async def _ensure_connection(self):
        """Redis 연결 보장"""
        if self._redis is None:
            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password if self._password else None,
                decode_responses=True,
            )

    def _make_key(self, query: str, agent_name: str = "CORE") -> str:
        """쿼리 해시 키 생성"""
        normalized = query.strip().lower()
        hash_val = hashlib.sha256(f"{agent_name}:{normalized}".encode()).hexdigest()[:16]
        return f"{CACHE_PREFIX}{agent_name}:{hash_val}"

    async def get(self, query: str, agent_name: str = "CORE") -> Optional[dict]:
        """캐시된 응답 조회

        Returns:
            캐시 히트 시 {"response": str, "cached_at": str}, 미스 시 None
        """
        try:
            await self._ensure_connection()
            key = self._make_key(query, agent_name)
            data = await self._redis.get(key)
            if data:
                logger.debug(f"[Cache] HIT: {agent_name} ({query[:30]}...)")
                from jinxus.core.metrics import get_metrics
                get_metrics().record_cache_hit()
                return json.loads(data)
            from jinxus.core.metrics import get_metrics
            get_metrics().record_cache_miss()
            return None
        except Exception as e:
            logger.warning(f"[Cache] 조회 실패: {e}")
            return None

    async def set(
        self,
        query: str,
        response: str,
        agent_name: str = "CORE",
        ttl: int = CACHE_TTL,
        metadata: Optional[dict] = None,
    ) -> None:
        """응답 캐싱

        Args:
            query: 원본 질문
            response: 에이전트 응답
            agent_name: 에이전트 이름
            ttl: 캐시 유효 시간 (초)
            metadata: 추가 메타데이터 (agents_used 등)
        """
        try:
            await self._ensure_connection()
            key = self._make_key(query, agent_name)
            from datetime import datetime
            cache_data = {
                "response": response,
                "cached_at": datetime.now().isoformat(),
                "agent_name": agent_name,
            }
            if metadata:
                cache_data.update(metadata)
            await self._redis.setex(key, ttl, json.dumps(cache_data, ensure_ascii=False))
            logger.debug(f"[Cache] SET: {agent_name} ({query[:30]}...) TTL={ttl}s")
        except Exception as e:
            logger.warning(f"[Cache] 저장 실패: {e}")

    async def invalidate(self, query: str, agent_name: str = "CORE") -> None:
        """캐시 무효화"""
        try:
            await self._ensure_connection()
            key = self._make_key(query, agent_name)
            await self._redis.delete(key)
        except Exception as e:
            logger.warning(f"[ResponseCache] 캐시 무효화 실패: {e}")

    async def close(self) -> None:
        """Redis 연결 종료"""
        if self._redis:
            await self._redis.close()
            self._redis = None


# 싱글톤
_cache: Optional[ResponseCache] = None


def get_response_cache() -> ResponseCache:
    """ResponseCache 싱글톤 반환"""
    global _cache
    if _cache is None:
        _cache = ResponseCache()
    return _cache
