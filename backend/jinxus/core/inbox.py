"""에이전트 간 비동기 메시지 큐 (Geny Inbox 패턴)

Redis 기반 1:1 메시지 전달 시스템.
에이전트가 바쁘면 inbox에 저장, 나중에 처리.
AAI 핵심 인프라 — 에이전트 직접 통신 채널.
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
_INBOX_KEY = "jinxus:inbox:{agent}"
_INBOX_TTL = 86400 * 7  # 7일


@dataclass
class InboxMessage:
    """Inbox 메시지"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    from_agent: str = ""
    to_agent: str = ""
    content: str = ""
    content_type: str = "text"  # text / task / report / question / mention
    priority: int = 0  # 0=normal, 1=high, 2=urgent
    read: bool = False
    created_at: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class InboxManager:
    """에이전트 Inbox 관리자

    각 에이전트는 Redis list로 된 inbox를 가진다.
    메시지는 FIFO로 처리되며, 우선순위별 정렬은 읽기 시 수행.
    """

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

    async def deliver(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        content_type: str = "text",
        priority: int = 0,
        metadata: Optional[dict] = None,
    ) -> str:
        """메시지 전달 (inbox에 저장)

        Returns:
            message_id
        """
        msg = InboxMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            content_type=content_type,
            priority=priority,
            metadata=metadata or {},
        )

        r = await self._get_redis()
        key = _INBOX_KEY.format(agent=to_agent)

        await r.rpush(key, json.dumps(asdict(msg), ensure_ascii=False))
        await r.expire(key, _INBOX_TTL)

        logger.info(
            f"[Inbox] {from_agent} → {to_agent}: {content_type} "
            f"(priority={priority}, id={msg.id})"
        )
        return msg.id

    async def read(
        self,
        agent: str,
        limit: int = 20,
        unread_only: bool = False,
    ) -> list[dict]:
        """inbox 메시지 읽기 (우선순위 내림차순)"""
        r = await self._get_redis()
        key = _INBOX_KEY.format(agent=agent)

        raw_list = await r.lrange(key, 0, -1)
        messages = []
        for raw in raw_list:
            try:
                msg = json.loads(raw)
                if unread_only and msg.get("read"):
                    continue
                messages.append(msg)
            except json.JSONDecodeError:
                continue

        # 우선순위 내림차순, 같으면 시간순
        messages.sort(key=lambda m: (-m.get("priority", 0), m.get("created_at", 0)))
        return messages[:limit]

    async def mark_read(self, agent: str, message_id: str) -> bool:
        """메시지 읽음 처리"""
        r = await self._get_redis()
        key = _INBOX_KEY.format(agent=agent)

        raw_list = await r.lrange(key, 0, -1)
        for i, raw in enumerate(raw_list):
            try:
                msg = json.loads(raw)
                if msg.get("id") == message_id:
                    msg["read"] = True
                    await r.lset(key, i, json.dumps(msg, ensure_ascii=False))
                    return True
            except (json.JSONDecodeError, Exception):
                continue
        return False

    async def mark_all_read(self, agent: str) -> int:
        """모든 메시지 읽음 처리"""
        r = await self._get_redis()
        key = _INBOX_KEY.format(agent=agent)

        raw_list = await r.lrange(key, 0, -1)
        count = 0
        for i, raw in enumerate(raw_list):
            try:
                msg = json.loads(raw)
                if not msg.get("read"):
                    msg["read"] = True
                    await r.lset(key, i, json.dumps(msg, ensure_ascii=False))
                    count += 1
            except (json.JSONDecodeError, Exception):
                continue
        return count

    async def unread_count(self, agent: str) -> int:
        """읽지 않은 메시지 수"""
        r = await self._get_redis()
        key = _INBOX_KEY.format(agent=agent)

        raw_list = await r.lrange(key, 0, -1)
        count = 0
        for raw in raw_list:
            try:
                msg = json.loads(raw)
                if not msg.get("read"):
                    count += 1
            except json.JSONDecodeError:
                continue
        return count

    async def delete_message(self, agent: str, message_id: str) -> bool:
        """메시지 삭제"""
        r = await self._get_redis()
        key = _INBOX_KEY.format(agent=agent)

        raw_list = await r.lrange(key, 0, -1)
        for raw in raw_list:
            try:
                msg = json.loads(raw)
                if msg.get("id") == message_id:
                    await r.lrem(key, 1, raw)
                    return True
            except json.JSONDecodeError:
                continue
        return False

    async def clear(self, agent: str) -> int:
        """inbox 비우기"""
        r = await self._get_redis()
        key = _INBOX_KEY.format(agent=agent)
        count = await r.llen(key)
        await r.delete(key)
        return count

    async def get_all_unread_counts(self) -> dict[str, int]:
        """모든 에이전트의 unread 수 (대시보드용)"""
        r = await self._get_redis()
        result = {}

        # jinxus:inbox:* 패턴 스캔
        async for key in r.scan_iter(match="jinxus:inbox:*"):
            agent = key.split(":")[-1]
            count = await self.unread_count(agent)
            if count > 0:
                result[agent] = count

        return result

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_inbox: Optional[InboxManager] = None


def get_inbox() -> InboxManager:
    global _inbox
    if _inbox is None:
        _inbox = InboxManager()
    return _inbox
