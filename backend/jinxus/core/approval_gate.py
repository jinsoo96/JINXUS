"""ApprovalGate — 진수 승인 게이트

JINXUS_CORE가 작업 계획 수립 후, 실행 전 진수에게 승인을 요청한다.
진수가 승인/수정/취소할 때까지 대기. 타임아웃 시 자동 승인.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from uuid import uuid4

import redis.asyncio as redis

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

APPROVAL_REDIS_PREFIX = "jinxus:approval:"
APPROVAL_TTL = 3600  # 1시간


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    MODIFIED = "modified"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    id: str
    task_description: str
    plan_summary: str
    subtasks: list
    session_id: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    user_feedback: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    resolved_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_description": self.task_description,
            "plan_summary": self.plan_summary,
            "subtasks": self.subtasks,
            "subtasks_count": len(self.subtasks),
            "session_id": self.session_id,
            "status": self.status.value,
            "user_feedback": self.user_feedback,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


class ApprovalGate:
    """진수 승인 게이트

    사용 흐름:
    1. JINXUS_CORE._decompose_node → approval_gate.request(plan) 호출
    2. 채널에 승인 요청 게시 (approval_request 타입 메시지)
    3. 진수가 프론트엔드에서 승인/수정/취소
    4. approval_gate.respond() 호출 → asyncio.Event 해제
    5. request() 리턴 → 실행 계속 또는 중단
    """

    def __init__(self):
        settings = get_settings()
        self._redis: Optional[redis.Redis] = None
        self._host = settings.redis_host
        self._port = settings.redis_port
        self._password = settings.redis_password
        # request_id → (asyncio.Event, ApprovalRequest)
        self._pending: Dict[str, tuple] = {}

    async def _ensure_connection(self):
        if self._redis is None:
            self._redis = redis.Redis(
                host=self._host,
                port=self._port,
                password=self._password if self._password else None,
                decode_responses=True,
            )

    async def request(
        self,
        task_description: str,
        plan_summary: str,
        subtasks: list,
        session_id: str,
        timeout: float = 300.0,
    ) -> ApprovalRequest:
        """승인 요청 생성 및 대기

        Returns:
            ApprovalRequest (status: approved | modified | cancelled)
        """
        await self._ensure_connection()

        req = ApprovalRequest(
            id=str(uuid4())[:12],
            task_description=task_description,
            plan_summary=plan_summary,
            subtasks=subtasks,
            session_id=session_id,
        )

        # Redis 저장
        key = f"{APPROVAL_REDIS_PREFIX}{req.id}"
        await self._redis.setex(key, APPROVAL_TTL, json.dumps(req.to_dict(), ensure_ascii=False))

        # 대기 이벤트 등록
        event = asyncio.Event()
        self._pending[req.id] = (event, req)

        logger.info(f"[ApprovalGate] 승인 요청: {req.id} — {task_description[:60]}")

        # #planning 채널에 승인 요청 게시
        try:
            from jinxus.hr.channel import get_company_channel
            channel = get_company_channel()
            await channel.post(
                from_name="JINXUS_CORE",
                content=plan_summary,
                channel="planning",
                message_type="approval_request",
                metadata={"request_id": req.id, "subtasks_count": len(subtasks)},
            )
        except Exception as e:
            logger.warning(f"[ApprovalGate] 채널 게시 실패: {e}")

        # 승인 대기
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            req.status = ApprovalStatus.APPROVED
            req.user_feedback = "(5분 타임아웃 — 자동 승인)"
            logger.info(f"[ApprovalGate] 타임아웃 자동 승인: {req.id}")
        finally:
            self._pending.pop(req.id, None)

        return req

    async def respond(
        self,
        request_id: str,
        status: ApprovalStatus,
        feedback: str = "",
    ) -> bool:
        """진수 응답 처리 (승인/수정/취소)"""
        await self._ensure_connection()

        if request_id not in self._pending:
            logger.warning(f"[ApprovalGate] 알 수 없는 요청: {request_id}")
            return False

        event, req = self._pending[request_id]
        req.status = status
        req.user_feedback = feedback
        req.resolved_at = datetime.now().isoformat()

        # Redis 업데이트
        key = f"{APPROVAL_REDIS_PREFIX}{request_id}"
        await self._redis.setex(key, APPROVAL_TTL, json.dumps(req.to_dict(), ensure_ascii=False))

        # 채널에 응답 게시
        try:
            from jinxus.hr.channel import get_company_channel
            channel = get_company_channel()
            status_label = {"approved": "✅ 승인", "modified": "✏️ 수정 요청", "cancelled": "❌ 취소"}
            content = status_label.get(status.value, status.value)
            if feedback:
                content += f"\n{feedback}"
            await channel.post(
                from_name="진수",
                content=content,
                channel="planning",
                message_type="approval_response",
                metadata={"request_id": request_id, "status": status.value},
            )
        except Exception as e:
            logger.warning(f"[ApprovalGate] 채널 응답 게시 실패: {e}")

        event.set()
        logger.info(f"[ApprovalGate] 응답 처리: {request_id} → {status.value}")
        return True

    async def get_pending(self) -> List[dict]:
        """대기 중인 승인 요청 목록"""
        return [req.to_dict() for _, req in self._pending.values()]

    async def get_request(self, request_id: str) -> Optional[dict]:
        """Redis에서 승인 요청 조회 (해결된 것 포함)"""
        await self._ensure_connection()
        key = f"{APPROVAL_REDIS_PREFIX}{request_id}"
        data = await self._redis.get(key)
        return json.loads(data) if data else None

    async def close(self):
        if self._redis:
            await self._redis.aclose()
            self._redis = None


# 싱글톤
_gate: Optional[ApprovalGate] = None


def get_approval_gate() -> ApprovalGate:
    global _gate
    if _gate is None:
        _gate = ApprovalGate()
    return _gate
