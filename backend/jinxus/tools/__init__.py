"""JINXUS 도구 시스템

기존 도구 + MCP 도구를 통합 관리한다.
"""
import logging
from typing import Optional

from .base import JinxTool, ToolResult
from .code_executor import CodeExecutor
from .web_searcher import WebSearcher
from .file_manager import FileManager
from .github_agent import GitHubAgent
from .github_graphql import GitHubGraphQL
from .scheduler import Scheduler
from .hr_tool import HRTool
from .system_manager import SystemManager
from .prompt_version_manager import (
    PromptVersionManager,
    get_prompt_version_manager,
    sync_all_prompts,
)
from .mcp_client import (
    MCPClient,
    MCPToolAdapter,
    MCPServerConfig as MCPServerConfigClient,
    get_mcp_client,
    initialize_mcp_client,
)
from .dynamic_executor import (
    DynamicToolExecutor,
    ToolCall,
    ExecutionResult,
    get_dynamic_executor,
)

logger = logging.getLogger(__name__)

__all__ = [
    "JinxTool",
    "ToolResult",
    "CodeExecutor",
    "WebSearcher",
    "FileManager",
    "GitHubAgent",
    "GitHubGraphQL",
    "Scheduler",
    "HRTool",
    "SystemManager",
    "PromptVersionManager",
    "get_prompt_version_manager",
    "sync_all_prompts",
    "MCPClient",
    "MCPToolAdapter",
    "get_mcp_client",
    "initialize_mcp_client",
    "register_tools",
    "register_mcp_tools",
    "get_tool",
    "get_tools_for_agent",
    "get_all_tools_info",
    # Dynamic Executor (Claude tool_use)
    "DynamicToolExecutor",
    "ToolCall",
    "ExecutionResult",
    "get_dynamic_executor",
]


# 도구 레지스트리 (기존 도구 + MCP 도구)
TOOL_REGISTRY: dict[str, JinxTool] = {}
MCP_TOOLS_REGISTERED: bool = False


def register_tools() -> dict[str, JinxTool]:
    """기존 도구 등록 및 반환"""
    global TOOL_REGISTRY

    if not TOOL_REGISTRY:
        TOOL_REGISTRY = {
            "code_executor": CodeExecutor(),
            "web_searcher": WebSearcher(),
            "file_manager": FileManager(),
            "github_agent": GitHubAgent(),
            "github_graphql": GitHubGraphQL(),
            "scheduler": Scheduler(),
            "hr_tool": HRTool(),
            "system_manager": SystemManager(),
            "prompt_version_manager": PromptVersionManager(),
        }
        logger.info(f"기존 도구 {len(TOOL_REGISTRY)}개 등록됨")

    return TOOL_REGISTRY


async def register_mcp_tools() -> dict[str, JinxTool]:
    """MCP 서버 연결 및 도구 등록

    Returns:
        등록된 전체 도구 (기존 + MCP)
    """
    global TOOL_REGISTRY, MCP_TOOLS_REGISTERED

    if MCP_TOOLS_REGISTERED:
        return TOOL_REGISTRY

    # 기존 도구 먼저 등록
    if not TOOL_REGISTRY:
        register_tools()

    try:
        # MCP 서버 설정 로드
        from jinxus.config.mcp_servers import get_enabled_servers, MCPServerConfig

        # MCP 클라이언트 초기화
        mcp_client = await initialize_mcp_client()

        # 활성화된 MCP 서버 연결
        enabled_servers = get_enabled_servers()
        connected_count = 0

        for server_config in enabled_servers:
            logger.info(f"MCP 서버 연결 시도: {server_config.name}")
            # MCPServerConfig를 mcp_client용 형식으로 변환
            client_config = MCPServerConfigClient(
                name=server_config.name,
                command=server_config.command,
                args=server_config.args,
                env=server_config.env if server_config.env else None,
                allowed_agents=server_config.allowed_agents,
            )

            try:
                success = await mcp_client.connect_server(client_config)
                if success:
                    connected_count += 1
                    logger.info(f"MCP 서버 연결 성공: {server_config.name}")

                    # 연결된 서버의 도구들을 레지스트리에 추가
                    tools = await mcp_client.list_tools(server_config.name)
                    for tool_info in tools:
                        adapter = MCPToolAdapter(
                            mcp_client=mcp_client,
                            server_name=server_config.name,
                            tool_name=tool_info["name"],
                            description=tool_info.get("description", ""),
                            allowed_agents=server_config.allowed_agents,
                            input_schema=tool_info.get("input_schema"),
                        )
                        TOOL_REGISTRY[adapter.name] = adapter
                else:
                    logger.warning(f"MCP 서버 연결 실패: {server_config.name}")
            except Exception as e:
                logger.error(f"MCP 서버 연결 예외 ({server_config.name}): {e}")

        MCP_TOOLS_REGISTERED = True
        logger.info(f"MCP 서버 {connected_count}/{len(enabled_servers)}개 연결, "
                   f"총 도구 {len(TOOL_REGISTRY)}개")

    except ImportError as e:
        logger.warning(f"MCP 설정 로드 실패: {e}")
    except Exception as e:
        logger.error(f"MCP 도구 등록 실패: {e}")

    return TOOL_REGISTRY


def get_tool(name: str) -> Optional[JinxTool]:
    """이름으로 도구 조회

    Args:
        name: 도구 이름 (기존: "code_executor", MCP: "mcp:memory:create_entities")

    Returns:
        JinxTool 또는 None
    """
    if not TOOL_REGISTRY:
        register_tools()
    return TOOL_REGISTRY.get(name)


def get_tools_for_agent(agent_name: str) -> dict[str, JinxTool]:
    """에이전트가 사용 가능한 도구만 반환

    Args:
        agent_name: 에이전트 이름 (예: "JX_CODER")

    Returns:
        사용 가능한 도구 딕셔너리
    """
    if not TOOL_REGISTRY:
        register_tools()

    return {
        name: tool
        for name, tool in TOOL_REGISTRY.items()
        if tool.is_allowed(agent_name)
    }


def get_all_tools_info() -> list[dict]:
    """모든 도구 정보 반환 (디버깅/상태 확인용)

    Returns:
        도구 정보 리스트
    """
    if not TOOL_REGISTRY:
        register_tools()

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "allowed_agents": tool.allowed_agents,
            "is_mcp": tool.name.startswith("mcp:"),
        }
        for tool in TOOL_REGISTRY.values()
    ]
