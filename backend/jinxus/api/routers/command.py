"""Command Router — 에이전트 직접 커맨드 실행 API

에이전트에게 직접 명령을 보내는 엔드포인트.
미션 시스템을 거치지 않고 특정 에이전트 CLI에 바로 실행.
"""
import asyncio
import json
import time
from logging import getLogger
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse

from jinxus.core.agent_executor import (
    execute_command,
    start_command_background,
    is_executing,
    AgentNotFoundError,
    AgentNotAliveError,
    AlreadyExecutingError,
)
from jinxus.cli_engine.session_logger import get_session_logger
from jinxus.cli_engine.session_manager import get_agent_session_manager

logger = getLogger(__name__)
router = APIRouter(prefix="/command", tags=["command"])


# ── Models ────────────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    prompt: str = Field(..., description="실행할 프롬프트")
    timeout: Optional[float] = Field(None, description="타임아웃 (초)")


class ExecuteResponse(BaseModel):
    success: bool
    session_id: str
    agent_name: str
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0
    cost_usd: float = 0.0
    tool_calls: List[Dict[str, Any]] = []
    file_changes: List[Dict[str, Any]] = []
    num_turns: int = 0


class BatchExecuteRequest(BaseModel):
    agent_names: List[str] = Field(..., description="에이전트 이름 목록")
    prompt: str = Field(..., description="실행할 프롬프트")
    timeout: Optional[float] = Field(600.0, description="에이전트당 타임아웃")
    parallel: bool = Field(True, description="병렬 실행 여부")


class BatchResult(BaseModel):
    total: int
    successful: int
    failed: int
    results: List[ExecuteResponse]
    total_duration_ms: int


# ── 단일 실행 ─────────────────────────────────────────────────────

@router.post("/{agent_name}/execute", response_model=ExecuteResponse)
async def execute_agent_command(agent_name: str, request: ExecuteRequest):
    """특정 에이전트에게 직접 명령 실행 (동기)"""
    manager = get_agent_session_manager()

    # 세션 확보 (없으면 생성)
    session = manager.get_session_by_name(agent_name)
    if not session:
        try:
            session = await manager.create_session(agent_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"세션 생성 실패: {e}")

    try:
        result = await execute_command(
            session_id=session.session_id,
            prompt=request.prompt,
            timeout=request.timeout,
        )
        return ExecuteResponse(
            success=result.success,
            session_id=session.session_id,
            agent_name=agent_name,
            output=result.output,
            error=result.error,
            duration_ms=result.duration_ms,
            cost_usd=result.cost_usd,
            tool_calls=result.tool_calls,
            file_changes=result.file_changes,
            num_turns=result.num_turns,
        )
    except AlreadyExecutingError:
        raise HTTPException(status_code=409, detail=f"{agent_name}이(가) 이미 실행 중")
    except AgentNotAliveError as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── SSE 스트리밍 실행 ─────────────────────────────────────────────

@router.post("/{agent_name}/execute/stream")
async def stream_agent_command(agent_name: str, request: ExecuteRequest):
    """에이전트 명령 실행 + SSE 스트리밍 (실시간 도구 로그)"""
    manager = get_agent_session_manager()

    session = manager.get_session_by_name(agent_name)
    if not session:
        try:
            session = await manager.create_session(agent_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"세션 생성 실패: {e}")

    try:
        holder = await start_command_background(
            session_id=session.session_id,
            prompt=request.prompt,
            timeout=request.timeout,
        )
    except AlreadyExecutingError:
        raise HTTPException(status_code=409, detail=f"{agent_name}이(가) 이미 실행 중")

    async def event_generator():
        session_logger = get_session_logger(session.session_id, create_if_missing=False)
        cursor = session_logger.get_cache_length() if session_logger else 0
        heartbeat_interval = 5.0
        last_heartbeat = time.time()

        while not holder.get("done", False):
            # 새 로그 확인
            if session_logger:
                new_entries, cursor = session_logger.get_cache_entries_since(cursor)
                for entry in new_entries:
                    yield _sse_event("log", entry.to_dict())

            # 하트비트
            now = time.time()
            if now - last_heartbeat >= heartbeat_interval:
                yield _sse_event("heartbeat", {"ts": now})
                last_heartbeat = now

            await asyncio.sleep(0.2)

        # 최종 로그 플러시
        if session_logger:
            new_entries, cursor = session_logger.get_cache_entries_since(cursor)
            for entry in new_entries:
                yield _sse_event("log", entry.to_dict())

        # 결과
        result = holder.get("result", {})
        yield _sse_event("result", result)
        yield _sse_event("done", {"session_id": session.session_id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ── 배치 실행 ─────────────────────────────────────────────────────

@router.post("/batch", response_model=BatchResult)
async def execute_batch_command(request: BatchExecuteRequest):
    """여러 에이전트에게 동시 명령"""
    manager = get_agent_session_manager()
    start = time.time()
    results = []

    async def _run_one(name: str):
        session = manager.get_session_by_name(name)
        if not session:
            try:
                session = await manager.create_session(name)
            except Exception as e:
                return ExecuteResponse(
                    success=False, session_id="", agent_name=name,
                    error=f"세션 생성 실패: {e}",
                )

        try:
            result = await execute_command(
                session_id=session.session_id,
                prompt=request.prompt,
                timeout=request.timeout,
            )
            return ExecuteResponse(
                success=result.success,
                session_id=session.session_id,
                agent_name=name,
                output=result.output,
                error=result.error,
                duration_ms=result.duration_ms,
                cost_usd=result.cost_usd,
                tool_calls=result.tool_calls,
                file_changes=result.file_changes,
            )
        except Exception as e:
            return ExecuteResponse(
                success=False, session_id=session.session_id,
                agent_name=name, error=str(e),
            )

    if request.parallel:
        tasks = [asyncio.create_task(_run_one(n)) for n in request.agent_names]
        results = list(await asyncio.gather(*tasks))
    else:
        for name in request.agent_names:
            results.append(await _run_one(name))

    total_ms = int((time.time() - start) * 1000)
    ok = sum(1 for r in results if r.success)

    return BatchResult(
        total=len(results), successful=ok, failed=len(results) - ok,
        results=results, total_duration_ms=total_ms,
    )


# ── 상태 조회 ─────────────────────────────────────────────────────

@router.get("/sessions")
async def list_agent_sessions():
    """모든 에이전트 세션 목록"""
    manager = get_agent_session_manager()
    return [s.to_dict() for s in manager.list_session_infos()]


@router.get("/sessions/{agent_name}")
async def get_agent_session_info(agent_name: str):
    """특정 에이전트 세션 정보"""
    manager = get_agent_session_manager()
    session = manager.get_session_by_name(agent_name)
    if not session:
        raise HTTPException(status_code=404, detail=f"세션 없음: {agent_name}")
    return session.get_session_info().to_dict()


@router.get("/sessions/{agent_name}/executing")
async def check_agent_executing(agent_name: str):
    """에이전트 실행 중 여부"""
    manager = get_agent_session_manager()
    session = manager.get_session_by_name(agent_name)
    if not session:
        return {"executing": False, "agent_name": agent_name}
    return {
        "executing": is_executing(session.session_id),
        "agent_name": agent_name,
        "session_id": session.session_id,
    }


# ── 로그 조회 ─────────────────────────────────────────────────────

@router.get("/sessions/{agent_name}/logs")
async def get_agent_logs(
    agent_name: str,
    limit: int = Query(100, ge=1, le=1000),
    level: Optional[str] = Query(None, description="TOOL,TOOL_RES,COMMAND,RESPONSE 등"),
):
    """에이전트 세션 로그 조회"""
    manager = get_agent_session_manager()
    session = manager.get_session_by_name(agent_name)
    if not session:
        raise HTTPException(status_code=404, detail=f"세션 없음: {agent_name}")

    session_logger = get_session_logger(session.session_id, create_if_missing=False)
    if not session_logger:
        return {"entries": [], "total": 0}

    from jinxus.cli_engine.models import LogLevel
    level_filter = None
    if level:
        try:
            levels = {LogLevel(lv.strip().upper()) for lv in level.split(",")}
            level_filter = levels if len(levels) > 1 else levels.pop()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid log level: {e}")

    entries = session_logger.get_logs(limit=limit, level=level_filter, newest_first=True)
    return {"entries": entries, "total": len(entries)}


# ── Helper ────────────────────────────────────────────────────────

def _sse_event(event_type: str, data) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"
