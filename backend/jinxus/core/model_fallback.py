"""ModelFallbackRunner — API 에러 시 자동 모델 전환 시스템

Geny 패턴 참고. 기존 model_router.py의 ModelFallbackRunner를 확장하여
에러 유형별 차등 대기, 인증 실패 시 후보 제거, ModelExhaustedError 발생을 지원.

사용:
    runner = ModelFallbackRunner()
    result = await runner.run(async_call_fn)
    # result.model_used → 최종 사용된 모델

    # 또는 예외 발생 모드:
    result = await runner.run_or_raise(async_call_fn)

연동:
    - process_manager.py: ClaudeProcess.execute() 시 모델 파라미터 결정
    - agent_executor.py: Anthropic API 직접 호출 시 모델 선택
    - settings.py: claude_model, claude_fallback_model, claude_fast_model
"""
import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from jinxus.config import get_settings

logger = logging.getLogger(__name__)


# ============================================================================
# Error classification
# ============================================================================

class ErrorType(Enum):
    """API 에러 유형 분류"""
    RATE_LIMIT = "rate_limit"           # 429 Too Many Requests
    OVERLOADED = "overloaded"           # 529 Overloaded / 503
    AUTHENTICATION = "authentication"   # 401/403 인증 실패
    TIMEOUT = "timeout"                 # 요청 타임아웃
    CONTEXT_OVERFLOW = "context_overflow"  # 컨텍스트 윈도우 초과
    NETWORK = "network"                 # 네트워크 오류
    UNKNOWN = "unknown"                 # 분류 불가


# 에러 메시지 패턴 → ErrorType 매핑
_ERROR_PATTERNS: Dict[ErrorType, List[str]] = {
    ErrorType.RATE_LIMIT: [
        r"rate.?limit",
        r"too.?many.?requests",
        r"429",
        r"RateLimitError",
    ],
    ErrorType.OVERLOADED: [
        r"overload",
        r"server.?busy",
        r"503",
        r"502",
        r"529",
        r"OverloadedError",
    ],
    ErrorType.AUTHENTICATION: [
        r"auth",
        r"api.?key",
        r"401",
        r"403",
        r"invalid.*key",
        r"AuthenticationError",
        r"PermissionError",
    ],
    ErrorType.TIMEOUT: [
        r"timeout",
        r"timed.?out",
        r"deadline.?exceeded",
        r"TimeoutError",
    ],
    ErrorType.CONTEXT_OVERFLOW: [
        r"context.?window",
        r"max.?tokens",
        r"too.?long",
        r"context_length_exceeded",
    ],
    ErrorType.NETWORK: [
        r"connection",
        r"network",
        r"dns",
        r"ECONNREFUSED",
    ],
}

# 에러 유형별 대기 시간 (초)
_WAIT_SECONDS: Dict[ErrorType, float] = {
    ErrorType.RATE_LIMIT: 30.0,
    ErrorType.OVERLOADED: 60.0,
    ErrorType.AUTHENTICATION: 0.0,    # 즉시 다음 모델 (이 모델은 제거)
    ErrorType.TIMEOUT: 10.0,
    ErrorType.CONTEXT_OVERFLOW: 0.0,   # 즉시 다음 모델 (재시도 의미 없음)
    ErrorType.NETWORK: 5.0,
    ErrorType.UNKNOWN: 5.0,
}

# 재시도 가능한 에러 유형 (같은 모델로 retry)
_RETRYABLE: set[ErrorType] = {
    ErrorType.RATE_LIMIT,
    ErrorType.OVERLOADED,
    ErrorType.TIMEOUT,
    ErrorType.NETWORK,
    ErrorType.UNKNOWN,
}


def classify_error(error: Exception) -> ErrorType:
    """예외 객체 또는 에러 메시지로 ErrorType 분류

    Anthropic SDK 예외 클래스명도 체크한다.
    """
    # 클래스명 기반 빠른 매칭
    class_name = type(error).__name__
    class_map = {
        "RateLimitError": ErrorType.RATE_LIMIT,
        "OverloadedError": ErrorType.OVERLOADED,
        "AuthenticationError": ErrorType.AUTHENTICATION,
        "PermissionDeniedError": ErrorType.AUTHENTICATION,
        "APITimeoutError": ErrorType.TIMEOUT,
        "APIConnectionError": ErrorType.NETWORK,
    }
    if class_name in class_map:
        return class_map[class_name]

    # 메시지 패턴 매칭
    error_str = str(error).lower()
    for error_type, patterns in _ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, error_str, re.IGNORECASE):
                return error_type

    return ErrorType.UNKNOWN


# ============================================================================
# Exceptions
# ============================================================================

class ModelExhaustedError(Exception):
    """모든 모델 후보가 소진되었을 때 발생

    Attributes:
        attempts: 총 시도 횟수
        last_error: 마지막 에러
        failed_models: 실패한 모델 목록과 에러 정보
    """
    def __init__(
        self,
        message: str,
        attempts: int = 0,
        last_error: Optional[Exception] = None,
        failed_models: Optional[List[dict]] = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error
        self.failed_models = failed_models or []


# ============================================================================
# Result
# ============================================================================

@dataclass
class FallbackResult:
    """폴백 실행 결과"""
    success: bool
    result: Any
    model_used: str
    attempts: int
    total_wait_seconds: float = 0.0
    error_type: Optional[ErrorType] = None
    error: Optional[str] = None
    failed_models: List[dict] = field(default_factory=list)


# ============================================================================
# ModelFallbackRunner
# ============================================================================

class ModelFallbackRunner:
    """API 에러 시 자동 모델 전환 실행기

    특징:
    - 마지막 성공 모델 기억 (클래스 변수, 프로세스 내 공유)
    - 에러 유형별 차등 대기 시간
    - AuthenticationError 시 해당 모델 영구 제거
    - 모든 후보 소진 시 ModelExhaustedError 발생 (run_or_raise)

    사용 예시:
        runner = ModelFallbackRunner()

        # 방법 1: FallbackResult 반환
        result = await runner.run(lambda model: call_api(model, prompt))
        if result.success:
            print(result.result)

        # 방법 2: 실패 시 예외 발생
        result = await runner.run_or_raise(lambda model: call_api(model, prompt))
    """

    # 클래스 레벨: 마지막 성공 모델 기억 (프로세스 내 전역)
    _last_success_model: Optional[str] = None

    # 클래스 레벨: 인증 실패로 제거된 모델 (프로세스 내 전역)
    _blacklisted_models: set[str] = set()

    def __init__(
        self,
        models: Optional[List[str]] = None,
        max_retries_per_model: int = 2,
        on_fallback: Optional[Callable[[str, str, ErrorType], None]] = None,
    ):
        """
        Args:
            models: 모델 후보 목록 (우선순위 순). None이면 settings에서 로드.
            max_retries_per_model: 모델당 최대 재시도 횟수 (같은 모델 retry)
            on_fallback: 폴백 발생 시 콜백 (from_model, to_model, error_type)
        """
        if models is not None:
            self.models = list(models)
        else:
            settings = get_settings()
            self.models = [
                settings.claude_model,               # 기본 (sonnet)
                settings.claude_fallback_model,       # 대체
                settings.claude_fast_model,           # 최후 수단 (haiku)
            ]
            # 중복 제거 (순서 유지)
            seen = set()
            deduped = []
            for m in self.models:
                if m not in seen:
                    seen.add(m)
                    deduped.append(m)
            self.models = deduped

        self.max_retries_per_model = max_retries_per_model
        self.on_fallback = on_fallback

    def add_model(self, model: str, position: Optional[int] = None) -> None:
        """모델 후보 동적 추가

        Args:
            model: 추가할 모델 ID
            position: 삽입 위치 (None이면 맨 뒤)
        """
        if model in self.models:
            return
        if model in ModelFallbackRunner._blacklisted_models:
            logger.warning("모델 %s는 블랙리스트에 있어 추가 불가", model)
            return
        if position is not None:
            self.models.insert(position, model)
        else:
            self.models.append(model)
        logger.info("모델 후보 추가: %s (position=%s)", model, position)

    def remove_model(self, model: str) -> bool:
        """모델 후보 동적 제거

        Returns:
            제거 성공 여부
        """
        if model in self.models:
            self.models.remove(model)
            logger.info("모델 후보 제거: %s", model)
            return True
        return False

    def get_available_models(self) -> List[str]:
        """블랙리스트 제외한 사용 가능 모델 목록"""
        return [m for m in self.models if m not in ModelFallbackRunner._blacklisted_models]

    def _get_model_priority(self, preferred_model: Optional[str] = None) -> List[str]:
        """우선순위 기반 모델 순서 반환

        1. 마지막 성공 모델
        2. 선호 모델
        3. 나머지 후보군
        (블랙리스트 모델 제외)
        """
        available = self.get_available_models()
        if not available:
            return []

        priority: List[str] = []

        # 1. 마지막 성공 모델
        last = ModelFallbackRunner._last_success_model
        if last and last in available:
            priority.append(last)

        # 2. 선호 모델
        if preferred_model and preferred_model in available and preferred_model not in priority:
            priority.append(preferred_model)

        # 3. 나머지
        for model in available:
            if model not in priority:
                priority.append(model)

        return priority

    async def run(
        self,
        call_fn: Callable[[str], Any],
        preferred_model: Optional[str] = None,
    ) -> FallbackResult:
        """폴백 지원 실행

        모든 모델이 실패해도 예외를 발생시키지 않고 FallbackResult를 반환.
        예외 발생이 필요하면 run_or_raise()를 사용.

        Args:
            call_fn: 모델 ID를 받아 실행하는 async 함수. 실패 시 예외 발생.
            preferred_model: 선호 모델 (optional)

        Returns:
            FallbackResult
        """
        models = self._get_model_priority(preferred_model)
        if not models:
            return FallbackResult(
                success=False,
                result=None,
                model_used="",
                attempts=0,
                error_type=ErrorType.AUTHENTICATION,
                error="No available models (all blacklisted)",
                failed_models=[],
            )

        total_attempts = 0
        total_wait = 0.0
        failed_models: List[dict] = []
        last_error_type = ErrorType.UNKNOWN

        for i, model in enumerate(models):
            for attempt in range(self.max_retries_per_model):
                total_attempts += 1

                try:
                    result = await call_fn(model)

                    # 성공: 마지막 성공 모델 기억
                    ModelFallbackRunner._last_success_model = model
                    return FallbackResult(
                        success=True,
                        result=result,
                        model_used=model,
                        attempts=total_attempts,
                        total_wait_seconds=total_wait,
                        failed_models=failed_models,
                    )

                except Exception as e:
                    error_type = classify_error(e)
                    last_error_type = error_type
                    error_msg = str(e)

                    logger.warning(
                        "[ModelFallback] %s 실패 (시도 %d/%d): %s - %s",
                        model, attempt + 1, self.max_retries_per_model,
                        error_type.value, error_msg[:200],
                    )

                    # AuthenticationError → 즉시 블랙리스트 + 다음 모델
                    if error_type == ErrorType.AUTHENTICATION:
                        ModelFallbackRunner._blacklisted_models.add(model)
                        logger.error(
                            "[ModelFallback] %s 인증 실패 → 블랙리스트 추가", model,
                        )
                        failed_models.append({
                            "model": model,
                            "error_type": error_type.value,
                            "error": error_msg[:500],
                            "blacklisted": True,
                        })
                        break  # 이 모델에서 재시도 안 함

                    # ContextOverflow → 재시도 의미 없음, 다음 모델
                    if error_type == ErrorType.CONTEXT_OVERFLOW:
                        failed_models.append({
                            "model": model,
                            "error_type": error_type.value,
                            "error": error_msg[:500],
                        })
                        break

                    # 재시도 가능하고 아직 재시도 횟수 남음 → 대기 후 재시도
                    if error_type in _RETRYABLE and attempt < self.max_retries_per_model - 1:
                        wait = _WAIT_SECONDS.get(error_type, 5.0)
                        logger.info(
                            "[ModelFallback] %s %.0f초 대기 후 재시도...",
                            model, wait,
                        )
                        await asyncio.sleep(wait)
                        total_wait += wait
                        continue

                    # 재시도 소진 → 다음 모델로
                    failed_models.append({
                        "model": model,
                        "error_type": error_type.value,
                        "error": error_msg[:500],
                    })
                    break

            # 폴백 콜백
            if self.on_fallback and i < len(models) - 1:
                next_model = models[i + 1]
                try:
                    self.on_fallback(model, next_model, last_error_type)
                except Exception as cb_err:
                    logger.warning(
                        "[ModelFallback] 폴백 콜백 에러: %s", cb_err,
                    )

        # 모든 모델 소진
        return FallbackResult(
            success=False,
            result=None,
            model_used=models[-1] if models else "",
            attempts=total_attempts,
            total_wait_seconds=total_wait,
            error_type=last_error_type,
            error=f"모든 모델 소진 (총 {total_attempts}회 시도, {total_wait:.0f}초 대기)",
            failed_models=failed_models,
        )

    async def run_or_raise(
        self,
        call_fn: Callable[[str], Any],
        preferred_model: Optional[str] = None,
    ) -> FallbackResult:
        """폴백 지원 실행 — 모든 모델 실패 시 ModelExhaustedError 발생

        Args:
            call_fn: 모델 ID를 받아 실행하는 async 함수
            preferred_model: 선호 모델 (optional)

        Returns:
            FallbackResult (성공 시)

        Raises:
            ModelExhaustedError: 모든 모델이 실패했을 때
        """
        result = await self.run(call_fn, preferred_model)

        if not result.success:
            raise ModelExhaustedError(
                message=result.error or "All models exhausted",
                attempts=result.attempts,
                failed_models=result.failed_models,
            )

        return result

    @classmethod
    def reset_blacklist(cls) -> List[str]:
        """블랙리스트 초기화 (수동 복구용)

        Returns:
            초기화 전 블랙리스트에 있던 모델 목록
        """
        removed = list(cls._blacklisted_models)
        cls._blacklisted_models.clear()
        if removed:
            logger.info("[ModelFallback] 블랙리스트 초기화: %s", removed)
        return removed

    @classmethod
    def reset_last_success(cls) -> Optional[str]:
        """마지막 성공 모델 초기화

        Returns:
            초기화 전 마지막 성공 모델
        """
        prev = cls._last_success_model
        cls._last_success_model = None
        return prev


# ============================================================================
# Singleton
# ============================================================================

_fallback_runner: Optional[ModelFallbackRunner] = None


def get_model_fallback_runner(
    models: Optional[List[str]] = None,
) -> ModelFallbackRunner:
    """전역 ModelFallbackRunner 인스턴스 반환

    처음 호출 시 생성, 이후 동일 인스턴스 반환.
    models를 지정하면 새 인스턴스로 교체.
    """
    global _fallback_runner
    if _fallback_runner is None or models is not None:
        _fallback_runner = ModelFallbackRunner(models=models)
    return _fallback_runner
