"""Company Channel — 에이전트 팀 채팅 채널

에이전트들이 직원처럼 서로 대화하고, 진수에게 승인을 요청하는 채널.
Redis에 히스토리 저장, asyncio.Queue로 SSE 구독자에게 실시간 전달.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import uuid4

import redis.asyncio as redis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

CHANNEL_REDIS_PREFIX = "jinxus:channel:"
CHANNEL_HISTORY_TTL = 86400 * 7  # 7일
CHANNEL_MAX_HISTORY = 200


class ChannelName(str, Enum):
    GENERAL = "general"
    DEV = "dev"
    PLATFORM = "platform"
    PRODUCT = "product"
    MARKETING = "marketing"
    BIZ_SUPPORT = "biz-support"


class MessageRole(str, Enum):
    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


# 에이전트 → 소속 채널 매핑
AGENT_CHANNEL_MAP: Dict[str, str] = {
    # 경영
    "JINXUS_CORE": ChannelName.GENERAL,
    "JX_CTO": ChannelName.GENERAL,
    "JX_CFO": ChannelName.GENERAL,
    "JX_COO": ChannelName.GENERAL,
    # 개발팀
    "JX_CODER": ChannelName.DEV,
    "JX_FRONTEND": ChannelName.DEV,
    "JX_BACKEND": ChannelName.DEV,
    "JX_REVIEWER": ChannelName.DEV,
    "JX_TESTER": ChannelName.DEV,
    "JX_MOBILE": ChannelName.DEV,
    # 플랫폼팀
    "JX_ARCHITECT": ChannelName.PLATFORM,
    "JX_INFRA": ChannelName.PLATFORM,
    "JX_AI_ENG": ChannelName.PLATFORM,
    "JX_SECURITY": ChannelName.PLATFORM,
    "JX_DATA_ENG": ChannelName.PLATFORM,
    "JX_PROMPT_ENG": ChannelName.PLATFORM,
    # 프로덕트팀
    "JX_PRODUCT": ChannelName.PRODUCT,
    "JX_RESEARCHER": ChannelName.PRODUCT,
    "JX_WEB_SEARCHER": ChannelName.PRODUCT,
    "JX_DEEP_READER": ChannelName.PRODUCT,
    "JX_FACT_CHECKER": ChannelName.PRODUCT,
    "JX_STRATEGY": ChannelName.PRODUCT,
    # 마케팅팀
    "JX_MARKETING": ChannelName.MARKETING,
    "JX_WRITER": ChannelName.MARKETING,
    "JS_PERSONA": ChannelName.MARKETING,
    "JX_SNS": ChannelName.MARKETING,
    # 경영지원팀
    "JX_ANALYST": ChannelName.BIZ_SUPPORT,
    "JX_OPS": ChannelName.BIZ_SUPPORT,
}


@dataclass
class ChannelMessage:
    id: str
    channel: str
    role: MessageRole
    from_name: str
    content: str
    message_type: str = "chat"  # chat | planning | approval_request | approval_response | system
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel": self.channel,
            "role": self.role.value,
            "from_name": self.from_name,
            "content": self.content,
            "message_type": self.message_type,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class CompanyChannel:
    """에이전트 팀 채널 매니저

    채널 목록: general, engineering, research, ops, planning
    general 채널에는 모든 채널 메시지가 미러링됨 (전사 공지 역할).
    """

    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._host = settings.redis_host
        self._port = settings.redis_port
        self._password = settings.redis_password
        # channel → set of asyncio.Queue (SSE 구독자)
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def _ensure_connection(self):
        if self._redis is None:
            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password if self._password else None,
                decode_responses=True,
            )

    async def post(
        self,
        from_name: str,
        content: str,
        channel: Optional[str] = None,
        message_type: str = "chat",
        metadata: Optional[dict] = None,
    ) -> ChannelMessage:
        """채널에 메시지 게시"""
        await self._ensure_connection()

        # 채널 자동 결정
        if channel is None:
            channel = AGENT_CHANNEL_MAP.get(from_name, ChannelName.GENERAL.value)
        if hasattr(channel, 'value'):
            channel = channel.value

        role = MessageRole.USER if from_name == "진수" else MessageRole.AGENT
        msg = ChannelMessage(
            id=str(uuid4())[:8],
            channel=channel,
            role=role,
            from_name=from_name,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
        )

        # Redis 히스토리 저장
        key = f"{CHANNEL_REDIS_PREFIX}{channel}"
        await self._redis.rpush(key, json.dumps(msg.to_dict(), ensure_ascii=False))
        await self._redis.expire(key, CHANNEL_HISTORY_TTL)
        await self._redis.ltrim(key, -CHANNEL_MAX_HISTORY, -1)

        # 실시간 구독자 전달
        await self._broadcast(channel, msg)

        # general 채널에 미러링 (engineering/research/ops → general에도 복사)
        if channel != ChannelName.GENERAL.value:
            await self._broadcast(ChannelName.GENERAL.value, msg)

        logger.debug(f"[Channel #{channel}] {from_name}: {content[:60]}")
        return msg

    async def clear_history(self, channel: str) -> int:
        """채널 히스토리 전체 삭제. 삭제된 메시지 수 반환."""
        await self._ensure_connection()
        key = f"{CHANNEL_REDIS_PREFIX}{channel}"
        count = await self._redis.llen(key)
        await self._redis.delete(key)
        logger.info(f"[Channel] #{channel} 히스토리 {count}건 삭제")
        return count

    async def get_history(self, channel: str, limit: int = 50) -> List[dict]:
        """채널 히스토리 조회"""
        await self._ensure_connection()
        key = f"{CHANNEL_REDIS_PREFIX}{channel}"
        entries = await self._redis.lrange(key, -limit, -1)
        return [json.loads(e) for e in entries]

    async def get_all_history(self, limit_per_channel: int = 50) -> Dict[str, List[dict]]:
        """모든 채널 히스토리"""
        result = {}
        for ch in ChannelName:
            result[ch.value] = await self.get_history(ch.value, limit_per_channel)
        return result

    async def subscribe(self, channels: Optional[List[str]] = None) -> asyncio.Queue:
        """채널 구독 — 큐 반환. channels=None이면 전체 구독"""
        target = channels or [ch.value for ch in ChannelName]
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        async with self._lock:
            for ch in target:
                if ch not in self._subscribers:
                    self._subscribers[ch] = set()
                self._subscribers[ch].add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue, channels: Optional[List[str]] = None):
        """채널 구독 해제"""
        target = channels or [ch.value for ch in ChannelName]
        async with self._lock:
            for ch in target:
                if ch in self._subscribers:
                    self._subscribers[ch].discard(q)

    async def _broadcast(self, channel: str, msg: ChannelMessage):
        """구독자에게 메시지 브로드캐스트"""
        async with self._lock:
            subscribers = set(self._subscribers.get(channel, set()))
        for q in subscribers:
            try:
                q.put_nowait(msg.to_dict())
            except asyncio.QueueFull:
                logger.warning(f"[Channel] #{channel} 구독자 큐 가득참, 드롭")

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_channel: Optional[CompanyChannel] = None


def get_company_channel() -> CompanyChannel:
    global _channel
    if _channel is None:
        _channel = CompanyChannel()
    return _channel
