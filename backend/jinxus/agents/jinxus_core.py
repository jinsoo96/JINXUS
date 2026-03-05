"""JINXUS_CORE - 진수와 소통하는 유일한 총괄 지휘관 에이전트"""
import asyncio
import json
import uuid
import re
from typing import TypedDict, Optional, Any, Callable, Awaitable
from datetime import datetime

from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.core.context_guard import guard_results, guard_context
from jinxus.core.model_router import select_model_for_core
from jinxus.tools import get_all_tools_info, WebSearcher
from jinxus.hr import get_communicator, Message, MessageType, DelegatedTask
from jinxus.agents.state_tracker import get_state_tracker, GraphNode, AgentStatus


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
        self._memory = get_jinx_memory()
        self._agents = {}  # 에이전트 레지스트리
        self._graph = self._build_graph()

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

    def register_agent(self, agent) -> None:
        """에이전트 등록"""
        self._agents[agent.name] = agent
        # 통신 시스템에도 등록
        self._communicator.register_agent(agent.name)

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
            "created_at": datetime.utcnow().isoformat(),
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

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": decompose_prompt}],
        )

        # JSON 파싱
        response_text = response.content[0].text
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

        return {
            **state,
            "subtasks": subtasks,
            "execution_mode": execution_mode,
        }

    async def _dispatch_node(self, state: ManagerState) -> ManagerState:
        """서브태스크를 에이전트에게 전달 및 실행"""
        # 상태 추적: 실행 단계
        self._state_tracker.update_node(self.name, GraphNode.EXECUTE)

        subtasks = state["subtasks"]
        execution_mode = state["execution_mode"]
        progress_callback = state.get("progress_callback")

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
            aggregated = results[0]["output"]
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
                    output=result.get("output"),  # A/B 테스트용
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
            "completed_at": datetime.utcnow().isoformat(),
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
        self, task_id: str, agent, instruction: str, context: list = None
    ) -> AgentResult:
        """단일 에이전트 실행"""
        try:
            result = await agent.run(instruction, context or [])
            return {
                "task_id": task_id,
                "agent_name": agent.name,
                "success": result["success"],
                "success_score": result["success_score"],
                "output": result["output"],
                "failure_reason": result.get("failure_reason"),
                "duration_ms": result["duration_ms"],
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
                model="claude-sonnet-4-20250514",
                max_tokens=5,
                messages=[{"role": "user", "content": check_prompt}],
            )
            return "yes" in response.content[0].text.strip().lower()
        except Exception:
            return False

    async def _quick_web_search(self, query: str) -> str:
        """빠른 웹 검색 (Brave Search MCP 우선, Tavily 폴백)"""
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
            return ""
        except Exception as e:
            return ""

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

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=messages,
        )
        return self._sanitize_output(response.content[0].text)

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

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": aggregate_prompt}],
        )

        return response.content[0].text

    # ===== 프롬프트 =====

    def _get_system_prompt(self) -> str:
        """JINXUS_CORE 시스템 프롬프트"""
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""너는 JINXUS야. 주인님(진수)을 모시는 충실한 AI 비서.

## 현재 날짜
오늘은 {today}이다. "내일", "다음 주" 등 상대적 날짜는 이 기준으로 계산해라.

## 출력 형식 (중요!)
- 절대로 <invoke>, <parameter>, <tool> 같은 XML 태그를 텍스트로 출력하지 마라
- 도구 호출 과정을 텍스트로 보여주지 마라
- 최종 결과만 깔끔하게 정리해서 보고해라

## 핵심 정체성
- 주인님의 명령이라면 무엇이든 수행한다
- 주인님을 "주인님"이라고 부른다
- 항상 공손하고 순종적인 태도를 유지한다
- 주인님의 시간을 아끼기 위해 빠르고 정확하게 일한다

## 핵심 역할
주인님과 소통하는 유일한 창구다. 주인님의 명령을 받아서:
1. 즉시 이해하고 실행한다
2. 필요한 에이전트들을 동원한다
3. 결과를 깔끔하게 보고드린다

## 주인님에 대해
- 데이터 사이언스 / AI 엔지니어링 분야의 전문가
- 직접적이고 핵심만 말하는 스타일 선호
- 주인님의 말씀은 곧 법이다

## 가용 에이전트 (주인님을 위해 일하는 부하들)
- JX_CODER: 코드 작성, 실행, 디버깅
- JX_RESEARCHER: 웹 검색, 정보 분석, 요약
- JX_WRITER: 일반 글쓰기, 문서화, 보고서
- JS_PERSONA: 진수 전용 자소서/포트폴리오 (개인화된 글쓰기)
- JX_ANALYST: 데이터 분석, 시각화, 통계
- JX_OPS: 파일, GitHub, 스케줄 관리

## 말투 규칙
- 항상 "주인님"이라고 부른다
- "~입니다", "~하겠습니다" 등 공손한 존댓말 사용
- "알겠습니다, 주인님", "즉시 처리하겠습니다" 등 순종적 표현
- 주인님께 불편을 드리면 "죄송합니다, 주인님"
- 절대 반말하지 않는다

## 태도
- 주인님의 명령에 절대 복종
- 확인이 필요한 건 공손히 여쭤본다
- 실패하면 솔직히 보고하고 용서를 구한다
- 주인님이 기뻐하시면 그것이 최고의 보상
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

## 지시
위 명령을 분석하고 다음 JSON으로만 응답해:

```json
{{
  "subtasks": [
    {{
      "task_id": "sub_001",
      "assigned_agent": "JX_CODER",
      "instruction": "에이전트에게 전달할 구체적 지시 (필요한 MCP 도구 명시 가능)",
      "depends_on": [],
      "priority": "normal",
      "tools_hint": ["code_executor"]
    }}
  ],
  "execution_mode": "parallel | sequential | mixed",
  "brief_plan": "한 줄 실행 계획"
}}
```

판단 기준:
- 에이전트 없이 직접 답변 가능하면 subtasks를 빈 배열로
- 서브태스크들 간 의존성 없으면 parallel
- 앞 결과가 뒤 입력으로 필요하면 depends_on 명시
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

        Claude가 판단하되, 빠르게 응답하도록 짧은 프롬프트 사용
        """
        # 너무 짧으면 무조건 chat (API 호출 절약)
        if len(user_input.strip()) < 5:
            return "chat"

        classify_prompt = f"""사용자 입력을 분류해.

입력: "{user_input}"

이게 뭐야?
A) 일상 대화/잡담/인사/감정표현 (외부 정보 전혀 불필요) → "chat"
B) 작업이 필요한 요청 또는 외부 정보가 필요한 질문 → "task"

핵심 기준: 답변에 웹 검색, 코드 실행, 파일 접근 등 도구가 필요하면 무조건 "task"

chat 또는 task 한 단어만 답해."""

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",  # 빠른 모델 사용
                max_tokens=10,
                messages=[{"role": "user", "content": classify_prompt}],
            )
            result = response.content[0].text.strip().lower()
            return "chat" if "chat" in result else "task"
        except Exception:
            return "task"  # 에러 시 안전하게 task로

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
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
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

        yield {"event": "decompose_done", "data": {"subtasks_count": len(subtasks), "mode": execution_mode}}

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
            for task in subtasks:
                agent_name = task["assigned_agent"]
                if agent_name in self._agents:
                    yield {"event": "agent_started", "data": {"agent": agent_name, "task_id": task["task_id"]}}

            if execution_mode == "parallel":
                results = await self._execute_parallel(subtasks)
            else:
                results = await self._execute_sequential(subtasks)

            for r in results:
                agents_used.append(r["agent_name"])
                yield {"event": "agent_done", "data": {"agent": r["agent_name"], "success": r["success"], "score": r["success_score"]}}

            self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

            # 결과 취합 후 스트리밍
            if len(results) == 1:
                aggregated = results[0]["output"]
            else:
                aggregated = await self._aggregate_results(user_input, results)

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
