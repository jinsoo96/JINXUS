# Geny 심층 분석: JINXUS에 적용 가능한 패턴 5가지

> 분석일: 2026-03-08
> 대상: [github.com/CocoRoF/Geny](https://github.com/CocoRoF/Geny)
> 목적: JINXUS에 없는 패턴 중 실제 도입 가치가 있는 것만 선별

---

## 요약

Geny는 JINXUS와 유사한 FastAPI + LangGraph 구조를 가지지만, 다음 영역에서 JINXUS에 없는 구체적인 패턴이 존재한다:

| # | 패턴 | JINXUS 현재 상태 | 도입 가치 |
|---|------|-----------------|----------|
| 1 | 난이도 기반 그래프 분기 | 모든 작업이 동일 파이프라인 | **높음** |
| 2 | Session Freshness Policy | 없음 (세션 staleness 감지 없음) | **높음** |
| 3 | Resilience Node 패턴 (Guard + PostModel 분리) | context_guard는 있으나 그래프 노드가 아님 | **중간** |
| 4 | Tool Policy Engine (역할 기반 도구 접근제어) | allowed_agents만 존재 | **중간** |
| 5 | LangGraph Checkpointer (SQLite 체크포인팅) | 없음 | **중간** |

---

## 패턴 1: 난이도 기반 그래프 분기 (Difficulty-Based Routing)

### Geny 구현

Geny의 `autonomous_graph.py`는 작업을 3단계로 분류하여 **각기 다른 실행 경로**를 사용한다:

- **EASY**: 직접 답변 → END (LLM 1회 호출)
- **MEDIUM**: 답변 → 리뷰 → (승인 → END | 거부 → 재시도 + iteration gate)
- **HARD**: TODO 분해 → 각 TODO 순차 실행 → 진행 체크 → 최종 리뷰 → 종합 답변

핵심은 **간단한 질문에 불필요한 파이프라인을 태우지 않는다**는 점이다.

### JINXUS 현재 문제

JINXUS는 "안녕"이든 "GitHub 레포 분석해서 리팩토링 계획 세워줘"든 모두 같은 경로를 탄다:
```
intake → decompose → dispatch → aggregate → reflect → memory_write → respond
```
- 간단한 인사에도 decompose + dispatch 비용 발생
- LLM 호출 최소 3-4회 (분해, 에이전트, 반성, 응답)

### 구체적 적용 방안

`jinxus_core.py`의 `intake` 노드 직후에 **difficulty classifier** 추가:

```python
# state.py에 추가
class Difficulty(Enum):
    EASY = "easy"      # 인사, 간단한 QA, 상태 질문
    MEDIUM = "medium"  # 단일 에이전트 작업
    HARD = "hard"      # 복수 에이전트 협업 필요

# jinxus_core.py - intake 노드 이후 조건 분기
graph.add_conditional_edges(
    "intake",
    self._classify_difficulty,
    {
        "easy": "quick_respond",    # LLM 1회로 직접 응답
        "medium": "decompose",      # 기존 파이프라인 (단일 에이전트)
        "hard": "decompose",        # 기존 파이프라인 (복수 에이전트)
    },
)
```

**예상 효과**: 간단한 질문의 응답 시간 70-80% 단축, API 비용 절감

---

## 패턴 2: Session Freshness Policy

### Geny 구현

`session_freshness.py`에서 세션의 "신선도"를 4단계로 평가한다:

```
FreshnessConfig:
- max_session_age_seconds: 14400 (4시간)
- max_idle_seconds: 3600 (1시간)
- max_iterations: 200
- compact_after_messages: 80

FreshnessStatus:
- FRESH: 정상
- STALE_WARN: 경고 (2시간/30분 유휴)
- STALE_COMPACT: 메시지 히스토리 과대 → 컴팩션 권장
- STALE_RESET: 세션 종료 및 재생성 필요
```

매 그래프 실행 전 `evaluate()`를 호출하여:
1. 세션 수명/유휴 시간/반복 횟수 체크
2. `should_compact` → context_guard에 컴팩션 트리거
3. `should_reset` → 세션 리셋 (새 세션 생성)

### JINXUS 현재 상태: **구현 완료** (2026-03-08)

- `backend/jinxus/core/session_freshness.py` 신규 생성
- `backend/jinxus/memory/short_term.py`에 세션 메타데이터(created_at/last_active/iteration_count) 관리 추가
- `backend/jinxus/agents/jinxus_core.py`의 `run()`/`run_stream()` 진입부에서 `_check_session_freshness()` 호출
- STALE_RESET: Redis 세션 클리어 + 메타 재초기화 / STALE_COMPACT: context_guard KEEP_RECENT 20개 / STALE_WARN: 로그 경고

### 구체적 적용 방안

`backend/jinxus/core/session_freshness.py` 신규 생성:

```python
@dataclass(frozen=True)
class FreshnessConfig:
    max_session_age_seconds: float = 14400.0   # 4시간
    max_idle_seconds: float = 3600.0           # 1시간
    max_iterations: int = 200
    compact_after_messages: int = 80
    warn_session_age_seconds: float = 7200.0
    warn_idle_seconds: float = 1800.0

class SessionFreshness:
    def evaluate(self, session_id, created_at, last_active, iterations, message_count) -> FreshnessResult:
        # RESET 조건 (가장 위험)
        if age > config.max_session_age_seconds:
            return FreshnessResult(status=STALE_RESET, reason="세션 수명 초과")
        if idle > config.max_idle_seconds:
            return FreshnessResult(status=STALE_RESET, reason="장시간 유휴")
        # COMPACT 조건
        if message_count >= config.compact_after_messages:
            return FreshnessResult(status=STALE_COMPACT, reason="메시지 히스토리 과대")
        # WARN 조건
        ...
```

통합 지점: `jinxus_core.py`의 `intake` 노드에서 `SessionFreshness.evaluate()` 호출

---

## 패턴 3: Resilience Node 패턴 (ContextGuard + PostModel을 그래프 노드로)

### Geny 구현

Geny는 context_guard와 후처리를 **그래프 노드로 분리**한다. 매 LLM 호출 앞뒤에 guard/post 노드를 삽입:

```
... → context_guard_medium → medium_answer → post_medium → ...
... → context_guard_todo → execute_todo → post_todo → ...
```

**ContextGuardNode**: LLM 호출 전 토큰 예산 체크 + 컴팩션
**PostModelNode**: LLM 호출 후 3가지 작업을 수행
  1. iteration 카운터 증가
  2. 완료 신호 감지 (`[TASK_COMPLETE]`, `[BLOCKED: reason]` 등 regex 파싱)
  3. transcript 기록 (short-term memory에 JSONL 저장)

### JINXUS 현재 문제

- `context_guard.py`는 독립 모듈이지만, 그래프 노드로 편입되어 있지 않음
- LLM 호출 후 완료 신호 감지 로직이 없음 (에이전트가 `[BLOCKED]`을 출력해도 무시)
- 작업 transcript가 장기메모리(Qdrant)에만 저장되고, 세션 단위 JSONL 로그 없음

### 구체적 적용 방안

**1단계**: `BaseAgent._build_graph()`에서 execute 노드 앞뒤에 guard/post 삽입:
```python
graph.add_node("pre_execute_guard", self._context_guard_node)
graph.add_node("execute", self._execute_node)
graph.add_node("post_execute", self._post_model_node)

graph.add_edge("plan", "pre_execute_guard")
graph.add_edge("pre_execute_guard", "execute")
graph.add_edge("execute", "post_execute")
graph.add_edge("post_execute", "evaluate")
```

**2단계**: PostModel 노드에서 완료 신호 감지:
```python
COMPLETION_PATTERNS = [
    re.compile(r"\[TASK_COMPLETE\]"),
    re.compile(r"\[BLOCKED:\s*(.+?)\]"),
    re.compile(r"\[ERROR:\s*(.+?)\]"),
    re.compile(r"\[CONTINUE:\s*(.+?)\]"),
]
```

**예상 효과**: 에이전트가 작업 완료를 명시적으로 신호할 수 있어 불필요한 반복 방지

---

## 패턴 4: Tool Policy Engine (역할 기반 도구 접근제어)

### Geny 구현

`tool_policy/policy.py`에서 **프로필 기반으로 MCP 서버와 도구를 필터링**:

```
MINIMAL: 빌트인 도구만
CODING: 빌트인 + filesystem/git/code 서버
MESSAGING: 빌트인 + Slack/email/Discord
RESEARCH: 빌트인 + web/search/knowledge
FULL: 모든 서버

역할 매핑:
  worker/developer → CODING
  manager/planner → FULL
  researcher → RESEARCH
```

`filter_mcp_config()`: 해당 프로필에 허용되지 않은 MCP 서버를 제거
`filter_tool_names()`: 개별 도구 이름도 화이트리스트로 필터

### JINXUS 현재 상태

- `tools/base.py`에 `allowed_agents` 필드가 있지만, 도구 단위로만 필터
- MCP 서버 레벨의 접근제어는 없음
- 모든 에이전트가 모든 MCP 서버에 접근 가능

### 구체적 적용 방안

`backend/jinxus/tools/tool_policy.py` 신규 생성:

```python
class ToolProfile(Enum):
    MINIMAL = "minimal"
    CODING = "coding"
    RESEARCH = "research"
    FULL = "full"

AGENT_PROFILE_MAP = {
    "JX_CODER": ToolProfile.CODING,
    "JX_RESEARCHER": ToolProfile.RESEARCH,
    "JX_WRITER": ToolProfile.MINIMAL,
    "JX_ANALYST": ToolProfile.RESEARCH,
    "JX_OPS": ToolProfile.FULL,
    "JINXUS_CORE": ToolProfile.FULL,
}

class ToolPolicyEngine:
    def filter_tools_for_agent(self, agent_name: str, available_tools: dict) -> dict:
        """에이전트의 프로필에 맞는 도구만 반환"""
        ...
```

통합: `BaseAgent.__init__()`에서 `get_tools_for_agent()` 호출 시 ToolPolicyEngine 적용

**예상 효과**: JX_WRITER가 filesystem MCP를 잘못 호출하는 등의 문제 원천 차단

---

## 패턴 5: LangGraph Checkpointer (그래프 상태 영속화)

### Geny 구현

`checkpointer.py`에서 LangGraph 그래프의 실행 상태를 **SQLite에 체크포인팅**:

```python
def create_checkpointer(storage_path, persistent=True, db_name="langgraph_checkpoints.db"):
    if persistent and storage_path:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            path = Path(storage_path) / db_name
            return SqliteSaver.from_conn_string(str(path))
        except ImportError:
            pass
    return MemorySaver()  # 폴백
```

그래프 컴파일 시 체크포인터를 주입:
```python
graph = workflow.compile(checkpointer=create_checkpointer(storage_path))
```

이로써:
- 장시간 실행 중 서버 재시작 시 마지막 노드부터 재개
- 동일 thread_id로 대화 이어가기
- 과거 그래프 실행 히스토리 조회

### JINXUS 현재 상태

- `BaseAgent._build_graph()`에서 `graph.compile()` 시 체크포인터 없음
- 서버 재시작 시 실행 중이던 그래프 상태 유실
- 텔레그램 장기 대화의 그래프 상태 복원 불가

### 구체적 적용 방안

**1단계**: `backend/jinxus/core/checkpointer.py` 신규 생성 (Geny 패턴 참고)

**2단계**: `BaseAgent._build_graph()`에 체크포인터 주입:
```python
from jinxus.core.checkpointer import create_checkpointer

def _build_graph(self) -> StateGraph:
    graph = StateGraph(AgentState)
    # ... 노드/엣지 추가
    checkpointer = create_checkpointer(
        storage_path=settings.data_dir / "checkpoints",
        persistent=True,
    )
    return graph.compile(checkpointer=checkpointer)
```

**3단계**: `BaseAgent.run()`에서 `thread_id` 전달:
```python
config = {"configurable": {"thread_id": state["task_id"]}}
final_state = await self._graph.ainvoke(initial_state, config=config)
```

**예상 효과**: 자율 실행(autonomous_runner)에서 서버 재시작 후 작업 재개 가능

---

## 도입 우선순위

| 순위 | 패턴 | 구현 난이도 | 영향도 | 추천 시기 |
|------|------|-----------|--------|----------|
| 1 | 난이도 기반 그래프 분기 | 낮음 | **높음** (API 비용/응답속도) | v1.3.x |
| 2 | Session Freshness Policy | 낮음 | **높음** (안정성) | v1.3.x |
| 3 | Resilience Node 패턴 | 중간 | 중간 (신뢰성) | v1.4.x |
| 4 | Tool Policy Engine | 낮음 | 중간 (정확도) | v1.4.x |
| 5 | LangGraph Checkpointer | 낮음 | 중간 (내구성) | v1.4.x |

---

## Geny에 있지만 JINXUS에 불필요한 것

- **3D City Visualization**: Three.js 기반 에이전트 시각화 — 실용성 낮음 (JINXUS는 실무 도구)
- **Multi-Pod Session Routing Middleware**: Redis 기반 세션 라우팅 — JINXUS는 단일 서버 운영 중
- **PromptBuilder Fluent API**: 섹션/우선순위/모드 기반 프롬프트 조립 — JINXUS의 md 파일 기반이 더 단순하고 충분
- **Manager-Worker Delegation**: Geny는 Claude CLI subprocess 기반이라 별도 세션 관리 필요 — JINXUS는 직접 API 호출이라 불필요
