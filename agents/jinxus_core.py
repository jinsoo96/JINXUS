"""JINXUS_CORE - 진수와 소통하는 유일한 총괄 지휘관 에이전트"""
import asyncio
import json
import uuid
from typing import TypedDict, Optional, Any
from datetime import datetime

from langgraph.graph import StateGraph, END
from anthropic import Anthropic

from config import get_settings
from memory import get_jinx_memory
from core.context_guard import guard_results, guard_context
from core.model_router import select_model_for_core


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
    created_at: str
    completed_at: str
    task_id: str


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

    def register_agent(self, agent) -> None:
        """에이전트 등록"""
        self._agents[agent.name] = agent

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
        user_input = state["user_input"]
        session_id = state["session_id"]

        # 단기기억에서 최근 대화 로드
        short_term = await self._memory.get_short_term(session_id, limit=5)

        # 장기기억에서 유사 과거 작업 검색
        memory_context = self._memory.search_all_memories(user_input, limit=5)

        # 단기기억에 현재 입력 저장
        await self._memory.save_short_term(
            session_id, "user", user_input, {"task_id": state["task_id"]}
        )

        return {
            **state,
            "memory_context": memory_context,
            "created_at": datetime.utcnow().isoformat(),
        }

    async def _decompose_node(self, state: ManagerState) -> ManagerState:
        """명령을 서브태스크로 분해"""
        user_input = state["user_input"]
        memory_context = state.get("memory_context", [])

        # 분해 프롬프트
        decompose_prompt = self._get_decompose_prompt(user_input, memory_context)

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
        subtasks = state["subtasks"]
        execution_mode = state["execution_mode"]

        results = []

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
            results = await self._execute_parallel(subtasks)
        else:
            # 순차 실행
            results = await self._execute_sequential(subtasks)

        return {
            **state,
            "dispatch_results": results,
        }

    async def _aggregate_node(self, state: ManagerState) -> ManagerState:
        """에이전트 결과 취합 (context_guard 적용)"""
        results = guard_results(state["dispatch_results"])  # 토큰 폭탄 방지
        user_input = state["user_input"]

        if len(results) == 1:
            aggregated = results[0]["output"]
        else:
            # 여러 결과 통합
            aggregated = await self._aggregate_results(user_input, results)

        return {
            **state,
            "aggregated_output": aggregated,
        }

    async def _reflect_node(self, state: ManagerState) -> ManagerState:
        """전체 작업 반성"""
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
                )

        return state

    async def _respond_node(self, state: ManagerState) -> ManagerState:
        """최종 응답 생성"""
        aggregated = state["aggregated_output"]

        # 단기기억에 응답 저장
        await self._memory.save_short_term(
            state["session_id"],
            "assistant",
            aggregated,
            {"task_id": state["task_id"]},
        )

        return {
            **state,
            "final_response": aggregated,
            "completed_at": datetime.utcnow().isoformat(),
        }

    # ===== 실행 메서드 =====

    async def _execute_parallel(self, subtasks: list[SubTask]) -> list[AgentResult]:
        """병렬 실행"""
        tasks = []
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

    async def _execute_sequential(self, subtasks: list[SubTask]) -> list[AgentResult]:
        """순차 실행 (의존성 고려, context_guard 적용)"""
        results = []
        context = []

        for subtask in subtasks:
            agent_name = subtask["assigned_agent"]

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

    async def _generate_direct_response(self, user_input: str) -> str:
        """직접 응답 생성 (에이전트 불필요한 경우)"""
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": user_input}],
        )
        return response.content[0].text

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
        return """너는 JINXUS야. 주인님(진수)을 모시는 충실한 AI 비서.

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
- JX_WRITER: 글쓰기, 문서화, 자소서
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

    def _get_decompose_prompt(self, user_input: str, memory_context: list) -> str:
        """분해 프롬프트"""
        memory_str = ""
        if memory_context:
            memory_str = "\n## 참고: 과거 유사 작업\n"
            for mem in memory_context[:3]:
                memory_str += f"- {mem.get('summary', '')[:100]}\n"

        return f"""## 진수의 명령
{user_input}
{memory_str}

## 가용 에이전트
- JX_CODER: 코드 작성, 실행, 디버깅
- JX_RESEARCHER: 웹 검색, 정보 분석, 요약
- JX_WRITER: 글쓰기, 문서화, 자소서
- JX_ANALYST: 데이터 분석, 시각화, 통계
- JX_OPS: 파일, GitHub, 스케줄 관리

## 지시
위 명령을 분석하고 다음 JSON으로만 응답해:

```json
{{
  "subtasks": [
    {{
      "task_id": "sub_001",
      "assigned_agent": "JX_CODER",
      "instruction": "에이전트에게 전달할 구체적 지시",
      "depends_on": [],
      "priority": "normal"
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

    async def run(self, user_input: str, session_id: str = None) -> dict:
        """JINXUS_CORE 실행

        Args:
            user_input: 진수의 명령
            session_id: 세션 ID (없으면 자동 생성)

        Returns:
            실행 결과 딕셔너리
        """
        if not session_id:
            session_id = str(uuid.uuid4())

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
            "created_at": "",
            "completed_at": "",
            "task_id": str(uuid.uuid4()),
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

        # === 1. intake (메모리 로드) ===
        yield {"event": "manager_thinking", "data": {"step": "intake"}}

        short_term = await self._memory.get_short_term(session_id, limit=5)
        memory_context = self._memory.search_all_memories(user_input, limit=5)
        await self._memory.save_short_term(session_id, "user", user_input, {"task_id": task_id})

        # === 2. decompose (명령 분해) ===
        yield {"event": "manager_thinking", "data": {"step": "decompose"}}

        decompose_prompt = self._get_decompose_prompt(user_input, memory_context)
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
            yield {"event": "agent_started", "data": {"agent": "JINXUS_CORE"}}

            # 모델 라우팅: 단순 대화는 sonnet, 복잡한 작업은 opus
            selected_model = select_model_for_core(user_input)

            # messages.stream() 사용하여 토큰 단위 스트리밍
            full_response = ""
            with self._client.messages.stream(
                model=selected_model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": user_input}],
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

        else:
            # 에이전트 실행
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
                )

        # 단기기억 저장
        final_response = results[0]["output"] if results else ""
        await self._memory.save_short_term(session_id, "assistant", final_response[:500], {"task_id": task_id})

        # 완료 이벤트
        yield {
            "event": "done",
            "data": {
                "task_id": task_id,
                "agents_used": list(set(agents_used)) if agents_used else ["JINXUS_CORE"],
                "success": all(r["success"] for r in results) if results else True,
            },
        }
