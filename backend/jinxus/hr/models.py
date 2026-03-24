"""HR 시스템 데이터 모델"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class AgentRole(Enum):
    """에이전트 역할"""
    CEO = "ceo"           # JINXUS_CORE
    SENIOR = "senior"     # 기본 에이전트들
    JUNIOR = "junior"     # 스폰된 에이전트
    INTERN = "intern"     # 임시 에이전트


@dataclass
class AgentRecord:
    """에이전트 기록"""
    id: str
    name: str
    role: AgentRole
    specialty: str
    description: str
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    hired_at: datetime = field(default_factory=datetime.utcnow)
    fired_at: Optional[datetime] = None
    fire_reason: Optional[str] = None
    is_active: bool = True
    total_tasks: int = 0
    success_rate: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    personality_id: str = ""        # personality.py 아키타입 ID

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "specialty": self.specialty,
            "description": self.description,
            "parent_id": self.parent_id,
            "children_ids": self.children_ids,
            "hired_at": self.hired_at.isoformat(),
            "fired_at": self.fired_at.isoformat() if self.fired_at else None,
            "fire_reason": self.fire_reason,
            "is_active": self.is_active,
            "total_tasks": self.total_tasks,
            "success_rate": self.success_rate,
            "metadata": self.metadata,
            "personality_id": self.personality_id,
        }


@dataclass
class HireSpec:
    """에이전트 고용 스펙"""
    specialty: str
    role: AgentRole = AgentRole.SENIOR
    name: Optional[str] = None  # 없으면 자동 생성
    description: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    personality_id: Optional[str] = None   # 없으면 랜덤 선택


@dataclass
class SpawnSpec:
    """새끼 에이전트 스폰 스펙"""
    parent_id: str
    specialty: str
    task_focus: str  # 특화된 작업 유형
    inherit_memory: bool = True
    temporary: bool = False  # True면 작업 완료 후 자동 해제


@dataclass
class OrgNode:
    """조직도 노드"""
    id: str
    name: str
    role: AgentRole
    specialty: str
    is_active: bool
    children: List["OrgNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role.value,
            "specialty": self.specialty,
            "is_active": self.is_active,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class OrgChart:
    """조직도"""
    root: OrgNode
    total_agents: int
    active_agents: int

    def to_dict(self) -> dict:
        return {
            "root": self.root.to_dict(),
            "total_agents": self.total_agents,
            "active_agents": self.active_agents,
        }
