"""DifficultyRouter — 작업 난이도 분류기

사용자 입력을 분석하여 Easy/Medium/Hard로 분류.
- Easy: CORE가 직접 답변 (에이전트 불필요)
- Medium: 단일 에이전트 위임
- Hard: 복수 에이전트 병렬 위임

Geny의 AdaptiveClassify 패턴: 규칙 기반 빠른 분류 → LLM fallback
"""
import re
from enum import Enum
from logging import getLogger
from typing import Optional

logger = getLogger(__name__)


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ReasoningStrategy(str, Enum):
    """추론 전략 — System 1 (빠른 직관) vs System 2 (깊은 분석)

    논문 참고: Agentic LLM Survey — System 1/2 Thinking
    """
    SINGLE_SHOT = "single_shot"        # System 1: 즉답 (인사, 간단 질문)
    CHAIN_OF_THOUGHT = "chain_of_thought"  # System 1.5: 단계별 추론
    TREE_OF_THOUGHTS = "tree_of_thoughts"  # System 2: 분기 탐색 (복잡한 문제)
    SELF_REFINE = "self_refine"        # System 2+: 생성→비평→수정 루프
    DEBATE = "debate"                  # System 2+: 다중 관점 토론


# ── 규칙 기반 빠른 분류 ──────────────────────────────────────────

# EASY: 인사, 상식, 단순 질문
_EASY_PATTERNS = [
    r"^(안녕|ㅎㅇ|하이|hello|hi|hey)\b",
    r"^(뭐해|뭐하|잘\s*지내|잘\s*있)",
    r"^(고마워|ㄱㅁ|감사|thanks|thx)",
    r"^(ㅋㅋ|ㅎㅎ|ㅇㅇ|ㄴㄴ|ㄱㄱ|ㅇㅋ)",
    r"^(네|응|알겠|오키|ㅇㅋ|ok|okay)\b",
    r"(몇\s*시|날씨|오늘|지금)",
    r"(누구|뭐야|뭔지|알려줘)\s*$",
]
_easy_re = [re.compile(p, re.IGNORECASE) for p in _EASY_PATTERNS]

# HARD: 복합 작업, 멀티 도메인
_HARD_KEYWORDS = [
    "만들어", "개발해", "구현해", "작성해", "빌드", "배포",
    "리팩토링", "마이그레이션", "전체", "프로젝트",
    "분석하고", "조사하고", "검토하고",  # 복합 동사 (A하고 B하고)
    "그리고", "또한", "추가로",  # 접속사
    "프론트엔드.*백엔드", "백엔드.*프론트엔드",  # 다중 도메인
    "테스트.*배포", "코드.*문서",  # 다중 작업
]
_hard_re = [re.compile(p, re.IGNORECASE) for p in _HARD_KEYWORDS]


def classify_difficulty(user_input: str) -> Difficulty:
    """규칙 기반 난이도 분류 (LLM 호출 없이 빠르게)

    분류 실패 시 MEDIUM 반환 (안전한 기본값).
    """
    text = user_input.strip()

    # 빈 입력
    if not text:
        return Difficulty.EASY

    # 너무 짧은 입력 (10자 이하) → EASY
    if len(text) <= 10:
        for pattern in _easy_re:
            if pattern.search(text):
                return Difficulty.EASY
        # 짧지만 패턴에 안 걸리면 MEDIUM
        return Difficulty.MEDIUM

    # EASY 패턴 체크
    for pattern in _easy_re:
        if pattern.search(text):
            return Difficulty.EASY

    # HARD 키워드 카운트
    hard_hits = sum(1 for p in _hard_re if p.search(text))

    # 2개 이상 HARD 키워드 → HARD
    if hard_hits >= 2:
        return Difficulty.HARD

    # 긴 입력 (200자 이상) + HARD 키워드 1개 → HARD
    if len(text) >= 200 and hard_hits >= 1:
        return Difficulty.HARD

    # 그 외 → MEDIUM
    return Difficulty.MEDIUM


def classify_difficulty_with_context(
    user_input: str,
    agent_count: int = 0,
    has_code_keywords: bool = False,
) -> Difficulty:
    """컨텍스트를 고려한 분류

    Args:
        user_input: 사용자 입력
        agent_count: 사용 가능한 에이전트 수
        has_code_keywords: 코드 관련 키워드 존재 여부
    """
    base = classify_difficulty(user_input)

    # 에이전트가 없으면 EASY로 강제
    if agent_count == 0:
        return Difficulty.EASY

    # 코드 키워드 있으면 최소 MEDIUM
    if has_code_keywords and base == Difficulty.EASY:
        return Difficulty.MEDIUM

    return base


# ── 추론 복잡도 키워드 ─────────────────────────────────────────────
_REASONING_KEYWORDS = {
    "comparison": ["비교", "차이", "vs", "versus", "장단점", "어떤 게 나아"],
    "multi_step": ["단계별", "순서대로", "절차", "방법", "how to", "과정"],
    "analysis": ["분석", "원인", "이유", "왜", "why", "근본"],
    "creative": ["아이디어", "브레인스토밍", "제안", "창의", "새로운 방법"],
    "code_complex": ["아키텍처", "설계", "리팩토링", "최적화", "시스템 디자인"],
}


def select_reasoning_strategy(
    user_input: str,
    difficulty: Difficulty,
) -> ReasoningStrategy:
    """난이도와 입력 특성에 따라 최적 추론 전략을 선택

    Difficulty와 독립적으로, 같은 MEDIUM이라도 질문 유형에 따라
    다른 추론 전략이 필요할 수 있다.
    """
    text = user_input.strip().lower()

    # EASY → 항상 SINGLE_SHOT
    if difficulty == Difficulty.EASY:
        return ReasoningStrategy.SINGLE_SHOT

    # 키워드 카테고리 매칭
    matched_categories = []
    for category, keywords in _REASONING_KEYWORDS.items():
        if any(k in text for k in keywords):
            matched_categories.append(category)

    # HARD + 다중 카테고리 → DEBATE 또는 SELF_REFINE
    if difficulty == Difficulty.HARD:
        if len(matched_categories) >= 2:
            return ReasoningStrategy.DEBATE
        if "code_complex" in matched_categories or "analysis" in matched_categories:
            return ReasoningStrategy.TREE_OF_THOUGHTS
        return ReasoningStrategy.SELF_REFINE

    # MEDIUM
    if "comparison" in matched_categories or "analysis" in matched_categories:
        return ReasoningStrategy.CHAIN_OF_THOUGHT
    if "creative" in matched_categories:
        return ReasoningStrategy.TREE_OF_THOUGHTS
    if "code_complex" in matched_categories:
        return ReasoningStrategy.CHAIN_OF_THOUGHT
    if "multi_step" in matched_categories:
        return ReasoningStrategy.CHAIN_OF_THOUGHT

    # MEDIUM 기본
    return ReasoningStrategy.CHAIN_OF_THOUGHT


def classify_with_strategy(
    user_input: str,
    agent_count: int = 0,
    has_code_keywords: bool = False,
) -> tuple[Difficulty, ReasoningStrategy]:
    """난이도 + 추론 전략을 동시에 반환

    Returns:
        (difficulty, reasoning_strategy) 튜플
    """
    difficulty = classify_difficulty_with_context(
        user_input, agent_count, has_code_keywords
    )
    strategy = select_reasoning_strategy(user_input, difficulty)

    logger.debug(
        f"[DifficultyRouter] 분류: {difficulty.value} / 전략: {strategy.value} "
        f"(input: {user_input[:50]}...)"
    )

    return difficulty, strategy
