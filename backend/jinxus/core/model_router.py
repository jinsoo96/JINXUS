"""모델 라우팅 및 폴백 시스템 — 비용 최적화 + 고가용성

Geny 참고: 에러 분류 + 복구 가능성 판단 + 폴백 체인 + 재시도 전략

복잡한 작업 → opus
단순한 작업 → sonnet (비용 절감)
에러 발생 시 → 폴백 모델로 자동 전환
"""
import asyncio
import logging
import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable, Any

from jinxus.config import get_settings

logger = logging.getLogger(__name__)


# 품질이 중요한 에이전트 (항상 메인 모델 사용)
QUALITY_CRITICAL_AGENTS = {"JX_WRITER", "JX_ANALYST"}

# 복잡한 작업 키워드 (메인 모델 사용)
COMPLEX_KEYWORDS = [
    "분석", "작성", "설계", "최적화", "자소서",
    "포트폴리오", "보고서", "논문", "리팩토링",
    "아키텍처", "시스템", "전략", "기획",
    "analyze", "design", "optimize", "architecture",
]


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


@dataclass
class FallbackResult:
    """폴백 실행 결과"""
    success: bool
    result: Any
    model_used: str
    attempts: int
    failure_reason: Optional[FailureReason] = None
    error: Optional[str] = None


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


class ModelFallbackRunner:
    """모델 폴백 실행기 (Geny 패턴)

    주 모델 실패 시 폴백 모델로 자동 전환.
    재시도 + 지수 백오프 지원.

    _last_success_model은 클래스 변수로 같은 프로세스 내
    모든 인스턴스(세션)에서 성공 모델 정보를 공유한다.
    """

    # 클래스 레벨: 프로세스 내 세션 간 성공 모델 공유
    _last_success_model: Optional[str] = None

    def __init__(
        self,
        models: list[str] = None,
        max_retries: int = 2,
        on_fallback: Optional[Callable[[str, str, FailureReason], None]] = None,
    ):
        """
        Args:
            models: 시도할 모델 목록 (우선순위 순)
            max_retries: 모델당 최대 재시도 횟수
            on_fallback: 폴백 발생 시 콜백 (from_model, to_model, reason)
        """
        settings = get_settings()
        self.models = models or [
            settings.claude_model,
            settings.claude_fallback_model,
        ]
        self.max_retries = max_retries
        self.on_fallback = on_fallback

    def get_model_priority(self, preferred_model: Optional[str] = None) -> list[str]:
        """우선순위 기반 모델 순서 반환

        1. 마지막 성공 모델 (세션 메모리)
        2. 선호 모델
        3. 나머지 후보군
        """
        priority = []

        # 1. 마지막 성공 모델 (클래스 변수에서 읽기)
        if ModelFallbackRunner._last_success_model and ModelFallbackRunner._last_success_model in self.models:
            priority.append(ModelFallbackRunner._last_success_model)

        # 2. 선호 모델
        if preferred_model and preferred_model in self.models:
            if preferred_model not in priority:
                priority.append(preferred_model)

        # 3. 나머지
        for model in self.models:
            if model not in priority:
                priority.append(model)

        return priority

    async def run(
        self,
        call_fn: Callable[[str], Any],
        preferred_model: Optional[str] = None,
    ) -> FallbackResult:
        """폴백 지원 실행

        Args:
            call_fn: 모델 ID를 받아 실행하는 함수 (async)
            preferred_model: 선호 모델 (optional)

        Returns:
            FallbackResult
        """
        models = self.get_model_priority(preferred_model)
        total_attempts = 0

        for model in models:
            for attempt in range(self.max_retries):
                total_attempts += 1

                try:
                    result = await call_fn(model)
                    ModelFallbackRunner._last_success_model = model
                    return FallbackResult(
                        success=True,
                        result=result,
                        model_used=model,
                        attempts=total_attempts,
                    )

                except Exception as e:
                    error_msg = str(e)
                    reason = classify_error(error_msg)

                    logger.warning(
                        f"Model {model} failed (attempt {attempt + 1}): {reason.value} - {error_msg[:100]}"
                    )

                    # 복구 불가능한 에러면 다음 모델로
                    if not is_recoverable(reason):
                        break

                    # 재시도 전 대기
                    delay = RETRY_DELAYS.get(reason, 1.0) * (attempt + 1)  # 지수 백오프
                    await asyncio.sleep(delay)

            # 폴백 콜백 호출
            if self.on_fallback and models.index(model) < len(models) - 1:
                next_model = models[models.index(model) + 1]
                self.on_fallback(model, next_model, reason)

        # 모든 모델 실패
        return FallbackResult(
            success=False,
            result=None,
            model_used=models[-1],
            attempts=total_attempts,
            failure_reason=reason,
            error=f"All models exhausted after {total_attempts} attempts",
        )


class ModelExhaustedError(Exception):
    """모든 모델이 실패했을 때 발생"""
    pass


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


# === 폴백 헬퍼 ===

_fallback_runner: Optional[ModelFallbackRunner] = None


def get_fallback_runner() -> ModelFallbackRunner:
    """전역 ModelFallbackRunner 인스턴스 반환"""
    global _fallback_runner
    if _fallback_runner is None:
        _fallback_runner = ModelFallbackRunner()
    return _fallback_runner
