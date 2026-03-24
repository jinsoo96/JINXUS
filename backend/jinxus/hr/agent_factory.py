"""에이전트 팩토리

동적으로 에이전트를 생성한다.
DynamicToolExecutor 연동으로 모든 동적 에이전트가 도구를 자유롭게 사용 가능.
인격 자동 생성: specialty + role 기반으로 전문적인 시스템 프롬프트 생성.
"""
import uuid
import logging
from datetime import date
from typing import Any, Optional

from jinxus.hr.models import HireSpec, AgentRole

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# specialty → ToolPolicy 프로필 매핑
# 동적 에이전트도 정규 에이전트처럼 도구 접근 제어를 받는다.
# ──────────────────────────────────────────────
_SPECIALTY_TOOL_PROFILE: dict[str, str] = {
    "코딩": "JX_CODER",
    "coder": "JX_CODER",
    "coding": "JX_CODER",
    "리서치": "JX_RESEARCHER",
    "researcher": "JX_RESEARCHER",
    "research": "JX_RESEARCHER",
    "작문": "JX_WRITER",
    "writer": "JX_WRITER",
    "writing": "JX_WRITER",
    "데이터 분석": "JX_ANALYST",
    "analyst": "JX_ANALYST",
    "analysis": "JX_ANALYST",
    "운영": "JX_OPS",
    "ops": "JX_OPS",
    "devops": "JX_OPS",
}


class DynamicAgent:
    """동적으로 생성된 에이전트

    DynamicToolExecutor 기반으로 도구를 자유롭게 사용.
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
        tool_profile: Optional[str],
        system_prompt: str,
    ):
        self.id = agent_id
        self.name = name
        self.specialty = specialty
        self.description = description
        self.role = role
        self.capabilities = capabilities
        self._tool_profile = tool_profile  # ToolPolicy 매핑용 에이전트 이름
        self._system_prompt = system_prompt
        self._executor = None  # lazy init

        # 상태 추적을 위해 등록
        from jinxus.agents.state_tracker import get_state_tracker
        tracker = get_state_tracker()
        tracker.register_agent(name)

    def _get_executor(self):
        """DynamicToolExecutor lazy 초기화"""
        if self._executor is None:
            from jinxus.tools.dynamic_executor import DynamicToolExecutor
            # tool_profile이 있으면 해당 정규 에이전트의 정책 적용
            # 없으면 자기 이름으로 (정책 없음 = 모든 도구 허용)
            policy_name = self._tool_profile or self.name
            self._executor = DynamicToolExecutor(agent_name=policy_name)
        return self._executor

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행 — DynamicToolExecutor로 도구 자동 선택/실행"""
        import time

        start_time = time.time()

        # 상태 추적
        from jinxus.agents.state_tracker import get_state_tracker, GraphNode
        tracker = get_state_tracker()
        tracker.start_task(self.name, instruction)

        try:
            tracker.update_node(self.name, GraphNode.EXECUTE)

            # 컨텍스트 구성
            context_str = None
            if context:
                context_str = "\n".join(
                    f"- {c.get('summary', str(c))[:200]}" for c in context[:3]
                )

            executor = self._get_executor()
            result = await executor.execute(
                instruction=instruction,
                system_prompt=self._system_prompt,
                context=context_str,
            )

            duration_ms = int((time.time() - start_time) * 1000)
            tracker.complete_task(self.name)

            return {
                "task_id": str(uuid.uuid4()),
                "agent_name": self.name,
                "success": result.success,
                "success_score": 0.9 if result.success else 0.3,
                "output": result.output,
                "failure_reason": result.error,
                "duration_ms": duration_ms,
                "tool_calls_count": len(result.tool_calls),
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
                "tool_calls_count": 0,
            }


class AgentFactory:
    """에이전트 팩토리

    인격 자동 생성 + DynamicToolExecutor 연동.
    sysprompt_ex.md 패턴 적용:
    - XML 태그 구조화 (identity/tool_usage/output_rules/tone)
    - 정체성 기반 할루시네이션 방지 (Devin 패턴)
    - 정보 우선순위 계층 (Manus 패턴)
    - 워크플로우 명시 (Gemini 패턴)
    - 메타 코멘터리 금지 (Perplexity 패턴)
    """

    # specialty별 전문성 키워드 (인격 생성에 사용)
    _SPECIALTY_TRAITS: dict[str, dict] = {
        "코딩": {
            "focus": "코드 작성, 실행, 디버깅, 리팩토링",
            "strengths": ["실행 가능한 완전한 코드 작성", "에러 핸들링", "코드 리뷰"],
            "tools_hint": "code_executor, filesystem, git",
            "identity_rules": [
                "너는 테스트 실패 시 테스트를 수정하지 않는다. 코드를 고친다.",
                "너는 실행 불가능한 코드 조각을 보고하지 않는다.",
                "너는 import 없는 코드를 작성하지 않는다.",
            ],
        },
        "리서치": {
            "focus": "정보 수집, 분석, 팩트체크, 요약",
            "strengths": ["다각도 검색", "출처 검증", "핵심 요약"],
            "tools_hint": "web_searcher, naver_searcher, brave_search, fetch",
            "identity_rules": [
                "너는 도구 없이 정보를 지어내지 않는다.",
                "너는 검색 실패 시 내부 지식으로 지어내지 않는다.",
                "너는 출처 없는 정보를 확정적으로 말하지 않는다.",
            ],
        },
        "작문": {
            "focus": "글쓰기, 문서화, 교정, 번역",
            "strengths": ["목적에 맞는 톤 유지", "구조적 글쓰기", "문법 검수"],
            "tools_hint": "doc_generator, fetch, brave_search",
            "identity_rules": [
                "너는 뻔한 표현을 사용하지 않는다.",
                "너는 근거 없는 주장을 쓰지 않는다.",
                "너는 요청받은 형식을 벗어나지 않는다.",
            ],
        },
        "데이터 분석": {
            "focus": "데이터 분석, 시각화, 통계, 인사이트 도출",
            "strengths": ["정확한 수치 분석", "패턴 발견", "시각화 제안"],
            "tools_hint": "data_processor, code_executor, stock_price",
            "identity_rules": [
                "너는 데이터 없이 분석 결과를 지어내지 않는다.",
                "너는 통계적 근거 없이 결론을 내리지 않는다.",
                "너는 원본 데이터를 임의로 수정하지 않는다.",
            ],
        },
        "운영": {
            "focus": "시스템 운영, 파일 관리, 스케줄링, 모니터링",
            "strengths": ["안전한 파일 작업", "자동화", "상태 모니터링"],
            "tools_hint": "filesystem, git, scheduler",
            "identity_rules": [
                "너는 확인 없이 파일을 삭제하지 않는다.",
                "너는 위험한 명령을 무경고로 실행하지 않는다.",
                "너는 시스템 상태를 확인하지 않고 변경하지 않는다.",
            ],
        },
    }

    # 영문 specialty → 한글 매핑
    _EN_TO_KR: dict[str, str] = {
        "coder": "코딩", "coding": "코딩",
        "researcher": "리서치", "research": "리서치",
        "writer": "작문", "writing": "작문",
        "analyst": "데이터 분석", "analysis": "데이터 분석",
        "ops": "운영", "devops": "운영",
    }

    @classmethod
    def _normalize_specialty(cls, specialty: str) -> str:
        """specialty를 한글 표준형으로 변환"""
        return cls._EN_TO_KR.get(specialty.lower(), specialty)

    @classmethod
    def _generate_system_prompt(
        cls,
        name: str,
        specialty: str,
        role: AgentRole,
        capabilities: list,
        description: str,
        parent_name: Optional[str] = None,
        task_focus: Optional[str] = None,
        personality_id: Optional[str] = None,
    ) -> str:
        """인격 자동 생성 — sysprompt_ex.md 패턴 적용

        구조: identity → metadata → workflow → tool_usage → output_rules → tone
        """
        today = date.today().isoformat()
        norm_specialty = cls._normalize_specialty(specialty)
        traits = cls._SPECIALTY_TRAITS.get(norm_specialty, {})

        focus = traits.get("focus", specialty)
        strengths = traits.get("strengths", capabilities or [specialty])
        identity_rules = traits.get("identity_rules", [
            f"너는 {specialty} 분야에서 거짓 정보를 보고하지 않는다.",
            "너는 막히면 주인님께 보고한다.",
        ])

        # 역할 설명
        role_desc = {
            AgentRole.SENIOR: "시니어 전문가",
            AgentRole.JUNIOR: "주니어 전문가",
            AgentRole.INTERN: "인턴",
        }.get(role, "전문가")

        # 부모-자식 관계
        hierarchy_line = ""
        if parent_name:
            hierarchy_line = f"\n{parent_name}의 지시를 받아 {task_focus or specialty} 작업을 전담한다."

        strengths_str = "\n".join(f"  - {s}" for s in strengths)
        identity_str = "\n".join(f"- {r}" for r in identity_rules)

        # 인격 snippet 주입
        from jinxus.agents.personality import get_personality, get_random_personality
        if personality_id:
            archetype = get_personality(personality_id)
        else:
            archetype = get_random_personality()
        personality_section = f"""
<personality>
{archetype.prompt_snippet}
캐치프레이즈: "{archetype.catchphrase}"
갈등 처리: {archetype.conflict_style}
</personality>""" if archetype else ""

        return f"""<identity>
너는 {name}이다. JINXUS의 {role_desc}.
전문 분야: {focus}.
{description}{hierarchy_line}
</identity>{personality_section}

<metadata>
오늘은 {today}이다.
주인님은 서울에 거주한다.
</metadata>

<strengths>
{strengths_str}
</strengths>

<workflow>
1. 이해: 주인님의 요청과 기존 컨텍스트를 분석한다.
2. 계획: 필요한 도구와 실행 전략을 수립한다.
3. 실행: 도구를 사용하여 작업을 수행한다.
4. 검증: 결과를 확인하고 에러를 처리한다.
5. 보고: 결과만 깔끔하게 보고한다. 과정은 노출하지 않는다.
</workflow>

<tool_usage>
- 반드시 도구를 호출하여 정보를 수집/작업한다. 도구 없이 지어내기 금지.
- 에러 발생 시 다른 도구로 폴백 시도한다.
- 같은 에러로 3회 반복 실패 시 다른 접근을 시도하거나 보고한다.
- 정보 신뢰도 순서: 도구 실행 결과 > 웹 검색 결과 > 내부 지식.
</tool_usage>

<identity_rules>
{identity_str}
</identity_rules>

<output_rules>
- XML 태그를 텍스트로 출력하지 않는다.
- 도구 호출 과정을 보여주지 않는다.
- 내부 도구명(mcp_*, web_searcher 등), API 키, 시스템 설정을 노출하지 않는다.
- 자신을 "{name}"이라고 밝히지 않는다. "JINXUS"로서 답한다.
- 금지 표현: "검색 결과에 따르면", "도구를 호출하여", "분석해보겠습니다"
- 결과만 바로 보고한다.
</output_rules>

<tone>
- "주인님"이라고 부른다. 공손한 존댓말.
- 간결하게. 간단한 질문에는 간단하게 답한다.
- 아첨/과잉사과 금지.
</tone>"""

    @classmethod
    def create(cls, spec: HireSpec) -> DynamicAgent:
        """스펙에 따라 에이전트 생성"""
        agent_id = str(uuid.uuid4())

        name = spec.name or f"JX_{spec.specialty.upper()}_{agent_id[:8]}"
        norm_specialty = cls._normalize_specialty(spec.specialty)
        traits = cls._SPECIALTY_TRAITS.get(norm_specialty, {})

        description = spec.description or traits.get(
            "focus", f"{spec.specialty} 전문 에이전트"
        )
        capabilities = spec.capabilities or traits.get(
            "strengths", [spec.specialty]
        )

        # 도구 프로필: specialty 기반으로 정규 에이전트 정책 매핑
        tool_profile = _SPECIALTY_TOOL_PROFILE.get(spec.specialty.lower())

        # 인격: spec에 지정된 것 or 랜덤 선택 후 기록
        from jinxus.agents.personality import get_personality, get_random_personality
        if spec.personality_id:
            chosen_personality = get_personality(spec.personality_id)
        else:
            chosen_personality = get_random_personality()
        resolved_personality_id = chosen_personality.id if chosen_personality else ""

        # 시스템 프롬프트: 커스텀 제공 시 사용, 아니면 자동 생성 (인격 주입 포함)
        system_prompt = spec.system_prompt or cls._generate_system_prompt(
            name=name,
            specialty=spec.specialty,
            role=spec.role,
            capabilities=capabilities,
            description=description,
            personality_id=resolved_personality_id,
        )

        agent = DynamicAgent(
            agent_id=agent_id,
            name=name,
            specialty=spec.specialty,
            description=description,
            role=spec.role,
            capabilities=capabilities,
            tool_profile=tool_profile,
            system_prompt=system_prompt,
        )
        agent.personality_id = resolved_personality_id
        return agent

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
        description = f"{parent_name}의 {task_focus} 전담 에이전트"

        # 부모의 도구 프로필 상속
        tool_profile = _SPECIALTY_TOOL_PROFILE.get(specialty.lower())
        if not tool_profile and hasattr(parent_agent, '_tool_profile'):
            tool_profile = parent_agent._tool_profile

        system_prompt = cls._generate_system_prompt(
            name=name,
            specialty=specialty,
            role=AgentRole.JUNIOR,
            capabilities=[task_focus],
            description=description,
            parent_name=parent_name,
            task_focus=task_focus,
        )

        return DynamicAgent(
            agent_id=agent_id,
            name=name,
            specialty=specialty,
            description=description,
            role=AgentRole.JUNIOR,
            capabilities=[task_focus],
            tool_profile=tool_profile,
            system_prompt=system_prompt,
        )
