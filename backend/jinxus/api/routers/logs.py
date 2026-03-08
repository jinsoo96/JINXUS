"""로그 API - 작업 이력 조회 및 관리"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from jinxus.memory import get_jinx_memory

router = APIRouter(prefix="/logs", tags=["logs"])


class TaskLog(BaseModel):
    """작업 로그"""
    id: str
    agent_name: str
    instruction: str
    success: bool
    success_score: float
    duration_ms: int
    failure_reason: Optional[str] = None
    created_at: str


class LogsResponse(BaseModel):
    """로그 목록 응답"""
    logs: list[TaskLog]
    total: int


@router.get("", response_model=LogsResponse)
async def get_logs(
    agent_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """작업 로그 조회

    Args:
        agent_name: 특정 에이전트 필터 (선택)
        limit: 조회 개수 (기본 50)
        offset: 시작 위치
    """
    memory = get_jinx_memory()

    # 메타 저장소에서 로그 조회
    logs = await memory._meta.get_recent_logs(
        agent_name=agent_name,
        limit=limit,
        offset=offset,
    )

    total = await memory._meta.get_logs_count(agent_name=agent_name)

    return LogsResponse(
        logs=[TaskLog(**log) for log in logs],
        total=total,
    )


@router.get("/summary")
async def get_logs_summary():
    """로그 요약 통계"""
    memory = get_jinx_memory()

    # 전체 통계
    total = await memory.get_total_tasks_count()

    # 에이전트별 통계
    from jinxus.agents import AGENT_REGISTRY
    agent_stats = {}
    for agent_name in AGENT_REGISTRY.keys():
        perf = await memory.get_agent_performance(agent_name, days=7)
        agent_stats[agent_name] = {
            "total_tasks": perf.get("total_tasks", 0),
            "success_rate": perf.get("success_rate", 0),
            "avg_duration_ms": perf.get("avg_duration_ms", 0),
        }

    return {
        "total_tasks": total,
        "agent_stats": agent_stats,
    }


# ===== 로그 삭제 API =====

class DeleteLogsRequest(BaseModel):
    """로그 일괄 삭제 요청"""
    log_ids: list[str]


class DeleteOldLogsRequest(BaseModel):
    """오래된 로그 삭제 요청"""
    days: int = 7
    keep_failures: bool = True  # 실패 로그는 유지 (학습용)


@router.delete("/{log_id}")
async def delete_log(log_id: str):
    """로그 단일 삭제"""
    memory = get_jinx_memory()
    success = await memory._meta.delete_log(log_id)

    if not success:
        raise HTTPException(status_code=404, detail="로그를 찾을 수 없습니다")

    return {"success": True, "deleted_id": log_id}


@router.delete("")
async def delete_logs_bulk(request: DeleteLogsRequest):
    """로그 일괄 삭제"""
    memory = get_jinx_memory()
    deleted_count = await memory._meta.delete_logs_bulk(request.log_ids)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "requested_count": len(request.log_ids),
    }


@router.delete("/agent/{agent_name}")
async def delete_logs_by_agent(agent_name: str):
    """에이전트별 로그 전체 삭제"""
    memory = get_jinx_memory()
    deleted_count = await memory._meta.delete_logs_by_agent(agent_name)

    return {
        "success": True,
        "agent_name": agent_name,
        "deleted_count": deleted_count,
    }


@router.post("/cleanup")
async def cleanup_old_logs(request: DeleteOldLogsRequest):
    """오래된 로그 정리 (학습 데이터 보존)

    - days: N일 이전 로그 삭제 (기본 7일)
    - keep_failures: True면 실패 로그는 보존 (JinxLoop 학습용)
    """
    memory = get_jinx_memory()
    deleted_count = await memory._meta.delete_old_logs(
        days=request.days,
        keep_failures=request.keep_failures,
    )

    return {
        "success": True,
        "deleted_count": deleted_count,
        "days_threshold": request.days,
        "kept_failures": request.keep_failures,
    }
