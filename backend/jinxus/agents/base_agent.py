"""JINXUS 에이전트 기반 클래스"""
from abc import ABC, abstractmethod
from typing import TypedDict, Optional
from datetime import datetime
import re
import uuid
import logging

from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_tools_for_agent
from jinxus.agents.state_tracker import get_state_tracker, GraphNode
from jinxus.core.context_guard import get_context_guard, BudgetStatus
from jinxus.core.checkpointer import create_checkpointer

logger = logging.getLogger(__name__)


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

    # Resilience (Guard/Post 노드용)
    iteration_count: int
    completion_signal: Optional[str]  # None | "TASK_COMPLETE" | "BLOCKED" | "ERROR"
    completion_reason: Optional[str]

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
    [receive] → [plan] → [pre_execute_guard] → [execute] → [post_execute] → [evaluate]
        → [reflect] → [memory_write] → [return_result]
    """

    name: str = "base_agent"
    description: str = "기본 에이전트"
    max_retries: int = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._progress_callback = None  # JINXUS_CORE에서 주입
        self._tools = get_tools_for_agent(self.name)
        self._prompt_version = "v1.0"
        self._graph = self._build_graph()
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

    def _build_graph(self) -> StateGraph:
        """LangGraph 그래프 구축

        노드 흐름:
        receive → plan → pre_execute_guard → execute → post_execute → evaluate
                                                                        ↓
                                            retry: execute ← evaluate (조건 분기)
                                            continue: reflect → memory_write → return_result → END
        """
        graph = StateGraph(AgentState)

        # 노드 추가
        graph.add_node("receive", self._receive_node)
        graph.add_node("plan", self._plan_node)
        graph.add_node("pre_execute_guard", self._pre_execute_guard)
        graph.add_node("execute", self._execute_node)
        graph.add_node("post_execute", self._post_execute)
        graph.add_node("evaluate", self._evaluate_node)
        graph.add_node("reflect", self._reflect_node)
        graph.add_node("memory_write", self._memory_write_node)
        graph.add_node("return_result", self._return_result_node)

        # 엣지 추가: plan → pre_execute_guard → execute → post_execute → evaluate
        graph.set_entry_point("receive")
        graph.add_edge("receive", "plan")
        graph.add_edge("plan", "pre_execute_guard")
        graph.add_edge("pre_execute_guard", "execute")
        graph.add_edge("execute", "post_execute")
        graph.add_edge("post_execute", "evaluate")

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

        # 체크포인터 주입 — 그래프 상태 영속화 (B-4)
        settings = get_settings()
        checkpointer = create_checkpointer(
            storage_path=settings.data_dir / "checkpoints",
            persistent=True,
        )
        return graph.compile(checkpointer=checkpointer)

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

        # CORE에서 전달받은 memory_context가 있으면 재검색 스킵
        existing_context = state.get("memory_context")
        if existing_context:
            await self._report_progress("작업 수신 (CORE 컨텍스트 사용)")
            memory_context = existing_context
        else:
            await self._report_progress("작업 수신, 관련 기억 검색 중...")
            memory_context = self._memory.search_long_term(
                agent_name=self.name,
                query=state["instruction"],
                limit=5,
            )

        return {
            **state,
            "memory_context": memory_context,
            "created_at": datetime.now().isoformat(),
            "agent_name": self.name,
            "prompt_version": self._prompt_version,
            "retry_count": 0,
            "tool_results": [],
        }

    async def _plan_node(self, state: AgentState) -> AgentState:
        """실행 계획 수립"""
        self._state_tracker.update_node(self.name, GraphNode.PLAN)
        await self._report_progress(f"실행 계획 수립 중... (도구: {', '.join(list(self._tools.keys())[:5]) if self._tools else '없음'})")
        system_prompt = self._get_system_prompt()
        plan_prompt = self._get_plan_prompt(state)

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": plan_prompt}],
        )

        plan_text = response.content[0].text
        await self._report_progress(f"계획 수립 완료 → 실행 단계 진입")

        # 간단한 계획 파싱 (실제로는 더 정교하게)
        plan = [{"step": 1, "action": plan_text}]

        return {
            **state,
            "plan": plan,
            "current_step": 0,
        }

    # ===== Resilience 노드 (Guard / Post) =====

    # 완료 신호 감지용 정규식 패턴
    _COMPLETION_PATTERNS = [
        re.compile(r"\[TASK_COMPLETE\]"),
        re.compile(r"\[BLOCKED:\s*(.+?)\]"),
        re.compile(r"\[ERROR:\s*(.+?)\]"),
    ]

    async def _pre_execute_guard(self, state: AgentState) -> AgentState:
        """execute 노드 실행 전 컨텍스트 윈도우 예산 체크 + 컴팩션

        BLOCK/OVERFLOW 상태이면 에러 메시지를 output에 설정하고
        success=False로 마킹하여 evaluate에서 조기 종료되도록 한다.
        """
        self._state_tracker.update_node(self.name, GraphNode.PRE_EXECUTE_GUARD)
        await self._report_progress("컨텍스트 예산 검사 중...")

        guard = get_context_guard(self._model)

        # context 필드의 메시지를 기반으로 예산 체크 + 자동 컴팩션
        messages = state.get("context", [])
        compacted_messages, budget = guard.check_and_compact(messages, auto_compact=True)

        if budget.status in (BudgetStatus.BLOCK, BudgetStatus.OVERFLOW):
            # 컨텍스트 예산 초과 — 실행 차단
            logger.warning(
                "[%s] 컨텍스트 예산 초과 (%.1f%%), 실행 차단",
                self.name, budget.usage_percent,
            )
            return {
                **state,
                "context": compacted_messages,
                "success": False,
                "failure_reason": (
                    f"컨텍스트 예산 초과 ({budget.status.value}): "
                    f"{budget.used_tokens}/{budget.max_tokens} 토큰 "
                    f"({budget.usage_percent:.1f}%)"
                ),
                "output": (
                    f"[GUARD] 컨텍스트 윈도우 예산 초과로 실행이 차단되었습니다. "
                    f"({budget.usage_percent:.1f}% 사용)"
                ),
            }

        if budget.status == BudgetStatus.WARN:
            logger.info(
                "[%s] 컨텍스트 예산 경고 (%.1f%%)", self.name, budget.usage_percent,
            )

        return {
            **state,
            "context": compacted_messages,
        }

    async def _post_execute(self, state: AgentState) -> AgentState:
        """execute 노드 실행 후 후처리

        1. iteration 카운터 증가
        2. 완료 신호 감지 ([TASK_COMPLETE], [BLOCKED: reason], [ERROR: reason])
        3. 출력에서 신호 마커 제거 (사용자에게 보이지 않도록)
        """
        self._state_tracker.update_node(self.name, GraphNode.POST_EXECUTE)

        new_iteration = state.get("iteration_count", 0) + 1
        output = state.get("output", "")

        # 완료 신호 감지
        completion_signal = None
        completion_reason = None

        for pattern in self._COMPLETION_PATTERNS:
            match = pattern.search(output)
            if match:
                marker = match.group(0)
                if "TASK_COMPLETE" in marker:
                    completion_signal = "TASK_COMPLETE"
                    completion_reason = "작업 완료"
                    logger.info("[%s] 완료 신호 감지: TASK_COMPLETE", self.name)
                elif "BLOCKED:" in marker:
                    completion_signal = "BLOCKED"
                    completion_reason = match.group(1).strip()
                    logger.warning("[%s] 블록 신호 감지: %s", self.name, completion_reason)
                elif "ERROR:" in marker:
                    completion_signal = "ERROR"
                    completion_reason = match.group(1).strip()
                    logger.error("[%s] 에러 신호 감지: %s", self.name, completion_reason)
                break  # 첫 번째 매칭된 신호만 처리

        # 출력에서 신호 마커 제거
        cleaned_output = output
        for pattern in self._COMPLETION_PATTERNS:
            cleaned_output = pattern.sub("", cleaned_output)
        cleaned_output = cleaned_output.strip()

        result = {
            **state,
            "iteration_count": new_iteration,
            "output": cleaned_output,
            "completion_signal": completion_signal,
            "completion_reason": completion_reason,
        }

        # 완료 신호에 따른 상태 업데이트
        if completion_signal == "TASK_COMPLETE":
            result["success"] = True
        elif completion_signal in ("BLOCKED", "ERROR"):
            result["success"] = False
            result["failure_reason"] = f"[{completion_signal}] {completion_reason}"

        return result

    # ===== 실행 노드 (서브클래스 구현) =====

    @abstractmethod
    async def _execute_node(self, state: AgentState) -> AgentState:
        """실행 (서브클래스에서 구현)"""
        pass

    async def _evaluate_node(self, state: AgentState) -> AgentState:
        """실행 결과 평가

        post_execute에서 completion_signal로 이미 성공/실패가 결정된 경우 재평가 건너뜀.
        """
        self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

        # post_execute에서 이미 결정된 경우 → 그대로 통과 (API 호출 절약)
        if state.get("success") is True:
            await self._report_progress("실행 성공 확인 → 평가 생략")
            return {**state, "success_score": state.get("success_score", 0.9)}

        tool_results = state.get("tool_results", [])
        tool_count = len(tool_results)
        await self._report_progress(f"실행 결과 평가 중... (도구 결과 {tool_count}개)")

        if not tool_results:
            return {
                **state,
                "success": False,
                "success_score": 0.0,
                "failure_reason": state.get("failure_reason", "No tool results"),
                "retry_count": state["retry_count"] + 1,
            }

        # 모든 도구가 성공했는지 확인
        all_success = all(r.get("success", False) for r in tool_results)
        avg_score = (
            sum(r.get("score", 0.5) for r in tool_results) / len(tool_results)
            if tool_results
            else 0.0
        )

        failure_reason = state.get("failure_reason")
        if not all_success and not failure_reason:
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
        """작업 반성 및 개선점 도출

        최적화: 명확한 실패(score < 0.5)는 반성 스킵 — 실패 원인이 이미 명확하므로
        API 호출 낭비 방지. 성공 또는 아슬아슬한 실패만 반성.
        """
        self._state_tracker.update_node(self.name, GraphNode.REFLECT)

        # 명확한 실패 → 반성 스킵 (API 호출 절약)
        score = state.get("success_score", 0.0)
        if not state.get("success") and score < 0.5:
            await self._report_progress(f"명확한 실패 (점수: {score:.1f}) → 반성 생략")
            return {
                **state,
                "reflection": state.get("failure_reason", "실행 실패"),
                "improvement_hint": "",
            }

        status = "성공" if state["success"] else "실패"
        await self._report_progress(f"작업 반성 중... (결과: {status}, 점수: {score:.1f})")
        reflection_prompt = f"""작업 결과를 분석하고 반성해줘.

## 원본 지시
{state['instruction']}

## 실행 결과
성공: {state['success']}
점수: {score}
실패 이유: {state.get('failure_reason', 'N/A')}

## 요청
1. 잘한 점과 부족한 점을 분석해줘.
2. 다음에 개선할 점을 제안해줘.

JSON으로 응답해:
{{"reflection": "...", "improvement_hint": "..."}}
"""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=512,
            messages=[{"role": "user", "content": reflection_prompt}],
        )

        reflection_text = response.content[0].text

        # JSON 파싱 시도
        reflection = reflection_text
        improvement_hint = ""
        try:
            import json
            json_text = reflection_text
            if "```" in json_text:
                json_text = json_text.split("```")[1]
                if json_text.startswith("json"):
                    json_text = json_text[4:]
            parsed = json.loads(json_text.strip())
            reflection = parsed.get("reflection", reflection_text)
            improvement_hint = parsed.get("improvement_hint", "")
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

        return {
            **state,
            "reflection": reflection,
            "improvement_hint": improvement_hint,
        }

    async def _memory_write_node(self, state: AgentState) -> AgentState:
        """장기기억에 작업 결과 저장"""
        self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)
        await self._report_progress("기억 저장 중...")
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
        await self._report_progress("결과 반환")
        duration_ms = int(
            (datetime.now() - datetime.fromisoformat(state["created_at"])).total_seconds() * 1000
        )

        return {
            **state,
            "duration_ms": duration_ms,
        }

    # ===== 진행 보고 =====

    async def _report_progress(self, detail: str):
        """SSE progress_callback이 설정되어 있으면 호출"""
        if hasattr(self, '_progress_callback') and self._progress_callback:
            try:
                await self._progress_callback(f"[{self.name}] {detail}")
            except Exception:
                pass  # 콜백 실패는 무시

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

    # ===== 협업 인터페이스 =====

    async def request_help(
        self,
        to_agent: str,
        instruction: str,
        context: list = None,
        collab_session_id: Optional[str] = None,
    ) -> dict:
        """다른 에이전트에게 도움 요청 (협업)

        예: JX_RESEARCHER가 코드 작성이 필요할 때 JX_CODER에게 요청
            result = await self.request_help("JX_CODER", "이 코드 작성해줘")

        Args:
            to_agent: 도움을 줄 에이전트 이름
            instruction: 요청 내용
            context: 추가 컨텍스트
            collab_session_id: 협업 세션 ID

        Returns:
            AgentResult 딕셔너리
        """
        from jinxus.core.collaboration import get_collaborator
        collaborator = get_collaborator()
        return await collaborator.request_help(
            from_agent=self.name,
            to_agent=to_agent,
            instruction=instruction,
            context=context,
            collab_session_id=collab_session_id,
        )

    # ===== 공개 인터페이스 =====

    async def run(self, instruction: str, context: list[dict] = None, memory_context: list = None) -> dict:
        """에이전트 실행

        Args:
            instruction: JINXUS_CORE로부터 받은 지시
            context: 추가 컨텍스트 (이전 에이전트 결과 등)
            memory_context: CORE에서 전달된 메모리 컨텍스트 (있으면 재검색 스킵)

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
            "iteration_count": 0,
            "completion_signal": None,
            "completion_reason": None,
            "agent_name": self.name,
            "prompt_version": self._prompt_version,
            "memory_context": memory_context or [],
            "duration_ms": 0,
            "created_at": "",
        }

        # 그래프 실행 — thread_id로 체크포인트 추적 (B-4)
        config = {"configurable": {"thread_id": initial_state["task_id"]}}
        final_state = await self._graph.ainvoke(initial_state, config=config)

        # tool_results에서 도구 이름 추출
        tool_calls = []
        for tr in final_state.get("tool_results", []):
            names = tr.get("tool_calls", [])
            if isinstance(names, list):
                tool_calls.extend(names)

        return {
            "task_id": final_state["task_id"],
            "agent_name": self.name,
            "success": final_state["success"],
            "success_score": final_state["success_score"],
            "output": final_state["output"],
            "failure_reason": final_state.get("failure_reason"),
            "duration_ms": final_state["duration_ms"],
            "tool_calls": tool_calls,
        }
