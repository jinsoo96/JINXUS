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
from jinxus.hr.agent_factory import AgentFactory
# personas는 agents/__init__.py 순환 임포트 방지를 위해 사용 시점에 임포트

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
        """기존 에이전트들을 HR 레코드에 등록.

        에이전트 목록/역할/설명은 personas.py에서 자동 파생 — 하드코딩 없음.
        순환 임포트 방지를 위해 personas를 여기서 임포트한다.
        """
        from jinxus.agents.personas import PERSONAS, get_persona  # 지연 임포트

        core_persona = get_persona("JINXUS_CORE")
        core_id = "jinxus_core"
        self._records[core_id] = AgentRecord(
            id=core_id,
            name="JINXUS_CORE",
            role=AgentRole.CEO,
            specialty=core_persona.skills or core_persona.role,
            description=f"{core_persona.role} — {core_persona.personality}",
            personality_id=core_persona.personality_id,
        )

        # PERSONAS에서 JINXUS_CORE 제외하고 자동 등록
        for code, persona in PERSONAS.items():
            if code == "JINXUS_CORE":
                continue
            agent_id = code.lower()
            self._records[agent_id] = AgentRecord(
                id=agent_id,
                name=code,
                role=AgentRole.SENIOR,
                specialty=persona.skills or persona.role,
                description=f"{persona.role} — {persona.personality}",
                parent_id=core_id,
                personality_id=persona.personality_id,
            )
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
            personality_id=getattr(agent, "personality_id", ""),
        )

        # 저장
        self._records[agent.id] = record
        self._agents[agent.id] = agent

        # 부모에 자식 추가
        if record.parent_id and record.parent_id in self._records:
            self._records[record.parent_id].children_ids.append(agent.id)

        # 동적 페르소나 등록 → /personas API에서 자동 반환
        self._register_dynamic_persona(agent, spec)

        logger.info(f"[HR] 에이전트 고용: {agent.name} ({spec.specialty})")

        return record

    @staticmethod
    def _register_dynamic_persona(agent: Any, spec: HireSpec) -> None:
        """동적 고용 에이전트의 페르소나를 등록 → 프론트엔드 자동 동기화."""
        from jinxus.agents.personas import AgentPersona, register_dynamic_persona

        # specialty에서 팀 추론
        _SPECIALTY_TEAM = {
            "코딩": "개발팀", "coder": "개발팀", "coding": "개발팀",
            "리서치": "프로덕트팀", "researcher": "프로덕트팀", "research": "프로덕트팀",
            "작문": "마케팅팀", "writer": "마케팅팀", "writing": "마케팅팀",
            "데이터 분석": "경영지원팀", "analyst": "경영지원팀", "analysis": "경영지원팀",
            "운영": "경영지원팀", "ops": "경영지원팀", "devops": "플랫폼팀",
            "인프라": "플랫폼팀", "infra": "플랫폼팀", "platform": "플랫폼팀",
        }
        _SPECIALTY_CHANNEL = {
            "개발팀": "dev", "플랫폼팀": "platform",
            "프로덕트팀": "product", "마케팅팀": "marketing", "경영지원팀": "biz-support",
        }

        team = _SPECIALTY_TEAM.get(spec.specialty.lower(), "경영지원팀")
        channel = _SPECIALTY_CHANNEL.get(team, "general")
        personality_id = getattr(agent, "personality_id", "")

        persona = AgentPersona(
            korean_name=agent.name,
            full_name=agent.name,
            display_name=agent.name,
            role=spec.specialty,
            emoji="🤖",
            personality=agent.description or f"{spec.specialty} 전문가",
            speech_style="맡은 업무를 성실히 수행한다.",
            channel_intro="작업 시작합니다.",
            skills=spec.specialty,
            team=team,
            channels=(channel, "general"),
            personality_id=personality_id,
            rank=4,
        )
        register_dynamic_persona(agent.name, persona)

    async def fire(self, agent_id: str, reason: str = "") -> bool:
        """에이전트 해고 (Soft-Delete: 레코드 보존, 비활성화)

        Args:
            agent_id: 에이전트 ID
            reason: 해고 사유

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

        if not record.is_active:
            logger.warning(f"[HR] 이미 해고된 에이전트: {agent_id}")
            return False

        # Soft-Delete: 비활성화만 (레코드 보존)
        record.is_active = False
        record.fired_at = datetime.now()
        record.fire_reason = reason or "수동 해고"

        # 부모에서 제거
        if record.parent_id and record.parent_id in self._records:
            parent = self._records[record.parent_id]
            if agent_id in parent.children_ids:
                parent.children_ids.remove(agent_id)

        # 자식들도 해고 (cascade)
        for child_id in list(record.children_ids):
            await self.fire(child_id, reason=f"부모({record.name}) 해고로 인한 연쇄 해고")

        # 에이전트 인스턴스 제거 (레코드는 보존)
        self._agents.pop(agent_id, None)

        # 동적 페르소나 제거
        from jinxus.agents.personas import unregister_dynamic_persona
        unregister_dynamic_persona(record.name)

        logger.info(f"[HR] 에이전트 해고 (soft-delete): {record.name} — 사유: {record.fire_reason}")

        return True

    async def rehire(self, agent_id: str) -> Optional[AgentRecord]:
        """해고된 에이전트 재고용

        Args:
            agent_id: 재고용할 에이전트 ID

        Returns:
            재고용된 AgentRecord 또는 None
        """
        record = self._records.get(agent_id)
        if not record:
            logger.warning(f"[HR] 에이전트 없음: {agent_id}")
            return None

        if record.is_active:
            logger.warning(f"[HR] 이미 활성 상태: {agent_id}")
            return None

        # 재활성화
        record.is_active = True
        record.fired_at = None
        record.fire_reason = None

        # 부모에 자식 재등록
        if record.parent_id and record.parent_id in self._records:
            parent = self._records[record.parent_id]
            if agent_id not in parent.children_ids:
                parent.children_ids.append(agent_id)

        logger.info(f"[HR] 에이전트 재고용: {record.name}")

        return record

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

    def get_fired_records(self) -> List[AgentRecord]:
        """해고된 에이전트 레코드 조회"""
        return [r for r in self._records.values() if not r.is_active and r.fired_at]

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
                "name": f"JX_{key.upper().replace(' ', '_')}",
                "description": traits.get("focus", ""),
                "capabilities": traits.get("strengths", []),
            }
            for key, traits in AgentFactory._SPECIALTY_TRAITS.items()
        ]


def get_hr_manager() -> HRManager:
    """HR 매니저 싱글톤 반환"""
    return HRManager.get_instance()
