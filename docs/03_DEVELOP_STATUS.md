# JINXUS 개발 현황

## 버전 v1.2.2 (진행 중)

### 2026-03-05 업데이트 (2)

#### 참조 프로젝트 분석 및 고도화

**목적:**
- 참조 프로젝트(claude_company, Geny) 구조 분석
- Geny의 LangGraph 패턴을 JINXUS에 적용
- 핵심 모듈 고도화

**참조 프로젝트:**
- [claude_company](https://github.com/CocoRoF/claude_company): CLI subprocess 패턴
- [Geny](https://github.com/CocoRoF/Geny): FastAPI + LangGraph 자율 에이전트 시스템

---

#### 1. context_guard.py 고도화 (Geny 패턴 적용)

**기존:**
- 단순 문자 수 기반 truncation (MAX_OUTPUT_CHARS = 4000)

**개선:**
- **토큰 추정**: 영어 4자/토큰, 한국어 3자/토큰으로 보수적 추정
- **3단계 모니터링**: `BudgetStatus` enum (OK → WARN 75% → BLOCK 90% → OVERFLOW 100%)
- **컴팩션 전략**: `CompactionStrategy` enum
  - KEEP_RECENT: 최근 N개 메시지만 유지
  - TRUNCATE_EARLY: 초기 메시지 제거
  - REMOVE_TOOL_DETAILS: 도구 호출 상세 축소
- **ContextWindowGuard 클래스**:
  - `estimate_tokens()`: 텍스트 토큰 수 추정
  - `check()`: 예산 상태 확인 → `BudgetCheck` 반환
  - `compact()`: 전략별 메시지 컴팩션
  - `check_and_compact()`: 검사 + 자동 컴팩션 통합

---

#### 2. model_router.py 고도화 (Geny ModelFallbackRunner 패턴)

**기존:**
- 2단계 모델 선택 (주 → 폴백)
- 에러 처리 없음

**개선:**
- **에러 분류**: `FailureReason` enum (8가지)
  - RATE_LIMITED, OVERLOADED, TIMEOUT, CONTEXT_WINDOW
  - AUTH_ERROR, NETWORK_ERROR, UNKNOWN, ABORT
- **복구 가능성 판단**: `is_recoverable()` 함수
- **ModelFallbackRunner 클래스**:
  - 우선순위 기반 모델 순서 (마지막 성공 → 선호 → 나머지)
  - 재시도 + 지수 백오프
  - 에러 유형별 대기 시간 (Rate Limit: 5초, Overloaded: 3초 등)
  - 폴백 이벤트 콜백 지원
  - `FallbackResult` 반환 (성공 여부, 사용 모델, 시도 횟수, 실패 이유)

---

#### 3. code_executor.py 고도화 (claude_company 패턴)

**기존:**
- macOS/Linux만 지원
- 기본적인 subprocess 실행

**개선:**
- **크로스 플랫폼 지원**: Windows/macOS/Linux
  - Windows: cmd.exe 래퍼, STARTUPINFO 설정
  - Unix: 표준 asyncio subprocess
- **Claude CLI 실행 파일 자동 탐색**: `find_claude_executable()`
- **긴 프롬프트 stdin 전송**: Windows 2000자, Unix 8000자 임계값
- **MCP 설정 자동 로딩**: `.mcp.json` 자동 생성
- **우아한 종료**: `_kill_current_process()`
  1. terminate() (SIGTERM) 시도
  2. 5초 대기
  3. kill() (SIGKILL) 강제 종료
- **경로 검증**: 디렉토리 순회 공격 방지
- **세션 관리**: `list_storage_files()`, `read_storage_file()`, `cleanup_all_sessions()`

---

---

### 2026-03-05 업데이트 (3) - UI/UX 고도화 (Geny 참고) ✅ 완료

#### 1. Dashboard 탭 추가 ✅

**목적:**
- 에이전트 상태 실시간 모니터링
- 최근 활동 타임라인 표시
- 시스템 상태 한눈에 파악

**UI 레이아웃:**
```
┌─────────────────────────────────────┬─────────────────────────────┐
│ 에이전트 상태 (좌측)                   │ 활동 타임라인 (우측)          │
│ ● JX_CODER [작업중]                  │ 10:52:01 JX_CODER 작업 시작   │
│ ○ JX_RESEARCHER [대기]              │ 10:52:15 검색 완료            │
│ ✗ JX_WRITER [오류]                   │ 10:52:30 코드 생성 완료       │
├─────────────────────────────────────┼─────────────────────────────┤
│ 인프라 상태                           │ 통계 카드                     │
│ Redis: ● 연결됨                      │ 전체 작업 / 성공률 / 활성     │
│ Qdrant: ● 연결됨                     │ 에이전트 수 / 가동 시간        │
└─────────────────────────────────────┴─────────────────────────────┘
```

**구현 내용:**
- `frontend/src/components/tabs/DashboardTab.tsx` (신규 330줄)
- 통계 카드 4개: 시스템 상태, 활성 에이전트, 전체 작업, 평균 성공률
- 에이전트 상태 목록: 실시간 상태 + 현재 작업 + 노드 위치
- 활동 타임라인: 최근 10개 작업 로그 (성공/실패 아이콘)
- 인프라 상태: Redis, Qdrant, 가동 시간, 처리 작업 수
- 자동 갱신: 5초 간격 (ON/OFF 토글)
- `logsApi` 추가: getLogs(), getSummary()

---

#### 2. Graph 시각화 탭 추가 ✅

**목적:**
- JINXUS_CORE 워크플로우 노드 시각화
- 에이전트 실행 흐름 파악
- 현재 실행 중인 노드 하이라이트

**UI 레이아웃:**
```
┌─────────────────────────────────────────────────────────────────┐
│ [intake] → [decompose] → [dispatch] → [aggregate] → [respond]  │
│                              │                                  │
│              ┌───────────────┼───────────────┐                  │
│              ▼               ▼               ▼                  │
│         [JX_CODER]    [JX_RESEARCHER]   [JX_WRITER]            │
│                                                                 │
│  [범례: ○ 대기 | ● 실행중 | ✓ 완료 | ✗ 오류]                      │
└─────────────────────────────────────────────────────────────────┘
```

**구현 내용:**
- `frontend/src/components/tabs/GraphTab.tsx` (신규 290줄)
- 에이전트 선택 드롭다운 (JINXUS_CORE, JX_CODER 등)
- 노드 체인 시각화: 상태별 색상 (대기/실행중/완료/오류)
- 서브 에이전트 분기 표시 (JINXUS_CORE 선택 시)
- 속성 패널: 노드 클릭 시 상세 정보 표시
- 자동 갱신: 3초 간격 (실시간/정지 토글)
- 범례 표시
- 기존 백엔드 API 활용: `/agents/runtime/all`, `/agents/{name}/graph`

---

#### 3. 사이드바 및 라우팅 업데이트 ✅

**수정 파일:**
- `frontend/src/store/useAppStore.ts`: 탭 타입에 'dashboard', 'graph' 추가
- `frontend/src/components/Sidebar.tsx`: 대시보드, 그래프 메뉴 추가
- `frontend/src/app/page.tsx`: DashboardTab, GraphTab 라우팅 추가
- `frontend/src/lib/api.ts`: logsApi 추가 (getLogs, getSummary)

---

#### 향후 UI/UX 개선 예정

| 항목 | 설명 | 우선순위 |
|------|------|----------|
| 로그 필터링 강화 | 에이전트별/레벨별 필터 | 중간 |
| Command 탭 | 에이전트 직접 명령 실행 | 중간 |
| 워크플로우 편집기 | 드래그앤드롭 노드 편집 | 낮음 |
| 3D 플레이그라운드 | Three.js 시각화 | 낮음 |

---

### 2026-03-05 업데이트 (1)

#### 1. JS_PERSONA 에이전트 (신규)

**목적:**
- 진수 전용 자소서/포트폴리오 작성 에이전트
- JX_WRITER와 분리하여 개인화된 글쓰기 전담

**구현 내용:**

**`backend/jinxus/agents/js_persona.py` (신규):**
- 진수 프로필 로드 및 캐싱
- 회사 유형별 전략 (스타트업/빅테크/대기업/연구소)
- 문서 유형별 가이드 (자소서/포트폴리오/이력서/면접준비)
- 과거 자소서 장기기억 참조
- 프로필 업데이트 기능

**`backend/jinxus/agents/__init__.py`:**
- `JSPersona` import 및 레지스트리 등록

**`backend/jinxus/agents/jinxus_core.py`:**
- decompose 프롬프트에 JS_PERSONA 추가
- 자소서 요청 시 JS_PERSONA 자동 라우팅

**`backend/prompts/js_persona/system.md` (신규):**
- JS_PERSONA 시스템 프롬프트

---

#### 2. Daemon 모드 (신규)

**목적:**
- 24시간 백그라운드 자율 작동
- 스케줄 작업 자동 실행 및 자가 강화

**구현 내용:**

**`backend/jinxus/channels/daemon.py` (신규):**
- `JinxusDaemon` 클래스
- 스케줄 작업 콜백 연동
- 헬스체크 루프 (Redis/Qdrant 모니터링)
- 자가 강화 루프 (JinxLoop 6시간 주기)
- 백그라운드 작업 제출/관리
- 시그널 핸들링 (graceful shutdown)

**`backend/pyproject.toml`:**
- `jinxus-daemon` 엔트리포인트 추가

---

#### 3. 코드 정리 (CLAUDE.md 지시 수행)

**mcp_client.py:**
- 하드코딩 디버그 로그 (`/tmp/mcp_debug.log`) 4개 제거
- `logger.debug()` 사용으로 변경

**telegram_bot.py:**
- 미사용 함수 제거: `_escape_markdown()`, `send_photo()`, `send_document()`
- 총 69줄 감소

**task.py:**
- `_cleanup_old_tasks()` 함수 추가 (메모리 누수 방지)
- `MAX_TASKS = 100` 제한 추가
- `duration_ms` 계산 구현 (TODO 해결)
- `started_at` 필드 추가

---

#### 4. Agent History API 개선

**목적:**
- 에이전트 작업 이력 조회 시 벡터 검색 대신 SQLite 직접 조회로 효율성 개선

**구현 내용:**

**`backend/jinxus/api/routers/agents.py`:**
- `get_agent_history()` 개선:
  - 기존: `memory.search_long_term(agent_name, "", limit=limit)` (빈 쿼리로 벡터 검색)
  - 변경: `meta_store.get_recent_logs(agent_name, limit, offset)` (SQLite 직접 조회)
- `offset` 파라미터 추가 (페이지네이션 지원)
- `total` 필드에 정확한 전체 로그 수 반환
- 미사용 `get_jinx_memory()` import 제거

---

#### 6. 미사용 Import 정리 (CLAUDE.md 지시)

**목적:**
- 불필요한 import 제거로 코드 경량화
- 메모리 효율성 개선

**정리된 파일들:**
- `agents/base_agent.py`: time, ToolResult, Any 제거
- `channels/cli.py`: get_settings 제거
- `channels/telegram_bot.py`: asyncio 제거
- `tools/scheduler.py`: asyncio, get_settings 제거
- `tools/system_manager.py`: timedelta 제거
- `tools/prompt_version_manager.py`: re, datetime 제거
- `tools/mcp_client.py`: asyncio 제거
- `tools/cache_manager.py`: datetime 제거
- `tools/dynamic_executor.py`: Any 제거
- `tools/base.py`: datetime 제거
- `tools/file_manager.py`: Optional, os 제거
- `core/background_worker.py`: Any 제거
- `core/jinx_loop.py`: datetime 제거
- `api/routers/logs.py`: datetime 제거
- `api/routers/memory.py`: MemorySearchRequest 제거
- `api/models/request.py`: Enum 제거
- `api/models/response.py`: datetime, Any 제거
- `hr/agent_factory.py`: Optional, Dict 제거
- `hr/manager.py`: DynamicAgent 제거

---

#### 5. Dynamic Tool Executor 개선

**목적:**
- MCP 도구 잘못 선택 문제 해결

**구현 내용:**

**`backend/jinxus/tools/dynamic_executor.py`:**
- `TOOL_SELECTION_GUIDE` 상수 추가 (80줄 분량 가이드라인)
- GitHub/파일시스템/웹검색/Git 작업별 명확한 도구 매핑
- `execute()` 메서드에서 시스템 프롬프트에 가이드라인 자동 추가

---

## 버전 v1.2.1 (진행 중)

### 2026-03-03 업데이트 (오후)

#### 1. 스케줄 작업 영속화

**목적:**
- APScheduler 스케줄 작업을 SQLite에 저장하여 서버 재시작 시 자동 복구
- 스케줄 작업 완료 시 텔레그램 알림 전송

**구현 내용:**

**`backend/jinxus/tools/scheduler.py`:**
- `meta_store` 연동: 스케줄 작업 SQLite 저장
- `restore_from_db()`: 서버 시작 시 DB에서 작업 복구
- `_execute_scheduled_task()`: JINXUS_CORE를 통해 작업 실행 + 알림
- add/remove/pause/resume 시 DB 상태 동기화

**`backend/jinxus/api/server.py`:**
- 서버 시작 시 스케줄러 자동 복구
- JINXUS_CORE 콜백 연결
- 텔레그램 알림 콜백 연결

**`backend/jinxus/channels/telegram_bot.py`:**
- `get_telegram_send_func()`: 스케줄러용 알림 함수 반환

---

#### 2. 프롬프트 버전 동기화

**목적:**
- 프롬프트 파일과 SQLite DB 간 동기화
- 버전 히스토리 관리 및 롤백 지원
- prompts/{agent}/versions/ 디렉토리에 자동 백업

**구현 내용:**

**`backend/jinxus/tools/prompt_version_manager.py` (신규):**
- JX_OPS 전용 도구
- 액션:
  - `sync`: 모든 에이전트 프롬프트 파일↔DB 동기화
  - `list`: 버전 히스토리 조회
  - `get`: 특정 버전 내용 조회
  - `rollback`: 이전 버전으로 롤백 (파일+DB)
  - `save`: 새 버전 저장
- 서버 시작 시 자동 동기화 (`sync_all_prompts()`)

**`backend/jinxus/tools/__init__.py`:**
- `PromptVersionManager` 등록

**`backend/jinxus/config/settings.py`:**
- `backend_root` property 추가 (prompts_dir 경로 수정)

---

#### 3. Task API 텔레그램 알림 연동

**목적:**
- `/task` API로 생성된 작업의 시작/완료/실패 시 텔레그램 알림 전송
- BackgroundWorker가 아닌 직접 Task API 사용 시에도 알림 지원

**구현 내용:**

**`backend/jinxus/api/routers/task.py`:**
- `_telegram_notify`: 전역 알림 콜백 변수
- `set_telegram_notify()`: 서버 시작 시 텔레그램 함수 연결
- `_run_task()` 내 알림 전송:
  - 🚀 작업 시작 알림 (task_id, 내용)
  - ✅ 작업 완료 알림 (task_id, 소요시간, 에이전트, 결과)
  - ❌ 작업 실패 알림 (task_id, 오류 내용)

**`backend/jinxus/api/server.py`:**
- lifespan에서 `set_telegram_notify(telegram_send_func)` 호출
- 텔레그램 봇 시작 직후 Task API에 알림 함수 연결

---

#### 4. 시스템 관리 도구 (이전 세션)

**`backend/jinxus/tools/system_manager.py`:**
- 세션 관리: list_sessions, clear_session, clear_all_sessions
- 작업 관리: list_tasks, clear_completed_tasks, cancel_task
- 메모리 관리: get_memory_stats, prune_memories, delete_memory
- 통계: get_agent_stats, get_system_status
- 텔레그램에서 자연어로 시스템 관리 가능 ("세션 지워", "작업 삭제해" 등)

---

#### 5. GitHub API Rate Limit 최적화 + 범용 캐싱

**목적:**
- GitHub API rate limit (5,000/hour) 최적화
- 모든 외부 API 호출에 Redis 캐싱 적용
- MCP 도구에도 자동 캐싱 지원

**구현 내용:**

**`backend/jinxus/tools/github_graphql.py` (신규):**
- GraphQL API로 REST API 여러 번 대신 한 번 호출
- 필요한 필드만 선택적 조회
- Redis 캐싱 (5분 TTL)
- Rate limit 자동 대기/재시도
- 액션:
  - `repo_overview`: 레포+브랜치+커밋+이슈+PR 한 번에 조회
  - `user_repos`: 사용자 레포 목록 (최대 100개)
  - `repo_files`: 레포 파일 트리 조회
  - `search_code`: 코드 검색
  - `raw_query`: 직접 GraphQL 쿼리 실행
  - `rate_limit`: 현재 rate limit 상태 조회

**`backend/jinxus/tools/cache_manager.py` (신규):**
- 범용 캐시 매니저 (GitHub, Brave Search, MCP 등 모든 외부 호출)
- 네임스페이스 분리: `github:`, `brave:`, `mcp:`, `web:`
- 서비스별 TTL 설정:
  - github: 300초 (5분)
  - brave: 600초 (10분)
  - mcp: 180초 (3분)
  - web: 120초 (2분)
- 캐시 통계 추적 (hits, misses, hit_rate)
- 편의 함수: `cache_get()`, `cache_set()`, `cache_clear()`, `cache_stats()`

**`backend/jinxus/tools/mcp_client.py` 수정:**
- `MCPToolAdapter`에 자동 캐싱 지원
- 읽기 전용 도구 패턴 자동 감지:
  - 캐싱 가능: `get_`, `list_`, `search_`, `read_`, `fetch_`, `query_`, `brave_web_search` 등
  - 캐싱 제외: `create_`, `update_`, `delete_`, `write_`, `navigate`, `click` 등

**`backend/jinxus/tools/system_manager.py` 수정:**
- 캐시 관리 액션 추가:
  - `get_cache_stats`: 캐시 통계 조회 (전체 키 수, 서비스별 분포, 히트율 등)
  - `clear_cache`: 캐시 정리 (전체 또는 네임스페이스별)
- 텔레그램에서 자연어로 관리 가능: "캐시 정리해", "GitHub 캐시만 지워", "캐시 상태 알려줘"

---

#### 6. JinxLoop A/B 테스트 완성

**목적:**
- 프롬프트 개선 시 실제 성능 비교를 통한 검증
- 기존 프롬프트 vs 새 프롬프트 A/B 테스트
- 10% 이상 개선 시에만 새 프롬프트 채택

**구현 내용:**

**`backend/jinxus/core/jinx_loop.py`:**
- `run_ab_test()`: A/B 테스트 실행 (기존 vs 새 프롬프트 비교)
- `_get_test_cases()`: 성공한 과거 작업에서 테스트 케이스 추출
- `_run_with_prompt()`: 특정 프롬프트로 작업 실행
- `_score_response()`: Claude를 사용해 응답 품질 점수화
- `improve_agent()` 내 A/B 테스트 통합: 테스트 실패 시 변경 차단

**`backend/jinxus/memory/meta_store.py`:**
- `log_task()`: output 컬럼 추가 (A/B 테스트용, 500자 제한)
- `log_ab_test()`: A/B 테스트 결과 SQLite 저장
- `get_successful_tasks()`: 성공 작업 + output 조회 (score >= 0.7, output 있는 것만)
- `agent_task_logs` 테이블: output 컬럼 추가 + 마이그레이션
- `ab_test_logs` 테이블: test_id, agent_name, old_score, new_score, winner, test_count

**`backend/jinxus/memory/jinx_memory.py`:**
- `log_agent_stat()`: output 파라미터 추가
- `log_ab_test()`: 파사드 메서드
- `get_successful_tasks()`: 파사드 메서드

**`backend/jinxus/agents/jinxus_core.py`:**
- `log_agent_stat()` 호출 시 `output=result.get("output")` 전달

**A/B 테스트 로직:**
1. `get_successful_tasks()`로 과거 성공 작업 추출 (input + output 쌍)
2. 각 테스트 케이스에 대해 기존/새 프롬프트로 실행
3. `_score_response()`로 품질 점수 평가 (0.0-1.0)
4. 평균 점수 비교, 10% 이상 개선 시 승리
5. 결과를 `ab_test_logs` 테이블에 기록

---

#### 7. Thinking Panel + SSE 스트리밍 취소

**목적:**
- 장시간 작업 시 AI의 사고 과정 실시간 표시
- 작업 중 사용자가 중지 버튼으로 취소 가능
- 백엔드 SSE 스트리밍 완전 취소 지원

**구현 내용:**

**`frontend/src/components/ThinkingPanel.tsx` (신규):**
- 실시간 Thinking 로그 표시 패널
- 작업 단계별 아이콘 + 시간 표시
- 작업 중지 버튼
- 접기/펼치기 토글

**`frontend/src/components/tabs/ChatTab.tsx` 수정:**
- ThinkingPanel 통합
- SSE 이벤트 → Thinking 로그 변환
  - `start` → 작업 시작
  - `manager_thinking` → 분석 단계
  - `decompose_done` → 작업 분해 완료
  - `agent_started/done` → 에이전트 상태
  - `cancelled` → 취소됨
- 토글 버튼 (🧠 로그)
- `handleStopTask()` → SSE 취소 API 호출

**`backend/jinxus/api/routers/chat.py` 수정:**
- `_cancel_events: Dict[str, asyncio.Event]` - 취소 이벤트 추적
- `POST /chat/cancel/{task_id}` - SSE 스트림 취소 엔드포인트
- `GET /chat/active` - 활성 스트림 목록
- 스트림 생성 시 취소 이벤트 체크

**`frontend/src/lib/api.ts` 수정:**
- `SSEEvent` 타입에 `detail`, `message` 필드 추가
- `chatApi.cancelStream(taskId)` - 스트림 취소 API
- `chatApi.getActiveStreams()` - 활성 스트림 조회

**UI 레이아웃:**
```
┌─────────────────────────────────────┬──────────────────────┐
│ 채팅 영역                            │ 🧠 Thinking Log      │
│                                     │ ────────────────────│
│                                     │ 📥 10:52:01 입력 분석 │
│                                     │ 🔍 10:52:03 작업 분해 │
│                                     │ 🤖 10:52:05 JX_CODER │
│                                     │ [⏹️ 작업 중지]        │
└─────────────────────────────────────┴──────────────────────┘
```

---

## 버전 v1.2.0 (완료)

### 2026-03-03 업데이트 (오전)

#### 1. MCP 연결 상태 관리 UI

**백엔드 변경사항:**
- `backend/jinxus/api/routers/status.py`: MCP 상태 API 엔드포인트 추가
  - `GET /status/mcp`: 모든 MCP 서버 연결 상태 조회
  - `POST /status/mcp/reconnect/{server_name}`: 특정 서버 재연결
- `backend/jinxus/config/mcp_servers.py`: `requires_api_key` 필드 추가
  - API 키 필요 여부를 명시하여 상태 정확도 향상

**프론트엔드 변경사항:**
- `frontend/src/components/tabs/ToolsTab.tsx`: MCP 상태 UI 신규 생성
  - 서버별 연결 상태 표시 (connected/disconnected/api_key_missing/disabled)
  - 도구 목록 확장/축소 기능
  - 재연결 버튼
- `frontend/src/lib/api.ts`: MCP 상태 타입 정의 추가
- `frontend/src/store/useAppStore.ts`: tools 탭 타입 추가
- `frontend/src/components/Sidebar.tsx`: "도구" 메뉴 항목 추가
- `frontend/src/app/page.tsx`: ToolsTab 라우팅 추가

---

#### 2. 백그라운드 작업 진행 보고 (Progress Callback)

**목적:**
- 백그라운드에서 실행되는 장시간 작업의 중간 진행 상황을 텔레그램 등으로 보고
- 사용자가 작업 진행 상태를 실시간으로 파악 가능

**구현 내용:**

**`backend/jinxus/agents/jinxus_core.py`:**
- `ManagerState`에 `progress_callback` 필드 추가
- `run()` 메서드에 `progress_callback` 파라미터 추가
- `_dispatch_node()`에서 작업 분해 완료 시 보고
- `_execute_sequential()`에서 각 에이전트 시작/완료 시 보고
- `_execute_parallel()`에서 병렬 실행 시작 시 보고

**`backend/jinxus/core/orchestrator.py`:**
- `run_task()` 메서드에 `progress_callback` 파라미터 추가
- JinxusCore.run()에 콜백 전달

**`backend/jinxus/core/background_worker.py`:**
- `_execute_task()`에서 `progress_callback` 람다 생성
- `notify_callback`이 있는 경우에만 진행 보고 활성화

**진행 보고 예시 (텔레그램):**
```
📊 진행 보고
📋 작업 분해 완료: 3개 서브태스크 (sequential 모드)

📊 진행 보고
🔄 [1/3] JX_RESEARCHER 실행 중...

📊 진행 보고
   ✓ JX_RESEARCHER 완료 (점수: 0.9)
```

---

#### 3. MCP 도구 선택 문제 (완료)

**문제:**
- GitHub 레포지토리 분석 요청 시 github MCP 대신 filesystem MCP 선택
- "Path not allowed: /" 오류 발생

**해결 내용:**
- `backend/jinxus/tools/dynamic_executor.py`에 `TOOL_SELECTION_GUIDE` 추가
- 도구 유형별 명확한 사용 가이드라인 제공:
  - GitHub 작업: `mcp__github__*` 도구 사용
  - 파일 시스템: `mcp__filesystem__*` 도구 사용
  - 웹 검색/크롤링: `mcp__brave_search__*`, `mcp__fetch__*`, `mcp__playwright__*`
  - Git 작업: `mcp__git__*` 도구 사용
- `execute()` 메서드에서 시스템 프롬프트에 가이드라인 자동 추가

---

## 버전 v1.1.0 (완료)

### 주요 기능
- SSE 스트리밍 실시간 토큰 출력
- 채팅 히스토리 세션 관리
- 에이전트 API 모듈 바인딩 문제 수정
- GitHub list_user_repos 기능 수정

---

## 파일 구조

```
backend/jinxus/
├── agents/
│   ├── jinxus_core.py     # 총괄 지휘관 (progress_callback 지원)
│   ├── jx_coder.py        # 코딩 에이전트
│   ├── jx_researcher.py   # 리서치 에이전트
│   ├── jx_writer.py       # 작문 에이전트
│   ├── jx_analyst.py      # 분석 에이전트
│   └── jx_ops.py          # 운영 에이전트 (system_manager, prompt_version_manager)
├── core/
│   ├── orchestrator.py    # 오케스트레이터 (progress_callback 전달)
│   ├── background_worker.py  # 백그라운드 워커 (progress_callback 생성)
│   └── jinx_loop.py       # 자가 강화 엔진 (A/B 테스트 완성)
├── tools/
│   ├── scheduler.py       # 스케줄러 (SQLite 영속화, 자동 복구)
│   ├── system_manager.py  # 시스템 관리 도구 (세션/작업/메모리/캐시)
│   ├── prompt_version_manager.py  # 프롬프트 버전 관리 (v1.2.1)
│   ├── github_graphql.py  # GitHub GraphQL API (rate limit 최적화)
│   └── cache_manager.py   # 범용 캐시 매니저 (Redis 기반)
├── memory/
│   ├── meta_store.py      # SQLite 메타 저장소 (scheduled_tasks, ab_test_logs)
│   └── jinx_memory.py     # 통합 메모리 파사드 (A/B 테스트 메서드 포함)
├── api/
│   ├── server.py          # 서버 (스케줄러 초기화, 프롬프트 동기화, Task API 알림 연결)
│   └── routers/
│       ├── chat.py        # Chat API (SSE 스트리밍 + 취소 지원)
│       ├── status.py      # MCP 상태 API
│       └── task.py        # Task API (텔레그램 알림 지원)
├── channels/
│   └── telegram_bot.py    # 텔레그램 봇 (get_telegram_send_func 추가)
└── config/
    ├── settings.py        # 설정 (backend_root property)
    └── mcp_servers.py     # MCP 서버 설정

backend/prompts/
├── {agent}/
│   ├── system.md          # 현재 활성 프롬프트
│   └── versions/          # 버전 백업 (자동 생성)
│       └── v1.0.md

frontend/src/
├── components/
│   ├── ThinkingPanel.tsx  # Thinking 로그 패널 + 중지 버튼 (v1.2.1)
│   └── tabs/
│       ├── ChatTab.tsx    # 채팅 탭 (ThinkingPanel 통합)
│       └── ToolsTab.tsx   # MCP 상태 UI
├── lib/
│   └── api.ts             # API 타입 정의 (SSE 취소 추가)
└── store/
    └── useAppStore.ts     # 상태 관리
```
