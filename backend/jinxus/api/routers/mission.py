"""Mission API v2.0.0 — 미션 CRUD + SSE 스트리밍

미션 실행이 백그라운드 태스크로 분리되어 SSE 연결 끊김에도 미션이 계속 진행된다.
POST /mission → 미션 생성 + 백그라운드 실행 시작 + 이벤트 구독 SSE 반환
GET /mission/{id}/events → 기존 미션 이벤트 재구독

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
from jinxus.core.agent_messenger import get_agent_messenger


def _get_executor():
    """v4 CLI executor 우선, 실패 시 오케스트레이터 fallback"""
    try:
        from jinxus.core.mission_executor_v4 import get_mission_executor_v4
        return get_mission_executor_v4()
    except Exception:
        from jinxus.core.mission_executor import get_mission_executor
        return get_mission_executor()

router = APIRouter(prefix="/mission", tags=["mission"])
logger = logging.getLogger(__name__)

# 동시 미션 실행 제한
MAX_CONCURRENT_MISSIONS = 10


class MissionRequest(BaseModel):
    """미션 요청"""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None


@router.post("")
async def create_and_execute_mission(request: MissionRequest):
    """미션 생성 + 백그라운드 실행 시작 + 이벤트 구독 SSE 반환

    미션은 백그라운드 태스크로 실행되므로 클라이언트 연결이 끊겨도 계속 진행된다.
    """
    executor = _get_executor()

    # 동시 실행 제한
    active_count = len(executor._active_missions)
    if active_count >= MAX_CONCURRENT_MISSIONS:
        raise HTTPException(
            status_code=503,
            detail=f"동시 미션 수({MAX_CONCURRENT_MISSIONS}) 초과",
        )

    mission_router = get_mission_router()
    messenger = get_agent_messenger()
    store = get_mission_store()

    # 미션 생성
    mission = await mission_router.create_mission(
        request.message, request.session_id
    )

    # 이벤트 구독 (백그라운드 태스크 시작 전에 구독해야 이벤트 놓치지 않음)
    queue = messenger.subscribe(mission.id)

    # 백그라운드 태스크로 미션 실행 시작
    executor.start_mission(mission)

    async def event_generator():
        # mission_created를 즉시 전송 (백그라운드 태스크 스케줄 대기 없이)
        yield {
            "event": "mission_created",
            "data": json.dumps(mission.to_dict(), ensure_ascii=False),
        }
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    evt_name = event.get("event", "")

                    # Python 로그 이벤트 필터링 + 이미 전송한 mission_created 스킵
                    if evt_name in ("log", "error", "mission_created"):
                        continue

                    yield {
                        "event": evt_name,
                        "data": json.dumps(event.get("data", {}), ensure_ascii=False),
                    }

                    # 미션 종료 이벤트면 스트림 종료
                    if evt_name in ("mission_complete", "mission_failed", "mission_cancelled"):
                        break

                except asyncio.TimeoutError:
                    # keepalive 전송 + 미션 상태 확인
                    yield {"event": "keepalive", "data": "{}"}
                    m = await store.get(mission.id)
                    if not m or m.status.value in ("complete", "failed", "cancelled"):
                        break
        except asyncio.CancelledError:
            # 클라이언트 연결 끊김 — 미션은 백그라운드에서 계속 실행됨
            logger.debug(f"[Mission SSE] 클라이언트 연결 끊김 (mission={mission.id}), 미션은 계속 실행")
        finally:
            messenger.unsubscribe(mission.id, queue)

    return EventSourceResponse(event_generator())


@router.post("/start")
async def start_mission(request: MissionRequest):
    """Geny 패턴: 미션 생성 + 실행 시작 → JSON 즉시 반환 (SSE는 GET /events로)"""
    executor = _get_executor()

    active_count = len(executor._active_missions)
    if active_count >= MAX_CONCURRENT_MISSIONS:
        raise HTTPException(503, f"동시 미션 수({MAX_CONCURRENT_MISSIONS}) 초과")

    mission_router = get_mission_router()
    mission = await mission_router.create_mission(
        request.message, request.session_id
    )
    executor.start_mission(mission)

    return mission.to_dict()


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
    executor = _get_executor()
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
        executor = _get_executor()
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
                    event = await asyncio.wait_for(queue.get(), timeout=15)
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
        except asyncio.CancelledError:
            logger.debug(f"[Mission SSE] 이벤트 구독 끊김 (mission={mission_id})")
        finally:
            messenger.unsubscribe(mission_id, queue)

    return EventSourceResponse(event_generator())


@router.post("/{mission_id}/approve")
async def approve_mission(mission_id: str):
    """미션 승인 (승인 게이트 통과)"""
    store = get_mission_store()
    mission = await store.get(mission_id)
    if not mission:
        raise HTTPException(404, "미션을 찾을 수 없습니다")

    # 승인 이벤트 발행 → 오케스트레이터가 감지
    messenger = get_agent_messenger()
    await messenger._emit(mission_id, {
        "event": "mission_approved",
        "data": {"id": mission_id, "message": "승인됨"},
    })
    return {"success": True, "mission_id": mission_id}
