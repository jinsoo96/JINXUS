"""Chat API - SSE 스트리밍 채팅 + 히스토리 관리"""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from typing import Optional

from jinxus.api.models import ChatRequest
from jinxus.core import get_orchestrator
from jinxus.memory import get_jinx_memory

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(request: ChatRequest):
    """채팅 요청 처리 (SSE 스트리밍)

    진수 → JINXUS_CORE → 에이전트들 → 응답

    SSE 이벤트:
    - start: 작업 시작
    - manager_thinking: JINXUS_CORE 분석 중
    - agent_started: 에이전트 실행 시작
    - agent_done: 에이전트 실행 완료
    - message: 응답 청크
    - done: 작업 완료
    """
    orchestrator = get_orchestrator()

    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    async def event_generator():
        try:
            async for event in orchestrator.run_task_stream(
                request.message, request.session_id
            ):
                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/sync")
async def chat_sync(request: ChatRequest):
    """동기 채팅 요청 (SSE 없이)

    Returns:
        전체 응답
    """
    orchestrator = get_orchestrator()

    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    try:
        result = await orchestrator.run_task(request.message, request.session_id)
        return {
            "task_id": result["task_id"],
            "session_id": result["session_id"],
            "response": result["response"],
            "agents_used": result["agents_used"],
            "success": result["success"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    """모든 채팅 세션 목록 조회

    Returns:
        세션 목록 (웹, 텔레그램, 스케줄 포함)
    """
    memory = get_jinx_memory()
    sessions = await memory.list_sessions()

    return {
        "sessions": sessions,
        "total": len(sessions),
    }


@router.get("/history/{session_id}")
async def get_session_history(session_id: str):
    """특정 세션의 채팅 히스토리 조회

    Args:
        session_id: 세션 ID

    Returns:
        메시지 목록
    """
    memory = get_jinx_memory()
    messages = await memory.get_full_session_history(session_id)

    return {
        "session_id": session_id,
        "messages": messages,
        "total": len(messages),
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """세션 삭제

    Args:
        session_id: 삭제할 세션 ID
    """
    memory = get_jinx_memory()
    await memory.clear_session(session_id)

    return {
        "success": True,
        "message": f"세션 '{session_id}' 삭제 완료",
    }
