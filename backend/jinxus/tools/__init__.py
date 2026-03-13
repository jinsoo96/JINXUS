"""JINXUS 도구 시스템

기존 도구 + MCP 도구를 통합 관리한다.
"""
import logging
from typing import Optional

from .base import JinxTool, ToolResult
from .code_executor import CodeExecutor
from .web_searcher import WebSearcher
from .naver_searcher import NaverSearcher
from .weather import WeatherTool
from .file_manager import FileManager
from .github_agent import GitHubAgent
from .github_graphql import GitHubGraphQL
from .scheduler import Scheduler
from .hr_tool import HRTool
from .system_manager import SystemManager
from .pdf_reader import PDFReader
from .image_analyzer import ImageAnalyzer
from .rss_reader import RSSReader
from .stock_price import StockPrice
from .community_monitor import CommunityMonitor
from .self_modifier import SelfModifier
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
    "NaverSearcher",
    "WeatherTool",
    "FileManager",
    "GitHubAgent",
    "GitHubGraphQL",
    "Scheduler",
    "HRTool",
    "SystemManager",
    "PDFReader",
    "ImageAnalyzer",
    "RSSReader",
    "StockPrice",
    "CommunityMonitor",
    "SelfModifier",
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

# 런타임 비활성화 목록 (재시작 시 초기화)
_RUNTIME_DISABLED: set[str] = set()


def register_tools() -> dict[str, JinxTool]:
    """기존 도구 등록 및 반환"""
    global TOOL_REGISTRY

    if not TOOL_REGISTRY:
        TOOL_REGISTRY = {
            "code_executor": CodeExecutor(),
            "web_searcher": WebSearcher(),
            "naver_searcher": NaverSearcher(),
            "weather": WeatherTool(),
            "file_manager": FileManager(),
            "github_agent": GitHubAgent(),
            "github_graphql": GitHubGraphQL(),
            "scheduler": Scheduler(),
            "hr_tool": HRTool(),
            "system_manager": SystemManager(),
            "pdf_reader": PDFReader(),
            "image_analyzer": ImageAnalyzer(),
            "rss_reader": RSSReader(),
            "stock_price": StockPrice(),
            "community_monitor": CommunityMonitor(),
            "self_modifier": SelfModifier(),
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
                        # MCP spec 어노테이션 파싱 (서버가 직접 제공하는 경우 우선 사용)
                        annot_from_spec = None
                        if tool_info.get("annotations"):
                            try:
                                from jinxus.core.tool_annotation import ToolAnnotations
                                annot_from_spec = ToolAnnotations.from_dict(tool_info["annotations"])
                            except Exception:
                                pass  # 파싱 실패 시 이름 기반 추론으로 fallback

                        adapter = MCPToolAdapter(
                            mcp_client=mcp_client,
                            server_name=server_config.name,
                            tool_name=tool_info["name"],
                            description=tool_info.get("description", ""),
                            allowed_agents=server_config.allowed_agents,
                            input_schema=tool_info.get("input_schema"),
                            annotations=annot_from_spec,  # None이면 _annotation_hook이 자동 추론
                        )
                        TOOL_REGISTRY[adapter.name] = adapter
                        logger.debug(
                            f"MCP 도구 등록: {adapter.name} "
                            f"| annotations={adapter.annotations}"
                        )
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
            "enabled": tool.name not in _RUNTIME_DISABLED,
        }
        for tool in TOOL_REGISTRY.values()
    ]


def set_tool_enabled(name: str, enabled: bool) -> bool:
    """런타임에 도구 활성화/비활성화 (재시작 시 초기화)"""
    if enabled:
        _RUNTIME_DISABLED.discard(name)
    else:
        _RUNTIME_DISABLED.add(name)
    logger.info(f"도구 '{name}' {'활성화' if enabled else '비활성화'}")
    return True
