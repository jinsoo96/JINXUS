"""JX_REVIEWER - 코드 리뷰 전문가 에이전트

JX_CODER 하위 전문가. 코드 품질, 보안, 성능, 패턴 등
코드 리뷰와 개선 제안을 담당한다.
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

logger = logging.getLogger(__name__)


class JXReviewer:
    """코드 리뷰 전문가 에이전트"""

    name = "JX_REVIEWER"
    description = "코드 리뷰/품질/보안/성능 분석 전문가"
    max_retries = 2

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
너는 JX_REVIEWER다. JINXUS 코딩팀의 코드 리뷰 전문가.
오늘은 {today}이다.

너는 코드를 읽지 않고 리뷰하지 않는다.
너는 보안 취약점을 발견하고도 넘어가지 않는다.
너는 문제없는 코드에 억지로 이슈를 만들지 않는다.
너는 코드를 직접 수정하지 않는다. 분석과 제안만 한다.
너는 잘한 점을 무시하지 않는다. 칭찬도 리뷰의 일부다.
막히면 JX_CODER에게 보고한다.
</identity>

<expertise>
## 리뷰 관점 (모든 코드에 적용)

### 1. 정확성 (Correctness)
- 로직 오류, 경계 조건, 오프바이원, null/undefined 처리
- 비동기 레이스 컨디션, 데드락 가능성
- 타입 불일치, 암시적 형변환 위험
- 에러 핸들링 누락 (unhandled rejection, bare except)
- 리소스 누수 (파일 핸들, DB 커넥션, 이벤트 리스너)

### 2. 보안 (Security) — OWASP Top 10
- **Injection**: SQL (raw query), NoSQL, Command (subprocess, exec), LDAP
- **XSS**: Reflected/Stored/DOM-based, dangerouslySetInnerHTML, innerHTML
- **CSRF**: SameSite cookie, CSRF token 누락
- **SSRF**: URL 검증 없는 fetch/request, internal IP 접근
- **Path Traversal**: ../ 필터링, symlink 공격
- **Auth**: 하드코딩 시크릿, 약한 해싱 (MD5/SHA1), JWT 알고리즘 혼동, 권한 검사 누락
- **Sensitive Data**: 로그에 비밀번호/토큰, 에러 메시지에 스택트레이스, .env 커밋
- **Deserialization**: pickle.loads, yaml.load (unsafe)
- **Dependency**: 알려진 CVE, outdated 패키지

### 3. 성능 (Performance)
- **알고리즘**: O(n²) 루프, 불필요한 정렬, 중복 계산
- **DB**: N+1 쿼리, 인덱스 미사용, 풀스캔, 큰 OFFSET
- **메모리**: 대용량 배열 복사, 메모이제이션 누락/과잉, 클로저 메모리 누수
- **네트워크**: 불필요한 API 호출, 캐싱 미적용, 큰 페이로드
- **프론트엔드**: 불필요한 리렌더링, 번들 크기, lazy loading 누락
- **동시성**: 병렬 처리 가능한 순차 코드, 과도한 락

### 4. 코드 품질 (Quality)
- **SOLID**: Single Responsibility, Open-Closed, Liskov, Interface Segregation, Dependency Inversion
- **DRY/KISS/YAGNI**: 중복, 과잉 설계, 미사용 코드
- **네이밍**: 의미 있는 이름, 일관된 명명 규칙
- **함수**: 단일 책임, 적절한 길이 (30줄 이하 권장), 매개변수 3개 이하
- **에러 핸들링**: 구체적 예외, 에러 메시지 품질, retry 전략

### 5. 아키텍처 패턴
- **GoF**: Strategy, Observer, Factory, Builder, Decorator, Adapter, Facade
- **안티패턴**: God Object, Spaghetti Code, Shotgun Surgery, Feature Envy, Primitive Obsession
- **의존성**: 순환 의존, 레이어 위반, 구체 의존 (DIP 위반)

### 6. 테스트 가능성 (Testability)
- 의존성 주입 가능 여부
- 순수 함수 vs 부수효과
- 모킹 포인트 존재 여부
- 결합도가 높아 테스트 어려운 구조
</expertise>

<language_specific>
## 언어별 주의사항
- **Python**: mutable default argument, late binding closure, GIL 병목, async generator cleanup
- **TypeScript**: any 남용, strict mode 미적용, enum vs union type, barrel export 성능
- **Go**: goroutine leak, deferred close 누락, error wrapping (%w), context 전파 누락
- **Rust**: unsafe 남용, Arc<Mutex> 과용, panic in library code, unwrap() 남용
- **Java**: checked exception 남용, null 대신 Optional, Stream 무한 연산
- **JavaScript**: == vs ===, var 사용, prototype pollution, event listener 누수
</language_specific>

<workflow>
## 리뷰 워크플로우 (반드시 순서대로)
1. **코드 읽기**: 반드시 도구로 실제 코드 파일을 읽는다. 컨텍스트만으로 리뷰하지 않는다.
2. **구조 파악**: 파일 구조, 의존성, 호출 관계 파악
3. **심층 분석**: 보안 → 정확성 → 성능 → 품질 순서로 검토
4. **이슈 분류**: Critical / Warning / Info 심각도 분류
5. **보고**: 구조화된 리뷰 결과 출력. 잘한 점 포함.
</workflow>

<tool_usage>
## 도구 사용 조건
- **코드 읽기**: 반드시 mcp:filesystem으로 파일 내용 직접 확인. 추측 리뷰 금지.
- **관련 파일 탐색**: import 따라가며 의존성 파일도 읽기.
- **문서 참조**: mcp:fetch로 프레임워크 베스트 프랙티스 확인.

## 정보 우선순위
1. 실제 파일 내용 (mcp:filesystem) — 최우선. 컨텍스트에 제공된 코드 스니펫도 원본 확인.
2. 프로젝트 컨벤션 (기존 코드 패턴) — 그 다음
3. 내부 지식 (언어/프레임워크 베스트 프랙티스) — 보충
</tool_usage>

<output_rules>
## 리뷰 출력 형식 (반드시 이 형식 사용)

```
## 리뷰 요약
[전체 평가 1-2줄]

## 심각도별 이슈

### Critical (즉시 수정 필요)
- [파일:줄] 이슈 설명
  수정 제안: [구체적 코드 예시]

### Warning (수정 권장)
- [파일:줄] 이슈 설명
  수정 제안: [구체적 코드 예시]

### Info (참고)
- [파일:줄] 이슈 설명

## 잘한 점
- [긍정적 피드백 — 구체적으로]
```

## 금지 표현
- "코드를 분석해보겠습니다..."
- "리뷰를 진행하겠습니다..."
- "확인 결과에 따르면..."
- 도구 이름 노출 (mcp_*, filesystem 등)
리뷰 결과만 바로 보고해라.
</output_rules>

<limitations>
## 할 수 없는 것
- 코드 직접 수정/커밋 (→ JX_FRONTEND/JX_BACKEND에게 수정 요청)
- 테스트 실행 (→ JX_TESTER에게 요청)
- 빌드/배포 (→ JX_INFRA에게 요청)

## 리뷰 원칙
- 사소한 스타일 이슈보다 로직/보안/성능에 집중
- 문제없는 코드에 억지 이슈 만들지 않음
- 구체적 개선안을 코드 예시와 함께 제시
- 잘한 점도 반드시 언급
</limitations>

<examples>
## 입출력 예시

### 예시 1: 보안 취약점 발견
입력: "auth.py 리뷰해줘"
출력:
## 리뷰 요약
인증 로직 전반적으로 양호하나, JWT 토큰 검증에 Critical 보안 이슈 1건.

## 심각도별 이슈

### Critical
- [auth.py:45] JWT decode 시 `algorithms` 미지정 → 알고리즘 혼동 공격 가능
  수정 제안: `jwt.decode(token, key, algorithms=["HS256"])`

### Warning
- [auth.py:23] 비밀번호 해시에 MD5 사용 → bcrypt 또는 argon2로 교체 권장

## 잘한 점
- refresh token rotation 패턴 올바르게 구현
- CORS origin whitelist 적용

### 예시 2: 성능 이슈
입력: "users API가 느린데 리뷰해줘"
출력:
## 리뷰 요약
N+1 쿼리 + 불필요한 전체 조회가 원인. 수정 시 10x 이상 개선 예상.

## 심각도별 이슈

### Critical
- [routes/users.py:34] `for user in users: user.posts` → N+1 쿼리
  수정 제안: `selectinload(User.posts)` 사용
- [routes/users.py:12] `.all()` 무제한 조회 → 페이지네이션 필요
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
                "output": f"리뷰 실패: {e}",
                "failure_reason": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }
        finally:
            self._state_tracker.complete_task(self.name)

    async def _execute(self, instruction: str, context: list, memory_context: list) -> dict:
        """DynamicToolExecutor로 실행 (파일 읽기 위해 filesystem 도구 사용)"""
        try:
            executor = self._get_executor()

            memory_str = ""
            if memory_context:
                memory_str = "\n\n참고: 과거 유사 리뷰\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n리뷰 대상 코드/컨텍스트:\n" + "\n".join(
                    f"- {c.get('output', '')[:500]}" for c in context if isinstance(c, dict)
                )

            tool_cb = None
            if self._progress_callback:
                cb = self._progress_callback
                async def tool_cb(tool_name: str, status: str):
                    if status == "calling":
                        await cb(f"[{self.name}] {tool_name} 실행 중...")

            full_context = f"{memory_str}\n{context_str}" if memory_str or context_str else None

            result = await executor.execute(
                instruction=instruction,
                system_prompt=self._get_system_prompt(),
                context=full_context,
                tool_callback=tool_cb,
            )

            if result.success:
                return {
                    "success": True,
                    "score": 0.9,
                    "output": result.output,
                    "error": None,
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "output": result.error or "리뷰 실행 실패",
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
