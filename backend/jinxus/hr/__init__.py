"""JINXUS HR 시스템

에이전트 고용, 해고, 스폰, 통신 관리
"""
from .models import (
    AgentRole,
    AgentRecord,
    HireSpec,
    SpawnSpec,
    OrgChart,
    OrgNode,
)
from .manager import HRManager, get_hr_manager
from .agent_factory import AgentFactory
from .communicator import (
    AgentCommunicator,
    get_communicator,
    Message,
    MessageType,
    DelegatedTask,
    TaskStatus,
)

__all__ = [
    "AgentRole",
    "AgentRecord",
    "HireSpec",
    "SpawnSpec",
    "OrgChart",
    "OrgNode",
    "HRManager",
    "get_hr_manager",
    "AgentFactory",
    "AgentCommunicator",
    "get_communicator",
    "Message",
    "MessageType",
    "DelegatedTask",
    "TaskStatus",
]
