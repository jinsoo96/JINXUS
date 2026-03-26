"""Tool Policy Engine (B-6) — 에이전트별 도구 접근 정책

v2.1.0: 도구 제한 전면 해제 — 모든 에이전트가 모든 도구를 자율적으로 선택
각 에이전트에게 모든 도구의 디스크립션을 제공하고, 에이전트가 스스로 판단해 필요한 도구를 사용.
max_tool_rounds / max_continuations 만 유지하여 리소스 낭비 방지.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# 에이전트별 도구 정책 정의
# whitelist: None = 모든 도구 허용
# blacklist: [] = 차단 없음
# max_tool_rounds: 에이전트별 최대 도구 호출 횟수 (리소스 제어)
# max_continuations: 컨텍스트 이어받기 최대 횟수
AGENT_POLICIES: dict[str, dict] = {
    "JX_RESEARCHER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 15,
        "max_continuations": 3,
    },
    "JX_CODER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 15,
        "max_continuations": 3,
    },
    "JX_WRITER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    "JX_ANALYST": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    "JX_OPS": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 15,
        "max_continuations": 2,
    },
    # === JX_CODER 하위 전문가 팀 ===
    "JX_FRONTEND": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    "JX_BACKEND": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 15,
        "max_continuations": 2,
    },
    "JX_INFRA": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    "JX_REVIEWER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 20,
        "max_continuations": 3,
    },
    "JX_TESTER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 15,
        "max_continuations": 2,
    },
    # === 임원진 (C-Suite) ===
    # JINXUS_CORE(CEO)는 정책 없음 → 전체 도구 허용 (오케스트레이터)
    "JX_CTO": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    "JX_COO": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    "JX_CFO": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    # === 마케팅팀 ===
    "JX_MARKETING": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    "JS_PERSONA": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 8,
        "max_continuations": 1,
    },
    "JX_SNS": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    # === 기획팀 ===
    "JX_PRODUCT": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    "JX_STRATEGY": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    # === JX_RESEARCHER 하위 전문가 팀 ===
    "JX_WEB_SEARCHER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 12,
        "max_continuations": 2,
    },
    "JX_DEEP_READER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
        "max_continuations": 2,
    },
    "JX_FACT_CHECKER": {
        "whitelist": None,
        "blacklist": [],
        "max_tool_rounds": 10,
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
