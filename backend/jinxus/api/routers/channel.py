"""Company Channel API — 에이전트 팀 채팅 채널

Endpoints:
- GET  /channel/history/{channel}    채널 히스토리
- GET  /channel/history              전체 채널 히스토리
- GET  /channel/stream               SSE 실시간 스트림 (전체 채널)
- POST /channel/message              진수가 채널에 메시지 게시
- POST /channel/approve              승인/수정/취소
- GET  /channel/approvals/pending    대기 중인 승인 목록
"""
import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from jinxus.hr.channel import get_company_channel, ChannelName
from jinxus.core.approval_gate import get_approval_gate, ApprovalStatus
from jinxus.hr.agent_reactor import get_agent_reactor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/channel", tags=["channel"])


class PostMessageRequest(BaseModel):
    content: str
    channel: Optional[str] = None
    message_type: str = "chat"


class ApprovalRequest(BaseModel):
    request_id: str
    status: str  # "approved" | "modified" | "cancelled"
    feedback: Optional[str] = ""


@router.get("/history/{channel_name}")
async def get_channel_history(channel_name: str, limit: int = 50):
    """채널 히스토리 조회"""
    valid_channels = {ch.value for ch in ChannelName}
    if channel_name not in valid_channels:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 채널: {channel_name}")
    ch = get_company_channel()
    messages = await ch.get_history(channel_name, limit=limit)
    return {"channel": channel_name, "messages": messages}


@router.delete("/history/{channel_name}")
async def clear_channel_history(channel_name: str):
    """채널 히스토리 전체 삭제 (Redis)"""
    valid_channels = {ch.value for ch in ChannelName}
    if channel_name not in valid_channels:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 채널: {channel_name}")
    ch = get_company_channel()
    deleted = await ch.clear_history(channel_name)
    return {"success": True, "channel": channel_name, "deleted": deleted}


@router.get("/history")
async def get_all_history(limit: int = 50):
    """전체 채널 히스토리"""
    ch = get_company_channel()
    history = await ch.get_all_history(limit_per_channel=limit)
    return {"channels": history}


@router.get("/stream")
async def stream_channel(
    request: Request,
    channels: Optional[str] = None,
    cleared_at: Optional[str] = None,
):
    """SSE 실시간 채널 스트림

    channels: 콤마 구분 채널 목록 (없으면 전체)
    cleared_at: 채널별 삭제 시점 JSON (예: {"general":"2026-03-28T00:00:00Z"})
               이 시점 이전 메시지는 전송하지 않음
    """
    ch = get_company_channel()
    target_channels = channels.split(",") if channels else None

    # cleared_at 파싱 (채널별 삭제 시점)
    cleared_map: dict = {}
    if cleared_at:
        try:
            cleared_map = json.loads(cleared_at)
        except (json.JSONDecodeError, TypeError):
            pass

    # 구독 전 히스토리 먼저 전송 (최근 20개)
    history_data = []
    if target_channels:
        for c in target_channels:
            msgs = await ch.get_history(c, limit=20)
            history_data.extend(msgs)
    else:
        all_hist = await ch.get_all_history(limit_per_channel=20)
        for msgs in all_hist.values():
            history_data.extend(msgs)

    # cleared_at 이전 메시지 필터링
    if cleared_map:
        history_data = [
            m for m in history_data
            if not (
                cleared_map.get(m.get("channel", ""))
                and m.get("created_at", "") <= cleared_map[m["channel"]]
            )
        ]

    # 시간순 정렬
    history_data.sort(key=lambda m: m.get("created_at", ""))

    q = await ch.subscribe(target_channels)

    async def event_generator():
        try:
            # 히스토리 먼저 전송
            for msg in history_data:
                yield f"data: {json.dumps({'type': 'history', 'message': msg}, ensure_ascii=False)}\n\n"

            # 실시간 스트림
            while not await request.is_disconnected():
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps({'type': 'message', 'message': msg}, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"type\": \"ping\"}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await ch.unsubscribe(q, target_channels)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/message")
async def post_message(request: PostMessageRequest):
    """진수가 채널에 메시지 게시 + 에이전트 자동 반응 트리거"""
    ch = get_company_channel()
    msg = await ch.post(
        from_name="진수",
        content=request.content,
        channel=request.channel,
        message_type=request.message_type,
    )
    # 에이전트들이 자동으로 반응 (fire-and-forget)
    if request.message_type == "chat":
        reactor = get_agent_reactor()
        asyncio.create_task(reactor.react(request.content, msg.channel))
    return {"success": True, "message": msg.to_dict()}


@router.post("/approve")
async def approve_task(request: ApprovalRequest):
    """진수 승인/수정/취소 처리"""
    try:
        status = ApprovalStatus(request.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 status: {request.status}")

    gate = get_approval_gate()
    success = await gate.respond(
        request_id=request.request_id,
        status=status,
        feedback=request.feedback or "",
    )
    if not success:
        raise HTTPException(status_code=404, detail=f"승인 요청을 찾을 수 없음: {request.request_id}")

    return {"success": True, "request_id": request.request_id, "status": request.status}


@router.get("/approvals/pending")
async def get_pending_approvals():
    """대기 중인 승인 요청 목록"""
    gate = get_approval_gate()
    pending = await gate.get_pending()
    return {"pending": pending, "count": len(pending)}
