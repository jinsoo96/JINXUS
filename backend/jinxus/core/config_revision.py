"""Config Revision + Rollback (Paperclip 패턴)

에이전트 설정 변경을 리비전으로 기록. 문제 시 이전 버전 롤백.
HR 시스템 안전성 강화.
"""
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

import redis.asyncio as aioredis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# Redis 키
_REVISIONS_KEY = "jinxus:config_revisions:{agent}"
_CURRENT_CONFIG_KEY = "jinxus:config_current:{agent}"
_MAX_REVISIONS = 50


@dataclass
class ConfigRevision:
    """설정 리비전"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent: str = ""
    version: int = 0
    config_snapshot: dict = field(default_factory=dict)
    change_reason: str = ""
    changed_by: str = ""  # 누가 변경했는지 (user / system / agent)
    created_at: float = field(default_factory=time.time)


class ConfigRevisionManager:
    """설정 리비전 관리자"""

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

    async def save_revision(
        self,
        agent: str,
        config: dict,
        change_reason: str = "",
        changed_by: str = "system",
    ) -> ConfigRevision:
        """설정 변경 리비전 저장"""
        r = await self._get_redis()
        revisions_key = _REVISIONS_KEY.format(agent=agent)

        # 현재 버전 번호
        count = await r.llen(revisions_key)
        version = count + 1

        revision = ConfigRevision(
            agent=agent,
            version=version,
            config_snapshot=config,
            change_reason=change_reason,
            changed_by=changed_by,
        )

        # 리비전 저장
        await r.rpush(revisions_key, json.dumps(asdict(revision), ensure_ascii=False))
        await r.ltrim(revisions_key, -_MAX_REVISIONS, -1)

        # 현재 설정 업데이트
        current_key = _CURRENT_CONFIG_KEY.format(agent=agent)
        await r.set(current_key, json.dumps(config, ensure_ascii=False))

        logger.info(
            f"[ConfigRevision] {agent} v{version}: {change_reason} (by {changed_by})"
        )
        return revision

    async def get_current(self, agent: str) -> Optional[dict]:
        """현재 설정 조회"""
        r = await self._get_redis()
        current_key = _CURRENT_CONFIG_KEY.format(agent=agent)
        data = await r.get(current_key)
        if data:
            return json.loads(data)
        return None

    async def get_history(self, agent: str, limit: int = 20) -> list[dict]:
        """리비전 이력 조회"""
        r = await self._get_redis()
        revisions_key = _REVISIONS_KEY.format(agent=agent)
        raw_list = await r.lrange(revisions_key, -limit, -1)
        revisions = []
        for raw in raw_list:
            try:
                revisions.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return list(reversed(revisions))

    async def get_revision(self, agent: str, version: int) -> Optional[dict]:
        """특정 버전 리비전 조회"""
        history = await self.get_history(agent, limit=_MAX_REVISIONS)
        for rev in history:
            if rev.get("version") == version:
                return rev
        return None

    async def rollback(self, agent: str, version: int) -> Optional[ConfigRevision]:
        """특정 버전으로 롤백

        Returns:
            새로 생성된 롤백 리비전 (None if version not found)
        """
        target = await self.get_revision(agent, version)
        if not target:
            logger.warning(f"[ConfigRevision] 롤백 대상 없음: {agent} v{version}")
            return None

        config = target.get("config_snapshot", {})
        return await self.save_revision(
            agent=agent,
            config=config,
            change_reason=f"롤백: v{version}으로 복원",
            changed_by="system",
        )

    async def diff(self, agent: str, v1: int, v2: int) -> dict:
        """두 버전 간 차이점"""
        rev1 = await self.get_revision(agent, v1)
        rev2 = await self.get_revision(agent, v2)

        if not rev1 or not rev2:
            return {"error": "버전을 찾을 수 없음"}

        config1 = rev1.get("config_snapshot", {})
        config2 = rev2.get("config_snapshot", {})

        added = {k: v for k, v in config2.items() if k not in config1}
        removed = {k: v for k, v in config1.items() if k not in config2}
        changed = {
            k: {"from": config1[k], "to": config2[k]}
            for k in config1
            if k in config2 and config1[k] != config2[k]
        }

        return {"added": added, "removed": removed, "changed": changed}

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_config_revision: Optional[ConfigRevisionManager] = None


def get_config_revision() -> ConfigRevisionManager:
    global _config_revision
    if _config_revision is None:
        _config_revision = ConfigRevisionManager()
    return _config_revision
