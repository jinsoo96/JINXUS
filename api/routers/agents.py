"""Agents API - 에이전트 상태 조회"""
from fastapi import APIRouter, HTTPException

from api.models import AgentStatus, AgentListResponse
from core import get_orchestrator
from memory import get_jinx_memory

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents():
    """에이전트 목록 및 성능 조회"""
    orchestrator = get_orchestrator()
    memory = get_jinx_memory()

    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    agents = []
    for agent_name in orchestrator.get_agents():
        try:
            status = await orchestrator.get_agent_status(agent_name)
            agents.append(AgentStatus(
                name=status.get("name", agent_name),
                prompt_version=status.get("prompt_version", "v1.0"),
                total_tasks=status.get("total_tasks", 0),
                success_rate=status.get("success_rate", 0.0),
                avg_score=status.get("avg_score", 0.0),
                avg_duration_ms=status.get("avg_duration_ms", 0),
                recent_failures=status.get("recent_failures", 0),
            ))
        except Exception:
            agents.append(AgentStatus(
                name=agent_name,
                prompt_version="v1.0",
                total_tasks=0,
                success_rate=0.0,
                avg_score=0.0,
                avg_duration_ms=0,
                recent_failures=0,
            ))

    return AgentListResponse(agents=agents)


@router.get("/{agent_name}/status", response_model=AgentStatus)
async def get_agent_status(agent_name: str):
    """특정 에이전트 상태 조회"""
    orchestrator = get_orchestrator()

    if not orchestrator.is_initialized:
        await orchestrator.initialize()

    if agent_name not in orchestrator.get_agents():
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}")

    status = await orchestrator.get_agent_status(agent_name)

    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])

    return AgentStatus(
        name=status.get("name", agent_name),
        prompt_version=status.get("prompt_version", "v1.0"),
        total_tasks=status.get("total_tasks", 0),
        success_rate=status.get("success_rate", 0.0),
        avg_score=status.get("avg_score", 0.0),
        avg_duration_ms=status.get("avg_duration_ms", 0),
        recent_failures=status.get("recent_failures", 0),
    )


@router.get("/{agent_name}/history")
async def get_agent_history(agent_name: str, limit: int = 20):
    """에이전트 작업 이력 조회"""
    memory = get_jinx_memory()

    # 장기기억에서 해당 에이전트 작업 검색
    # TODO: 더 나은 구현 필요
    results = memory.search_long_term(agent_name, "", limit=limit)

    return {
        "agent_name": agent_name,
        "history": results,
        "total": len(results),
    }
