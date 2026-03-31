"""Relevance Gate — 에이전트 관련성 필터 (Geny 패턴)

broadcast 메시지가 에이전트 역할과 관련 있는지 LLM으로 판단.
무관하면 skip → 불필요한 LLM 비용 절약.

사용 예:
- 그룹 채팅에서 전 에이전트 반응 대신 관련 에이전트만 반응
- AAI 화이트보드에서 새 항목 등장 시 관련 에이전트만 트리거
"""
import logging
import re
from typing import Optional

from anthropic import AsyncAnthropic

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# 키워드 기반 빠른 필터 (LLM 호출 전)
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "JX_CODER": ["코드", "개발", "구현", "버그", "PR", "커밋", "리팩토링", "프론트", "백엔드", "API", "빌드"],
    "JX_RESEARCHER": ["조사", "검색", "리서치", "논문", "분석", "데이터", "통계", "트렌드"],
    "JX_WRITER": ["작성", "문서", "글", "보고서", "자소서", "번역", "에세이", "콘텐츠"],
    "JX_ANALYST": ["분석", "비교", "평가", "전략", "시장", "경쟁", "인사이트"],
    "JX_OPS": ["배포", "서버", "인프라", "모니터링", "Docker", "CI/CD", "장애"],
    "JX_MARKETING": ["마케팅", "광고", "홍보", "SNS", "브랜딩", "캠페인"],
    "JX_PRODUCT": ["기획", "UX", "사용자", "요구사항", "스펙", "와이어프레임"],
    "JX_CTO": ["아키텍처", "기술", "스택", "설계", "확장", "보안"],
}


async def check_relevance(
    message: str,
    agent_name: str,
    agent_role: str = "",
    agent_specialty: str = "",
    threshold: float = 0.5,
    use_llm: bool = True,
) -> tuple[bool, float]:
    """메시지가 에이전트와 관련 있는지 판단

    2단계 판단:
    1. 키워드 매칭 (빠름, 무비용)
    2. LLM 판단 (정확, 유비용) — use_llm=True일 때만

    Args:
        message: 판단할 메시지
        agent_name: 에이전트 이름
        agent_role: 에이전트 역할 설명
        agent_specialty: 에이전트 전문 분야
        threshold: 관련성 임계값 (0.0~1.0)
        use_llm: LLM 판단 사용 여부

    Returns:
        (is_relevant, confidence) 튜플
    """
    if not message:
        return False, 0.0

    # 1단계: 키워드 매칭
    keywords = _ROLE_KEYWORDS.get(agent_name, [])
    if keywords:
        msg_lower = message.lower()
        matches = sum(1 for kw in keywords if kw.lower() in msg_lower)
        if matches >= 2:
            return True, min(1.0, matches * 0.3)
        if matches == 0 and not use_llm:
            return False, 0.0

    # @멘션 확인
    if f"@{agent_name}" in message or f"@{agent_name.lower()}" in message.lower():
        return True, 1.0

    # 2단계: LLM 판단
    if not use_llm:
        # 키워드 1개 매치면 일단 관련 있다고 판단
        if keywords and any(kw.lower() in message.lower() for kw in keywords):
            return True, 0.4
        return False, 0.0

    try:
        settings = get_settings()
        client = AsyncAnthropic(api_key=settings.anthropic_api_key)

        role_desc = agent_role or agent_specialty or agent_name
        prompt = (
            f"에이전트 역할: {role_desc}\n"
            f"전문 분야: {agent_specialty}\n\n"
            f"메시지: {message[:500]}\n\n"
            f"이 메시지가 위 에이전트의 역할/전문 분야와 관련이 있습니까?\n"
            f"YES 또는 NO만 답하세요."
        )

        response = await client.messages.create(
            model=settings.claude_fast_model,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )

        answer = response.content[0].text.strip().upper()

        if "YES" in answer:
            return True, 0.8
        elif "NO" in answer:
            return False, 0.8
        else:
            # 모호한 답변 → 포함
            return True, 0.3

    except Exception as e:
        logger.warning(f"[RelevanceGate] LLM 판단 실패: {e}, 기본 포함으로 처리")
        return True, 0.1


async def filter_relevant_agents(
    message: str,
    agents: list[dict],
    use_llm: bool = False,
) -> list[str]:
    """메시지와 관련된 에이전트만 필터링

    Args:
        message: 판단할 메시지
        agents: [{"name": "JX_CODER", "role": "...", "specialty": "..."}] 형태
        use_llm: LLM 판단 사용 여부

    Returns:
        관련 에이전트 이름 리스트
    """
    relevant = []

    for agent in agents:
        is_relevant, confidence = await check_relevance(
            message=message,
            agent_name=agent.get("name", ""),
            agent_role=agent.get("role", ""),
            agent_specialty=agent.get("specialty", ""),
            use_llm=use_llm,
        )
        if is_relevant:
            relevant.append(agent["name"])

    if not relevant:
        # 아무도 관련 없으면 전체 포함 (메시지 유실 방지)
        return [a["name"] for a in agents]

    return relevant
