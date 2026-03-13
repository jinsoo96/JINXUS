"""자율 멀티스텝 작업 실행기 v1.7.0

복잡한 작업을 여러 라운드로 분해하여 자율적으로 실행한다.
각 라운드의 결과가 다음 라운드의 컨텍스트로 전달되며,
중간 진행 상황을 콜백(텔레그램 등)으로 보고한다.

v1.7.0 추가:
- Redis 기반 step 체크포인트 (서버 재시작 시 복구)
- 실제 진행률 (completed_steps / total_steps)
- 개별 step 타임아웃 (asyncio.wait_for)
- 가드레일 (step 결과 검증 + 재시도)
- 일시정지/재개 (PAUSED 상태)

사용 예:
    runner = AutonomousRunner()
    result = await runner.run(
        task="이 프로젝트 분석하고 개선사항 적용해줘",
        session_id="telegram_123",
        progress_callback=send_telegram,
    )
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Awaitable

from anthropic import AsyncAnthropic
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

# 가드레일 실패 패턴 (LLM 호출 없이 패턴 매칭으로 검증)
_GUARDRAIL_FAIL_PATTERNS = [
    "할 수 없습니다",
    "접근할 수 없습니다",
    "권한이 없습니다",
    "찾을 수 없습니다",
    "오류가 발생했습니다",
    "실패했습니다",
    "I cannot",
    "I'm unable to",
    "Error:",
    "Exception:",
    "Traceback (most recent call last)",
]


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
    retry_count: int = 0


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


# Redis 체크포인트 키
_CHECKPOINT_KEY = "jinxus:checkpoint:{task_id}"


class AutonomousRunner:
    """자율 멀티스텝 작업 실행기

    복합 작업을 LLM으로 분해 → 각 단계를 orchestrator.run_task()로 실행
    → 중간 평가 → 계획 조정 → 완료까지 반복

    v1.7.0: 체크포인트, 실제 진행률, step 타임아웃, 가드레일, 일시정지
    """

    def __init__(
        self,
        max_steps: int = 10,
        timeout_seconds: int = 4 * 3600,
        evaluate_interval: int = 3,
        task_id: Optional[str] = None,
        progress_update: Optional[Callable[[int, int, int], Awaitable[None]]] = None,
    ):
        self._max_steps = max_steps
        self._timeout_seconds = timeout_seconds
        self._evaluate_interval = evaluate_interval
        self._cancelled = False
        self._paused = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 초기 상태: 실행 중
        self._task_id = task_id

        settings = get_settings()
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._step_timeout = settings.step_timeout_seconds
        self._guardrail_max_retries = settings.guardrail_max_retries
        self._checkpoint_ttl = settings.checkpoint_ttl_hours * 3600

        # 실시간 진행률 콜백
        self._progress_update: Optional[Callable[[int, int, int], Awaitable[None]]] = progress_update

    def cancel(self):
        """실행 취소"""
        self._cancelled = True
        # 일시정지 중이면 해제해서 취소 처리
        self._pause_event.set()

    def pause(self):
        """실행 일시정지"""
        self._paused = True
        self._pause_event.clear()
        logger.info(f"[AutonomousRunner] 일시정지: {self._task_id}")

    def resume(self):
        """실행 재개"""
        self._paused = False
        self._pause_event.set()
        logger.info(f"[AutonomousRunner] 재개: {self._task_id}")

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def run(
        self,
        task: str,
        session_id: str,
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> AutonomousResult:
        """자율 실행"""
        from jinxus.core.orchestrator import get_orchestrator

        orchestrator = get_orchestrator()
        if not orchestrator.is_initialized:
            await orchestrator.initialize()

        start_time = time.time()
        self._cancelled = False

        # 체크포인트에서 복구 시도
        checkpoint = await self._load_checkpoint()
        if checkpoint:
            return await self._resume_from_checkpoint(
                checkpoint, task, session_id, orchestrator,
                start_time, progress_callback,
            )

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
        return await self._execute_steps(
            task, steps, [], 0, total_planned,
            session_id, orchestrator, start_time, progress_callback,
        )

    async def _resume_from_checkpoint(
        self, checkpoint: dict, task: str, session_id: str,
        orchestrator, start_time: float, progress_callback,
    ) -> AutonomousResult:
        """체크포인트에서 재개"""
        records = [
            StepRecord(**r) for r in checkpoint["records"]
        ]
        remaining_steps = checkpoint["remaining_steps"]
        step_index = checkpoint["step_index"]
        total_planned = checkpoint["total_planned"]

        if progress_callback:
            await progress_callback(
                f"[Autonomous] 체크포인트에서 재개: {step_index}/{total_planned} 완료됨"
            )

        return await self._execute_steps(
            task, remaining_steps, records, step_index, total_planned,
            session_id, orchestrator, start_time, progress_callback,
        )

    async def _execute_steps(
        self, task: str, steps: list[dict], records: list[StepRecord],
        step_index: int, total_planned: int,
        session_id: str, orchestrator, start_time: float,
        progress_callback,
    ) -> AutonomousResult:
        """단계별 실행 루프 (체크포인트, 가드레일, 타임아웃 포함)"""

        while steps and step_index < self._max_steps:
            # 일시정지 대기
            await self._pause_event.wait()

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

            # 진행률 업데이트
            progress_pct = int((step_index - 1) / max(total_planned, 1) * 100)
            if self._progress_update:
                await self._progress_update(progress_pct, step_index - 1, total_planned)

            # 가드레일 재시도 루프
            record = await self._execute_step_with_guardrail(
                step_index, instruction, description,
                records, session_id, orchestrator, progress_callback,
            )

            records.append(record)

            # 진행률 업데이트 (step 완료)
            progress_pct = int(step_index / max(total_planned, 1) * 100)
            if self._progress_update:
                await self._progress_update(progress_pct, step_index, total_planned)

            if progress_callback:
                status = "완료" if record.success else "실패"
                retry_info = f" (재시도 {record.retry_count}회)" if record.retry_count > 0 else ""
                await progress_callback(
                    f"[Autonomous] [{step_index}/{total_planned}] {description} - {status}{retry_info} ({record.duration_s:.1f}s)"
                )

            # 체크포인트 저장
            await self._save_checkpoint(
                task, records, steps, step_index, total_planned
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

        # 완료 시 체크포인트 삭제
        await self._delete_checkpoint()

        return self._build_result(task, records, total_planned, start_time)

    async def _execute_step_with_guardrail(
        self, step_index: int, instruction: str, description: str,
        records: list[StepRecord], session_id: str,
        orchestrator, progress_callback,
    ) -> StepRecord:
        """가드레일 포함 step 실행 (타임아웃 + 검증 + 재시도)"""
        retry_count = 0
        current_instruction = instruction

        while True:
            # 이전 결과를 컨텍스트로 포함
            context_instruction = self._build_context_instruction(
                current_instruction, records
            )

            step_start = time.time()
            try:
                # step 타임아웃 적용
                result = await asyncio.wait_for(
                    orchestrator.run_task(
                        user_input=context_instruction,
                        session_id=f"{session_id}_auto_{step_index}",
                        progress_callback=progress_callback,
                    ),
                    timeout=self._step_timeout,
                )

                response = result.get("response", "")
                agents_used = result.get("agents_used", [])
                duration = time.time() - step_start

                # 가드레일 검증
                if retry_count < self._guardrail_max_retries:
                    validation = await self._validate_step(instruction, response)

                    if not validation.get("valid", True):
                        retry_count += 1
                        feedback = validation.get("feedback", "")
                        reason = validation.get("reason", "검증 실패")
                        logger.warning(
                            f"[AutonomousRunner] Step {step_index} 가드레일 실패 "
                            f"(시도 {retry_count}/{self._guardrail_max_retries}): {reason}"
                        )
                        if progress_callback:
                            await progress_callback(
                                f"[Autonomous] [{step_index}] 검증 실패, 재시도 ({retry_count}/{self._guardrail_max_retries}): {reason[:100]}"
                            )
                        # 피드백 포함하여 재시도 (원본 instruction 기반 — 누적 방지)
                        current_instruction = (
                            f"{instruction}\n\n"
                            f"[가드레일 피드백 #{retry_count}] {feedback}\n"
                            f"이전 결과가 부적절했습니다. 위 피드백을 반영하여 다시 수행해주세요."
                        )
                        continue

                return StepRecord(
                    index=step_index,
                    instruction=instruction,
                    description=description,
                    response=response,
                    agents_used=agents_used,
                    success=True,
                    duration_s=duration,
                    retry_count=retry_count,
                )

            except asyncio.TimeoutError:
                duration = time.time() - step_start
                logger.error(
                    f"[AutonomousRunner] Step {step_index} 타임아웃 ({self._step_timeout}초)"
                )

                if retry_count < self._guardrail_max_retries:
                    retry_count += 1
                    if progress_callback:
                        await progress_callback(
                            f"[Autonomous] [{step_index}] 타임아웃, 재시도 ({retry_count}/{self._guardrail_max_retries})"
                        )
                    current_instruction = (
                        f"{instruction}\n\n"
                        f"[이전 시도 피드백] 이전 시도가 {self._step_timeout}초 타임아웃으로 실패했습니다. "
                        f"더 간결하게 처리해주세요."
                    )
                    continue

                return StepRecord(
                    index=step_index,
                    instruction=instruction,
                    description=description,
                    response=f"타임아웃 ({self._step_timeout}초)",
                    success=False,
                    duration_s=duration,
                    retry_count=retry_count,
                )

            except Exception as e:
                duration = time.time() - step_start
                logger.error(f"[AutonomousRunner] Step {step_index} 실패: {e}")

                if retry_count < self._guardrail_max_retries:
                    retry_count += 1
                    if progress_callback:
                        await progress_callback(
                            f"[Autonomous] [{step_index}] 오류, 재시도 ({retry_count}/{self._guardrail_max_retries}): {str(e)[:80]}"
                        )
                    current_instruction = (
                        f"{instruction}\n\n"
                        f"[이전 시도 피드백] 오류 발생: {str(e)[:200]}. "
                        f"다른 방법으로 시도해주세요."
                    )
                    continue

                return StepRecord(
                    index=step_index,
                    instruction=instruction,
                    description=description,
                    response=str(e),
                    success=False,
                    duration_s=duration,
                    retry_count=retry_count,
                )

    async def _validate_step(self, instruction: str, response: str) -> dict:
        """가드레일: step 결과 검증 (패턴 매칭 — LLM 호출 없음)"""
        # 빈 응답은 즉시 실패
        if not response or len(response.strip()) < 10:
            return {
                "valid": False,
                "reason": "빈 응답 또는 너무 짧은 응답",
                "feedback": "의미있는 결과를 생성해주세요.",
            }

        # 응답 전체가 실패 패턴으로 시작하는 경우만 실패 처리
        # (결과 중간에 에러 언급하는 건 정상 응답일 수 있으므로 첫 200자만 검사)
        head = response.strip()[:200]
        for pattern in _GUARDRAIL_FAIL_PATTERNS:
            if head.startswith(pattern) or (len(head) < 50 and pattern in head):
                return {
                    "valid": False,
                    "reason": f"실패 패턴 감지: {pattern}",
                    "feedback": f"이전 결과가 '{pattern}'로 시작합니다. 다른 방법으로 시도해주세요.",
                }

        return {"valid": True}

    # ===== 체크포인트 (Redis) =====

    async def _get_redis(self):
        """Redis 연결 획득"""
        import redis.asyncio as redis_lib
        settings = get_settings()
        return redis_lib.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password if settings.redis_password else None,
            decode_responses=True,
        )

    async def _save_checkpoint(
        self, task: str, records: list[StepRecord],
        remaining_steps: list[dict], step_index: int, total_planned: int,
    ) -> None:
        """체크포인트 저장 (Redis)"""
        if not self._task_id:
            return

        try:
            r = await self._get_redis()
            key = _CHECKPOINT_KEY.format(task_id=self._task_id)

            checkpoint = {
                "task": task,
                "records": [asdict(r) for r in records],
                "remaining_steps": remaining_steps,
                "step_index": step_index,
                "total_planned": total_planned,
                "saved_at": time.time(),
            }

            await r.set(key, json.dumps(checkpoint, ensure_ascii=False))
            await r.expire(key, self._checkpoint_ttl)
            await r.aclose()

            logger.debug(f"[AutonomousRunner] 체크포인트 저장: step {step_index}/{total_planned}")

        except Exception as e:
            logger.warning(f"[AutonomousRunner] 체크포인트 저장 실패: {e}")

    async def _load_checkpoint(self) -> Optional[dict]:
        """체크포인트 로드 (Redis)"""
        if not self._task_id:
            return None

        try:
            r = await self._get_redis()
            key = _CHECKPOINT_KEY.format(task_id=self._task_id)
            data = await r.get(key)
            await r.aclose()

            if data:
                checkpoint = json.loads(data)
                logger.info(
                    f"[AutonomousRunner] 체크포인트 발견: "
                    f"step {checkpoint['step_index']}/{checkpoint['total_planned']}"
                )
                return checkpoint

        except Exception as e:
            logger.warning(f"[AutonomousRunner] 체크포인트 로드 실패: {e}")

        return None

    async def _delete_checkpoint(self) -> None:
        """체크포인트 삭제"""
        if not self._task_id:
            return

        try:
            r = await self._get_redis()
            key = _CHECKPOINT_KEY.format(task_id=self._task_id)
            await r.delete(key)
            await r.aclose()
        except Exception as e:
            logger.debug(f"[AutonomousRunner] 체크포인트 삭제 실패: {e}")

    # ===== LLM 호출 =====

    def _parse_json_safe(self, text: str, fallback: dict | None = None) -> dict:
        """4단계 JSON 파싱 폴백 — LLM 응답이 완벽하지 않아도 크래시 방지

        1단계: 직접 json.loads
        2단계: 마크다운 코드 블록 추출
        3단계: 정규식으로 JSON 객체 추출
        4단계: fallback 반환 (크래시 방지)
        """
        import re as _re
        stripped = text.strip()

        # 1단계: 직접 파싱
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            logger.debug(f"[AutonomousRunner] JSON 직접 파싱 실패, 다음 단계 시도: {e}")

        # 2단계: 마크다운 코드 블록 추출
        for marker in ["```json", "```"]:
            if marker in stripped:
                try:
                    extracted = stripped.split(marker, 1)[1].split("```", 1)[0].strip()
                    return json.loads(extracted)
                except (json.JSONDecodeError, IndexError) as e:
                    logger.debug(f"[AutonomousRunner] 코드 블록 파싱 실패 (marker={marker}): {e}")

        # 3단계: 정규식으로 JSON 객체 추출
        match = _re.search(r'\{.*\}', stripped, _re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError as e:
                logger.debug(f"[AutonomousRunner] 정규식 JSON 파싱 실패: {e}")

        # 4단계: 폴백 (크래시 방지)
        logger.warning(f"[AutonomousRunner] JSON 파싱 실패, 폴백 사용: {stripped[:100]}")
        return fallback if fallback is not None else {}

    async def _create_plan(self, task: str) -> list[dict]:
        """LLM으로 작업 계획 생성"""
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2000,
                system=PLAN_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": task}],
            )

            text = response.content[0].text.strip()
            plan = self._parse_json_safe(text, fallback={"steps": []})
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

            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1500,
                system=EVALUATE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            return self._parse_json_safe(text, fallback={"done": False})

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
        # 실패 격리: step 개별 실패는 격리하고 전체 중단 없이 진행.
        # stopped_reason이 없고 records가 있으면 partial success도 성공으로 처리.
        failed = [r for r in records if not r.success]
        success = not stopped_reason and len(records) > 0
        if failed:
            logger.info(
                f"[AutonomousRunner] 실패 격리: {len(failed)}/{len(records)} 스텝 실패 "
                f"({', '.join(r.description[:30] for r in failed)})"
            )
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
