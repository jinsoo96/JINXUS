"""Agents API - 에이전트 상태 조회"""
from fastapi import APIRouter, HTTPException

from jinxus.api.models import AgentStatus, AgentListResponse
from jinxus.core import get_orchestrator
from jinxus.memory import get_jinx_memory

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


@router.get("/{agent_name}/runtime")
async def get_agent_runtime_status(agent_name: str):
    """에이전트 실시간 상태 조회 (LangGraph 노드, 현재 도구 등)"""
    from jinxus.agents.state_tracker import get_state_tracker

    tracker = get_state_tracker()
    state = tracker.get_state(agent_name)

    if not state:
        return {
            "name": agent_name,
            "status": "unknown",
            "current_node": None,
            "current_task": None,
            "current_tools": [],
            "last_update": None,
        }

    return state.to_dict()


@router.get("/runtime/all")
async def get_all_runtime_status():
    """모든 에이전트 실시간 상태 조회"""
    from jinxus.agents.state_tracker import get_state_tracker

    tracker = get_state_tracker()
    all_states = tracker.get_all_states()

    return {
        "agents": [state.to_dict() for state in all_states.values()],
        "working_count": len(tracker.get_working_agents()),
    }


@router.get("/{agent_name}/graph")
async def get_agent_graph(agent_name: str):
    """에이전트 LangGraph 구조 반환 (시각화용)"""
    # LangGraph 노드 정의
    nodes = [
        {"id": "receive", "label": "수신", "description": "작업 수신 및 초기화"},
        {"id": "plan", "label": "계획", "description": "실행 계획 수립"},
        {"id": "execute", "label": "실행", "description": "도구 사용 및 작업 수행"},
        {"id": "evaluate", "label": "평가", "description": "실행 결과 평가"},
        {"id": "reflect", "label": "반성", "description": "작업 반성 및 개선점 도출"},
        {"id": "memory_write", "label": "기억", "description": "장기기억에 저장"},
        {"id": "return_result", "label": "완료", "description": "결과 반환"},
    ]

    edges = [
        {"from": "receive", "to": "plan"},
        {"from": "plan", "to": "execute"},
        {"from": "execute", "to": "evaluate"},
        {"from": "evaluate", "to": "reflect", "label": "성공"},
        {"from": "evaluate", "to": "execute", "label": "재시도"},
        {"from": "reflect", "to": "memory_write"},
        {"from": "memory_write", "to": "return_result"},
    ]

    # 현재 노드 조회
    from jinxus.agents.state_tracker import get_state_tracker
    tracker = get_state_tracker()
    state = tracker.get_state(agent_name)
    current_node = state.current_node.value if state and state.current_node else None

    return {
        "agent_name": agent_name,
        "nodes": nodes,
        "edges": edges,
        "current_node": current_node,
    }
