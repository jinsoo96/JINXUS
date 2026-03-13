"""Zero-LLM 쿼리 의도 분류기 (graph-tool-call 패턴 적용)

사용자 쿼리에서 읽기/쓰기/삭제 의도를 LLM 호출 없이 키워드 매칭으로 분류한다.
한국어 조사/어미 정규화를 포함하여 한국어-영어 혼합 쿼리에 대응.

참고: https://github.com/SonAIengine/graph-tool-call (retrieval/intent.py)
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# ─── 한국어 형태소 정규화 패턴 ───────────────────────

# 조사 제거 패턴 (조사가 붙은 토큰에서 체언 추출)
_KO_POSTPOSITIONS = re.compile(
    r"(을|를|이|가|은|는|에|에서|에게|께|로|으로|와|과|의|도|만|까지|부터|라도|처럼)$"
)

# 동사 어미 정규화 (명령/청유/존댓말 제거 → 어근 추출)
_KO_VERB_ENDINGS = re.compile(
    r"(해줘|해주세요|해주실래요|해줄래|해주기|하기|합니다|해요|해봐|하고|"
    r"해야|하는|해라|하자|해줄|해봐줘|해봐주세요|해주|해줘요|해봐요)$"
)


# ─── 의도 키워드 사전 ────────────────────────────────

# 읽기/조회 의도
_READ_KEYWORDS = frozenset({
    # 영어
    "get", "list", "show", "read", "fetch", "retrieve", "search", "find",
    "view", "query", "lookup", "check", "inspect", "describe", "display",
    "browse", "look", "peek", "see",
    # 한국어
    "조회", "목록", "보기", "보여", "검색", "확인", "열람", "표시",
    "가져오기", "가져와", "찾기", "찾아", "얻기", "얻어", "살펴",
    "알려", "알아", "봐", "봐줘", "보여줘", "가져", "찾아줘",
})

# 쓰기/생성/수정 의도
_WRITE_KEYWORDS = frozenset({
    # 영어
    "create", "add", "update", "modify", "edit", "set", "put", "post",
    "write", "change", "patch", "configure", "save", "upload", "submit",
    "register", "insert", "append", "push",
    # 한국어
    "생성", "추가", "수정", "변경", "편집", "설정", "등록", "저장",
    "업로드", "작성", "만들어", "바꿔", "고쳐", "넣어", "올려",
    "써줘", "작성해", "만들어줘", "추가해", "수정해", "변경해",
})

# 삭제/제거 의도
_DELETE_KEYWORDS = frozenset({
    # 영어
    "delete", "remove", "destroy", "drop", "purge", "erase",
    "unregister", "revoke", "cancel", "terminate", "disable", "clear",
    # 한국어
    "삭제", "제거", "취소", "해제", "폐기", "비활성화", "해지",
    "지워", "없애", "지워줘", "삭제해", "제거해", "없애줘",
})

# 실행/실시 의도 (코드 실행, 빌드, 테스트 등)
_EXECUTE_KEYWORDS = frozenset({
    # 영어
    "run", "execute", "start", "launch", "deploy", "build", "test",
    "trigger", "invoke", "call",
    # 한국어
    "실행", "시작", "실시", "구동", "배포", "빌드", "테스트",
    "실행해", "시작해", "돌려", "돌려줘",
})


@dataclass
class QueryIntent:
    """쿼리의 행동 의도 (behavioral intent).

    각 차원은 [0.0, 1.0] 신뢰도를 나타낸다.
    여러 의도가 동시에 감지될 수 있음 (예: 검색+저장 쿼리).
    """
    read_intent: float = 0.0
    write_intent: float = 0.0
    delete_intent: float = 0.0
    execute_intent: float = 0.0

    @property
    def is_neutral(self) -> bool:
        """유의미한 의도 신호가 없으면 True."""
        return (
            self.read_intent == 0.0
            and self.write_intent == 0.0
            and self.delete_intent == 0.0
            and self.execute_intent == 0.0
        )

    @property
    def primary_intent(self) -> str:
        """가장 강한 의도 반환."""
        intents = {
            "read": self.read_intent,
            "write": self.write_intent,
            "delete": self.delete_intent,
            "execute": self.execute_intent,
        }
        best = max(intents, key=intents.get)
        return best if intents[best] > 0.0 else "neutral"

    def __repr__(self) -> str:
        parts = []
        if self.read_intent > 0:
            parts.append(f"read={self.read_intent:.2f}")
        if self.write_intent > 0:
            parts.append(f"write={self.write_intent:.2f}")
        if self.delete_intent > 0:
            parts.append(f"delete={self.delete_intent:.2f}")
        if self.execute_intent > 0:
            parts.append(f"execute={self.execute_intent:.2f}")
        return f"QueryIntent({', '.join(parts) if parts else 'neutral'})"


def _normalize_korean(text: str) -> str:
    """한국어 텍스트 정규화 - 조사와 동사 어미 제거.

    Examples:
        "사용자를 삭제해줘" → "사용자 삭제"
        "목록을 조회해주세요" → "목록 조회"
        "코드를 실행해줘" → "코드 실행"
    """
    tokens = text.split()
    normalized = []
    for token in tokens:
        # 동사 어미 먼저 제거 (더 긴 패턴 우선)
        t = _KO_VERB_ENDINGS.sub("", token)
        # 그 다음 조사 제거
        t = _KO_POSTPOSITIONS.sub("", t)
        if t:
            normalized.append(t)
    return " ".join(normalized)


def classify_intent(query: str) -> QueryIntent:
    """쿼리를 행동 의도로 분류 (LLM 호출 없음).

    한국어 형태소 정규화 + 키워드 매칭으로 의도를 파악한다.
    중립 의도(neutral)는 키워드가 전혀 없는 경우.

    Args:
        query: 사용자 쿼리 (한국어/영어/혼합 지원)

    Returns:
        QueryIntent: 각 의도 차원의 신뢰도

    Examples:
        classify_intent("파일 목록 보여줘") → read_intent=1.0
        classify_intent("PR 생성하고 push해줘") → write_intent=0.5, execute_intent=0.5
        classify_intent("캐시 삭제해줘") → delete_intent=1.0
    """
    # 한국어 정규화 버전 생성
    normalized = _normalize_korean(query)

    # 토큰 집합 구성 (원본 + 정규화 버전 합집합)
    tokens = set(normalized.lower().split())
    tokens |= set(query.lower().split())

    # 각 의도 키워드 히트 수 계산
    read_hits = len(tokens & _READ_KEYWORDS)
    write_hits = len(tokens & _WRITE_KEYWORDS)
    delete_hits = len(tokens & _DELETE_KEYWORDS)
    execute_hits = len(tokens & _EXECUTE_KEYWORDS)

    total = read_hits + write_hits + delete_hits + execute_hits
    if total == 0:
        return QueryIntent()

    return QueryIntent(
        read_intent=min(read_hits / total, 1.0),
        write_intent=min(write_hits / total, 1.0),
        delete_intent=min(delete_hits / total, 1.0),
        execute_intent=min(execute_hits / total, 1.0),
    )
