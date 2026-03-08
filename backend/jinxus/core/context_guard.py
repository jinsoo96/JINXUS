"""컨텍스트 윈도우 관리 — 토큰 폭탄 방지

Geny 참고: 토큰 추정 + 3단계 모니터링 + 컴팩션 전략

에이전트 output이 너무 길면 aggregate 시 컨텍스트 한도 초과 또는 과도한 과금 발생.
이 모듈로 토큰 사용량을 모니터링하고 필요시 컴팩션을 수행한다.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional

# 모델별 컨텍스트 윈도우 (토큰)
MODEL_CONTEXT_LIMITS = {
    "claude-opus-4-5-20251101": 200000,
    "claude-sonnet-4-20250514": 200000,
    "claude-3-5-sonnet-latest": 200000,
    "default": 100000,
}

# 토큰 추정 상수 (보수적)
CHARS_PER_TOKEN_EN = 4  # 영어: 약 4자/토큰
CHARS_PER_TOKEN_KO = 3  # 한국어: 약 2-3자/토큰 (보수적으로 3)

# 기본 제한
MAX_OUTPUT_CHARS = 4000   # 에이전트 output 최대 길이
MAX_CONTEXT_CHARS = 8000  # aggregate로 넘기는 최대 전체 길이


class BudgetStatus(Enum):
    """컨텍스트 예산 상태"""
    OK = "ok"              # 정상 (< 75%)
    WARN = "warn"          # 경고 (75% ~ 90%)
    BLOCK = "block"        # 차단 필요 (>= 90%)
    OVERFLOW = "overflow"  # 초과 (>= 100%)


class CompactionStrategy(Enum):
    """컴팩션 전략"""
    KEEP_RECENT = "keep_recent"        # 최근 N개 메시지만 유지
    TRUNCATE_EARLY = "truncate_early"  # 초기 메시지 제거
    REMOVE_TOOL_DETAILS = "remove_tool_details"  # 도구 호출 상세 축소


@dataclass
class BudgetCheck:
    """예산 체크 결과"""
    status: BudgetStatus
    used_tokens: int
    max_tokens: int
    usage_percent: float
    should_compact: bool
    recommended_strategy: Optional[CompactionStrategy] = None


class ContextWindowGuard:
    """컨텍스트 윈도우 가드 (Geny 패턴)

    토큰 사용량을 추정하고 3단계 모니터링을 수행한다.
    """

    WARN_THRESHOLD = 0.75   # 75%에서 경고
    BLOCK_THRESHOLD = 0.90  # 90%에서 차단

    def __init__(self, model: str = "default"):
        self.model = model
        self.max_tokens = MODEL_CONTEXT_LIMITS.get(model, MODEL_CONTEXT_LIMITS["default"])

    def estimate_tokens(self, text: str) -> int:
        """텍스트의 토큰 수 추정

        휴리스틱: 영어 4자/토큰, 한국어 3자/토큰으로 보수적 추정
        """
        if not text:
            return 0

        # 한글 비율 계산
        korean_chars = sum(1 for c in text if '\uAC00' <= c <= '\uD7A3')
        total_chars = len(text)

        if total_chars == 0:
            return 0

        korean_ratio = korean_chars / total_chars

        # 가중 평균
        avg_chars_per_token = (
            CHARS_PER_TOKEN_KO * korean_ratio +
            CHARS_PER_TOKEN_EN * (1 - korean_ratio)
        )

        return int(total_chars / avg_chars_per_token)

    def estimate_messages_tokens(self, messages: list[dict]) -> int:
        """메시지 리스트의 토큰 수 추정"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                # 멀티파트 메시지
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.estimate_tokens(part["text"])
        return total

    def check(self, messages: list[dict]) -> BudgetCheck:
        """현재 메시지의 토큰 예산 상태 확인"""
        used_tokens = self.estimate_messages_tokens(messages)
        usage_percent = used_tokens / self.max_tokens

        if usage_percent >= 1.0:
            status = BudgetStatus.OVERFLOW
            should_compact = True
            strategy = CompactionStrategy.TRUNCATE_EARLY
        elif usage_percent >= self.BLOCK_THRESHOLD:
            status = BudgetStatus.BLOCK
            should_compact = True
            strategy = CompactionStrategy.KEEP_RECENT
        elif usage_percent >= self.WARN_THRESHOLD:
            status = BudgetStatus.WARN
            should_compact = False
            strategy = CompactionStrategy.REMOVE_TOOL_DETAILS
        else:
            status = BudgetStatus.OK
            should_compact = False
            strategy = None

        return BudgetCheck(
            status=status,
            used_tokens=used_tokens,
            max_tokens=self.max_tokens,
            usage_percent=usage_percent * 100,
            should_compact=should_compact,
            recommended_strategy=strategy,
        )

    def should_block(self, messages: list[dict]) -> bool:
        """새 메시지 거부 필요 여부 (check() 결과로 판단)"""
        result = self.check(messages)
        return result.status in (BudgetStatus.BLOCK, BudgetStatus.OVERFLOW)

    def compact(
        self,
        messages: list[dict],
        strategy: CompactionStrategy = CompactionStrategy.KEEP_RECENT,
        keep_count: int = 10,
    ) -> list[dict]:
        """메시지 컴팩션 수행

        Args:
            messages: 원본 메시지 리스트
            strategy: 컴팩션 전략
            keep_count: KEEP_RECENT 전략 시 유지할 메시지 수

        Returns:
            컴팩션된 메시지 리스트
        """
        if not messages:
            return []

        if strategy == CompactionStrategy.KEEP_RECENT:
            # 최근 N개만 유지
            return messages[-keep_count:]

        elif strategy == CompactionStrategy.TRUNCATE_EARLY:
            # 앞부분 제거 (시스템 메시지 제외)
            system_msgs = [m for m in messages if m.get("role") == "system"]
            other_msgs = [m for m in messages if m.get("role") != "system"]

            # 후반 60% 유지
            keep_from = len(other_msgs) * 4 // 10
            return system_msgs + other_msgs[keep_from:]

        elif strategy == CompactionStrategy.REMOVE_TOOL_DETAILS:
            # 도구 호출 결과 축소
            compacted = []
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 1000:
                    # 긴 컨텐츠 축소
                    compacted.append({
                        **msg,
                        "content": content[:500] + "\n...[축소됨]...\n" + content[-200:],
                    })
                else:
                    compacted.append(msg)
            return compacted

        return messages

    def check_and_compact(
        self,
        messages: list[dict],
        auto_compact: bool = True,
    ) -> tuple[list[dict], BudgetCheck]:
        """검사 + 필요시 컴팩션 통합 처리

        Args:
            messages: 메시지 리스트
            auto_compact: 자동 컴팩션 여부

        Returns:
            (컴팩션된 메시지, 예산 체크 결과) 튜플
        """
        check_result = self.check(messages)

        if check_result.should_compact and auto_compact and check_result.recommended_strategy:
            compacted = self.compact(messages, check_result.recommended_strategy)
            return compacted, check_result

        return messages, check_result


# 전역 가드 인스턴스
_guard: Optional[ContextWindowGuard] = None


def get_context_guard(model: str = "default") -> ContextWindowGuard:
    """전역 ContextWindowGuard 인스턴스 반환"""
    global _guard
    if _guard is None or _guard.model != model:
        _guard = ContextWindowGuard(model)
    return _guard


# === 기존 호환 함수들 (하위 호환성 유지) ===

def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """에이전트 output 길이 제한

    Args:
        output: 원본 출력
        max_chars: 최대 글자 수

    Returns:
        잘린 출력 (중간 생략 표시 포함)
    """
    if not output:
        return ""

    if len(output) <= max_chars:
        return output

    half = max_chars // 2
    omitted = len(output) - max_chars
    return (
        output[:half]
        + f"\n\n... [중간 {omitted}자 생략] ...\n\n"
        + output[-half:]
    )


def guard_results(results: list[dict]) -> list[dict]:
    """aggregate 전에 각 에이전트 output 자르기

    Args:
        results: 에이전트 실행 결과 리스트

    Returns:
        output이 잘린 결과 리스트
    """
    guarded = []
    for r in results:
        guarded.append({
            **r,
            "output": truncate_output(r.get("output", "")),
        })
    return guarded


def guard_context(context: list[dict], max_chars: int = MAX_CONTEXT_CHARS) -> list[dict]:
    """순차 실행 시 컨텍스트 크기 제한

    Args:
        context: 이전 작업 결과 컨텍스트
        max_chars: 전체 컨텍스트 최대 크기

    Returns:
        크기 제한된 컨텍스트
    """
    if not context:
        return []

    total_chars = sum(len(c.get("summary", "")) for c in context)

    if total_chars <= max_chars:
        return context

    # 최신 것부터 유지하면서 크기 제한
    guarded = []
    current_chars = 0

    for c in reversed(context):
        summary = c.get("summary", "")
        if current_chars + len(summary) <= max_chars:
            guarded.insert(0, c)
            current_chars += len(summary)
        else:
            # 마지막 항목은 잘라서라도 포함
            remaining = max_chars - current_chars
            if remaining > 100:
                guarded.insert(0, {
                    **c,
                    "summary": summary[:remaining] + "...(생략)",
                })
            break

    return guarded
