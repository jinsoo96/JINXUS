"""Tool Policy Engine (B-6) — 에이전트별 도구 접근 정책

각 에이전트가 사용할 수 있는 도구를 제한하여:
1. 불필요한 도구 노출 방지 (LLM 혼동 감소)
2. 보안 강화 (코드 실행 등 위험 도구 제한)
3. 비용 절감 (불필요한 MCP 호출 방지)
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# 에이전트별 도구 정책 정의
# whitelist: 허용 도구 패턴 (None = 모두 허용)
# blacklist: 차단 도구 패턴 (whitelist보다 우선)
# max_tool_rounds: 에이전트별 최대 도구 호출 횟수 (None = 기본값 사용)
AGENT_POLICIES: dict[str, dict] = {
    "JX_RESEARCHER": {
        "whitelist": [
            "web_searcher", "naver_searcher", "weather",
            "github_agent",
            "pdf_reader", "image_analyzer",
            "rss_reader", "community_monitor",
            "mcp:brave_search:*", "mcp:fetch:*",
        ],
        "blacklist": [
            "code_executor", "mcp:filesystem:*", "mcp:git:*",
            "mcp:github:*",  # deprecated MCP GitHub 서버 차단 → github_agent 사용
        ],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    "JX_CODER": {
        "whitelist": [
            "code_executor", "web_searcher",
            "github_agent", "github_graphql",
            "self_modifier",
            "mcp:filesystem:*", "mcp:git:*",
            "mcp:fetch:*",
        ],
        "blacklist": [
            "mcp:github:*",  # deprecated MCP GitHub 서버 차단 → github_agent 사용
        ],
        "max_tool_rounds": 15,
        "max_continuations": 3,
    },
    "JX_WRITER": {
        "whitelist": [
            "web_searcher", "naver_searcher",
            "pdf_reader", "image_analyzer",
            "mcp:brave_search:*", "mcp:fetch:*",
            "mcp:slack:*", "mcp:notion:*",
        ],
        "blacklist": [
            "code_executor", "mcp:filesystem:*", "mcp:git:*",
        ],
        "max_tool_rounds": 8,
        "max_continuations": 1,
    },
    "JX_ANALYST": {
        "whitelist": [
            "web_searcher", "naver_searcher", "weather",
            "pdf_reader", "image_analyzer",
            "rss_reader", "stock_price", "community_monitor",
            "mcp:brave_search:*", "mcp:fetch:*", "mcp:github:*",
            "mcp:notion:*",
        ],
        "blacklist": [
            "code_executor", "mcp:filesystem:*",
        ],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    "JX_OPS": {
        "whitelist": None,  # 모든 도구 허용 (운영 에이전트)
        "blacklist": [],
        "max_tool_rounds": 15,
        "max_continuations": 2,
    },
    # === JX_CODER 하위 전문가 팀 ===
    "JX_FRONTEND": {
        "whitelist": [
            "code_executor",
            "mcp:filesystem:*", "mcp:fetch:*",
        ],
        "blacklist": [
            "mcp:git:*", "mcp:github:*",  # git/github는 JX_CODER가 직접 처리
        ],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    "JX_BACKEND": {
        "whitelist": [
            "code_executor", "web_searcher", "github_agent",
            "self_modifier",
            "mcp:filesystem:*", "mcp:git:*", "mcp:fetch:*",
        ],
        "blacklist": [],
        "max_tool_rounds": 15,
        "max_continuations": 2,
    },
    "JX_INFRA": {
        "whitelist": [
            "code_executor",
            "self_modifier",
            "mcp:filesystem:*", "mcp:git:*", "mcp:fetch:*",
        ],
        "blacklist": [
            "mcp:github:*",  # GitHub 조작은 JX_CODER 경유
        ],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    "JX_REVIEWER": {
        "whitelist": [
            "github_agent", "github_graphql",  # GitHub 레포 읽기
            "mcp:filesystem:*", "mcp:fetch:*",  # 로컬/원격 코드 읽기
        ],
        "blacklist": [
            "code_executor",  # 리뷰어는 코드 실행 불가
            "mcp:git:*", "mcp:github:*",  # deprecated MCP GitHub 차단
        ],
        "max_tool_rounds": 20,
        "max_continuations": 3,
    },
    "JX_TESTER": {
        "whitelist": [
            "code_executor",
            "mcp:filesystem:*",  # 코드 읽기 + 테스트 실행
        ],
        "blacklist": [
            "mcp:git:*", "mcp:github:*",
        ],
        "max_tool_rounds": 15,
        "max_continuations": 2,
    },
}


def _match_pattern(tool_name: str, pattern: str) -> bool:
    """도구 이름이 패턴과 매치되는지 확인

    패턴:
    - "web_searcher" → 정확히 일치
    - "mcp:brave_search:*" → prefix 매칭
    """
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        return tool_name.startswith(prefix)
    return tool_name == pattern


def filter_tools_for_agent(
    agent_name: str,
    tools: dict,
) -> dict:
    """에이전트 정책에 따라 도구 필터링

    Args:
        agent_name: 에이전트 이름
        tools: {name: JinxTool} 딕셔너리

    Returns:
        필터링된 도구 딕셔너리
    """
    policy = AGENT_POLICIES.get(agent_name)

    if not policy:
        return tools  # 정책 없으면 모든 도구 허용

    whitelist = policy.get("whitelist")
    blacklist = policy.get("blacklist", [])

    filtered = {}

    for name, tool in tools.items():
        # 블랙리스트 체크 (우선)
        if any(_match_pattern(name, p) for p in blacklist):
            continue

        # 화이트리스트 체크
        if whitelist is None:
            # None = 모든 도구 허용
            filtered[name] = tool
        elif any(_match_pattern(name, p) for p in whitelist):
            filtered[name] = tool

    if len(filtered) != len(tools):
        logger.debug(
            f"[ToolPolicy] {agent_name}: {len(tools)} → {len(filtered)} 도구 "
            f"(차단: {len(tools) - len(filtered)}개)"
        )

    return filtered


def get_max_tool_rounds(agent_name: str, default: int = 15) -> int:
    """에이전트별 최대 도구 호출 횟수 반환"""
    policy = AGENT_POLICIES.get(agent_name)
    if policy and policy.get("max_tool_rounds") is not None:
        return policy["max_tool_rounds"]
    return default


def get_max_continuations(agent_name: str, default: int = 2) -> int:
    """에이전트별 최대 continuation 횟수 반환

    max_rounds 도달 후 작업이 미완료일 때, 컨텍스트를 요약하여
    새 세션으로 이어서 작업할 수 있는 최대 횟수.
    """
    policy = AGENT_POLICIES.get(agent_name)
    if policy and policy.get("max_continuations") is not None:
        return policy["max_continuations"]
    return default
