"""HR 매니저

에이전트 고용, 해고, 스폰, 조직도 관리
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from jinxus.hr.models import (
    AgentRole,
    AgentRecord,
    HireSpec,
    SpawnSpec,
    OrgChart,
    OrgNode,
)
from jinxus.hr.agent_factory import AgentFactory, DynamicAgent

logger = logging.getLogger(__name__)


class HRManager:
    """HR 매니저

    에이전트 풀 관리:
    - 고용: 새 에이전트 생성
    - 해고: 에이전트 비활성화
    - 스폰: 새끼 에이전트 생성
    - 조직도: 계층 구조 관리
    """

    _instance: Optional["HRManager"] = None

    def __init__(self):
        self._records: Dict[str, AgentRecord] = {}
        self._agents: Dict[str, Any] = {}  # 실제 에이전트 인스턴스
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "HRManager":
        if cls._instance is None:
            cls._instance = HRManager()
        return cls._instance

    def initialize(self, orchestrator: Any = None) -> None:
        """초기화: 기존 에이전트들을 레코드에 등록"""
        if self._initialized:
            return

        if orchestrator:
            # 기존 에이전트들을 HR 시스템에 등록
            self._register_existing_agents(orchestrator)

        self._initialized = True
        logger.info("HRManager 초기화 완료")

    def _register_existing_agents(self, orchestrator: Any) -> None:
        """기존 에이전트들을 HR 레코드에 등록"""
        # JINXUS_CORE 등록
        core_id = "jinxus_core"
        self._records[core_id] = AgentRecord(
            id=core_id,
            name="JINXUS_CORE",
            role=AgentRole.CEO,
            specialty="총괄 관리",
            description="진수와 소통하는 유일한 총괄 지휘관",
        )

        # 기존 에이전트들 등록
        existing_agents = {
            "JX_CODER": ("코딩", "코드 작성, 실행, 디버깅 전문가"),
            "JX_RESEARCHER": ("리서치", "정보 수집, 분석, 요약 전문가"),
            "JX_WRITER": ("작문", "글쓰기, 문서화 전문가"),
            "JX_ANALYST": ("데이터 분석", "데이터 분석, 시각화 전문가"),
            "JX_OPS": ("운영", "파일, 스케줄, 시스템 운영 전문가"),
        }

        for name, (specialty, description) in existing_agents.items():
            agent_id = name.lower()
            self._records[agent_id] = AgentRecord(
                id=agent_id,
                name=name,
                role=AgentRole.SENIOR,
                specialty=specialty,
                description=description,
                parent_id=core_id,
            )
            # 부모에 자식 추가
            self._records[core_id].children_ids.append(agent_id)

    async def hire(self, spec: HireSpec) -> AgentRecord:
        """새 에이전트 고용

        Args:
            spec: 고용 스펙

        Returns:
            생성된 에이전트 레코드
        """
        # 에이전트 생성
        agent = AgentFactory.create(spec)

        # 레코드 생성
        record = AgentRecord(
            id=agent.id,
            name=agent.name,
            role=spec.role,
            specialty=spec.specialty,
            description=agent.description,
            parent_id="jinxus_core",  # 기본적으로 CORE 아래에 배치
        )

        # 저장
        self._records[agent.id] = record
        self._agents[agent.id] = agent

        # 부모에 자식 추가
        if record.parent_id and record.parent_id in self._records:
            self._records[record.parent_id].children_ids.append(agent.id)

        logger.info(f"[HR] 에이전트 고용: {agent.name} ({spec.specialty})")

        return record

    async def fire(self, agent_id: str) -> bool:
        """에이전트 해고

        Args:
            agent_id: 에이전트 ID

        Returns:
            성공 여부
        """
        record = self._records.get(agent_id)
        if not record:
            logger.warning(f"[HR] 에이전트 없음: {agent_id}")
            return False

        if record.role == AgentRole.CEO:
            logger.warning("[HR] CEO는 해고할 수 없음")
            return False

        # 비활성화
        record.is_active = False
        record.fired_at = datetime.utcnow()

        # 부모에서 제거
        if record.parent_id and record.parent_id in self._records:
            parent = self._records[record.parent_id]
            if agent_id in parent.children_ids:
                parent.children_ids.remove(agent_id)

        # 자식들도 해고 (cascade)
        for child_id in record.children_ids:
            await self.fire(child_id)

        # 에이전트 인스턴스 제거
        self._agents.pop(agent_id, None)

        logger.info(f"[HR] 에이전트 해고: {record.name}")

        return True

    async def spawn_child(self, spec: SpawnSpec) -> AgentRecord:
        """새끼 에이전트 스폰

        Args:
            spec: 스폰 스펙

        Returns:
            생성된 에이전트 레코드
        """
        parent_record = self._records.get(spec.parent_id)
        if not parent_record:
            raise ValueError(f"부모 에이전트 없음: {spec.parent_id}")

        parent_agent = self._agents.get(spec.parent_id)

        # 새끼 에이전트 생성
        child = AgentFactory.spawn_child(
            parent_agent=parent_agent,
            specialty=spec.specialty,
            task_focus=spec.task_focus,
        )

        # 레코드 생성
        record = AgentRecord(
            id=child.id,
            name=child.name,
            role=AgentRole.JUNIOR,
            specialty=spec.specialty,
            description=child.description,
            parent_id=spec.parent_id,
            metadata={"temporary": spec.temporary, "task_focus": spec.task_focus},
        )

        # 저장
        self._records[child.id] = record
        self._agents[child.id] = child

        # 부모에 자식 추가
        parent_record.children_ids.append(child.id)

        logger.info(f"[HR] 새끼 에이전트 스폰: {child.name} (부모: {parent_record.name})")

        return record

    def get_agent(self, agent_id: str) -> Optional[Any]:
        """에이전트 인스턴스 조회"""
        return self._agents.get(agent_id)

    def get_record(self, agent_id: str) -> Optional[AgentRecord]:
        """에이전트 레코드 조회"""
        return self._records.get(agent_id)

    def get_all_records(self) -> List[AgentRecord]:
        """모든 에이전트 레코드 조회"""
        return list(self._records.values())

    def get_active_records(self) -> List[AgentRecord]:
        """활성 에이전트 레코드만 조회"""
        return [r for r in self._records.values() if r.is_active]

    def get_org_chart(self) -> OrgChart:
        """조직도 생성"""
        def build_node(agent_id: str) -> Optional[OrgNode]:
            record = self._records.get(agent_id)
            if not record:
                return None

            children = []
            for child_id in record.children_ids:
                child_node = build_node(child_id)
                if child_node:
                    children.append(child_node)

            return OrgNode(
                id=record.id,
                name=record.name,
                role=record.role,
                specialty=record.specialty,
                is_active=record.is_active,
                children=children,
            )

        # CEO(JINXUS_CORE)부터 시작
        root = build_node("jinxus_core")
        if not root:
            root = OrgNode(
                id="unknown",
                name="UNKNOWN",
                role=AgentRole.CEO,
                specialty="N/A",
                is_active=False,
            )

        return OrgChart(
            root=root,
            total_agents=len(self._records),
            active_agents=len([r for r in self._records.values() if r.is_active]),
        )

    def get_available_specs(self) -> List[dict]:
        """고용 가능한 에이전트 스펙 목록"""
        return [
            {
                "specialty": key,
                "name": f"JX_{key.upper()}",
                "description": spec.get("description", ""),
                "capabilities": spec.get("capabilities", []),
            }
            for key, spec in AgentFactory.DEFAULT_SPECS.items()
        ]


def get_hr_manager() -> HRManager:
    """HR 매니저 싱글톤 반환"""
    return HRManager.get_instance()
