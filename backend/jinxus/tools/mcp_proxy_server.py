"""MCP Proxy Server — JINXUS Python 도구를 MCP 서버로 노출

Claude Code CLI가 이 MCP 서버를 연결하면
HR 도구, 스케줄러, 메모리 검색 등을 네이티브 도구처럼 사용 가능.

실행: python -m jinxus.tools.mcp_proxy_server
환경변수:
    JINXUS_BACKEND_PORT: 백엔드 포트 (기본 19000)
    JINXUS_AGENT_NAME: 에이전트 이름 (도구 필터링용)
"""
import asyncio
import json
import os
import sys
from logging import getLogger

logger = getLogger(__name__)

# MCP SDK import (없으면 graceful 실패)
try:
    from mcp.server.fastmcp import FastMCP
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    logger.warning("MCP SDK not available. Install: pip install mcp")


def create_mcp_server(tool_names: list = None) -> "FastMCP":
    """JINXUS 도구를 MCP 서버로 변환

    Args:
        tool_names: 노출할 도구 이름 목록 (None이면 전부)

    Returns:
        FastMCP 서버 인스턴스
    """
    if not HAS_MCP:
        raise RuntimeError("MCP SDK not installed")

    mcp = FastMCP("jinxus-tools")

    # 도구 레지스트리에서 도구 로드
    from jinxus.tools import get_tool, get_all_tools_info

    all_tools = get_all_tools_info()
    registered = 0

    for tool_info in all_tools:
        name = tool_info.get("name", "")
        if tool_names and name not in tool_names:
            continue

        tool = get_tool(name)
        if tool is None:
            continue

        # MCP 도구로 등록
        _register_tool(mcp, tool, tool_info)
        registered += 1

    logger.info("MCP proxy server: %d tools registered", registered)
    return mcp


def _register_tool(mcp: "FastMCP", tool, tool_info: dict):
    """개별 도구를 MCP 서버에 등록"""
    name = tool_info.get("name", "")
    description = tool_info.get("description", f"JINXUS tool: {name}")

    # input_schema에서 파라미터 추출
    schema = tool_info.get("input_schema", {})
    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # MCP 도구 등록 (데코레이터 대신 직접 등록)
    async def _handler(**kwargs):
        try:
            result = await tool.run(kwargs)
            if result.success:
                return result.output
            else:
                return f"Error: {result.error}"
        except Exception as e:
            return f"Tool execution error: {e}"

    # FastMCP의 도구 등록
    _handler.__name__ = name
    _handler.__doc__ = description
    mcp.tool(name=name, description=description)(_handler)


def build_proxy_mcp_config(
    backend_port: int = 19000,
    tool_names: list = None,
) -> dict:
    """에이전트 세션용 JINXUS 도구 프록시 MCP 설정 생성

    Claude CLI의 --mcp-config에 넘길 설정.
    """
    env = {
        "JINXUS_BACKEND_PORT": str(backend_port),
    }
    if tool_names:
        env["JINXUS_TOOL_NAMES"] = ",".join(tool_names)

    return {
        "mcpServers": {
            "_jinxus_builtin": {
                "command": sys.executable,
                "args": ["-m", "jinxus.tools.mcp_proxy_server"],
                "env": env,
            },
        },
    }


# ============================================================================
# Standalone entry point
# ============================================================================

def main():
    """MCP 서버 실행 (stdio transport)"""
    if not HAS_MCP:
        print("Error: MCP SDK not installed. pip install mcp", file=sys.stderr)
        sys.exit(1)

    # 환경변수에서 설정 로드
    tool_names_str = os.environ.get("JINXUS_TOOL_NAMES", "")
    tool_names = [t.strip() for t in tool_names_str.split(",") if t.strip()] or None

    mcp = create_mcp_server(tool_names=tool_names)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
