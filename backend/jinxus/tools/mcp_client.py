"""MCP (Model Context Protocol) 클라이언트 래퍼

외부 MCP 서버들을 JINXUS 도구 시스템과 통합한다.
"""
import json
import logging
from typing import Any, Optional
from dataclasses import dataclass
from contextlib import AsyncExitStack

from .base import JinxTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """MCP 서버 설정"""
    name: str                    # 서버 이름 (예: "memory", "brave-search")
    command: str                 # 실행 명령 (예: "npx", "python")
    args: list[str]              # 명령 인자
    env: Optional[dict] = None   # 환경 변수
    allowed_agents: list[str] = None  # 사용 가능한 에이전트


class MCPClient:
    """MCP 서버 연결 및 도구 호출 클라이언트"""

    def __init__(self):
        self._sessions: dict[str, Any] = {}  # server_name -> ClientSession
        self._exit_stack = AsyncExitStack()
        self._tools_cache: dict[str, list[dict]] = {}  # server_name -> tools list
        self._initialized = False

    async def initialize(self):
        """MCP 클라이언트 초기화"""
        if self._initialized:
            return

        try:
            # mcp 라이브러리 동적 임포트 (설치 안 됐을 때 graceful 처리)
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            self._ClientSession = ClientSession
            self._StdioServerParameters = StdioServerParameters
            self._stdio_client = stdio_client
            self._initialized = True
            logger.info("MCP 클라이언트 초기화 완료")
        except ImportError:
            logger.warning("mcp 라이브러리 미설치 - MCP 도구 비활성화")
            self._initialized = False

    async def connect_server(self, config: MCPServerConfig) -> bool:
        """MCP 서버 연결

        Args:
            config: MCP 서버 설정

        Returns:
            연결 성공 여부
        """
        if not self._initialized:
            await self.initialize()

        if not self._initialized:
            logger.warning(f"MCP 미초기화 - {config.name} 서버 연결 스킵")
            return False

        try:
            logger.debug(f"MCP 서버 연결 시도: {config.name} ({config.command} {config.args})")

            server_params = self._StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env,
            )

            # stdio 연결 설정
            stdio_transport = await self._exit_stack.enter_async_context(
                self._stdio_client(server_params)
            )
            stdio, write = stdio_transport

            logger.debug(f"MCP 서버 stdio 연결됨: {config.name}")

            # 세션 생성 및 초기화
            session = await self._exit_stack.enter_async_context(
                self._ClientSession(stdio, write)
            )
            await session.initialize()

            self._sessions[config.name] = session

            # 사용 가능한 도구 목록 캐시
            tools_response = await session.list_tools()
            self._tools_cache[config.name] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in tools_response.tools
            ]

            logger.info(f"MCP 서버 연결됨: {config.name} (도구 {len(self._tools_cache[config.name])}개)")
            return True

        except Exception as e:
            logger.error(f"MCP 서버 연결 실패 ({config.name}): {e}")
            return False

    async def list_tools(self, server_name: str = None) -> list[dict]:
        """연결된 MCP 서버의 도구 목록

        Args:
            server_name: 특정 서버만 조회 (None이면 전체)

        Returns:
            도구 목록 (name, description, server 포함)
        """
        tools = []

        servers = [server_name] if server_name else self._tools_cache.keys()

        for srv in servers:
            if srv in self._tools_cache:
                for tool in self._tools_cache[srv]:
                    tools.append({
                        **tool,
                        "server": srv,
                        "full_name": f"mcp:{srv}:{tool['name']}",
                    })

        return tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> ToolResult:
        """MCP 도구 호출

        Args:
            server_name: MCP 서버 이름
            tool_name: 도구 이름
            arguments: 도구 인자

        Returns:
            ToolResult: 실행 결과
        """
        import time
        start_time = time.time()

        if server_name not in self._sessions:
            return ToolResult(
                success=False,
                output=None,
                error=f"MCP 서버 '{server_name}' 연결되지 않음",
                duration_ms=0,
            )

        try:
            session = self._sessions[server_name]
            result = await session.call_tool(tool_name, arguments)

            duration_ms = int((time.time() - start_time) * 1000)

            # 결과 파싱
            if result.isError:
                return ToolResult(
                    success=False,
                    output=None,
                    error=str(result.content),
                    duration_ms=duration_ms,
                )

            # 콘텐츠 추출
            output = ""
            for content in result.content:
                if hasattr(content, "text"):
                    output += content.text
                elif hasattr(content, "data"):
                    output += str(content.data)

            return ToolResult(
                success=True,
                output=output,
                error=None,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"MCP 도구 호출 실패 ({server_name}:{tool_name}): {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=duration_ms,
            )

    async def close(self):
        """모든 MCP 연결 종료"""
        await self._exit_stack.aclose()
        self._sessions.clear()
        self._tools_cache.clear()
        logger.info("MCP 클라이언트 연결 종료")

    @property
    def connected_servers(self) -> list[str]:
        """연결된 서버 목록"""
        return list(self._sessions.keys())

    def is_connected(self, server_name: str) -> bool:
        """특정 서버 연결 여부"""
        return server_name in self._sessions


class MCPToolAdapter(JinxTool):
    """MCP 서버를 JINXUS 도구로 감싸는 어댑터

    기존 JinxTool 인터페이스와 호환되게 MCP 도구를 노출한다.
    자동 캐싱 지원 (읽기 전용 도구만)
    """

    # 캐싱 가능한 MCP 도구 패턴 (읽기 전용)
    CACHEABLE_PATTERNS = [
        "get_", "list_", "search_", "read_", "fetch_", "query_",
        "brave_web_search",  # Brave 검색
        "get_file_contents", "read_file", "list_directory",  # Filesystem
        "list_repos", "get_repo", "get_file", "get_issue", "get_pr",  # GitHub
    ]

    # 캐싱 제외 (쓰기 작업)
    NON_CACHEABLE_PATTERNS = [
        "create_", "update_", "delete_", "write_", "push_", "commit_",
        "navigate", "click", "type", "screenshot",  # Playwright (동적)
    ]

    def __init__(
        self,
        mcp_client: MCPClient,
        server_name: str,
        tool_name: str,
        description: str = "",
        allowed_agents: list[str] = None,
        input_schema: dict = None,
    ):
        super().__init__()
        self._mcp_client = mcp_client
        self._server_name = server_name
        self._tool_name = tool_name

        self.name = f"mcp:{server_name}:{tool_name}"
        self.description = description or f"MCP 도구 ({server_name}/{tool_name})"
        self.allowed_agents = allowed_agents or []
        self.input_schema = input_schema or {
            "type": "object",
            "properties": {},
            "required": [],
        }

        # 캐싱 가능 여부 사전 계산
        self._is_cacheable = self._check_cacheable()

    def _check_cacheable(self) -> bool:
        """이 도구가 캐싱 가능한지 확인"""
        tool_lower = self._tool_name.lower()

        # 제외 패턴 먼저 체크
        for pattern in self.NON_CACHEABLE_PATTERNS:
            if pattern in tool_lower:
                return False

        # 캐싱 가능 패턴 체크
        for pattern in self.CACHEABLE_PATTERNS:
            if pattern in tool_lower:
                return True

        # 기본값: 캐싱 안 함 (안전)
        return False

    def _make_cache_id(self, input_data: dict) -> str:
        """캐시 식별자 생성"""
        import json
        import hashlib
        content = f"{self._server_name}:{self._tool_name}:{json.dumps(input_data, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()

    async def run(self, input_data: dict) -> ToolResult:
        """MCP 도구 실행 (캐싱 지원)"""
        self._start_timer()

        use_cache = input_data.pop("use_cache", True)  # 캐시 사용 여부

        # 캐시 확인
        if self._is_cacheable and use_cache:
            try:
                from .cache_manager import cache_get, cache_set

                cache_id = self._make_cache_id(input_data)
                cached = await cache_get("mcp", cache_id)

                if cached:
                    return ToolResult(
                        success=True,
                        output={**cached, "from_cache": True},
                        duration_ms=self._get_duration_ms(),
                    )
            except Exception:
                pass  # 캐시 실패해도 계속 진행

        # 실제 MCP 호출
        result = await self._mcp_client.call_tool(
            self._server_name,
            self._tool_name,
            input_data,
        )

        # 성공한 결과 캐싱
        if self._is_cacheable and use_cache and result.success:
            try:
                from .cache_manager import cache_set

                cache_id = self._make_cache_id(input_data)
                await cache_set("mcp", cache_id, result.output)
            except Exception:
                pass

        return result


# 글로벌 MCP 클라이언트 인스턴스
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """MCP 클라이언트 싱글톤"""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


async def initialize_mcp_client() -> MCPClient:
    """MCP 클라이언트 초기화 및 반환"""
    client = get_mcp_client()
    await client.initialize()
    return client
