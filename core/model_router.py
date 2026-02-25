"""작업 복잡도에 따른 모델 자동 선택 — 비용 최적화

복잡한 작업 → opus
단순한 작업 → sonnet (비용 절감)
"""
from config import get_settings


# 품질이 중요한 에이전트 (항상 메인 모델 사용)
QUALITY_CRITICAL_AGENTS = {"JX_WRITER", "JX_ANALYST"}

# 복잡한 작업 키워드 (메인 모델 사용)
COMPLEX_KEYWORDS = [
    "분석", "작성", "설계", "최적화", "자소서",
    "포트폴리오", "보고서", "논문", "리팩토링",
    "아키텍처", "시스템", "전략", "기획",
    "analyze", "design", "optimize", "architecture",
]


def select_model(agent_name: str, instruction: str) -> str:
    """에이전트 + 명령 복잡도 기반 모델 선택

    Args:
        agent_name: 에이전트 이름 (JX_CODER, JX_WRITER 등)
        instruction: 작업 지시 내용

    Returns:
        모델 ID (claude_model 또는 claude_fallback_model)
    """
    settings = get_settings()

    # 1. 품질이 중요한 에이전트 → 메인 모델 (opus)
    if agent_name in QUALITY_CRITICAL_AGENTS:
        return settings.claude_model

    # 2. 복잡한 키워드가 있으면 → 메인 모델
    instruction_lower = instruction.lower()
    if any(kw in instruction_lower for kw in COMPLEX_KEYWORDS):
        return settings.claude_model

    # 3. 긴 명령 → 메인 모델 (복잡할 가능성 높음)
    if len(instruction) > 200:
        return settings.claude_model

    # 4. 짧고 단순한 명령 → 폴백 모델 (sonnet, 비용 절감)
    return settings.claude_fallback_model


def select_model_for_core(user_input: str) -> str:
    """JINXUS_CORE용 모델 선택

    decompose, aggregate 등 핵심 작업용.

    Args:
        user_input: 사용자 입력

    Returns:
        모델 ID
    """
    settings = get_settings()

    # CORE는 대부분 메인 모델 사용 (정확한 분해가 중요)
    # 아주 짧은 간단한 대화만 폴백 사용
    if len(user_input) < 50 and not any(kw in user_input.lower() for kw in COMPLEX_KEYWORDS):
        # 인사, 간단한 질문 등
        simple_patterns = ["안녕", "뭐해", "hi", "hello", "네", "응", "ㅇㅇ", "고마워", "감사"]
        if any(p in user_input.lower() for p in simple_patterns):
            return settings.claude_fallback_model

    return settings.claude_model


def get_model_info(model_id: str) -> dict:
    """모델 정보 반환 (디버깅/로깅용)"""
    settings = get_settings()

    is_main = model_id == settings.claude_model

    return {
        "model_id": model_id,
        "is_main_model": is_main,
        "tier": "primary" if is_main else "fallback",
    }
