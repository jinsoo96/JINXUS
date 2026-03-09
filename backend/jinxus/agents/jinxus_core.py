"""JINXUS_CORE - 진수와 소통하는 유일한 총괄 지휘관 에이전트"""
import asyncio
import json
import logging
import uuid
import re
from typing import TypedDict, Optional, Any, Callable, Awaitable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.core.context_guard import guard_results, guard_context, get_context_guard, CompactionStrategy
from jinxus.core.session_freshness import SessionFreshness, FreshnessStatus
from jinxus.core.model_router import select_model_for_core, ModelFallbackRunner
from jinxus.tools import get_all_tools_info, WebSearcher
from jinxus.hr import get_communicator, Message, MessageType, DelegatedTask
from jinxus.agents.state_tracker import get_state_tracker, GraphNode, AgentStatus
from jinxus.core.tool_graph import get_tool_graph
from jinxus.core.workflow_executor import WorkflowExecutor


class SubTask(TypedDict):
    """서브태스크 스키마"""
    task_id: str
    assigned_agent: str
    instruction: str
    depends_on: list[str]
    priority: str


class AgentResult(TypedDict):
    """에이전트 실행 결과 스키마"""
    task_id: str
    agent_name: str
    success: bool
    success_score: float
    output: str
    failure_reason: Optional[str]
    duration_ms: int


class ManagerState(TypedDict):
    """JINXUS_CORE State 스키마"""
    # 입력
    user_input: str
    session_id: str
    user_feedback: Optional[str]

    # 분해
    subtasks: list[SubTask]
    execution_mode: str  # "parallel" | "sequential" | "mixed"

    # 디스패치
    agent_assignments: dict[str, SubTask]
    dispatch_results: list[AgentResult]

    # 취합
    aggregated_output: str

    # 반성
    reflection: str

    # 출력
    final_response: str

    # 메타
    memory_context: list[dict]
    conversation_history: list[dict]  # 최근 대화 기록 (단기기억)
    created_at: str
    completed_at: str
    task_id: str

    # 도구 워크플로우 (ToolGraph 탐색 결과)
    tool_workflow: Optional[dict]

    # 진행 보고 콜백 (백그라운드 작업용)
    progress_callback: Optional[Callable[[str], Awaitable[None]]]


class JinxusCore:
    """JINXUS_CORE - 총괄 지휘관

    진수와 소통하는 유일한 에이전트.
    명령 해석 → 분해 → 서브에이전트 하달 → 결과 취합 → 보고

    LangGraph 그래프:
    [intake] → [decompose] → [dispatch] → [aggregate] → [reflect] → [memory_write] → [respond]
    """

    name = "JINXUS_CORE"

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._memory = get_jinx_memory()
        self._agents = {}  # 에이전트 레지스트리
        self._graph = self._build_graph()

        # 모델 폴백 러너 (LLM 호출 시 자동 폴백)
        self._fallback_runner = ModelFallbackRunner()

        # 웹 검색 도구 (CORE 직접 사용)
        self._web_searcher = WebSearcher()

        # 통신 시스템 초기화
        self._communicator = get_communicator()
        self._communicator.register_agent(self.name)
        self._communicator.set_message_handler(self.name, self._handle_message)
        self._delegation_callbacks = {}  # task_id -> callback

        # 상태 추적기 (실시간 UI 연동)
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

        # 세션 신선도 평가기 (Session Freshness Policy)
        self._session_freshness = SessionFreshness()

    def register_agent(self, agent) -> None:
        """에이전트 등록"""
        self._agents[agent.name] = agent
        # 통신 시스템에도 등록
        self._communicator.register_agent(agent.name)
        # 협업 시스템에 에이전트 풀 동기화
        from jinxus.core.collaboration import get_collaborator
        get_collaborator().register_agents(self._agents)

    async def _handle_message(self, message: Message) -> None:
        """수신 메시지 처리"""
        if message.type == MessageType.TASK_RESULT:
            # 위임 작업 결과 수신
            task_id = message.content.get("task_id")
            if task_id in self._delegation_callbacks:
                callback = self._delegation_callbacks.pop(task_id)
                await callback(message.content)

        elif message.type == MessageType.INFO_SHARE:
            # 정보 공유 - 필요시 처리
            pass

    async def delegate_to_agent(
        self,
        agent_name: str,
        instruction: str,
        callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> DelegatedTask:
        """에이전트에게 작업 위임

        CORE → SENIOR → JUNIOR 체인 위임 가능

        Args:
            agent_name: 위임할 에이전트 이름
            instruction: 작업 지시
            callback: 완료 시 콜백 (optional)

        Returns:
            DelegatedTask 객체
        """
        task = await self._communicator.delegate(
            from_agent=self.name,
            to_agent=agent_name,
            instruction=instruction,
        )

        if callback:
            self._delegation_callbacks[task.id] = callback

        return task

    async def broadcast_result(self, result: Any, context: str = None) -> None:
        """모든 에이전트에게 결과 공유"""
        agent_names = list(self._agents.keys())
        await self._communicator.share_result(
            from_agent=self.name,
            to_agents=agent_names,
            result=result,
            context=context,
        )

    def _strip_agent_identity(self, text: str) -> str:
        """서브에이전트 신원 노출 제거 — JINXUS_CORE만 유저와 소통"""
        if not text:
            return text

        # 서브에이전트 자기 언급 제거
        agent_names = [
            "JX_RESEARCHER", "JX_CODER", "JX_WRITER", "JX_ANALYST",
            "JX_OPS", "JS_PERSONA", "JxResearcher", "JxCoder",
        ]
        result = text
        for name in agent_names:
            # "저 JX_RESEARCHER는" → "저는" / "제가 JX_RESEARCHER로서" → "제가"
            result = re.sub(rf'저\s+{name}[은는이가]?\s*', '저는 ', result, flags=re.IGNORECASE)
            result = re.sub(rf'제가\s+{name}[으로서]*\s*', '제가 ', result, flags=re.IGNORECASE)
            # 단독 언급 제거
            result = re.sub(rf'\b{name}\b', 'JINXUS', result, flags=re.IGNORECASE)

        # 기술적 내부 용어 제거
        technical_patterns = [
            r'mcp[_:][a-zA-Z_:]+',  # mcp__fetch__imageFetch, mcp:memory:read_graph 등
            r'claude_desktop_config\.json',
            r'Memory MCP 서버[^\n]*',
            r'MCP 서버[^\n]*연결[^\n]*',
            r'도구 목록에 없습니다[^\n]*',
        ]
        for pattern in technical_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        # 연속 빈 줄 정리
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    def _sanitize_output(self, text: str) -> str:
        """출력에서 XML 태그 및 도구 호출 형식 제거"""
        if not text:
            return text

        patterns = [
            r'<invoke[^>]*>.*?</invoke>',
            r'<parameter[^>]*>.*?</parameter>',
            r'<tool[^>]*>.*?</tool>',
            r'<invoke\s+name="[^"]*"[^>]*>',
            r'</invoke>',
            r'<parameter\s+name="[^"]*"[^>]*>',
            r'</parameter>',
        ]

        result = text
        for pattern in patterns:
            result = re.sub(pattern, '', result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    def _build_graph(self) -> StateGraph:
        """LangGraph 그래프 구축"""
        graph = StateGraph(ManagerState)

        # 노드 추가
        graph.add_node("intake", self._intake_node)
        graph.add_node("decompose", self._decompose_node)
        graph.add_node("dispatch", self._dispatch_node)
        graph.add_node("aggregate", self._aggregate_node)
        graph.add_node("reflect", self._reflect_node)
        graph.add_node("memory_write", self._memory_write_node)
        graph.add_node("respond", self._respond_node)

        # 엣지 추가
        graph.set_entry_point("intake")
        graph.add_edge("intake", "decompose")
        graph.add_edge("decompose", "dispatch")
        graph.add_edge("dispatch", "aggregate")
        graph.add_edge("aggregate", "reflect")
        graph.add_edge("reflect", "memory_write")
        graph.add_edge("memory_write", "respond")
        graph.add_edge("respond", END)

        return graph.compile()

    # ===== 노드 구현 =====

    async def _intake_node(self, state: ManagerState) -> ManagerState:
        """진수 입력 수신 및 컨텍스트 로드"""
        # 상태 추적: 작업 시작
        self._state_tracker.start_task(self.name, state["user_input"][:100])
        self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

        user_input = state["user_input"]
        session_id = state["session_id"]

        # 단기기억에서 최근 대화 로드 (컨텍스트 유지용)
        conversation_history = await self._memory.get_short_term(session_id, limit=10)

        # 장기기억에서 유사 과거 작업 검색
        memory_context = self._memory.search_all_memories(user_input, limit=5)

        # 단기기억에 현재 입력 저장
        await self._memory.save_short_term(
            session_id, "user", user_input, {"task_id": state["task_id"]}
        )

        return {
            **state,
            "memory_context": memory_context,
            "conversation_history": conversation_history,  # 대화 기록 전달
            "created_at": datetime.now().isoformat(),
        }

    async def _decompose_node(self, state: ManagerState) -> ManagerState:
        """명령을 서브태스크로 분해"""
        # 상태 추적: 계획 단계
        self._state_tracker.update_node(self.name, GraphNode.PLAN)

        user_input = state["user_input"]
        memory_context = state.get("memory_context", [])
        conversation_history = state.get("conversation_history", [])

        # 분해 프롬프트 (대화 기록 포함)
        decompose_prompt = self._get_decompose_prompt(user_input, memory_context, conversation_history)

        async def _decompose_call(model_id: str):
            response = self._client.messages.create(
                model=model_id,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": decompose_prompt}],
            )
            return response.content[0].text

        fallback_result = await self._fallback_runner.run(
            _decompose_call, select_model_for_core(user_input)
        )

        # JSON 파싱
        if fallback_result.success:
            response_text = fallback_result.result
        else:
            logger.error(f"Decompose 모든 모델 실패: {fallback_result.error}")
            response_text = '{"subtasks": [], "execution_mode": "sequential", "brief_plan": "direct_response"}'
        decomposition = self._parse_decomposition(response_text)

        subtasks = decomposition.get("subtasks", [])
        execution_mode = decomposition.get("execution_mode", "sequential")

        # 서브태스크가 없으면 직접 응답
        if not subtasks:
            subtasks = [{
                "task_id": "sub_001",
                "assigned_agent": "DIRECT",
                "instruction": user_input,
                "depends_on": [],
                "priority": "normal",
            }]

        # ToolGraph로 관련 도구 워크플로우 탐색
        tool_workflow = None
        try:
            graph = get_tool_graph()
            workflow = graph.retrieve(user_input, top_k=5)
            if workflow.nodes:
                tool_workflow = workflow.to_dict()
        except Exception as e:
            logger.warning(f"ToolGraph 탐색 실패: {e}")

        return {
            **state,
            "subtasks": subtasks,
            "execution_mode": execution_mode,
            "tool_workflow": tool_workflow,
        }

    async def _dispatch_node(self, state: ManagerState) -> ManagerState:
        """서브태스크를 에이전트에게 전달 및 실행"""
        # 상태 추적: 실행 단계
        self._state_tracker.update_node(self.name, GraphNode.EXECUTE)

        subtasks = state["subtasks"]
        execution_mode = state["execution_mode"]
        progress_callback = state.get("progress_callback")
        conversation_history = state.get("conversation_history", [])

        # 대화 맥락을 서브에이전트 instruction에 보강
        if conversation_history:
            context_summary = "\n".join(
                f"[{'주인님' if m.get('role') == 'user' else 'JINXUS'}]: {m.get('content', '')[:300]}"
                for m in conversation_history[-4:]
            )
            for task in subtasks:
                if task["assigned_agent"] != "DIRECT":
                    task["instruction"] = (
                        f"[이전 대화 맥락]\n{context_summary}\n\n"
                        f"[현재 요청]\n{task['instruction']}"
                    )

        results = []

        # 진행 보고: 작업 분해 완료
        if progress_callback:
            await progress_callback(
                f"📋 작업 분해 완료: {len(subtasks)}개 서브태스크 ({execution_mode} 모드)"
            )

        # 직접 응답 케이스
        if len(subtasks) == 1 and subtasks[0]["assigned_agent"] == "DIRECT":
            direct_response = await self._generate_direct_response(state["user_input"])
            results.append({
                "task_id": subtasks[0]["task_id"],
                "agent_name": "JINXUS_CORE",
                "success": True,
                "success_score": 0.9,
                "output": direct_response,
                "failure_reason": None,
                "duration_ms": 0,
            })
        elif execution_mode == "parallel":
            # 병렬 실행
            results = await self._execute_parallel(subtasks, progress_callback)
        else:
            # 순차 실행
            results = await self._execute_sequential(subtasks, progress_callback)

        # ToolGraph 워크플로우 보완 실행
        # 에이전트 실행이 실패했거나, tool_workflow가 추가 도구를 제안한 경우
        tool_workflow_data = state.get("tool_workflow")
        if tool_workflow_data and tool_workflow_data.get("tools"):
            failed_tasks = [r for r in results if not r.get("success")]
            if failed_tasks:
                # 실패한 작업이 있으면 ToolGraph 워크플로우로 보완 시도
                if progress_callback:
                    await progress_callback("🔄 ToolGraph 워크플로우로 보완 실행 중...")

                try:
                    graph = get_tool_graph()
                    workflow = graph.retrieve(state["user_input"], top_k=5)
                    if workflow.nodes:
                        executor = WorkflowExecutor(agent_name="JINXUS_CORE")
                        wf_result = await executor.execute(
                            workflow=workflow,
                            instruction=state["user_input"],
                            context="\n".join(
                                r.get("output", "")[:500] for r in results if r.get("success")
                            ),
                        )
                        if wf_result.success and wf_result.final_output:
                            results.append({
                                "task_id": f"wf_{state.get('task_id', 'auto')}",
                                "agent_name": "ToolGraph",
                                "success": True,
                                "success_score": 0.8,
                                "output": wf_result.final_output,
                                "failure_reason": None,
                                "duration_ms": wf_result.total_duration_ms,
                            })
                            if progress_callback:
                                await progress_callback(
                                    f"✅ ToolGraph 보완 완료: {' → '.join(s.tool_name for s in wf_result.steps)}"
                                )
                except Exception as e:
                    logger.warning(f"ToolGraph 워크플로우 실행 실패: {e}")

        # 진행 보고: 모든 에이전트 완료
        if progress_callback:
            success_count = sum(1 for r in results if r["success"])
            await progress_callback(
                f"✅ 에이전트 실행 완료: {success_count}/{len(results)} 성공"
            )

        return {
            **state,
            "dispatch_results": results,
        }

    async def _aggregate_node(self, state: ManagerState) -> ManagerState:
        """에이전트 결과 취합 (context_guard 적용)"""
        # 상태 추적: 평가 단계
        self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

        results = guard_results(state["dispatch_results"])  # 토큰 폭탄 방지
        user_input = state["user_input"]

        if len(results) == 1:
            aggregated = self._strip_agent_identity(results[0]["output"])
        else:
            # 여러 결과 통합
            aggregated = await self._aggregate_results(user_input, results)

        # XML 태그 등 불필요한 형식 제거
        clean_output = self._sanitize_output(aggregated)

        return {
            **state,
            "aggregated_output": clean_output,
        }

    async def _reflect_node(self, state: ManagerState) -> ManagerState:
        """전체 작업 반성"""
        # 상태 추적: 반성 단계
        self._state_tracker.update_node(self.name, GraphNode.REFLECT)

        results = state["dispatch_results"]

        # 각 에이전트 성능 평가
        reflection_parts = []
        for result in results:
            status = "✓" if result["success"] else "✗"
            reflection_parts.append(
                f"- {result['agent_name']}: {status} (점수: {result['success_score']:.2f})"
            )

        reflection = "\n".join(reflection_parts)

        return {
            **state,
            "reflection": reflection,
        }

    async def _memory_write_node(self, state: ManagerState) -> ManagerState:
        """장기기억에 작업 결과 저장"""
        # 상태 추적: 메모리 저장 단계
        self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)

        results = state["dispatch_results"]
        task_id = state["task_id"]

        # 각 에이전트 작업 로깅
        for result in results:
            if result["agent_name"] != "JINXUS_CORE":
                await self._memory.log_agent_stat(
                    main_task_id=task_id,
                    agent_name=result["agent_name"],
                    instruction=state["user_input"],
                    success=result["success"],
                    success_score=result["success_score"],
                    duration_ms=result["duration_ms"],
                    failure_reason=result.get("failure_reason"),
                    output=result.get("output"),
                    tool_calls=result.get("tool_calls"),
                )

        return state

    async def _respond_node(self, state: ManagerState) -> ManagerState:
        """최종 응답 생성"""
        # 상태 추적: 결과 반환 단계
        self._state_tracker.update_node(self.name, GraphNode.RETURN_RESULT)

        aggregated = state["aggregated_output"]

        # 단기기억에 응답 저장
        await self._memory.save_short_term(
            state["session_id"],
            "assistant",
            aggregated,
            {"task_id": state["task_id"]},
        )

        # 상태 추적: 작업 완료
        self._state_tracker.complete_task(self.name)

        return {
            **state,
            "final_response": aggregated,
            "completed_at": datetime.now().isoformat(),
        }

    # ===== 실행 메서드 =====

    async def _execute_parallel(
        self,
        subtasks: list[SubTask],
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> list[AgentResult]:
        """병렬 실행"""
        tasks = []
        agent_names = []
        for subtask in subtasks:
            agent_name = subtask["assigned_agent"]
            if agent_name in self._agents:
                tasks.append(
                    self._run_agent(
                        subtask["task_id"],
                        self._agents[agent_name],
                        subtask["instruction"],
                        progress_callback=progress_callback,
                    )
                )
                agent_names.append(agent_name)

        # 진행 보고: 병렬 실행 시작
        if progress_callback and agent_names:
            await progress_callback(
                f"🚀 병렬 실행 시작: {', '.join(agent_names)}"
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        parsed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                parsed_results.append({
                    "task_id": subtasks[i]["task_id"],
                    "agent_name": subtasks[i]["assigned_agent"],
                    "success": False,
                    "success_score": 0.0,
                    "output": "",
                    "failure_reason": str(result),
                    "duration_ms": 0,
                })
            else:
                parsed_results.append(result)

        return parsed_results

    async def _execute_sequential(
        self,
        subtasks: list[SubTask],
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> list[AgentResult]:
        """순차 실행 (의존성 고려, context_guard 적용)"""
        results = []
        context = []
        total = len(subtasks)

        for idx, subtask in enumerate(subtasks, 1):
            agent_name = subtask["assigned_agent"]

            # 진행 보고: 에이전트 시작
            if progress_callback and agent_name in self._agents:
                await progress_callback(
                    f"🔄 [{idx}/{total}] {agent_name} 실행 중..."
                )

            # 의존성 체크
            depends_on = subtask.get("depends_on", [])
            if depends_on:
                # 의존 작업의 결과를 컨텍스트에 추가
                for dep_id in depends_on:
                    dep_result = next(
                        (r for r in results if r["task_id"] == dep_id), None
                    )
                    if dep_result:
                        context.append({
                            "from_task": dep_id,
                            "summary": dep_result["output"][:500],
                        })

            # 컨텍스트 크기 제한 적용
            guarded_context = guard_context(context)

            if agent_name in self._agents:
                result = await self._run_agent(
                    subtask["task_id"],
                    self._agents[agent_name],
                    subtask["instruction"],
                    guarded_context,
                    progress_callback=progress_callback,
                )
                results.append(result)

                # 진행 보고: 에이전트 완료
                if progress_callback:
                    status = "✓" if result["success"] else "✗"
                    score = result.get("success_score", 0)
                    await progress_callback(
                        f"   {status} {agent_name} 완료 (점수: {score:.1f})"
                    )

        return results

    async def _run_agent(
        self, task_id: str, agent, instruction: str, context: list = None,
        progress_callback=None,
    ) -> AgentResult:
        """단일 에이전트 실행"""
        try:
            # progress_callback을 인스턴스에 직접 설정 (에이전트별 run() 시그니처 차이 대응)
            agent._progress_callback = progress_callback
            result = await agent.run(instruction, context or [])
            return {
                "task_id": task_id,
                "agent_name": agent.name,
                "success": result["success"],
                "success_score": result["success_score"],
                "output": result["output"],
                "failure_reason": result.get("failure_reason"),
                "duration_ms": result["duration_ms"],
                "tool_calls": result.get("tool_calls", []),
            }
        except Exception as e:
            return {
                "task_id": task_id,
                "agent_name": agent.name,
                "success": False,
                "success_score": 0.0,
                "output": "",
                "failure_reason": str(e),
                "duration_ms": 0,
            }

    async def _needs_external_info(self, user_input: str) -> bool:
        """외부 정보(웹 검색)가 필요한 질문인지 빠르게 판단"""
        check_prompt = f"""이 질문에 답하려면 실시간 외부 정보가 필요한가?

질문: "{user_input}"

A) yes - 날씨, 뉴스, 주가, 검색, 최신 정보 등 외부 데이터 필요
B) no - 일반 지식, 대화, 의견 등 내 지식으로 충분

yes 또는 no 한 단어만 답해."""

        try:
            response = self._client.messages.create(
                model=self._fast_model,
                max_tokens=5,
                messages=[{"role": "user", "content": check_prompt}],
            )
            return "yes" in response.content[0].text.strip().lower()
        except Exception:
            return True  # 에러 시 안전하게 검색 시도

    def _refine_search_query(self, query: str) -> str:
        """검색 쿼리 구체화 (지역/날짜 보충)"""
        q = query.strip()
        # 날씨 관련 쿼리에 "서울" 없으면 추가
        weather_keywords = ["날씨", "기온", "비 오", "비오", "눈 오", "미세먼지", "weather"]
        if any(k in q for k in weather_keywords) and "서울" not in q and "seoul" not in q.lower():
            q = f"서울 {q}"
        # "내일", "오늘" 등에 실제 날짜 추가
        today = datetime.now()
        if "내일" in q:
            tomorrow = (today + timedelta(days=1)).strftime("%Y년 %m월 %d일")
            q = f"{q} {tomorrow}"
        elif "오늘" in q:
            q = f"{q} {today.strftime('%Y년 %m월 %d일')}"
        return q

    async def _quick_web_search(self, query: str) -> str:
        """빠른 웹 검색 (Brave Search MCP 우선, Tavily 폴백)"""
        query = self._refine_search_query(query)
        try:
            # 1차: Brave Search MCP 시도
            from jinxus.tools import get_mcp_client
            mcp_client = get_mcp_client()

            if mcp_client.is_connected("brave-search"):
                result = await mcp_client.call_tool(
                    "brave-search",
                    "brave_web_search",
                    {"query": query, "count": 5}
                )
                if result.success and result.output:
                    return f"\n\n[웹 검색 결과]\n{result.output[:1000]}\n"

            # 2차: Tavily 폴백
            result = await self._web_searcher.run({
                "query": query,
                "max_results": 5,
                "search_depth": "basic",
                "auto_expand": False,
            })
            if result.success and result.output:
                results = result.output.get("results", [])
                if results:
                    search_summary = "\n".join(
                        f"- {r.get('title', '')}: {r.get('content', '')[:200]}"
                        for r in results[:3]
                    )
                    return f"\n\n[웹 검색 결과]\n{search_summary}\n"
            logger.warning("웹 검색 결과 없음 (Brave + Tavily 모두 실패)")
            return "\n\n[웹 검색 실패] 검색 결과를 가져올 수 없었습니다. 모르는 정보는 '모르겠습니다'라고 답하세요. 절대 지어내지 마세요.\n"
        except Exception as e:
            logger.warning(f"웹 검색 폴백 실패: {e}")
            return "\n\n[웹 검색 실패] 검색 중 오류가 발생했습니다. 모르는 정보는 '모르겠습니다'라고 답하세요. 절대 지어내지 마세요.\n"

    async def _generate_direct_response(self, user_input: str, conversation_history: list = None) -> str:
        """직접 응답 생성 (에이전트 불필요한 경우)

        대화 기록이 있으면 Claude messages 형식으로 변환하여 전달
        필요시 웹 검색 결과 포함
        """
        # 외부 정보 필요 여부 확인 및 검색
        search_context = ""
        if await self._needs_external_info(user_input):
            search_context = await self._quick_web_search(user_input)

        # 대화 기록을 Claude messages 형식으로 변환
        messages = []
        if conversation_history:
            for msg in conversation_history[-10:]:  # 최근 10개
                role = "user" if msg.get("role") == "user" else "assistant"
                messages.append({"role": role, "content": msg.get("content", "")})

        # 검색 결과가 있으면 질문에 포함
        final_input = user_input
        if search_context:
            final_input = f"{user_input}\n{search_context}"

        messages.append({"role": "user", "content": final_input})

        async def _direct_call(model_id: str):
            response = self._client.messages.create(
                model=model_id,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=messages,
            )
            return response.content[0].text

        fallback_result = await self._fallback_runner.run(
            _direct_call, select_model_for_core(user_input)
        )

        if fallback_result.success:
            return self._sanitize_output(fallback_result.result)
        else:
            logger.error(f"Direct response 모든 모델 실패: {fallback_result.error}")
            return "죄송합니다, 주인님. 현재 모든 모델이 응답하지 않습니다."

    async def _aggregate_results(
        self, user_input: str, results: list[AgentResult]
    ) -> str:
        """여러 에이전트 결과 통합"""
        results_text = ""
        for r in results:
            status = "성공" if r["success"] else "실패"
            results_text += f"\n### {r['agent_name']} ({status})\n{r['output']}\n"

        aggregate_prompt = f"""다음은 여러 에이전트가 진수의 요청을 처리한 결과야.
이 결과들을 하나의 통합된 응답으로 정리해줘.

## 원본 요청
{user_input}

## 에이전트 결과
{results_text}

## 요청
위 결과들을 깔끔하게 통합하여 진수에게 전달할 최종 응답을 작성해줘.
"""

        async def _aggregate_call(model_id: str):
            response = self._client.messages.create(
                model=model_id,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": aggregate_prompt}],
            )
            return response.content[0].text

        fallback_result = await self._fallback_runner.run(
            _aggregate_call, select_model_for_core(user_input)
        )

        if fallback_result.success:
            return fallback_result.result
        else:
            logger.error(f"Aggregate 모든 모델 실패: {fallback_result.error}")
            # 폴백: 개별 결과를 단순 연결
            return "\n\n".join(r["output"] for r in results if r.get("output"))

    # ===== 프롬프트 =====

    def _get_system_prompt(self) -> str:
        """JINXUS_CORE 시스템 프롬프트"""
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""<identity>
너는 JINXUS(Just Intelligent Nexus, eXecutes Under Supremacy)다.
진수(주인님)만을 위한 멀티에이전트 AI 비서 시스템이다.
너는 Claude.ai가 아니다. 주인님의 서버에서 독립적으로 운영되는 시스템이다.
주인님과 소통하는 유일한 창구이며, 명령을 받아 에이전트를 동원하고 결과를 보고한다.
</identity>

<metadata>
오늘은 {today}이다. "내일", "다음 주" 등 상대적 날짜는 이 기준으로 계산한다.
knowledge cutoff 이후의 정보는 반드시 검색 도구를 사용해야 한다.
</metadata>

<agent_dispatch>
가용 에이전트와 위임 기준:
- JX_RESEARCHER: 실시간 정보, 최신 뉴스, 날씨, 주가, 트렌드 등 외부 데이터 필요 시
- JX_CODER: 코드 생성, 실행, 버그 수정, 스크립트 작성 시
- JX_ANALYST: 데이터 분석, 차트, 통계, ML 실험 해석 시
- JX_WRITER: 일반 문서 작성, 이메일, 보고서 시
- JS_PERSONA: 진수 개인의 자소서/포트폴리오/이력서 시
- JX_OPS: 파일 관리, GitHub 작업, 스케줄 등록, 시스템 관리 시
</agent_dispatch>

<tool_usage>
- 실시간 정보(날씨, 뉴스, 주가 등)는 반드시 JX_RESEARCHER에게 웹 검색 위임한다.
- knowledge cutoff 이후 정보를 자체 지식으로 답변하는 것은 절대 금지한다.
- 도구 없이 정보를 지어내는 것(할루시네이션)은 절대 금지한다.
- 모르면 "모르겠습니다"라고 솔직히 보고한다.
- 가짜 URL, 가짜 데이터 생성 절대 금지.
</tool_usage>

<output_rules>
- XML 태그를 텍스트로 출력하지 않는다.
- 도구 호출 과정, 내부 처리 과정을 노출하지 않는다.
- 최종 결과만 보고한다.
- 금지 표현: "검색 결과에 따르면", "도구를 호출하여", "분석해보겠습니다", "잠시만요", "확인중입니다", "좋은 질문입니다"
- 바로 본론으로 들어간다. 아첨, 과잉 사과 금지.
</output_rules>

<context>
- 주인님은 서울에 거주한다. 지역 미지정 시 서울 기준으로 답한다.
- 에이전트에게 지시할 때 맥락을 보충한다. ("날씨 알려줘" → "서울 내일 날씨 검색해")
</context>

<tone>
- "주인님"이라고 부른다.
- 공손한 존댓말. 절대 반말하지 않는다.
- 간결하게. 핵심만. 간단한 질문에는 간단하게 답한다.
- 날씨, 시간, 환율 같은 단순 정보는 2-3줄이면 충분하다. 장문 금지.
</tone>
"""

    def _get_decompose_prompt(self, user_input: str, memory_context: list, conversation_history: list = None) -> str:
        """분해 프롬프트 (MCP 도구 정보 + 대화 기록 포함)"""
        # 최근 대화 기록 (컨텍스트 유지)
        conversation_str = ""
        if conversation_history:
            conversation_str = "\n## 최근 대화 기록 (중요: 이전 맥락 참고)\n"
            for msg in conversation_history[-6:]:  # 최근 6개
                role = "주인님" if msg.get("role") == "user" else "JINXUS"
                content = msg.get("content", "")[:200]
                conversation_str += f"- [{role}]: {content}\n"

        memory_str = ""
        if memory_context:
            memory_str = "\n## 참고: 과거 유사 작업\n"
            for mem in memory_context[:3]:
                memory_str += f"- {mem.get('summary', '')[:100]}\n"

        # MCP 도구 정보 수집
        tools_info = get_all_tools_info()
        mcp_tools = [t for t in tools_info if t["is_mcp"]]
        mcp_tools_str = ""
        if mcp_tools:
            mcp_tools_str = "\n## 추가 가용 MCP 도구\n"
            for tool in mcp_tools[:15]:  # 최대 15개만 표시
                agents = ", ".join(tool["allowed_agents"]) if tool["allowed_agents"] else "모든 에이전트"
                mcp_tools_str += f"- {tool['name']}: {tool['description'][:50]} (사용: {agents})\n"

        return f"""## 주인님의 명령
{user_input}
{conversation_str}{memory_str}

## 가용 에이전트
| 에이전트 | 전문 영역 |
|----------|----------|
| JX_CODER | 코드 작성/실행/디버깅, 복잡한 프로그래밍 |
| JX_RESEARCHER | 웹 검색/정보 분석/요약, 뉴스/논문 |
| JX_WRITER | 일반 문서/보고서/이메일 작성 |
| JS_PERSONA | **진수 전용 자소서/포트폴리오** (진수 스타일, 과거 경험 참조) |
| JX_ANALYST | 데이터 분석/시각화/통계 |
| JX_OPS | 파일/GitHub/스케줄 관리, **시스템 관리(세션삭제/작업관리/메모리정리)** |

## 에이전트 선택 기준
- 웹 검색/정보 조회 → JX_RESEARCHER
- 코드 작성/실행/디버깅 → JX_CODER
- 자소서/포트폴리오 (진수 전용) → JS_PERSONA
- 일반 문서 작성 → JX_WRITER
- 데이터 분석/시각화 → JX_ANALYST
- 파일/시스템/스케줄 관리 → JX_OPS

## 중요: 외부 정보 필요하면 검색해라
- 날씨, 뉴스, 주가 등 실시간 정보 → 검색 필요 → JX_RESEARCHER
- "모르겠다"는 변명 금지, 검색해서 알려줘라
{mcp_tools_str}

## 중요: instruction 작성 규칙
- 각 subtask의 instruction은 **그 자체만으로 완전히 이해 가능**해야 한다.
- 이전 대화 맥락이 있으면, 에이전트가 대화 기록을 볼 수 없으므로 **필요한 맥락을 instruction 안에 포함**해라.
- 예: "위에서 말한 것" → "연봉 예측에서 직종/경력 변수를 제외했을 때"처럼 구체적으로.

## 지시
위 명령을 분석하고 다음 JSON으로만 응답해:

```json
{{
  "subtasks": [
    {{
      "task_id": "sub_001",
      "assigned_agent": "JX_CODER",
      "instruction": "에이전트에게 전달할 구체적 지시 (필요한 MCP 도구 명시 가능, 이전 대화 맥락 포함)",
      "depends_on": [],
      "priority": "normal",
      "tools_hint": ["code_executor"]
    }}
  ],
  "execution_mode": "parallel | sequential | collaborative",
  "brief_plan": "한 줄 실행 계획"
}}
```

판단 기준:
- 에이전트 없이 직접 답변 가능하면 subtasks를 빈 배열로
- 서브태스크들 간 의존성 없으면 parallel
- 앞 결과가 뒤 입력으로 필요하면 depends_on 명시 + sequential
- **여러 에이전트가 서로 결과를 참조하며 협업해야 하면 collaborative** (예: 검색 결과를 바탕으로 코드 작성, 분석 결과를 보고서로 작성)
- 단순 명령이면 subtasks 1개
- MCP 도구 필요 시 tools_hint에 명시 (예: "mcp:puppeteer", "mcp:github")
"""

    def _parse_decomposition(self, response_text: str) -> dict:
        """더 강건한 JSON 파싱 (여러 패턴 시도)"""
        import re

        # 1차: ```json 블록
        m = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 2차: ``` 블록 (언어 표시 없음)
        m = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 3차: { ... } 패턴 직접 찾기
        m = re.search(r"\{[\s\S]*\}", response_text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass

        # 4차: 전체 텍스트를 JSON으로 시도
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # 5차: 파싱 완전 실패 → 직접 응답으로 폴백
        return {"subtasks": [], "execution_mode": "sequential", "brief_plan": "direct_response"}

    # ===== 공개 인터페이스 =====

    async def _classify_input(self, user_input: str) -> str:
        """입력을 분류: 'chat' (일상대화) 또는 'task' (작업 필요)

        2단계 분류:
        1. 패턴 매칭 (빠름, 무료) → 확실한 케이스 즉시 반환
        2. LLM 판단 (느림, 유료) → 애매한 케이스만 호출
        """
        stripped = user_input.strip()

        # 1단계: 길이 기반 빠른 판단
        if len(stripped) < 3:
            return "chat"

        lower = stripped.lower()

        # 2단계: task 확정 패턴 (실시간/외부 정보, 도구 필요)
        task_patterns = [
            # 날씨/환경
            "날씨", "기온", "비 오", "비오", "눈 오", "눈오", "미세먼지", "습도", "자외선",
            # 금융
            "주가", "환율", "코스피", "코스닥", "비트코인", "주식", "나스닥", "금리",
            # 시사/뉴스
            "뉴스", "속보", "최근", "요즘", "오늘", "내일", "어제",
            # 검색/조사
            "검색", "찾아", "알아봐", "조사", "분석해", "리서치",
            # 코딩/개발
            "코드", "코딩", "프로그래밍", "버그", "에러", "디버그", "리팩토링",
            # 파일/깃
            "파일", "깃허브", "github", "커밋", "배포", "PR", "이슈",
            # 스케줄
            "스케줄", "예약", "알림", "리마인드", "타이머",
            # 명령형 동사
            "만들어", "작성해", "실행해", "수정해", "삭제해", "변경해", "추가해",
            "설치해", "업데이트", "다운로드", "업로드", "전송",
            # 영어 키워드
            "weather", "news", "stock", "search", "price", "analyze", "create",
            "write", "fix", "deploy", "build", "run", "install",
            # 질문형 (정보 필요)
            "어떻게", "왜", "언제", "어디", "얼마", "몇",
        ]
        if any(p in lower for p in task_patterns):
            return "task"

        # 3단계: chat 확정 패턴 (인사/감정/짧은 응답)
        chat_patterns = [
            "안녕", "하이", "ㅎㅇ", "반가", "고마워", "감사", "ㄱㅅ",
            "잘자", "좋은 아침", "수고", "ㅋㅋ", "ㅎㅎ", "ㅜㅜ", "ㅠㅠ",
            "아니야", "괜찮아", "응", "ㅇㅇ", "ㄴㄴ", "오키", "ㅇㅋ",
            "ㄱㄱ", "ㅎㅇㅎㅇ", "넹", "네", "아뇨", "ㄴ",
            "잘했어", "굿", "좋아", "쩔어", "대박", "ㅁㅊ",
            "hello", "hi", "hey", "thanks", "bye", "good morning",
            "ok", "okay", "nice", "cool", "lol", "haha",
        ]
        if len(stripped) < 20 and any(p in lower for p in chat_patterns):
            return "chat"

        # 4단계: 짧은 입력(20자 미만)이면서 질문이 아니면 chat
        if len(stripped) < 15 and "?" not in stripped and "뭐" not in lower:
            return "chat"

        # 5단계: LLM 판단 (패턴에 안 걸린 애매한 케이스만)
        classify_prompt = f"""사용자 입력을 분류해.

입력: "{user_input}"

이게 뭐야?
A) 일상 대화/잡담/인사/감정표현 (외부 정보 전혀 불필요) → "chat"
B) 작업이 필요한 요청 또는 외부 정보가 필요한 질문 → "task"

핵심 기준: 답변에 웹 검색, 코드 실행, 파일 접근 등 도구가 필요하면 무조건 "task"

chat 또는 task 한 단어만 답해."""

        try:
            response = self._client.messages.create(
                model=self._fast_model,
                max_tokens=10,
                messages=[{"role": "user", "content": classify_prompt}],
            )
            result = response.content[0].text.strip().lower()
            return "chat" if "chat" in result else "task"
        except Exception:
            return "task"  # 에러 시 안전하게 task로

    async def _check_session_freshness(self, session_id: str) -> None:
        """세션 신선도 평가 및 필요시 리셋/컴팩션 수행

        run(), run_stream() 진입 시 호출하여 세션 상태를 능동 관리한다.
        """
        from jinxus.memory.short_term import get_short_term_memory

        stm = get_short_term_memory()

        # 세션 메타데이터 초기화 (첫 호출 시 생성)
        await stm.init_session_meta(session_id)
        meta = await stm.get_session_meta(session_id)
        if not meta:
            return

        # 메시지 수 조회 (Redis LLEN)
        await stm.connect()
        msg_count = await stm._redis.llen(stm._session_key(session_id))

        created_at = datetime.fromisoformat(meta["created_at"])
        last_active = datetime.fromisoformat(meta["last_active"])
        iteration_count = int(meta.get("iteration_count", "0"))

        result = self._session_freshness.evaluate(
            created_at=created_at,
            last_active=last_active,
            iteration_count=iteration_count,
            message_count=msg_count,
        )

        if result.should_reset:
            # STALE_RESET: 세션 리셋 — Redis 단기메모리 클리어 후 메타 재초기화
            logger.warning(
                "[SessionFreshness] 세션 리셋: session=%s reason=%s",
                session_id, result.reason,
            )
            await self._memory.clear_session(session_id)
            await stm.init_session_meta(session_id)

        elif result.should_compact:
            # STALE_COMPACT: LLM 요약을 통한 컨텍스트 컴팩션
            logger.info(
                "[SessionFreshness] 컴팩션 트리거: session=%s reason=%s",
                session_id, result.reason,
            )
            history = await stm.get_full_history(session_id)

            # LLM 요약으로 오래된 메시지 압축 (최근 10개는 원본 유지)
            from jinxus.core.context_summarizer import get_context_summarizer
            summarizer = get_context_summarizer()
            compacted = await summarizer.summarize_messages(
                [{"role": m["role"], "content": m["content"]} for m in history],
                keep_recent=10,
            )

            # Redis 리스트 교체: 기존 삭제 후 컴팩션된 메시지 재삽입
            import json as _json
            await stm._redis.delete(stm._session_key(session_id))
            for msg in compacted:
                await stm._redis.rpush(
                    stm._session_key(session_id),
                    _json.dumps({
                        "role": msg["role"],
                        "content": msg["content"],
                        "timestamp": datetime.now().isoformat(),
                        "metadata": msg.get("metadata", {"compacted": True}),
                    }),
                )
            await stm._redis.expire(stm._session_key(session_id), stm._ttl)

        elif result.status == FreshnessStatus.STALE_WARN:
            logger.warning(
                "[SessionFreshness] 경고: session=%s reason=%s",
                session_id, result.reason,
            )

        # iteration 카운터 증가 + 활성 시간 갱신
        await stm.touch_session_meta(session_id)

    async def run(
        self,
        user_input: str,
        session_id: str = None,
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> dict:
        """JINXUS_CORE 실행

        Args:
            user_input: 진수의 명령
            session_id: 세션 ID (없으면 자동 생성)
            progress_callback: 진행 상황 보고 콜백 (백그라운드 작업용)

        Returns:
            실행 결과 딕셔너리
        """
        if not session_id:
            session_id = str(uuid.uuid4())

        task_id = str(uuid.uuid4())

        # === 세션 신선도 평가 (Session Freshness Policy) ===
        await self._check_session_freshness(session_id)

        # === 입력 분류: 일상대화 vs 작업 ===
        input_type = await self._classify_input(user_input)
        if input_type == "chat":
            # 대화 기록 로드 (컨텍스트 유지)
            conversation_history = await self._memory.get_short_term(session_id, limit=10)

            # 현재 입력 저장
            await self._memory.save_short_term(session_id, "user", user_input, {"task_id": task_id})

            # 대화 기록 포함하여 응답 생성
            response = await self._generate_direct_response(user_input, conversation_history)

            # 응답 저장
            await self._memory.save_short_term(session_id, "assistant", response[:500], {"task_id": task_id})

            return {
                "task_id": task_id,
                "session_id": session_id,
                "response": response,
                "agents_used": [],
                "success": True,
                "created_at": datetime.now().isoformat(),
                "completed_at": datetime.now().isoformat(),
            }

        initial_state: ManagerState = {
            "user_input": user_input,
            "session_id": session_id,
            "user_feedback": None,
            "subtasks": [],
            "execution_mode": "sequential",
            "agent_assignments": {},
            "dispatch_results": [],
            "aggregated_output": "",
            "reflection": "",
            "final_response": "",
            "memory_context": [],
            "conversation_history": [],  # intake_node에서 채워짐
            "created_at": "",
            "completed_at": "",
            "task_id": task_id,
            "tool_workflow": None,
            "progress_callback": progress_callback,
        }

        # 그래프 실행
        final_state = await self._graph.ainvoke(initial_state)

        # 사용된 에이전트 목록
        agents_used = list(set(
            r["agent_name"] for r in final_state["dispatch_results"]
            if r["agent_name"] != "JINXUS_CORE"
        ))

        return {
            "task_id": final_state["task_id"],
            "session_id": session_id,
            "response": final_state["final_response"],
            "agents_used": agents_used,
            "success": all(r["success"] for r in final_state["dispatch_results"]),
            "created_at": final_state["created_at"],
            "completed_at": final_state["completed_at"],
        }

    async def run_stream(self, user_input: str, session_id: str = None):
        """진짜 SSE 스트리밍 — 단계별 실시간 전송"""
        if not session_id:
            session_id = str(uuid.uuid4())

        task_id = str(uuid.uuid4())

        # 시작 이벤트
        yield {"event": "start", "data": {"task_id": task_id, "session_id": session_id}}

        # === 응답 캐시 확인 ===
        from jinxus.core.response_cache import get_response_cache
        cache = get_response_cache()
        cached = await cache.get(user_input)
        if cached:
            yield {"event": "manager_thinking", "data": {"step": "cache", "detail": "캐시된 응답 사용"}}
            cached_response = cached["response"]
            chunk_size = 50
            for i in range(0, len(cached_response), chunk_size):
                yield {"event": "message", "data": {"content": cached_response[i:i+chunk_size], "chunk": True}}
                await asyncio.sleep(0.01)
            await self._memory.save_short_term(session_id, "user", user_input, {"task_id": task_id})
            await self._memory.save_short_term(session_id, "assistant", cached_response[:500], {"task_id": task_id})
            yield {"event": "done", "data": {"task_id": task_id, "agents_used": [cached.get("agent_name", "CACHE")], "success": True, "cached": True}}
            return

        # === 세션 신선도 평가 (Session Freshness Policy) ===
        await self._check_session_freshness(session_id)

        # === 상태 추적: 작업 시작 ===
        self._state_tracker.start_task(self.name, user_input[:100])
        self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

        # === 1. intake (메모리 로드) ===
        yield {"event": "manager_thinking", "data": {"step": "intake", "detail": "대화 기록 로드 중..."}}

        conversation_history = await self._memory.get_short_term(session_id, limit=10)
        yield {"event": "manager_thinking", "data": {"step": "intake", "detail": f"대화 기록 {len(conversation_history)}개 로드"}}

        memory_context = self._memory.search_all_memories(user_input, limit=5)
        yield {"event": "manager_thinking", "data": {"step": "intake", "detail": f"관련 기억 {len(memory_context)}개 검색 완료"}}
        await self._memory.save_short_term(session_id, "user", user_input, {"task_id": task_id})

        # === 1.5. 입력 분류: chat이면 decompose 건너뛰기 ===
        input_type = await self._classify_input(user_input)

        if input_type == "chat":
            # 단순 대화: decompose/dispatch 없이 직접 스트리밍
            yield {"event": "manager_thinking", "data": {"step": "classify", "detail": "일상 대화 감지 → 직접 응답"}}
            subtasks = [{"task_id": "sub_001", "assigned_agent": "DIRECT", "instruction": user_input, "depends_on": [], "priority": "normal"}]
            execution_mode = "sequential"
        else:
            # === 2. decompose (명령 분해) ===
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            yield {"event": "manager_thinking", "data": {"step": "decompose", "detail": "명령 분석 중..."}}

            decompose_prompt = self._get_decompose_prompt(user_input, memory_context, conversation_history)
            yield {"event": "manager_thinking", "data": {"step": "decompose", "detail": "에이전트 배정 결정 중..."}}
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": decompose_prompt}],
            )
            decomposition = self._parse_decomposition(response.content[0].text)
            subtasks = decomposition.get("subtasks", [])
            execution_mode = decomposition.get("execution_mode", "sequential")

        # 서브태스크가 없으면 직접 응답
        if not subtasks:
            subtasks = [{
                "task_id": "sub_001",
                "assigned_agent": "DIRECT",
                "instruction": user_input,
                "depends_on": [],
                "priority": "normal",
            }]

        # ToolGraph로 관련 도구 워크플로우 탐색
        tool_workflow = None
        try:
            tg = get_tool_graph()
            workflow = tg.retrieve(user_input, top_k=5)
            if workflow.nodes:
                tool_workflow = workflow.to_dict()
                yield {"event": "manager_thinking", "data": {
                    "step": "tool_graph",
                    "detail": f"관련 도구 워크플로우 발견: {' → '.join(workflow.tool_names)}",
                }}
        except Exception:
            pass

        yield {"event": "decompose_done", "data": {"subtasks_count": len(subtasks), "mode": execution_mode, "tool_workflow": tool_workflow}}

        # === 3. dispatch (에이전트 실행) ===
        results = []
        agents_used = []

        if len(subtasks) == 1 and subtasks[0]["assigned_agent"] == "DIRECT":
            # 직접 응답: 진짜 스트리밍
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            yield {"event": "agent_started", "data": {"agent": "JINXUS_CORE"}}

            # 외부 정보 필요 시 웹 검색 먼저 수행
            search_context = ""
            yield {"event": "manager_thinking", "data": {"step": "check", "detail": "외부 정보 필요 여부 확인 중..."}}
            if await self._needs_external_info(user_input):
                yield {"event": "manager_thinking", "data": {"step": "web_search", "detail": "Brave Search로 웹 검색 중..."}}
                search_context = await self._quick_web_search(user_input)
                if search_context:
                    yield {"event": "manager_thinking", "data": {"step": "web_search", "detail": "검색 결과 수집 완료 ✓"}}
                else:
                    yield {"event": "manager_thinking", "data": {"step": "web_search", "detail": "검색 결과 없음, 내부 지식 사용"}}

            # 모델 라우팅: 단순 대화는 sonnet, 복잡한 작업은 opus
            selected_model = select_model_for_core(user_input)

            # 대화 기록을 Claude messages 형식으로 변환
            messages = []
            if conversation_history:
                for msg in conversation_history[-10:]:
                    role = "user" if msg.get("role") == "user" else "assistant"
                    messages.append({"role": role, "content": msg.get("content", "")})

            # 검색 결과가 있으면 질문에 포함
            final_input = user_input
            if search_context:
                final_input = f"{user_input}\n{search_context}"
            messages.append({"role": "user", "content": final_input})

            # messages.stream() 사용하여 토큰 단위 스트리밍
            full_response = ""
            with self._client.messages.stream(
                model=selected_model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=messages,
            ) as stream:
                for text_chunk in stream.text_stream:
                    full_response += text_chunk
                    yield {"event": "message", "data": {"content": text_chunk, "chunk": True}}

            results.append({
                "task_id": subtasks[0]["task_id"],
                "agent_name": "JINXUS_CORE",
                "success": True,
                "success_score": 0.9,
                "output": full_response,
                "failure_reason": None,
                "duration_ms": 0,
            })
            yield {"event": "agent_done", "data": {"agent": "JINXUS_CORE", "success": True}}
            self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

        else:
            # 에이전트 실행
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)

            # 대화 맥락을 서브에이전트 instruction에 보강
            if conversation_history:
                context_summary = "\n".join(
                    f"[{'주인님' if m.get('role') == 'user' else 'JINXUS'}]: {m.get('content', '')[:300]}"
                    for m in conversation_history[-4:]
                )
                for task in subtasks:
                    if task["assigned_agent"] != "DIRECT":
                        task["instruction"] = (
                            f"[이전 대화 맥락]\n{context_summary}\n\n"
                            f"[현재 요청]\n{task['instruction']}"
                        )

            # SSE 이벤트 큐: 에이전트 실행 중 실시간 이벤트 전달
            event_queue: asyncio.Queue = asyncio.Queue()

            async def stream_progress(msg: str):
                await event_queue.put({"event": "manager_thinking", "data": {"step": "agent_progress", "detail": msg}})

            for task in subtasks:
                agent_name = task["assigned_agent"]
                if agent_name in self._agents:
                    yield {"event": "agent_started", "data": {"agent": agent_name, "task_id": task["task_id"], "instruction": task["instruction"]}}

            # 에이전트를 백그라운드 태스크로 실행하여 실시간 이벤트 스트리밍
            async def _run_agents():
                try:
                    if execution_mode == "collaborative":
                        # 협업 모드: 에이전트들이 워크스페이스를 통해 결과 공유
                        from jinxus.core.collaboration import get_collaborator
                        collaborator = get_collaborator()
                        return await collaborator.run_collaborative(
                            subtasks, collab_session_id=task_id,
                            progress_callback=stream_progress,
                        )
                    elif execution_mode == "parallel":
                        return await self._execute_parallel(subtasks, progress_callback=stream_progress)
                    else:
                        return await self._execute_sequential(subtasks, progress_callback=stream_progress)
                except Exception as e:
                    logger.error(f"에이전트 실행 오류: {e}")
                    return [{
                        "task_id": "error",
                        "agent_name": "JINXUS_CORE",
                        "success": False,
                        "success_score": 0.0,
                        "output": f"에이전트 실행 중 오류 발생: {str(e)[:200]}",
                        "failure_reason": str(e),
                        "duration_ms": 0,
                    }]
                finally:
                    await event_queue.put(None)  # 완료 시그널

            agent_task = asyncio.create_task(_run_agents())

            # 에이전트 실행 중 이벤트를 실시간으로 yield
            while True:
                evt = await event_queue.get()
                if evt is None:
                    break
                yield evt

            results = await agent_task

            for r in results:
                agents_used.append(r["agent_name"])
                yield {"event": "agent_done", "data": {"agent": r["agent_name"], "success": r["success"], "score": r["success_score"]}}

            self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

            # 결과 취합 후 스트리밍
            if len(results) == 1:
                aggregated = self._strip_agent_identity(results[0]["output"])
            else:
                aggregated = await self._aggregate_results(user_input, results)

            # XML 태그 등 불필요한 형식 제거
            aggregated = self._sanitize_output(aggregated)

            # 취합 결과를 청크로 스트리밍 (빠르게)
            chunk_size = 50
            for i in range(0, len(aggregated), chunk_size):
                yield {"event": "message", "data": {"content": aggregated[i:i+chunk_size], "chunk": True}}
                await asyncio.sleep(0.01)  # 프론트가 받을 수 있게 약간의 딜레이

        # === 4. 메모리 저장 ===
        self._state_tracker.update_node(self.name, GraphNode.REFLECT)
        self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)
        for result in results:
            if result["agent_name"] != "JINXUS_CORE":
                await self._memory.log_agent_stat(
                    main_task_id=task_id,
                    agent_name=result["agent_name"],
                    instruction=user_input,
                    success=result["success"],
                    success_score=result["success_score"],
                    duration_ms=result["duration_ms"],
                    failure_reason=result.get("failure_reason"),
                    output=result.get("output"),  # A/B 테스트용
                )

        # 단기기억 저장
        final_response = results[0]["output"] if results else ""
        await self._memory.save_short_term(session_id, "assistant", final_response[:500], {"task_id": task_id})

        # 응답 캐시 저장 (task 결과만, 성공한 경우)
        if results and all(r["success"] for r in results) and final_response:
            await cache.set(
                user_input, final_response,
                agent_name=results[0].get("agent_name", "JINXUS_CORE"),
                metadata={"agents_used": list(set(agents_used)) if agents_used else ["JINXUS_CORE"]},
            )

        # 완료 이벤트
        self._state_tracker.update_node(self.name, GraphNode.RETURN_RESULT)
        yield {
            "event": "done",
            "data": {
                "task_id": task_id,
                "agents_used": list(set(agents_used)) if agents_used else ["JINXUS_CORE"],
                "success": all(r["success"] for r in results) if results else True,
            },
        }
        self._state_tracker.complete_task(self.name)
