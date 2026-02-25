"""Status API - 시스템 상태 조회"""
from fastapi import APIRouter, Query

from api.models import SystemStatusResponse
from core import get_orchestrator
from memory import get_jinx_memory

router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=SystemStatusResponse)
async def get_system_status():
    """전체 시스템 상태"""
    orchestrator = get_orchestrator()

    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    status = await orchestrator.get_system_status()

    return SystemStatusResponse(
        status=status.get("status", "unknown"),
        uptime_seconds=status.get("uptime_seconds", 0),
        redis_connected=status.get("redis_connected", False),
        qdrant_connected=status.get("qdrant_connected", False),
        total_tasks_processed=status.get("total_tasks_processed", 0),
        active_agents=status.get("active_agents", []),
    )


@router.get("/performance")
async def get_performance_report(days: int = Query(7, ge=1, le=30)):
    """에이전트별 성능 리포트"""
    memory = get_jinx_memory()
    orchestrator = get_orchestrator()

    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    report = {}
    for agent_name in orchestrator.get_agents():
        performance = await memory.get_agent_performance(agent_name, days=days)
        report[agent_name] = performance

    # 전체 통계
    total_tasks = sum(p.get("total_tasks", 0) for p in report.values())
    avg_success_rate = (
        sum(p.get("success_rate", 0) for p in report.values()) / len(report)
        if report else 0
    )

    return {
        "period_days": days,
        "summary": {
            "total_tasks": total_tasks,
            "avg_success_rate": avg_success_rate,
            "agents_count": len(report),
        },
        "agents": report,
    }


@router.get("/health")
async def health_check():
    """헬스 체크 (간단)"""
    return {"status": "ok"}
