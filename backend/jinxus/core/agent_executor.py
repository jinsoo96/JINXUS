"""통합 에이전트 실행 서비스

Geny의 핵심 철학: **모든 에이전트 실행이 이 하나의 모듈을 통과.**
미션이든, 직접 커맨드든, 채팅 브로드캐스트든 같은 경로.

이 모듈이 소유하는 것:
- 활성 실행 추적 (_active_executions)
- 세션 로깅 (log_command / log_response)
- 비용 기록
- 자동 부활 (agent.revive)
- 중복 실행 방지
- 타임아웃 처리
"""
import asyncio
import time
from logging import getLogger
from typing import Dict, Optional

from jinxus.cli_engine.models import ExecutionResult, SessionStatus
from jinxus.cli_engine.session_logger import get_session_logger
from jinxus.cli_engine.session_manager import get_agent_session_manager
from jinxus.core.completion_signals import (
    parse_completion_signal, is_failure_signal, is_actionable_signal,
    SIGNAL_BLOCKED, SIGNAL_ERROR,
)
from jinxus.core.context_guard import get_context_guard, BudgetStatus

logger = getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class AgentNotFoundError(Exception):
    pass


class AgentNotAliveError(Exception):
    pass


class AlreadyExecutingError(Exception):
    pass


# ============================================================================
# Active execution registry
# ============================================================================

_active_executions: Dict[str, dict] = {}


def is_executing(session_id: str) -> bool:
    holder = _active_executions.get(session_id)
    return holder is not None and not holder.get("done", True)


def cleanup_execution(session_id: str):
    _active_executions.pop(session_id, None)


# ============================================================================
# Resolve & revive
# ============================================================================

async def _resolve_agent(session_id: str):
    """에이전트 조회 + 자동 부활"""
    manager = get_agent_session_manager()
    agent = manager.get_session(session_id)
    if not agent:
        # session_id가 아닌 agent_name일 수 있음
        agent = manager.get_session_by_name(session_id)
    if not agent:
        raise AgentNotFoundError(f"Agent session not found: {session_id}")

    if not agent.is_alive():
        logger.info("[%s] Agent not alive, attempting revive", session_id)
        revived = await agent.revive()
        if not revived:
            raise AgentNotAliveError(
                f"Agent {agent.agent_name} is not alive and revival failed"
            )
        logger.info("[%s] ✅ Agent revived", session_id)

    return agent


# ============================================================================
# Core execution (shared by sync & background)
# ============================================================================

async def _execute_core(
    agent,
    prompt: str,
    holder: dict,
    *,
    timeout: Optional[float] = None,
    on_event=None,
) -> ExecutionResult:
    """실행 라이프사이클

    1. Invoke agent (CLI 프로세스)
    2. 결과 기록
    """
    try:
        result = await agent.invoke(
            prompt=prompt,
            timeout=timeout,
            on_event=on_event,
        )

        holder["result"] = result.to_dict()
        return result

    except asyncio.TimeoutError:
        duration_ms = int((time.time() - holder["start_time"]) * 1000)
        error_msg = f"Timeout after {duration_ms / 1000:.1f}s"
        result = ExecutionResult(
            success=False,
            session_id=agent.session_id,
            error=error_msg,
            duration_ms=duration_ms,
        )
        holder["error"] = error_msg
        holder["result"] = result.to_dict()
        return result

    except asyncio.CancelledError:
        duration_ms = int((time.time() - holder["start_time"]) * 1000)
        result = ExecutionResult(
            success=False,
            session_id=agent.session_id,
            error="Execution cancelled",
            duration_ms=duration_ms,
        )
        holder["error"] = "Execution cancelled"
        holder["result"] = result.to_dict()
        return result

    except Exception as e:
        duration_ms = int((time.time() - holder["start_time"]) * 1000)
        logger.error("❌ Execution failed for %s: %s", agent.session_id, e, exc_info=True)
        result = ExecutionResult(
            success=False,
            session_id=agent.session_id,
            error=str(e),
            duration_ms=duration_ms,
        )
        holder["error"] = str(e)
        holder["result"] = result.to_dict()
        return result

    finally:
        holder["done"] = True


# ============================================================================
# Public API — synchronous execution
# ============================================================================

async def execute_command(
    session_id: str,
    prompt: str,
    *,
    timeout: Optional[float] = None,
    on_event=None,
) -> ExecutionResult:
    """에이전트 명령 실행 (동기, 완료까지 대기)

    미션 실행, 직접 커맨드, 브로드캐스트 모두 이 함수를 호출.

    Args:
        session_id: 세션 ID 또는 에이전트 이름
        prompt: 실행할 프롬프트
        timeout: 타임아웃 (초)
        on_event: StreamEvent 실시간 콜백

    Raises:
        AgentNotFoundError: 세션 없음
        AgentNotAliveError: 프로세스 죽음, 부활 실패
        AlreadyExecutingError: 이미 실행 중
    """
    agent = await _resolve_agent(session_id)
    actual_sid = agent.session_id

    if is_executing(actual_sid):
        raise AlreadyExecutingError(
            f"Already executing on {agent.agent_name} ({actual_sid})"
        )

    # Context Guard: 실행 전 상태 체크
    guard = get_context_guard()
    pre_check = guard.check([{"content": prompt}])
    if pre_check.status == BudgetStatus.BLOCK:
        logger.warning(
            "[%s] Context Guard BLOCK 상태 (%.1f%%), 컴팩션 시도",
            actual_sid, pre_check.usage_percent,
        )
    elif pre_check.status == BudgetStatus.WARN:
        logger.warning(
            "[%s] Context Guard WARN 상태 (%.1f%%)",
            actual_sid, pre_check.usage_percent,
        )

    holder = {
        "done": False,
        "result": None,
        "error": None,
        "start_time": time.time(),
    }
    _active_executions[actual_sid] = holder

    try:
        result = await _execute_core(
            agent, prompt, holder,
            timeout=timeout,
            on_event=on_event,
        )

        # 완료 신호 확인
        if result.output:
            signal = parse_completion_signal(result.output)
            if signal:
                if signal.type == SIGNAL_BLOCKED:
                    logger.warning(
                        "[%s] BLOCKED 신호 감지: %s", actual_sid, signal.detail,
                    )
                elif signal.type == SIGNAL_ERROR:
                    logger.error(
                        "[%s] ERROR 신호 감지: %s", actual_sid, signal.detail,
                    )
                    result.success = False
                    if not result.error:
                        result.error = f"ERROR: {signal.detail}"

        # Context Guard: 실행 후 상태 체크
        post_check = guard.check([{"content": result.output or ""}])
        if post_check.status != pre_check.status:
            log_fn = logger.warning if post_check.status in (BudgetStatus.BLOCK, BudgetStatus.OVERFLOW) else logger.info
            log_fn(
                "[%s] Context Guard 상태 변경: %s -> %s (%.1f%%)",
                actual_sid, pre_check.status.value, post_check.status.value,
                post_check.usage_percent,
            )

        return result
    finally:
        cleanup_execution(actual_sid)


# ============================================================================
# Public API — background execution
# ============================================================================

async def start_command_background(
    session_id: str,
    prompt: str,
    *,
    timeout: Optional[float] = None,
    on_event=None,
) -> dict:
    """백그라운드 실행 시작 — holder를 즉시 반환

    SSE 스트리밍에서 holder["done"]과 session_logger를 폴링하여
    실시간 로그를 전달.
    """
    agent = await _resolve_agent(session_id)
    actual_sid = agent.session_id

    if is_executing(actual_sid):
        raise AlreadyExecutingError(
            f"Already executing on {agent.agent_name} ({actual_sid})"
        )

    holder = {
        "done": False,
        "result": None,
        "error": None,
        "start_time": time.time(),
        "session_id": actual_sid,
        "agent_name": agent.agent_name,
    }
    _active_executions[actual_sid] = holder

    async def _run():
        try:
            await _execute_core(
                agent, prompt, holder,
                timeout=timeout,
                on_event=on_event,
            )
        finally:
            # 5분 후 자동 정리
            async def _deferred_cleanup():
                await asyncio.sleep(300)
                cleanup_execution(actual_sid)
            asyncio.create_task(_deferred_cleanup())

    asyncio.create_task(_run())
    return holder
