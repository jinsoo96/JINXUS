"""JX_CODER - 코딩팀 오케스트레이터

JX_CODER는 코딩 작업의 총괄 팀장이다.
직접 코드를 작성하기도 하지만, 복잡한 작업은 전문가 팀에게 분배한다.

전문가 팀:
- JX_FRONTEND: 프론트엔드 (React, Next.js, Vue, Svelte, Flutter 등)
- JX_BACKEND: 백엔드 (FastAPI, Django, Express, Go, Rust 등)
- JX_INFRA: 인프라 (Docker, K8s, CI/CD, 클라우드 등)
- JX_REVIEWER: 코드 리뷰 (품질, 보안, 성능)
- JX_TESTER: 테스트/검증 (pytest, Jest, 타입 체크 등)

작업 흐름:
1. 작업 분류 → 필요한 전문가 결정
2. 전문가 배치 (병렬 가능)
3. 결과 수집 → 리뷰/테스트 (선택)
4. 최종 결과 취합 → JINXUS_CORE에 보고
"""
import asyncio
import json
import re
import tempfile
import uuid
import time
import logging
from typing import Optional
from pathlib import Path

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools.code_executor import CodeExecutor
from jinxus.tools import get_dynamic_executor, DynamicToolExecutor
from jinxus.agents.state_tracker import get_state_tracker, GraphNode
from jinxus.agents.base_agent import AgentCallbackMixin, _agent_display_name

logger = logging.getLogger(__name__)


class JXCoder(AgentCallbackMixin):
    """코딩팀 오케스트레이터

    간단한 작업은 직접 처리, 복잡한 작업은 전문가 팀에게 분배.
    """

    name = "JX_CODER"
    description = "코딩팀 총괄 오케스트레이터 (프론트/백엔드/인프라/리뷰/테스트 전문가 팀 보유)"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v3.0"  # 팀 오케스트레이터 버전
        self._code_executor = CodeExecutor()
        self._executor: Optional[DynamicToolExecutor] = None
        self._use_dynamic_tools = settings.use_dynamic_tools if hasattr(settings, 'use_dynamic_tools') else True
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)
        self._progress_callback = None

        # 전문가 팀 (지연 초기화)
        self._specialists: dict = {}
        self._specialists_initialized = False

    def _init_specialists(self):
        """전문가 팀 지연 초기화"""
        if self._specialists_initialized:
            return
        try:
            from jinxus.agents.coding import CODING_SPECIALISTS
            for name, cls in CODING_SPECIALISTS.items():
                self._specialists[name] = cls()
                logger.info(f"[JX_CODER] 전문가 등록: {name}")
            self._specialists_initialized = True
        except Exception as e:
            logger.error(f"[JX_CODER] 전문가 팀 초기화 실패: {e}")

    def _get_executor(self) -> DynamicToolExecutor:
        if self._executor is None:
            self._executor = get_dynamic_executor(self.name)
        return self._executor

    async def _decompose_task(self, instruction: str) -> dict:
        """작업을 분석하여 전문가 배치 계획 수립

        Returns:
            {
                "mode": "direct" | "delegate",
                "specialists": ["JX_FRONTEND", "JX_BACKEND", ...],
                "tasks": [{"agent": "JX_FRONTEND", "instruction": "..."}],
                "needs_review": bool,
                "needs_test": bool,
                "execution": "parallel" | "sequential",
                "reason": str,
            }
        """
        decompose_prompt = f"""코딩 작업을 분석하여 전문가 배치를 결정해.

작업: "{instruction}"

사용 가능한 전문가:
- JX_FRONTEND: 프론트엔드 (React, Next.js, Vue, Svelte, CSS, 컴포넌트, UI/UX)
- JX_BACKEND: 백엔드 (FastAPI, Django, Express, DB, API, 인증, 큐)
- JX_INFRA: 인프라 (Docker, CI/CD, 배포, 서버, 모니터링)
- JX_REVIEWER: 코드 리뷰 (품질, 보안, 성능 분석)
- JX_TESTER: 테스트 (단위/통합/E2E, 타입 체크)

판단 기준:
- 단순 스크립트, 단일 파일 작업: "direct" (내가 직접 처리)
- 프론트+백엔드 동시: 전문가 2명 이상 배치
- "리뷰해줘", "코드 리뷰": JX_REVIEWER만 배치
- "테스트", "검증", "타입 체크": JX_TESTER만 배치
- 큰 기능 구현: 전문가 작업 → JX_REVIEWER + JX_TESTER 후속
- 버그/에러/디버깅 작업: mode="debug" 사용 (가설 분기 디버깅)

## 파일 소유권 원칙 (병렬 실행 시 필수)
- 같은 파일을 두 전문가에게 절대 배정하지 마라
- 각 task의 instruction에 담당 파일/디렉토리 범위를 명시하라
- 전문가 간 경계는 인터페이스 계약(함수 시그니처, API 스펙)으로 정의하라

JSON으로 답변:
{{
    "mode": "direct 또는 delegate 또는 debug",
    "specialists": ["필요한 전문가 이름"],
    "tasks": [
        {{"agent": "전문가 이름", "instruction": "구체적이고 self-contained인 지시사항 (담당 파일 범위 포함)", "file_scope": ["담당 파일/디렉토리 패턴"]}}
    ],
    "needs_review": true/false,
    "needs_test": true/false,
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

            # JSON 추출 (LLM 출력의 깨진 JSON 복구 시도)
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                raw = match.group()
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    # 흔한 오류 복구: trailing comma, 한국어 주석 등
                    cleaned = re.sub(r',\s*([}\]])', r'\1', raw)  # trailing comma 제거
                    cleaned = re.sub(r'//.*', '', cleaned)  # 주석 제거
                    result = json.loads(cleaned)
                return result
        except Exception as e:
            logger.warning(f"[JX_CODER] 작업 분해 실패, 직접 처리: {e}")

        # 분해 실패 시 직접 처리
        return {
            "mode": "direct",
            "specialists": [],
            "tasks": [],
            "needs_review": False,
            "needs_test": False,
            "execution": "parallel",
            "reason": "분해 실패, 직접 처리",
        }

    async def _run_specialist(
        self, agent_name: str, instruction: str, context: list = None
    ) -> dict:
        """전문가 에이전트 실행 (실패 시 직접 처리 fallback)"""
        specialist = self._specialists.get(agent_name)
        if not specialist:
            logger.warning(f"[JX_CODER] 전문가 {agent_name} 없음, 직접 처리로 전환")
            return await self._fallback_direct(agent_name, instruction, context)

        # 프로그레스 콜백 전달
        if self._progress_callback:
            specialist._progress_callback = self._progress_callback

        # 전문가 시작 이벤트
        await self._report_progress(
            instruction[:100], agent_name=agent_name, event_type="specialist_started"
        )

        try:
            result = await specialist.run(instruction, context)
            status = "완료" if result.get("success") else "실패"
            output_preview = (result.get("output", "") or "")[:100]
            await self._report_progress(
                f"{status}: {output_preview}", agent_name=agent_name, event_type="specialist_done"
            )

            # 전문가 실패 시 직접 처리 fallback
            if not result.get("success"):
                logger.warning(f"[JX_CODER] {agent_name} 실패, 직접 처리 시도")
                _dn = _agent_display_name(agent_name)
                await self._report_progress(
                    f"[{_dn}] 실패 → 직접 처리로 전환"
                )
                fallback = await self._fallback_direct(agent_name, instruction, context)
                if fallback.get("success"):
                    return fallback
                # fallback도 실패하면 원래 전문가 결과 반환
            return result
        except Exception as e:
            logger.error(f"[JX_CODER] {agent_name} 실행 예외: {e}")
            _dn = _agent_display_name(agent_name)
            await self._report_progress(f"[{_dn}] 예외 → 직접 처리 전환")
            return await self._fallback_direct(agent_name, instruction, context)

    async def _fallback_direct(
        self, agent_name: str, instruction: str, context: list = None
    ) -> dict:
        """전문가 실패 시 JX_CODER가 직접 처리"""
        start_time = time.time()
        try:
            result = await self._execute_with_retry(instruction, context or [])
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "task_id": str(uuid.uuid4()),
                "agent_name": f"{agent_name}(fallback→JX_CODER)",
                "success": result.get("success", False),
                "success_score": result.get("score", 0.5),
                "output": result.get("output", ""),
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
            }
        except Exception as e:
            logger.error(f"[JX_CODER] fallback 직접 처리도 실패: {e}")
            return {
                "task_id": str(uuid.uuid4()),
                "agent_name": f"{agent_name}(fallback→JX_CODER)",
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
        needs_review = plan.get("needs_review", False)
        needs_test = plan.get("needs_test", False)

        if not tasks:
            # 전문가 목록만 있고 tasks가 없는 경우
            specialists = plan.get("specialists", [])
            tasks = [{"agent": s, "instruction": instruction} for s in specialists]

        # === 1단계: 메인 작업 실행 ===
        await self._report_progress(
            f"전문가 팀 배치: {', '.join(t['agent'] for t in tasks)} ({execution})"
        )

        main_results = []

        if execution == "parallel" and len(tasks) > 1:
            # 병렬 실행
            coros = [
                self._run_specialist(t["agent"], t["instruction"], context)
                for t in tasks
            ]
            main_results = await asyncio.gather(*coros, return_exceptions=True)
            # 예외를 결과로 변환
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
            # 순차 실행 (이전 결과를 컨텍스트로 전달)
            accumulated_context = list(context) if context else []
            for task in tasks:
                result = await self._run_specialist(
                    task["agent"], task["instruction"], accumulated_context
                )
                main_results.append(result)
                if result.get("success"):
                    accumulated_context.append(result)

        # === 2단계: 리뷰 / 테스트 (메인 결과 기반) ===
        review_results = []

        if needs_review or needs_test:
            review_tasks = []
            main_outputs = [r for r in main_results if r.get("success")]

            if needs_review and "JX_REVIEWER" in self._specialists:
                code_summary = "\n\n".join(
                    f"### {r.get('agent_name', '?')} 결과:\n{r.get('output', '')[:1000]}"
                    for r in main_outputs
                )
                review_instruction = (
                    f"아래 코드 작업 결과를 리뷰해줘.\n\n"
                    f"원본 요청: {instruction}\n\n{code_summary}"
                )
                review_tasks.append(("JX_REVIEWER", review_instruction))

            if needs_test and "JX_TESTER" in self._specialists:
                code_summary = "\n\n".join(
                    f"### {r.get('agent_name', '?')} 결과:\n{r.get('output', '')[:1000]}"
                    for r in main_outputs
                )
                test_instruction = (
                    f"아래 코드에 대한 테스트를 작성하고 검증해줘.\n\n"
                    f"원본 요청: {instruction}\n\n{code_summary}"
                )
                review_tasks.append(("JX_TESTER", test_instruction))

            if review_tasks:
                await self._report_progress(
                    f"리뷰/테스트 단계: {', '.join(t[0] for t in review_tasks)}"
                )
                review_coros = [
                    self._run_specialist(agent, inst, main_results)
                    for agent, inst in review_tasks
                ]
                review_results = await asyncio.gather(*review_coros, return_exceptions=True)
                review_results = [
                    r if isinstance(r, dict) else {
                        "success": False, "output": str(r)
                    }
                    for r in review_results
                ]

        # === 3단계: 결과 취합 ===
        all_results = main_results + review_results
        all_success = all(r.get("success", False) for r in main_results)
        avg_score = (
            sum(r.get("success_score", 0.0) for r in all_results) / len(all_results)
            if all_results else 0.0
        )

        # 최종 보고서 생성
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
            "code": None,
            "specialists_used": [t["agent"] for t in tasks],
        }

    async def _execute_debug(
        self, instruction: str, context: list, memory_context: list
    ) -> dict:
        """ACH(Analysis of Competing Hypotheses) 디버깅

        1. 가설 생성 (Claude로 3개 경쟁 가설)
        2. 각 가설을 병렬로 조사 (전문가 또는 직접)
        3. 증거 기반으로 가장 유력한 원인 선택
        4. 수정 실행
        """
        self._init_specialists()
        await self._report_progress("ACH 디버깅 모드 시작: 가설 생성 중...")

        # 1단계: 가설 생성
        hypothesis_prompt = f"""이 버그/에러를 분석해서 가능한 원인 가설 3개를 세워줘.

문제: {instruction}

JSON으로 답변:
{{
    "hypotheses": [
        {{"id": 1, "theory": "원인 가설", "investigation": "확인 방법 (구체적인 파일, 로그, 코드 위치)", "agent": "조사할 전문가 (JX_BACKEND/JX_FRONTEND/JX_INFRA 중 택1)"}},
        ...
    ]
}}"""

        try:
            response = self._client.messages.create(
                model=self._fast_model,
                max_tokens=500,
                messages=[{"role": "user", "content": hypothesis_prompt}],
            )
            match = re.search(r'\{[\s\S]*\}', response.content[0].text)
            hypotheses = json.loads(match.group())["hypotheses"] if match else []
        except Exception as e:
            logger.warning(f"[JX_CODER] ACH 가설 생성 실패, 직접 처리 전환: {e}")
            return await self._execute_with_retry(instruction, context, memory_context)

        if not hypotheses:
            return await self._execute_with_retry(instruction, context, memory_context)

        # 2단계: 병렬 조사
        await self._report_progress(
            f"가설 {len(hypotheses)}개 병렬 조사 시작: "
            + ", ".join(f"H{h['id']}: {h['theory'][:30]}" for h in hypotheses)
        )

        investigation_coros = []
        for h in hypotheses:
            agent = h.get("agent", "JX_BACKEND")
            inv_instruction = (
                f"가설 조사: '{h['theory']}'\n"
                f"확인 방법: {h['investigation']}\n"
                f"원본 문제: {instruction}\n\n"
                f"이 가설이 맞는지 증거를 수집하라. "
                f"결론을 confidence(0.0~1.0)와 함께 보고하라."
            )
            investigation_coros.append(self._run_specialist(agent, inv_instruction, context))

        results = await asyncio.gather(*investigation_coros, return_exceptions=True)
        results = [
            r if isinstance(r, dict) else {"success": False, "output": str(r)}
            for r in results
        ]

        # 3단계: 증거 기반 수렴
        evidence_summary = "\n\n".join(
            f"### 가설 {h['id']}: {h['theory']}\n조사 결과: {r.get('output', '없음')[:800]}"
            for h, r in zip(hypotheses, results)
        )

        await self._report_progress("증거 수집 완료, 중재 판단 중...")

        arbitrate_prompt = f"""디버깅 증거를 분석하여 최종 판단을 내려라.

원본 문제: {instruction}

{evidence_summary}

가장 유력한 원인과 구체적인 수정 방안을 제시하라. 코드 수정이 필요하면 코드를 포함하라."""

        try:
            executor = self._get_executor()

            tool_cb = self._make_tool_callback()

            fix_result = await executor.execute(
                instruction=arbitrate_prompt,
                system_prompt=self._get_system_prompt(),
                tool_callback=tool_cb,
            )

            return {
                "success": fix_result.success,
                "score": 0.9 if fix_result.success else 0.4,
                "output": fix_result.output,
                "error": fix_result.error,
                "code": None,
                "specialists_used": [h.get("agent", "?") for h in hypotheses],
            }
        except Exception as e:
            # 수정 실패 시 조사 결과만이라도 반환
            return {
                "success": True,
                "score": 0.6,
                "output": f"## 디버깅 분석 결과\n\n{evidence_summary}\n\n(자동 수정 실패: {e})",
                "error": None,
                "code": None,
                "specialists_used": [h.get("agent", "?") for h in hypotheses],
            }

    # ===== 기존 직접 실행 로직 (단순 작업용) =====

    async def _classify_task(self, instruction: str) -> dict:
        """작업 유형을 Claude가 판단 (직접 실행용)"""
        classify_prompt = f"""이 코딩 요청을 분류해.

요청: "{instruction}"

다음 두 가지를 판단해:
1. MCP 도구 필요? (git/github 조작, 브라우저 자동화, 웹 크롤링 등)
2. 복잡한 작업? (프로젝트 생성, 패키지 설치, 여러 파일 수정, 프레임워크 설정 등)

JSON으로 답해: {{"mcp": "yes/no", "complex": "yes/no"}}"""

        try:
            response = self._client.messages.create(
                model=self._fast_model,
                max_tokens=50,
                messages=[{"role": "user", "content": classify_prompt}],
            )
            text = response.content[0].text
            match = re.search(r'\{[^}]+\}', text)
            if match:
                result = json.loads(match.group())
                return {
                    "needs_mcp": result.get("mcp", "no").lower() == "yes",
                    "is_complex": result.get("complex", "no").lower() == "yes",
                }
        except Exception as e:
            logger.warning(f"[JXCoder] 작업 분류 JSON 파싱 실패, 기본값 사용: {e}")
        return {"needs_mcp": False, "is_complex": False}

    def _get_system_prompt(self) -> str:
        from datetime import datetime
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""너는 JX_CODER야. JINXUS의 코딩팀 총괄.
오늘은 {today}이다.

## 역할
주인님의 코딩 요청을 받아 직접 처리하거나, 전문가 팀에게 배분한다.

## 직접 처리 (단순 작업)
- 반드시 실행 가능한 완전한 코드 작성
- 필요한 import 문 포함
- 결과를 print()로 출력
- try-except로 에러 핸들링

## 출력 형식
- XML 태그 출력 금지. 도구 호출 과정 노출 금지.
- 최종 결과만 깔끔하게 보고.
- 코드 블록은 ```python 사용.
"""

    async def run(self, instruction: str, context: list = None, memory_context: list = None) -> dict:
        """에이전트 실행 (전체 흐름)"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            if not memory_context:
                try:
                    memory_context = self._memory.search_long_term(
                        agent_name=self.name, query=instruction, limit=3
                    )
                except Exception:
                    memory_context = []

            # === [plan] 작업 분해 ===
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            plan = await self._decompose_task(instruction)
            await self._report_progress(f"작업 분석 완료: {plan.get('reason', '')} (mode={plan['mode']})")

            # === [execute] 실행 ===
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)

            if plan["mode"] == "debug":
                # ACH 디버깅: 가설 분기 → 병렬 조사 → 증거 기반 수렴
                result = await self._execute_debug(instruction, context or [], memory_context)
            elif plan["mode"] == "delegate" and plan.get("specialists"):
                # 전문가 팀에게 위임
                result = await self._execute_delegated(plan, instruction, context or [])
            else:
                # 직접 실행 (기존 로직)
                result = await self._execute_with_retry(instruction, context, memory_context)

            # === [evaluate] 평가 ===
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
                "specialists_used": result.get("specialists_used", []),
            }

        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            raise
        finally:
            self._state_tracker.complete_task(self.name)

    async def _execute_with_retry(
        self, instruction: str, context: list, memory_context: list
    ) -> dict:
        """직접 실행 + 재시도 (최대 3회)"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await self._execute_direct(instruction, context, memory_context, last_error)
                if result["success"]:
                    return result
                last_error = result.get("error", "Unknown error")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        return {
            "success": False,
            "score": 0.0,
            "output": f"죄송합니다, {self.max_retries}번 시도했지만 실패했습니다.\n마지막 오류: {last_error}",
            "error": last_error,
            "code": None,
        }

    async def _execute_direct(
        self, instruction: str, context: list, memory_context: list, last_error: str = None
    ) -> dict:
        """직접 실행 (단순 작업)"""
        task_type = await self._classify_task(instruction)

        if self._use_dynamic_tools and task_type["needs_mcp"]:
            result = await self._execute_with_mcp_tools(instruction, memory_context, last_error)
            if result["success"]:
                return result

        if task_type["is_complex"]:
            return await self._execute_with_claude_code(instruction, last_error)

        return await self._execute_simple(instruction, context, memory_context, last_error)

    async def _execute_with_mcp_tools(
        self, instruction: str, memory_context: list, last_error: str = None
    ) -> dict:
        """MCP 도구 사용 실행"""
        logger.info(f"[JX_CODER] MCP 도구 사용 → DynamicToolExecutor")
        self._state_tracker.update_tools(self.name, ["mcp:git", "mcp:github", "mcp:fetch"])

        try:
            executor = self._get_executor()

            memory_str = ""
            if memory_context:
                memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            error_context = ""
            if last_error:
                error_context = f"\n\n이전 시도 오류: {last_error}"

            system_prompt = self._get_system_prompt() + """

## MCP 도구 활용 지침
- Git 작업: mcp:git 도구 사용
- GitHub 작업: mcp:github 도구 사용
- 웹페이지 가져오기: mcp:fetch 도구 사용
- 브라우저 자동화: mcp:playwright 도구 사용
"""

            context = f"{memory_str}\n{error_context}" if memory_str or error_context else None

            tool_cb = self._make_tool_callback()

            result = await executor.execute(
                instruction=instruction,
                system_prompt=system_prompt,
                context=context,
                tool_callback=tool_cb,
            )

            if result.success:
                tools_used = [tc.tool_name for tc in result.tool_calls]
                return {
                    "success": True,
                    "score": 0.95 if tools_used else 0.85,
                    "output": result.output,
                    "error": None,
                    "code": None,
                    "tool_calls": tools_used,
                }
            else:
                partial = "\n".join(str(r.get("output",""))[:300] for r in result.raw_results if r.get("output"))
                return {
                    "success": bool(partial),
                    "score": 0.3 if partial else 0.0,
                    "output": partial or f"코드 실행 실패: {result.error or '알 수 없는 오류'}",
                    "error": result.error,
                    "code": None,
                }

        except Exception as e:
            logger.error(f"[JX_CODER] MCP 도구 실행 실패: {e}")
            return {
                "success": False,
                "score": 0.0,
                "output": f"코드 실행 중 오류: {str(e)[:200]}",
                "error": str(e),
                "code": None,
            }

    async def _execute_with_claude_code(
        self, instruction: str, last_error: str = None
    ) -> dict:
        """복잡한 작업: Claude Code CLI 사용"""
        logger.info(f"[JX_CODER] 복잡한 작업 → Claude Code CLI 사용")

        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도 오류: {last_error}"

        prompt = f"""주인님의 요청을 완수해줘:
{instruction}
{error_context}

필요한 패키지 설치, 파일 생성, 코드 작성 및 실행을 모두 수행해.
작업이 완료되면 결과를 명확히 출력해."""

        try:
            result = await self._code_executor.run({"prompt": prompt})

            if result.success:
                output_data = result.output or {}
                code_output = output_data.get("code_output", "")
                files_created = output_data.get("files_created", [])
                working_dir = output_data.get("working_dir", "")

                file_list = ""
                if files_created:
                    file_list = f"\n\n## 생성된 파일\n" + "\n".join(
                        f"- {f}" for f in files_created
                    )

                output = f"""주인님, 작업이 완료되었습니다.

## Claude Code 실행 결과
```
{code_output[:3000]}
```
{file_list}

작업 디렉토리: {working_dir}
"""
                return {
                    "success": True,
                    "score": 0.95,
                    "output": output,
                    "error": None,
                    "code": None,
                }
            else:
                return {
                    "success": False,
                    "score": 0.3,
                    "output": f"Claude Code 실행 오류:\n{result.error}",
                    "error": result.error,
                    "code": None,
                }

        except Exception as e:
            logger.error(f"[JX_CODER] Claude Code 실행 실패: {e}")
            return {
                "success": False,
                "score": 0.2,
                "output": f"Claude Code 실행 중 오류: {e}",
                "error": str(e),
                "code": None,
            }

    async def _execute_simple(
        self, instruction: str, context: list, memory_context: list, last_error: str = None
    ) -> dict:
        """간단한 작업: 코드 생성 후 python3 직접 실행"""
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도에서 오류 발생: {last_error}\n이 오류를 피해서 다시 작성해줘."

        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        code_prompt = f"""주인님의 요청: {instruction}
{memory_str}
{error_context}

실행 가능한 Python 코드를 작성해줘. 결과는 반드시 print()로 출력해.
```python 블록 안에 코드를 작성해."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": code_prompt}],
        )

        generated_text = response.content[0].text
        code = self._extract_code(generated_text)

        if not code:
            return {
                "success": False,
                "score": 0.2,
                "output": f"코드 블록을 찾지 못했습니다.\n\n응답:\n{generated_text}",
                "error": "No code block found",
                "code": None,
            }

        exec_result = await self._execute_python(code)

        if exec_result["success"]:
            output = f"""주인님, 코드 실행이 완료되었습니다.

## 생성된 코드
```python
{code}
```

## 실행 결과
```
{exec_result['stdout']}
```
"""
            return {
                "success": True,
                "score": 0.95,
                "output": output,
                "error": None,
                "code": code,
            }
        else:
            return {
                "success": False,
                "score": 0.3,
                "output": f"코드 실행 오류:\n```\n{exec_result['stderr']}\n```",
                "error": exec_result["stderr"],
                "code": code,
            }

    async def _reflect(self, instruction: str, result: dict) -> str:
        """반성"""
        if not result["success"]:
            return f"실패 원인: {result.get('error', 'Unknown')}."

        specialists = result.get("specialists_used", [])
        if specialists:
            return f"전문가 팀({', '.join(specialists)}) 위임 처리 성공."

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": f"작업 '{instruction}' 성공. 핵심 배움 1-2문장."}],
            )
            return response.content[0].text
        except Exception:
            return "작업 성공."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        """장기기억에 저장"""
        try:
            importance = 0.3
            if not result["success"]:
                importance += 0.4
            if result.get("specialists_used"):
                importance += 0.2
            if len(reflection) > 50:
                importance += 0.1

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
            logger.warning(f"[JX_CODER] 메모리 저장 실패")

    def _extract_code(self, text: str) -> Optional[str]:
        """응답에서 Python 코드 추출"""
        pattern = r"```python\s*(.*?)\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()

        pattern = r"```\s*(.*?)\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()

        return None

    async def _execute_python(self, code: str) -> dict:
        """Python 코드 실행"""
        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = Path(tmpdir) / "script.py"
            code_file.write_text(code, encoding="utf-8")

            try:
                process = await asyncio.create_subprocess_exec(
                    "python3",
                    str(code_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30
                )

                return {
                    "success": process.returncode == 0,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "exit_code": process.returncode,
                }

            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "실행 시간 초과 (30초)",
                    "exit_code": -1,
                }
            except Exception as e:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": str(e),
                    "exit_code": -1,
                }

    async def _report_progress(self, detail: str, agent_name: str = None, event_type: str = "progress"):
        """SSE 프로그레스 콜백

        event_type: "progress" | "specialist_started" | "specialist_done"
        """
        if self._progress_callback:
            try:
                prefix = f"[{agent_name or self.name}]"
                # 구조화된 이벤트 포맷: {{TYPE:agent}} detail
                if event_type != "progress":
                    await self._progress_callback(f"{{{{{event_type}:{agent_name or self.name}}}}} {detail}")
                else:
                    await self._progress_callback(f"{prefix} {detail}")
            except Exception as e:
                logger.debug(f"[JX_CODER] 프로그레스 콜백 실패: {e}")
