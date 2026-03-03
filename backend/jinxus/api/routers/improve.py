"""Improve API - 자가 강화 관리"""
from fastapi import APIRouter, HTTPException

from jinxus.api.models import (
    ImproveRequest,
    RollbackRequest,
    ImproveHistoryResponse,
    ImproveHistoryItem,
)
from jinxus.core import get_jinx_loop
from jinxus.memory import get_jinx_memory

router = APIRouter(prefix="/improve", tags=["improve"])


@router.post("")
async def trigger_improve(request: ImproveRequest):
    """수동 자가 강화 트리거"""
    jinx_loop = get_jinx_loop()

    try:
        if request.agent_name:
            # 특정 에이전트만
            result = await jinx_loop.improve_agent(
                agent_name=request.agent_name,
                trigger_type="manual",
                trigger_source="user",
            )
            return {
                "success": True,
                "improvements": [result],
            }
        else:
            # 전체 에이전트 점검
            results = await jinx_loop.run_scheduled_check()
            return {
                "success": True,
                "improvements": results,
                "message": f"{len(results)} agents improved",
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=ImproveHistoryResponse)
async def get_improve_history(agent_name: str = None, limit: int = 20):
    """개선 이력 조회"""
    memory = get_jinx_memory()

    try:
        history = await memory.get_improve_history(agent_name, limit)

        return ImproveHistoryResponse(
            history=[
                ImproveHistoryItem(
                    id=h.get("id", ""),
                    target_agent=h.get("target_agent", ""),
                    trigger_type=h.get("trigger_type", ""),
                    old_version=h.get("old_version", ""),
                    new_version=h.get("new_version", ""),
                    improvement_applied=h.get("improvement_applied", ""),
                    score_before=h.get("score_before"),
                    score_after=h.get("score_after"),
                    created_at=h.get("created_at", ""),
                )
                for h in history
            ]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rollback")
async def rollback_prompt(request: RollbackRequest):
    """프롬프트 버전 롤백"""
    memory = get_jinx_memory()

    try:
        success = await memory.rollback_prompt(request.agent_name, request.version)

        if success:
            return {
                "success": True,
                "agent_name": request.agent_name,
                "rolled_back_to": request.version,
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Version {request.version} not found for {request.agent_name}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/prompts/{agent_name}")
async def get_prompt_versions(agent_name: str):
    """에이전트 프롬프트 버전 이력"""
    memory = get_jinx_memory()

    try:
        versions = await memory.get_prompt_history(agent_name)
        active = await memory.get_active_prompt(agent_name)

        return {
            "agent_name": agent_name,
            "active_version": active.get("version") if active else "v1.0",
            "versions": versions,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
