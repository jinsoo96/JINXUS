"""구조화된 완료 신호 파싱 모듈

에이전트 응답에서 구조화된 완료 신호를 감지하고 파싱한다.

지원 패턴:
- [TASK_COMPLETE] — 작업 정상 완료
- [BLOCKED: detail] — 작업 차단 (권한, 의존성 등)
- [ERROR: detail] — 에러 발생
- [CONTINUE: detail] — 작업 계속 필요 (추가 지시 요청)
"""
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# 완료 신호 타입
SIGNAL_COMPLETE = "complete"
SIGNAL_BLOCKED = "blocked"
SIGNAL_ERROR = "error"
SIGNAL_CONTINUE = "continue"


@dataclass
class CompletionSignal:
    """구조화된 완료 신호"""
    type: str                    # complete / blocked / error / continue
    detail: str = ""             # 상세 사유 (BLOCKED, ERROR, CONTINUE에서 사용)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# Guard-Post 완료 시그널 패턴
_COMPLETION_PATTERNS = [
    (re.compile(r'\[TASK_COMPLETE\]', re.IGNORECASE), SIGNAL_COMPLETE),
    (re.compile(r'\[BLOCKED:\s*(.+?)\]', re.IGNORECASE), SIGNAL_BLOCKED),
    (re.compile(r'\[ERROR:\s*(.+?)\]', re.IGNORECASE), SIGNAL_ERROR),
    (re.compile(r'\[CONTINUE:\s*(.+?)\]', re.IGNORECASE), SIGNAL_CONTINUE),
]


def parse_completion_signal(text: str) -> Optional[CompletionSignal]:
    """텍스트에서 완료 신호를 파싱한다.

    Args:
        text: 에이전트 응답 텍스트

    Returns:
        CompletionSignal if found, None otherwise
    """
    if not text:
        return None

    for pattern, signal_type in _COMPLETION_PATTERNS:
        m = pattern.search(text)
        if m:
            detail = m.group(1) if m.lastindex else ""
            return CompletionSignal(type=signal_type, detail=detail)

    return None


def strip_signal_from_text(text: str) -> str:
    """텍스트에서 완료 신호 태그를 제거한다.

    Args:
        text: 원본 텍스트

    Returns:
        신호 태그가 제거된 텍스트
    """
    if not text:
        return ""

    cleaned = text
    for pattern, _ in _COMPLETION_PATTERNS:
        cleaned = pattern.sub('', cleaned)
    return cleaned.strip()


def is_failure_signal(signal: CompletionSignal) -> bool:
    """실패 계열 신호인지 판별"""
    return signal.type in (SIGNAL_BLOCKED, SIGNAL_ERROR)


def is_actionable_signal(signal: CompletionSignal) -> bool:
    """후속 조치가 필요한 신호인지 판별 (blocked, error, continue)"""
    return signal.type in (SIGNAL_BLOCKED, SIGNAL_ERROR, SIGNAL_CONTINUE)
