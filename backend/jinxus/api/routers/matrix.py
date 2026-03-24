"""Matrix Application Service 수신 라우터

Synapse → JINXUS 방향 이벤트 수신.
진수가 Matrix 룸에 메시지 보내면 → AgentReactor 트리거.

Matrix AS 스펙:
  PUT {url}/_matrix/app/v1/transactions/{txnId}
  GET {url}/_matrix/app/v1/users/{userId}
  GET {url}/_matrix/app/v1/rooms/{roomAlias}
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from jinxus.config import get_settings

logger = logging.getLogger(__name__)
# prefix 없음 — Synapse가 /_matrix/app/v1/* 경로를 그대로 전송
router = APIRouter(tags=["matrix"])

HS_TOKEN = "49e01b31d44c265af3d4dfb3a1d230dea8774ba69ee47c4a0e23d1b5e7e488bb"

# Matrix 룸 ID → JINXUS 채널 이름 역방향 매핑 (런타임에 채워짐)
_room_to_channel: dict[str, str] = {}


def register_room_channel(room_id: str, channel: str) -> None:
    """룸 생성 시 등록"""
    _room_to_channel[room_id] = channel


def _check_auth(authorization: Optional[str]) -> None:
    if authorization != f"Bearer {HS_TOKEN}":
        raise HTTPException(status_code=403, detail="M_FORBIDDEN")


@router.put("/_matrix/app/v1/transactions/{txn_id}")
async def receive_transaction(
    txn_id: str,
    request: Request,
    authorization: str = Header(None),
):
    """Synapse가 이벤트 push하는 엔드포인트"""
    _check_auth(authorization)

    body = await request.json()
    for event in body.get("events", []):
        asyncio.create_task(_dispatch(event))

    return JSONResponse({})


@router.get("/_matrix/app/v1/users/{user_id:path}")
async def query_user(
    user_id: str,
    authorization: str = Header(None),
):
    """Synapse가 가상 유저 존재 확인 요청"""
    _check_auth(authorization)
    localpart = user_id.split(":")[0].lstrip("@")
    if localpart.startswith(("jx_", "js_", "jinxus_bot")):
        return JSONResponse({})
    raise HTTPException(status_code=404, detail="M_NOT_FOUND")


@router.get("/_matrix/app/v1/rooms/{room_alias:path}")
async def query_room(
    room_alias: str,
    authorization: str = Header(None),
):
    """Synapse가 룸 별칭 존재 확인 요청"""
    _check_auth(authorization)
    localpart = room_alias.split(":")[0].lstrip("#")
    if localpart.startswith("jinxus-"):
        return JSONResponse({})
    raise HTTPException(status_code=404, detail="M_NOT_FOUND")


async def _dispatch(event: dict) -> None:
    """이벤트 디스패치 → AgentReactor"""
    if event.get("type") != "m.room.message":
        return

    sender: str = event.get("sender", "")
    room_id: str = event.get("room_id", "")
    content: dict = event.get("content", {})

    # 에이전트 메시지 무시 (jx_, js_, jinxus_bot)
    if any(sender.startswith(f"@{p}") for p in ("jx_", "js_", "jinxus_bot")):
        return
    if content.get("msgtype") != "m.text":
        return

    text: str = content.get("body", "").strip()
    if not text:
        return

    # 룸 → 채널 매핑 (없으면 general)
    channel = _room_to_channel.get(room_id, "general")

    logger.info(f"[Matrix] 메시지 수신: {sender} → #{channel}: {text[:60]}")

    try:
        from jinxus.hr.agent_reactor import get_agent_reactor
        reactor = get_agent_reactor()
        await reactor.react(text, channel)
    except Exception as e:
        logger.error(f"[Matrix] react 실패: {e}")
