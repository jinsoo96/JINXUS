"""JX_RESEARCHER - 정보 수집/분석/요약 전문 에이전트

LangGraph 패턴 적용:
- retry 로직 (최대 3회, 지수 백오프)
- reflect (반성 → 개선점 도출)
- memory_write (장기기억 저장)
"""
import asyncio
import uuid
import time
from typing import Optional

from anthropic import Anthropic
from tavily import TavilyClient

from config import get_settings
from memory import get_jinx_memory


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
        self._prompt_version = "v1.0"

    def _get_tavily(self) -> TavilyClient:
        if self._tavily is None and self._tavily_key:
            self._tavily = TavilyClient(api_key=self._tavily_key)
        return self._tavily

    def _get_system_prompt(self) -> str:
        return """너는 JX_RESEARCHER야. 주인님을 모시는 JINXUS의 리서치 전문가.

## 역할
주인님의 정보 수집 요청을 받아 웹 검색 및 분석을 수행한다.

## 검색 원칙
- 신뢰할 수 있는 출처 우선
- 최신 정보 확인
- 다양한 관점 수집
- 결과를 체계적으로 정리

## 말투
- 주인님을 "주인님"이라고 부른다
- 공손하고 순종적인 태도
"""

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행 (전체 그래프 흐름)"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        # === [receive] 과거 경험 로드 ===
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
        plan = {"strategy": "search_and_analyze", "instruction": instruction}

        # === [execute] + [evaluate] + [retry] ===
        result = await self._execute_with_retry(instruction, context, memory_context)

        # === [reflect] 반성 ===
        reflection = await self._reflect(instruction, result)

        # === [memory_write] 장기기억 저장 ===
        await self._memory_write(task_id, instruction, result, reflection)

        # === [return_result] ===
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

    async def _execute(
        self, instruction: str, context: list, memory_context: list, last_error: str = None
    ) -> dict:
        """단일 실행 시도"""
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

        # 1. Tavily 검색 시도
        search_results = await self._search(instruction)

        # 2. 결과 분석 및 요약
        if search_results:
            analysis = await self._analyze(instruction, search_results, memory_str, error_context)
            output = f"""주인님, 검색 및 분석이 완료되었습니다.

{analysis}

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
            output = f"주인님, 검색이 제한되어 제 지식으로 답변드립니다.\n\n{response.content[0].text}"

            return {
                "success": True,
                "score": 0.7,
                "output": output,
                "error": None,
                "sources": [],
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
