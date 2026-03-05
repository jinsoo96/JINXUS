"""JINXUS 에이전트 기반 클래스"""
from abc import ABC, abstractmethod
from typing import TypedDict, Optional
from datetime import datetime
import uuid

from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_tools_for_agent
from jinxus.agents.state_tracker import get_state_tracker, GraphNode


class AgentState(TypedDict):
    """에이전트 공통 State 스키마"""
    # 입력 (JINXUS_CORE로부터)
    task_id: str
    instruction: str
    context: list[dict]

    # 계획
    plan: list[dict]
    current_step: int

    # 실행
    tool_results: list[dict]

    # 평가
    success: bool
    success_score: float
    failure_reason: Optional[str]
    retry_count: int

    # 반성
    reflection: str
    improvement_hint: str

    # 출력
    output: str

    # 메타
    agent_name: str
    prompt_version: str
    memory_context: list[dict]
    duration_ms: int
    created_at: str


class BaseAgent(ABC):
    """JINXUS 에이전트 추상 기반 클래스

    모든 Sub-Agent는 이 클래스를 상속받아 구현한다.
    공통 LangGraph 그래프 구조:
    [receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
    """

    name: str = "base_agent"
    description: str = "기본 에이전트"
    max_retries: int = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._tools = get_tools_for_agent(self.name)
        self._prompt_version = "v1.0"
        self._graph = self._build_graph()
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

    def _build_graph(self) -> StateGraph:
        """LangGraph 그래프 구축"""
        graph = StateGraph(AgentState)

        # 노드 추가
        graph.add_node("receive", self._receive_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("evaluate", self._evaluate_node)
        graph.add_node("reflect", self._reflect_node)
        graph.add_node("memory_write", self._memory_write_node)
        graph.add_node("return_result", self._return_result_node)

        # 엣지 추가
        graph.set_entry_point("receive")
        graph.add_edge("receive", "plan")
        graph.add_edge("plan", "execute")
        graph.add_edge("execute", "evaluate")

        # evaluate에서 조건 분기
        graph.add_conditional_edges(
            "evaluate",
            self._should_retry,
            {
                "retry": "execute",
                "continue": "reflect",
            },
        )

        graph.add_edge("reflect", "memory_write")
        graph.add_edge("memory_write", "return_result")
        graph.add_edge("return_result", END)

        return graph.compile()

    def _should_retry(self, state: AgentState) -> str:
        """재시도 여부 결정"""
        if not state["success"] and state["retry_count"] < self.max_retries:
            return "retry"
        return "continue"

    # ===== 노드 구현 =====

    async def _receive_node(self, state: AgentState) -> AgentState:
        """작업 수신 및 초기화"""
        # 상태 추적: 작업 시작
        self._state_tracker.start_task(self.name, state["instruction"])
        self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

        # 장기기억에서 유사 경험 검색
        memory_context = self._memory.search_long_term(
            agent_name=self.name,
            query=state["instruction"],
            limit=5,
        )

        return {
            **state,
            "memory_context": memory_context,
            "created_at": datetime.utcnow().isoformat(),
            "agent_name": self.name,
            "prompt_version": self._prompt_version,
            "retry_count": 0,
            "tool_results": [],
        }

    async def _plan_node(self, state: AgentState) -> AgentState:
        """실행 계획 수립"""
        self._state_tracker.update_node(self.name, GraphNode.PLAN)
        system_prompt = self._get_system_prompt()
        plan_prompt = self._get_plan_prompt(state)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": plan_prompt}],
        )

        plan_text = response.content[0].text

        # 간단한 계획 파싱 (실제로는 더 정교하게)
        plan = [{"step": 1, "action": plan_text}]

        return {
            **state,
            "plan": plan,
            "current_step": 0,
        }

    @abstractmethod
    async def _execute_node(self, state: AgentState) -> AgentState:
        """실행 (서브클래스에서 구현)"""
        pass

    async def _evaluate_node(self, state: AgentState) -> AgentState:
        """실행 결과 평가"""
        self._state_tracker.update_node(self.name, GraphNode.EVALUATE)
        # 기본 평가: 도구 결과 기반
        tool_results = state.get("tool_results", [])

        if not tool_results:
            return {
                **state,
                "success": False,
                "success_score": 0.0,
                "failure_reason": "No tool results",
                "retry_count": state["retry_count"] + 1,
            }

        # 모든 도구가 성공했는지 확인
        all_success = all(r.get("success", False) for r in tool_results)
        avg_score = (
            sum(r.get("score", 0.5) for r in tool_results) / len(tool_results)
            if tool_results
            else 0.0
        )

        failure_reason = None
        if not all_success:
            errors = [r.get("error") for r in tool_results if r.get("error")]
            failure_reason = "; ".join(errors) if errors else "Tool execution failed"

        return {
            **state,
            "success": all_success,
            "success_score": avg_score if all_success else 0.3,
            "failure_reason": failure_reason,
            "retry_count": state["retry_count"] + 1 if not all_success else state["retry_count"],
        }

    async def _reflect_node(self, state: AgentState) -> AgentState:
        """작업 반성 및 개선점 도출"""
        self._state_tracker.update_node(self.name, GraphNode.REFLECT)
        reflection_prompt = f"""
작업 결과를 분석하고 반성해줘.

## 원본 지시
{state['instruction']}

## 실행 결과
성공: {state['success']}
점수: {state['success_score']}
실패 이유: {state.get('failure_reason', 'N/A')}

## 도구 사용 결과
{state.get('tool_results', [])}

## 요청
1. 이번 작업에서 잘한 점과 부족한 점을 분석해줘.
2. 다음에 같은 유형의 작업을 할 때 개선할 점을 제안해줘.

JSON으로 응답해:
{{"reflection": "...", "improvement_hint": "..."}}
"""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": reflection_prompt}],
        )

        reflection_text = response.content[0].text

        # 간단한 파싱 (실제로는 JSON 파싱 필요)
        return {
            **state,
            "reflection": reflection_text,
            "improvement_hint": "",
        }

    async def _memory_write_node(self, state: AgentState) -> AgentState:
        """장기기억에 작업 결과 저장"""
        self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)
        # 중요도 계산
        importance_score = self._calc_importance(state)

        # 저장 여부 결정
        if self._should_save_to_longterm(state):
            self._memory.save_long_term(
                agent_name=self.name,
                task_id=state["task_id"],
                instruction=state["instruction"],
                summary=state.get("output", "")[:500],
                outcome="success" if state["success"] else "failure",
                success_score=state["success_score"],
                key_learnings=state.get("reflection", ""),
                importance_score=importance_score,
                prompt_version=self._prompt_version,
            )

        return state

    async def _return_result_node(self, state: AgentState) -> AgentState:
        """최종 결과 반환"""
        self._state_tracker.update_node(self.name, GraphNode.RETURN_RESULT)
        self._state_tracker.complete_task(self.name)
        duration_ms = int(
            (datetime.utcnow() - datetime.fromisoformat(state["created_at"])).total_seconds() * 1000
        )

        return {
            **state,
            "duration_ms": duration_ms,
        }

    # ===== 헬퍼 메서드 =====

    @abstractmethod
    def _get_system_prompt(self) -> str:
        """시스템 프롬프트 반환 (서브클래스에서 구현)"""
        pass

    def _get_plan_prompt(self, state: AgentState) -> str:
        """계획 수립 프롬프트"""
        memory_context = state.get("memory_context", [])
        context_str = "\n".join(
            f"- {m.get('summary', '')}" for m in memory_context[:3]
        )

        return f"""
## 작업 지시
{state['instruction']}

## 참고: 과거 유사 경험
{context_str if context_str else '없음'}

## 사용 가능한 도구
{', '.join(self._tools.keys()) if self._tools else '없음'}

## 요청
위 작업을 수행하기 위한 실행 계획을 세워줘.
"""

    def _should_save_to_longterm(self, state: AgentState) -> bool:
        """장기기억 저장 여부 결정"""
        # 단순 작업은 저장 안 함
        if state.get("duration_ms", 0) < 5000:
            return False

        # 반성이 비어있으면 저장 안 함
        if not state.get("reflection") or len(state.get("reflection", "")) < 20:
            return False

        return True

    def _calc_importance(self, state: AgentState) -> float:
        """중요도 점수 계산"""
        score = 0.0

        # 실패한 작업은 중요 (실패에서 배움)
        if not state["success"]:
            score += 0.4

        # 복잡한 계획일수록 중요
        if len(state.get("plan", [])) >= 3:
            score += 0.2

        # 반성이 구체적일수록 중요
        if len(state.get("reflection", "")) > 100:
            score += 0.2

        return min(score, 1.0)

    # ===== 공개 인터페이스 =====

    async def run(self, instruction: str, context: list[dict] = None) -> dict:
        """에이전트 실행

        Args:
            instruction: JINXUS_CORE로부터 받은 지시
            context: 추가 컨텍스트 (이전 에이전트 결과 등)

        Returns:
            AgentResult 딕셔너리
        """
        initial_state: AgentState = {
            "task_id": str(uuid.uuid4()),
            "instruction": instruction,
            "context": context or [],
            "plan": [],
            "current_step": 0,
            "tool_results": [],
            "success": False,
            "success_score": 0.0,
            "failure_reason": None,
            "retry_count": 0,
            "reflection": "",
            "improvement_hint": "",
            "output": "",
            "agent_name": self.name,
            "prompt_version": self._prompt_version,
            "memory_context": [],
            "duration_ms": 0,
            "created_at": "",
        }

        # 그래프 실행
        final_state = await self._graph.ainvoke(initial_state)

        return {
            "task_id": final_state["task_id"],
            "agent_name": self.name,
            "success": final_state["success"],
            "success_score": final_state["success_score"],
            "output": final_state["output"],
            "failure_reason": final_state.get("failure_reason"),
            "duration_ms": final_state["duration_ms"],
        }
