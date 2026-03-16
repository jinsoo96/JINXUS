"""Agents API - 에이전트 상태 조회"""
import logging
from fastapi import APIRouter, HTTPException

from jinxus.api.models import AgentStatus, AgentListResponse
from jinxus.api.deps import get_ready_orchestrator
from jinxus.core import get_orchestrator
from jinxus.memory.meta_store import get_meta_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentListResponse)
async def list_agents():
    """에이전트 목록 및 성능 조회"""
    orchestrator = await get_ready_orchestrator()

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
        except Exception as e:
            logger.warning(f"에이전트 상태 조회 실패 [{agent_name}]: {e}")
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
    orchestrator = await get_ready_orchestrator()

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
async def get_agent_history(agent_name: str, limit: int = 20, offset: int = 0):
    """에이전트 작업 이력 조회 (SQLite에서 직접 조회)"""
    meta_store = get_meta_store()

    # SQLite agent_task_logs 테이블에서 직접 조회 (벡터 검색보다 효율적)
    logs = await meta_store.get_recent_logs(
        agent_name=agent_name,
        limit=limit,
        offset=offset,
    )
    total = await meta_store.get_logs_count(agent_name=agent_name)

    return {
        "agent_name": agent_name,
        "history": logs,
        "total": total,
        "limit": limit,
        "offset": offset,
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
    from jinxus.agents.state_tracker import get_state_tracker, AgentRuntimeState, AgentStatus

    orchestrator = get_orchestrator()
    tracker = get_state_tracker()

    # orchestrator에서 등록된 에이전트 목록 + JINXUS_CORE
    registered_agents = orchestrator.get_agents() if orchestrator.is_initialized else []
    # JINXUS_CORE를 맨 앞에 추가
    all_agents = ["JINXUS_CORE"] + registered_agents

    # 상태 추적기에 없는 에이전트는 기본 상태로 추가
    result_agents = []
    for agent_name in all_agents:
        state = tracker.get_state(agent_name)
        if state:
            result_agents.append(state.to_dict())
        else:
            # 기본 idle 상태 반환
            result_agents.append({
                "name": agent_name,
                "status": "idle",
                "current_node": None,
                "current_task": None,
                "current_tools": [],
                "last_update": None,
                "error_message": None,
            })

    return {
        "agents": result_agents,
        "working_count": len(tracker.get_working_agents()),
    }


@router.get("/JX_CODER/team")
async def get_jx_coder_team():
    """JX_CODER 전문가 팀 조회"""
    from jinxus.agents.coding import CODING_SPECIALISTS
    from jinxus.agents.state_tracker import get_state_tracker

    tracker = get_state_tracker()
    team = []
    for name, cls in CODING_SPECIALISTS.items():
        state = tracker.get_state(name)
        team.append({
            "name": name,
            "description": cls.description,
            "status": state.status.value if state else "idle",
            "current_task": state.current_task if state else None,
            "current_node": state.current_node.value if (state and state.current_node) else None,
        })
    return {"parent": "JX_CODER", "team": team}


@router.get("/JX_RESEARCHER/team")
async def get_jx_researcher_team():
    """JX_RESEARCHER 전문가 팀 조회"""
    from jinxus.agents.research import RESEARCH_SPECIALISTS
    from jinxus.agents.state_tracker import get_state_tracker

    tracker = get_state_tracker()
    team = []
    for name, cls in RESEARCH_SPECIALISTS.items():
        state = tracker.get_state(name)
        team.append({
            "name": name,
            "description": cls.description,
            "status": state.status.value if state else "idle",
            "current_task": state.current_task if state else None,
            "current_node": state.current_node.value if (state and state.current_node) else None,
        })
    return {"parent": "JX_RESEARCHER", "team": team}


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
