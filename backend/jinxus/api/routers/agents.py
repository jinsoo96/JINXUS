"""Agents API - 에이전트 상태 조회 + 실시간 SSE 스트림"""
import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from jinxus.api.models import AgentStatus, AgentListResponse
from jinxus.api.deps import get_ready_orchestrator
from jinxus.core import get_orchestrator
from jinxus.memory.meta_store import get_meta_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("/personas")
async def get_personas():
    """모든 에이전트 페르소나 메타데이터 반환 — 프론트엔드 단일 소스 동기화용.

    personas.py가 변경되면 이 엔드포인트가 자동으로 반영한다.
    프론트엔드는 이 데이터를 받아 personas.ts의 정적 fallback을 덮어쓴다.
    """
    from jinxus.agents.personas import get_all_personas
    from jinxus.agents.personality import get_personality

    result: dict = {}
    for code, p in get_all_personas().items():
        # home_channel: 임원은 general, 나머지는 첫 번째 비-general 채널
        if p.team == "임원":
            home_channel = "general"
        else:
            non_general = [c for c in p.channels if c not in ("general", "planning")]
            home_channel = non_general[0] if non_general else (p.channels[0] if p.channels else "general")

        archetype = get_personality(p.personality_id) if p.personality_id else None
        result[code] = {
            "name": p.full_name or p.korean_name,
            "firstName": p.korean_name,
            "role": p.role,
            "team": p.team,
            "channel": home_channel,
            "emoji": p.emoji,
            "personalityId": p.personality_id,
            "personalityLabel": archetype.label if archetype else "",
            "personalityEmoji": archetype.emoji if archetype else "",
            "personalityTagline": archetype.tagline if archetype else "",
            "mbti": p.mbti,
            "rank": p.rank,
        }

    return {"personas": result}


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


@router.get("/runtime/stream")
async def stream_runtime_status(request: Request):
    """실시간 에이전트 상태 변경 SSE 스트림.

    이벤트:
    - init: 초기 상태 스냅샷 (에이전트별 1개)
    - state_change: 상태 변경 (working/idle/error)
    - node_change: LangGraph 노드 변경
    - tools_change: 사용 중 도구 변경
    - tool_call: 도구 호출 로그
    - ping: 15초 keepalive
    """
    from jinxus.agents.state_tracker import get_state_tracker

    tracker = get_state_tracker()
    orchestrator = get_orchestrator()
    q = tracker.subscribe()

    async def event_generator():
        try:
            # 초기 상태 스냅샷 전송
            registered_agents = orchestrator.get_agents() if orchestrator.is_initialized else []
            all_agents = ["JINXUS_CORE"] + registered_agents

            for agent_name in all_agents:
                state = tracker.get_state(agent_name)
                if state:
                    data = {
                        "agent": state.name,
                        "status": state.status.value,
                        "node": state.current_node.value if state.current_node else None,
                        "task": state.current_task,
                        "tools": state.current_tools,
                    }
                else:
                    data = {
                        "agent": agent_name,
                        "status": "idle",
                        "node": None,
                        "task": None,
                        "tools": [],
                    }
                yield {"event": "init", "data": json.dumps(data, ensure_ascii=False)}

            # 실시간 이벤트 스트리밍
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {"event": event["type"], "data": json.dumps(event, ensure_ascii=False)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            tracker.unsubscribe(q)

    return EventSourceResponse(event_generator())


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


# ── 전문가팀 레지스트리 (동적 조회용) ────────────────────────────────────
# 새 전문가팀 추가 시 여기에만 등록하면 API 자동 노출
def _get_specialist_registry() -> dict[str, dict]:
    """부모 에이전트 → 전문가 딕셔너리 매핑 (지연 임포트)"""
    from jinxus.agents.coding import CODING_SPECIALISTS
    from jinxus.agents.research import RESEARCH_SPECIALISTS
    return {
        "JX_CODER": CODING_SPECIALISTS,
        "JX_RESEARCHER": RESEARCH_SPECIALISTS,
    }


@router.get("/{agent_name}/team")
async def get_agent_team(agent_name: str):
    """전문가 팀 조회 — 범용 엔드포인트.

    부모 에이전트 이름으로 소속 전문가 팀을 조회한다.
    현재 지원: JX_CODER, JX_RESEARCHER (확장 가능)
    """
    from jinxus.agents.state_tracker import get_state_tracker

    registry = _get_specialist_registry()
    specialists = registry.get(agent_name)
    if not specialists:
        raise HTTPException(
            status_code=404,
            detail=f"전문가 팀 없음: {agent_name}. 가능: {list(registry.keys())}",
        )

    tracker = get_state_tracker()
    team = []
    for name, cls in specialists.items():
        state = tracker.get_state(name)
        team.append({
            "name": name,
            "description": cls.description,
            "status": state.status.value if state else "idle",
            "current_task": state.current_task if state else None,
            "current_node": state.current_node.value if (state and state.current_node) else None,
        })
    return {"parent": agent_name, "team": team}


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
