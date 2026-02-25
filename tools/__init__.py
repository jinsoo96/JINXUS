from .base import JinxTool, ToolResult
from .code_executor import CodeExecutor
from .web_searcher import WebSearcher
from .file_manager import FileManager
from .github_agent import GitHubAgent
from .scheduler import Scheduler

__all__ = [
    "JinxTool",
    "ToolResult",
    "CodeExecutor",
    "WebSearcher",
    "FileManager",
    "GitHubAgent",
    "Scheduler",
]


# 도구 레지스트리
TOOL_REGISTRY: dict[str, JinxTool] = {}


def register_tools() -> dict[str, JinxTool]:
    """모든 도구 등록 및 반환"""
    global TOOL_REGISTRY

    if not TOOL_REGISTRY:
        TOOL_REGISTRY = {
            "code_executor": CodeExecutor(),
            "web_searcher": WebSearcher(),
            "file_manager": FileManager(),
            "github_agent": GitHubAgent(),
            "scheduler": Scheduler(),
        }

    return TOOL_REGISTRY


def get_tool(name: str) -> JinxTool | None:
    """이름으로 도구 조회"""
    if not TOOL_REGISTRY:
        register_tools()
    return TOOL_REGISTRY.get(name)


def get_tools_for_agent(agent_name: str) -> dict[str, JinxTool]:
    """에이전트가 사용 가능한 도구만 반환"""
    if not TOOL_REGISTRY:
        register_tools()

    return {
        name: tool
        for name, tool in TOOL_REGISTRY.items()
        if tool.is_allowed(agent_name)
    }
