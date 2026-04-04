"""Whiteboard API v1.0.0 — 공유 화이트보드 CRUD + 에이전트 발견 → 자동 미션

엔드포인트:
- GET    /whiteboard              → 전체 항목 조회
- GET    /whiteboard/guidelines   → 활성 지침사항만
- GET    /whiteboard/new-memos    → NEW 상태 메모만 (프론트 폴링용)
- POST   /whiteboard              → 항목 추가
- PUT    /whiteboard/{id}         → 항목 수정
- DELETE /whiteboard/{id}         → 항목 삭제
- POST   /whiteboard/{id}/discover → 에이전트 발견 → CORE에 보고 → 미션 자동 생성
"""
import logging
import uuid
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from jinxus.core.whiteboard import (
    WhiteboardItem, ItemType, ItemStatus,
    get_whiteboard_store,
)

router = APIRouter(prefix="/whiteboard", tags=["whiteboard"])
logger = logging.getLogger(__name__)


# ── Request Models ──

class CreateItemRequest(BaseModel):
    type: str = Field(..., description="guideline 또는 memo")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    tags: List[str] = Field(default_factory=list)
    source: str = Field(default="manual", description="manual / recording / file")


class UpdateItemRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None


class DiscoverRequest(BaseModel):
    agent_code: str = Field(..., description="발견한 에이전트 코드")


# ── Endpoints ──

@router.get("")
async def list_items():
    """전체 화이트보드 항목 조회"""
    store = get_whiteboard_store()
    items = await store.list_all()
    return {"items": [i.to_dict() for i in items], "total": len(items)}


@router.get("/guidelines")
async def list_guidelines():
    """활성 지침사항 목록 (에이전트 컨텍스트 주입용)"""
    store = get_whiteboard_store()
    items = await store.get_active_guidelines()
    return {"guidelines": [i.to_dict() for i in items], "total": len(items)}


@router.get("/new-memos")
async def list_new_memos():
    """NEW 상태 메모 목록 (프론트엔드 에이전트 발견 대상)"""
    store = get_whiteboard_store()
    items = await store.list_new_memos()
    return {"memos": [i.to_dict() for i in items], "total": len(items)}


@router.get("/{item_id}")
async def get_item(item_id: str):
    """항목 상세 조회"""
    store = get_whiteboard_store()
    item = await store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")
    return item.to_dict()


@router.post("")
async def create_item(request: CreateItemRequest):
    """화이트보드에 항목 추가"""
    try:
        item_type = ItemType(request.type)
    except ValueError:
        raise HTTPException(status_code=400, detail="type은 'guideline' 또는 'memo'만 가능합니다")

    store = get_whiteboard_store()
    item = WhiteboardItem(
        id=str(uuid.uuid4()),
        type=item_type,
        title=request.title,
        content=request.content,
        tags=request.tags,
        source=request.source,
    )
    await store.save(item)
    logger.info(f"[Whiteboard] 항목 추가: [{item_type.value}] {request.title}")
    return {"success": True, "item": item.to_dict()}


@router.put("/{item_id}")
async def update_item(item_id: str, request: UpdateItemRequest):
    """항목 수정"""
    store = get_whiteboard_store()
    item = await store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")

    if request.title is not None:
        item.title = request.title
    if request.content is not None:
        item.content = request.content
    if request.tags is not None:
        item.tags = request.tags
    if request.status is not None:
        try:
            item.status = ItemStatus(request.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 상태: {request.status}")

    await store.save(item)
    return {"success": True, "item": item.to_dict()}


@router.delete("/{item_id}")
async def delete_item(item_id: str):
    """항목 삭제"""
    store = get_whiteboard_store()
    await store.delete(item_id)
    return {"success": True}


@router.post("/{item_id}/discover")
async def discover_item(item_id: str, request: DiscoverRequest):
    """에이전트가 화이트보드 메모를 발견 → CORE에 보고 → 자동 미션 생성

    1. 항목을 SEEN 상태로 변경
    2. 활성 지침사항을 수집
    3. 미션을 생성하고 백그라운드 실행 시작
    4. 항목을 CLAIMED 상태로 변경
    """
    store = get_whiteboard_store()
    item = await store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다")
    if item.status != ItemStatus.NEW:
        return {"success": False, "reason": "이미 처리된 항목입니다", "status": item.status.value}

    # 1. 발견 표시
    item = await store.mark_discovered(item_id, request.agent_code)

    # 2. 활성 지침사항 수집
    guidelines = await store.get_active_guidelines()
    guidelines_text = ""
    if guidelines:
        guidelines_text = "\n\n## 업무 지침사항 (반드시 참고)\n" + "\n".join(
            f"- **{g.title}**: {g.content}" for g in guidelines
        )

    # 3. 미션 생성
    from jinxus.core.mission_router import get_mission_router
    from jinxus.core.mission_executor import get_mission_executor
    from jinxus.core.agent_messenger import get_agent_messenger

    mission_prompt = (
        f"[화이트보드 발견] {request.agent_code}가 화이트보드에서 새 메모를 발견했습니다.\n\n"
        f"## 메모 내용\n"
        f"제목: {item.title}\n"
        f"내용: {item.content}\n"
        f"태그: {', '.join(item.tags) if item.tags else '없음'}\n"
        f"출처: {item.source}"
        f"{guidelines_text}\n\n"
        f"위 메모 내용을 분석하고, 적절한 작업을 수행해 주세요. "
        f"지침사항이 있으면 반드시 준수하세요."
    )

    mission_router = get_mission_router()
    mission = await mission_router.create_mission(mission_prompt, session_id=None)

    # 4. 미션 실행 시작
    executor = get_mission_executor()
    executor.start_mission(mission)

    # 5. 항목에 미션 연결
    await store.mark_claimed(item_id, mission.id)

    logger.info(
        f"[Whiteboard] 자동 미션 생성: '{item.title}' → 미션 {mission.id} "
        f"(발견: {request.agent_code}, 타입: {mission.type.value})"
    )

    # 6. 에이전트 말풍선 이벤트 (프론트엔드 표시용)
    messenger = get_agent_messenger()
    await messenger._emit("global", {
        "event": "whiteboard_discovery",
        "data": {
            "agent": request.agent_code,
            "item_id": item_id,
            "item_title": item.title,
            "mission_id": mission.id,
            "mission_type": mission.type.value,
        },
    })

    return {
        "success": True,
        "item": item.to_dict(),
        "mission_id": mission.id,
        "mission_type": mission.type.value,
        "mission_title": mission.title,
    }
