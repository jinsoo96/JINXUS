"""JX_RESEARCHER - 리서치팀 오케스트레이터

JX_RESEARCHER는 리서치 작업의 총괄 팀장이다.
단순 검색은 직접 처리하지만, 복잡한 조사는 전문가 팀에게 분배한다.

전문가 팀:
- JX_WEB_SEARCHER: 웹/뉴스 검색, 실시간 정보 수집
- JX_DEEP_READER: 문서/PDF/이미지 심층 분석
- JX_FACT_CHECKER: 교차 검증, 출처 신뢰도 평가

작업 흐름:
1. 작업 분류 → 직접 처리 or 전문가 배치
2. 전문가 배치 (병렬 가능)
3. 결과 수집 → 교차 검증 (선택)
4. 최종 결과 취합 → JINXUS_CORE에 보고

v2.0: DynamicToolExecutor 통합
v2.1: 출력 정제 (XML 태그 제거)
v3.0: 리서치팀 오케스트레이터 승격
"""
import asyncio
import json
import logging
import uuid
import time
import re
from typing import Optional

import httpx
from anthropic import Anthropic
from tavily import TavilyClient

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_dynamic_executor, DynamicToolExecutor
from jinxus.agents.state_tracker import get_state_tracker, GraphNode

logger = logging.getLogger("jinxus.agents.jx_researcher")


class JXResearcher:
    """리서치팀 오케스트레이터

    단순 검색은 직접 처리, 복잡한 조사는 전문가 팀에게 분배.

    블루프린트 그래프 구조:
    [receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                              ↑             │
                              └──[retry]────┘  (최대 3회)
    """

    name = "JX_RESEARCHER"
    description = "리서치팀 총괄 오케스트레이터 (웹검색/문서분석/팩트체크 전문가 팀 보유)"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._tavily_key = settings.tavily_api_key
        self._tavily: Optional[TavilyClient] = None
        self._naver_client_id = settings.naver_client_id
        self._naver_client_secret = settings.naver_client_secret
        self._memory = get_jinx_memory()
        self._prompt_version = "v3.0"  # 팀 오케스트레이터 버전
        # 동적 도구 실행기 (MCP 포함)
        self._executor: Optional[DynamicToolExecutor] = None
        self._use_dynamic_tools = settings.use_dynamic_tools if hasattr(settings, 'use_dynamic_tools') else True
        # 상태 추적기 (실시간 UI 연동)
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)
        self._progress_callback = None

        # 전문가 팀 (지연 초기화)
        self._specialists: dict = {}
        self._specialists_initialized = False

    def _get_executor(self) -> DynamicToolExecutor:
        """동적 도구 실행기 지연 로드"""
        if self._executor is None:
            self._executor = get_dynamic_executor(self.name)
        return self._executor

    def _init_specialists(self):
        """전문가 팀 지연 초기화"""
        if self._specialists_initialized:
            return
        try:
            from jinxus.agents.research import RESEARCH_SPECIALISTS
            for name, cls in RESEARCH_SPECIALISTS.items():
                self._specialists[name] = cls()
                logger.info(f"[JX_RESEARCHER] 전문가 등록: {name}")
            self._specialists_initialized = True
        except Exception as e:
            logger.error(f"[JX_RESEARCHER] 전문가 팀 초기화 실패: {e}")

    async def _decompose_research(self, instruction: str) -> dict:
        """리서치 작업을 분석하여 전문가 배치 계획 수립"""
        decompose_prompt = f"""리서치 작업을 분석하여 전문가 배치를 결정해.

작업: "{instruction}"

사용 가능한 전문가:
- JX_WEB_SEARCHER: 웹/뉴스 검색, 실시간 정보 수집 (날씨, 주가, 뉴스, 트렌드 등)
- JX_DEEP_READER: 문서/PDF/이미지 심층 분석, 웹페이지 깊은 내용 파악, GitHub 소스코드 분석
- JX_FACT_CHECKER: 교차 검증, 출처 신뢰도 평가, 정보 정확성 확인

판단 기준:
- 단순 검색 (날씨, 뉴스, 시세 등): "direct" (내가 직접 처리)
- 깊은 조사 (비교 분석, 논문 리뷰 등): 전문가 2명 이상 배치
- 문서/코드 분석: JX_DEEP_READER 배치
- 중요한 사실 확인이 필요한 경우: needs_verification=true → JX_FACT_CHECKER 후속
- 여러 출처 수집 + 분석: JX_WEB_SEARCHER → JX_DEEP_READER 순차

JSON으로 답변:
{{
    "mode": "direct 또는 delegate",
    "specialists": ["필요한 전문가 이름"],
    "tasks": [
        {{"agent": "전문가 이름", "instruction": "구체적인 지시사항"}}
    ],
    "needs_verification": true/false,
    "execution": "parallel 또는 sequential",
    "reason": "판단 이유 한 줄"
}}"""

        try:
            response = self._client.messages.create(
                model=self._fast_model,
                max_tokens=500,
                messages=[{"role": "user", "content": decompose_prompt}],
            )
            text = response.content[0].text

            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
        except Exception as e:
            logger.warning(f"[JX_RESEARCHER] 작업 분해 실패, 직접 처리: {e}")

        return {
            "mode": "direct",
            "specialists": [],
            "tasks": [],
            "needs_verification": False,
            "execution": "parallel",
            "reason": "분해 실패, 직접 처리",
        }

    async def _report_progress(self, message: str, agent_name: str = None):
        """진행 상황 보고"""
        if self._progress_callback:
            try:
                await self._progress_callback(message)
            except Exception as e:
                logger.debug(f"[JX_RESEARCHER] 프로그레스 콜백 실패: {e}")

    async def _run_specialist(
        self, agent_name: str, instruction: str, context: list = None
    ) -> dict:
        """전문가 에이전트 실행 (실패 시 직접 처리 fallback)"""
        specialist = self._specialists.get(agent_name)
        if not specialist:
            logger.warning(f"[JX_RESEARCHER] 전문가 {agent_name} 없음, 직접 처리로 전환")
            return await self._fallback_direct(agent_name, instruction, context)

        # 프로그레스 콜백 전달
        if self._progress_callback:
            specialist._progress_callback = self._progress_callback

        await self._report_progress(f"[{agent_name}] 작업 시작", agent_name=agent_name)

        try:
            result = await specialist.run(instruction, context)
            status = "완료" if result.get("success") else "실패"
            await self._report_progress(f"[{agent_name}] {status}", agent_name=agent_name)

            if not result.get("success"):
                logger.warning(f"[JX_RESEARCHER] {agent_name} 실패, 직접 처리 시도")
                await self._report_progress(f"[{agent_name}] 실패 → JX_RESEARCHER 직접 처리로 전환")
                fallback = await self._fallback_direct(agent_name, instruction, context)
                if fallback.get("success"):
                    return fallback
            return result
        except Exception as e:
            logger.error(f"[JX_RESEARCHER] {agent_name} 실행 예외: {e}")
            await self._report_progress(f"[{agent_name}] 예외 → 직접 처리 전환")
            return await self._fallback_direct(agent_name, instruction, context)

    async def _fallback_direct(
        self, agent_name: str, instruction: str, context: list = None
    ) -> dict:
        """전문가 실패 시 JX_RESEARCHER가 직접 처리"""
        start_time = time.time()
        try:
            result = await self._execute_with_retry(instruction, context or [], [])
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "task_id": str(uuid.uuid4()),
                "agent_name": f"{agent_name}(fallback→JX_RESEARCHER)",
                "success": result.get("success", False),
                "success_score": result.get("score", 0.5),
                "output": result.get("output", ""),
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
            }
        except Exception as e:
            logger.error(f"[JX_RESEARCHER] fallback 직접 처리도 실패: {e}")
            return {
                "task_id": str(uuid.uuid4()),
                "agent_name": f"{agent_name}(fallback→JX_RESEARCHER)",
                "success": False,
                "success_score": 0.0,
                "output": f"전문가 및 직접 처리 모두 실패: {e}",
                "failure_reason": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }

    async def _execute_delegated(
        self, plan: dict, instruction: str, context: list
    ) -> dict:
        """전문가 팀에게 위임 실행"""
        self._init_specialists()

        tasks = plan.get("tasks", [])
        execution = plan.get("execution", "parallel")
        needs_verification = plan.get("needs_verification", False)

        if not tasks:
            specialists = plan.get("specialists", [])
            tasks = [{"agent": s, "instruction": instruction} for s in specialists]

        # === 1단계: 메인 작업 실행 ===
        await self._report_progress(
            f"리서치팀 배치: {', '.join(t['agent'] for t in tasks)} ({execution})"
        )

        main_results = []

        if execution == "parallel" and len(tasks) > 1:
            coros = [
                self._run_specialist(t["agent"], t["instruction"], context)
                for t in tasks
            ]
            main_results = await asyncio.gather(*coros, return_exceptions=True)
            main_results = [
                r if isinstance(r, dict) else {
                    "agent_name": tasks[i]["agent"],
                    "success": False,
                    "output": str(r),
                    "failure_reason": str(r),
                }
                for i, r in enumerate(main_results)
            ]
        else:
            accumulated_context = list(context) if context else []
            for task in tasks:
                result = await self._run_specialist(
                    task["agent"], task["instruction"], accumulated_context
                )
                main_results.append(result)
                if result.get("success"):
                    accumulated_context.append(result)

        # === 2단계: 교차 검증 (선택) ===
        verification_results = []

        if needs_verification and "JX_FACT_CHECKER" in self._specialists:
            main_outputs = [r for r in main_results if r.get("success")]
            if main_outputs:
                info_summary = "\n\n".join(
                    f"### {r.get('agent_name', '?')} 수집 결과:\n{r.get('output', '')[:1000]}"
                    for r in main_outputs
                )
                verify_instruction = (
                    f"아래 수집된 정보의 정확성을 교차 검증해줘.\n\n"
                    f"원본 요청: {instruction}\n\n{info_summary}"
                )
                await self._report_progress("교차 검증 단계: JX_FACT_CHECKER")
                verify_result = await self._run_specialist(
                    "JX_FACT_CHECKER", verify_instruction, main_results
                )
                verification_results.append(verify_result)

        # === 3단계: 결과 취합 ===
        all_results = main_results + verification_results
        all_success = all(r.get("success", False) for r in main_results)
        avg_score = (
            sum(r.get("success_score", 0.0) for r in all_results) / len(all_results)
            if all_results else 0.0
        )

        output_parts = []
        for r in all_results:
            agent = r.get("agent_name", "?")
            status = "성공" if r.get("success") else "실패"
            output_parts.append(
                f"### [{agent}] {status}\n{r.get('output', '결과 없음')[:2000]}"
            )

        combined_output = "\n\n---\n\n".join(output_parts)

        return {
            "success": all_success,
            "score": avg_score,
            "output": combined_output,
            "error": None if all_success else "일부 전문가 작업 실패",
            "sources": [],
            "tool_calls": [],
            "specialists_used": [t["agent"] for t in tasks],
        }

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

        return f"""<identity>
너는 JX_RESEARCHER다. JINXUS의 정보 수집 전문가.
</identity>

<metadata>
오늘은 {today}이다. "내일"은 이 날짜 기준 다음 날이다.
주인님은 서울에 거주한다. 지역 미지정 시 서울 기준.
</metadata>

<tool_usage>
- 답변 전 반드시 도구를 호출하여 정보를 수집한다. 예외 없음.
- 도구 없이 정보를 지어내는 것은 절대 금지.
- 검색 쿼리를 구체적으로 작성한다:
  - 지역 미지정 시 "서울" 추가 ("날씨" → "서울 날씨")
  - 날짜 명시 ("내일 날씨" → "서울 {today} 기준 내일 날씨 예보")
- 검색 결과에서 질문과 무관한 정보(다른 지역, 다른 날짜)는 버린다.

### GitHub 관련 작업 (중요!)
- GitHub 레포지토리/커밋/PR/이슈/소스코드 조회: **반드시 `github_agent` 도구 사용**
- 소스코드 분석 요청 시:
  1. `github_agent`(action="get_contents", repo="owner/repo") → 디렉토리 구조 파악
  2. `github_agent`(action="get_file", repo="owner/repo", path="파일경로") → 주요 파일 내용 읽기
  3. 읽은 코드를 분석하여 보고
- 커밋 조회: `github_agent`(action="list_commits", repo="owner/repo" 또는 username="사용자명")
- 레포 목록: `github_agent`(action="list_user_repos", username="사용자명")
- **mcp__github__* 도구는 사용 금지** (deprecated)
- 한 번 실패해도 포기하지 말고 다른 action이나 파라미터로 재시도할 것
</tool_usage>

<output_rules>
- 간단한 질문에는 간단하게 답한다. 날씨/환율 같은 건 2-3줄이면 충분.
- 출처 URL은 1-2개만. 5개씩 나열 금지.
- XML 태그를 텍스트로 출력하지 않는다.
- 도구 호출 과정을 보여주지 않는다.
- 금지 표현: "검색 결과에 따르면", "조사해본 결과"
- **절대 금지**: 내부 도구명(mcp_*, web_searcher, github_agent 등), MCP 서버 설정, API 키, 시스템 설정 파일명을 사용자에게 노출하지 않는다.
- 도구 사용이 불가능하면 기술적 이유 대신 "현재 해당 정보를 조회할 수 없습니다"라고 간단히 안내한다.
- 자신을 "JX_RESEARCHER"라고 밝히지 않는다. "JINXUS"로서 답한다.
</output_rules>

<tone>
- "주인님"이라고 부른다. 공손한 존댓말.
</tone>
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
            except Exception as e:
                logger.warning(f"[JXResearcher] 장기 메모리 검색 실패, 컨텍스트 없이 진행: {e}")

            # === [plan] 작업 분해 → 직접 처리 or 팀 위임 ===
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            plan = await self._decompose_research(instruction)
            logger.info(f"[JX_RESEARCHER] 작업 모드: {plan.get('mode')} - {plan.get('reason', '')}")

            # === [execute] + [evaluate] + [retry] ===
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)

            if plan["mode"] == "delegate" and plan.get("specialists"):
                await self._report_progress(
                    f"리서치 계획: {plan.get('reason', '전문가 팀 배치')}"
                )
                result = await self._execute_delegated(plan, instruction, context or [])
            else:
                self._state_tracker.update_tools(self.name, ["naver", "tavily", "brave-search"])
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
                model=self._fast_model,
                max_tokens=10,
                messages=[{"role": "user", "content": classify_prompt}],
            )
            result = response.content[0].text.strip().lower()
            # simple이 아니면 MCP 필요
            return "simple" not in result
        except Exception:
            return False  # 에러 시 안전하게 Tavily 사용

    def _is_weather_query(self, instruction: str) -> tuple[bool, str]:
        """날씨 쿼리인지 판별하고, 지역명 추출"""
        weather_keywords = ["날씨", "기온", "비 오", "비오", "눈 오", "눈오", "미세먼지", "weather", "기상"]
        lower = instruction.lower()
        if not any(k in lower for k in weather_keywords):
            return False, ""

        # 서울 구 이름 추출
        from jinxus.tools.weather import SEOUL_DISTRICTS
        for district in SEOUL_DISTRICTS:
            if district in instruction:
                return True, district

        # "서울" 언급되거나 지역 미지정
        return True, "서울"

    async def _get_weather(self, location: str) -> Optional[dict]:
        """OpenWeatherMap으로 날씨 직접 조회"""
        try:
            from jinxus.tools.weather import WeatherTool
            weather_tool = WeatherTool()
            result = await weather_tool.run({"location": location, "mode": "forecast"})
            if result.success:
                return result.output
        except Exception as e:
            logger.warning(f"날씨 API 조회 실패: {e}")
        return None

    async def _execute(
        self, instruction: str, context: list, memory_context: list, last_error: str = None
    ) -> dict:
        """단일 실행 — DynamicToolExecutor로 통일 (weather, naver, tavily, MCP 모두 도구로 등록됨)"""
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도에서 오류 발생: {last_error}\n다른 접근 방식으로 시도해줘."

        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 검색\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        # === DynamicToolExecutor: Claude가 도구를 자동 선택 ===
        # weather, naver_searcher, web_searcher, MCP 도구 전부 사용 가능
        if self._use_dynamic_tools:
            result = await self._execute_with_dynamic_tools(
                instruction, memory_str, error_context
            )
            if result["success"]:
                return result
            logger.warning(f"DynamicToolExecutor 실패, 직접 검색 폴백: {result.get('error')}")

        # === 폴백: 직접 네이버/Tavily 검색 ===
        search_results = await self._search(instruction)

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
            # 검색 실패 — 할루시네이션 방지: 실패로 보고
            logger.warning(f"JX_RESEARCHER 웹 검색 실패: {instruction[:100]}")
            return {
                "success": False,
                "score": 0.2,
                "output": "주인님, 웹 검색에 실패했습니다. 검색 도구가 정상 작동하지 않는 상태입니다.",
                "error": "웹 검색 실패 (Brave Search + Tavily 모두 불가)",
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

            # 도구 호출 콜백 (실시간 이벤트)
            tool_cb = None
            if hasattr(self, '_progress_callback') and self._progress_callback:
                cb = self._progress_callback
                async def tool_cb(tool_name: str, status: str):
                    if status == "calling":
                        await cb(f"🔧 [{self.name}] {tool_name} 호출 중...")
                    elif status == "error":
                        await cb(f"❌ [{self.name}] {tool_name} 실패")

            result = await executor.execute(
                instruction=instruction,
                system_prompt=system_prompt,
                context=context,
                tool_callback=tool_cb,
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
                # 도구 실패해도 부분 결과가 있으면 전달
                partial = ""
                for r in result.raw_results:
                    if r.get("output"):
                        partial += str(r["output"])[:300] + "\n"
                fallback_output = partial.strip() if partial else f"도구 실행에 실패했습니다: {result.error or '알 수 없는 오류'}"
                return {
                    "success": bool(partial),
                    "score": 0.3 if partial else 0.0,
                    "output": fallback_output,
                    "error": result.error,
                    "tool_calls": [tc.tool_name for tc in result.tool_calls] if result.tool_calls else [],
                }

        except Exception as e:
            return {
                "success": False,
                "score": 0.0,
                "output": f"리서치 실행 중 오류가 발생했습니다: {str(e)[:200]}",
                "error": str(e),
                "tool_calls": [],
            }

    async def _search(self, query: str) -> list:
        """네이버 우선 검색, 실패 시 Tavily 폴백"""
        # 1차: 네이버 검색 (한국어에 최적화)
        if self._naver_client_id and self._naver_client_secret:
            naver_results = await self._search_naver(query)
            if naver_results:
                logger.info(f"네이버 검색 성공: {len(naver_results)}건")
                return naver_results

        # 2차: Tavily 폴백
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
        except Exception as e:
            logger.error(f"Tavily 검색 실패: {e}")
            return []

    async def _search_naver(self, query: str) -> list:
        """네이버 검색 API - 웹 + 뉴스 병합"""
        try:
            headers = {
                "X-Naver-Client-Id": self._naver_client_id,
                "X-Naver-Client-Secret": self._naver_client_secret,
            }
            params = {"query": query, "display": 5, "start": 1, "sort": "sim"}

            # 한국어 키워드 감지로 카테고리 결정
            news_keywords = ["뉴스", "소식", "사건", "사고", "속보"]
            categories = ["webkr"]
            if any(k in query for k in news_keywords):
                categories = ["news", "webkr"]

            all_results = []
            async with httpx.AsyncClient(timeout=10.0) as client:
                for category in categories:
                    url = f"https://openapi.naver.com/v1/search/{category}"
                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                    for item in data.get("items", []):
                        title = re.sub(r"<[^>]+>", "", item.get("title", ""))
                        content = re.sub(r"<[^>]+>", "", item.get("description", ""))
                        all_results.append({
                            "title": title,
                            "url": item.get("originallink") or item.get("link", ""),
                            "content": content,
                            "published_date": item.get("pubDate"),
                            "score": 1.0,
                        })

            return all_results[:10]

        except Exception as e:
            logger.warning(f"네이버 검색 실패, Tavily로 폴백: {e}")
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
        except Exception as e:
            logger.warning(f"[JXResearcher] 장기 메모리 저장 실패 (결과 반환은 정상): {e}")
