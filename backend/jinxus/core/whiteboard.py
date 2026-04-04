"""Whiteboard v1.0.0 — 공유 화이트보드 시스템

에이전트들이 발견하고 반응하는 공유 정보 허브.
두 가지 항목 타입:
- guideline: 업무 지침사항 (항상 참고, 미션 컨텍스트에 주입)
- memo: 메모/녹음 기록 (에이전트가 발견 → CORE에 보고 → 자동 미션 생성)

Redis 키: jinxus:whiteboard:items (Hash), jinxus:whiteboard:item:{id} (String)
"""
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, List

import redis.asyncio as aioredis
from jinxus.config import get_settings

logger = logging.getLogger(__name__)


class ItemType(str, Enum):
    GUIDELINE = "guideline"  # 업무 지침사항 (항상 참고)
    MEMO = "memo"            # 메모 (발견 → 미션 생성)


class ItemStatus(str, Enum):
    NEW = "new"           # 새로 등록됨 (아직 아무도 안 봄)
    SEEN = "seen"         # 에이전트가 발견함
    CLAIMED = "claimed"   # 미션 생성됨 (작업 진행 중)
    DONE = "done"         # 작업 완료
    ARCHIVED = "archived" # 보관 처리


@dataclass
class WhiteboardItem:
    """화이트보드 항목"""
    id: str
    type: ItemType
    title: str
    content: str
    status: ItemStatus = ItemStatus.NEW
    # 메타
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = None
    # 발견 정보 (memo만)
    discovered_by: Optional[str] = None
    discovered_at: Optional[str] = None
    # 미션 연결 (memo만)
    mission_id: Optional[str] = None
    # 태그
    tags: List[str] = field(default_factory=list)
    # 소스 (녹음, 직접입력, 파일 등)
    source: str = "manual"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WhiteboardItem":
        data["type"] = ItemType(data["type"])
        data["status"] = ItemStatus(data["status"])
        return cls(**data)


class WhiteboardStore:
    """Redis 기반 화이트보드 저장소"""
    _PREFIX = "jinxus:whiteboard"

    def __init__(self):
        settings = get_settings()
        self._redis: Optional[aioredis.Redis] = None
        self._host = settings.redis_host
        self._port = settings.redis_port
        self._password = settings.redis_password

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=self._host,
                port=self._port,
                password=self._password if self._password else None,
                decode_responses=True,
            )
        return self._redis

    async def save(self, item: WhiteboardItem) -> None:
        """항목 저장/업데이트"""
        r = await self._get_redis()
        item.updated_at = datetime.now().isoformat()
        key = f"{self._PREFIX}:item:{item.id}"
        await r.set(key, json.dumps(item.to_dict(), ensure_ascii=False))
        # 인덱스에 추가
        await r.hset(f"{self._PREFIX}:index", item.id, item.type.value)

    async def get(self, item_id: str) -> Optional[WhiteboardItem]:
        """항목 조회"""
        r = await self._get_redis()
        data = await r.get(f"{self._PREFIX}:item:{item_id}")
        if not data:
            return None
        return WhiteboardItem.from_dict(json.loads(data))

    async def list_all(self) -> List[WhiteboardItem]:
        """전체 항목 조회 (최신순)"""
        r = await self._get_redis()
        index = await r.hgetall(f"{self._PREFIX}:index")
        items = []
        for item_id in index:
            item = await self.get(item_id)
            if item and item.status != ItemStatus.ARCHIVED:
                items.append(item)
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items

    async def list_by_type(self, item_type: ItemType) -> List[WhiteboardItem]:
        """타입별 항목 조회"""
        all_items = await self.list_all()
        return [i for i in all_items if i.type == item_type]

    async def list_new_memos(self) -> List[WhiteboardItem]:
        """NEW 상태의 메모만 조회 (에이전트 발견 대상)"""
        all_items = await self.list_all()
        return [i for i in all_items if i.type == ItemType.MEMO and i.status == ItemStatus.NEW]

    async def get_active_guidelines(self) -> List[WhiteboardItem]:
        """활성 지침사항 목록 (미션 컨텍스트 주입용)"""
        all_items = await self.list_all()
        return [i for i in all_items
                if i.type == ItemType.GUIDELINE
                and i.status not in (ItemStatus.ARCHIVED, ItemStatus.DONE)]

    async def mark_discovered(self, item_id: str, agent_code: str) -> Optional[WhiteboardItem]:
        """에이전트가 항목을 발견했음을 표시"""
        item = await self.get(item_id)
        if not item or item.status != ItemStatus.NEW:
            return None
        item.status = ItemStatus.SEEN
        item.discovered_by = agent_code
        item.discovered_at = datetime.now().isoformat()
        await self.save(item)
        logger.info(f"[Whiteboard] {agent_code}가 '{item.title}' 발견")
        return item

    async def mark_claimed(self, item_id: str, mission_id: str) -> Optional[WhiteboardItem]:
        """미션이 생성되어 작업 중 표시"""
        item = await self.get(item_id)
        if not item:
            return None
        item.status = ItemStatus.CLAIMED
        item.mission_id = mission_id
        await self.save(item)
        return item

    async def mark_done(self, item_id: str) -> Optional[WhiteboardItem]:
        """작업 완료 표시"""
        item = await self.get(item_id)
        if not item:
            return None
        item.status = ItemStatus.DONE
        await self.save(item)
        return item

    async def delete(self, item_id: str) -> bool:
        """항목 삭제"""
        r = await self._get_redis()
        await r.delete(f"{self._PREFIX}:item:{item_id}")
        await r.hdel(f"{self._PREFIX}:index", item_id)
        return True

    async def close(self):
        if self._redis:
            await self._redis.close()
            self._redis = None


# 싱글톤
_store: Optional[WhiteboardStore] = None


def get_whiteboard_store() -> WhiteboardStore:
    global _store
    if _store is None:
        _store = WhiteboardStore()
    return _store
