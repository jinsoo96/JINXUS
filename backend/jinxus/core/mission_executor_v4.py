"""MissionExecutor v4.0 — CLI 기반 미션 실행 엔진

v3에서 변경된 점:
- orchestrator.run_task_stream() → agent_executor.execute_command() 직접 호출
- 각 에이전트가 CLI 프로세스로 실제 작업 수행
- 200ms 로그 폴링으로 실시간 도구 사용 로그 전달
- file_changes 자동 추적
- 난이도 분류 (Easy/Medium/Hard) 도입

미션 플로우:
1. 난이도 분류
2. EASY → CORE가 직접 답변
3. MEDIUM → 단일 에이전트 CLI 실행
4. HARD → 복수 에이전트 병렬 CLI 실행
5. 결과 취합 + 보고
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from jinxus.core.mission import (
    Mission, MissionType, MissionStatus, get_mission_store,
)
from jinxus.core.agent_messenger import get_agent_messenger
from jinxus.core.agent_executor import (
    execute_command, AlreadyExecutingError, AgentNotFoundError, AgentNotAliveError,
)
from jinxus.core.completion_signals import (
    parse_completion_signal, is_failure_signal,
    SIGNAL_BLOCKED, SIGNAL_ERROR, SIGNAL_CONTINUE,
)
from jinxus.core.difficulty_router import Difficulty
from jinxus.core.cross_validator import cross_validate
from jinxus.core.competitive_dispatch import (
    competitive_execute, should_use_competitive,
)
from jinxus.core.agent_performance import get_performance_tracker
from jinxus.agents.personas import get_persona, get_korean_name
from jinxus.cli_engine.models import StreamEvent, StreamEventType
from jinxus.cli_engine.session_logger import (
    get_session_logger, extract_thinking_preview, format_tool_detail,
)
from jinxus.cli_engine.session_manager import get_agent_session_manager

logger = logging.getLogger(__name__)


def _agent_label(code: str) -> str:
    """에이전트 코드 → '이름(직무)' 변환. 보고서/로그용."""
    if code == "JINXUS_CORE":
        return "진서스"
    p = get_persona(code)
    return f"{p.korean_name}({p.role})" if p.role else p.korean_name


def _agent_names_str(agents: list) -> str:
    """에이전트 코드 리스트 → 이름 나열 문자열."""
    return ", ".join(_agent_label(a) for a in agents if a != "JINXUS_CORE")


class MissionExecutorV4:
    """v4 미션 실행 엔진 — CLI 기반, 진짜 병렬 실행"""

    def __init__(self):
        self._store = get_mission_store()
        self._messenger = get_agent_messenger()
        self._session_manager = get_agent_session_manager()
        self._active_missions: Dict[str, asyncio.Task] = {}

    async def cleanup_orphan_missions(self):
        """서버 재시작 시 고아 미션 정리"""
        store = self._store
        for status in (MissionStatus.BRIEFING, MissionStatus.IN_PROGRESS, MissionStatus.REVIEW):
            try:
                orphans = await store.list_by_status(status, limit=50)
                for mission in orphans:
                    if mission.id not in self._active_missions:
                        mission.status = MissionStatus.FAILED
                        mission.error = "서버 재시작으로 미션이 중단되었습니다"
                        mission.completed_at = datetime.now().isoformat()
                        await store.save(mission)
            except Exception as e:
                logger.warning("[MissionExecutorV4] 고아 미션 정리 실패: %s", e)

    def start_mission(self, mission: Mission) -> asyncio.Task:
        """미션을 백그라운드 태스크로 시작"""
        task = asyncio.create_task(
            self._execute(mission),
            name=f"mission-{mission.id}",
        )
        self._active_missions[mission.id] = task
        task.add_done_callback(lambda t: self._active_missions.pop(mission.id, None))
        return task

    async def cancel_mission(self, mission_id: str) -> bool:
        """미션 취소"""
        mission = await self._store.get(mission_id)
        if not mission:
            return False
        if mission.status in (MissionStatus.COMPLETE, MissionStatus.FAILED, MissionStatus.CANCELLED):
            return False

        task = self._active_missions.get(mission_id)
        if task and not task.done():
            task.cancel()

        mission.status = MissionStatus.CANCELLED
        mission.completed_at = datetime.now().isoformat()
        await self._store.save(mission)
        await self._emit(mission.id, {"event": "mission_cancelled", "data": {"id": mission_id}})
        return True

    # ── Core execution ────────────────────────────────────────────

    async def _emit(self, mission_id: str, event: dict):
        await self._messenger._emit(mission_id, event)

    async def _execute(self, mission: Mission):
        """미션 전체 실행"""
        try:
            await self._emit(mission.id, {"event": "mission_created", "data": mission.to_dict()})

            mission.status = MissionStatus.BRIEFING
            mission.started_at = datetime.now().isoformat()
            await self._store.save(mission)
            await self._emit(mission.id, {"event": "mission_status", "data": {
                "id": mission.id, "status": "briefing", "message": "미션 분석 중...",
            }})

            # ── 난이도 분류 (mission_router의 type을 기준으로) ──
            _TYPE_TO_DIFFICULTY = {
                MissionType.QUICK: Difficulty.EASY,
                MissionType.STANDARD: Difficulty.MEDIUM,
                MissionType.EPIC: Difficulty.HARD,
                MissionType.RAID: Difficulty.HARD,
            }
            difficulty = _TYPE_TO_DIFFICULTY.get(mission.type, Difficulty.MEDIUM)
            logger.info("[Mission %s] Type: %s → Difficulty: %s", mission.id[:8], mission.type.value, difficulty.value)

            await self._emit(mission.id, {"event": "mission_thinking", "data": {
                "id": mission.id, "from": "JINXUS_CORE",
                "step": "classify", "detail": f"난이도: {difficulty.value}",
            }})

            # ── 실행 ──
            if difficulty == Difficulty.EASY:
                await self._execute_easy(mission)
            elif difficulty == Difficulty.MEDIUM:
                await self._execute_medium(mission)
            else:
                await self._execute_hard(mission)

            # ── 완료 (Redis에서 conversations 복원 후 저장) ──
            mission.status = MissionStatus.COMPLETE
            mission.completed_at = datetime.now().isoformat()
            await self._sync_conversations(mission)
            await self._store.save(mission)

            await self._emit(mission.id, {"event": "mission_complete", "data": {
                "id": mission.id,
                "title": mission.title,
                "result": mission.result,
                "duration_ms": mission.duration_ms,
                "agents_used": mission.assigned_agents,
            }})

            # ── DB에 실행 기록 영속 저장 ──
            await self._persist_mission_log(mission, difficulty.value)

            # ── 업무 노트 자동 생성 ──
            try:
                await self._create_work_note(mission)
            except Exception as e:
                logger.warning("[Mission %s] 업무노트 생성 실패: %s", mission.id[:8], e)

        except asyncio.CancelledError:
            mission.status = MissionStatus.CANCELLED
            mission.completed_at = datetime.now().isoformat()
            await self._sync_conversations(mission)
            await self._store.save(mission)
            await self._emit(mission.id, {"event": "mission_cancelled", "data": {"id": mission.id}})

        except Exception as e:
            logger.error("[Mission %s] Failed: %s", mission.id[:8], e, exc_info=True)
            mission.status = MissionStatus.FAILED
            mission.error = str(e)[:500]
            mission.completed_at = datetime.now().isoformat()
            await self._sync_conversations(mission)
            await self._store.save(mission)
            await self._emit(mission.id, {"event": "mission_failed", "data": {
                "id": mission.id, "error": str(e)[:300],
            }})

    # ── Easy: CORE 직접 답변 ──────────────────────────────────────

    async def _execute_easy(self, mission: Mission):
        """간단한 질문 — API 호출로 직접 답변"""
        from jinxus.config import get_settings
        from anthropic import Anthropic

        settings = get_settings()
        client = Anthropic(api_key=settings.anthropic_api_key)

        mission.status = MissionStatus.IN_PROGRESS
        mission.assigned_agents = ["JINXUS_CORE"]
        await self._store.save(mission)

        await self._emit(mission.id, {"event": "mission_status", "data": {
            "id": mission.id, "status": "in_progress",
            "message": "응답 생성 중...",
            "agents": ["JINXUS_CORE"],
        }})

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.claude_fast_model or "claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": mission.original_input}],
        )

        result_text = response.content[0].text
        mission.result = result_text

        # 응답을 SSE 스트림으로 전달 (프론트엔드가 표시할 수 있도록)
        await self._emit(mission.id, {"event": "mission_message", "data": {
            "id": mission.id,
            "chunk": result_text,
        }})

    # ── Medium: 단일 에이전트 ─────────────────────────────────────

    async def _execute_medium(self, mission: Mission):
        """단일 에이전트 위임"""
        # 에이전트 선택 (간단한 규칙 기반)
        agent_name = self._select_single_agent(mission.original_input)

        mission.status = MissionStatus.IN_PROGRESS
        mission.assigned_agents = ["JINXUS_CORE", agent_name]
        await self._store.save(mission)

        # 브리핑
        await self._run_briefing(mission)

        # 에이전트 세션 확보
        session = await self._session_manager.create_session(agent_name)

        # 실행 (로그 폴링 포함)
        result = await self._execute_agent_with_logging(
            mission, agent_name, session, mission.original_input,
        )

        # 완료 신호 확인
        if result.output:
            signal = parse_completion_signal(result.output)
            if signal and signal.type == SIGNAL_BLOCKED:
                logger.warning(
                    "[Mission %s] 에이전트 %s BLOCKED: %s",
                    mission.id[:8], agent_name, signal.detail,
                )
                await self._emit(mission.id, {"event": "mission_agent_blocked", "data": {
                    "id": mission.id, "agent": agent_name,
                    "reason": signal.detail,
                    "timestamp": datetime.now().isoformat(),
                }})

        mission.result = result.output if result.success else f"실패: {result.error}"

        # 결과를 SSE로 전달
        if mission.result:
            await self._emit(mission.id, {"event": "mission_message", "data": {
                "id": mission.id, "chunk": mission.result,
            }})

    # ── Hard: 복수 에이전트 DAG 실행 ─────────────────────────────

    async def _execute_hard(self, mission: Mission):
        """복수 에이전트 DAG 기반 실행

        depends_on 필드가 있으면 DAG로 의존성 해석하여 실행.
        의존성 없는 태스크는 병렬, 있는 태스크는 선행 완료 후 실행.
        Competitive Dispatch 및 교차 검증도 유지.
        """
        from jinxus.core.dag_scheduler import DAGScheduler, CycleDetectedError

        # 작업 분해 (LLM으로)
        subtasks = await self._decompose_task(mission)

        agent_names = list(set(st["agent"] for st in subtasks))
        mission.status = MissionStatus.IN_PROGRESS
        mission.assigned_agents = ["JINXUS_CORE"] + agent_names
        await self._store.save(mission)

        # 브리핑
        await self._run_briefing(mission)

        # 에이전트 세션 일괄 확보
        sessions = await self._session_manager.ensure_agents(agent_names)

        # DAG 호환 형태로 변환 (task_id, depends_on 보장)
        dag_subtasks = []
        for i, st in enumerate(subtasks):
            dag_subtasks.append({
                "task_id": st.get("task_id", f"sub_{i:03d}"),
                "assigned_agent": st.get("agent", st.get("assigned_agent", "JX_CODER")),
                "instruction": st["instruction"],
                "depends_on": st.get("depends_on", []),
                "priority": st.get("priority", "normal"),
            })

        # depends_on이 하나라도 있으면 DAG 모드, 없으면 기존 병렬+경쟁 모드
        has_dependencies = any(st.get("depends_on") for st in dag_subtasks)

        if has_dependencies:
            # ── DAG 모드: depends_on 기반 실행 ──
            results = await self._execute_hard_dag(
                mission, dag_subtasks, sessions,
            )
        else:
            # ── 기존 모드: 병렬 + Competitive Dispatch ──
            results = await self._execute_hard_parallel(
                mission, subtasks, sessions, agent_names,
            )

        # 완료 신호 확인: BLOCKED 에이전트 감지 및 SSE 알림
        for r in results:
            agent = r.get("agent_name", r.get("agent", "?"))
            output = r.get("output", "")
            if output:
                signal = parse_completion_signal(output)
                if signal and signal.type == SIGNAL_BLOCKED:
                    logger.warning(
                        "[Mission %s] 에이전트 %s BLOCKED: %s",
                        mission.id[:8], agent, signal.detail,
                    )
                    await self._emit(mission.id, {"event": "mission_agent_blocked", "data": {
                        "id": mission.id, "agent": agent,
                        "reason": signal.detail,
                        "timestamp": datetime.now().isoformat(),
                    }})

        # ── 교차 검증 (HARD/RAID) ──
        results = await cross_validate(results, mission)

        retry_pass = sum(1 for r in results if not r.get('needs_retry'))
        await self._emit(mission.id, {"event": "mission_thinking", "data": {
            "id": mission.id, "from": "JINXUS_CORE",
            "step": "cross_validate",
            "detail": f"교차 검증 완료: {retry_pass}/{len(results)} 통과",
        }})

        # 결과 취합
        mission.result = await self._synthesize_results(mission, results)

        # 결과를 SSE로 전달
        if mission.result:
            await self._emit(mission.id, {"event": "mission_message", "data": {
                "id": mission.id, "chunk": mission.result,
            }})

    async def _execute_hard_dag(self, mission, dag_subtasks, sessions):
        """DAG 모드: depends_on 기반으로 의존성 해석하여 실행"""
        from jinxus.core.dag_scheduler import DAGScheduler, CycleDetectedError

        async def _dag_executor(subtask, dep_results):
            agent = subtask["assigned_agent"]
            instruction = subtask["instruction"]

            # 선행 태스크 결과를 instruction에 주입
            if dep_results:
                context_parts = []
                for dep_id, dep_res in dep_results.items():
                    dep_output = dep_res.get("output", "")[:500]
                    if dep_output:
                        context_parts.append(f"[{dep_id} 결과]: {dep_output}")
                if context_parts:
                    instruction = (
                        "[선행 작업 결과]\n"
                        + "\n".join(context_parts)
                        + f"\n\n[현재 작업]\n{instruction}"
                    )

            session = sessions.get(agent)
            if not session:
                return {
                    "task_id": subtask["task_id"],
                    "agent_name": agent,
                    "agent": agent,
                    "success": False,
                    "success_score": 0.0,
                    "output": "세션 없음",
                    "failure_reason": "세션 확보 실패",
                    "duration_ms": 0,
                }

            result = await self._execute_agent_with_logging(
                mission, agent, session, instruction,
            )
            return {
                "task_id": subtask["task_id"],
                "agent_name": agent,
                "agent": agent,
                "success": result.success,
                "success_score": 0.9 if result.success else 0.0,
                "output": result.output or "",
                "tool_calls": result.tool_calls,
                "file_changes": result.file_changes,
                "cost_usd": result.cost_usd,
                "duration_ms": result.duration_ms,
            }

        async def _on_progress(completed, total, task_id):
            await self._emit(mission.id, {"event": "mission_thinking", "data": {
                "id": mission.id, "from": "JINXUS_CORE",
                "step": "dag_progress",
                "detail": f"진행: {completed}/{total} (완료: {task_id})",
            }})

        try:
            scheduler = DAGScheduler(dag_subtasks)
            levels = scheduler.parallelism_levels
            level_desc = " -> ".join("[" + ", ".join(l) + "]" for l in levels)
            logger.info("[Mission %s] DAG 실행 계획: %s", mission.id[:8], level_desc)

            await self._emit(mission.id, {"event": "mission_thinking", "data": {
                "id": mission.id, "from": "JINXUS_CORE",
                "step": "dag_plan",
                "detail": f"DAG 실행 계획: {len(dag_subtasks)}개 태스크, {len(levels)}단계",
            }})

            results = await scheduler.execute(_dag_executor, on_progress=_on_progress)
        except CycleDetectedError as e:
            logger.error("[Mission %s] DAG 순환 참조: %s", mission.id[:8], e)
            await self._emit(mission.id, {"event": "mission_thinking", "data": {
                "id": mission.id, "from": "JINXUS_CORE",
                "step": "dag_fallback",
                "detail": "순환 참조 감지 -> 병렬 실행으로 폴백",
            }})
            for st in dag_subtasks:
                st["depends_on"] = []
            scheduler = DAGScheduler(dag_subtasks)
            results = await scheduler.execute(_dag_executor, on_progress=_on_progress)

        # 스킵된 태스크 로깅
        for r in results:
            if r.get("skipped"):
                logger.warning(
                    "[Mission %s] Task %s skipped: %s",
                    mission.id[:8], r["task_id"], r.get("skip_reason"),
                )

        return results

    async def _execute_hard_parallel(self, mission, subtasks, sessions, agent_names):
        """기존 병렬 + Competitive Dispatch 모드"""

        async def _run_subtask(subtask: dict):
            agent = subtask["agent"]
            instruction = subtask["instruction"]
            session = sessions.get(agent)
            if not session:
                return {"agent": agent, "success": False, "output": "세션 없음"}

            result = await self._execute_agent_with_logging(
                mission, agent, session, instruction,
            )
            return {
                "agent": agent,
                "success": result.success,
                "output": result.output or "",
                "tool_calls": result.tool_calls,
                "file_changes": result.file_changes,
                "cost_usd": result.cost_usd,
                "duration_ms": result.duration_ms,
            }

        # Competitive Dispatch 지원
        mission_type_val = mission.type.value if hasattr(mission.type, 'value') else str(mission.type)
        normal_subtasks = []
        competitive_subtasks = []

        for st in subtasks:
            if should_use_competitive(mission_type_val, st, len(subtasks)):
                competitive_subtasks.append(st)
            else:
                normal_subtasks.append(st)

        normal_tasks = [asyncio.create_task(_run_subtask(st)) for st in normal_subtasks]

        competitive_tasks = []
        for st in competitive_subtasks:
            comp_agents = self._pick_competitive_agents(st, agent_names)
            comp_sessions = await self._session_manager.ensure_agents(comp_agents)
            sessions.update(comp_sessions)
            competitive_tasks.append(
                asyncio.create_task(
                    competitive_execute(st, comp_agents, _run_subtask)
                )
            )

        all_results = await asyncio.gather(*(normal_tasks + competitive_tasks))
        results = list(all_results)

        if competitive_subtasks:
            logger.info(
                "[Mission %s] Competitive: %d건 경쟁 실행, %d건 일반 실행",
                mission.id[:8], len(competitive_subtasks), len(normal_subtasks),
            )

        return results

    # ── 에이전트 실행 + 실시간 스트리밍 ─────────────────────────

    async def _execute_agent_with_logging(
        self,
        mission: Mission,
        agent_name: str,
        session,
        instruction: str,
    ):
        """에이전트 실행 + on_event 콜백으로 실시간 SSE 이벤트 발행

        v4.1: 200ms 로그 폴링 대신 on_event 콜백으로 StreamEvent를 직접 수신.
        도구 호출, 어시스턴트 텍스트, 결과가 발생하는 즉시 SSE로 전달.
        """

        # DM: 지시
        await self._store.add_conversation(
            mission.id, "JINXUS_CORE", agent_name, instruction[:200], "dm"
        )
        await self._emit(mission.id, {"event": "agent_dm", "data": {
            "id": mission.id, "from": "JINXUS_CORE", "to": agent_name,
            "message": instruction[:200],
            "timestamp": datetime.now().isoformat(),
        }})
        await self._emit(mission.id, {"event": "mission_agent_activity", "data": {
            "id": mission.id, "agent": agent_name, "action": "working",
        }})

        # 실시간 스트림 이벤트 큐 (on_event는 sync 콜백이므로 큐를 통해 async emit)
        event_queue: asyncio.Queue = asyncio.Queue()
        _tool_count = 0
        _text_buffer: list = []

        def _on_stream_event(event: StreamEvent):
            """ClaudeProcess의 StreamParser가 호출하는 sync 콜백.
            이벤트를 큐에 넣고 relay 태스크가 비동기로 SSE 발행."""
            try:
                event_queue.put_nowait(event)
            except Exception:
                pass

        # 이벤트 릴레이 태스크: 큐에서 꺼내 SSE로 발행
        async def _relay_events():
            nonlocal _tool_count
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    except asyncio.TimeoutError:
                        # 버퍼에 쌓인 텍스트 플러시
                        await _flush_text_buffer()
                        continue

                    etype = event.event_type

                    # 헬퍼: SSE 발행 + 대화 로그 저장
                    async def _emit_and_save(detail: str, msg_type: str = "thinking"):
                        await self._emit(mission.id, {"event": "mission_thinking", "data": {
                            "id": mission.id,
                            "from": agent_name,
                            "step": "agent_progress",
                            "detail": detail,
                            "timestamp": datetime.now().isoformat(),
                        }})
                        await self._store.add_conversation(
                            mission.id, agent_name, None, detail[:200], msg_type,
                        )

                    # 도구 사용 시작
                    if etype == StreamEventType.TOOL_USE and event.tool_name:
                        _tool_count += 1
                        await _flush_text_buffer()
                        detail = format_tool_detail(event.tool_name, event.tool_input or {})
                        await _emit_and_save(f"\U0001f527 {event.tool_name}: {detail}")

                    # 어시스턴트 메시지 (전체 턴 완료 시)
                    elif etype == StreamEventType.ASSISTANT_MESSAGE:
                        if event.tool_name:
                            _tool_count += 1
                            await _flush_text_buffer()
                            detail = format_tool_detail(event.tool_name, event.tool_input or {})
                            await _emit_and_save(f"\U0001f527 {event.tool_name}: {detail}")
                        if event.text:
                            text_preview = event.text[:200]
                            msg = f"\U0001f4ac {text_preview}"
                            await self._emit(mission.id, {"event": "mission_thinking", "data": {
                                "id": mission.id,
                                "from": agent_name,
                                "step": "agent_thinking",
                                "detail": msg,
                                "timestamp": datetime.now().isoformat(),
                            }})
                            await self._store.add_conversation(
                                mission.id, agent_name, None, msg[:200], "thinking",
                            )

                    # 콘텐츠 델타 (스트리밍 텍스트 조각) — 저장 안 함 (flush 시 저장)
                    elif etype == StreamEventType.CONTENT_BLOCK_DELTA:
                        if event.text:
                            _text_buffer.append(event.text)
                            if sum(len(t) for t in _text_buffer) >= 100:
                                await _flush_text_buffer()

                    # 시스템 초기화 (세션 시작)
                    elif etype == StreamEventType.SYSTEM_INIT:
                        tools_count = len(event.tools or [])
                        model_name = event.model or "unknown"
                        await _emit_and_save(f"\u26a1 세션 시작 (모델: {model_name}, 도구: {tools_count}개)")

                    # 도구 실행 결과
                    elif etype == StreamEventType.TOOL_RESULT:
                        output_preview = (event.tool_output or "")[:100]
                        if output_preview:
                            prefix = "\u2717" if event.is_error else "\u2713"
                            await _emit_and_save(f"{prefix} {output_preview}")

                    # 결과 (실행 완료)
                    elif etype == StreamEventType.RESULT:
                        await _flush_text_buffer()
                        cost = event.total_cost_usd or 0
                        turns = event.num_turns or 0
                        dur = event.duration_ms or 0
                        summary = (
                            f"\u2705 실행 완료 (도구 {_tool_count}개, "
                            f"{turns}턴, {dur/1000:.1f}s, ${cost:.4f})"
                        )
                        await _emit_and_save(summary)

            except asyncio.CancelledError:
                # 종료 시 남은 텍스트 플러시
                await _flush_text_buffer()

        async def _flush_text_buffer():
            """버퍼에 쌓인 텍스트 델타를 하나로 합쳐 발행 + 저장"""
            if not _text_buffer:
                return
            combined = "".join(_text_buffer)
            _text_buffer.clear()
            if combined.strip():
                preview = combined.strip()[:150]
                msg = f"\U0001f4ac {preview}"
                await self._emit(mission.id, {"event": "mission_thinking", "data": {
                    "id": mission.id,
                    "from": agent_name,
                    "step": "agent_thinking",
                    "detail": msg,
                    "timestamp": datetime.now().isoformat(),
                }})
                await self._store.add_conversation(
                    mission.id, agent_name, None, msg[:200], "thinking",
                )

        # 릴레이 태스크 시작
        relay_task = asyncio.create_task(_relay_events())

        try:
            # ── CLI 실행 (on_event 콜백 전달) ──
            result = await execute_command(
                session_id=session.session_id,
                prompt=instruction,
                on_event=_on_stream_event,
            )
        except (AgentNotFoundError, AgentNotAliveError, AlreadyExecutingError) as e:
            from jinxus.cli_engine.models import ExecutionResult
            result = ExecutionResult(
                success=False, session_id=session.session_id, error=str(e),
            )
        finally:
            # 릴레이 태스크에게 남은 이벤트 처리 시간을 주고 종료
            await asyncio.sleep(0.3)
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass

        # 보고
        report_msg = result.output[:200] if result.output else ("완료" if result.success else "실패")
        await self._store.add_conversation(
            mission.id, agent_name, "JINXUS_CORE", report_msg, "report"
        )

        # 도구 사용 내역 발행
        if result.tool_calls:
            await self._emit(mission.id, {"event": "mission_tool_calls", "data": {
                "id": mission.id, "agent": agent_name,
                "tools": result.tool_calls[:10],
                "timestamp": datetime.now().isoformat(),
            }})

        await self._emit(mission.id, {"event": "agent_report", "data": {
            "id": mission.id, "from": agent_name, "to": "JINXUS_CORE",
            "message": report_msg,
            "success": result.success,
            "tool_calls": [
                {"name": tc.get("name", ""), "detail": tc.get("input", {})}
                for tc in (result.tool_calls or [])[:10]
            ],
            "file_changes": result.file_changes or [],
            "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms,
            "timestamp": datetime.now().isoformat(),
        }})

        await self._emit(mission.id, {"event": "mission_agent_activity", "data": {
            "id": mission.id, "agent": agent_name, "action": "done",
        }})

        # 성과 프로파일 기록
        try:
            task_type = self._infer_task_type(instruction)
            tracker = get_performance_tracker()
            await tracker.record_result(
                agent_name=agent_name,
                task_type=task_type,
                success=result.success,
                duration_ms=result.duration_ms,
            )
        except Exception as e:
            logger.warning("[Mission %s] 성과 기록 실패: %s", mission.id[:8], e)

        return result

    # ── 대화 로그 동기화 ─────────────────────────────────────────

    async def _sync_conversations(self, mission: Mission):
        """Redis에 저장된 agent_conversations를 로컬 mission 객체에 병합.

        add_conversation()은 Redis에 직접 저장하지만 로컬 객체는 업데이트하지 않는다.
        save() 호출 전에 이 메서드로 Redis의 최신 대화 로그를 가져와야 덮어쓰기를 방지한다.
        """
        try:
            fresh = await self._store.get(mission.id)
            if fresh and fresh.agent_conversations:
                mission.agent_conversations = fresh.agent_conversations
        except Exception as e:
            logger.warning("[Mission %s] 대화 로그 동기화 실패: %s", mission.id[:8], e)

    # ── 브리핑 ────────────────────────────────────────────────────

    async def _run_briefing(self, mission: Mission):
        agents = mission.assigned_agents or ["JINXUS_CORE"]

        await self._emit(mission.id, {"event": "mission_huddle", "data": {
            "id": mission.id, "participants": agents,
            "topic": f"미션 브리핑: {mission.title}",
        }})

        briefing_msg = f"미션: {mission.title}. {mission.description[:200]}"
        await self._store.add_conversation(mission.id, "JINXUS_CORE", None, briefing_msg, "huddle")

        await self._emit(mission.id, {"event": "mission_briefing_message", "data": {
            "id": mission.id, "from": "JINXUS_CORE", "message": briefing_msg,
            "timestamp": datetime.now().isoformat(),
        }})

        for agent in agents:
            if agent == "JINXUS_CORE":
                continue
            await self._store.add_conversation(mission.id, agent, "JINXUS_CORE", "네, 맡겠습니다.", "huddle")
            await self._emit(mission.id, {"event": "mission_briefing_message", "data": {
                "id": mission.id, "from": agent, "message": "네, 맡겠습니다.",
                "timestamp": datetime.now().isoformat(),
            }})

    # ── 작업 분해 (LLM) ──────────────────────────────────────────

    async def _decompose_task(self, mission: Mission) -> List[dict]:
        """LLM으로 작업을 서브태스크로 분해"""
        from jinxus.config import get_settings
        from anthropic import Anthropic
        import json

        settings = get_settings()
        client = Anthropic(api_key=settings.anthropic_api_key)

        # 사용 가능한 에이전트 목록
        try:
            from jinxus.agents.personas import get_all_personas
            personas = get_all_personas()
            agent_list = "\n".join(
                f"- {name}: {p.role} ({p.display_name})"
                for name, p in personas.items()
                if p.rank >= 2  # 팀 리드 이상만
            )
        except Exception:
            agent_list = "- JX_CODER: 코드 작성\n- JX_RESEARCHER: 조사\n- JX_ANALYST: 분석"

        await self._emit(mission.id, {"event": "mission_thinking", "data": {
            "id": mission.id, "from": "JINXUS_CORE",
            "step": "decompose", "detail": "작업 분해 중...",
        }})

        # 성과 데이터 수집
        perf_section = ""
        try:
            tracker = get_performance_tracker()
            perf_section = await tracker.get_recommendation_prompt()
        except Exception as e:
            logger.debug("[Mission %s] 성과 데이터 로드 실패: %s", mission.id[:8], e)

        prompt = f"""다음 작업을 서브태스크로 분해하라. 각 서브태스크에 적합한 에이전트를 배정하라.
성공률이 높고 해당 작업 유형 경험이 많은 에이전트를 우선 배정하라.

## 사용 가능한 에이전트
{agent_list}

{perf_section}

## 작업
{mission.original_input}

## 응답 형식 (JSON)
[
  {{"agent": "JX_코드명", "instruction": "구체적 지시사항"}},
  {{"agent": "JX_코드명", "instruction": "구체적 지시사항", "execution_mode": "competitive"}},
  ...
]
주의: agent 필드에 반드시 JX_로 시작하는 코드명(JX_CODER, JX_BACKEND 등)만 사용하라. 한글 이름 금지.

## execution_mode 옵션
- 생략 시 일반 실행 (기본값)
- "competitive": 동일 태스크를 2명에게 동시 위임하여 우수한 결과 채택 (비용 2배)
  - RAID 미션에서 결과 품질이 매우 중요한 핵심 서브태스크에만 적용
  - 예: 아키텍처 설계, 핵심 알고리즘 구현, 보안 감사 등

JSON만 응답하라. 설명 불필요."""

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.claude_model or "claude-sonnet-4-6",
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()

        # JSON 추출
        try:
            # ```json ... ``` 래핑 제거
            if "```" in text:
                start = text.index("[")
                end = text.rindex("]") + 1
                text = text[start:end]
            subtasks = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # 파싱 실패 → 단일 태스크로 폴백
            logger.warning("[Mission %s] Decompose parse failed, using fallback", mission.id[:8])
            subtasks = [{"agent": "JX_CODER", "instruction": mission.original_input}]

        # agent 필드 정규화: LLM이 이름 형태로 반환한 경우 코드명으로 변환
        import re
        for st in subtasks:
            agent_val = st.get("agent", "")
            if agent_val and not agent_val.startswith("JX_") and agent_val != "JINXUS_CORE":
                # "예린(JX_FRONTEND)" → "JX_FRONTEND" 추출
                match = re.search(r'(JX_\w+)', agent_val)
                if match:
                    st["agent"] = match.group(1)
                else:
                    # 이름으로만 된 경우 personas에서 역조회
                    try:
                        all_p = get_all_personas() if 'get_all_personas' not in dir() else personas
                        for code, p in all_p.items():
                            if p.korean_name in agent_val or p.display_name in agent_val:
                                st["agent"] = code
                                break
                    except Exception:
                        pass

        await self._emit(mission.id, {"event": "mission_thinking", "data": {
            "id": mission.id, "from": "JINXUS_CORE",
            "step": "decompose", "detail": f"서브태스크 {len(subtasks)}개 분해 완료",
        }})

        return subtasks

    # ── 결과 취합 (LLM) ──────────────────────────────────────────

    async def _synthesize_results(self, mission: Mission, results: list) -> str:
        """서브태스크 결과를 종합"""
        from jinxus.config import get_settings
        from anthropic import Anthropic

        settings = get_settings()
        client = Anthropic(api_key=settings.anthropic_api_key)

        results_text = ""
        for r in results:
            agent_code = r.get("agent", "?")
            label = _agent_label(agent_code)
            output = r.get("output", "")[:1000]
            success = "✅" if r.get("success") else "❌"
            results_text += f"\n### {label} {success}\n{output}\n"

        prompt = f"""다음 직원들의 작업 결과를 종합하여 최종 보고서를 작성하라.

## 원래 요청
{mission.original_input}

## 직원별 작업 결과
{results_text}

## 지시
- 결론부터 말하라
- 각 직원의 이름과 기여를 포함하라 (코드명 JX_xxx 절대 사용 금지, 이름만 사용)
- 실패한 작업이 있으면 언급하라
- 불필요한 수식어 금지"""

        response = await asyncio.to_thread(
            client.messages.create,
            model=settings.claude_model or "claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    # ── Competitive Dispatch 에이전트 선택 ──────────────────────

    def _pick_competitive_agents(self, subtask: dict, available_agents: List[str]) -> List[str]:
        """경쟁 실행할 에이전트 2명을 선택한다.

        원래 배정된 에이전트 + 같은 도메인의 다른 에이전트.
        적합한 2명이 없으면 원래 에이전트만 반환 (단독 실행).
        """
        primary = subtask.get("agent", "JX_CODER")

        # 같은 도메인 에이전트 매핑
        _DOMAIN_PEERS: Dict[str, List[str]] = {
            "JX_CODER": ["JX_REVIEWER", "JX_OPS"],
            "JX_REVIEWER": ["JX_CODER", "JX_ANALYST"],
            "JX_RESEARCHER": ["JX_ANALYST", "JX_WRITER"],
            "JX_ANALYST": ["JX_RESEARCHER", "JX_CODER"],
            "JX_WRITER": ["JX_RESEARCHER", "JX_ANALYST"],
            "JX_OPS": ["JX_CODER", "JX_SECURITY"],
            "JX_DESIGNER": ["JX_CODER", "JX_WRITER"],
            "JX_SECURITY": ["JX_OPS", "JX_REVIEWER"],
            "JX_DATA": ["JX_ANALYST", "JX_CODER"],
        }

        peers = _DOMAIN_PEERS.get(primary, [])
        for peer in peers:
            if peer != primary:
                return [primary, peer]

        # 피어 없으면 available_agents에서 primary 아닌 첫 번째
        for agent in available_agents:
            if agent != primary and agent != "JINXUS_CORE":
                return [primary, agent]

        return [primary]

    # ── 에이전트 선택 (규칙 기반) ─────────────────────────────────

    def _select_single_agent(self, user_input: str) -> str:
        """입력에서 적합한 에이전트 1명 선택"""
        text = user_input.lower()

        code_keywords = ["코드", "구현", "개발", "프론트", "백엔드", "api", "버그", "수정", "리팩"]
        research_keywords = ["조사", "검색", "분석", "찾아", "알아봐", "비교"]
        write_keywords = ["작성", "문서", "글", "블로그", "이메일"]
        ops_keywords = ["배포", "서버", "도커", "인프라", "모니터"]

        if any(k in text for k in code_keywords):
            return "JX_CODER"
        if any(k in text for k in research_keywords):
            return "JX_RESEARCHER"
        if any(k in text for k in write_keywords):
            return "JX_WRITER"
        if any(k in text for k in ops_keywords):
            return "JX_OPS"

        return "JX_CODER"  # 기본값

    @staticmethod
    def _infer_task_type(instruction: str) -> str:
        """지시 내용에서 작업 유형 추론 (성과 프로파일용)"""
        text = instruction.lower()
        mapping = [
            (["코드", "구현", "개발", "프론트", "백엔드", "api", "버그", "수정", "리팩"], "coding"),
            (["조사", "검색", "찾아", "알아봐", "비교"], "research"),
            (["분석", "데이터", "통계", "리포트"], "analysis"),
            (["작성", "문서", "글", "블로그", "이메일"], "writing"),
            (["배포", "서버", "도커", "인프라", "모니터"], "ops"),
            (["테스트", "검증", "확인"], "testing"),
        ]
        for keywords, task_type in mapping:
            if any(k in text for k in keywords):
                return task_type
        return "general"

    # ── DB 영속 저장 ──────────────────────────────────────────────

    async def _persist_mission_log(self, mission: Mission, difficulty: str):
        """미션 실행 기록을 MetaStore(SQLite)에 영속 저장

        저장되는 정보:
        - 미션 ID, 제목, 타입, 난이도
        - 참여 에이전트, 결과, 소요 시간
        - 에이전트 대화 로그 요약
        """
        try:
            from jinxus.memory.meta_store import get_meta_store
            import uuid

            meta = get_meta_store()

            # 각 에이전트별로 작업 로그 저장
            for agent_name in mission.assigned_agents:
                if agent_name == "JINXUS_CORE":
                    continue

                # 해당 에이전트의 대화에서 보고 내용 추출
                agent_output = ""
                for conv in (mission.agent_conversations or []):
                    if conv.get("from") == agent_name and conv.get("type") == "report":
                        agent_output = conv.get("message", "")
                        break

                await meta.log_task(
                    main_task_id=mission.id,
                    agent_name=agent_name,
                    instruction=mission.original_input[:500],
                    success=mission.status == MissionStatus.COMPLETE,
                    success_score=0.9 if mission.status == MissionStatus.COMPLETE else 0.0,
                    duration_ms=mission.duration_ms or 0,
                    output=agent_output[:2000] if agent_output else mission.result[:2000] if mission.result else "",
                )

            # JINXUS_CORE 작업 로그도 저장 (취합 역할)
            await meta.log_task(
                main_task_id=mission.id,
                agent_name="JINXUS_CORE",
                instruction=mission.original_input[:500],
                success=mission.status == MissionStatus.COMPLETE,
                success_score=0.9 if mission.status == MissionStatus.COMPLETE else 0.0,
                duration_ms=mission.duration_ms or 0,
                output=f"[{mission.type.value}/{difficulty}] {mission.title}",
            )

            logger.info("[Mission %s] Persisted to DB (%d agents)", mission.id[:8], len(mission.assigned_agents))
        except Exception as e:
            logger.warning("[Mission %s] DB persist failed: %s", mission.id[:8], e)

    # ── 업무 노트 자동 생성 ──────────────────────────────────────

    async def _create_work_note(self, mission: Mission):
        """미션 완료 시 업무노트(Notes 탭) 자동 생성"""
        from jinxus.api.routers.dev_notes import create_work_note

        conversations = mission.agent_conversations or []
        conv_lines = []
        for c in conversations[-20:]:
            sender = _agent_label(c.get('from', '?'))
            conv_lines.append(f"- **{sender}**: {c.get('message', '')[:200]}")
        conv_summary = "\n".join(conv_lines) if conv_lines else "(대화 없음)"

        duration_str = ""
        if mission.duration_ms:
            secs = mission.duration_ms / 1000
            if secs < 60:
                duration_str = f"{secs:.1f}초"
            else:
                duration_str = f"{secs / 60:.1f}분"

        type_labels = {
            "quick": "QUICK", "standard": "STANDARD",
            "epic": "EPIC", "raid": "RAID",
        }
        type_val = mission.type.value if hasattr(mission.type, 'value') else str(mission.type)
        type_label = type_labels.get(type_val, "STANDARD")

        content = f"""# {mission.title}

**날짜:** {datetime.now().strftime("%Y-%m-%d %H:%M")}
**업무 타입:** {type_label}
**상태:** 완료
**소요 시간:** {duration_str or '측정 안 됨'}
**참여 직원:** {_agent_names_str(mission.assigned_agents) if mission.assigned_agents else '없음'}

## 업무 요청

{mission.original_input}

## 실행 결과

{mission.result or '(결과 없음)'}

## 에이전트 활동 로그

{conv_summary}
"""
        create_work_note(mission.title, content)
        logger.info("[Mission %s] 업무노트 생성 완료: %s", mission.id[:8], mission.title)


# 싱글톤
_executor: Optional[MissionExecutorV4] = None


def get_mission_executor_v4() -> MissionExecutorV4:
    global _executor
    if _executor is None:
        _executor = MissionExecutorV4()
    return _executor
