"""JX_RESEARCHER - 정보 수집/분석/요약 전문 에이전트

LangGraph 패턴 적용:
- retry 로직 (최대 3회, 지수 백오프)
- reflect (반성 → 개선점 도출)
- memory_write (장기기억 저장)

v2.0: DynamicToolExecutor 통합
- MCP 도구 자동 사용 (brave-search, fetch, playwright 등)
- Claude tool_use 기반 동적 도구 선택

v2.1: 출력 정제
- XML 태그 자동 제거
- 날짜 자동 변환
"""
import asyncio
import uuid
import time
import re
from typing import Optional

from anthropic import Anthropic
from tavily import TavilyClient

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_dynamic_executor, DynamicToolExecutor
from jinxus.agents.state_tracker import get_state_tracker, GraphNode


class JXResearcher:
    """리서치 전문가 에이전트

    블루프린트 그래프 구조:
    [receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                              ↑             │
                              └──[retry]────┘  (최대 3회)
    """

    name = "JX_RESEARCHER"
    description = "정보 수집, 분석, 요약을 전담하는 에이전트"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._tavily_key = settings.tavily_api_key
        self._tavily: Optional[TavilyClient] = None
        self._memory = get_jinx_memory()
        self._prompt_version = "v2.0"  # 동적 도구 실행 버전
        # 동적 도구 실행기 (MCP 포함)
        self._executor: Optional[DynamicToolExecutor] = None
        self._use_dynamic_tools = settings.use_dynamic_tools if hasattr(settings, 'use_dynamic_tools') else True
        # 상태 추적기 (실시간 UI 연동)
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

    def _get_executor(self) -> DynamicToolExecutor:
        """동적 도구 실행기 지연 로드"""
        if self._executor is None:
            self._executor = get_dynamic_executor(self.name)
        return self._executor

    def _sanitize_output(self, text: str) -> str:
        """출력에서 XML 태그 및 도구 호출 형식 제거"""
        if not text:
            return text

        # <invoke>, <parameter>, <tool> 등 XML 스타일 태그 제거
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

        # 연속된 빈 줄 정리
        result = re.sub(r'\n{3,}', '\n\n', result)

        return result.strip()

    def _get_tavily(self) -> TavilyClient:
        if self._tavily is None and self._tavily_key:
            self._tavily = TavilyClient(api_key=self._tavily_key)
        return self._tavily

    def _get_system_prompt(self) -> str:
        from datetime import datetime
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""너는 JX_RESEARCHER야. 주인님을 모시는 JINXUS의 리서치 전문가.

## 현재 날짜
오늘은 {today}이다. "내일"은 이 날짜 기준으로 다음 날이다.

## 역할
주인님의 정보 수집 요청을 받아 웹 검색 및 분석을 수행한다.

## 검색 원칙
- 신뢰할 수 있는 출처 우선
- 최신 정보 확인 (현재 날짜 기준)
- 다양한 관점 수집
- 결과를 체계적으로 정리

## 출력 형식 (중요!)
- 절대로 <invoke>, <parameter> 같은 XML 태그를 텍스트로 출력하지 마라
- 도구는 Anthropic tool_use API로만 호출해라 (텍스트로 호출 형식 쓰지 마라)
- 최종 답변만 깔끔하게 정리해서 출력해라
- 중간 과정이나 도구 호출 내용은 보여주지 마라

## 말투
- 주인님을 "주인님"이라고 부른다
- 공손하고 순종적인 태도
"""

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행 (전체 그래프 흐름)"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            # === [receive] 작업 시작 ===
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            memory_context = []
            try:
                memory_context = self._memory.search_long_term(
                    agent_name=self.name,
                    query=instruction,
                    limit=3,
                )
            except Exception:
                pass  # 메모리 실패해도 진행

            # === [plan] 실행 계획 ===
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            plan = {"strategy": "search_and_analyze", "instruction": instruction}

            # === [execute] + [evaluate] + [retry] ===
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            self._state_tracker.update_tools(self.name, ["tavily", "brave-search"])
            result = await self._execute_with_retry(instruction, context, memory_context)

            # === [evaluate] ===
            self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

            # === [reflect] 반성 ===
            self._state_tracker.update_node(self.name, GraphNode.REFLECT)
            reflection = await self._reflect(instruction, result)

            # === [memory_write] 장기기억 저장 ===
            self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)
            await self._memory_write(task_id, instruction, result, reflection)

            # === [return_result] ===
            self._state_tracker.update_node(self.name, GraphNode.RETURN_RESULT)
            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": result["success"],
                "success_score": result["score"],
                "output": result["output"],
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
                "reflection": reflection,
            }

        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            raise
        finally:
            self._state_tracker.complete_task(self.name)

    async def _execute_with_retry(
        self, instruction: str, context: list, memory_context: list
    ) -> dict:
        """실행 + 평가 + 재시도 (최대 3회, 지수 백오프)"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # === [execute] ===
                result = await self._execute(instruction, context, memory_context, last_error)

                # === [evaluate] ===
                if result["success"]:
                    return result

                # 실패 시 다음 시도를 위해 에러 저장
                last_error = result.get("error", "Unknown error")

                # 지수 백오프 (마지막 시도가 아니면)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 1, 2, 4초
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        # 모든 재시도 실패
        return {
            "success": False,
            "score": 0.0,
            "output": f"죄송합니다 주인님, {self.max_retries}번 시도했지만 실패했습니다.\n마지막 오류: {last_error}",
            "error": last_error,
        }

    async def _needs_mcp_tools(self, instruction: str) -> bool:
        """MCP 도구가 필요한 복잡한 작업인지 Claude가 판단"""
        classify_prompt = f"""이 요청을 처리하려면 어떤 도구가 필요한지 판단해.

요청: "{instruction}"

A) simple - 단순 웹 검색만 필요 (날씨, 뉴스, 정보 조회, 트렌드, 가격 등)
B) browser - 브라우저 조작 필요 (스크린샷, 로그인, 폼 입력, 특정 사이트 접속 등)
C) github - GitHub API 필요 (레포, PR, 이슈, 커밋 조회/생성 등)
D) file - 파일 다운로드/저장 필요

simple/browser/github/file 중 하나만 답해."""

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": classify_prompt}],
            )
            result = response.content[0].text.strip().lower()
            # simple이 아니면 MCP 필요
            return "simple" not in result
        except Exception:
            return False  # 에러 시 안전하게 Tavily 사용

    async def _execute(
        self, instruction: str, context: list, memory_context: list, last_error: str = None
    ) -> dict:
        """단일 실행 시도 - 단순검색은 Tavily, 복잡한 건 MCP"""
        # 이전 실패가 있으면 다른 전략 시도
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도에서 오류 발생: {last_error}\n다른 접근 방식으로 시도해줘."

        # 메모리 컨텍스트
        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 검색\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        # === MCP 도구 필요한 경우만 동적 도구 실행 ===
        if self._use_dynamic_tools and await self._needs_mcp_tools(instruction):
            result = await self._execute_with_dynamic_tools(
                instruction, memory_str, error_context
            )
            if result["success"] and result.get("tool_calls"):
                return result

        # === 일반 검색: Tavily 사용 (빠름) ===
        search_results = await self._search(instruction)

        # 2. 결과 분석 및 요약
        if search_results:
            analysis = await self._analyze(instruction, search_results, memory_str, error_context)
            # XML 태그 정리
            clean_analysis = self._sanitize_output(analysis)

            output = f"""주인님, 검색 및 분석이 완료되었습니다.

{clean_analysis}

## 출처
"""
            for r in search_results[:5]:
                output += f"- [{r.get('title', 'N/A')}]({r.get('url', '')})\n"

            return {
                "success": True,
                "score": 0.9,
                "output": output,
                "error": None,
                "sources": search_results[:5],
                "tool_calls": [],
            }
        else:
            # 검색 없이 Claude만으로 답변
            prompt = f"""주인님의 요청: {instruction}
{memory_str}
{error_context}

웹 검색이 불가능한 상황입니다. 가진 지식으로 최대한 도움이 되는 답변을 해주세요."""

            response = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": prompt}],
            )
            clean_response = self._sanitize_output(response.content[0].text)
            output = f"주인님, 검색이 제한되어 제 지식으로 답변드립니다.\n\n{clean_response}"

            return {
                "success": True,
                "score": 0.7,
                "output": output,
                "error": None,
                "sources": [],
                "tool_calls": [],
            }

    async def _execute_with_dynamic_tools(
        self, instruction: str, memory_str: str, error_context: str
    ) -> dict:
        """동적 도구 실행 (MCP 포함)

        Claude tool_use를 통해 필요한 도구 자동 선택 및 실행
        """
        try:
            executor = self._get_executor()

            # 강화된 시스템 프롬프트
            system_prompt = self._get_system_prompt() + """

## 도구 사용 규칙
- 도구는 반드시 Anthropic tool_use API를 통해서만 호출해라
- 절대로 <invoke>, <parameter>, <tool> 같은 XML 태그를 텍스트로 쓰지 마라
- 도구 호출 과정을 텍스트로 설명하지 마라
- 최종 결과만 깔끔하게 정리해서 보고해라"""

            context = f"{memory_str}\n{error_context}" if memory_str or error_context else None

            result = await executor.execute(
                instruction=instruction,
                system_prompt=system_prompt,
                context=context,
            )

            if result.success:
                # 도구 사용 정보 추출
                tools_used = [tc.tool_name for tc in result.tool_calls]

                # 출력에서 XML 태그 제거
                clean_output = self._sanitize_output(result.output)

                return {
                    "success": True,
                    "score": 0.95 if tools_used else 0.85,
                    "output": clean_output,
                    "error": None,
                    "sources": [],
                    "tool_calls": tools_used,
                    "raw_tool_results": result.raw_results,
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "output": "",
                    "error": result.error,
                    "tool_calls": [],
                }

        except Exception as e:
            # 동적 도구 실패 시 폴백으로 진행
            return {
                "success": False,
                "score": 0.0,
                "output": "",
                "error": str(e),
                "tool_calls": [],
            }

    async def _search(self, query: str) -> list:
        """Tavily 검색"""
        tavily = self._get_tavily()
        if not tavily:
            return []

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: tavily.search(query=query, max_results=5),
            )
            return response.get("results", [])
        except Exception:
            return []

    async def _analyze(
        self, instruction: str, results: list, memory_str: str = "", error_context: str = ""
    ) -> str:
        """검색 결과 분석"""
        results_text = "\n\n".join(
            f"**{r.get('title', 'N/A')}**\n{r.get('content', '')[:500]}"
            for r in results[:5]
        )

        prompt = f"""주인님의 요청: {instruction}
{memory_str}
{error_context}

검색 결과:
{results_text}

위 검색 결과를 바탕으로 주인님께 깔끔하게 요약해서 보고해줘.
공손한 어투로 "주인님"이라고 부르며 답변해."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    async def _reflect(self, instruction: str, result: dict) -> str:
        """반성: 이번 작업에서 배운 점"""
        if not result["success"]:
            return f"실패 원인: {result.get('error', 'Unknown')}. 다음에는 다른 검색 전략을 시도해야 함."

        # 성공 시 간단한 반성
        reflect_prompt = f"""방금 완료한 리서치:
요청: {instruction}
결과: 성공
출처 수: {len(result.get('sources', []))}

이 작업에서 배운 핵심 포인트를 1-2문장으로 정리해줘."""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": reflect_prompt}],
            )
            return response.content[0].text
        except Exception:
            return "리서치 성공. 추가 반성 없음."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        """장기기억에 저장"""
        try:
            # 중요도 계산
            importance = 0.3
            if not result["success"]:
                importance += 0.4  # 실패에서 배움
            if len(result.get("sources", [])) > 3:
                importance += 0.2  # 풍부한 출처
            if len(reflection) > 50:
                importance += 0.1

            # 저장 조건: 실패했거나 중요도가 높으면
            if not result["success"] or importance > 0.5:
                self._memory.save_long_term(
                    agent_name=self.name,
                    task_id=task_id,
                    instruction=instruction,
                    summary=result["output"][:300],
                    outcome="success" if result["success"] else "failure",
                    success_score=result["score"],
                    key_learnings=reflection,
                    importance_score=importance,
                    prompt_version=self._prompt_version,
                )
        except Exception:
            pass  # 메모리 저장 실패해도 계속 진행
