"""PromptBuilder — 에이전트 시스템 프롬프트 조립기

페르소나 정보 + 역할 + MCP 도구 목록 + 메모리 컨텍스트를 합쳐서
Claude Code CLI의 --append-system-prompt에 넘길 프롬프트를 만든다.

사용:
    prompt = build_agent_prompt(persona=get_persona("JX_CODER"), ...)
"""
from logging import getLogger
from typing import List, Optional

logger = getLogger(__name__)


def build_agent_prompt(
    agent_name: str,
    korean_name: str = "",
    role: str = "worker",
    personality: str = "",
    speech_style: str = "",
    skills: Optional[List[str]] = None,
    team: str = "",
    background: str = "",
    quirks: str = "",
    extra_system_prompt: str = "",
    memory_context: str = "",
) -> str:
    """에이전트 시스템 프롬프트 빌드

    Args:
        agent_name: 에이전트 ID (JX_CODER)
        korean_name: 한국어 이름 (민준)
        role: 역할 (developer, researcher, etc.)
        personality: 성격 설명
        speech_style: 말투 설명
        skills: 보유 스킬 목록
        team: 소속 팀
        background: 배경 설명
        quirks: 특이 행동/습관
        extra_system_prompt: 추가 지시사항
        memory_context: 메모리에서 가져온 컨텍스트
    """
    parts = []

    # 1. 아이덴티티
    identity = f"너는 {korean_name}({agent_name})이다."
    if team:
        identity += f" JINXUS의 {team} 소속."
    if role:
        identity += f" 역할: {role}."
    parts.append(identity)

    # 2. 성격/말투
    if personality:
        parts.append(f"성격: {personality}")
    if speech_style:
        parts.append(f"말투: {speech_style}")
    if background:
        parts.append(f"배경: {background}")
    if quirks:
        parts.append(f"특이사항: {quirks}")

    # 3. 스킬
    if skills:
        parts.append(f"전문 분야: {', '.join(skills)}")

    # 4. 말투 규칙 (최우선)
    parts.append("""
## 말투 규칙 (절대 준수)
- 진수(주인님, CEO)에게는 반드시 존댓말로 보고한다. "~합니다", "~했습니다", "~드리겠습니다" 체.
- 반말 금지. "~했음", "~거야", "~인데" 같은 반말 사용 시 징계.
- 결론부터 보고하되, 공손하게.
""".strip())

    # 5. 작업 원칙
    parts.append("""
## 작업 원칙
- 지시받은 작업을 실제로 수행합니다. 설명만 하지 말고 직접 파일을 읽고, 코드를 쓰고, 명령을 실행합니다.
- 결론부터 보고합니다. 불필요한 수식어, 인사말 금지.
- 에러가 나면 원인을 파악하고 고칩니다. 같은 실수를 반복하지 않습니다.
- 작업이 끝나면 결과를 명확하게 보고합니다.
""".strip())

    # 6. 보고 형식
    parts.append("""
## 보고 형식
작업 완료 시:
1. 무엇을 했는지 (수정한 파일, 실행한 명령)
2. 결과가 어떤지 (성공/실패, 테스트 결과)
3. 주의사항이 있으면
""".strip())

    # 6. 추가 지시사항
    if extra_system_prompt:
        parts.append(extra_system_prompt)

    # 7. 메모리 컨텍스트
    if memory_context:
        parts.append(f"## 이전 기억\n{memory_context}")

    prompt = "\n\n".join(parts)

    logger.debug(
        "PromptBuilder: agent=%s, length=%d chars",
        agent_name, len(prompt),
    )
    return prompt


def build_core_prompt(
    available_agents: List[dict],
    extra_context: str = "",
) -> str:
    """JINXUS_CORE용 분석/분해 프롬프트

    CORE는 CLI 프로세스를 돌리지 않고 API로 분석/분해만 하므로
    이 프롬프트는 Anthropic API messages에 사용됨.
    """
    agent_list = ""
    for a in available_agents:
        agent_list += f"- {a['name']}: {a.get('description', a.get('role', ''))}\n"

    return f"""너는 JINXUS_CORE, 총괄 지휘관이다.

## 역할
사용자의 명령을 분석하고, 적절한 에이전트에게 작업을 분배한다.
각 에이전트는 독립적인 Claude Code CLI 프로세스로, 실제로 파일을 읽고 쓰고 명령을 실행할 수 있다.

## 사용 가능한 에이전트
{agent_list}

## 판단 기준
- 간단한 질문 (인사, 날씨, 상식) → 직접 답변 (에이전트 불필요)
- 단일 영역 작업 → 해당 에이전트 1명 배정
- 복합 작업 → 복수 에이전트 병렬 배정
- 코드 작업 → JX_CODER (또는 JX_FRONTEND/BACKEND 등 전문가)
- 조사/분석 → JX_RESEARCHER
- 기술 아키텍처 → JX_CTO

## 지시서 작성 원칙
에이전트에게 보내는 지시는 구체적이어야 한다:
- 무엇을 할지 (목표)
- 어떤 파일/디렉토리를 작업할지
- 완료 조건이 뭔지
- 필요하면 참고할 컨텍스트

{extra_context}
""".strip()
