"""AgentMessenger v1.0.0 — 에이전트 간 메시징 시스템

에이전트끼리 DM, 회의 소집(huddle), 전체 공지(broadcast)를 주고받는다.
미션 실행 중 에이전트 간 티키타카를 가능하게 하는 핵심 모듈.

메시지는 Mission의 agent_conversations에 기록되어 프론트엔드에서 시각화된다.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """에이전트 간 메시지"""
    from_agent: str
    to_agent: Optional[str]  # None이면 브로드캐스트
    content: str
    msg_type: str = "dm"     # dm / huddle / broadcast / report
    mission_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "message": self.content,
            "type": self.msg_type,
            "mission_id": self.mission_id,
            "timestamp": self.timestamp,
        }


@dataclass
class Huddle:
    """회의 (에이전트 그룹 소집)"""
    id: str
    topic: str
    participants: List[str]
    mission_id: Optional[str] = None
    messages: List[AgentMessage] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AgentMessenger:
    """에이전트 간 메시징 허브

    Usage:
        messenger = get_agent_messenger()

        # DM 전송
        await messenger.send_dm("JX_CODER", "JX_REVIEWER", "코드 리뷰 부탁해", mission_id="m-123")

        # 회의 소집
        huddle = await messenger.create_huddle(
            ["JINXUS_CORE", "JX_CODER", "JX_WRITER"],
            topic="README 업데이트 브리핑",
            mission_id="m-123",
        )
        await messenger.huddle_message(huddle.id, "JINXUS_CORE", "README 업데이트 미션이다.")

        # 이벤트 구독 (프론트엔드 SSE용)
        queue = messenger.subscribe(mission_id="m-123")
    """

    def __init__(self):
        # mission_id → [asyncio.Queue] 구독자 목록
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        # 활성 회의
        self._huddles: Dict[str, Huddle] = {}
        # 에이전트별 인박스 (미션과 무관한 DM 버퍼)
        self._inboxes: Dict[str, List[AgentMessage]] = {}
        # 이벤트 버퍼 (구독 전 이벤트 유실 방지, 미션당 최대 50개)
        self._event_buffer: Dict[str, List[dict]] = {}
        self._buffer_limit = 50

    async def send_dm(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        mission_id: Optional[str] = None,
    ) -> AgentMessage:
        """에이전트 간 DM 전송"""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            msg_type="dm",
            mission_id=mission_id,
        )

        # 인박스에 저장
        if to_agent not in self._inboxes:
            self._inboxes[to_agent] = []
        self._inboxes[to_agent].append(msg)
        # 최대 50개 유지
        if len(self._inboxes[to_agent]) > 50:
            self._inboxes[to_agent] = self._inboxes[to_agent][-50:]

        # 미션 스토어에 기록
        if mission_id:
            await self._record_to_mission(mission_id, msg)

        # SSE 이벤트 발행
        await self._emit(mission_id, {
            "event": "agent_dm",
            "data": msg.to_dict(),
        })

        logger.debug(f"[Messenger] DM: {from_agent} → {to_agent}: {content[:50]}")
        return msg

    async def create_huddle(
        self,
        participants: List[str],
        topic: str,
        mission_id: Optional[str] = None,
    ) -> Huddle:
        """회의 소집 — 에이전트들이 회의실로 모임"""
        import uuid
        huddle = Huddle(
            id=str(uuid.uuid4())[:8],
            topic=topic,
            participants=participants,
            mission_id=mission_id,
        )
        self._huddles[huddle.id] = huddle

        await self._emit(mission_id, {
            "event": "huddle_start",
            "data": {
                "huddle_id": huddle.id,
                "topic": topic,
                "participants": participants,
                "mission_id": mission_id,
                "timestamp": huddle.created_at,
            },
        })

        logger.info(f"[Messenger] 회의 소집: {topic} | 참석: {participants}")
        return huddle

    async def huddle_message(
        self,
        huddle_id: str,
        from_agent: str,
        content: str,
    ) -> Optional[AgentMessage]:
        """회의 중 발언"""
        huddle = self._huddles.get(huddle_id)
        if not huddle:
            logger.warning(f"[Messenger] 회의 {huddle_id} 없음")
            return None

        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=None,
            content=content,
            msg_type="huddle",
            mission_id=huddle.mission_id,
        )
        huddle.messages.append(msg)

        if huddle.mission_id:
            await self._record_to_mission(huddle.mission_id, msg)

        await self._emit(huddle.mission_id, {
            "event": "huddle_message",
            "data": {
                "huddle_id": huddle_id,
                **msg.to_dict(),
            },
        })

        return msg

    async def end_huddle(self, huddle_id: str) -> None:
        """회의 종료"""
        huddle = self._huddles.pop(huddle_id, None)
        if huddle:
            await self._emit(huddle.mission_id, {
                "event": "huddle_end",
                "data": {
                    "huddle_id": huddle_id,
                    "topic": huddle.topic,
                    "total_messages": len(huddle.messages),
                },
            })

    async def broadcast(
        self,
        from_agent: str,
        content: str,
        mission_id: Optional[str] = None,
    ) -> AgentMessage:
        """전체 공지"""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=None,
            content=content,
            msg_type="broadcast",
            mission_id=mission_id,
        )

        if mission_id:
            await self._record_to_mission(mission_id, msg)

        await self._emit(mission_id, {
            "event": "agent_broadcast",
            "data": msg.to_dict(),
        })

        return msg

    async def report(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        mission_id: Optional[str] = None,
    ) -> AgentMessage:
        """보고 (결과 보고)"""
        msg = AgentMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            msg_type="report",
            mission_id=mission_id,
        )

        if mission_id:
            await self._record_to_mission(mission_id, msg)

        await self._emit(mission_id, {
            "event": "agent_report",
            "data": msg.to_dict(),
        })

        return msg

    def subscribe(self, mission_id: str) -> asyncio.Queue:
        """미션 이벤트 구독 (SSE용)"""
        queue: asyncio.Queue = asyncio.Queue()
        if mission_id not in self._subscribers:
            self._subscribers[mission_id] = []
        self._subscribers[mission_id].append(queue)

        # 버퍼 리플레이
        for event in self._event_buffer.get(mission_id, []):
            queue.put_nowait(event)

        return queue

    def unsubscribe(self, mission_id: str, queue: asyncio.Queue) -> None:
        """구독 해제"""
        subs = self._subscribers.get(mission_id, [])
        if queue in subs:
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(mission_id, None)
            self._event_buffer.pop(mission_id, None)

    def get_inbox(self, agent_name: str) -> List[AgentMessage]:
        """에이전트 인박스 조회"""
        return self._inboxes.get(agent_name, [])

    def clear_inbox(self, agent_name: str) -> None:
        """인박스 비우기"""
        self._inboxes.pop(agent_name, None)

    async def _emit(self, mission_id: Optional[str], event: dict) -> None:
        """이벤트 발행 (구독자 + 버퍼)"""
        if not mission_id:
            return

        # 버퍼에 저장
        if mission_id not in self._event_buffer:
            self._event_buffer[mission_id] = []
        buf = self._event_buffer[mission_id]
        buf.append(event)
        if len(buf) > self._buffer_limit:
            self._event_buffer[mission_id] = buf[-self._buffer_limit:]

        # 구독자에게 전달
        for queue in self._subscribers.get(mission_id, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"[Messenger] 구독자 큐 가득 참 (mission={mission_id})")

    async def _record_to_mission(self, mission_id: str, msg: AgentMessage) -> None:
        """미션 스토어에 대화 기록"""
        try:
            from jinxus.core.mission import get_mission_store
            store = get_mission_store()
            await store.add_conversation(
                mission_id=mission_id,
                from_agent=msg.from_agent,
                to_agent=msg.to_agent,
                message=msg.content,
                msg_type=msg.msg_type,
            )
        except Exception as e:
            logger.warning(f"[Messenger] 미션 대화 기록 실패: {e}")


# 싱글톤
_messenger: Optional[AgentMessenger] = None


def get_agent_messenger() -> AgentMessenger:
    global _messenger
    if _messenger is None:
        _messenger = AgentMessenger()
    return _messenger
