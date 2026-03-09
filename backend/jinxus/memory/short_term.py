"""Redis 기반 단기기억 시스템"""
import json
import redis.asyncio as redis
from typing import Optional
from datetime import datetime

from jinxus.config import get_settings


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

    def _session_meta_key(self, session_id: str) -> str:
        """세션 메타데이터 키 생성"""
        return f"jinxus:session_meta:{session_id}"

    # ===== 세션 메타데이터 (Session Freshness Policy 용) =====

    async def get_session_meta(self, session_id: str) -> dict | None:
        """세션 메타데이터 조회 (created_at, last_active, iteration_count)"""
        await self.connect()
        key = self._session_meta_key(session_id)
        data = await self._redis.hgetall(key)
        return data if data else None

    async def init_session_meta(self, session_id: str) -> None:
        """세션 메타데이터 초기화 (첫 메시지 시 호출)"""
        await self.connect()
        key = self._session_meta_key(session_id)
        exists = await self._redis.exists(key)
        if not exists:
            now = datetime.now().isoformat()
            await self._redis.hset(key, mapping={
                "created_at": now,
                "last_active": now,
                "iteration_count": "0",
            })
            await self._redis.expire(key, self._ttl)

    async def touch_session_meta(self, session_id: str) -> None:
        """세션 활성 시간 갱신 + iteration 카운터 증가"""
        await self.connect()
        key = self._session_meta_key(session_id)
        now = datetime.now().isoformat()
        await self._redis.hset(key, "last_active", now)
        await self._redis.hincrby(key, "iteration_count", 1)
        await self._redis.expire(key, self._ttl)

    async def clear_session_meta(self, session_id: str) -> None:
        """세션 메타데이터 삭제"""
        await self.connect()
        key = self._session_meta_key(session_id)
        await self._redis.delete(key)

    async def save_message(
        self, session_id: str, role: str, content: str, metadata: Optional[dict] = None
    ) -> None:
        """메시지 저장"""
        await self.connect()
        key = self._session_key(session_id)

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
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
        """세션 삭제 (메시지 + 메타데이터)"""
        await self.connect()
        key = self._session_key(session_id)
        meta_key = self._session_meta_key(session_id)
        await self._redis.delete(key, meta_key)

    async def extend_ttl(self, session_id: str) -> None:
        """세션 TTL 연장"""
        await self.connect()
        key = self._session_key(session_id)
        await self._redis.expire(key, self._ttl)

    async def list_sessions(self) -> list[dict]:
        """모든 세션 목록 조회"""
        await self.connect()
        pattern = "jinxus:session:*"
        sessions = []

        async for key in self._redis.scan_iter(match=pattern):
            session_id = key.replace("jinxus:session:", "")
            # 세션 정보 조회
            messages = await self._redis.lrange(key, 0, -1)
            if messages:
                first_msg = json.loads(messages[0])
                last_msg = json.loads(messages[-1])
                ttl = await self._redis.ttl(key)

                # 세션 타입 판별
                if session_id.startswith("telegram_"):
                    session_type = "telegram"
                    chat_id = session_id.replace("telegram_", "").replace("telegram_bg_", "")
                elif session_id.startswith("scheduled_"):
                    session_type = "scheduled"
                    chat_id = None
                else:
                    session_type = "web"
                    chat_id = None

                sessions.append({
                    "session_id": session_id,
                    "session_type": session_type,
                    "chat_id": chat_id,
                    "message_count": len(messages),
                    "first_message_at": first_msg.get("timestamp"),
                    "last_message_at": last_msg.get("timestamp"),
                    "ttl_seconds": ttl if ttl > 0 else None,
                    "preview": last_msg.get("content", "")[:100],
                })

        # 최신순 정렬
        sessions.sort(key=lambda x: x.get("last_message_at", ""), reverse=True)
        return sessions


# 싱글톤 인스턴스
_short_term_memory: Optional[ShortTermMemory] = None


def get_short_term_memory() -> ShortTermMemory:
    """단기기억 싱글톤 반환"""
    global _short_term_memory
    if _short_term_memory is None:
        _short_term_memory = ShortTermMemory()
    return _short_term_memory
