"""자율 멀티스텝 작업 실행기

복잡한 작업을 여러 라운드로 분해하여 자율적으로 실행한다.
각 라운드의 결과가 다음 라운드의 컨텍스트로 전달되며,
중간 진행 상황을 콜백(텔레그램 등)으로 보고한다.

사용 예:
    runner = AutonomousRunner()
    result = await runner.run(
        task="이 프로젝트 분석하고 개선사항 적용해줘",
        session_id="telegram_123",
        progress_callback=send_telegram,
    )
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

from anthropic import Anthropic
from jinxus.config import get_settings

logger = logging.getLogger(__name__)

PLAN_SYSTEM_PROMPT = """너는 JINXUS의 작업 계획 생성기다.
복잡한 작업을 독립적인 실행 단계(step)들로 분해해야 한다.

규칙:
- 각 step은 JINXUS_CORE가 한 번의 run_task로 처리할 수 있는 단위여야 한다
- step 수는 2~10개 사이로 유지
- 각 step은 이전 step의 결과에 의존할 수 있다
- 각 step에 명확한 instruction을 작성하라

응답 형식 (JSON만 출력):
{
  "steps": [
    {"instruction": "수행할 구체적 지시", "description": "간단한 설명"},
    ...
  ]
}"""

EVALUATE_SYSTEM_PROMPT = """너는 JINXUS의 작업 결과 평가기다.
현재까지 실행된 결과와 남은 계획을 보고 다음을 판단하라:

1. 작업이 충분히 완료되었는가? (done: true/false)
2. 남은 계획을 수정해야 하는가?
3. 수정이 필요하면 새로운 remaining steps를 제시하라

응답 형식 (JSON만 출력):
{
  "done": false,
  "reason": "판단 근거",
  "remaining_steps": [
    {"instruction": "...", "description": "..."}
  ]
}"""


@dataclass
class StepRecord:
    """실행된 단계 기록"""
    index: int
    instruction: str
    description: str
    response: str
    agents_used: list[str] = field(default_factory=list)
    success: bool = True
    duration_s: float = 0.0


@dataclass
class AutonomousResult:
    """자율 실행 전체 결과"""
    success: bool
    task: str
    steps_completed: int
    steps_total: int
    records: list[StepRecord] = field(default_factory=list)
    final_summary: str = ""
    total_duration_s: float = 0.0
    stopped_reason: Optional[str] = None


class AutonomousRunner:
    """자율 멀티스텝 작업 실행기

    복합 작업을 LLM으로 분해 → 각 단계를 orchestrator.run_task()로 실행
    → 중간 평가 → 계획 조정 → 완료까지 반복
    """

    def __init__(
        self,
        max_steps: int = 10,
        timeout_seconds: int = 4 * 3600,
        evaluate_interval: int = 3,
    ):
        """
        Args:
            max_steps: 최대 실행 단계 수
            timeout_seconds: 전체 타임아웃 (기본 4시간)
            evaluate_interval: 몇 스텝마다 중간 평가할지 (기본 3스텝마다)
        """
        self._max_steps = max_steps
        self._timeout_seconds = timeout_seconds
        self._evaluate_interval = evaluate_interval
        self._cancelled = False

        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model

    def cancel(self):
        """실행 취소"""
        self._cancelled = True

    async def run(
        self,
        task: str,
        session_id: str,
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> AutonomousResult:
        """자율 실행

        Args:
            task: 복합 작업 설명
            session_id: 세션 ID
            progress_callback: 진행 보고 콜백

        Returns:
            AutonomousResult
        """
        from jinxus.core.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if not orchestrator.is_initialized:
            await orchestrator.initialize()

        start_time = time.time()
        self._cancelled = False

        # 1. 작업 계획 생성
        if progress_callback:
            await progress_callback("[Autonomous] 작업 계획 생성 중...")

        steps = await self._create_plan(task)
        if not steps:
            return AutonomousResult(
                success=False,
                task=task,
                steps_completed=0,
                steps_total=0,
                stopped_reason="계획 생성 실패",
                total_duration_s=time.time() - start_time,
            )

        total_planned = len(steps)
        if progress_callback:
            step_list = "\n".join(f"  {i+1}. {s['description']}" for i, s in enumerate(steps))
            await progress_callback(
                f"[Autonomous] 계획 수립 완료 ({total_planned}단계)\n{step_list}"
            )

        # 2. 각 단계 실행
        records: list[StepRecord] = []
        step_index = 0

        while steps and step_index < self._max_steps:
            # 타임아웃 체크
            elapsed = time.time() - start_time
            if elapsed > self._timeout_seconds:
                if progress_callback:
                    await progress_callback(
                        f"[Autonomous] 타임아웃 ({self._timeout_seconds}초) - 중단"
                    )
                return self._build_result(
                    task, records, total_planned, start_time,
                    stopped_reason=f"타임아웃 ({elapsed:.0f}초)",
                )

            # 취소 체크
            if self._cancelled:
                return self._build_result(
                    task, records, total_planned, start_time,
                    stopped_reason="사용자 취소",
                )

            current_step = steps.pop(0)
            step_index += 1

            instruction = current_step["instruction"]
            description = current_step.get("description", instruction[:50])

            if progress_callback:
                await progress_callback(
                    f"[Autonomous] [{step_index}/{total_planned}] {description}"
                )

            # 이전 결과를 컨텍스트로 포함
            context_instruction = self._build_context_instruction(
                instruction, records
            )

            # orchestrator.run_task 실행
            step_start = time.time()
            try:
                result = await orchestrator.run_task(
                    user_input=context_instruction,
                    session_id=f"{session_id}_auto_{step_index}",
                    progress_callback=progress_callback,
                )

                record = StepRecord(
                    index=step_index,
                    instruction=instruction,
                    description=description,
                    response=result.get("response", ""),
                    agents_used=result.get("agents_used", []),
                    success=True,
                    duration_s=time.time() - step_start,
                )

            except Exception as e:
                logger.error(f"[AutonomousRunner] Step {step_index} 실패: {e}")
                record = StepRecord(
                    index=step_index,
                    instruction=instruction,
                    description=description,
                    response=str(e),
                    success=False,
                    duration_s=time.time() - step_start,
                )

            records.append(record)

            if progress_callback:
                status = "완료" if record.success else "실패"
                await progress_callback(
                    f"[Autonomous] [{step_index}/{total_planned}] {description} - {status} ({record.duration_s:.1f}s)"
                )

            # 중간 평가 (evaluate_interval마다)
            if steps and step_index % self._evaluate_interval == 0:
                if progress_callback:
                    await progress_callback("[Autonomous] 중간 평가 중...")

                evaluation = await self._evaluate_progress(task, records, steps)

                if evaluation.get("done"):
                    if progress_callback:
                        reason = evaluation.get("reason", "작업 완료")
                        await progress_callback(f"[Autonomous] 조기 완료: {reason}")
                    break

                new_steps = evaluation.get("remaining_steps")
                if new_steps:
                    steps = new_steps
                    total_planned = step_index + len(steps)
                    if progress_callback:
                        await progress_callback(
                            f"[Autonomous] 계획 조정: 남은 {len(steps)}단계"
                        )

        return self._build_result(task, records, total_planned, start_time)

    async def _create_plan(self, task: str) -> list[dict]:
        """LLM으로 작업 계획 생성"""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                system=PLAN_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": task}],
            )

            import json
            text = response.content[0].text.strip()
            # JSON 블록 추출
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            plan = json.loads(text)
            steps = plan.get("steps", [])

            # 최대 스텝 수 제한
            return steps[:self._max_steps]

        except Exception as e:
            logger.error(f"[AutonomousRunner] 계획 생성 실패: {e}")
            return []

    async def _evaluate_progress(
        self, task: str, records: list[StepRecord], remaining_steps: list[dict]
    ) -> dict:
        """중간 평가 — 계속할지, 계획을 조정할지 판단"""
        try:
            completed_summary = "\n".join(
                f"Step {r.index}: [{('성공' if r.success else '실패')}] {r.description}\n  결과: {r.response[:300]}"
                for r in records[-5:]  # 최근 5개만
            )

            remaining_summary = "\n".join(
                f"  - {s['description']}"
                for s in remaining_steps
            )

            prompt = (
                f"원본 작업: {task}\n\n"
                f"완료된 단계:\n{completed_summary}\n\n"
                f"남은 계획:\n{remaining_summary}"
            )

            response = self._client.messages.create(
                model=self._model,
                max_tokens=1500,
                system=EVALUATE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            import json
            text = response.content[0].text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            return json.loads(text)

        except Exception as e:
            logger.error(f"[AutonomousRunner] 평가 실패: {e}")
            return {"done": False}

    def _build_context_instruction(
        self, instruction: str, records: list[StepRecord]
    ) -> str:
        """이전 단계 결과를 포함한 지시 구성"""
        if not records:
            return instruction

        # 최근 3개 결과만 포함 (컨텍스트 비대화 방지)
        recent = records[-3:]
        context_parts = ["[이전 작업 결과 요약]"]
        for r in recent:
            status = "성공" if r.success else "실패"
            # 결과를 500자로 제한
            preview = r.response[:500] + "..." if len(r.response) > 500 else r.response
            context_parts.append(f"- [{status}] {r.description}: {preview}")

        context_parts.append(f"\n[현재 지시]\n{instruction}")
        return "\n".join(context_parts)

    def _build_result(
        self,
        task: str,
        records: list[StepRecord],
        total_planned: int,
        start_time: float,
        stopped_reason: Optional[str] = None,
    ) -> AutonomousResult:
        """최종 결과 구성"""
        success = all(r.success for r in records) and not stopped_reason
        total_duration = time.time() - start_time

        # 최종 요약: 마지막 성공 응답
        final_summary = ""
        for r in reversed(records):
            if r.success and r.response:
                final_summary = r.response
                break

        return AutonomousResult(
            success=success,
            task=task,
            steps_completed=len(records),
            steps_total=total_planned,
            records=records,
            final_summary=final_summary,
            total_duration_s=total_duration,
            stopped_reason=stopped_reason,
        )
