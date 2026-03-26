"""ToolLoader — 에이전트 세션용 MCP 설정 빌드

기존 MCP 서버 설정 + JINXUS 내장 도구 프록시를 합쳐서
에이전트 세션에 넘길 MCP 설정을 만든다.
"""
import os
import sys
from logging import getLogger
from typing import Dict, List, Optional

logger = getLogger(__name__)


def build_session_mcp_config(
    agent_name: str,
    global_mcp_servers: Optional[Dict] = None,
    builtin_tool_names: Optional[List[str]] = None,
    extra_mcp: Optional[Dict] = None,
) -> Optional[Dict]:
    """에이전트 세션용 MCP 설정 빌드

    Args:
        agent_name: 에이전트 이름 (도구 필터링용)
        global_mcp_servers: 전역 MCP 서버 설정 (config/mcp_servers.py에서)
        builtin_tool_names: 노출할 JINXUS 내장 도구 이름 목록
        extra_mcp: 추가 MCP 서버 설정

    Returns:
        {"mcpServers": {...}} 형태의 MCP 설정 dict
    """
    servers = {}

    # 1. JINXUS 내장 도구 프록시
    backend_port = int(os.environ.get("JINXUS_PORT", "19000"))
    proxy_env = {
        "JINXUS_BACKEND_PORT": str(backend_port),
        "JINXUS_AGENT_NAME": agent_name,
    }
    if builtin_tool_names:
        proxy_env["JINXUS_TOOL_NAMES"] = ",".join(builtin_tool_names)

    servers["_jinxus_builtin"] = {
        "command": sys.executable,
        "args": ["-m", "jinxus.tools.mcp_proxy_server"],
        "env": proxy_env,
    }

    # 2. 전역 MCP 서버 (config/mcp_servers.py에서 로드된 것)
    if global_mcp_servers:
        for name, config in global_mcp_servers.items():
            # 에이전트 필터링
            allowed = config.get("allowed_agents")
            if allowed and agent_name not in allowed and "*" not in allowed:
                continue

            # MCP 서버 설정 변환
            server_config = {}
            if "command" in config:
                server_config["command"] = config["command"]
                server_config["args"] = config.get("args", [])
            elif "url" in config:
                server_config["url"] = config["url"]

            if "env" in config:
                server_config["env"] = config["env"]

            if server_config:
                servers[name] = server_config

    # 3. 추가 MCP 설정 (세션별 커스텀)
    if extra_mcp:
        for name, config in extra_mcp.get("mcpServers", {}).items():
            servers[name] = config

    if not servers:
        return None

    return {"mcpServers": servers}


def load_global_mcp_servers() -> Dict:
    """config/mcp_servers.py에서 전역 MCP 서버 목록 로드"""
    try:
        from jinxus.config.mcp_servers import MCP_SERVERS
        result = {}
        for server in MCP_SERVERS:
            name = server.get("name", "")
            if name:
                result[name] = server
        return result
    except Exception as e:
        logger.warning("Failed to load global MCP servers: %s", e)
        return {}
