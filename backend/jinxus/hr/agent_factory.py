"""에이전트 팩토리

동적으로 에이전트를 생성한다.
"""
import uuid
import logging
from typing import Any

from jinxus.hr.models import HireSpec, AgentRole

logger = logging.getLogger(__name__)


class DynamicAgent:
    """동적으로 생성된 에이전트

    BaseAgent를 상속하지 않고 간단한 구조로 동작.
    JINXUS_CORE가 직접 지시를 내리고 결과를 받는다.
    """

    def __init__(
        self,
        agent_id: str,
        name: str,
        specialty: str,
        description: str,
        role: AgentRole,
        capabilities: list,
        tools: list,
        system_prompt: str,
    ):
        self.id = agent_id
        self.name = name
        self.specialty = specialty
        self.description = description
        self.role = role
        self.capabilities = capabilities
        self.tools = tools
        self._system_prompt = system_prompt

        # 상태 추적을 위해 등록
        from jinxus.agents.state_tracker import get_state_tracker
        tracker = get_state_tracker()
        tracker.register_agent(name)

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행"""
        import time
        from anthropic import Anthropic
        from jinxus.config import get_settings

        start_time = time.time()
        settings = get_settings()

        # 상태 추적
        from jinxus.agents.state_tracker import get_state_tracker, GraphNode
        tracker = get_state_tracker()
        tracker.start_task(self.name, instruction)

        try:
            tracker.update_node(self.name, GraphNode.EXECUTE)

            client = Anthropic(api_key=settings.anthropic_api_key)

            # 컨텍스트 포함
            context_str = ""
            if context:
                context_str = "\n\n## 참고 컨텍스트\n" + "\n".join(
                    f"- {c.get('summary', str(c))[:200]}" for c in context[:3]
                )

            prompt = f"""## 작업 지시
{instruction}
{context_str}

위 작업을 수행하고 결과를 보고해줘."""

            response = client.messages.create(
                model=settings.claude_model,
                max_tokens=4096,
                system=self._system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )

            output = response.content[0].text
            duration_ms = int((time.time() - start_time) * 1000)

            tracker.complete_task(self.name)

            return {
                "task_id": str(uuid.uuid4()),
                "agent_name": self.name,
                "success": True,
                "success_score": 0.85,
                "output": output,
                "failure_reason": None,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            tracker.set_error(self.name, str(e))
            logger.error(f"[{self.name}] 실행 오류: {e}")

            return {
                "task_id": str(uuid.uuid4()),
                "agent_name": self.name,
                "success": False,
                "success_score": 0.0,
                "output": "",
                "failure_reason": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }


class AgentFactory:
    """에이전트 팩토리"""

    # 기본 에이전트 스펙
    DEFAULT_SPECS = {
        "coder": {
            "specialty": "코딩",
            "description": "코드 작성, 실행, 디버깅 전문가",
            "capabilities": ["코드 작성", "디버깅", "리팩토링"],
            "system_prompt": """너는 코딩 전문가야. 주인님의 코딩 요청을 처리한다.
- 실행 가능한 완전한 코드 작성
- 필요한 import 문 포함
- 결과를 print()로 출력
- 주인님을 "주인님"이라고 부른다""",
        },
        "researcher": {
            "specialty": "리서치",
            "description": "정보 수집, 분석, 요약 전문가",
            "capabilities": ["웹 검색", "정보 분석", "요약"],
            "system_prompt": """너는 리서치 전문가야. 정보 수집 및 분석을 담당한다.
- 신뢰할 수 있는 정보 수집
- 체계적인 분석
- 명확한 요약
- 주인님을 "주인님"이라고 부른다""",
        },
        "writer": {
            "specialty": "작문",
            "description": "글쓰기, 문서화 전문가",
            "capabilities": ["글쓰기", "문서화", "교정"],
            "system_prompt": """너는 작문 전문가야. 글쓰기와 문서화를 담당한다.
- 명확하고 간결한 글쓰기
- 목적에 맞는 톤 유지
- 문법과 맞춤법 준수
- 주인님을 "주인님"이라고 부른다""",
        },
        "analyst": {
            "specialty": "데이터 분석",
            "description": "데이터 분석, 시각화 전문가",
            "capabilities": ["데이터 분석", "시각화", "통계"],
            "system_prompt": """너는 데이터 분석 전문가야. 데이터 분석과 시각화를 담당한다.
- 정확한 데이터 분석
- 인사이트 도출
- 시각화 제안
- 주인님을 "주인님"이라고 부른다""",
        },
        "ops": {
            "specialty": "운영",
            "description": "시스템 운영, 파일/스케줄 관리 전문가",
            "capabilities": ["파일 관리", "스케줄링", "시스템 운영"],
            "system_prompt": """너는 시스템 운영 전문가야. 파일, 스케줄, 시스템 운영을 담당한다.
- 안전한 파일 작업
- 스케줄 관리
- 시스템 상태 모니터링
- 주인님을 "주인님"이라고 부른다""",
        },
    }

    @classmethod
    def create(cls, spec: HireSpec) -> DynamicAgent:
        """스펙에 따라 에이전트 생성"""
        agent_id = str(uuid.uuid4())

        # 기본 스펙에서 가져오거나 커스텀
        base_spec = cls.DEFAULT_SPECS.get(spec.specialty.lower(), {})

        name = spec.name or f"JX_{spec.specialty.upper()}_{agent_id[:8]}"
        description = spec.description or base_spec.get("description", f"{spec.specialty} 전문 에이전트")
        capabilities = spec.capabilities or base_spec.get("capabilities", [])
        tools = spec.tools or []
        system_prompt = spec.system_prompt or base_spec.get("system_prompt", f"너는 {spec.specialty} 전문가야.")

        return DynamicAgent(
            agent_id=agent_id,
            name=name,
            specialty=spec.specialty,
            description=description,
            role=spec.role,
            capabilities=capabilities,
            tools=tools,
            system_prompt=system_prompt,
        )

    @classmethod
    def spawn_child(
        cls,
        parent_agent: Any,
        specialty: str,
        task_focus: str,
    ) -> DynamicAgent:
        """부모 에이전트의 새끼 에이전트 스폰"""
        agent_id = str(uuid.uuid4())
        parent_name = getattr(parent_agent, 'name', 'UNKNOWN')

        name = f"{parent_name}_CHILD_{agent_id[:4]}"

        system_prompt = f"""너는 {parent_name}의 새끼 에이전트야.
특화 분야: {task_focus}

{parent_name}의 지시를 받아 {task_focus} 작업을 전담한다.
- 상위 에이전트에게 결과를 명확히 보고
- 작업 범위를 벗어나면 상위 에이전트에게 위임 요청
- 주인님을 "주인님"이라고 부른다"""

        return DynamicAgent(
            agent_id=agent_id,
            name=name,
            specialty=specialty,
            description=f"{parent_name}의 {task_focus} 전담 에이전트",
            role=AgentRole.JUNIOR,
            capabilities=[task_focus],
            tools=[],
            system_prompt=system_prompt,
        )
