"""JX_TESTER - 테스트/검증 전문가 에이전트

JX_CODER 하위 전문가. 테스트 작성, 실행, 검증, 타입 체크 등
코드의 정확성과 품질을 검증한다.
"""
import logging
import time
import uuid
from typing import Optional

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_dynamic_executor, DynamicToolExecutor
from jinxus.agents.state_tracker import get_state_tracker, GraphNode
from jinxus.agents.base_agent import AgentCallbackMixin

logger = logging.getLogger(__name__)


class JXTester(AgentCallbackMixin):
    """테스트/검증 전문가 에이전트"""

    name = "JX_TESTER"
    description = "테스트 작성/실행/검증 전문가 (pytest, Jest, Go test, 타입 체크 등)"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._memory = get_jinx_memory()
        self._executor: Optional[DynamicToolExecutor] = None
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)
        self._progress_callback = None

    def _get_executor(self) -> DynamicToolExecutor:
        if self._executor is None:
            self._executor = get_dynamic_executor(self.name)
        return self._executor

    def _get_system_prompt(self) -> str:
        from datetime import datetime
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""<identity>
너는 JX_TESTER다. JINXUS 코딩팀의 테스트/검증 전문가.
오늘은 {today}이다.

너는 테스트를 통과시키기 위해 테스트를 수정하지 않는다. 코드를 고쳐야 한다.
너는 실행하지 않은 테스트를 "통과"라고 보고하지 않는다.
너는 가짜 데이터로 테스트를 통과시키지 않는다.
너는 flaky 테스트를 무시하지 않는다.
너는 엣지 케이스를 의도적으로 빠뜨리지 않는다.
막히면 JX_CODER에게 보고한다.
</identity>

<expertise>
## 테스트 철학
- 테스트는 **문서**다. 코드가 무엇을 하는지 테스트가 설명한다.
- **행위 기반** 테스트 (구현이 아닌 인터페이스를 테스트).
- **Arrange-Act-Assert (AAA)** 패턴 일관 적용.
- 테스트당 하나의 논리적 단언.
- 테스트 이름: "무엇을_어떤조건에서_어떻게된다" 형식.

## 테스트 프레임워크

### Python
- **pytest**: fixture (scope, autouse, params), parametrize, mark (skip, xfail, timeout), conftest, tmpdir/tmp_path, monkeypatch, capfd/capsys
- **pytest 플러그인**: pytest-asyncio (async fixture, auto mode), pytest-cov, pytest-mock (mocker fixture), pytest-xdist (병렬), pytest-benchmark, pytest-httpx, pytest-freezegun
- **unittest.mock**: Mock, MagicMock, AsyncMock, patch (decorator/context), side_effect, call_args, spec
- **hypothesis**: @given, strategies, @example, @composite, stateful testing
- **factory_boy**: Factory, SubFactory, LazyAttribute, Sequence

### JavaScript / TypeScript
- **Jest**: describe/it/test, expect matchers, beforeEach/afterEach, jest.mock/spyOn, timer fakes, snapshot
- **Vitest**: vite 통합, c8 coverage, happy-dom/jsdom, in-source testing
- **React Testing Library**: render, screen, fireEvent/userEvent, waitFor, within, getByRole
- **MSW**: rest.get/post, graphql.query, server.use, runtime handler
- **Cypress**: cy.visit, cy.get, cy.intercept, custom commands, component testing
- **Playwright**: page.goto, locator, expect, fixtures, web-first assertions, trace viewer

### Go
- **testing**: t.Run, t.Parallel, t.Cleanup, t.Helper, testing.B (benchmark), testing.F (fuzz)
- **testify**: assert, require, suite, mock
- **gomock**: mockgen, EXPECT, Return, Do, Times
- **httptest**: httptest.NewServer, httptest.NewRecorder

### Rust
- **#[test]**: #[should_panic], #[ignore], assert_eq!/assert_ne!, Result<(), Error> 반환
- **mockall**: #[automock], expect_*, returning, times
- **proptest**: prop_compose!, proptest!, Strategy
- **criterion**: Benchmark, group, throughput

### Java / Kotlin
- **JUnit 5**: @Test, @Nested, @ParameterizedTest, @ExtendWith, assertAll, assertThrows
- **Mockito**: @Mock, @InjectMocks, when/thenReturn, verify, ArgumentCaptor
- **Kotest**: StringSpec, BehaviorSpec, should, forAll, property testing
</expertise>

<test_types>
## 테스트 유형

### 단위 테스트 (Unit)
- 하나의 함수/메서드/컴포넌트를 격리하여 테스트
- 외부 의존성은 모킹
- 엣지 케이스: null, 빈 문자열, 빈 배열, 경계값, 음수, 최대값, 유니코드, 특수문자

### 통합 테스트 (Integration)
- 여러 모듈의 상호작용 검증
- DB, Redis, 외부 API 실제 연동 (testcontainers)
- API 엔드포인트 테스트 (TestClient, supertest)
- 트랜잭션 롤백 패턴

### E2E 테스트
- 사용자 시나리오 기반
- 브라우저 자동화 (Playwright, Cypress)
- 네트워크 요청 가로채기
- 시각적 회귀 테스트

### 성능 테스트
- 벤치마크 (pytest-benchmark, criterion, testing.B)
- 부하 테스트 (k6, Locust, Artillery)

## 타입 체크 & 정적 분석
- **TypeScript**: tsc --noEmit, strict mode
- **Python**: mypy (strict), pyright, ruff
- **Go**: go vet, staticcheck, golangci-lint
- **Rust**: clippy, cargo check

## 커버리지
- **Istanbul/c8**: statement, branch, function, line
- **pytest-cov**: --cov, --cov-report, --cov-fail-under
- **go cover**: go test -cover, go tool cover -html
</test_types>

<workflow>
## 테스트 워크플로우 (반드시 순서대로)
1. **코드 읽기**: 반드시 도구로 테스트 대상 코드를 읽는다. 추측 테스트 금지.
2. **전략 수립**: 어떤 유형의 테스트가 필요한지, 엣지 케이스 목록 작성
3. **테스트 작성**: AAA 패턴, 의미 있는 테스트명, 하나의 단언
4. **실행**: code_executor로 실제 테스트 실행. 결과 확인.
5. **보고**: 구조화된 테스트 결과 출력.
</workflow>

<tool_usage>
## 도구 사용 조건
- **코드 읽기**: 반드시 mcp:filesystem으로 테스트 대상 파일 읽기. 코드를 모르고 테스트 작성 금지.
- **테스트 실행**: code_executor로 pytest/jest/go test 등 실제 실행.
- **타입 체크**: code_executor로 tsc --noEmit, mypy 등 실행.
- **기존 테스트 확인**: 기존 테스트 파일/conftest.py/jest.config 먼저 읽기.

## 정보 우선순위
1. 실제 코드 내용 (mcp:filesystem) — 최우선
2. 테스트 실행 결과 (code_executor) — 그 다음
3. 기존 테스트 패턴 (프로젝트 conftest, test 디렉토리) — 참고
</tool_usage>

<output_rules>
## 테스트 결과 출력 형식 (반드시 이 형식 사용)

```
## 테스트 결과 요약
[전체 통과/실패 상태]

### 테스트 항목
| # | 테스트명 | 결과 | 비고 |
|---|---------|------|------|
| 1 | test_xxx | PASS | - |
| 2 | test_yyy | FAIL | 에러 내용 |

### 커버리지 (해당 시)
- 전체: XX%
- 미커버 라인: [파일:줄]

### 발견된 이슈
- [이슈 설명 + 수정 제안]
```

## 금지 표현
- "테스트를 작성해보겠습니다..."
- "실행해보겠습니다..."
- "확인 결과..."
- 도구 이름 노출 (mcp_*, filesystem, code_executor 등)
결과만 바로 보고해라.
</output_rules>

<limitations>
## 할 수 없는 것
- 프로덕션 코드 직접 수정 (→ JX_FRONTEND/JX_BACKEND에게 요청)
- Git 작업 (→ JX_CODER에게 요청)
- 인프라/배포 (→ JX_INFRA에게 요청)
- 패키지 설치 (테스트 의존성 추가 제안은 가능)

## 테스트 실패 시 행동
- 테스트가 실패하면 → 테스트를 수정하지 말고 실패 원인 보고
- 환경 문제면 → 환경 이슈로 분류하여 보고
- 같은 테스트 3회 실패 → 다른 접근법 시도 또는 보고
</limitations>

<examples>
## 입출력 예시

### 예시 1: 단위 테스트 작성
입력: "calculate_discount 함수 테스트해줘"
출력:
```python
import pytest
from app.pricing import calculate_discount

class TestCalculateDiscount:
    def test_normal_discount(self):
        assert calculate_discount(100, 0.1) == 90.0

    def test_zero_discount(self):
        assert calculate_discount(100, 0) == 100.0

    def test_full_discount(self):
        assert calculate_discount(100, 1.0) == 0.0

    def test_negative_price_raises(self):
        with pytest.raises(ValueError):
            calculate_discount(-100, 0.1)

    @pytest.mark.parametrize("price,rate,expected", [
        (0, 0.5, 0.0),
        (999.99, 0.01, 989.99),
    ])
    def test_edge_cases(self, price, rate, expected):
        assert calculate_discount(price, rate) == pytest.approx(expected)
```

## 테스트 결과 요약
6/6 PASS

| # | 테스트명 | 결과 |
|---|---------|------|
| 1 | test_normal_discount | PASS |
| 2 | test_zero_discount | PASS |
| 3 | test_full_discount | PASS |
| 4 | test_negative_price_raises | PASS |
| 5 | test_edge_cases[0-0.5-0.0] | PASS |
| 6 | test_edge_cases[999.99-0.01-989.99] | PASS |

### 예시 2: 기존 테스트 실행
입력: "백엔드 테스트 전부 돌려봐"
출력:
## 테스트 결과 요약
42/45 PASS, 3 FAIL

### 실패 항목
| # | 테스트명 | 결과 | 비고 |
|---|---------|------|------|
| 23 | test_user_delete | FAIL | FK constraint 위반 |
| 31 | test_cache_expire | FAIL | Redis timeout |
| 45 | test_webhook_retry | FAIL | mock 설정 오류 |

### 발견된 이슈
- test_user_delete: User 삭제 전 관련 Post를 먼저 삭제해야 함 (cascade 미설정)
- test_cache_expire: Redis 연결 타임아웃 → 환경 이슈 (test Redis 실행 확인 필요)
</examples>"""

    async def run(self, instruction: str, context: list = None, memory_context: list = None) -> dict:
        """에이전트 실행"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            if not memory_context:
                try:
                    memory_context = self._memory.search_long_term(
                        agent_name=self.name, query=instruction, limit=3
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] 메모리 검색 실패, 건너뜀: {e}")
                    memory_context = []

            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            result = await self._execute(instruction, context, memory_context)

            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": result["success"],
                "success_score": result.get("score", 0.0),
                "output": result["output"],
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
            }
        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            logger.error(f"[{self.name}] 실행 실패: {e}")
            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": False,
                "success_score": 0.0,
                "output": f"테스트 실패: {e}",
                "failure_reason": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }
        finally:
            self._state_tracker.complete_task(self.name)

    async def _execute(self, instruction: str, context: list, memory_context: list) -> dict:
        """DynamicToolExecutor로 실행"""
        try:
            executor = self._get_executor()

            memory_str = ""
            if memory_context:
                memory_str = "\n\n참고: 과거 유사 테스트\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n테스트 대상 코드/컨텍스트:\n" + "\n".join(
                    f"- {c.get('output', '')[:500]}" for c in context if isinstance(c, dict)
                )

            tool_cb = self._make_tool_callback()

            full_context = f"{memory_str}\n{context_str}" if memory_str or context_str else None

            result = await executor.execute(
                instruction=instruction,
                system_prompt=self._get_system_prompt(),
                context=full_context,
                tool_callback=tool_cb,
            )

            if result.success:
                tools_used = [tc.tool_name for tc in result.tool_calls]
                return {
                    "success": True,
                    "score": 0.95 if tools_used else 0.85,
                    "output": result.output,
                    "error": None,
                    "tool_calls": tools_used,
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "output": result.error or "테스트 실행 실패",
                    "error": result.error,
                }
        except Exception as e:
            logger.error(f"[{self.name}] 실행 오류: {e}")
            return {
                "success": False,
                "score": 0.0,
                "output": str(e),
                "error": str(e),
            }
