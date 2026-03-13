"""MCP 도구 어노테이션 및 의도-어노테이션 정렬 점수 (graph-tool-call 패턴 적용)

도구의 행동 특성(읽기 전용, 파괴적, 멱등 등)을 어노테이션으로 표현하고,
쿼리 의도와 도구 어노테이션의 정렬 정도를 점수화한다.

이 모듈은 ToolGraph.retrieve() 에서 추가 점수 소스로 활용된다.

참고: https://github.com/SonAIengine/graph-tool-call (core/tool.py, retrieval/annotation_scorer.py)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from jinxus.core.tool_intent import QueryIntent


# ─── MCP 어노테이션 ──────────────────────────────────

@dataclass
class ToolAnnotations:
    """도구 행동 어노테이션 (MCP spec 호환).

    도구의 행동 특성을 메타데이터로 표현:
    - read_only_hint: True이면 데이터를 변경하지 않음 (안전한 도구)
    - destructive_hint: True이면 복구 불가능한 변경을 수행 (삭제, 덮어쓰기 등)
    - idempotent_hint: True이면 동일 입력에 대해 항상 동일 결과 (여러 번 실행해도 안전)
    - open_world_hint: True이면 외부 세계(인터넷, 파일시스템 등)에 접근

    None은 해당 특성을 알 수 없음을 의미.
    """
    read_only_hint: Optional[bool] = None
    destructive_hint: Optional[bool] = None
    idempotent_hint: Optional[bool] = None
    open_world_hint: Optional[bool] = None

    def to_dict(self) -> dict:
        """어노테이션을 dict로 직렬화 (None 값 제외)."""
        return {
            k: v for k, v in {
                "read_only_hint": self.read_only_hint,
                "destructive_hint": self.destructive_hint,
                "idempotent_hint": self.idempotent_hint,
                "open_world_hint": self.open_world_hint,
            }.items()
            if v is not None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolAnnotations":
        """dict에서 어노테이션 파싱 (camelCase 또는 snake_case 지원)."""
        # camelCase → snake_case 매핑
        camel_map = {
            "readOnlyHint": "read_only_hint",
            "destructiveHint": "destructive_hint",
            "idempotentHint": "idempotent_hint",
            "openWorldHint": "open_world_hint",
        }
        kwargs = {}
        for camel, snake in camel_map.items():
            if camel in data:
                kwargs[snake] = data[camel]
            elif snake in data:
                kwargs[snake] = data[snake]
        return cls(**kwargs)


# ─── 동사 기반 자동 어노테이션 ─────────────────────────

# 읽기 전용 동사 (read_only=True, idempotent=True)
_READ_VERBS = frozenset({
    "get", "list", "fetch", "read", "search", "find", "show",
    "check", "verify", "validate", "view", "browse", "inspect",
    "describe", "display",
})

# 생성 동사 (read_only=False, idempotent=False)
_CREATE_VERBS = frozenset({
    "create", "add", "post", "send", "submit", "register",
    "insert", "append", "push",
})

# 수정 동사 (read_only=False, idempotent=True)
_UPDATE_VERBS = frozenset({
    "update", "modify", "edit", "set", "put", "patch",
    "configure", "enable", "disable", "change",
})

# 저장 동사 (read_only=False, idempotent=True)
_SAVE_VERBS = frozenset({
    "save", "upload", "write", "load", "export", "import",
})

# 삭제 동사 (read_only=False, destructive=True, idempotent=True)
_DELETE_VERBS = frozenset({
    "delete", "remove", "destroy", "drop", "purge", "erase",
    "unregister", "revoke", "terminate", "clear",
})

# 실행 동사 (read_only=False, idempotent=False)
_EXECUTE_VERBS = frozenset({
    "run", "execute", "start", "launch", "deploy", "build",
    "trigger", "invoke", "call", "process", "handle",
})

# 중단 동사 (read_only=False, idempotent=True)
_STOP_VERBS = frozenset({
    "stop", "cancel", "close", "open", "init",
})


def infer_annotations_from_name(tool_name: str) -> Optional[ToolAnnotations]:
    """도구 이름의 첫 번째 동사에서 어노테이션 추론.

    Examples:
        "get_user" → read_only=True, idempotent=True
        "delete_file" → destructive=True
        "create_pr" → read_only=False, idempotent=False
        "run_test" → read_only=False, idempotent=False

    Returns:
        ToolAnnotations 또는 None (동사를 인식할 수 없는 경우)
    """
    # camelCase, snake_case 분리 후 첫 토큰 추출
    normalized = re.sub(r"([a-z])([A-Z])", r"\1_\2", tool_name).lower()
    normalized = normalized.replace("-", "_").replace(":", "_")
    tokens = [t for t in normalized.split("_") if t]

    if not tokens:
        return None

    verb = tokens[0]

    if verb in _READ_VERBS:
        return ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
        )
    elif verb in _DELETE_VERBS:
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=True,
            idempotent_hint=True,
        )
    elif verb in _CREATE_VERBS:
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
        )
    elif verb in _UPDATE_VERBS or verb in _SAVE_VERBS:
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
        )
    elif verb in _EXECUTE_VERBS:
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=True,
        )
    elif verb in _STOP_VERBS:
        return ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
        )

    return None


# ─── 의도-어노테이션 정렬 점수 ──────────────────────────

_NEUTRAL_SCORE = 0.5


def score_annotation_match(
    intent: QueryIntent,
    annotations: Optional[ToolAnnotations],
) -> float:
    """쿼리 의도와 도구 어노테이션의 정렬 점수 계산.

    Returns:
        [0.0, 1.0] 범위의 점수:
        - 1.0: 완전 정렬 (읽기 의도 + 읽기 전용 도구)
        - 0.5: 중립 (신호 없음)
        - 0.0: 명확한 불일치 (쓰기 의도 + 읽기 전용 도구)
    """
    if annotations is None or intent.is_neutral:
        return _NEUTRAL_SCORE

    scores: list[float] = []
    weights: list[float] = []

    # 읽기 의도 vs readOnlyHint
    if intent.read_intent > 0 and annotations.read_only_hint is not None:
        if annotations.read_only_hint:
            scores.append(1.0)   # 정확히 일치
        else:
            scores.append(0.3)   # 읽기 전용 아니지만 불일치는 아님
        weights.append(intent.read_intent)

    # 쓰기 의도 vs readOnlyHint (역방향)
    if intent.write_intent > 0 and annotations.read_only_hint is not None:
        if annotations.read_only_hint:
            scores.append(0.0)   # 심한 불일치: 쓰기 의도 + 읽기 전용 도구
        else:
            scores.append(1.0)
        weights.append(intent.write_intent)

    # 삭제 의도 vs destructiveHint
    if intent.delete_intent > 0 and annotations.destructive_hint is not None:
        if annotations.destructive_hint:
            scores.append(1.0)   # 정확히 일치
        else:
            scores.append(0.1)
        weights.append(intent.delete_intent)

    # 삭제 의도 vs readOnlyHint (불일치 체크)
    if intent.delete_intent > 0 and annotations.read_only_hint is not None:
        if annotations.read_only_hint:
            scores.append(0.0)   # 심한 불일치: 삭제 의도 + 읽기 전용 도구
        else:
            scores.append(0.7)
        weights.append(intent.delete_intent * 0.5)

    # 실행 의도 vs open_world_hint
    if intent.execute_intent > 0 and annotations.open_world_hint is not None:
        if annotations.open_world_hint:
            scores.append(0.9)   # 실행 도구는 외부 세계 접근 가능성 높음
        else:
            scores.append(0.4)
        weights.append(intent.execute_intent * 0.5)

    if not scores:
        return _NEUTRAL_SCORE

    total_weight = sum(weights)
    if total_weight == 0:
        return _NEUTRAL_SCORE

    return sum(s * w for s, w in zip(scores, weights)) / total_weight


def compute_annotation_scores(
    intent: QueryIntent,
    tool_annotations: dict[str, Optional[ToolAnnotations]],
) -> dict[str, float]:
    """모든 도구에 대한 의도-어노테이션 정렬 점수 계산.

    Args:
        intent: classify_intent()로 분류된 쿼리 의도
        tool_annotations: {tool_name: ToolAnnotations} 매핑

    Returns:
        중립(0.5)이 아닌 점수만 포함한 dict.
        의도가 중립이면 빈 dict 반환 (노이즈 방지).
    """
    if intent.is_neutral:
        return {}

    scores: dict[str, float] = {}
    for name, annotations in tool_annotations.items():
        score = score_annotation_match(intent, annotations)
        if score != _NEUTRAL_SCORE:
            scores[name] = score

    return scores
