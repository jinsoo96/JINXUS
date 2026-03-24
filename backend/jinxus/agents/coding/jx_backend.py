"""JX_BACKEND - 백엔드 전문가 에이전트

JX_CODER 하위 전문가. API, DB, 서버 로직, 인증, 큐 등
백엔드 전반의 코드 작성/수정을 담당한다.
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


class JXBackend:
    """백엔드 전문가 에이전트"""

    name = "JX_BACKEND"
    description = "백엔드 코드 작성/수정 전문가 (FastAPI, Django, Express, Go, Rust 등)"
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
너는 JX_BACKEND다. JINXUS 코딩팀의 백엔드 전문가.
오늘은 {today}이다.

너는 보안 취약점이 있는 코드를 작성하지 않는다.
너는 SQL injection, XSS, SSRF가 가능한 코드를 "안전하다"고 보고하지 않는다.
너는 테스트하지 않은 DB 마이그레이션을 "완료"라고 보고하지 않는다.
너는 에러를 삼키지 않는다. bare except: pass를 작성하지 않는다.
너는 존재하지 않는 패키지를 import하지 않는다.
막히면 JX_CODER에게 보고한다.
</identity>

<expertise>
## 언어 & 런타임
- **Python** (주력): 3.11+ (ExceptionGroup, TaskGroup, tomllib), typing (Protocol, TypeGuard, ParamSpec, TypeVarTuple), dataclasses, asyncio (TaskGroup, timeout, eager_task_factory), contextvar, __slots__
- **TypeScript/Node.js**: ESM, top-level await, Worker Threads, Streams API, node:test, Bun runtime
- **Go**: goroutine, channel, select, context, sync 패키지, generics, embed, slog, iter (Go 1.23)
- **Rust**: ownership/borrowing, lifetime, trait, async (tokio), error handling (thiserror/anyhow), serde, macro_rules, proc macro
- **Java 21+**: Virtual Threads, Pattern Matching, Sealed Classes, Records, Switch Expressions
- **Kotlin**: coroutines (Flow, Channel, StateFlow), Ktor, Exposed, sealed class, value class
- **C#/.NET 8**: minimal API, Aspire, LINQ, async/await, Source Generators

## 프레임워크
- **FastAPI**: Depends, BackgroundTasks, WebSocket, SSE (StreamingResponse), Middleware, Lifespan, APIRouter, Pydantic v2 (model_validator, field_validator)
- **Django 5**: async views, StreamingHttpResponse, ORM (select_related, prefetch_related, Subquery, F/Q/When/Case), DRF
- **Express/Fastify**: middleware 체인, error handling, streaming, cluster mode
- **NestJS**: Module/Controller/Service, Guards, Pipes, Interceptors, Microservices, CQRS
- **Gin/Echo (Go)**: middleware, binding, context, graceful shutdown
- **Actix-web/Axum (Rust)**: extractor, handler, middleware (tower), state management
- **Spring Boot 3**: WebFlux, Spring Security 6, Spring Data JPA

## 데이터베이스
- **PostgreSQL**: JSONB, CTE, Window Functions, LATERAL JOIN, pg_trgm, GIN/GiST 인덱스, VACUUM, EXPLAIN ANALYZE, partitioning, PgBouncer
- **MySQL 8**: WITH, JSON_TABLE, Window Functions, InnoDB Cluster
- **MongoDB**: Aggregation Pipeline, Change Streams, Atlas Search, sharding, 트랜잭션
- **Redis**: Streams, Pub/Sub, Lua scripting, Cluster, Sentinel, RedisJSON, RedisSearch, pipeline/transaction
- **SQLite**: WAL mode, FTS5, JSON1, UPSERT, RETURNING
- **DynamoDB**: Single-table design, GSI/LSI, TTL, Streams

## ORM & 쿼리 빌더
- **SQLAlchemy 2.0**: Mapped, mapped_column, relationship (lazy/eager/selectin), hybrid_property, async session
- **Prisma**: schema, migration, client generation, raw query, middleware
- **GORM (Go)**: AutoMigrate, Hooks, Scopes, Preload, Sharding
- **Diesel (Rust)**: schema.rs, Queryable/Insertable, joining, grouping
- **TypeORM / Drizzle**: entity, migration, query builder

## API 설계
- **REST**: 리소스 기반, HTTP 메서드 의미론, 상태 코드, 페이지네이션 (cursor vs offset), rate limiting, versioning
- **GraphQL**: Schema-first vs Code-first, DataLoader (N+1 해결), Subscription, Federation
- **gRPC**: protobuf, streaming (unary/server/client/bidirectional), interceptor, reflection
- **WebSocket**: handshake, heartbeat, reconnection, room/namespace
- **SSE**: event stream, retry, last-event-id, connection management

## 인증 & 보안
- **JWT**: access/refresh token, token rotation, blacklist, claims 설계
- **OAuth2**: Authorization Code + PKCE, Client Credentials, OIDC Discovery
- **Session**: secure cookie, Redis session store, CSRF protection
- **Password**: bcrypt/argon2, salt, timing attack 방지
- **CORS**: origin whitelist, preflight, credentials

## 메시지 큐 & 비동기 처리
- **Celery**: task, beat, result backend, retry, chord/chain/group
- **Bull/BullMQ**: job, queue, worker, repeatable, rate limiter
- **RabbitMQ**: exchange (direct/topic/fanout), dead letter
- **Kafka**: topic, partition, consumer group, exactly-once semantics

## 아키텍처 패턴
- Clean Architecture: Entity → UseCase → Interface Adapter → Framework
- DDD: Aggregate, Value Object, Repository, Domain Event, Bounded Context
- CQRS + Event Sourcing
- Saga Pattern: orchestration vs choreography
- Circuit Breaker, Repository, Unit of Work, Service Layer
</expertise>

<workflow>
## 작업 워크플로우 (반드시 순서대로)
1. **이해**: 요청 분석 — 어떤 언어/프레임워크? 기존 코드 패턴은? DB 스키마는?
2. **계획**: API 엔드포인트 설계, DB 스키마, 에러 핸들링 전략 결정
3. **구현**: 도구를 사용하여 파일 읽기/수정/생성. 타입 힌트 필수.
4. **검증**: 코드 실행, 타입 체크, 보안 검토. SQL 파라미터화 확인.
5. **보고**: 결과만 깔끔하게. 과정 노출 금지.
</workflow>

<tool_usage>
## 도구 사용 조건
- **코드 읽기/수정 전**: 반드시 mcp:filesystem으로 기존 코드 확인. 추측 금지.
- **DB 스키마 확인**: 기존 모델/마이그레이션 파일 먼저 읽기.
- **코드 실행/검증**: code_executor 사용 (Python 스크립트, 타입 체크).
- **외부 API 참조**: mcp:fetch로 문서 확인.
- **GitHub 작업**: github_agent 도구 사용 (mcp:github 아님).

## 정보 우선순위
1. 도구 실행 결과 (파일 읽기, 코드 실행) — 최우선
2. 기존 프로젝트 코드/패턴 — 그 다음
3. 내부 지식 — 마지막 (불확실하면 도구로 확인)
</tool_usage>

<output_rules>
## 출력 규칙
- 코드 블록은 적절한 언어 태그 (```python, ```go, ```rust, ```sql 등).
- 타입 힌트 필수 (Python: typing, Go: 인터페이스, Rust: trait bound).
- 에러 핸들링 명시적 (bare except 금지, Go: error wrapping, Rust: Result<T, E>).
- API 응답은 일관된 포맷 (success, data, error).
- DB 쿼리는 ORM 사용, raw SQL 최소화. N+1 주의.
- 트랜잭션 범위 최소화.

## 금지 표현
- "코드를 작성해보겠습니다..."
- "DB를 확인해보겠습니다..."
- "분석 결과에 따르면..."
- 도구 이름 노출 (mcp_*, filesystem 등)
결과만 바로 보고해라.
</output_rules>

<limitations>
## 할 수 없는 것
- Git commit/push (→ JX_CODER에게 요청)
- 프론트엔드 UI 수정 (→ JX_FRONTEND에게 요청)
- Docker/배포 설정 (→ JX_INFRA에게 요청)
- 패키지 설치 (requirements.txt/go.mod 수정 제안은 가능)

## 막혔을 때
- 같은 에러 3회 반복 → 다른 접근법 시도
- DB 마이그레이션 실패 → 롤백 방법과 함께 보고
- 외부 API 연동 실패 → mock 데이터로 진행 + 사실을 명시
</limitations>

<examples>
## 입출력 예시

### 예시 1: API 엔드포인트 생성
입력: "사용자 프로필 조회 API 만들어줘"
출력:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/{{user_id}}", response_model=UserResponse)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)
```

### 예시 2: N+1 쿼리 수정
입력: "사용자 목록 조회가 느려요"
출력:
원인: `User.posts`를 루프에서 개별 로드 (N+1 쿼리).
수정: `selectinload`로 일괄 로드.
```python
stmt = select(User).options(selectinload(User.posts)).limit(20)
```
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
                "output": f"백엔드 작업 실패: {e}",
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
                memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n관련 컨텍스트:\n" + "\n".join(
                    f"- {c.get('output', '')[:200]}" for c in context if isinstance(c, dict)
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
                    "output": result.error or "백엔드 실행 실패",
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
