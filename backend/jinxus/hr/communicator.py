"""에이전트 간 통신 및 작업 위임 시스템"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable, Awaitable
from uuid import uuid4

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """메시지 유형"""
    TASK_DELEGATE = "task_delegate"  # 작업 위임
    TASK_RESULT = "task_result"      # 작업 결과
    INFO_SHARE = "info_share"        # 정보 공유
    QUERY = "query"                  # 질의
    RESPONSE = "response"            # 응답
    STATUS_UPDATE = "status_update"  # 상태 업데이트


class TaskStatus(Enum):
    """위임 작업 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Message:
    """에이전트 간 메시지"""
    id: str
    type: MessageType
    from_agent: str
    to_agent: str
    content: Any
    created_at: datetime = field(default_factory=datetime.now)
    correlation_id: Optional[str] = None  # 관련 메시지 ID (응답/결과용)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "correlation_id": self.correlation_id,
        }


@dataclass
class DelegatedTask:
    """위임된 작업"""
    id: str
    instruction: str
    from_agent: str
    to_agent: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "instruction": self.instruction,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AgentCommunicator:
    """에이전트 간 통신 관리자

    Features:
    - 메시지 송수신
    - 작업 위임 (CORE → SENIOR → JUNIOR 체인)
    - 결과 버블업
    - 비동기 메시지 큐
    """

    def __init__(self):
        self._message_queues: Dict[str, asyncio.Queue] = {}
        self._message_handlers: Dict[str, Callable[[Message], Awaitable[None]]] = {}
        self._delegated_tasks: Dict[str, DelegatedTask] = {}
        self._task_callbacks: Dict[str, Callable[[DelegatedTask], Awaitable[None]]] = {}

    def register_agent(self, agent_name: str):
        """에이전트 등록"""
        if agent_name not in self._message_queues:
            self._message_queues[agent_name] = asyncio.Queue()
            logger.info(f"Agent {agent_name} registered to communicator")

    def unregister_agent(self, agent_name: str):
        """에이전트 등록 해제"""
        if agent_name in self._message_queues:
            del self._message_queues[agent_name]
        if agent_name in self._message_handlers:
            del self._message_handlers[agent_name]
        logger.info(f"Agent {agent_name} unregistered from communicator")

    def set_message_handler(
        self,
        agent_name: str,
        handler: Callable[[Message], Awaitable[None]]
    ):
        """메시지 핸들러 설정"""
        self._message_handlers[agent_name] = handler

    async def send(
        self,
        from_agent: str,
        to_agent: str,
        content: Any,
        message_type: MessageType = MessageType.INFO_SHARE,
        correlation_id: Optional[str] = None,
    ) -> Message:
        """메시지 전송"""
        if to_agent not in self._message_queues:
            raise ValueError(f"Agent {to_agent} not registered")

        message = Message(
            id=str(uuid4()),
            type=message_type,
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            correlation_id=correlation_id,
        )

        await self._message_queues[to_agent].put(message)
        logger.debug(f"Message sent: {from_agent} -> {to_agent} [{message_type.value}]")

        return message

    async def receive(self, agent_name: str, timeout: float = None) -> Optional[Message]:
        """메시지 수신 (블로킹)"""
        if agent_name not in self._message_queues:
            raise ValueError(f"Agent {agent_name} not registered")

        try:
            if timeout:
                message = await asyncio.wait_for(
                    self._message_queues[agent_name].get(),
                    timeout=timeout
                )
            else:
                message = await self._message_queues[agent_name].get()
            return message
        except asyncio.TimeoutError:
            return None

    async def delegate(
        self,
        from_agent: str,
        to_agent: str,
        instruction: str,
        callback: Optional[Callable[[DelegatedTask], Awaitable[None]]] = None,
    ) -> DelegatedTask:
        """작업 위임

        CORE → SENIOR → JUNIOR 체인으로 작업 위임
        결과는 콜백 또는 poll로 확인
        """
        task = DelegatedTask(
            id=str(uuid4()),
            instruction=instruction,
            from_agent=from_agent,
            to_agent=to_agent,
        )

        self._delegated_tasks[task.id] = task

        if callback:
            self._task_callbacks[task.id] = callback

        # 위임 메시지 전송
        await self.send(
            from_agent=from_agent,
            to_agent=to_agent,
            content={"task_id": task.id, "instruction": instruction},
            message_type=MessageType.TASK_DELEGATE,
        )

        logger.info(f"Task delegated: {from_agent} -> {to_agent} [{task.id[:8]}]")
        return task

    async def complete_task(
        self,
        task_id: str,
        result: Any = None,
        error: Optional[str] = None,
    ):
        """위임 작업 완료 보고"""
        if task_id not in self._delegated_tasks:
            raise ValueError(f"Task {task_id} not found")

        task = self._delegated_tasks[task_id]
        task.completed_at = datetime.now()

        if error:
            task.status = TaskStatus.FAILED
            task.error = error
        else:
            task.status = TaskStatus.COMPLETED
            task.result = result

        # 결과 버블업 메시지
        await self.send(
            from_agent=task.to_agent,
            to_agent=task.from_agent,
            content={
                "task_id": task_id,
                "result": result,
                "error": error,
            },
            message_type=MessageType.TASK_RESULT,
            correlation_id=task_id,
        )

        # 콜백 실행
        if task_id in self._task_callbacks:
            try:
                await self._task_callbacks[task_id](task)
            except Exception as e:
                logger.error(f"Task callback error: {e}")
            finally:
                del self._task_callbacks[task_id]

        logger.info(f"Task completed: {task_id[:8]} - {task.status.value}")

    async def share_result(
        self,
        from_agent: str,
        to_agents: List[str],
        result: Any,
        context: Optional[str] = None,
    ):
        """결과 공유 (브로드캐스트)"""
        for to_agent in to_agents:
            if to_agent in self._message_queues:
                await self.send(
                    from_agent=from_agent,
                    to_agent=to_agent,
                    content={"result": result, "context": context},
                    message_type=MessageType.INFO_SHARE,
                )

    def get_task(self, task_id: str) -> Optional[DelegatedTask]:
        """위임 작업 조회"""
        return self._delegated_tasks.get(task_id)

    def get_pending_tasks(self, agent_name: str) -> List[DelegatedTask]:
        """에이전트의 대기 중인 작업 목록"""
        return [
            task for task in self._delegated_tasks.values()
            if task.to_agent == agent_name and task.status == TaskStatus.PENDING
        ]

    def get_delegated_tasks(self, agent_name: str) -> List[DelegatedTask]:
        """에이전트가 위임한 작업 목록"""
        return [
            task for task in self._delegated_tasks.values()
            if task.from_agent == agent_name
        ]

    async def start_message_processor(self, agent_name: str):
        """메시지 처리 루프 시작"""
        if agent_name not in self._message_handlers:
            logger.warning(f"No handler for agent {agent_name}")
            return

        handler = self._message_handlers[agent_name]

        while True:
            try:
                message = await self.receive(agent_name)
                if message:
                    await handler(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Message processing error for {agent_name}: {e}")


# 싱글톤
_communicator: Optional[AgentCommunicator] = None


def get_communicator() -> AgentCommunicator:
    """Communicator 싱글톤 반환"""
    global _communicator
    if _communicator is None:
        _communicator = AgentCommunicator()
    return _communicator
