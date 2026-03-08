# JINXUS 개발 현황

## 버전 v1.4.0 (진행 중)

### 2026-03-08 코드 품질 + Geny 레퍼런스 기반 개선

> 참고: [Geny](https://github.com/CocoRoF/Geny) 심층 분석 → `docs/07_GENY_ANALYSIS.md`

#### 백엔드 개선

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| B-1 | ModelFallbackRunner 실사용 통합 | 완료 | decompose/aggregate/direct_response에 폴백 러너 통합, run_stream은 기존 유지 |
| B-2 | 난이도 기반 그래프 분기 (Geny 패턴) | 완료 | _classify_input에 패턴 매칭 추가 + run_stream에도 chat 분기 적용 → decompose LLM 호출 절약 |
| B-3 | Session Freshness Policy (Geny 패턴) | 완료 | `core/session_freshness.py` 신규 — 4단계 평가(FRESH/WARN/COMPACT/RESET). `short_term.py`에 세션 메타데이터(created_at/last_active/iteration_count) 추가. `jinxus_core.py` run()/run_stream() 진입부에서 평가 호출, RESET시 세션 클리어, COMPACT시 KEEP_RECENT 20개 유지 |
| B-4 | LangGraph Checkpointer (Geny 패턴) | 완료 | SQLite 기반 그래프 상태 영속화 → 서버 재시작 시 작업 재개. `core/checkpointer.py` 신규, `base_agent.py`에 체크포인터 주입 + thread_id 전달 |
| B-5 | Resilience Node 패턴 (Geny 패턴) | 완료 | `pre_execute_guard` + `post_execute` 노드를 그래프에 삽입. ContextGuard 예산 체크/컴팩션 + 완료 신호 감지(`[TASK_COMPLETE]`, `[BLOCKED]`, `[ERROR]`) + 신호 마커 제거. `state_tracker.py`에 `PRE_EXECUTE_GUARD`/`POST_EXECUTE` GraphNode 추가, `AgentState`에 `iteration_count`/`completion_signal`/`completion_reason` 추가 |
| B-6 | Tool Policy Engine (Geny 패턴) | 예정 | 에이전트 역할별 MCP 서버 접근 화이트리스트 필터링 |
| B-7 | DynamicExecutor 도구 호출 제한 상향 | 완료 | `max_tool_rounds` 5 → 15. GitHub 레포 분석 등 다단계 도구 호출 작업에서 조기 중단 방지 |
| B-8 | SSE 에이전트 진행 이벤트 상세화 | 완료 | `run_stream`에서 `progress_callback` 연결, `agent_started`에 `instruction` 필드 추가. Thinking Log에서 어떤 에이전트가 무슨 작업을 하는지 실시간 확인 가능 |

#### 프론트엔드 개선

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| F-1 | AgentCard N+1 폴링 제거 | 완료 | AgentsTab에서 getAllRuntimeStatus() 일괄 fetch → AgentCard에 runtime prop 전달 |
| F-2 | Error Boundary 추가 | 완료 | ErrorBoundary.tsx 생성, page.tsx에서 각 탭을 래핑 (key={activeTab}로 탭 전환 시 리셋) |
| F-3 | 반응형 레이아웃 기본 대응 | 완료 | Sidebar 모바일 햄버거 메뉴, Header 모바일 축약, DashboardTab 반응형 grid |
| F-4 | 접근성 (a11y) 기본 대응 | 완료 | Sidebar aria-current/aria-label, Header 반응형, nav aria-label |
| F-5 | AgentGraph 폴링 통일 | 완료 | 2s → 5s 통일 |
| F-6 | Skeleton 로딩 UI | 완료 | Skeleton.tsx 컴포넌트 (StatCard/AgentCard/LogRow/List), DashboardTab 스켈레톤 적용 |
| F-7 | 시간대 KST 24시간 통일 | 완료 | 모든 타임스탬프에 `timeZone: 'Asia/Seoul'`, `hour12: false` 적용 (ChatTab, ThinkingPanel, DashboardTab, LogsTab, TasksDropdown) |
| F-8 | 탭 전환 시 채팅 유지 | 완료 | ChatTab을 항상 마운트 (CSS hidden), 탭 이동해도 SSE 스트리밍 끊기지 않음 |
| F-9 | 헤더 중복 제거 + 사이드바 로고 황금색 | 완료 | Header의 "JINXUS v1.3.0" 제거, Sidebar 로고를 `text-primary` (황금색)으로 변경 |
| F-10 | Thinking Log 상세화 | 완료 | 에이전트명 + 작업 내용(instruction) 표시, step 아이콘/라벨 추가 (classify, tool_graph, agent_progress 등) |

#### 향후 개선 예정

| # | 항목 | 설명 | 우선순위 |
|---|------|------|----------|
| B-6 | Tool Policy Engine | 에이전트 역할별 MCP 서버 접근 화이트리스트 필터링 | 중간 |
| B-9 | ToolGraph 개선 | find_similar_workflows 유사도, retrieve_with_history 활용, agent_name 필터 | 낮음 |
| F-11 | 실시간 도구 호출 로그 | 에이전트 내부 도구 호출을 실시간 SSE로 전달 (현재는 완료 후 일괄 전달) | 중간 |
| F-12 | 3D 플레이그라운드 | Three.js 기반 에이전트 시각화 | 낮음 |

---

## 버전 v1.3.0 (완료)

### 2026-03-08 그래프 기반 도구 탐색 엔진

> 참고: [graph-tool-call](https://github.com/SonAIengine/graph-tool-call) by 손성준

#### 1. ToolGraph 엔진 (`core/tool_graph.py`) — Phase 1
- `ToolNode`, `ToolEdge`, `Workflow` 데이터 모델
- 6가지 엣지 타입: REQUIRES, PRECEDES, COMPLEMENTARY, SIMILAR_TO, CONFLICTS_WITH, BELONGS_TO
- BFS 탐색 + 위상 정렬로 워크플로우 자동 구성
- 키워드 매칭 기반 seed 노드 탐색 → 그래프 확장 → 점수 순 정렬
- `build_jinxus_tool_graph()`: 기존 9개 도구를 노드로 자동 등록 + 수동 엣지 정의
- 노드/엣지 가중치 업데이트 (학습용 인터페이스)

#### 2. WorkflowExecutor (`core/workflow_executor.py`) — Phase 2
- ToolGraph.retrieve()로 탐색된 워크플로우를 순차 실행
- 각 노드 실행 결과를 다음 노드에 컨텍스트로 전달
- 실패 시 SIMILAR_TO 엣지로 대체 도구 자동 탐색
- 실행 결과 기반 그래프 가중치 학습 (성공 +0.1, 실패 -0.05)

#### 3. JINXUS_CORE 통합
- `jinxus_core.py`: decompose 단계에서 ToolGraph 워크플로우 탐색 추가
- `ManagerState`에 `tool_workflow` 필드 추가
- run() 및 run_stream() 양쪽에 통합
- SSE 이벤트에 `tool_graph` 스텝 추가 ("관련 도구 워크플로우 발견: ...")

#### 4. API 엔드포인트
- `GET /status/tool-graph` — 전체 도구 그래프 구조 조회
- `POST /status/tool-graph/retrieve` — 쿼리에서 워크플로우 탐색

#### 5. 프론트엔드 배포/개발 환경 개선
- **Cache-Control 헤더**: `next.config.js`에 `no-cache, no-store, must-revalidate` 적용 (브라우저 캐시 문제 방지)
- **generateBuildId**: 타임스탬프 기반 빌드 ID 생성 (프로덕션 빌드 캐시 무효화)
- **개발 모드 스크립트**: `dev.sh` — `next dev` 핫리로드 (코드 수정 시 자동 반영)
- **프로덕션 빌드 스크립트**: `rebuild.sh` — 프로세스 종료 → 캐시 삭제 → 빌드 → 서버 시작 자동화
- **버전 통일**: 전체 UI v1.1.0 → v1.3.0 업데이트 (Sidebar, Header, SettingsTab)
- **태그라인 제거**: "주인님의 충실한 AI 비서" 문구 삭제 (Header, layout.tsx 메타태그)
- **백엔드 버전 동기화**: server.py FastAPI 메타데이터 + 루트 엔드포인트 v1.3.0

#### 5-2. 캐시 전략 및 코드 품질 개선
- **next.config.js 캐시 전략 세분화**: HTML/API는 no-cache, JS/CSS 번들은 immutable 장기 캐시 (파일명 hash 기반)
- **API cache-busting**: GET 요청에 `?_cb=timestamp` 자동 추가, `Cache-Control: no-cache` 헤더
- **SSE 파서 버그 수정**: event/data 쌍이 손실되던 문제 해결 — 빈 줄 기반 이벤트 구분자 처리, flush 로직 추가
- **AbortController 메모리 누수 방지**: ChatTab unmount 시 SSE 연결 자동 정리, `reader.releaseLock()` 호출
- **dev.sh / rebuild.sh 스크립트**: 개발 모드(핫리로드) / 프로덕션 빌드 자동화

#### 5-3. 프론트엔드 버그 수정 (3차)
- **AgentCard.tsx 폴링 주기 통일**: 3초 → 5초 (DashboardTab/GraphTab과 동일)
- **AgentCard.tsx 동적 Tailwind 클래스 버그**: `${getStatusColor()}/20` 컴파일 불가 → `getStatusBgColor()` 정적 클래스 함수 분리
- **LogsTab.tsx race condition 수정**: `deleteLog`/`deleteLogs`/`cleanup` 후 `fetchLogs()`에 `await` 누락 → 삭제 완료 전 fetch 시작되는 문제 해결
- **DashboardTab.tsx NaN 방지**: `agent_stats`가 빈 객체일 때 0으로 나누는 문제 수정 (count 체크 추가)
- **HireAgentModal.tsx Tailwind 동적 클래스 수정**: `bg-${color}-500/20` → 정적 클래스 문자열로 교체

#### 6. 프론트엔드 UI/UX 개선
- **마크다운 렌더링**: `react-markdown` + `remark-gfm` + `react-syntax-highlighter` 추가
  - `MarkdownRenderer.tsx` 컴포넌트 (코드블록 구문 강조, 복사 버튼, 테이블, 링크)
  - ChatTab의 AI 응답 + 스트리밍 컨텐츠에 적용 (사용자 메시지는 plain text 유지)
  - `@tailwindcss/typography` 플러그인 추가 (prose 클래스)
- **에러 토스트 UI**: `react-hot-toast` 추가
  - `layout.tsx`에 `Toaster` 컴포넌트 (dark 테마)
  - ChatTab: 세션 로드/삭제/메시지 전송 실패 시 토스트
  - LogsTab: `alert()` → `toast.success()` 교체
- **메시지 배열 길이 제한**: useAppStore `addMessage`에서 최대 300개 유지 (메모리 누수 방지)
- **중복 API 호출 제거**: page.tsx의 15초 systemStatus 갱신 제거 (각 탭이 자체 갱신 담당)

#### 6. 자율 멀티스텝 실행기 (`core/autonomous_runner.py`)
- `AutonomousRunner`: 복합 작업을 LLM으로 분해 → 각 단계를 순차 실행 → 중간 평가 → 계획 조정
- Sonnet으로 작업 계획 생성 (2~10 단계), 3스텝마다 중간 평가
- 이전 단계 결과를 다음 단계 컨텍스트로 전달 (최근 3개)
- 타임아웃 (기본 4시간), 최대 스텝 수 제한, 취소 지원
- `BackgroundWorker`에 `autonomous` 모드 통합
- 텔레그램 `/auto` 명령 추가 (복합 작업 자율 실행)
- Task API에 `autonomous`, `max_steps`, `timeout_seconds` 파라미터 추가

#### 7. 런타임 그래프 학습 — Phase 3
- `meta_store.py`: `workflow_patterns` 테이블 추가 (쿼리, 도구 시퀀스, 성공 여부, 사용 횟수)
- `save_workflow_pattern()`: 워크플로우 패턴 저장 (동일 시퀀스면 use_count 증가)
- `find_similar_workflows()`: 성공한 패턴을 사용 횟수 순으로 조회
- `WorkflowExecutor._learn_from_result()`: 실행 후 자동으로 패턴 저장 + 가중치 학습
- `ToolGraph.retrieve_with_history()`: 과거 성공 패턴 참고하여 가중치 부스트

---

## 버전 v1.2.4 (완료)

### 2026-03-08 코드 품질 개선 (3차)

#### 1. context_guard.py `should_block` 버그 수정
- `@property`로 항상 `False` 반환하던 버그 → 메서드로 변경
- `messages` 인자를 받아 `check()` 실행, status가 BLOCK/OVERFLOW이면 `True` 반환

#### 2. jinxus_core.py 로깅 개선
- 모듈 상단에 `import logging` + `logger = logging.getLogger(__name__)` 추가
- 2군데 인라인 로거 생성 (`import logging; logging.getLogger(__name__).debug(...)`) → 모듈 레벨 `logger` 사용으로 교체
- ToolGraph 탐색/워크플로우 실패 로깅: `debug` → `warning` 레벨 승격
- `_quick_web_search()` 웹 검색 폴백 실패 시 `logger.warning` 로깅 추가

#### 3. tool_graph.py 노드 초기화 TOOL_REGISTRY 자동 추출
- `build_jinxus_tool_graph()`의 하드코딩된 9개 노드 등록 → `TOOL_REGISTRY`에서 자동 추출
- 각 도구의 `name`, `description`, `allowed_agents`는 TOOL_REGISTRY에서 가져옴
- `keywords`, `category` 등 그래프 전용 메타데이터는 `_NODE_META` 수동 매핑으로 보완
- 새 도구 추가 시 TOOL_REGISTRY에만 등록하면 ToolGraph 노드 자동 반영
- 기존 수동 엣지 정의는 유지

#### 4. model_router.py 성공 모델 클래스 변수 승격
- `ModelFallbackRunner._last_success_model`을 인스턴스 변수 → 클래스 변수로 승격
- 같은 프로세스 내 모든 인스턴스(세션)에서 성공 모델 정보 공유
- `get_model_priority()`, `run()` 내 참조를 `ModelFallbackRunner._last_success_model`로 변경

---

### 2026-03-08 코드 품질 개선 (2차)

#### 1. system_manager.py 하드코딩 에이전트 목록 제거
- 3군데 하드코딩된 에이전트 배열 → `_get_all_agent_names()` 헬퍼로 동적 조회
- 오케스트레이터에서 등록된 에이전트를 런타임에 가져오고, 실패 시 폴백 목록 사용

#### 2. web_searcher.py search_news 노출
- `search_news()` 메서드가 `run()` 인터페이스에서 접근 불가 → `mode` 파라미터 추가
- `mode: "news"` 시 뉴스 검색, `mode: "search"` (기본) 시 일반 검색

#### 3. plugin_loader.py 완성
- `allowed_agents = []` (빈 리스트)를 "모든 에이전트 차단"으로 처리하던 버그 수정
- `not allowed` 조건으로 변경하여 빈 리스트 = 모든 에이전트 허용

#### 4. 플러그인 관리 API 추가
- `GET /plugins` - 로드된 플러그인 목록
- `GET /plugins/{name}` - 플러그인 상세 정보
- `POST /plugins/enable` - 플러그인 활성화
- `POST /plugins/disable` - 플러그인 비활성화
- `POST /plugins/reload` - 전체 재스캔

#### 5. README 버전 배지 업데이트
- `v1.1.0` → `v1.2.4`

---

## 버전 v1.2.3 (완료)

### 2026-03-08 코드 품질 개선

#### 1. LogsTab API 하드코딩 제거 (CRITICAL fix)
- `LogsTab.tsx`에서 `http://localhost:19000` 직접 호출 → `logsApi` (lib/api.ts) 경유로 전면 교체
- `logsApi`에 `deleteLog()`, `deleteLogs()`, `cleanup()` 메서드 추가
- 로컬 `TaskLog` 타입 중복 정의 제거 → `lib/api.ts`에서 import로 통일

#### 2. 중복 코드 / 미사용 import 정리
- `useAppStore.ts`: `fetchAgents()` 중복 함수 제거 → `loadAgents()` 하나로 통일
- `AgentsTab.tsx`: `fetchAgents` → `loadAgents` 교체
- `ChatTab.tsx`: 미사용 `next/image` import 제거, `<Image>` → `<img>` 교체
- `HireAgentModal.tsx`: 수집만 하고 전달 안 하던 `role` 파라미터를 `hrApi.hireAgent()`에 전달하도록 수정

#### 3. 백엔드 에러 핸들링 보강
- `github_agent.py`: 5군데 `except: pass` → `logger.warning/debug` 로깅 추가
- `github_graphql.py`: 2군데 `except: pass` → `logger.debug` 로깅 추가
- `cache_manager.py`: 3군데 `except: pass` → `logger.debug` 로깅 추가

#### 4. Scheduler Race Condition 해결
- `scheduler.py`: `asyncio.Lock` 추가 (`_jobs_lock`)
- `_add_job`, `_remove_job`, `_pause_job`, `_resume_job`에서 `_jobs` dict 접근 시 lock 적용

#### 5. 코드 정리
- `code_executor.py`: 함수 내부 `import shutil as sh` 중복 import 제거 → 전역 `shutil` 사용

#### 6. 프론트엔드 환경변수 분리
- `next.config.js`: `http://localhost:19000` 하드코딩 → `process.env.NEXT_PUBLIC_API_URL` 환경변수로 분리

#### 7. 에이전트 목록 동적 조회
- `LogsTab.tsx`: 하드코딩 에이전트 배열 → `useAppStore`의 `agents`에서 동적으로 생성

---

## 버전 v1.2.2 (완료)

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
- 자동 갱신: 5초 간격 (실시간/정지 토글)
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
│   ├── orchestrator.py        # 오케스트레이터 (progress_callback 전달)
│   ├── background_worker.py   # 백그라운드 워커 (autonomous 모드 지원)
│   ├── autonomous_runner.py   # 자율 멀티스텝 실행기 (v1.3.0)
│   ├── tool_graph.py          # ToolGraph 엔진 (v1.3.0)
│   ├── workflow_executor.py   # 워크플로우 실행기 (v1.3.0)
│   ├── context_guard.py        # 컨텍스트 윈도우 가드 (pre_execute_guard 노드에서 호출)
│   ├── checkpointer.py        # LangGraph Checkpointer (B-4, SqliteSaver/MemorySaver)
│   └── jinx_loop.py           # 자가 강화 엔진 (A/B 테스트 완성)
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
