"""Chat API - SSE 스트리밍 채팅"""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse

from api.models import ChatRequest
from core import get_orchestrator

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
