"""모델 라우팅 및 폴백 시스템 — 비용 최적화 + 고가용성

Geny 참고: 에러 분류 + 복구 가능성 판단 + 폴백 체인 + 재시도 전략

복잡한 작업 → opus
단순한 작업 → sonnet (비용 절감)
에러 발생 시 → 폴백 모델로 자동 전환
"""
import logging
import re
from enum import Enum
from typing import Optional

from jinxus.config import get_settings

logger = logging.getLogger(__name__)


def _get_quality_critical_agents() -> set[str]:
    """settings에서 품질 중요 에이전트 목록 로드"""
    return set(get_settings().quality_critical_agents)


def _get_complex_keywords() -> list[str]:
    """settings에서 복잡도 키워드 목록 로드"""
    return get_settings().complex_keywords


class FailureReason(Enum):
    """실패 원인 분류 (Geny 패턴)"""
    RATE_LIMITED = "rate_limited"       # API 속도 제한
    OVERLOADED = "overloaded"           # 서버 과부하
    TIMEOUT = "timeout"                 # 타임아웃
    CONTEXT_WINDOW = "context_window"   # 컨텍스트 윈도우 초과
    AUTH_ERROR = "auth_error"           # 인증 오류
    NETWORK_ERROR = "network_error"     # 네트워크 오류
    UNKNOWN = "unknown"                 # 알 수 없는 오류
    ABORT = "abort"                     # 사용자 취소


# 에러 메시지 패턴 → FailureReason 매핑
ERROR_PATTERNS = {
    FailureReason.RATE_LIMITED: [
        r"rate.?limit",
        r"too.?many.?requests",
        r"429",
    ],
    FailureReason.OVERLOADED: [
        r"overload",
        r"server.?busy",
        r"503",
        r"502",
    ],
    FailureReason.TIMEOUT: [
        r"timeout",
        r"timed.?out",
        r"deadline.?exceeded",
    ],
    FailureReason.CONTEXT_WINDOW: [
        r"context.?window",
        r"max.?tokens",
        r"too.?long",
    ],
    FailureReason.AUTH_ERROR: [
        r"auth",
        r"api.?key",
        r"401",
        r"403",
    ],
    FailureReason.NETWORK_ERROR: [
        r"connection",
        r"network",
        r"dns",
    ],
}

# 복구 가능한 에러 (폴백 시도)
RECOVERABLE_ERRORS = {
    FailureReason.RATE_LIMITED,
    FailureReason.OVERLOADED,
    FailureReason.TIMEOUT,
    FailureReason.NETWORK_ERROR,
}

# 에러 유형별 대기 시간 (초)
RETRY_DELAYS = {
    FailureReason.RATE_LIMITED: 5.0,
    FailureReason.OVERLOADED: 3.0,
    FailureReason.TIMEOUT: 2.0,
    FailureReason.NETWORK_ERROR: 2.0,
    FailureReason.UNKNOWN: 1.0,
}


def classify_error(error_message: str) -> FailureReason:
    """에러 메시지를 FailureReason으로 분류"""
    error_lower = error_message.lower()

    for reason, patterns in ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, error_lower):
                return reason

    return FailureReason.UNKNOWN


def is_recoverable(reason: FailureReason) -> bool:
    """복구 가능한 에러인지 판단"""
    return reason in RECOVERABLE_ERRORS


# ModelFallbackRunner, ModelExhaustedError, FallbackResult는
# model_fallback.py로 이전됨. 하위 호환을 위해 re-export.
from jinxus.core.model_fallback import (  # noqa: F401
    ModelFallbackRunner,
    ModelExhaustedError,
    FallbackResult,
    get_model_fallback_runner as get_fallback_runner,
)


# === 기존 호환 함수들 ===

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
    if agent_name in _get_quality_critical_agents():
        return settings.claude_model

    # 2. 복잡한 키워드가 있으면 → 메인 모델
    instruction_lower = instruction.lower()
    if any(kw in instruction_lower for kw in _get_complex_keywords()):
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
    if len(user_input) < 50 and not any(kw in user_input.lower() for kw in _get_complex_keywords()):
        # 인사, 간단한 질문 등
        if any(p in user_input.lower() for p in settings.simple_patterns):
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
