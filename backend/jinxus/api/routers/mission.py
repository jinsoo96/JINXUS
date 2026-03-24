"""Mission API v1.0.0 — 미션 CRUD + SSE 스트리밍

모든 사용자 입력은 미션으로 변환되어 처리된다.
기존 /chat 엔드포인트를 대체하는 새로운 진입점.

SSE 이벤트:
- mission_created: 미션 생성됨
- mission_status: 상태 변경 (briefing/in_progress/review)
- mission_huddle: 회의 소집
- mission_briefing_message: 브리핑 중 발언
- mission_agent_activity: 에이전트 활동 (started/working/done)
- mission_message: 응답 청크
- mission_thinking: CORE 분석 중
- mission_complete: 미션 완료
- mission_failed: 미션 실패
- mission_cancelled: 미션 취소
- agent_dm: 에이전트 간 DM
- agent_report: 에이전트 보고
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from jinxus.core.mission import MissionStatus, get_mission_store
from jinxus.core.mission_router import get_mission_router
from jinxus.core.mission_executor import get_mission_executor
from jinxus.core.agent_messenger import get_agent_messenger  # events 엔드포인트용

router = APIRouter(prefix="/mission", tags=["mission"])
logger = logging.getLogger(__name__)

# 동시 미션 실행 제한
MAX_CONCURRENT_MISSIONS = 10
_mission_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _mission_semaphore
    if _mission_semaphore is None:
        _mission_semaphore = asyncio.Semaphore(MAX_CONCURRENT_MISSIONS)
    return _mission_semaphore


class MissionRequest(BaseModel):
    """미션 요청"""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None


@router.post("")
async def create_and_execute_mission(request: MissionRequest):
    """미션 생성 + 실행 (SSE 스트리밍)

    사용자 입력 → 미션 변환 → 실행 → 결과 스트리밍
    """
    sem = _get_semaphore()
    if sem.locked():
        raise HTTPException(
            status_code=503,
            detail=f"동시 미션 수({MAX_CONCURRENT_MISSIONS}) 초과",
        )

    mission_router = get_mission_router()
    executor = get_mission_executor()

    # 미션 생성
    mission = await mission_router.create_mission(
        request.message, request.session_id
    )

    # 필터링할 이벤트 (Python 로그 등 프론트에 불필요한 것)
    _SKIP_EVENTS = {"log", "error"}

    async def event_generator():
        async with _get_semaphore():
            got_done = False

            try:
                async for event in executor.execute_stream(mission):
                    evt_name = event["event"]
                    # Python 로그 이벤트 필터링
                    if evt_name in _SKIP_EVENTS:
                        continue
                    yield {
                        "event": evt_name,
                        "data": json.dumps(event["data"], ensure_ascii=False),
                    }
                    if evt_name in ("mission_complete", "mission_failed", "mission_cancelled"):
                        got_done = True

            except asyncio.CancelledError:
                yield {
                    "event": "mission_cancelled",
                    "data": json.dumps({"id": mission.id, "message": "취소됨"}, ensure_ascii=False),
                }
                got_done = True
            except Exception as e:
                logger.error(f"미션 SSE 에러 {mission.id}: {e}", exc_info=True)
                yield {
                    "event": "mission_failed",
                    "data": json.dumps({"id": mission.id, "error": str(e)[:300]}, ensure_ascii=False),
                }
            finally:
                if not got_done:
                    yield {
                        "event": "mission_complete",
                        "data": json.dumps({"id": mission.id, "title": mission.title}, ensure_ascii=False),
                    }

    return EventSourceResponse(event_generator())


@router.get("/list")
async def list_missions(status: Optional[str] = None, limit: int = 20):
    """미션 목록 조회"""
    store = get_mission_store()

    if status:
        try:
            ms = MissionStatus(status)
            missions = await store.list_by_status(ms, limit=limit)
        except ValueError:
            raise HTTPException(400, f"잘못된 상태: {status}")
    else:
        missions = await store.list_recent(limit=limit)

    return {
        "missions": [m.to_dict() for m in missions],
        "total": len(missions),
    }


@router.get("/{mission_id}")
async def get_mission(mission_id: str):
    """미션 상세 조회"""
    store = get_mission_store()
    mission = await store.get(mission_id)
    if not mission:
        raise HTTPException(404, "미션을 찾을 수 없습니다")
    return mission.to_dict()


@router.post("/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    """미션 취소"""
    executor = get_mission_executor()
    success = await executor.cancel_mission(mission_id)
    if not success:
        raise HTTPException(400, "미션을 취소할 수 없습니다 (이미 완료/취소됨)")
    return {"success": True, "mission_id": mission_id}


@router.delete("/{mission_id}")
async def delete_mission(mission_id: str):
    """미션 삭제"""
    store = get_mission_store()
    mission = await store.get(mission_id)
    if not mission:
        raise HTTPException(404, "미션을 찾을 수 없습니다")
    # 진행 중이면 먼저 취소
    if mission.status.value in ("briefing", "in_progress", "review"):
        executor = get_mission_executor()
        await executor.cancel_mission(mission_id)
    await store.delete(mission_id)
    return {"success": True, "mission_id": mission_id}


@router.get("/{mission_id}/conversations")
async def get_mission_conversations(mission_id: str):
    """미션 에이전트 대화 로그 조회"""
    store = get_mission_store()
    mission = await store.get(mission_id)
    if not mission:
        raise HTTPException(404, "미션을 찾을 수 없습니다")
    return {
        "mission_id": mission_id,
        "conversations": mission.agent_conversations,
        "total": len(mission.agent_conversations),
    }


@router.get("/{mission_id}/events")
async def mission_events(mission_id: str):
    """미션 실시간 이벤트 스트리밍 (진행 중인 미션 구독)"""
    store = get_mission_store()
    mission = await store.get(mission_id)
    if not mission:
        raise HTTPException(404, "미션을 찾을 수 없습니다")

    messenger = get_agent_messenger()

    async def event_generator():
        queue = messenger.subscribe(mission_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event["data"], ensure_ascii=False),
                    }
                    # 미션 종료 이벤트면 스트림 종료
                    if event["event"] in ("mission_complete", "mission_failed", "mission_cancelled"):
                        break
                except asyncio.TimeoutError:
                    yield {"event": "keepalive", "data": "{}"}
                    # 미션 상태 확인
                    m = await store.get(mission_id)
                    if not m or m.status.value in ("complete", "failed", "cancelled"):
                        break
        finally:
            messenger.unsubscribe(mission_id, queue)

    return EventSourceResponse(event_generator())
