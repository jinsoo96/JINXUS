"""MCP 서버 설정 관리

사용할 MCP 서버들을 여기서 정의한다.
새 MCP 서버 추가: 이 파일에 설정 추가 후 서버 재시작
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MCPServerConfig:
    """MCP 서버 설정"""
    name: str                          # 서버 이름
    command: str                       # 실행 명령
    args: list[str] = field(default_factory=list)  # 명령 인자
    env: dict = field(default_factory=dict)        # 환경 변수
    allowed_agents: list[str] = field(default_factory=list)  # 허용 에이전트 (빈 리스트 = 전체)
    enabled: bool = True               # 활성화 여부
    description: str = ""              # 설명
    requires_api_key: str = ""         # 필요한 API 키 이름 (빈 문자열 = 키 불필요)


# ============================================================
# MCP 서버 설정 목록
# ============================================================

MCP_SERVERS: list[MCPServerConfig] = [
    # ----------------------------------------------------------
    # Memory - 지식 그래프 기반 영구 메모리
    # 학습 내용 더 잘 축적
    # ----------------------------------------------------------
    MCPServerConfig(
        name="memory",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"],
        allowed_agents=[],  # 모든 에이전트
        enabled=True,
        description="지식 그래프 기반 영구 메모리",
    ),

    # ----------------------------------------------------------
    # Filesystem - 파일 시스템 접근
    # WORKSPACE_ROOT env로 경로 지정. 미설정 시 /home/jinsookim 사용
    # Docker 볼륨: /home/jinsookim:/home/jinsookim:rw 마운트됨
    # ----------------------------------------------------------
    MCPServerConfig(
        name="filesystem",
        command="npx",
        args=[
            "-y",
            "@modelcontextprotocol/server-filesystem",
            os.getenv("WORKSPACE_ROOT", "/home/jinsookim"),
        ],
        allowed_agents=[
            "JX_OPS", "JX_CODER", "JX_WRITER", "JX_ANALYST",
            "JX_FRONTEND", "JX_BACKEND", "JX_INFRA", "JX_REVIEWER", "JX_TESTER",
        ],
        enabled=True,
        description="파일 시스템 읽기/쓰기 (/home/jinsookim 전체 접근)",
    ),

    # ----------------------------------------------------------
    # Brave Search - 웹 검색
    # BRAVE_API_KEY 환경변수 필요
    # ----------------------------------------------------------
    MCPServerConfig(
        name="brave-search",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env={"BRAVE_API_KEY": os.getenv("BRAVE_API_KEY", "")},
        allowed_agents=[],  # 모든 에이전트 사용 가능
        enabled=True,  # 항상 활성화 (API 키 없으면 연결 안 됨)
        description="Brave 웹 검색",
        requires_api_key="BRAVE_API_KEY",
    ),

    # ----------------------------------------------------------
    # Fetch - 웹 콘텐츠 가져오기
    # URL에서 콘텐츠 추출
    # ----------------------------------------------------------
    MCPServerConfig(
        name="fetch",
        command="npx",
        args=["-y", "@kazuph/mcp-fetch"],
        allowed_agents=[],  # 모든 에이전트 사용 가능
        enabled=True,
        description="웹 콘텐츠 가져오기",
    ),

    # ----------------------------------------------------------
    # GitHub - GitHub API 연동
    # GITHUB_TOKEN 환경변수 필요
    # ----------------------------------------------------------
    MCPServerConfig(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_TOKEN", "")},
        allowed_agents=["JX_OPS", "JX_CODER", "JX_RESEARCHER"],
        enabled=True,  # 항상 활성화 (API 키 없으면 연결 안 됨)
        description="GitHub 레포지토리 관리",
        requires_api_key="GITHUB_TOKEN",
    ),

    # ----------------------------------------------------------
    # Git - 로컬 Git 저장소 관리
    # ----------------------------------------------------------
    MCPServerConfig(
        name="git",
        command="npx",
        args=["-y", "mcp-git"],
        allowed_agents=["JX_OPS", "JX_CODER"],
        enabled=True,
        description="로컬 Git 저장소 관리",
    ),

    # ----------------------------------------------------------
    # Sequential Thinking - 단계별 사고
    # 복잡한 문제 해결
    # ----------------------------------------------------------
    MCPServerConfig(
        name="sequential-thinking",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        allowed_agents=[],  # 모든 에이전트
        enabled=True,
        description="단계별 사고 및 문제 해결",
    ),

    # ----------------------------------------------------------
    # Playwright - 브라우저 자동화 (더 강력한 버전)
    # 웹 스크래핑, 스크린샷, 브라우저 조작
    # ----------------------------------------------------------
    MCPServerConfig(
        name="playwright",
        command="npx",
        args=["-y", "@playwright/mcp", "--headless"],  # headless 모드 추가
        allowed_agents=["JX_RESEARCHER", "JX_CODER", "JX_OPS"],
        enabled=True,
        description="Playwright 브라우저 자동화 (크롬/파이어폭스/사파리)",
    ),

    # ----------------------------------------------------------
    # Puppeteer - 브라우저 자동화 (대안)
    # 웹 스크래핑, 스크린샷
    # ----------------------------------------------------------
    MCPServerConfig(
        name="puppeteer",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        allowed_agents=["JX_RESEARCHER", "JX_CODER"],
        enabled=False,  # playwright 사용하므로 비활성화
        description="Puppeteer 브라우저 자동화",
    ),

    # ----------------------------------------------------------
    # SQLite - SQLite 데이터베이스
    # ----------------------------------------------------------
    MCPServerConfig(
        name="sqlite",
        command="npx",
        args=[
            "-y",
            "mcp-sqlite-server",
            "--db-path",
            os.path.join(os.path.dirname(__file__), "..", "data", "jinxus_meta.db"),
        ],
        allowed_agents=["JX_ANALYST", "JX_OPS"],
        enabled=True,
        description="SQLite 데이터베이스 접근",
    ),

    # ----------------------------------------------------------
    # Slack - 슬랙 메시지 읽기/쓰기
    # SLACK_BOT_TOKEN, SLACK_TEAM_ID 환경변수 필요
    # 채널 메시지 조회, 전송, 사용자 목록 등
    # ----------------------------------------------------------
    MCPServerConfig(
        name="slack",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env={
            "SLACK_BOT_TOKEN": os.getenv("SLACK_BOT_TOKEN", ""),
            "SLACK_TEAM_ID": os.getenv("SLACK_TEAM_ID", ""),
        },
        allowed_agents=["JX_OPS", "JX_WRITER"],  # 운영/문서 에이전트만
        enabled=bool(os.getenv("SLACK_BOT_TOKEN")),  # 토큰 있을 때만 활성화
        description="Slack 채널 메시지 읽기/쓰기",
        requires_api_key="SLACK_BOT_TOKEN",
    ),

    # ----------------------------------------------------------
    # Notion - 노션 페이지/데이터베이스 읽기/쓰기
    # NOTION_API_KEY 환경변수 필요 (내부 통합 토큰)
    # 페이지 조회, 생성, 업데이트, 데이터베이스 쿼리 등
    # ----------------------------------------------------------
    MCPServerConfig(
        name="notion",
        command="npx",
        args=["-y", "@notionhq/notion-mcp-server"],
        env={
            "OPENAPI_MCP_HEADERS": '{"Authorization": "Bearer ' + os.getenv("NOTION_API_KEY", "") + '", "Notion-Version": "2022-06-28"}',
        },
        allowed_agents=["JX_WRITER", "JX_ANALYST", "JX_OPS"],
        enabled=bool(os.getenv("NOTION_API_KEY")),  # 키 있을 때만 활성화
        description="Notion 페이지/데이터베이스 읽기/쓰기",
        requires_api_key="NOTION_API_KEY",
    ),
]


def get_enabled_servers() -> list[MCPServerConfig]:
    """활성화된 MCP 서버 목록"""
    return [s for s in MCP_SERVERS if s.enabled]


def get_all_servers() -> list[MCPServerConfig]:
    """모든 MCP 서버 목록 (비활성화 포함)"""
    return MCP_SERVERS


def get_server_by_name(name: str) -> Optional[MCPServerConfig]:
    """이름으로 MCP 서버 설정 조회"""
    for s in MCP_SERVERS:
        if s.name == name:
            return s
    return None


def get_servers_for_agent(agent_name: str) -> list[MCPServerConfig]:
    """에이전트가 사용 가능한 MCP 서버 목록"""
    return [
        s for s in get_enabled_servers()
        if not s.allowed_agents or agent_name in s.allowed_agents
    ]
