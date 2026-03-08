"""범용 캐시 매니저 - 모든 외부 API 호출에 적용

Redis 기반 캐싱으로 rate limit 최적화.
GitHub, Brave Search, MCP 도구 등 모든 외부 호출에 사용 가능.
"""
import hashlib
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """범용 캐시 매니저

    특징:
    - Redis 기반 (TTL 자동 만료)
    - 네임스페이스 분리 (github:, mcp:, brave: 등)
    - 캐시 통계 추적
    - 수동/자동 정리
    """

    DEFAULT_TTL = 300  # 5분
    MAX_CACHE_SIZE_MB = 100  # Redis 메모리 한도 (대략적)

    # 서비스별 TTL 설정 (베스트 프랙티스 기반)
    SERVICE_TTL = {
        "github": 1800,      # 30분 (레포 정보, ETag로 추가 최적화)
        "github_dynamic": 300,  # 5분 (이슈/PR 등 자주 변하는 데이터)
        "brave": 1800,       # 30분 (검색 결과는 자주 안 바뀜)
        "mcp": 300,          # 5분 (MCP 도구)
        "web": 600,          # 10분 (웹 페이지)
        "default": 300,
    }

    # TTL jitter 범위 (cache stampede 방지)
    TTL_JITTER_PERCENT = 0.1  # ±10%

    def __init__(self):
        self._redis = None
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
        }

    async def _get_redis(self):
        """Redis 클라이언트 lazy 초기화"""
        if self._redis is None:
            try:
                import redis.asyncio as redis
                from jinxus.config import get_settings
                settings = get_settings()
                self._redis = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    password=settings.redis_password or None,
                    decode_responses=True,
                )
            except Exception as e:
                logger.warning(f"Redis 연결 실패: {e}")
        return self._redis

    def _make_key(self, namespace: str, identifier: str) -> str:
        """캐시 키 생성

        Args:
            namespace: 서비스 이름 (github, brave, mcp 등)
            identifier: 고유 식별자 (URL, 쿼리 등)

        Returns:
            캐시 키 (예: "cache:github:abc123")
        """
        # identifier가 너무 길면 해시
        if len(identifier) > 100:
            identifier = hashlib.md5(identifier.encode()).hexdigest()
        return f"cache:{namespace}:{identifier}"

    def _get_ttl(self, namespace: str, custom_ttl: int = None) -> int:
        """TTL 결정 (jitter 포함하여 cache stampede 방지)"""
        import random

        base_ttl = custom_ttl or self.SERVICE_TTL.get(namespace, self.DEFAULT_TTL)

        # ±10% jitter 추가
        jitter = int(base_ttl * self.TTL_JITTER_PERCENT)
        return base_ttl + random.randint(-jitter, jitter)

    async def get(self, namespace: str, identifier: str) -> Optional[Any]:
        """캐시에서 조회

        Args:
            namespace: 서비스 이름
            identifier: 고유 식별자

        Returns:
            캐시된 데이터 또는 None
        """
        try:
            redis = await self._get_redis()
            if not redis:
                return None

            key = self._make_key(namespace, identifier)
            data = await redis.get(key)

            if data:
                self._stats["hits"] += 1
                return json.loads(data)
            else:
                self._stats["misses"] += 1
                return None

        except Exception as e:
            logger.debug(f"캐시 조회 실패: {e}")
            self._stats["misses"] += 1
            return None

    async def set(
        self,
        namespace: str,
        identifier: str,
        data: Any,
        ttl: int = None
    ) -> bool:
        """캐시에 저장

        Args:
            namespace: 서비스 이름
            identifier: 고유 식별자
            data: 저장할 데이터
            ttl: 만료 시간 (초), None이면 서비스 기본값

        Returns:
            저장 성공 여부
        """
        try:
            redis = await self._get_redis()
            if not redis:
                return False

            key = self._make_key(namespace, identifier)
            ttl = self._get_ttl(namespace, ttl)

            await redis.setex(key, ttl, json.dumps(data, default=str))
            self._stats["sets"] += 1
            return True

        except Exception as e:
            logger.debug(f"캐시 저장 실패: {e}")
            return False

    async def delete(self, namespace: str, identifier: str) -> bool:
        """특정 캐시 삭제"""
        try:
            redis = await self._get_redis()
            if not redis:
                return False

            key = self._make_key(namespace, identifier)
            await redis.delete(key)
            return True

        except Exception as e:
            logger.debug(f"캐시 삭제 실패: {e}")
            return False

    async def clear_namespace(self, namespace: str) -> int:
        """특정 네임스페이스의 모든 캐시 삭제

        Args:
            namespace: 서비스 이름 (github, brave, mcp 등)

        Returns:
            삭제된 키 개수
        """
        try:
            redis = await self._get_redis()
            if not redis:
                return 0

            pattern = f"cache:{namespace}:*"
            keys = []
            async for key in redis.scan_iter(match=pattern, count=100):
                keys.append(key)

            if keys:
                await redis.delete(*keys)

            logger.info(f"캐시 정리: {namespace} - {len(keys)}개 삭제")
            return len(keys)

        except Exception as e:
            logger.error(f"캐시 정리 실패: {e}")
            return 0

    async def clear_all(self) -> int:
        """모든 캐시 삭제"""
        try:
            redis = await self._get_redis()
            if not redis:
                return 0

            pattern = "cache:*"
            keys = []
            async for key in redis.scan_iter(match=pattern, count=100):
                keys.append(key)

            if keys:
                await redis.delete(*keys)

            logger.info(f"전체 캐시 정리: {len(keys)}개 삭제")
            return len(keys)

        except Exception as e:
            logger.error(f"전체 캐시 정리 실패: {e}")
            return 0

    async def get_stats(self) -> dict:
        """캐시 통계 조회"""
        try:
            redis = await self._get_redis()
            if not redis:
                return {"error": "Redis 연결 안 됨"}

            # 네임스페이스별 키 개수
            namespaces = {}
            total_keys = 0

            for ns in ["github", "brave", "mcp", "web"]:
                pattern = f"cache:{ns}:*"
                count = 0
                async for _ in redis.scan_iter(match=pattern, count=100):
                    count += 1
                namespaces[ns] = count
                total_keys += count

            # 메모리 사용량
            info = await redis.info("memory")
            used_memory_mb = info.get("used_memory", 0) / (1024 * 1024)

            return {
                "total_keys": total_keys,
                "namespaces": namespaces,
                "memory_mb": round(used_memory_mb, 2),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "sets": self._stats["sets"],
                "hit_rate": round(
                    self._stats["hits"] / max(self._stats["hits"] + self._stats["misses"], 1) * 100,
                    1
                ),
            }

        except Exception as e:
            return {"error": str(e)}

    async def prune_old(self, max_age_seconds: int = 3600) -> int:
        """오래된 캐시 정리 (TTL이 이미 있어서 보통 필요 없음)

        Redis TTL이 자동 만료시키지만, 수동 정리가 필요할 때 사용
        """
        # Redis TTL이 자동으로 처리하므로 보통 필요 없음
        # 하지만 대량 정리가 필요할 때를 위해 남겨둠
        return await self.clear_all()

    # ===== ETag 지원 (GitHub 등 conditional request용) =====

    async def get_etag(self, namespace: str, identifier: str) -> Optional[str]:
        """저장된 ETag 조회"""
        try:
            redis = await self._get_redis()
            if not redis:
                return None

            key = f"etag:{namespace}:{identifier}"
            return await redis.get(key)
        except Exception as e:
            logger.debug(f"ETag 조회 실패: {e}")
            return None

    async def set_with_etag(
        self,
        namespace: str,
        identifier: str,
        data: Any,
        etag: str,
        ttl: int = None
    ) -> bool:
        """ETag와 함께 캐시 저장"""
        try:
            redis = await self._get_redis()
            if not redis:
                return False

            cache_key = self._make_key(namespace, identifier)
            etag_key = f"etag:{namespace}:{identifier}"
            ttl_val = self._get_ttl(namespace, ttl)

            # 데이터와 ETag 동시 저장
            pipe = redis.pipeline()
            pipe.setex(cache_key, ttl_val, json.dumps(data, default=str))
            pipe.setex(etag_key, ttl_val, etag)
            await pipe.execute()

            self._stats["sets"] += 1
            return True
        except Exception as e:
            logger.debug(f"ETag 캐시 저장 실패: {e}")
            return False

    async def validate_etag(self, namespace: str, identifier: str, etag: str) -> bool:
        """ETag 유효성 검증 (304 응답 시 캐시 연장용)"""
        try:
            stored_etag = await self.get_etag(namespace, identifier)
            return stored_etag == etag
        except Exception as e:
            logger.debug(f"ETag 검증 실패: {e}")
            return False

    async def extend_ttl(self, namespace: str, identifier: str, ttl: int = None) -> bool:
        """캐시 TTL 연장 (304 Not Modified 응답 시 사용)"""
        try:
            redis = await self._get_redis()
            if not redis:
                return False

            cache_key = self._make_key(namespace, identifier)
            etag_key = f"etag:{namespace}:{identifier}"
            ttl_val = self._get_ttl(namespace, ttl)

            # 두 키 모두 TTL 연장
            pipe = redis.pipeline()
            pipe.expire(cache_key, ttl_val)
            pipe.expire(etag_key, ttl_val)
            await pipe.execute()

            return True
        except Exception as e:
            logger.debug(f"TTL 연장 실패: {e}")
            return False


# 싱글톤 인스턴스
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """캐시 매니저 싱글톤"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager


# 편의 함수들
async def cache_get(namespace: str, identifier: str) -> Optional[Any]:
    """캐시 조회 (단축 함수)"""
    return await get_cache_manager().get(namespace, identifier)


async def cache_set(namespace: str, identifier: str, data: Any, ttl: int = None) -> bool:
    """캐시 저장 (단축 함수)"""
    return await get_cache_manager().set(namespace, identifier, data, ttl)


async def cache_clear(namespace: str = None) -> int:
    """캐시 정리 (단축 함수)"""
    manager = get_cache_manager()
    if namespace:
        return await manager.clear_namespace(namespace)
    return await manager.clear_all()


async def cache_stats() -> dict:
    """캐시 통계 (단축 함수)"""
    return await get_cache_manager().get_stats()
