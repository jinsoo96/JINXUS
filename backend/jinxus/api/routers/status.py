"""Status API - 시스템 상태 조회"""
from fastapi import APIRouter, Query

from jinxus.api.models import SystemStatusResponse
from jinxus.core import get_orchestrator
from jinxus.memory import get_jinx_memory

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


@router.get("/tool-graph")
async def get_tool_graph_info():
    """도구 그래프 구조 조회"""
    from jinxus.core.tool_graph import get_tool_graph
    graph = get_tool_graph()
    return graph.to_dict()


@router.post("/tool-graph/retrieve")
async def retrieve_tool_workflow(query: str, top_k: int = 5, agent_name: str = None):
    """쿼리에서 도구 워크플로우 탐색"""
    from jinxus.core.tool_graph import get_tool_graph
    graph = get_tool_graph()
    workflow = graph.retrieve(query, top_k=top_k, agent_name=agent_name)
    return workflow.to_dict()


@router.get("/tools")
async def get_registered_tools():
    """등록된 도구 목록"""
    from jinxus.tools import get_all_tools_info

    tools = get_all_tools_info()
    mcp_tools = [t for t in tools if t.get("is_mcp")]
    native_tools = [t for t in tools if not t.get("is_mcp")]

    return {
        "total": len(tools),
        "mcp_count": len(mcp_tools),
        "native_count": len(native_tools),
        "mcp_tools": [{"name": t["name"], "description": t.get("description", "")[:100]} for t in mcp_tools],
        "native_tools": [{"name": t["name"], "description": t.get("description", "")[:100]} for t in native_tools],
    }


@router.get("/mcp")
async def get_mcp_status():
    """MCP 서버 연결 상태 조회"""
    import os
    from jinxus.tools.mcp_client import get_mcp_client
    from jinxus.config.mcp_servers import get_all_servers

    mcp_client = get_mcp_client()

    # 연결된 서버 목록
    connected_servers = mcp_client.connected_servers

    # 모든 MCP 서버 목록 (비활성화 포함)
    all_configured_servers = get_all_servers()

    # 서버별 상세 정보
    servers_status = []

    for server_config in all_configured_servers:
        server_name = server_config.name

        # API 키 필요 여부 확인
        requires_key = server_config.requires_api_key
        has_api_key = bool(os.getenv(requires_key, "")) if requires_key else True

        if server_name in connected_servers:
            # 연결된 서버
            tools = await mcp_client.list_tools(server_name)
            servers_status.append({
                "name": server_name,
                "status": "connected",
                "description": server_config.description,
                "tools_count": len(tools),
                "tools": [{"name": t["name"], "description": t.get("description", "")[:80]} for t in tools],
                "requires_api_key": requires_key or None,
                "has_api_key": has_api_key,
                "enabled": server_config.enabled,
            })
        elif requires_key and not has_api_key:
            # API 키 필요한데 없음
            servers_status.append({
                "name": server_name,
                "status": "api_key_missing",
                "description": server_config.description,
                "tools_count": 0,
                "tools": [],
                "requires_api_key": requires_key,
                "has_api_key": False,
                "enabled": server_config.enabled,
                "error": f"{requires_key} 환경변수가 필요합니다",
            })
        elif not server_config.enabled:
            # 비활성화된 서버
            servers_status.append({
                "name": server_name,
                "status": "disabled",
                "description": server_config.description,
                "tools_count": 0,
                "tools": [],
                "requires_api_key": requires_key or None,
                "has_api_key": has_api_key,
                "enabled": False,
                "error": "서버가 비활성화됨",
            })
        else:
            # 연결 실패
            servers_status.append({
                "name": server_name,
                "status": "disconnected",
                "description": server_config.description,
                "tools_count": 0,
                "tools": [],
                "requires_api_key": requires_key or None,
                "has_api_key": has_api_key,
                "enabled": server_config.enabled,
                "error": "서버 연결 실패",
            })

    # 전체 MCP 도구 수
    all_tools = await mcp_client.list_tools()

    return {
        "initialized": mcp_client._initialized,
        "connected_count": len(connected_servers),
        "configured_count": len([s for s in all_configured_servers if s.enabled]),
        "total_configured": len(all_configured_servers),
        "total_tools": len(all_tools),
        "servers": servers_status,
    }


@router.post("/mcp/reconnect/{server_name}")
async def reconnect_mcp_server(server_name: str):
    """MCP 서버 재연결 시도"""
    from jinxus.tools.mcp_client import get_mcp_client, MCPServerConfig as ClientMCPConfig
    from jinxus.config.mcp_servers import get_server_by_name

    mcp_client = get_mcp_client()

    # 설정에서 서버 정보 가져오기
    server_config = get_server_by_name(server_name)

    if not server_config:
        return {
            "success": False,
            "error": f"서버 '{server_name}'가 설정에 없습니다",
        }

    if not server_config.enabled:
        return {
            "success": False,
            "error": f"서버 '{server_name}'가 비활성화 상태입니다",
        }

    # MCP 클라이언트용 설정으로 변환
    config = ClientMCPConfig(
        name=server_config.name,
        command=server_config.command,
        args=server_config.args,
        env=server_config.env,
        allowed_agents=server_config.allowed_agents,
    )

    success = await mcp_client.connect_server(config)

    return {
        "success": success,
        "server_name": server_name,
        "message": "연결 성공" if success else "연결 실패",
    }
