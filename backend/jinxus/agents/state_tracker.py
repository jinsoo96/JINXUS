"""에이전트 상태 추적기

에이전트의 실시간 상태를 추적하고 UI에 제공한다.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum


class AgentStatus(Enum):
    """에이전트 상태"""
    IDLE = "idle"
    WORKING = "working"
    ERROR = "error"


class GraphNode(Enum):
    """LangGraph 노드"""
    RECEIVE = "receive"
    PLAN = "plan"
    EXECUTE = "execute"
    EVALUATE = "evaluate"
    REFLECT = "reflect"
    MEMORY_WRITE = "memory_write"
    RETURN_RESULT = "return_result"


@dataclass
class AgentRuntimeState:
    """에이전트 런타임 상태"""
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_node: Optional[GraphNode] = None
    current_task: Optional[str] = None
    current_tools: List[str] = field(default_factory=list)
    last_update: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "current_node": self.current_node.value if self.current_node else None,
            "current_task": self.current_task,
            "current_tools": self.current_tools,
            "last_update": self.last_update.isoformat(),
            "error_message": self.error_message,
        }


class AgentStateTracker:
    """에이전트 상태 추적기 (싱글톤)"""

    _instance: Optional["AgentStateTracker"] = None

    def __init__(self):
        self._states: Dict[str, AgentRuntimeState] = {}

    @classmethod
    def get_instance(cls) -> "AgentStateTracker":
        if cls._instance is None:
            cls._instance = AgentStateTracker()
        return cls._instance

    def register_agent(self, agent_name: str) -> None:
        """에이전트 등록"""
        if agent_name not in self._states:
            self._states[agent_name] = AgentRuntimeState(name=agent_name)

    def start_task(self, agent_name: str, task_description: str) -> None:
        """작업 시작"""
        if agent_name not in self._states:
            self.register_agent(agent_name)

        state = self._states[agent_name]
        state.status = AgentStatus.WORKING
        state.current_task = task_description[:100]
        state.current_node = GraphNode.RECEIVE
        state.current_tools = []
        state.error_message = None
        state.last_update = datetime.utcnow()

    def update_node(self, agent_name: str, node: GraphNode) -> None:
        """현재 노드 업데이트"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.current_node = node
            state.last_update = datetime.utcnow()

    def update_tools(self, agent_name: str, tools: List[str]) -> None:
        """사용 중인 도구 업데이트"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.current_tools = tools
            state.last_update = datetime.utcnow()

    def complete_task(self, agent_name: str) -> None:
        """작업 완료"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.status = AgentStatus.IDLE
            state.current_node = None
            state.current_task = None
            state.current_tools = []
            state.last_update = datetime.utcnow()

    def set_error(self, agent_name: str, error: str) -> None:
        """에러 상태 설정"""
        if agent_name in self._states:
            state = self._states[agent_name]
            state.status = AgentStatus.ERROR
            state.error_message = error[:200]
            state.last_update = datetime.utcnow()

    def get_state(self, agent_name: str) -> Optional[AgentRuntimeState]:
        """에이전트 상태 조회"""
        return self._states.get(agent_name)

    def get_all_states(self) -> Dict[str, AgentRuntimeState]:
        """모든 에이전트 상태 조회"""
        return self._states.copy()

    def get_working_agents(self) -> List[AgentRuntimeState]:
        """작업 중인 에이전트 목록"""
        return [
            state for state in self._states.values()
            if state.status == AgentStatus.WORKING
        ]


def get_state_tracker() -> AgentStateTracker:
    """상태 추적기 싱글톤 반환"""
    return AgentStateTracker.get_instance()
