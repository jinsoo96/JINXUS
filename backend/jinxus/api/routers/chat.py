"""Chat API - SSE 스트리밍 채팅 + 히스토리 관리"""
import asyncio
import json
import logging
from typing import Dict
from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from jinxus.api.models import ChatRequest
from jinxus.core import get_orchestrator
from jinxus.memory import get_jinx_memory

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)

# SSE 스트리밍 취소용 이벤트 추적
_cancel_events: Dict[str, asyncio.Event] = {}


def get_cancel_event(task_id: str) -> asyncio.Event:
    """취소 이벤트 가져오기/생성"""
    if task_id not in _cancel_events:
        _cancel_events[task_id] = asyncio.Event()
    return _cancel_events[task_id]


def cleanup_cancel_event(task_id: str):
    """취소 이벤트 정리"""
    if task_id in _cancel_events:
        del _cancel_events[task_id]


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
    - cancelled: 사용자 취소
    """
    orchestrator = get_orchestrator()

    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    async def event_generator():
        task_id = None
        cancel_event = None

        try:
            async for event in orchestrator.run_task_stream(
                request.message, request.session_id
            ):
                # task_id 추출하여 취소 이벤트 연결
                if event["event"] == "start" and "task_id" in event["data"]:
                    task_id = event["data"]["task_id"]
                    cancel_event = get_cancel_event(task_id)
                    logger.info(f"SSE 스트림 시작: {task_id}")

                # 취소 확인
                if cancel_event and cancel_event.is_set():
                    logger.info(f"SSE 스트림 취소됨: {task_id}")
                    yield {
                        "event": "cancelled",
                        "data": json.dumps({"task_id": task_id, "message": "사용자가 작업을 취소했습니다"}, ensure_ascii=False),
                    }
                    break

                yield {
                    "event": event["event"],
                    "data": json.dumps(event["data"], ensure_ascii=False),
                }

        except asyncio.CancelledError:
            logger.info(f"SSE 스트림 CancelledError: {task_id}")
            yield {
                "event": "cancelled",
                "data": json.dumps({"task_id": task_id, "message": "작업이 취소되었습니다"}, ensure_ascii=False),
            }
        except Exception as e:
            logger.error(f"SSE 스트림 에러: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False),
            }
        finally:
            if task_id:
                cleanup_cancel_event(task_id)

    return EventSourceResponse(event_generator())


@router.post("/cancel/{task_id}")
async def cancel_stream(task_id: str):
    """SSE 스트리밍 취소

    Args:
        task_id: 취소할 작업 ID

    Returns:
        취소 결과
    """
    if task_id in _cancel_events:
        _cancel_events[task_id].set()
        logger.info(f"SSE 스트림 취소 요청: {task_id}")
        return {
            "success": True,
            "task_id": task_id,
            "message": "취소 신호 전송됨",
        }
    else:
        # 이벤트가 없으면 이미 완료되었거나 존재하지 않음
        return {
            "success": False,
            "task_id": task_id,
            "message": "해당 작업을 찾을 수 없음 (이미 완료되었거나 존재하지 않음)",
        }


@router.get("/active")
async def list_active_streams():
    """현재 활성 SSE 스트림 목록

    Returns:
        활성 스트림 task_id 목록
    """
    return {
        "active_streams": list(_cancel_events.keys()),
        "count": len(_cancel_events),
    }


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
