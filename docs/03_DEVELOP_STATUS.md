# JINXUS 개발 현황

## v4.1.1 (2026-04-04) — 버그픽스: 도구 사용 불가 / 로그 소실 / 병렬 이벤트

### 수정된 버그 3건

1. **도구 사용 불가 (모든 에이전트)**: `JXResearcher`, `JXCoder`, 코딩/리서치 전문가 에이전트 10개가 `BaseAgent`를 상속하지 않아 `_make_tool_callback()` 메서드 누락 → `DynamicToolExecutor` 실행 시 `AttributeError` 발생 → MCP/도구 사용 전체 실패. `AgentCallbackMixin` 클래스 도입 후 모든 에이전트가 상속.

2. **미션 완료 후 로그 소실**: `mission_executor.py`에서 `save(mission)` 호출 시 로컬 객체(빈 `agent_conversations`)로 Redis를 덮어씀. `add_conversation()`이 Redis에 저장한 대화 로그가 전부 소멸. `_sync_conversations()` 메서드 도입 — `save()` 전 Redis에서 최신 conversations 동기화 (v4 executor 패턴 적용).

3. **순차 실행 시 agent_started 순서 오류**: 모든 에이전트 `agent_started` 이벤트를 실행 전 일괄 전송하여 병렬/순차 구분 불가. 병렬 모드는 유지, 순차 모드는 각 에이전트 실행 직전에 구조화 콜백(`{{specialist_started:NAME}}`)으로 전송하도록 수정.

| 파일 | 변경 내용 |
|------|---------|
| `agents/base_agent.py` | `AgentCallbackMixin` 클래스 추가 (`_make_tool_callback`, `_report_progress`). `BaseAgent`가 상속 |
| `agents/jx_researcher.py`, `jx_coder.py` | `AgentCallbackMixin` 상속 추가 |
| `agents/research/*.py` (3개) | `AgentCallbackMixin` 상속 추가 |
| `agents/coding/*.py` (5개) | `AgentCallbackMixin` 상속 추가 |
| `core/mission_executor.py` | `_sync_conversations()` 추가, 모든 `save()` 전 동기화 |
| `agents/jinxus_core.py` | 순차 모드에서 `agent_started` 이벤트를 실행 직전 콜백으로 전송 |

### 추가 수정 (v4.1.1b)

4. **태스크로그에 JX_ 코드 노출**: `base_agent.py`의 `AgentCallbackMixin._make_tool_callback`·`_report_progress`에서 `self.name` (raw `JX_RESEARCHER` 등) 그대로 노출. `_agent_display_name()` 함수로 페르소나 Korean name 변환. `jx_researcher._run_specialist`·`jx_coder._run_specialist` 내 fallback 메시지도 동일 적용.

| 파일 | 변경 내용 |
|------|---------|
| `agents/base_agent.py` | `_agent_display_name()` 함수 추가, `AgentCallbackMixin`에서 활용 |
| `agents/jx_researcher.py` | `_agent_display_name` import + `_run_specialist` 메시지 한국어 이름 변환 |
| `agents/jx_coder.py` | `_agent_display_name` import + `_run_specialist` fallback 메시지 변환 |

## v4.1.0 (2026-04-03) — 화이트보드 시스템 (AAI Phase 2)

AAI 로드맵 2단계 "Shared Whiteboard" 구현. 복도 중앙에 대형 화이트보드를 설치하고,
에이전트가 자율적으로 발견 → CORE에 보고 → 자동 미션 생성하는 파이프라인 구축.

### 화이트보드 항목 2종류
- **지침사항(guideline)**: 업무 규칙. 항상 활성 상태로 미션 컨텍스트에 주입됨
- **메모(memo)**: 녹음/직접입력. 에이전트가 발견 시 자동으로 미션 생성 + 실행

### 백엔드

| 파일 | 설명 |
|------|------|
| `core/whiteboard.py` | WhiteboardStore (Redis) + WhiteboardItem 모델. 상태: new→seen→claimed→done→archived |
| `api/routers/whiteboard.py` | CRUD API + `POST /{id}/discover` (에이전트 발견 → 지침사항 수집 → 미션 자동 생성) |
| `api/routers/__init__.py` | whiteboard_router 등록 |
| `api/server.py` | 라우터 포함 + WhiteboardStore Redis 종료 처리 |

### 프론트엔드

| 파일 | 설명 |
|------|------|
| `map/mapData.ts` | 복도 중앙(col:20, row:18)에 `main_whiteboard` POI + `wb_main` 가구(3타일 너비) |
| `sprites/furniture.ts` | `makeMainWhiteboard()` — 포스트잇 스타일 대형 화이트보드 스프라이트 |
| `WhiteboardPanel.tsx` | 모달 오버레이 — 전체/지침/메모 탭, CRUD, 상태 뱃지, 태그 |
| `PixelOffice.tsx` | ① 클릭 감지(타일 19-21, 17-18) → 패널 오픈 ② 에이전트 POI 도착 시 새 메모 발견 → discover API → 자동 미션 ③ 글로우+뱃지 시각 효과 ④ 30초 폴링 |
| `api.ts` | `whiteboardApi` — listAll/getGuidelines/getNewMemos/createItem/updateItem/deleteItem/discoverItem |
| `store/useAppStore.ts` | `whiteboardOpen` / `setWhiteboardOpen` 상태 |
| `app/page.tsx` | WhiteboardPanel 글로벌 오버레이 마운트 |

### JX_SECRETARY — WaveNoter 자동 동기화 에이전트

| 파일 | 설명 |
|------|------|
| `agents/personas.py` | JX_SECRETARY(정소율) 페르소나 — 경영팀, 비서, rank 3 |
| `config/mcp_servers.py` | Playwright MCP allowed_agents에 JX_SECRETARY 추가 |
| `core/wavenote_sync.py` | WaveNoter 루틴 정의 — 미션 템플릿 + 서버 시작 시 자동 등록 |
| `api/server.py` | lifespan에 `ensure_wavenote_routine()` 호출 |
| `frontend/src/lib/personas.ts` | JX_SECRETARY 정적 fallback 추가 |

**루틴 흐름:**
```
10분마다 (cron: */10 * * * *) → RoutineManager 트리거
  → JX_SECRETARY에게 미션 배정
  → Playwright(headless)로 app.wavenote.ai 접속
  → 새 녹음 확인 → 화이트보드 API(POST /whiteboard)로 메모 등록
  → 에이전트가 화이트보드에서 발견 → 자동 미션 생성
```

### 실행 흐름
```
사용자: 메모 등록 (UI 또는 API)
  → 화이트보드에 NEW 표시 (파란 글로우 + 빨간 뱃지)
  → 에이전트가 배회 중 main_whiteboard POI 방문
  → "📋 확인 중..." 말풍선 + 8-13초 체류
  → NEW 메모 있으면 discover API 호출
  → 지침사항도 미션 프롬프트에 함께 주입
  → JINXUS_CORE가 미션 분류 → 에이전트 배정 → 실행
  → OFFICE FEED에 "화이트보드에서 발견 → 미션 생성" 기록
```

---

## v4.0.0 (2026-04-01) — AAI 인프라 + Geny/Paperclip 패턴 도입

Geny(자율주행 에이전트)와 Paperclip(회사 시뮬레이션)의 핵심 패턴을 분석하고 JINXUS에 적용.
Agent-Agent Interaction(AAI) 로드맵의 인프라 기반을 구축.

### 백엔드 신규 모듈 (core/)

| 모듈 | 출처 | 설명 |
|------|------|------|
| `structured_output.py` | Geny | Pydantic 스키마 주입 → LLM → 검증 실패 시 correction prompt 2단계 재시도 |
| `inbox.py` | Geny | Redis 기반 에이전트 간 1:1 비동기 메시지 큐 (deliver/read/mark_read) |
| `relevance_gate.py` | Geny | 키워드+LLM 2단계 관련성 필터. broadcast 시 관련 에이전트만 반응 |
| `goals.py` | Paperclip | Goal Hierarchy (company→team→agent→task). 미션에 목적 연결 |
| `mission_lock.py` | Paperclip | Redis SETNX 기반 Atomic Checkout. 미션 이중 실행 방지 (409 Conflict) |
| `budget.py` | Paperclip | 에이전트별/월별 API 비용 추적. ok→warning→hard_stop 3단계 |
| `heartbeat.py` | Paperclip | 에이전트 주기적 깨어남 프로토콜. 체크리스트 기반 자율 실행 |
| `routine.py` | Paperclip | Cron 기반 반복 미션 자동 생성. skip_if_active/coalesce/always_enqueue |
| `config_revision.py` | Paperclip | 에이전트 설정 변경 리비전 관리 + 버전 롤백 |

### 기존 모듈 강화

| 모듈 | 변경 |
|------|------|
| `autonomous_runner.py` (v1.8.0) | Iteration Gate 3중 체크 (Completion Signal + Context Budget + Iteration Count) |
| `jinx_memory.py` (v2.1.0) | LLM 게이트 메모리 주입 — haiku로 "필요한가?" 판단 후 Qdrant 검색 |
| `context_guard.py` | (이미 구현됨) 모델별 context limit, warn/block 2단계, 자동 compaction |
| `completion_signals.py` | (이미 구현됨) TASK_COMPLETE/BLOCKED/ERROR/CONTINUE 파싱 |

### 에이전트 인격 파일화 (Paperclip SOUL.md 패턴)

- `data/souls/{agent}/SOUL.md` — 성격, 전략적 자세, 소통 스타일
- `data/souls/{agent}/RULES.md` — 행동 규칙, 금지 사항, 에스컬레이션
- `agents/soul_loader.py` — 파일 로드 + mtime 캐시 + 런타임 편집 API
- 6개 에이전트 SOUL.md 작성 (CORE, CODER, RESEARCHER, WRITER, ANALYST, OPS)

### API (routers/aai.py)

`/aai` 접두사로 통합 라우터:
- Inbox: POST/GET /aai/inbox, /aai/inbox/unread/all
- Goals: CRUD /aai/goals, /aai/goals/{id}/hierarchy, /aai/goals/link-mission
- Heartbeat: POST /aai/heartbeat/wake, GET /aai/heartbeat/status
- Mission Lock: POST /aai/mission-lock/{id}/checkout, /release
- Budget: POST /aai/budget/record, GET /aai/budget/{agent}, /aai/budget
- Routine: CRUD /aai/routines, /aai/routines/{id}/runs
- Config Revision: GET /aai/config-revision/{agent}, POST .../rollback/{version}
- Soul: GET/POST /aai/souls, /aai/souls/{agent}

### 프론트엔드

- `lib/toast-gate.ts` — 이벤트 폭주 시 카테고리별 10초/3개 rate limiting (Paperclip 패턴)

### Autopilot 탭 — 에이전트 자율 행동 관리 UI

Geny, Stanford Generative Agents, AgentOffice, Smashing Magazine UX 패턴 조사 기반 구현.
백엔드 AAI 인프라(heartbeat, routine, inbox, budget, goals, trigger)의 프론트엔드 UI를 신규 구축.

**백엔드 추가:**
| 모듈 | 설명 |
|------|------|
| `core/trigger_engine.py` | 트리거 레지스트리 (cron/event/idle/interaction/threshold). Redis 영속화. AutonomyConfig (에이전트별 자율 설정) |
| `api/routers/aai.py` 확장 | `/aai/autonomy` (자율 설정 CRUD), `/aai/triggers` (트리거 CRUD) |

**프론트엔드 구조:**
| 컴포넌트 | 설명 |
|----------|------|
| `AutopilotTab.tsx` | 메인 탭 (서브탭 5개 라우팅) |
| `autopilot/ControlPanel.tsx` | 에이전트 그리드 + Autonomy Dial (4단계: 관찰/계획/확인후실행/자율실행) + 하트비트 + 깨우기 + 마스터 토글 |
| `autopilot/TriggerPanel.tsx` | 트리거 CRUD + 5가지 유형별 설정 폼 (cron/event/idle/interaction/threshold) |
| `autopilot/CommsPanel.tsx` | 에이전트 간 인박스 뷰어 + 메시지 보내기 (채팅 UI) |
| `autopilot/BudgetPanel.tsx` | 에이전트별 API 비용 대시보드 + 예산 수정 + 모델별 분포 + 월 선택기 |
| `autopilot/RoutinePanel.tsx` | Cron 루틴 CRUD + 실행 이력 + cron→한국어 변환 |

**API 배선:** `lib/api.ts`에 `aaiApi` 네임스페이스 (heartbeat/autonomy/triggers/routines/inbox/budget 전체)

**UX 패턴:**
- Autonomy Dial: Smashing Magazine "Shared Autonomy Controls" 패턴 (Watch→Plan→Confirm→Auto 4단계)
- Bounded Autonomy: 에이전트별 자율성 레벨 독립 설정
- Trigger Engine: 5가지 트리거 유형 (시간/이벤트/유휴/상호작용/임계값)

### Geny 프론트엔드 12개 개선 (이어서 완료)

| # | 항목 | 상태 |
|---|------|------|
| 1 | ExecutionTimeline (수직 타임라인 + 컬러 노드 + glow) | 완료 |
| 2 | DiffViewer → FileChangeBadge 대체 구현 | 완료 |
| 3 | thinking_preview (opacity + truncate) | 완료 |
| 4 | FileChangeSummary (파일명+op 배지) | 완료 |
| 5 | Dev Mode 토글 (Sidebar DEV 버튼) | 완료 |
| 6 | DateDivider (CompanyChat 날짜 구분선) | 완료 |
| 7 | CSS 변수 이중 테마 (:root dark + html.light) | 완료 |
| 8 | **메모리 파일 트리** — 카테고리 하위에 실제 결과 노드 트리, 중요도 dot, 접기/펼치기 | 완료 |
| 9 | **스키마 기반 Settings** — `/status/config/schema` API + SettingsTab 동적 설정 폼 (그룹별 필드, 런타임 변경) | 완료 |
| 10 | 세션 상태 dot + glow (이미 구현됨) | 완료 |
| 11 | **React Flow 워크플로우 에디터** — @xyflow/react 기반 에이전트 실행 그래프 시각화 (BFS 계층 레이아웃, MiniMap, Controls) | 완료 |
| 12 | Live2D 아바타 | 미진행 (대규모 작업) |

### 에이전트 내부 이름 노출 방지

- `mission_executor.py`: 모든 SSE 이벤트(`from`, `to`, `agent`, `agents`, `agents_used`, `participants`)에서 내부 코드명(JX_CODER 등) → 한국어 표시 이름(이민준 등)으로 자동 치환
- `_display_name()` / `_display_names()` 헬퍼 함수 (personas.py `get_all_personas()` 활용)
- 업무노트 자동 생성 시 에이전트 이름도 치환

---

## v3.3.3 (2026-03-30) — UI/UX 접근성 & 인터랙션 일괄 개선

[ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) 레포의 99개 UX 가이드라인 + 44개 React 퍼포먼스 규칙 기반 분석 후 적용.

### 접근성 (WCAG 준수)
- **뷰포트 줌 차단 해제**: `maximumScale: 1, userScalable: false` 제거 (WCAG 2.1 SC 1.4.4 위반)
- **Skip link 추가**: 키보드/스크린리더 사용자가 네비게이션 건너뛰고 본문 직행 (`#main-content`)
- **aria-live 상태 알림**: Header 인프라 상태 영역에 `role="status" aria-live="polite"` 적용
- **색상 외 텍스트 보조**: 연결 상태에 `sr-only` 텍스트("연결됨"/"연결 끊김") 추가 — 색상만으로 정보 전달 방지
- **ErrorBoundary role="alert"**: 에러 메시지에 스크린리더 즉시 알림 + 복구 안내 문구 추가
- **Toast aria 속성**: 에러 토스트에 `role="alert" aria-live="assertive"` 적용

### 모션 & 인터랙션
- **prefers-reduced-motion 전역 지원**: 모든 애니메이션/트랜지션 0.01ms로 단축 (globals.css)
- **motion-reduce 클래스**: Skeleton, TasksDropdown 스피너에 `motion-reduce:animate-none` 적용
- **press-feedback 유틸**: 버튼/카드 클릭 시 `scale(0.97)` 눌림 효과 (150ms ease-out)
- **focus-ring 유틸**: `focus-visible` 시 primary 컬러 4px 링 (키보드 탐색 시각화)
- **ESC 키 닫기**: TasksDropdown에 Escape 키 핸들러 추가

### 레이아웃 & 반응형
- **dvh 적용**: `h-screen` → `h-dvh`, `min-h-screen` → `min-h-dvh` (모바일 주소창 문제 해결)
- **z-index 스케일 시스템**: dropdown(10), sticky(20), overlay(30), modal(40), popover(50), toast(100)
- **touch-action: manipulation**: body 전역 적용 — 300ms 탭 딜레이 제거
- **overscroll-behavior**: body에 `overscroll-behavior-x: none`, 드롭다운에 `scroll-contain`

### 타이포그래피 & 숫자
- **tabular-nums**: Header 업타임, 작업 수, Sidebar 에이전트 통계 등 숫자 영역에 적용 — 자릿수 흔들림 방지
- **시맨틱 컬러 토큰**: CSS 변수 10종 추가 (primary, destructive, success, warning, info, muted, surface 등)
- **font-display: swap**: Inter, Fira Code에 적용 — FOIT(보이지 않는 텍스트) 방지
- **Google Fonts preconnect**: fonts.googleapis.com, fonts.gstatic.com 선제 연결

### UX 개선
- **빈 상태 개선**: LogsTab, ProjectsTab 빈 상태에 아이콘 + 제목 + 설명 패턴 적용
- **EmptyState 공용 컴포넌트**: `EmptyState`, `EmptySearchResult`, `EmptyLogs`, `EmptyMemory` 신규
- **Toast 자동 닫힘 명시**: 성공 3초, 일반 4초, 에러 6초 (기존: react-hot-toast 기본값)
- **트랜지션 토큰**: `duration-micro(150ms)`, `duration-normal(250ms)`, `duration-slow(400ms)` + easing 3종

### Tailwind 설정 확장
- `zIndex`: 6단계 스케일
- `transitionDuration`: micro/normal/slow 토큰
- `transitionTimingFunction`: enter(ease-out)/exit(ease-in)/spring 토큰
- `spacing`: icon-sm(16)/icon-md(20)/icon-lg(24) 토큰

### 미션 고아 정리 버그 수정 (`mission_executor.py`, `mission_executor_v4.py`)
- **기존**: 서버 재시작 시 IN_PROGRESS 미션을 무조건 FAILED 처리 → 실제 완료된 미션도 "중단" 표시
- **수정**: `result`가 있거나 서브태스크 전부 done이면 **COMPLETE로 복구**, 진짜 중단된 것만 FAILED

## v3.3.2 (2026-03-28) — GC/리소스 정리 + 미션 라우터 과분류 수정

### MissionRouter v2.0.0 — LLM 기반 미션 분류 (`mission_router.py`)
- **하드코딩 패턴 매칭 전면 제거** → haiku LLM 기반 분류로 교체
- 10자 이하 인사/잡담만 패턴으로 즉시 QUICK (LLM 호출 절약)
- 나머지 전부 LLM이 type(quick/standard/epic/raid) + title + agents를 JSON으로 판단
- LLM 실패 시 STANDARD fallback
- 에이전트도 LLM이 직접 선정 (기존: 키워드 매칭)
- 실제 테스트 8건 전부 정확 분류 (기존 하드코딩: 과반이 STANDARD로 잘못 분류)

### SQLite VACUUM (`meta_store.py`)
- `vacuum()` 메서드 추가 — 서버 시작 시 `cleanup_old_background_tasks()` 직후 자동 실행
- 삭제 후 빈 페이지 회수하여 DB 파일 크기 비대화 방지

### Qdrant 컬렉션 사이즈 가드 (`long_term.py`)
- `enforce_collection_cap()` — 컬렉션당 포인트 수 상한 (기본 10,000) 초과 시 importance 낮고 오래된 순으로 삭제
- `optimize_all_collections()`에 통합: 사이즈 가드 → 시간감쇠 정리 → 중복 제거 3단계
- 24시간 주기 외에도 상한 초과 시 즉시 정리되어 OOM 방지

### Redis 클라이언트 연결 누수 수정
- `ResponseCache.close()` 추가 (`core/response_cache.py`)
- `SharedWorkspace.close()` 추가 (`core/collaboration.py`)
- 서버 셧다운 캐스케이드에 두 클라이언트 종료 등록 (`api/server.py`)

## v3.3.1 (2026-03-28) — RAID 병렬 실행 수정 + 채팅 삭제 버그 수정

### RAID 미션 병렬 실행 개선 (`mission_executor_v4.py`)
- **전문가 에이전트 직접 배정**: `_decompose_task()` 에이전트 목록에서 `rank >= 2` 제한 제거 → 전문가(JX_FRONTEND, JX_BACKEND 등, rank=3)도 LLM이 직접 배정 가능
- **팀 구조 표시**: 에이전트를 팀별로 그룹핑하여 LLM에 전달 → 조직 구조 인지 후 적절한 분산 배정
- **분산 배정 원칙 프롬프트 추가**: "최소 2명 이상 분산", "전문가 우선 배정", "병렬 실행 극대화" 명시
- 기존: 코딩 작업이 JX_CODER(팀장)에게 전부 몰림 → 수정: JX_FRONTEND, JX_BACKEND 등에 직접 분산

### 세션 확보 안정화 (`session_manager.py`)
- `ensure_agents()`: 개별 에이전트 세션 생성 실패 시 해당 에이전트만 스킵 (기존: 한 명 실패하면 전체 중단)

### 채팅 삭제 버그 수정 (`channel.py`, `CompanyChat.tsx`, `api.ts`)
- **백엔드**: SSE `/channel/stream`에 `cleared_at` 파라미터 추가 → 삭제 시점 이전 히스토리 서버 측 필터링
- **프론트엔드**: SSE `type: 'history'` 이벤트도 `clearedAt` 필터 적용하여 정상 처리 (기존: history 이벤트 무시)
- **프론트엔드**: SSE 연결 시 `cleared_at` 파라미터를 서버에 전달하여 이중 필터링

## v3.3.0 (2026-03-27) — 논문 기반 에이전트 강화 (Agentic LLM Survey + SOTOPIA)

### Self-Refine 패턴 적용 (`jinx_loop.py`)
- **3단계 프롬프트 분리**: 기존 단일 프롬프트 → Generation(초안) → Feedback(자가비평) → Refinement(수정)
- 비평 점수 0.8 이상이면 초안 즉시 채택 (불필요한 LLM 호출 절약)
- `_parse_json_response()` 헬퍼 추가, 중복 `import re` 제거

### Schwartz 가치 체계 (`personality.py`)
- **10개 가치 차원** 추가: self_direction, stimulation, hedonism, achievement, power, security, conformity, tradition, benevolence, universalism
- **decision_style** 필드: intuitive/analytical/deliberative/spontaneous/dependent
- 전체 21개 아키타입에 가치 프로필 매핑
- `get_value_compatibility(a, b)` — 협업 매칭용 가치 호환성 점수

### System 1/2 추론 전략 (`difficulty_router.py`)
- **ReasoningStrategy enum**: SINGLE_SHOT, CHAIN_OF_THOUGHT, TREE_OF_THOUGHTS, SELF_REFINE, DEBATE
- `select_reasoning_strategy()` — 난이도 + 키워드 분석으로 최적 추론 전략 선택
- `classify_with_strategy()` — (Difficulty, ReasoningStrategy) 튜플 반환

### 토론 모델 + 신뢰 수준 (`collaboration.py`)
- **DebateSession**: 다중 에이전트 토론 (N라운드 의견 교환 → 합의도 측정 → 결론 도출)
- **TrustLevel**: 4단계 신뢰 (STRANGER/COLLEAGUE/TRUSTED/PARTNER), 비대칭 신뢰 변동 (쌓기 어렵고 잃기 쉬움)
- `filter_context_by_trust()` — 신뢰 수준별 정보 공개 범위 제어 (Dec-POMDP)
- `cross_validate()` — 복수 에이전트 결과 교차 검증, 낮은 일관성 경고

### Weak Partner 감지 (`competitive_dispatch.py`)
- `detect_weak_partners()` — 성공률 기준 저성능 에이전트 감지
- `weighted_vote()` — 과거 성과 가중 투표로 최적 결과 선택
- `competitive_execute_with_weak_filter()` — 약한 파트너 필터 후 경쟁 실행

### 다차원 성과 평가 (`agent_performance.py`)
- **SOTOPIA-EVAL 기반 5차원**: goal_completion, efficiency, collaboration, knowledge, compliance
- `MultiDimEvaluation.evaluate()` — 에이전트 결과를 5차원 자동 채점
- `get_profile()` — 차원별 평균/트렌드/최강·최약 차원 프로필
- `get_recommendation()` — 저성과 차원 개선 권고

### SOTOPIA 소셜 다이나믹스 (`social.ts`)
- **5가지 행동 타입**: speak, non_verbal, physical, none, leave
- **Relationship 시스템**: 에이전트 간 관계 점수 (-1~1), 상호작용 이력 추적
- **에피소드 이벤트**: meeting/collaboration/conflict/celebration/crisis — 관계에 영향
- **관계 기반 대화**: 친밀도에 따라 대화 스타일 변동 (친근 ↔ 형식적)

## v3.2.0 (2026-03-27) — 장기메모리 경험 축적 수정, ToolGraph v4

### 장기메모리 경험 축적 수정 (5가지 버그 해결)
- **JINXUS_CORE 서브에이전트 경험 저장**: `_memory_write_node`에서 `save_long_term()` 추가. 기존에는 SQLite 로그만 저장하고 Qdrant 벡터에는 저장하지 않았음
- **CORE 자체 경험도 저장**: JINXUS_CORE가 취합한 응답도 장기기억에 축적
- **저장 조건 완화**: duration 임계값 500ms→100ms, 실패 경험 무조건 저장, 도구 사용 작업도 저장
- **비동기 쓰기 안정화**: 1회 재시도 로직 + error 레벨 로깅 + `_write_fail_count` 카운터
- **Qdrant 연결 검증**: `connect()`에서 즉시 연결 확인, 실패 시 예외 재발생
- **Reflection 시스템 수정**: 존재하지 않던 `get_recent_memories()` → scroll API 기반 `_get_recent_memories()` 구현
- **헬스체크 강화**: `pending_writes`, `write_failures` 모니터링 필드 추가

### ToolGraph v4 업그레이드 (graph-tool-call 최신 반영)
- **임베딩 시맨틱 검색 추가**: OpenAI 임베딩을 4번째 검색 소스로 추가 (BM25 25% + 그래프 40% + 임베딩 20% + 어노테이션 15%)
- **대화 컨텍스트 인식**: `retrieve_with_context()` — "그거 취소해줘" 같은 모호한 쿼리를 대화 히스토리에서 해석
- **멀티턴 히스토리 강화**: 이전 도구의 PRECEDES 이웃에 30% 부스트 (다음 단계 도구 자동 추천)
- **도구 임베딩 배치 생성**: lazy init으로 첫 검색 시 244개 도구 임베딩 일괄 계산
- **모호한 쿼리 판별**: 대명사/짧은 참조 자동 감지 → 컨텍스트 키워드로 보강

## v3.1.1 (2026-03-26) — SSE 실시간 스트리밍, Geny 참고 개편, UX 개선

### SSE 실시간 스트리밍 (Geny 패턴 적용)
- **Next.js SSE 버퍼링 해결**: Edge Runtime SSE 프록시 라우트 (`/api/sse/[...path]`) 추가
- **Geny 2-Phase 패턴**: POST `/mission/start` (JSON 즉시 반환) → EventSource GET `/mission/{id}/events` (실시간 수신)
- 기존 POST 응답에서 SSE 읽던 방식 → 브라우저 네이티브 EventSource로 전환
- 채팅, 스마트 라우터, 에이전트 직접 채팅 모두 SSE 프록시 경유

### 세션/로그 관리 (Geny 철학 적용)
- **세션 수명 연장**: idle 60분→24시간 하드 리셋, idle 전환만 하고 안 죽임
- **자동 부활 우선**: dead 세션 즉시 삭제 ❌ → 부활 시도 (max 3회), 초과해도 재초기화 시도
- **로그 캐시 확대**: 500 → 1000 엔트리
- `.jinxus_sessions` 정리 + `.gitignore` 추가

### 에이전트 이름 변경 기능
- `PUT /agents/{code}/rename` API 추가
- Redis 영속화 (서버 재시작 유지)
- Corporation 탭 EmployeeCard에서 연필 아이콘 클릭 → 인라인 편집
- 변경 즉시 전체 UI 반영 (PixelOffice, 미션 로그, 사이드바, 시스템 프롬프트)

### 미션 제목 짤림 수정
- `_make_title` max_len 20자 → 제한 없음 (첫 줄 전체 사용)
- 브리핑 메시지 `description[:200]` 제한 제거
- 미션 헤더: 기본 전체 표시
- 로그 라인: thinking만 한줄, DM/RPT/MTG 등 전체 표시

### 텔레그램 봇 → 미션 시스템 연동
- 텔레그램 메시지 → 미션 생성 → Task 탭에 동일하게 표시
- 완료 시 업무노트(dev_notes) 내용만 텔레그램에 전송

### PixelOffice 개선
- 캐릭터 이름: 2글자(firstName) → 3글자(fullName) 표시
- 흡연 텍스트: "흡연 중" → "니코틴 부족" / "니코틴 충전 중"
- 핀치 줌아웃 수정: React passive listener → 네이티브 `{ passive: false }` 이벤트
- 모바일 최소 줌: 하드코딩 0.3 → 뷰포트 기반 동적 계산 (맵 전체 보기 가능)
- "JINXUS CORP." 중복 문구 제거, "Corp. env" → "Office View"

### UI/UX 개선
- **Sidebar**: Office 탭에 작업중 에이전트 수 뱃지
- **Docker 로그 색상**: stderr 기반 → 로그 레벨 기반 (ERROR=빨강, WARN=노랑, INFO=초록)
- **Projects 로그 패널**: 기본 높이 220px → 700px, 최대 900px
- **MissionTab Log 버튼**: 헤더 오른쪽에 시스템 로그 슬라이드 패널
- **모바일 로그**: 에이전트 이름 표시 + 수평 스크롤
- **작업중 드롭다운**: 크기 축소, 빈 상태 한줄 표시
- **에이전트 직접 채팅**: `event.data.message` 필드 매칭 수정 (답변 안 보이던 버그)
- **EmployeeCard**: 이름변경 + 채널이동(직접채팅) + 해고 버튼 통합
- **업무노트**: 선택된 노트 제목 전체 표시, 헤더 truncate 제거

### 인프라
- Cloudflare Tunnel: `localhost` → `100.75.83.105` (Tailscale IP) 설정
- `docker compose restart`는 환경변수 안 읽음 → `--force-recreate` 필요
- MCP memory 서버: npx 캐시 zod 깨짐 → 캐시 제거 후 복구

---

## ModelFallbackRunner 구현 (2026-03-25) — API 에러 시 자동 모델 전환

### 개요
API rate limit, overload, 인증 실패 등 발생 시 자동으로 다른 모델로 전환하는 시스템.
기존 `model_router.py`의 간단한 ModelFallbackRunner를 `model_fallback.py`로 분리/확장.

### 신규 파일
| 파일 | 역할 |
|------|------|
| `backend/jinxus/core/model_fallback.py` | ModelFallbackRunner 본체. 에러 분류, 차등 대기, 블랙리스트, ModelExhaustedError |

### 핵심 기능
- **에러 유형별 차등 대기**: RateLimitError 30초, OverloadedError 60초, TimeoutError 10초, AuthenticationError 즉시 전환+블랙리스트
- **마지막 성공 모델 기억**: 클래스 변수로 프로세스 내 전역 공유, 다음 호출 시 우선 사용
- **AuthenticationError 시 영구 제거**: 블랙리스트에 추가, 이후 후보에서 제외
- **모델 동적 추가/제거**: `add_model()`, `remove_model()` 메서드
- **모든 후보 소진 시 ModelExhaustedError 발생**: `run_or_raise()` 메서드
- **settings.py 호환**: claude_model, claude_fallback_model, claude_fast_model 3단계 후보

### 변경 파일
| 파일 | 변경 내용 |
|------|-----------|
| `backend/jinxus/core/model_router.py` | 구 ModelFallbackRunner/FallbackResult/ModelExhaustedError 제거, model_fallback.py에서 re-export |
| `backend/jinxus/core/__init__.py` | ModelFallbackRunner, ModelExhaustedError, get_model_fallback_runner export 추가 |

---

## 아키텍처 종합 검토 (2026-03-25) — 전체 시스템 리뷰

재원(백엔드) · 예린(프론트엔드) · 수빈(크로스리뷰) → 민준 종합.
상세 보고서: `docs/08_ARCHITECTURE_REVIEW.md`

**핵심 발견:**
- [H-1] MissionExecutor v3/v4 공존 → v3 deprecated 처리 필요
- [H-2] tool_policy 전면 비활성 (whitelist=None) → 활성화 또는 제거 결정 필요
- [H-3] PixelOffice.tsx 2,000줄 모놀리스 → 서브컴포넌트 분리 필요
- [M-4] SSE 재연결 로직 채널별 불일치 → consumeSSE() 통합 필요
- [M-6] /agents/runtime/all 폴링 → SSE 단일 스트림 전환 검토

---

## 버전 v4.0.0 (2026-03-25) — CLI 기반 에이전트 런타임 전환 (v4 아키텍처)

### 개요

LangGraph 중심의 v3 구조에서 **Claude CLI 직접 실행 기반 v4 구조**로 전환.
에이전트를 독립 프로세스로 실행하고 stdio 스트림을 실시간 파싱하는 새로운 런타임 계층 도입.
난이도 분류기로 Easy/Medium/Hard 자동 판별 후 실행 전략을 분기하는 v4 미션 엔진 추가.

---

### 신규 파일 — CLI Engine (에이전트 런타임 인프라)

| # | 파일 | 역할 | 줄 수 |
|---|------|------|-------|
| 1 | `cli_engine/models.py` | 공유 데이터 모델 (`SessionStatus`, `SessionInfo`, `ExecutionResult`, `StreamEvent`, `LogEntry`) | ~173 |
| 2 | `cli_engine/session_manager.py` | 세션 중앙 관리자 — 에이전트 생성/조회/삭제, 유휴 모니터 (`AgentSessionManager`) | ~329 |
| 3 | `cli_engine/agent_session.py` | 에이전트 세션 생명주기 — `ClaudeProcess` 래퍼, 페르소나+프롬프트 주입 (`AgentSession`) | ~226 |
| 4 | `cli_engine/session_logger.py` | 세션 로그 3계층 (메모리 캐시 → 파일 → DB), 200ms 폴링용 캐시 (`SessionLogger`) | ~443 |
| 5 | `cli_engine/process_manager.py` | Claude CLI 프로세스 관리 — stdio 스트림 파싱, 명령어 빌드 (`ClaudeProcess`) | ~409 |
| 6 | `cli_engine/stream_parser.py` | Claude CLI `--output-format stream-json` JSON 이벤트 파싱 (`StreamParser`) | ~252 |
| 7 | `cli_engine/prompt_builder.py` | 에이전트/CORE용 시스템 프롬프트 빌더 (`build_agent_prompt`, `build_core_prompt`) | ~148 |
| 8 | `cli_engine/__init__.py` | 모듈 초기화 | ~31 |

**의존 관계:** `agent_session` → `process_manager` → `stream_parser` → `models`
`session_manager` → `agent_session`, `session_logger`

---

### 신규 파일 — Core (v4 실행 엔진)

| # | 파일 | 역할 | 줄 수 |
|---|------|------|-------|
| 1 | `core/agent_executor.py` | **에이전트 실행 단일 진입점** — 동기 `execute_command()` + 비동기 `start_command_background()`. 모든 에이전트 실행이 이 모듈을 통과 | ~254 |
| 2 | `core/difficulty_router.py` | **난이도 자동 분류** — `Difficulty` enum (EASY/MEDIUM/HARD), 규칙 기반 + LLM fallback. 미션 엔진 v4의 입력 | ~111 |
| 3 | `core/mission_executor_v4.py` | **v4 미션 엔진** — 난이도별 실행 전략 분기 (EASY: CORE 직답, MEDIUM: 단일 에이전트, HARD: 병렬 에이전트) | ~664 |

**의존 관계:** `mission_executor_v4` → `agent_executor` + `difficulty_router`
`agent_executor` → `cli_engine/session_manager`

---

### 신규 파일 — API Routers

| # | 파일 | 역할 | 줄 수 |
|---|------|------|-------|
| 1 | `api/routers/command.py` | **에이전트 직접 커맨드 API** — `POST /command/{agent_name}/execute`, `POST /command/{agent_name}/execute/stream`, `POST /command/batch`, `GET /command/sessions` | ~294 |

**의존 관계:** `command.py` → `core/agent_executor`

---

### 신규 파일 — Tools (MCP 인프라)

| # | 파일 | 역할 | 줄 수 |
|---|------|------|-------|
| 1 | `tools/mcp_proxy_server.py` | **MCP 프록시 서버** — JINXUS 네이티브 도구를 MCP 프로토콜로 외부 노출 (`create_mcp_server`, `build_proxy_mcp_config`) | ~136 |
| 2 | `tools/tool_loader.py` | **에이전트 세션용 MCP 설정 빌더** — `build_session_mcp_config()`, `load_global_mcp_servers()`. 에이전트 실행 시 MCP 서버 목록 조립 | ~93 |

**의존 관계:** `agent_session.py` → `tool_loader` → `mcp_proxy_server`

---

### v4 아키텍처 실행 흐름

```
사용자 입력
    ↓
[API] POST /command/{agent}/execute  또는  POST /missions
    ↓
[Routers] command.py  또는  mission.py
    ↓
[Core] agent_executor.execute_command()          ← 동기 단일 실행
      agent_executor.start_command_background()  ← 비동기 백그라운드
    │
    ├─ [Core] difficulty_router.classify_difficulty()
    │       → EASY / MEDIUM / HARD
    │
    └─ [Core] mission_executor_v4 (난이도별 전략)
            ├─ EASY  : CORE 직접 API 호출 (Anthropic)
            ├─ MEDIUM: 단일 에이전트 CLI 선택
            └─ HARD  : 복수 에이전트 병렬 CLI 실행
    ↓
[CLI Engine] 에이전트 세션 생성
    ├─ SessionManager.create_session(agent_name)
    ├─ AgentSession.create()
    │       └─ prompt_builder → 시스템 프롬프트 조립
    │       └─ tool_loader   → MCP 서버 설정 조립
    │       └─ ClaudeProcess → `claude --output-format stream-json` 실행
    └─ StreamParser.parse()  → LogEntry 생성
    ↓
[Logger] SessionLogger (3계층)
    ├─ 메모리 캐시 (200ms 폴링)
    ├─ 파일 로그
    └─ DB (SQLite 메타)
    ↓
[API] event_generator() → SSE 스트림 → 프론트엔드
    ↓
[FE] PixelOffice.tsx 실시간 시각화
```

---

### 레거시 대비 변경점

| 항목 | v3 (구) | v4 (신) |
|------|---------|---------|
| 에이전트 실행 | LangGraph 노드 + Python 함수 호출 | Claude CLI 독립 프로세스 |
| 실행 진입점 | `jinx_loop.py` → `JinxusCore` | `agent_executor.py` 단일 게이트 |
| 난이도 분기 | 없음 | `difficulty_router` (EASY/MEDIUM/HARD) |
| 미션 엔진 | `mission_executor.py` (v3) | `mission_executor_v4.py` |
| MCP 탑재 | 전역 설정 | `tool_loader`가 세션별 동적 조립 |
| 로그 | `state_tracker` 이벤트 버스 | `session_logger` 3계층 캐시 |

---

## 버전 v3.0.0 (2026-03-24) — PixelOffice 대개편 & 조직 현실화 & HR 강화

### 아키텍처 대개편 (1323줄 모놀리스 → 15개 모듈)

| # | 파일 | 역할 | 줄 수 |
|---|------|------|-------|
| 1 | `engine/types.ts` | 타입 정의 (CharState, RoomDef, POIDef 등) | ~100 |
| 2 | `engine/constants.ts` | 상수 (MAP 60x40, SCALE 4, 타일 등) | ~31 |
| 3 | `engine/camera.ts` | 카메라/뷰포트 (드래그 스크롤, 줌 0.3x-2.0x) | ~113 |
| 4 | `engine/pathfinding.ts` | BFS 경로탐색 | ~51 |
| 5 | `engine/social.ts` | 잡담 템플릿, 유휴 행동, 시간대별 루틴 | ~60 |
| 6 | `engine/scheduler.ts` | 에이전트별 일과표 (rank/team 기반) | ~49 |
| 7 | `sprites/character.ts` | **16x24 치비 스프라이트** (구 12x16) | ~231 |
| 8 | `sprites/colors.ts` | 팔레트 (머리 12색, 셔츠=TEAM_CONFIG) | ~40 |
| 9 | `sprites/icons.ts` | 도구 아이콘 5x5 + 매핑 | ~69 |
| 10 | `sprites/furniture.ts` | 가구 15종 (기존 6 + 신규 9) | ~204 |
| 11 | `sprites/cache.ts` | 스프라이트 캐시 | ~34 |
| 12 | `map/mapData.ts` | 60x40 맵 레이아웃 (실내 8실 + 야외 6구역) | ~269 |
| 13 | `render/emoji.ts` | 활동→이모지 매핑 + 머리 위 표시 | ~87 |
| 14 | `poi/poiManager.ts` | POI 상태 추적 (용량, 대기열) | ~57 |
| 15 | `PixelOffice.tsx` | React 셸 + 게임 루프 + 이벤트 | ~952 |

### 맵 확장 (30x18 → 60x40)

| 구역 | 위치 | 타입 |
|------|------|------|
| 주차장 | 좌상단 | 야외 |
| 로비/입구 | 중상단 | 야외 |
| 정원 | 우상단 | 야외 |
| 입구 복도 | y4-5 전폭 | 복도 |
| 경영실 | 좌측 상층 | 사무실 |
| 개발팀 | 중앙 상층 (넓음) | 사무실 |
| 플랫폼팀 | 우측 상층 | 사무실 |
| 회의실 | 우측 끝 상층 | 공용 |
| 중앙 복도 + 휴게실 | y18-21 | 복도/공용 |
| 경영지원팀 | 좌측 하층 | 사무실 |
| 프로덕트팀 | 중앙 하층 (넓음) | 사무실 |
| 마케팅팀 | 우측 하층 | 사무실 |
| 서버실 | 우측 끝 하층 | 공용 |
| 흡연장 | 좌하단 | 야외 |
| 테라스 | 중하단 | 야외 |
| 옥상정원 | 우하단 | 야외 |

### 캐릭터 리디자인

| 항목 | Before | After |
|------|--------|-------|
| 스프라이트 크기 | 12×16px | **16×24px** |
| 등신 비율 | 2.3등신 | **2등신 (치비)** |
| 머리 크기 | 7px | **10px** (둥글고 큰 머리) |
| 눈 크기 | 1px | **2px** (표정 표현) |
| 볼터치 | 없음 | **있음** (귀여움↑) |
| 헤어스타일 | 1종 | **계획: 6-8종** |

### POI 확장 (7→28개)

실내: 커피머신, 화이트보드, 책장, 서버랙, 프린터, 자판기, 냉장고, 정수기, 소파, 회의테이블
야외: 흡연장 벤치, 정원 벤치, 주차장, 테라스 파라솔, 옥상정원

### 카메라 시스템 (신규)

- 마우스 드래그로 뷰포트 이동
- 휠로 줌 인/아웃 (0.3x~2.0x)
- 줌 잔상 버그 수정 (clearRect 전체 캔버스 초기화)

### 조직 현실화

| # | 항목 | 설명 |
|---|------|------|
| ORG-1 | 부서명 | 프로덕트개발팀→개발팀, 그로스팀→마케팅팀, 경영지원→경영지원팀 |
| ORG-2 | 직급 | 개발팀장, 플랫폼팀장, 프로덕트팀장, 마케팅팀장, PM, 시스템 운영 등 |
| ORG-3 | 채널 | GROWTH→MARKETING, growth→marketing 전체 동기화 |

### HR 시스템 강화

| # | 항목 | 설명 |
|---|------|------|
| HR-1 | 해고 UI 버튼 | JINXUS_CORE 제외 전 에이전트 해고 가능 (🗑️ 아이콘) |
| HR-2 | 재고용 복구 | 에이전트 인스턴스 + 페르소나 재생성 (기존: record만 활성화) |

### 버그 수정

| # | 항목 | 설명 |
|---|------|------|
| BUG-1 | 작업로그 삭제 | DELETE /logs 라우트 충돌 → POST /logs/bulk-delete |
| BUG-2 | 업무노트 자동생성 | get_conversations() → mission.agent_conversations |
| BUG-3 | 줌 잔상 | 카메라 변환 전 clearRect 추가 |

### UI 개선

| # | 항목 | 설명 |
|---|------|------|
| UI-1 | 탭 이름 영어화 | Office, Corporation, Projects, Memory, Logs, Tools, Notes, Settings |
| UI-2 | 채팅 탭 제거 | 기능 Office 탭으로 흡수 |
| UI-3 | muteChat 전역화 | Office/Corporation 동시 적용 |
| UI-4 | OFFICE FEED 토글 | 사이드바 접기/펼치기 (모바일 대응) |
| UI-5 | 미션 실시간 피드 | mission_tool_calls 이벤트, 도구 호출 표시 |
| UI-6 | 뒤로가기 버튼 | 에이전트 채팅 뷰에 ← 추가 |
| UI-7 | 옛 팀명 제거 | matrix.ts, CompanyChat.tsx 채널 ID 정합성 |

---

## 버전 v2.9.0 (2026-03-22) — 가상 오피스 플레이그라운드 & UI 대개편

### 플레이그라운드 (Pixel Office)

| # | 항목 | 설명 |
|---|------|------|
| PG-1 | 에이전트 탭 '플레이그라운드' 서브탭 | Canvas 기반 가상 오피스 |
| PG-2 | 12x16 픽셀 스프라이트 캐릭터 | 4방향, 걷기 3프레임 사이클 |
| PG-3 | BFS 경로 탐색 | 부드러운 보간 이동 (48px/s) |
| PG-4 | 에이전트별 고유 외형 | 팀 유니폼, 12종 머리색 |
| PG-5 | 도구별 애니메이션 6종 | idle/walk/type/read/think/search |
| PG-6 | 도구 사용 5x5 픽셀 아이콘 | 터미널/돋보기/연필/뇌/지구 |
| PG-7 | 작업 시작 시 말풍선 | 3초 페이드아웃 |
| PG-8 | SSE 실시간 상태 스트림 | 폴링 → 즉시 반응 |
| PG-9 | 50x30 타일 오피스 | 6개 팀 방 + 복도, 2x 스케일 |

### UI 대개편

| # | 항목 | 설명 |
|---|------|------|
| UI-1 | 대시보드 → 설정 탭 통합 | 4개 접이식 섹션, 사이드바 대시보드 제거 |
| UI-2 | 채팅/프로젝트 탭 시스템 로그 하단 패널 | VSCode 스타일, 드래그 리사이즈 |
| UI-3 | 전체 에이전트 이름 한국어 표시 통일 | JX_ 코드 제거 |

### 백엔드

| # | 항목 | 설명 |
|---|------|------|
| BE-1 | GET /agents/runtime/stream SSE 엔드포인트 | 실시간 상태 변경 스트림 |
| BE-2 | StateTracker 이벤트 버스 | subscribe/notify 패턴 |

### 정리

| # | 항목 | 설명 |
|---|------|------|
| CLN-1 | start.sh, stop.sh 삭제 | 구버전 tmux 방식 |
| CLN-2 | daemon.sh uvicorn 호출 버그 수정 | — |

---

## 버전 v2.6.1 (2026-03-19) — Matrix 연결 수정 + 프롬프트 엔지니어 채용

### 핵심 변경
- **Matrix URL 고정**: `getMatrixHS()` `window.hostname` 기반 → `NEXT_PUBLIC_MATRIX_HS` env var 우선 사용 (`100.75.83.105:8008` 고정) → Cloudflare 접속 시 오작동 제거
- **fetch 타임아웃**: whoami(6s), 룸조회(5s), 메시지전송(10s), sync long-poll 30s→10s
- **marketing Matrix 룸**: `CHANNEL_TO_ALIAS_LOCALPART` 누락 추가, Synapse에 방 생성 + 에이전트 참가
- **Matrix AS 토큰**: `docker compose restart` → `docker compose up -d` 변경 필요 (restart는 env_file 재로드 안 함)
- **Matrix 에러 메시지 개선**: "Synapse 서버 상태 확인" → "메시지 전송은 계속 가능" + 재연결 버튼
- **프롬프트 엔지니어(지호) 채용**: 에이전트 총 28명, 개발팀 12명
- **channel.py AGENT_CHANNEL_MAP**: 신규 에이전트 6명 + 기존 누락분 추가

| # | 항목 | 파일 |
|---|------|------|
| MTX-1 | Matrix HS env var 고정 | `matrix.ts`, `.env.local`, `NEXT_PUBLIC_MATRIX_HS` |
| MTX-2 | fetch 타임아웃 추가 | `matrix.ts` (`fetchWithTimeout`) |
| MTX-3 | sync 30s→10s | `matrix.ts` |
| MTX-4 | marketing 채널 Matrix 룸 | `matrix.ts`, `matrix_channel.py` |
| MTX-5 | 에러 배너 + 재연결 버튼 | `CompanyChat.tsx` |
| MTX-6 | AS 토큰 로드 수정 | `docker compose up -d` (env_file 재로드) |
| HIRE-6 | 프롬프트 엔지니어(이지호) 채용 | `personas.py`, `personas.ts` |
| HIRE-7 | channel.py 신규 에이전트 등록 | `channel.py` |

---

## 버전 v2.6.0 (2026-03-19) — 에이전트 대규모 채용 + 카운트 단일화 + 이미지 최적화

### 핵심 변경
- **개발팀 에이전트 5명 신규 채용**: JX_AI_ENG(승우), JX_SECURITY(정민), JX_DATA_ENG(서준), JX_MOBILE(은지), JX_ARCHITECT(민성)
- **에이전트 총원 27명** (22→27, 개발팀 6→11명)
- **에이전트 수 단일 소스**: `hrAgents` 기반으로 통일. Sidebar/Dashboard/AgentsTab/GraphTab/CompanyChat 모두 `hrAgents.length` 사용, 하드코딩 +1 제거
- **마스코트 이미지 로딩 최적화**: layout.tsx preload 링크 추가 + 웰컴 스크린 `fetchPriority="high"` 적용

| # | 항목 | 파일 |
|---|------|------|
| HIRE-1 | AI/ML 엔지니어(승우) 채용 | `personas.py`, `personas.ts` |
| HIRE-2 | 보안 엔지니어(정민) 채용 | `personas.py`, `personas.ts` |
| HIRE-3 | 데이터 엔지니어(서준) 채용 | `personas.py`, `personas.ts` |
| HIRE-4 | 모바일 개발자(은지) 채용 | `personas.py`, `personas.ts` |
| HIRE-5 | 시스템 아키텍트(민성) 채용 | `personas.py`, `personas.ts` |
| FIX-A | 에이전트 수 단일 소스(hrAgents) | `Sidebar.tsx`, `DashboardTab.tsx`, `AgentsTab.tsx`, `GraphTab.tsx`, `CompanyChat.tsx` |
| FIX-B | 마스코트 이미지 preload | `layout.tsx`, `ChatTab.tsx` |

---

## 버전 v2.5.0 (2026-03-19) — 프론트엔드 구조 수정 + 성능 최적화

### 핵심 변경
- **Next.js 구조 수정**: `output: 'standalone'` 제거 (`next start` 충돌 원인), `layout.tsx` 서버/클라이언트 경계 위반 수정 (`ClientProviders` 분리)
- **번들 최적화**: `react-syntax-highlighter` dynamic import → 초기 JS 316KB → 76.8KB (**76% 감소**)
- **308 redirect 수정**: `getInfo()` trailing slash 제거 → `/api/`→308→`/api` 체인 제거
- **정적 캐시 최적화**: `_next/static/` 해시 파일 `immutable` 캐시 적용 (기존 `no-cache` → 매번 재다운로드 낭비)
- **`sharp` 설치**: 프로덕션 이미지 최적화 활성화
- **dev.sh 개선**: production(기본)/dev/rebuild 모드 분리

| # | 항목 | 파일 |
|---|------|------|
| ARCH-1 | output:standalone 제거 | `next.config.js` |
| ARCH-2 | ClientProviders 분리 | `ClientProviders.tsx` (신규), `layout.tsx` |
| ARCH-3 | SyntaxHighlighter dynamic import | `MarkdownRenderer.tsx` |
| ARCH-4 | getInfo trailing slash 제거 | `api.ts` |
| ARCH-5 | 정적 캐시 immutable 설정 | `next.config.js` |
| ARCH-6 | sharp 설치 | `package.json` |
| ARCH-7 | dev.sh prod/dev/rebuild 분리 | `dev.sh` |

---

## 버전 v2.4.0 (2026-03-19) — 인격 시스템 + HR·채널 연동 수정 + 프론트엔드 성능 개선

### 프론트엔드 로딩 성능 개선 (2026-03-19 추가)
- **production 모드로 전환**: `next dev` → `next start` (JS 번들 14MB → 409KB, **35배 감소**)
- **HMR WebSocket 수정**: `allowedDevOrigins` 미설정으로 `jinxus.js-96.com`에서 WebSocket 400 차단 → 추가 후 101 정상
- **TTFB 개선**: 7초(cold) → 105ms (로컬), 330ms (Cloudflare 경유)
- **dev.sh 개선**: `--dev` 플래그로 개발/production 모드 선택, 빌드 실패 시 자동 fallback

| # | 항목 | 파일 |
|---|------|------|
| PERF-1 | production 빌드 서빙 | `dev.sh` (`next start` 기본) |
| PERF-2 | allowedDevOrigins 추가 | `next.config.js` |
| PERF-3 | SSE 직접 연결 URL | `.env.local` `NEXT_PUBLIC_STREAM_URL` |

---

## 버전 v2.4.0 (2026-03-19) — 인격 시스템 + HR·채널 연동 수정

### 핵심 변경
- **인격 아키타입 시스템**: 20개 인격 풀(개척자·전략가·반골·장인 등). 기존 에이전트 전원 personality_id 할당. 신규 고용 시 랜덤 배정 + 시스템 프롬프트 자동 주입
- **CompanyChat 채널 멤버**: HR 고용 목록 기반으로 필터링. 미고용 에이전트 노출 제거
- **에이전트 카운트 통일**: AgentsTab `(N)` = hiredSet.size (JINXUS_CORE 포함) = 채널 멤버 수 동일 소스
- **버전 수정**: settings.py 하드코딩 오류 2.7.0 → 2.4.0

| # | 항목 | 파일 |
|---|------|------|
| PERS-1 | 인격 아키타입 풀 | `agents/personality.py` (신규, 20개) |
| PERS-2 | 에이전트 personality_id 전원 매핑 | `agents/personas.py` |
| PERS-3 | 고용 시 랜덤 인격 선택 | `hr/agent_factory.py`, `hr/models.py` |
| PERS-4 | 시스템 프롬프트 인격 주입 | `hr/agent_factory.py` `<personality>` 블록 |
| PERS-5 | API personality 필드 노출 | `api/routers/agents.py` |
| PERS-6 | EmployeeCard 인격 뱃지·MBTI | `AgentsTab.tsx` |
| FIX-1 | 채널 멤버 HR 고용 연동 | `CompanyChat.tsx` hiredCodes 필터 |
| FIX-2 | 에이전트 카운트 통일 | `AgentsTab.tsx` hiredSet.size |
| FIX-3 | 버전 수정 | `settings.py` |

---

## 버전 v2.11.0 (2026-03-19) — C-Suite 임원팀 완성 + 백엔드↔프론트 단일 소스 아키텍처

### 핵심 변경
- **`personas.py` 단일 소스**: 백엔드에서 에이전트를 추가/수정하면 프론트엔드 전체(AgentsTab·채널·프로젝트 등)에 자동 반영
- **C-Suite 4인 완성**: CEO(JINXUS), CTO(채영), COO(세준), CFO(미래)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| ORG-6 | JX_COO 추가 | `personas.py`, `personas.ts` | COO 오세준(⚡). 임원팀. 팀간 병목 해결·운영 조율·스케줄 관리 |
| ORG-7 | JX_CFO 추가 | `personas.py`, `personas.ts` | CFO 윤미래(💰). 임원팀. ROI 분석·재무·투자 의사결정 |
| ARCH-1 | Backend→Front 단일 소스 | `personas.py`, `agents.py`, `personas.ts`, `api.ts`, `useAppStore.ts` | `GET /agents/personas` 엔드포인트 추가. 앱 시작 시 `loadPersonas()` 호출 → `setDynamicPersonaMap()` → 동적 Proxy 맵 덮어쓰기 |
| ARCH-2 | personas.ts 동적화 | `personas.ts` | `_dynamicMap` + Proxy 패턴. 정적 fallback 유지. `setDynamicPersonaMap()` export |
| ARCH-3 | personasVersion 트리거 | `useAppStore.ts`, `AgentsTab.tsx` | personas 로드 완료 시 버전 카운터 증가 → useMemo deps 트리거로 컴포넌트 리렌더링 |
| ARCH-4 | AgentsTab 동적 팀그룹 | `AgentsTab.tsx` | 모듈 레벨 `TEAM_AGENTS` 상수 제거 → 컴포넌트 내 `useMemo([personasVersion])` 로 교체 |
| POLICY-1 | Tool Policy 신규 에이전트 | `tool_policy.py` | JX_CTO·JX_COO·JX_CFO·JX_MARKETING·JS_PERSONA·JX_SNS·JX_PRODUCT·JX_STRATEGY 도구 정책 등록 |
| POLICY-2 | MCP 접근 권한 확장 | `mcp_servers.py` | filesystem(CTO), playwright(SNS), postgres(CFO·COO·STRATEGY), notion/slack(COO·CFO·MARKETING 등) |

### 최종 팀 구조 (v2.11.0)
| 팀 | 역할 | 멤버 |
|---|---|---|
| 임원 | C-Suite 의사결정 | JINXUS(CEO), 채영(CTO), 세준(COO), 미래(CFO) |
| 엔지니어링 | 개발·QA·인프라 | 민준(팀장), 예린, 재원, 도현, 수빈, 하은 |
| 리서치 | 조사·팩트체크 | 지은(팀장), 유진, 시우, 나연 |
| 운영 | 시스템·데이터 | 태양(시스템운영), 현수(데이터분석) |
| 마케팅 | 브랜딩·콘텐츠·SNS | 지훈(팀장), 소희(라이터), 아름(퍼소나), 다현(SNS) |
| 기획 | 전략·제품·기획 | 서연(PM), 준혁(전략가) |

---

## 버전 v2.10.0 (2026-03-19) — 조직 구조 전면 재설계 + 스크롤 수정

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| ORG-1 | 임원팀 분리 | `personas.ts`, `personas.py` | `전사` 팀 폐지 → `임원` 팀 신설. CEO(JINXUS_CORE), CTO(이채영)만 임원 |
| ORG-2 | JX_WRITER 마케팅 이동 | `personas.ts`, `personas.py` | `전사`→`마케팅` 팀, channel `general`→`marketing`. 지훈 팀장 아래 배치 |
| ORG-3 | JX_ANALYST 운영 이동 | `personas.ts`, `personas.py` | `전사`→`운영` 팀, channel `general`→`ops`. 태양과 협업 |
| ORG-4 | JS_PERSONA 백엔드 팀 수정 | `personas.py` | `전사`→`마케팅` (프론트는 이미 올바름) |
| ORG-5 | 전략기획 멤버 수정 | `personas.ts` | planning 채널 = planning 소속 + 임원팀만. 기존엔 라이터·분석가·퍼소나도 포함돼 오류 |
| NEW-1 | JX_SNS 추가 | `personas.ts`, `personas.py` | SNS 매니저 남다현(📱). 마케팅팀. 바이럴·인스타·틱톡·커뮤니티 관리 |
| NEW-2 | JX_STRATEGY 추가 | `personas.ts`, `personas.py` | 비즈니스 전략가 신준혁(🎯). 기획팀. 시장분석·OKR·투자자보고서 |
| UI-1 | AgentsTab 임원팀 색상 | `AgentsTab.tsx` | '전사' amber→'임원' amber (🏅 임원 구분) |
| UI-2 | AgentsTab 왼쪽 패널 스크롤 | `AgentsTab.tsx` | `overflow-y-auto min-h-0` 추가. 에이전트 목록 잘림 해결 |

### 최종 팀 구조 (v2.10.0)
| 팀 | 역할 | 멤버 |
|---|---|---|
| 임원 | C-Suite 의사결정 | JINXUS(CEO), 채영(CTO) |
| 엔지니어링 | 개발·QA·인프라 | 민준(팀장), 예린, 재원, 도현, 수빈, 하은 |
| 리서치 | 조사·팩트체크 | 지은(팀장), 유진, 시우, 나연 |
| 운영 | 시스템·데이터 | 태양(시스템운영), 현수(데이터분석) |
| 마케팅 | 브랜딩·콘텐츠·SNS | 지훈(팀장), 소희(라이터), 아름(퍼소나), 다현(SNS) |
| 기획 | 전략·제품·기획 | 서연(PM), 준혁(전략가) |

---

## 버전 v2.9.0 (2026-03-19) — 채널/팀 동적 연동 완성 (personas.ts 단일 소스)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| FE-1 | CompanyChat 채널 멤버 동적화 | `tabs/CompanyChat.tsx` | 하드코딩 `getChannelMembers()` 제거. `getChannelAgents()` 사용 — general=전체, planning=planning+전사팀, 나머지=채널 소속 |
| FE-2 | ChannelMembers 패널 개선 | `tabs/CompanyChat.tsx` | 이모지+이름+직함 표시. `FIRST_NAME_EMOJI`/`PERSONA_MAP` 직접 참조 제거 |
| FE-3 | AgentsTab 코더/리서치팀 API 제거 | `tabs/AgentsTab.tsx` | `coderTeam`/`researcherTeam` 상태·API폴링·하드코딩 섹션 전부 삭제. 직원현황 그리드는 이미 `getTeamGroups()`+`TEAM_ORDER` 기반 |
| FE-4 | 불필요한 아이콘/타입 제거 | `tabs/AgentsTab.tsx` | `Code2`, `Search` lucide 아이콘, `CodingSpecialist` 타입 임포트 제거 |

---

## 버전 v2.8.0 (2026-03-19) — 텔레그램↔Matrix↔팀 업무 완전 연동

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| TG-1 | 텔레그램 task 분류 | `channels/telegram_bot.py` | `_classify_as_task()` 키워드 패턴 분류. 업무 지시면 AgentReactor 경로, 대화면 JINXUS_CORE 경로 |
| TG-2 | 텔레그램→Matrix 전사 공지 | `channels/telegram_bot.py` | task 분류 시 Matrix general 채널에 `📢 [CEO 진수님 지시] {message}` 즉시 게시 |
| TG-3 | 즉시 확인 응답 | `channels/telegram_bot.py` | task 접수 즉시 "전사 공지됐습니다. 팀장들이 배분하고 진행할게요." 응답 (논블로킹) |
| TG-4 | AgentReactor telegram_callback | `hr/agent_reactor.py` | `react()` / `_execute_task()`에 `telegram_callback` 파라미터 추가. 작업 완료 후 콜백 호출 |
| TG-5 | 텔레그램 완료 보고 | `hr/agent_reactor.py` | 업무 노트 작성 후 "✅ 업무 완료 보고 / 담당 / 결과 / 📒 노트 작성됨" 형식으로 자동 발송 |

### 전체 흐름 (v2.8.0)
```
진수 텔레그램 메시지
  ├─ task 분류 (키워드 패턴)
  │   ├─ Matrix general에 CEO 공지 게시
  │   ├─ 텔레그램: "전사 공지됐습니다" 즉시 응답
  │   └─ 백그라운드:
  │       ├─ 팀장들 general 채널에서 반응 (존댓말)
  │       ├─ 팀장 → 팀 채널 브리핑 → 팀원 배분
  │       ├─ 팀원들 실제 업무 실행
  │       ├─ general에 최종 보고
  │       ├─ 업무 노트 자동 작성
  │       └─ 텔레그램으로 완료 보고
  └─ chat 분류 → JINXUS_CORE 처리 후 텔레그램 응답
```

---

## 버전 v2.7.0 (2026-03-19) — 탭 통합 + Matrix .env 연동 + UI 정비

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| INT-1 | 직원 현황 + 에이전트 탭 통합 | `components/tabs/AgentsTab.tsx` | GraphTab 부서별 그리드(EmployeeCard)를 AgentsTab 오른쪽 패널 기본 뷰로 통합. 카드 클릭 → 직접 채팅 전환. 채팅 헤더에 "현황" 버튼으로 복귀 |
| INT-2 | GraphTab 제거 | `Sidebar.tsx`, `app/page.tsx`, `store/useAppStore.ts` | '직원 현황' 탭 항목 삭제. `graph` import/라우팅/타입 전부 제거 |
| INT-3 | Matrix 계정 .env 연동 | `frontend/.env.local` (신규), `CompanyChat.tsx` | `NEXT_PUBLIC_MATRIX_USER` / `NEXT_PUBLIC_MATRIX_PASSWORD` 환경변수 도입. 하드코딩된 `'jinsu'`/`'jinxus2026!'` 제거 |
| INT-4 | MatrixAS 하드코딩 토큰 제거 | `channels/matrix_channel.py`, `config/settings.py` | `getattr(..., fallback_token)` 패턴 제거 → `settings.matrix_as_token` 직접 참조. settings 기본값도 빈 문자열로 변경 (실제값은 .env) |
| INT-5 | 사이드바 "업무 노트" 레이블 수정 | `Sidebar.tsx` | '개발 노트' → '업무 노트' 로 변경 |
| INT-6 | 마케팅/기획팀 색상 추가 | `AgentsTab.tsx` | TEAM_COLOR/TEAM_LABEL_COLOR에 '마케팅'(pink), '기획'(cyan) 추가 |

---

## 버전 v2.6.0 (2026-03-19) — 팀채팅 Matrix 프론트엔드 전환 + 조직 확장 + 대화형 AgentReactor

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| ORG-1 | CompanyChat Matrix 전환 | `components/tabs/CompanyChat.tsx` | SSE 기반 → Matrix Client-Server API 기반으로 교체. auto-login(`jinsu`), `/sync` long-polling, 채널↔룸 매핑, 자동 재연결 |
| ORG-2 | Matrix 경량 클라이언트 | `lib/matrix.ts` (신규) | login/sync/send/resolveRoomAlias 구현. matrix-js-sdk 의존성 없이 직접 fetch. LOCALPART→이름 PERSONA_MAP 자동 파생 |
| ORG-3 | 마케팅팀 채널 추가 | `hr/channel.py`, `CompanyChat.tsx` | `marketing` 채널 신설. ChannelName enum 추가. 채널 display명 한국 기업 방식으로 정비 (전사 공지/개발팀/마케팅팀 등) |
| ORG-4 | JX_MARKETING 채용 | `agents/jx_marketing.py` (신규), `agents/personas.py` | 박지훈 마케팅 팀장. ENFJ. 브랜딩·그로스해킹·SNS·캠페인. marketing 채널 소속 |
| ORG-5 | JX_PRODUCT 채용 | `agents/jx_product.py` (신규), `agents/personas.py` | 김서연 제품 기획 PM. INFJ. 유저리서치·로드맵·OKR·스프린트. planning 채널 소속 |
| ORG-6 | 에이전트 존댓말 강제 | `hr/agent_reactor.py`, `agents/personas.py` | 진수(오너)에게 반드시 존댓말 사용 규칙 system prompt에 명시. 반말 절대 금지 |
| ORG-7 | 대화형 AgentReactor | `hr/agent_reactor.py` | 병렬 반응 → 순차 반응으로 전환. 이전 직원 발언을 컨텍스트로 주입해 실제 대화처럼 연결. 0.6초 간격 타이핑 시뮬레이션 |
| ORG-8 | 팀 내부 논의 플로우 | `hr/agent_reactor.py` _execute_task | task 실행 시: 팀장이 팀 채널에서 내부 브리핑 → 작업 실행 → 결과를 general 채널에 CEO 보고 방식으로 최종 정리 |
| ORG-9 | 프론트엔드 페르소나 확장 | `lib/personas.ts` | JX_MARKETING(지훈), JX_PRODUCT(서연) 추가. JS_PERSONA 소속팀 marketing으로 이동 |

**Matrix 접속**: Element → 홈서버 `http://100.75.83.105:8008` / `jinsu` / `jinxus2026!`

---

## 버전 v2.5.0 (2026-03-19) — Matrix(matrix.org) 팀채팅 통합 + claude-opus-4-6 업그레이드

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| MX-1 | Synapse 홈서버 | `docker-compose.yml`, `synapse/` | matrixdotorg/synapse:latest 컨테이너 추가. PostgreSQL 백엔드. AS 등록 (`synapse/appservices/jinxus_agents.yaml`) |
| MX-2 | Matrix AS 클라이언트 | `channels/matrix_channel.py` (신규) | MatrixAS 클래스: 에이전트 가상 계정 등록/display_name/룸 생성/참가/메시지 전송. aiohttp + yarl.URL(encoded=True)로 URL 이중 인코딩 방지 |
| MX-3 | AS 이벤트 수신 라우터 | `api/routers/matrix.py` | `PUT /_matrix/app/v1/transactions/{txnId}` → AgentReactor. `GET /_matrix/app/v1/users/{userId}` 가상 유저 확인. room_id→channel 역방향 매핑 |
| MX-4 | 서버 자동 셋업 | `api/server.py` | lifespan 시작 시 `setup_all_agents()` 백그라운드 실행. 16개 에이전트 등록 + 5개 룸 생성/참가 + room_id→channel 매핑 |
| MX-5 | AgentReactor Matrix 연동 | `hr/agent_reactor.py` | 에이전트 반응 생성 후 Matrix 룸에도 동시 포스팅. `@jx_coder`, `@jx_researcher` 등 독립 계정으로 메시지 전송 |
| MX-6 | 다중 에이전트 페르소나 | `agents/personas.py` | mbti/background/quirks/catchphrase/conflict_style/collaboration_note 필드 추가. 16명 풍부한 한국 직장인 캐릭터 설정 |
| MX-7 | API 키/모델 업그레이드 | `.env` | ANTHROPIC_API_KEY 교체. CLAUDE_MODEL=claude-opus-4-6 (최신). CLAUDE_FALLBACK_MODEL=claude-sonnet-4-6 |
| MX-8 | 앱 로깅 설정 | `main.py` | logging.basicConfig(INFO) 추가. 앱 로거 출력 정상화 |
| MX-9 | scheduler 콜백 수정 | `api/server.py` | get_jinxus_core 존재하지 않음 → get_orchestrator().process() 사용 |

**Element 연결**: 홈서버 `http://100.75.83.105:8008`, 계정 `@jinsu:100.75.83.105` / `jinxus2026!`

---

## 버전 v2.4.4 (2026-03-19) — 이채영 CTO 실제 고용 + 팀채팅 SSE 수정

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| CO-32 | JX_CTO 에이전트 구현 | `agents/jx_cto.py` (신규) | 이채영 CTO/QA총괄 실제 에이전트 파일 생성. 코드 리뷰/QA/아키텍처/장애 분류 후 CTO 관점 분석. 백엔드 레지스트리 등록 확인 |
| CO-33 | SSE 자동 재연결 | `lib/api.ts` streamChannel | 연결 끊김 시 지수 백오프(1s→2s→…→15s) 자동 재연결. 서버 재시작 후 새로고침 불필요 |
| CO-34 | SSE 채널 전환 최적화 | `components/tabs/CompanyChat.tsx` | activeChannel → ref로 변경. 부서 채널 전환 시 SSE 재연결 제거. 연결 1개 유지 |

---

## 버전 v2.4.3 (2026-03-19) — 하드코딩 제거 + 에이전트 병렬 직접 실행

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| CO-24 | personas 단일 소스 (BE) | `agents/personas.py` | AgentPersona에 skills/team/channels 필드 추가. CHANNEL_AGENT_MAP 자동 생성. 하드코딩 에이전트 목록 전체 제거 |
| CO-25 | AgentReactor 파생화 | `hr/agent_reactor.py` | CHANNEL_DEFAULT_AGENTS·AGENT_SKILLS 하드코딩 제거 → personas.py에서 자동 파생. `__init__`에서 `CHANNEL_AGENT_MAP` 직접 사용 |
| CO-26 | HR Manager 파생화 | `hr/manager.py` | 하드코딩 existing_agents 제거 → PERSONAS 순회 자동 등록. 순환 임포트 방지를 위해 지연 임포트 적용 |
| CO-27 | personas 단일 소스 (FE) | `lib/personas.ts` | FIRST_NAME_EMOJI(firstName→emoji 파생), getTeamGroups() 추가. 16개 에이전트 전체 정의 |
| CO-28 | CompanyChat 부서 채널 | `components/tabs/CompanyChat.tsx` | AGENT_EMOJI 하드코딩 제거 → FIRST_NAME_EMOJI 사용. 채널 🏢전체/💻개발부서/🔬리서치부서/🖥️운영부서/📋플래닝으로 재구성. ChannelMembers 컴포넌트 추가 |
| CO-29 | GraphTab 파생화 | `components/tabs/GraphTab.tsx` | TEAM_AGENTS 하드코딩 제거 → getTeamGroups() 사용 |
| CO-30 | 병렬 에이전트 실행 | `hr/agent_reactor.py` | `_execute_task`: JINXUS_CORE 단독 처리 제거 → 분류된 에이전트들이 병렬로 직접 실행(asyncio.gather). 각 에이전트 결과를 소속 채널에 게시. JINXUS_CORE는 타 채널 작업 시 원래 채널에 요약만 |
| CO-31 | 순환 임포트 해결 | `hr/manager.py` | jinxus.agents.personas 모듈 레벨 임포트 제거 → `_register_existing_agents()` 내부 지연 임포트로 변경. 백엔드 정상 기동 확인 |

---

## 버전 v2.4.2 (2026-03-19) — CEO명 JINXUS + 이채영 CTO 고용 + UI 정리

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| CO-19 | CEO 이름 통일 | `agents/personas.py`, `lib/personas.ts`, `CompanyChat.tsx` | JINXUS_CORE korean_name: 진우 → JINXUS. 채널/직원현황/에이전트탭 전체 JINXUS로 표시 |
| CO-20 | 이채영 (JX_CTO) 고용 | `agents/personas.py`, `hr/manager.py`, `hr/agent_reactor.py`, `lib/personas.ts`, `GraphTab.tsx` | 이채영(채영) CTO/QA총괄 신규 에이전트. general/engineering/ops/planning 채널 참석. 직원 현황 전사팀에 표시 |
| CO-21 | 채팅 인사말 수정 | `components/tabs/ChatTab.tsx` | "안녕하세요, 주인님" → "안녕하세요," |
| CO-22 | 브라우저 탭 타이틀 | `app/layout.tsx`, `app/page.tsx` | 정적: "JINXUS". 동적: systemApi.getInfo() 후 "JINXUS - v{버전}"으로 업데이트 |
| CO-23 | 연결 검증 | 채널 API | POST /channel/message → 진수 메시지 → JINXUS(CORE) 반응 확인. 팀 채널 정상 동작 확인 |

---

## 버전 v2.4.1 (2026-03-19) — 직원 이름 통일 + GraphTab → 직원 현황

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| CO-14 | 페르소나 상수 (FE) | `lib/personas.ts` | PERSONA_MAP — 에이전트 코드 → {성+이름, 이름, 직함, 팀, 채널, 이모지}. getDisplayName/getFirstName/getRole/getPersona 헬퍼. 프론트엔드 전체에서 단일 참조 |
| CO-15 | GraphTab → 직원 현황 | `components/tabs/GraphTab.tsx` | 워크플로우 그래프 제거 → 부서별 직원 카드 레이아웃. 전사/엔지니어링/리서치/운영 4개 팀. 실시간 상태 + 현재 작업 + 팀 채널 이동 버튼 |
| CO-16 | 사이드바 탭 레이블 | `components/Sidebar.tsx` | '그래프' (GitBranch) → '직원 현황' (Users). 사이드바 에이전트 이름도 한국 이름(이름만)으로 변경 |
| CO-17 | AgentCard 한국화 | `components/AgentCard.tsx` | 에이전트 코드 → 성+이름 + 직함 + 이모지 아바타 표시. useAppStore 의존성 제거 |
| CO-18 | AgentsTab 한국화 | `components/tabs/AgentsTab.tsx` | shortName() 제거. 에이전트 목록/전문가팀/채팅헤더 전부 한국 이름+직함+이모지로 통일 |

---

## 버전 v2.4.0 (2026-03-19) — Company OS: 에이전트 직원화 + 팀 채널 + 승인 게이트

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| CO-1 | CompanyChannel | `hr/channel.py` | Redis 기반 에이전트 팀 채널. #general/#engineering/#research/#ops/#planning 5개 채널. asyncio.Queue로 SSE 구독자에게 실시간 전달. general 채널에 전체 미러링 |
| CO-2 | ApprovalGate | `core/approval_gate.py` | 작업 실행 전 진수 승인 게이트. asyncio.Event 대기 + 5분 타임아웃 자동 승인. approved/modified/cancelled 3가지 응답. Redis 영속화 |
| CO-3 | AgentPersonas | `agents/personas.py` | 에이전트별 직원 페르소나. 한국 이름 15명: 진우(CORE)/민준(CODER)/예린(FRONTEND)/재원(BACKEND)/도현(INFRA)/수빈(REVIEWER)/하은(TESTER)/지은(RESEARCHER)/유진(WEB_SEARCHER)/시우(DEEP_READER)/나연(FACT_CHECKER)/소희(WRITER)/현수(ANALYST)/태양(OPS)/아름(PERSONA). get_persona_system_addon() system prompt 자동 주입 |
| CO-4 | 채널 통합 (CORE) | `agents/jinxus_core.py` | decompose 후 → 채널 계획 공지 → 에이전트별 LLM 반응 병렬 생성(fast model) → 승인 게이트 → 실행. 취소 시 early return, 수정 시 feedback 주입 |
| CO-5 | 채널 통합 (agents) | `agents/base_agent.py` | `post_to_channel()` 메서드 추가. 에이전트가 작업 중 팀 채널에 의견 공유 가능 |
| CO-6 | 실행 중 채널 포스팅 | `agents/jinxus_core.py` `_run_agent()` | 에이전트 실행 시작/완료 시 소속 채널에 상태 자동 게시 |
| CO-7 | Channel API | `api/routers/channel.py` | GET /channel/history/{ch}, GET /channel/stream (SSE), POST /channel/message (reactor 트리거), POST /channel/approve, GET /channel/approvals/pending |
| CO-8 | 설정 추가 | `config/settings.py` | `approval_gate_enabled` (기본 True). 환경변수로 게이트 on/off 가능 |
| CO-9 | CompanyChat 탭 | `components/tabs/CompanyChat.tsx` | Slack 스타일 팀 채팅 UI. 한국 이름 표시. 왼쪽 채널 목록 + 오른쪽 메시지 + 승인 카드. approval_request 메시지에 승인/수정/취소 버튼 인라인 표시 |
| CO-10 | 프론트엔드 API | `lib/api.ts` | channelApi 추가 (getHistory/getAllHistory/postMessage/approve/getPendingApprovals/streamChannel) |
| CO-11 | 탭 등록 | `app/page.tsx`, `Sidebar.tsx`, `store/useAppStore.ts` | '팀 채널' 탭 추가 (Building2 아이콘). 타입에 'channel' 추가 |
| CO-12 | 서버 종료 정리 | `api/server.py` | lifespan 종료 시 CompanyChannel + ApprovalGate Redis 연결 정리 |
| CO-13 | AgentReactor | `hr/agent_reactor.py` | 진수 채널 메시지 → 자동 에이전트 반응 엔진. 메시지 분류(casual/question/task) → 담당 에이전트 1~3명 결정 → in-character 반응 병렬 생성 → 채널 게시 → task면 JINXUS_CORE로 실제 실행. fire-and-forget. POST /channel/message에 연동 |

---

## 버전 v2.3.1 (2026-03-16) — 안정화 패치 (리소스 누수 수정 + 동시성 보호 + 종료 처리)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| STAB-1 | Redis 커넥션 try-finally | `core/autonomous_runner.py` | `_save_checkpoint`, `_load_checkpoint`, `_delete_checkpoint`에서 예외 발생 시에도 `aclose()` 보장. 커넥션 누수 수정 |
| STAB-2 | 이벤트 버퍼 asyncio.Lock | `core/background_worker.py` | `_event_buffer`/`_event_subscribers` 동시 접근 보호. `subscribe_events`/`unsubscribe_events` async 전환 |
| STAB-3 | 이벤트 구독 await 적용 | `api/routers/chat.py`, `api/routers/task.py` | `subscribe_events`/`unsubscribe_events` 호출부에 `await` 추가 |
| STAB-4 | LLM API 타임아웃 | `core/autonomous_runner.py` | `_create_plan` 120초, `_evaluate_progress` 90초 `asyncio.wait_for` 적용. 네트워크 장애 시 무한 대기 방지 |
| STAB-5 | StateTracker Redis 종료 | `agents/state_tracker.py`, `api/server.py` | `close()` 메서드 추가, lifespan 종료 시 호출 |
| STAB-6 | ArtifactStore Redis 종료 | `core/artifact_store.py`, `api/server.py` | `close()` 메서드 추가, lifespan 종료 시 호출 |
| STAB-7 | ShortTermMemory 종료 | `api/server.py` | lifespan 종료 시 `disconnect()` 호출 |
| STAB-8 | SubprocessManager 방어 강화 | `core/subprocess_manager.py` | `os.killpg` ProcessLookupError 개별 처리, TCP 헬스체크 writer finally 정리 |
| FE-1 | ChatTab 폴링 interval 정리 | `components/tabs/ChatTab.tsx` | 백그라운드 에러 시 setInterval을 ref에 저장, 언마운트 시 cleanup |
| FE-2 | LogsTab clearTimeout 통일 | `components/tabs/LogsTab.tsx` | `clearInterval` → `clearTimeout` (setTimeout ID에 대한 잘못된 호출 수정) |
| FE-3 | Sidebar 비활성 탭 폴링 스킵 | `components/Sidebar.tsx` | `document.visibilityState` 체크 추가 |
| FE-4 | SSE 파서 디버그 로깅 | `lib/sse-parser.ts` | JSON 파싱 실패 시 개발 모드에서 `console.debug` 출력 |
| FE-5 | 폴링 간격 상수 통일 | `lib/constants.ts`, `Sidebar.tsx`, `LogsTab.tsx` | `SIDEBAR_POLLING_MS`, `LOGS_ACTIVE_POLLING_MS`, `LOGS_IDLE_POLLING_MS` 상수화 |

---

## 버전 v2.3.0 (2026-03-15) — 자율 프로젝트 실행 강화 (자동 라우팅 + 아티팩트 + 리뷰 루프 + 프로세스 관리)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| ROUTE-1 | Smart Router (자동 라우팅) | `core/smart_router.py` | 사용자 메시지를 chat/task/background/project 4단계로 자동 분류. 패턴 매칭 → LLM 폴백 2단계 분류 |
| ROUTE-2 | `/chat/smart` 엔드포인트 | `api/routers/chat.py` | 자동 라우팅 SSE 스트리밍. chat/task → 기존 JINXUS_CORE, background → BackgroundWorker, project → ProjectManager 자동 연결 |
| ROUTE-3 | 프론트엔드 스마트 API | `frontend/src/lib/api.ts` | `chatApi.streamSmart()` 추가 |
| ART-1 | Artifact Store | `core/artifact_store.py` | Redis 기반 페이즈 간 아티팩트 공유. file/data/code/report 4종. 자동 추출 (파일경로, 코드블록, 보고서) |
| ART-2 | ProjectManager 아티팩트 통합 | `core/project_manager.py` | 페이즈 완료 시 아티팩트 자동 추출, 후속 페이즈에 아티팩트 컨텍스트 주입, 프로젝트 삭제 시 아티팩트 정리 |
| ART-3 | 아티팩트 API | `api/routers/projects.py` | `GET /projects/{id}/artifacts` 엔드포인트 추가 |
| REVIEW-1 | Review→Fix Loop | `core/review_loop.py` | LLM 기반 코드 리뷰. critical/warning 이슈 감지 → 수정 지시 생성. 최대 2회 반복 |
| REVIEW-2 | ProjectManager 리뷰 통합 | `core/project_manager.py` | 코딩 페이즈 완료 시 자동 리뷰 → 이슈 발견 시 수정 페이즈 동적 추가. depends_on 자동 재배선 |
| PROC-1 | Subprocess Manager | `core/subprocess_manager.py` | 장기 프로세스 시작/중지/재시작/헬스체크. 로그 버퍼, 자동 재시작, 보안 검증 (명령어/디렉토리 화이트리스트) |
| PROC-2 | 프로세스 관리 API | `api/routers/processes.py` | `/processes` CRUD + `/logs` + `/health` 엔드포인트 |
| PROC-3 | 서버 종료 시 프로세스 정리 | `api/server.py` | lifespan 종료 시 `SubprocessManager.stop_all()` 호출 |
| FIX-1 | WAITING 페이즈 디스패치 누락 수정 | `core/project_manager.py` | `_dispatch_ready_phases`에서 `PENDING`만 체크 → `WAITING`도 포함. WAITING 상태 페이즈가 영원히 대기하던 버그 |
| FIX-2 | 수정 페이즈 리뷰 스킵 | `core/project_manager.py` | `is_fix_phase=True`인 페이즈는 리뷰 대상에서 제외. 무한 수정 체인 방지 |
| FIX-3 | 빈 결과 리뷰 방지 | `core/project_manager.py` | 결과가 50자 미만이거나 "계획 생성 실패"인 경우 리뷰 스킵. 의미없는 수정 페이즈 생성 방지 |
| FIX-5 | 페이즈 지시에 파일 생성 명시 | `core/project_manager.py` | `_DECOMPOSE_PROMPT`에 mcp:filesystem/code_executor로 실제 파일 생성하라는 규칙 추가 |
| FIX-6 | BackgroundWorker 작업 유실 대응 | `core/project_manager.py` | `_phase_watcher`에서 task가 None인 경우 (조기 정리됨) 완료 처리. 페이즈가 영원히 running 상태로 남는 버그 |
| ROUTE-4 | Smart Router 분류 정확도 개선 | `core/smart_router.py` | 프로젝트 패턴 확대 (파이프라인, 에이전트, 구조 등), 복합 마커 + 프로젝트 패턴 조합 판정, 백그라운드 패턴 엄격화 |

---

## 버전 v2.2.0 (2026-03-14) — 성능/메모리 누수 패치 + 동시성 개선 + 프론트엔드 연동 + 정리

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| PERF-1 | Anthropic API 비블로킹화 | `jinxus_core.py`, `base_agent.py`, `dynamic_executor.py` | `self._client.messages.create()` → `asyncio.to_thread()` 래핑. 동시 채팅 요청 시 이벤트루프 블로킹 제거. 10개 호출 지점 전부 적용 |
| LEAK-1 | `_cancel_events` TTL 자동 정리 | `api/routers/chat.py` | `Dict[str, Event]` → `Dict[str, tuple[Event, float]]`. 10분 TTL 초과 좀비 엔트리 자동 제거 |
| LEAK-2 | 시스템 프롬프트 캐시 크기 제한 | `tools/dynamic_executor.py` | `_enhanced_system_prompt_cache` 무제한 → 최대 8개 (LRU 방식) |
| LEAK-3 | BackgroundWorker 완료 작업 정리 확장 | `core/background_worker.py` | `clear_completed_tasks()`에서 `_event_subscribers`, `_waiting_tasks`, `_autonomous_runners` 함께 정리 |
| LEAK-4 | JinxMemory.close() 서버 종료 시 호출 | `api/server.py` | lifespan 종료 시 ThreadPoolExecutor 쓰기 풀 안전 종료 |
| FIX-1 | 세마포어 TOCTTOU 수정 | `api/routers/chat.py` | `sem._value` (비공개 API) → `sem.locked()` (공개 API) |
| FIX-2 | executor 싱글톤 race condition | `tools/dynamic_executor.py` | double-check locking 패턴 (`threading.Lock`) 적용 |
| FE-1 | AgentCard AgentsTab 연동 | `components/tabs/AgentsTab.tsx` | 에이전트 미선택 시 오른쪽 패널에 AgentCard 그리드 표시 |
| FE-2 | OrgChart AgentsTab 연동 | `components/tabs/AgentsTab.tsx` | 왼쪽 패널 하단에 조직도 토글 섹션 추가 |
| INF-1 | daemon.sh Linux systemd 수정 | `daemon.sh` | ExecStart → uvicorn 직접 실행, Restart=always, journalctl 로그 |
| CLN-1 | 미사용 파일 삭제 | 4개 파일 | `wrrf_weights.py` (빈 파일), macOS plist 2개, `frontend/rebuild.sh` |
| OPS-1 | JX_OPS 도구 초기화 보호 | `agents/jx_ops.py` | 각 도구 개별 try/except. 하나 실패해도 나머지 도구 정상 작동 |
| COLLAB-1 | 실패 서브태스크 재분배 | `agents/jinxus_core.py` | `_reassign_failed_tasks()`: 에이전트 A 실패 → 대체 에이전트 B에 재위임. `_REASSIGN_MAP` 기반 역량 매칭 |
| MCP-1 | MCP 서버 6개 추가 | `config/mcp_servers.py` | firecrawl, postgres, sentry, todoist + 조건부 활성화 (API 키 기반) |
| MCP-2 | 동적 MCP 로더 API | `api/routers/status.py` | `POST/DELETE /status/mcp/servers` — URL/npm 패키지 입력 → 즉시 연결/등록/제거 |
| MCP-3 | 동적 MCP 로더 UI | `components/tabs/ToolsTab.tsx` | MCP 탭에 "서버 추가" 폼 + 삭제 버튼. 서버명/패키지/환경변수/에이전트 설정 |
| TOOL-1 | data_processor 네이티브 도구 | `tools/data_processor.py` | pandas 기반 CSV/Excel/JSON 분석 (read, describe, filter, query, convert) |
| TOOL-2 | doc_generator 네이티브 도구 | `tools/doc_generator.py` | python-docx/python-pptx 기반 Word/PPT 문서 생성 (마크다운 → 문서 변환) |
| TOOL-3 | Tool Policy 확장 | `core/tool_policy.py` | JX_WRITER/JX_ANALYST에 data_processor, doc_generator, firecrawl 추가 |
| PKG-1 | 패키지 설치 | `requirements.txt` | pdfplumber, feedparser, pandas, openpyxl, python-docx, python-pptx |

---

## 버전 v2.1.0 (2026-03-13) — 리서치팀 체계 + SSE 로그 수정 + 프론트엔드 성능

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| TEAM-R1 | JX_RESEARCHER 팀 오케스트레이터 승격 | `agents/jx_researcher.py` | JX_CODER 패턴 적용. `_decompose_research()` → delegate/direct 모드 분기. 전문가 팀 병렬/순차 실행 + fallback |
| TEAM-R2 | JX_WEB_SEARCHER 신규 | `agents/research/jx_web_searcher.py` | 웹/뉴스 검색, 실시간 정보 수집 전문가. Brave Search, 네이버, RSS, 커뮤니티 |
| TEAM-R3 | JX_DEEP_READER 신규 | `agents/research/jx_deep_reader.py` | 문서/PDF/이미지 심층 분석, GitHub 코드 분석 전문가 |
| TEAM-R4 | JX_FACT_CHECKER 신규 | `agents/research/jx_fact_checker.py` | 교차 검증, 출처 신뢰도 평가, 팩트체크 전문가 |
| TEAM-R5 | 리서치팀 레지스트리 | `agents/research/__init__.py` | RESEARCH_SPECIALISTS 딕셔너리 (코딩팀과 동일 패턴) |
| TEAM-R6 | 리서치팀 Tool Policy | `core/tool_policy.py` | JX_WEB_SEARCHER, JX_DEEP_READER, JX_FACT_CHECKER 각각 전용 정책 |
| TEAM-R7 | 리서치팀 API 엔드포인트 | `api/routers/agents.py` | `GET /agents/JX_RESEARCHER/team` 추가 |
| SSE-1 | BackgroundWorker 이벤트 버퍼 | `core/background_worker.py` | `_event_buffer` 추가. 구독 전 발생한 이벤트 보관 → 구독 시 자동 replay. 실시간 로그 유실 방지 |
| FE-P1 | 비활성 탭 폴링 중지 | `app/page.tsx`, `DashboardTab.tsx`, `AgentsTab.tsx` | `isActive` prop 추가. 숨겨진 탭에서 폴링 완전 중지 → 탭 전환 시 랙 해소 |
| FE-P2 | AgentsTab 리서치팀 UI | `components/tabs/AgentsTab.tsx` | 코더팀 아래 리서치팀 목록 표시 (Search 아이콘, 상태 배지) |
| FE-P3 | API 클라이언트 확장 | `lib/api.ts` | `agentApi.getResearcherTeam()` 추가 |

---

## 버전 v2.0.1 (2026-03-13) — 프론트엔드 버그 수정 + SelfModifier 워크스페이스 확장

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| FE-1 | AgentsTab SSE 필드 불일치 수정 | `components/tabs/AgentsTab.tsx` | 직접 채팅 응답이 화면에 안 뜨던 버그. `event.data.message` → `event.data.content` (api.ts SSEEvent 타입과 일치). tool_call status `undefined` → `?? 'done'` fallback 추가 |
| FE-2 | LogsTab 폴링 완화 | `components/tabs/LogsTab.tsx` | 활성 탭 폴링 500ms → 2000ms. 로그 갱신이 빈번하지 않은데 과도한 API 호출 발생하던 것 수정 |
| FE-3 | GraphTab 편집 UX 개선 | `components/tabs/GraphTab.tsx` | 노드/엣지 편집 시 자동 새로고침 자동 정지 (편집 내용 덮어쓰기 방지). `저장됨` toast → `변경됨 — 자동 갱신 정지됨` (백엔드 미반영 명시). 힌트에 "편집은 시각화 전용" 안내 추가 |
| SM-1 | SelfModifier WORKSPACE_ROOT 지원 | `tools/self_modifier.py` | `_safe_path()` 확장: `PROJECT_ROOT`(JINXUS 자기 수정) + `WORKSPACE_ROOT`(=/home/jinsookim, 신규 프로젝트 개발) 모두 허용. `list_source`에 `root_dir` 파라미터 추가 |
| SM-2 | git_status/git_commit async화 | `tools/self_modifier.py` | sync `subprocess.run` → async `_run_cmd()`. 이벤트 루프 블로킹 제거 |
| QA-1 | silent `except: pass` 전수 제거 | 50개 위치, 24개 파일 | `except Exception: pass` → `logger.warning()/logger.debug()`. teardown/cleanup은 debug, 실질 오류는 warning. `json.JSONDecodeError` 폴백 cascade는 의도된 패턴으로 유지 |
| NOTE-1 | 개발 노트 시스템 추가 | `api/routers/dev_notes.py`, `components/tabs/NotesTab.tsx` | `docs/dev_notes/*.md` CRUD API + 프론트엔드 뷰어/편집기. Sidebar에 "개발 노트" 탭 추가. react-markdown + remark-gfm 렌더링. JINXUS가 작업 완료 후 자동으로 노트 작성하도록 self_modifier description 업데이트 |

---

## 버전 v2.0.0 (2026-03-13) — 자기 수정 능력 + 다중 언어 검증 + 병렬 쓰기

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| BUG-1 | `asyncio.get_event_loop()` 잔존 버그 수정 | `agents/state_tracker.py` | `get_event_loop()` → `get_running_loop()`. v1.9.6에서 background_worker.py는 수정됐는데 state_tracker.py 미수정분 완료 |
| SELF-1 | `SelfModifier` 도구 신규 추가 | `tools/self_modifier.py` | JINXUS 자기 수정 도구. 다중 언어 검증: Python(ast.parse), TS/TSX/JS/JSX(esbuild — frontend/node_modules 우선), Rust(rustfmt exit code 2), JSON(json.loads). 툴 없으면 검증 스킵(graceful). `write_files` 배치 액션으로 여러 파일 병렬 검증+쓰기. `restart_backend`는 httpx Unix socket → Docker API |
| SELF-2 | Docker 소켓 마운트 | `docker-compose.yml` | `/var/run/docker.sock:ro` 추가. `restart_backend` 구현 |
| SELF-3 | `PROJECT_ROOT` 환경변수 추가 | `docker-compose.yml` | `PROJECT_ROOT=/home/jinsookim/jinxus`. SelfModifier 경로 기준점 |
| SELF-4 | Tool Policy 업데이트 | `core/tool_policy.py` | JX_CODER, JX_BACKEND, JX_INFRA whitelist에 `self_modifier` 추가 |
| SELF-5 | 도구 레지스트리 등록 | `tools/__init__.py` | SelfModifier import + 등록 |

**자기 수정 워크플로우**:
1. `read_file` / `list_source` → 현재 코드 파악
2. `write_file` (단일) 또는 `write_files` (병렬) → 언어별 검증 후 쓰기
3. `restart_backend` → 변경사항 반영 (30초 후 복구)

**언어별 검증**:

| 확장자 | 검증기 | 비고 |
|--------|--------|------|
| `.py` | `ast.parse()` | 항상 사용 가능 |
| `.ts` `.tsx` `.js` `.jsx` | `esbuild` (syntax only, 타입 체크 제외) | frontend/node_modules 우선 |
| `.rs` | `rustfmt --check` (exit 2 = syntax 오류) | 없으면 스킵 |
| `.json` | `json.loads()` | 항상 사용 가능 |
| 그 외 | 검증 없이 통과 | TOML, YAML, MD 등 |

---

## 버전 v1.9.6 (2026-03-12) — 백그라운드 로그 실시간 스트리밍 (근본 수정)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| LOG-1 | AutonomousRunner 이벤트 루프 블로킹 수정 | `core/autonomous_runner.py` | `Anthropic` → `AsyncAnthropic` 전환. `_create_plan`, `_evaluate_progress`의 `messages.create` → `await`. 기존 동기 호출이 이벤트 루프를 블로킹해서 SSE 연결 자체가 안 잡히던 것 수정 |
| LOG-2 | SSELogHandler 루프 캡처 수정 | `core/background_worker.py` | `asyncio.get_event_loop()` → `asyncio.get_running_loop()` 핸들러 생성 시 캡처. `call_soon_threadsafe`로 안전 스케줄링 |
| LOG-3 | 5분 타임아웃 background task 제외 | `ChatTab.tsx` | `isBackgroundTask` 플래그 추가. 백그라운드 작업 중에는 5분 클라이언트 타임아웃 비적용 |

---

## 버전 v1.9.5 (2026-03-12) — 버전 수정 + 백그라운드 로그 실시간 스트리밍

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| FIX-1 | 버전 1.8.4 → 1.9.5 | `config/settings.py` | `jinxus_version` 하드코딩 수정 |
| LOG-1 | 백그라운드 로그 실시간 스트리밍 | `core/background_worker.py` | `_SSELogHandler` 추가. `_execute_single`/`_execute_autonomous` 실행 중 `jinxus.*` 로거 전체를 SSE progress 이벤트로 실시간 발행. 노이즈(keepalive, 체크포인트 등) 필터링 |

---

## 버전 v1.9.4 (2026-03-12) — 탭 전환 로딩 제거

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| UX-1 | DashboardTab 항상 마운트 유지 | `app/page.tsx` | ChatTab/AgentsTab과 동일하게 항상 마운트, CSS hidden 전환. 탭 이동 시 매번 로딩 스피너 보이던 문제 해결 |
| UX-2 | renderTab() 제거 | `app/page.tsx` | 중간 함수 제거 → 각 탭 조건 직접 렌더링으로 단순화 |

---

## 버전 v1.9.3 (2026-03-12) — HMR 복구 + 프론트엔드 개발 구조 개선

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| HMR-1 | HMR 복구 | `next.config.js` | `assetPrefix: /_bust/${Date.now()}` 제거 — 이게 HMR WebSocket 경로를 망가뜨리는 범인이었음. Cache-Control 헤더만으로 브라우저 캐시 bust 충분 |
| HMR-2 | dev.sh 구조 개선 | `frontend/dev.sh` | 기본: pm2 재시작 (`.next` 유지, HMR 빠름). `--clean`: 캐시 삭제 후 재시작. `--stop/--log` 명령 추가 |

---

## 버전 v1.9.2 (2026-03-12) — 프론트엔드 daemon화 + GraphTab 렌더링 수정

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| INF-1 | 프론트엔드 pm2 daemon화 | `frontend/dev.sh` | `exec npx next dev` (foreground) → pm2 daemon. SSH 세션 종료돼도 유지됨. `pm2 status/logs jinxus-frontend`로 확인 |
| FIX-1 | GraphTab 폴링 toast 스팸 | `GraphTab.tsx` | `toast.error` 최초 로드 실패 시만 표시. `isFirstLoad` ref 추가. 폴링 중 API 실패는 무시 |
| FIX-2 | GraphTab SVG viewBox | `GraphTab.tsx` | 고정 viewBox `"0 0 760 1000"` 추가 + `preserveAspectRatio="xMidYMid meet"`. 좁은 화면에서 노드 클리핑 방지 |
| FIX-3 | ChatTab textarea 전환 | `ChatTab.tsx` | `input[type=text]` → `textarea`. Shift+Enter 줄바꿈 지원. 자동 높이 확장 (최대 160px). 버튼 title 수정 |

---

## 버전 v1.9.1 (2026-03-12) — ChatTab 전송 버튼 통합 (자동 라우팅)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| UX-1 | 전송/백그라운드 버튼 통합 | `ChatTab.tsx` | Cog(백그라운드) 버튼 제거. Send 버튼 하나로 통합. `shouldRunBackground()` 헬퍼로 메시지 내용 자동 판단: 구현·개발·리팩토링 등 복잡 키워드 포함 or 120자 초과 시 → 백그라운드 자율 모드, 아니면 → SSE 즉시 스트리밍 |
| UX-2 | Enter 키 전송 | `ChatTab.tsx` | 기존 Ctrl+Enter → Enter로 변경 (Shift+Enter는 줄바꿈 허용) |

---

## 버전 v1.9.0 (2026-03-12) — 코드 품질 정리 + 에이전트 직접 채팅 + 그래프 500 수정

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| REF-1 | `AutonomousRunner` 생성자 파라미터 정리 | `autonomous_runner.py`, `background_worker.py` | `runner._progress_update = ...` 직접 대입 제거 → 생성자 `progress_update=` 파라미터로 전달 |
| REF-2 | 완료 작업 주기적 정리 | `background_worker.py` | `_worker_loop`에 1시간 주기 `clear_completed_tasks()` 추가 (worker-0 전담). 완료 작업 인메모리 무한 누적 방지 |
| REF-3 | 오케스트레이터 초기화 패턴 통합 | `api/deps.py` (신규), `agents.py`, `status.py`, `task.py`, `chat.py` | 6개 파일 8군데 중복된 3줄 패턴 → `get_ready_orchestrator()` 한 함수로 통일 |
| REF-4 | `loadAgents` 동시 호출 보호 | `useAppStore.ts` | `_agentsLoading` 플래그 추가. 탭 전환 시 동시 다중 호출로 인한 중복 요청 방지 |
| BUG-1 | `get_orchestrator` import 누락 → 500 | `agents.py`, `status.py`, `task.py` | REF-3 작업 중 `get_ready_orchestrator`로 교체하면서 직접 호출하는 함수들의 import가 사라짐 → `NameError` → `/agents/runtime/all` 500 → 그래프 탭 매번 에러 토스트 |
| FEAT-1 | 에이전트 직접 채팅 | `AgentsTab.tsx`, `chat.py`, `api.ts` | AgentsTab 좌우 분할 레이아웃. 왼쪽: 컴팩트 에이전트 목록. 오른쪽: 선택 에이전트와 직접 대화 패널 (JINXUS_CORE 우회). 도구 호출 배지 실시간 표시 |
| FEAT-2 | `/chat/agent/{agent_name}` 엔드포인트 | `chat.py` | 특정 에이전트 직접 SSE 스트리밍. `prompts/{agent}/system.md` 자동 로드. tool_call 이벤트 방출 |
| FEAT-3 | SSE `tool_call` 이벤트 타입 추가 | `api.ts` | `SSEEvent.event`에 `'tool_call'` 추가, `data.tool` 필드 추가 |

---

## 버전 v1.8.4 (2026-03-12) — ToolsTab 완전 연결 (analytics + plugins 탭)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| UI-1 | 도구 통계 탭 추가 | `ToolsTab.tsx`, `api.ts` | `/status/tool-analytics` 연결. 도구별 호출 횟수·성공률·평균 응답시간·사용 에이전트. 요약 카드 3개 + 상세 테이블 |
| UI-2 | 플러그인 탭 추가 | `ToolsTab.tsx` | `pluginsApi` 연결. 도구 활성화/비활성화 토글, 전체 재로드. 네이티브/MCP 타입 구분 |
| UI-3 | PluginInfo 타입 보강 | `api.ts` | `is_mcp?: boolean` 필드 추가 |

---

## 버전 v1.8.3 (2026-03-12) — 도구 추가 (RSS/주식코인/커뮤니티 모니터링)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| TOOL-3 | RSS 피드 구독 도구 | `tools/rss_reader.py` | feedparser 기반. 여러 피드 동시 집계 + 키워드 필터. HN/TechCrunch/Reddit 등 단축키 지원 |
| TOOL-4 | 주식/코인 시세 도구 | `tools/stock_price.py` | CoinGecko(코인) + Yahoo Finance(주식) 무료 API. 국내주식(삼성전자 등) + 미국주식 + BTC/ETH 등 |
| TOOL-5 | 커뮤니티 모니터링 도구 | `tools/community_monitor.py` | Reddit(Hot/Search) + HackerNews(Top/Search) 게시물·댓글 수집. API 키 불필요 |

---

## 버전 v1.8.2 (2026-03-12) — GraphTab 안정화 + 도구 확장 (PDF/이미지/Slack/Notion)

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| GFX-1 | GraphTab 드래그 crash 수정 | `GraphTab.tsx` | `getScreenCTM()` null 체크 추가 — Firefox/미마운트 SVG에서 `!.inverse()` crash 방지 |
| GFX-2 | GraphTab stale closure 수정 | `GraphTab.tsx` | `onSVGMouseUp`에서 `graph` 대신 `graphRef.current` 사용. `useEffect`로 ref 동기화 |
| TOOL-1 | PDF 읽기 도구 추가 | `tools/pdf_reader.py` | pdfplumber 기반. 페이지 범위 지정 가능. 최대 글자 수 제한. JX_RESEARCHER/WRITER/ANALYST 허용 |
| TOOL-2 | 이미지 분석 도구 추가 | `tools/image_analyzer.py` | Claude Vision API (haiku) 래핑. 파일 경로/URL 모두 지원. 최대 5MB. 모든 에이전트 허용 |
| MCP-1 | Slack MCP 추가 | `config/mcp_servers.py` | `@modelcontextprotocol/server-slack`. SLACK_BOT_TOKEN 있을 때만 활성화. JX_OPS/JX_WRITER 허용 |
| MCP-2 | Notion MCP 추가 | `config/mcp_servers.py` | `@notionhq/notion-mcp-server`. NOTION_API_KEY 있을 때만 활성화. JX_WRITER/JX_ANALYST/JX_OPS 허용 |
| CFG-1 | Settings에 Slack/Notion 키 추가 | `config/settings.py` | `slack_bot_token`, `slack_team_id`, `notion_api_key` 필드 추가 |

---

## 버전 v1.8.1 (2026-03-12) — 껍데기 UI 수정: 도구탭 실데이터 + 그래프 시각화

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| FIX-1 | 네이티브 도구 탭 빈화면 버그 | `status.py` | `/status/tools` 응답에 `allowed_agents`, `enabled` 누락 → 프론트 `.length` 런타임 에러 발생. 필드 추가 |
| FIX-2 | 도구 호출 로그 재시작 시 소실 | `status.py` | `/status/tool-logs`가 인메모리 `get_tool_call_logs()`만 사용 → Redis 영속 버전 `get_tool_call_logs_persistent()`으로 교체 |
| FIX-3 | ToolGraph SVG 시각화 | `ToolsTab.tsx` | 노드 카드 그리드 → SVG 원형 레이아웃 그래프. 노드 클릭 연결 하이라이트. 카테고리/엣지타입 색상 구분. 엣지 테이블 행 클릭 연동 |
| NOTE-1 | 텔레그램 백그라운드 작업 | — | 텔레그램 `/bg` → BackgroundWorker.submit() → `/task/active/list`의 `get_all_tasks()` 포함. 코드상 정상 연동. 작업 완료 후 대시보드에서 미표시는 정상 (active 상태만 표시) |

---

## 버전 v1.8.0 (2026-03-12) — Geny 3차 분석 반영: 안정성 + UX 강화

> 참고: [Geny](https://github.com/CocoRoF/Geny) 3차 분석 — 미적용 패턴 4개 도입

| # | 항목 | 파일 | 설명 |
|---|------|------|------|
| JSON-1 | 다단계 JSON 파싱 폴백 | `autonomous_runner.py` | `_parse_json_safe()` — 4단계 폴백(직접→코드블록→정규식→fallback). `_create_plan`, `_evaluate_progress`에 적용. 크래시 방지 |
| ISO-1 | 실패 격리 | `autonomous_runner.py` | `_build_result()`에서 step 실패 격리 — 일부 실패해도 전체 중단 없이 partial success. 실패 step 목록 로깅 |
| SIG-1 | 완료 시그널 감지 | `dynamic_executor.py` | `[TASK_COMPLETE]` → 즉시 성공 반환, `[BLOCKED: reason]`/`[ERROR: reason]` → 즉시 실패 반환. 불필요한 라운드 소비 방지 |
| CTX-1 | 컨텍스트 자동 압축 | `dynamic_executor.py` | 메시지 누적 240k 글자 초과 시 `REMOVE_TOOL_DETAILS` 전략 자동 적용. 도구 결과 축소로 컨텍스트 절약 |
| UI-1 | 에이전트 탭 컴팩트 뷰 | `AgentsTab.tsx` | 큰 카드 → 테이블 리스트. 클릭 시 인라인 로그 펼침. working만 glow |
| UI-2 | 위임 타임라인 수정 | `meta_store.py` | `ORDER BY ASC` → `DESC` — 최근 활동이 가장 오래된 것 보여주던 버그 수정 |
| UI-3 | Sidebar 에이전트 통계 | `Sidebar.tsx` | Geny 패턴 — Total/Running/Errors 3열 요약. 에이전트 클릭 시 로그탭 이동 + 해당 에이전트 필터 자동 적용. working만 glow dot |
| UI-4 | LogsTab 도구 필터 | `LogsTab.tsx` | 도구 사용 여부 필터 (전체/도구 사용/직접 응답). store logsAgentFilter 구독 — Sidebar 클릭 시 자동 필터 적용 |

---

## 버전 v1.7.2 (2026-03-12) — JX_CODER 전문가 팀 UI 표시

### 2026-03-12 AgentsTab 전문가 팀 섹션 추가

| # | 항목 | 상태 | 설명 | 구현 상세 |
|---|------|------|------|------|
| TEAM-UI-1 | `/agents/JX_CODER/team` 엔드포인트 | 완료 | JX_CODER 하위 5개 전문가 상태 조회 | `agents.py`에 `GET /agents/JX_CODER/team` 추가. `CODING_SPECIALISTS` + `state_tracker`로 실시간 status 반환 |
| TEAM-UI-2 | AgentsTab 전문가 팀 섹션 | 완료 | JX_CODER 전문가 5명 카드 표시 | 메인 에이전트 그리드 아래에 "JX_CODER 전문가 팀" 섹션. 이름·설명·상태 도트·작업 중 task 표시. 폴링 포함 |
| TEAM-UI-3 | `api.ts` `agentApi.getCoderTeam()` 추가 | 완료 | 프론트엔드 API 연결 | `CodingSpecialist` 타입 추가 |

---

## 버전 v1.7.1 (2026-03-12) — HR Soft-Delete + 대시보드 강화 + 위임 로깅

> 참고: [Geny](https://github.com/ysymyth/Geny) — ManagerDashboard 위임 이벤트, Soft-Delete + Restore, 난이도 기반 실행

### 2026-03-12 HR/대시보드/위임 로깅 개선

| # | 항목 | 상태 | 설명 | 구현 상세 |
|---|------|------|------|------|
| HR-1 | Soft-Delete + Rehire | 완료 | 해고 시 레코드 보존, 재고용 가능 | `fire()` → `is_active=False` + `fired_at` + `fire_reason`. `rehire()` → 재활성화 + 부모 재등록. API: `POST /hr/rehire/{id}`, `GET /hr/fired` |
| HR-2 | AgentsTab 해고 에이전트 표시 | 완료 | 해고된 에이전트 목록 + 재고용 버튼 | 접기/펼치기 UI, 해고일/사유 표시, 재고용 시 toast 알림 |
| DASH-1 | 에이전트 성능 비교 바 | 완료 | 성공률 막대 + 작업 수 + 평균 소요시간 | `logsApi.getSummary()` → `agent_stats` 활용 |
| DASH-2 | 위임 이벤트 타임라인 | 완료 | CORE → 서브에이전트 위임/완료 실시간 표시 | Redis `jinxus:delegation_log` (list, max 100). `DelegationLogger` 싱글톤 |
| DASH-3 | 백그라운드 작업 진행 표시 | 완료 | 활성 작업 목록 + 진행률 바 + 스텝 표시 | `taskApi.getActiveTasks()` → paused 상태 포함 |
| DL-1 | DelegationLogger | 완료 | CORE→서브에이전트 위임/완료 이벤트 Redis 기록 | `jinxus_core._run_agent()`에서 delegate/complete 이벤트 자동 기록. API: `GET /status/delegation-events` |
| API-1 | 작업 일시정지/재개 프론트엔드 | 완료 | taskApi에 pauseTask/resumeTask 추가 | ActiveTask 타입에 paused 상태 + steps 필드 추가 |

---

## 버전 v1.7.0 (2026-03-12) — 백그라운드 작업 강화

> 참고: [CrewAI](https://github.com/crewAIInc/crewAI) — FlowPersistence, @listen/@router 체이닝, HumanFeedbackPending, Guardrail, ThreadPoolExecutor 비동기 메모리

### 2026-03-12 AutonomousRunner 전면 개편 + 인프라 강화

| # | 항목 | 상태 | 설명 | 구현 상세 |
|---|------|------|------|------|
| BG-1 | 작업 상태 체크포인트 + 복구 | 완료 | AutonomousRunner 각 step 완료마다 Redis 체크포인트 저장 | Redis `jinxus:checkpoint:{task_id}` 키. `_save_checkpoint()`/`_load_checkpoint()`/`_delete_checkpoint()`. 서버 재시작 시 `_resume_from_checkpoint()`. TTL = `checkpoint_ttl_hours` (기본 24h) |
| BG-2 | 실제 진행률 | 완료 | `completed_steps / total_steps` 기반 진행률 | task.py 50% 하드코딩 제거. BackgroundTask에 `steps_completed`/`steps_total` 필드. `_progress_update` 콜백으로 step마다 SSE `step_progress` 이벤트 발행 |
| BG-3 | 스텝별 타임아웃 | 완료 | 개별 step에 `asyncio.wait_for(timeout)` 적용 | `settings.step_timeout_seconds` (기본 600초). 타임아웃 시 가드레일 재시도 또는 실패 처리 |
| BG-4 | 가드레일 | 완료 | step 결과 LLM 검증 + 피드백 포함 재시도 | `GUARDRAIL_SYSTEM_PROMPT`로 결과 평가. `_validate_step()` → `{valid, reason, feedback}`. 빈 응답 즉시 실패. 실패 시 피드백 컨텍스트 주입 재실행. `settings.guardrail_max_retries` (기본 2) |
| BG-5 | 일시정지/재개 | 완료 | 텔레그램 `/pause` `/resume` + Web API + SSE | `asyncio.Event` 기반. `AutonomousRunner.pause()/resume()`. `BackgroundWorker.pause_task()/resume_task()`. `TaskStatus.PAUSED` 상태. API: `POST /task/active/{id}/pause`, `/resume`. SSE: `paused`/`resumed` 이벤트 |
| BG-6 | 작업 체이닝 | 완료 | 선행 작업 완료 시 후속 작업 자동 트리거 | `BackgroundTask.depends_on` 필드. `submit(depends_on=task_id)`. `_waiting_tasks` 대기열. `_trigger_dependent_tasks()`: 선행 완료 시 결과 주입 + 큐 투입. 실패해도 후속 트리거 |
| BG-7 | 메모리 비동기 write | 완료 | `ThreadPoolExecutor(1)` + drain barrier | `JinxMemory._write_pool`. `save_long_term()` → Future 반환. `_pending_writes` + `_pending_lock`. `drain_writes()`: search 전 자동 flush. `close()`: shutdown 시 drain + executor 종료 |

---

## 버전 v1.6.0 (완료)

### 2026-03-11 JX_CODER 전문가 팀 체계 구축

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| TEAM-1 | JX_CODER 미니 오케스트레이터 승격 | 완료 | JX_CODER가 단순 실행자 → 팀장으로 승격. 작업 분해(`_decompose_task`)로 전문가 배치, 병렬/순차 실행, 리뷰+테스트 후속 단계 |
| TEAM-2 | JX_FRONTEND 전문가 | 완료 | React/Next.js/Vue/Svelte/Angular/Flutter, TypeScript, TailwindCSS, Zustand/Redux, Vite/Webpack, 접근성, Core Web Vitals |
| TEAM-3 | JX_BACKEND 전문가 | 완료 | Python/Go/Rust/Java/Kotlin/C#, FastAPI/Django/Express/Gin/Actix-web/Spring, PostgreSQL/Redis/MongoDB, OAuth2/JWT, Celery/Kafka |
| TEAM-4 | JX_INFRA 전문가 | 완료 | Docker/K8s/Helm, GitHub Actions/ArgoCD, AWS/GCP/Azure/Vercel, Terraform/Ansible, Nginx/Caddy, Prometheus/Grafana/Sentry |
| TEAM-5 | JX_REVIEWER 전문가 | 완료 | OWASP Top 10, SOLID/DRY/KISS, 성능 분석 (N+1, Big O), GoF 패턴/안티패턴, 다국어 리뷰 (Python/TS/Go/Rust/Java) |
| TEAM-6 | JX_TESTER 전문가 | 완료 | pytest/Jest/Vitest/Go test, Playwright/Cypress, 타입 체크 (mypy/tsc), 커버리지, AAA 패턴, hypothesis/property testing |
| TEAM-7 | Tool Policy 확장 | 완료 | 5개 전문가별 도구 접근 정책 추가. REVIEWER는 읽기 전용, TESTER/FRONTEND/INFRA는 git/github 제한 |
| TEAM-8 | 전문가 격리 | 완료 | `agents/coding/` 하위 디렉토리 배치. CORE 자동 스캔 대상에서 제외 — JX_CODER만 내부적으로 관리 |

### 2026-03-11 Continuation + 디버깅 + Progressive Disclosure

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| CONT-1 | DynamicToolExecutor Continuation | 완료 | max_rounds 도달 시 자동 이어하기. 결과 요약 → 새 세션으로 continuation (에이전트별 max_continuations 설정). JX_CODER 최대 60회, JX_REVIEWER 최대 80회 도구 호출 가능 |
| CONT-2 | Continuation 최종 요약 | 완료 | 모든 continuation 소진 시 Claude에게 지금까지 결과 기반 최종 요약 생성 요청. "최대 횟수 도달" 대신 의미있는 응답 반환 |
| CONT-3 | Tool Policy max_continuations | 완료 | AGENT_POLICIES에 에이전트별 continuation 횟수 추가 (JX_CODER/JX_REVIEWER: 3, 나머지: 1~2) |
| DBG-1 | ACH 디버깅 모드 | 완료 | _decompose_task에 mode="debug" 추가. 가설 3개 생성 → 전문가 병렬 조사 → 증거 기반 수렴 → 자동 수정 시도 |
| PD-1 | Progressive Disclosure | 완료 | TOOL_SELECTION_GUIDE를 에이전트 보유 도구 기반 동적 생성. 불필요한 가이드 제거로 토큰 절약 + LLM 혼동 감소 |
| OWN-1 | Exclusive File Ownership | 완료 | _decompose_task에 파일 소유권 분리 원칙 추가. 병렬 실행 시 같은 파일을 두 전문가에게 배정하지 않도록 강제 |

### 2026-03-11 GitHub 도구 접근 정책 수정

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| FIX-1 | JX_CODER GitHub 도구 접근 | 완료 | tool_policy에 `github_agent`, `github_graphql` 추가. deprecated `mcp:github:*` 제거 → blacklist |
| FIX-2 | JX_REVIEWER GitHub 읽기 허용 | 완료 | `github_agent`, `github_graphql` whitelist 추가. 레포 코드 리뷰 시 GitHub 접근 가능 |
| FIX-3 | JX_REVIEWER 도구 한도 상향 | 완료 | max_tool_rounds 8→20. 레포 전체 리뷰 시 파일 다수 읽기 가능 |
| FIX-4 | allowed_agents 확장 | 완료 | `github_agent`에 JX_CODER/JX_REVIEWER 추가, `github_graphql`에 JX_REVIEWER 추가 |
| FIX-5 | TOOL_SELECTION_GUIDE 모순 수정 | 완료 | deprecated `mcp__github__*` 참조를 `github_agent`/`github_graphql`로 통일 |

### 2026-03-11 v1.6.0 품질 강화 + 영속화 + UX

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| QA-1 | Silent error 수정 | 완료 | 5개 전문가 에이전트 메모리 검색 `except Exception: pass` → `logger.warning()` 추가. 프로젝트 원칙 준수 |
| QA-2 | 전문가 실패 fallback | 완료 | `_run_specialist()` 실패 시 JX_CODER 직접 처리(`_fallback_direct`) 자동 전환. 전문가 예외 시에도 작업 중단 방지 |
| QA-3 | 팀 진행 SSE 이벤트 | 완료 | `_report_progress(agent_name=)` 확장. 전문가 시작/완료/실패/fallback 단계별 이벤트 발송 |
| QA-4 | 버전 중앙화 | 완료 | `settings.jinxus_version` 추가. server.py 2곳 하드코딩 제거 (`settings.jinxus_version` 참조). 프론트엔드 v1.5.0→v1.6.0 |
| QA-5 | 도구 로그 Redis 영속화 | 완료 | `state_tracker` 도구 호출 로그를 Redis(`jinxus:tool_call_logs`)에 실시간 저장. 최대 500건 유지. 재시작 후에도 조회 가능 |
| QA-6 | 메트릭 Redis 스냅샷 | 완료 | `metrics.py`에 `save_snapshot`/`restore_snapshot` 추가. 서버 시작 시 이전 스냅샷 복원, 5분 간격 자동 저장, 종료 시 최종 저장 |
| QA-7 | 프론트엔드 팀 진행 표시 | 완료 | SSEEvent에 `team_progress` 타입 추가. ThinkingPanel에 전문가 팀 아이콘(👥)/라벨 추가. ChatTab에 이벤트 핸들러 추가 |
| QA-8 | progress callback 에러 로깅 | 완료 | `_report_progress` silent `except: pass` → `logger.debug()` 추가 |

### 2026-03-12 프론트엔드 UI 반영 이슈 수정

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| FIX-6 | 프론트엔드 프로덕션 모드 빌드 갱신 | 완료 | `next start`(프로덕션)로 실행 중인데 빌드가 3/10에 멈춰있어 소스 변경 미반영. 재빌드+재시작 |
| FIX-7 | Sidebar 버전 하드코딩 제거 | 완료 | `v1.6.0` 리터럴 → `systemApi.getInfo()` 동적 로딩. SettingsTab과 동일 패턴 |

---

## 버전 v1.5.0

### 2026-03-10 에이전트 실행 효율화 리팩토링

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| EFF-1 | classify + needs_info 통합 | 완료 | `_classify_input`이 chat/chat_search/task 3가지로 분류. chat 경로에서 `_needs_external_info` API 호출 제거 (3호출→1호출) |
| EFF-2 | evaluate 스킵 (성공 시) | 완료 | `post_execute`에서 TASK_COMPLETE 설정된 경우 `_evaluate_node`에서 재평가 건너뜀 |
| EFF-3 | reflect 조건부 실행 | 완료 | 실패(score < 0.5) 시 Claude 반성 API 호출 스킵. max_tokens 1024→512 축소 |
| EFF-4 | 서브에이전트 memory 중복 제거 | 완료 | CORE의 memory_context를 서브에이전트에 전달. `_receive_node`에서 기존 컨텍스트 있으면 Qdrant 재검색 스킵 |
| EFF-5 | DynamicToolExecutor 캐싱 | 완료 | 도구 스키마, 도구 목록, system_prompt+guide 캐싱. 매 라운드 재빌드 제거 |

### 2026-03-10 백그라운드 작업 웹 UI 연결

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| BG-1 | 백그라운드 작업 생성 (웹 UI) | 완료 | ChatTab에 백그라운드 실행 버튼(Cog 아이콘) 추가. taskApi.createTask() → POST /task (autonomous=true) |
| BG-2 | 작업 진행 SSE 스트림 | 완료 | GET /task/{id}/stream 엔드포인트 추가. BackgroundWorker 인메모리 이벤트 큐 → SSE. started/progress/completed/failed 이벤트 |
| BG-3 | 프론트엔드 스트림 구독 | 완료 | taskApi.streamTaskProgress()로 SSE 구독. ThinkingPanel 터미널 뷰에 단계별 진행 표시. 완료 시 결과 자동 채팅에 표시 |
| BG-4 | Task API 통합 | 완료 | 모든 작업(autonomous/single)을 BackgroundWorker 경유로 통일. Task Store ↔ BackgroundWorker 상태 자동 동기화 |
| BG-5 | 탭 lazy load 최적화 | 완료 | next/dynamic으로 탭 컴포넌트 lazy import. dev 번들 8.5MB → 프로덕션 307KB |

### 2026-03-10 SSE 스트리밍 안정성 강화

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| STB-1 | run_stream 예외 보호 | 완료 | run_stream을 run_stream + _run_stream_inner로 분리. 어떤 예외든 error + done 이벤트 반드시 발송. 프론트엔드 무한 로딩 방지 |
| STB-2 | 메모리 저장 타임아웃 | 완료 | 메모리/캐시 저장을 asyncio.wait_for(10s)로 감싸서 Redis hang 시 done 이벤트 차단 방지 |
| STB-3 | SSE done 보장 (chat.py) | 완료 | event_generator에서 스트림 종료 시 done 이벤트 미발송 감지 → 강제 done 전송 |
| STB-4 | 강제 중지 버튼 개선 | 완료 | taskId 없어도 중지 가능. ThinkingPanel에서 isActive만으로 버튼 표시. 프론트엔드 상태 무조건 초기화 |
| STB-5 | 로딩 타임아웃 자동 중지 | 완료 | 5분 응답 없으면 자동으로 작업 중지 + 에러 토스트 표시 |
| STB-6 | 실행로그 상세화 | 완료 | base_agent 모든 노드에서 progress_callback 호출. jinxus_core 직접 응답 경로에도 분류/모델선택/API호출/취합 단계별 이벤트 추가 |
| STB-7 | 실시간 터미널 로그 | 완료 | TaskLogHandler: Python 로거(jinxus.*)를 SSE "log" 이벤트로 실시간 전달. DynamicToolExecutor에 TOOL_CALL/TOOL_RESULT 로그 추가. ThinkingPanel 터미널/요약 뷰 토글 |

### 2026-03-09 대화 맥락 + 인프라 강화

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| CTX-1 | 대화 맥락 유지 | 완료 | 서브에이전트 위임 시 최근 대화 4건을 instruction에 자동 포함. decompose 프롬프트에 "self-contained instruction" 지침 추가 |
| CTX-2 | 서브에이전트 신원 노출 방지 | 완료 | `_strip_agent_identity()` 메서드 추가. 단일 결과도 에이전트명(JX_*) → JINXUS 치환, MCP/기술 용어 자동 제거 |
| CTX-3 | 기술적 에러 메시지 차단 | 완료 | JX_RESEARCHER 프롬프트에 내부 도구명/MCP 설정 노출 금지 지침 추가. 도구 불가 시 간단 안내로 대체 |
| INF-1 | Docker 멀티스테이지 빌드 | 완료 | Dockerfile 2-stage 구조: builder(gcc, pip wheel, npm) → runtime(wheels 복사, Node.js, Playwright만 포함). 빌드 도구 제거 |
| INF-2 | jinxus healthcheck | 완료 | docker-compose.yml에 `curl -f http://localhost:19000/` healthcheck 추가 (10s interval, 30s start_period) |
| INF-3 | task.py Redis 마이그레이션 | 완료 | 인메모리 dict → Redis 해시(`jinxus:tasks:{id}`) + sorted set 인덱스. TaskStore 클래스. TTL 자동 만료 |
| INF-4 | Tool Policy API (B-6) | 완료 | `GET /status/tool-policies`, `GET /status/tool-policies/{agent}` 엔드포인트 추가. DynamicToolExecutor에 이미 통합 확인 |
| INF-5 | 실시간 도구 호출 로그 | 완료 | state_tracker에 `log_tool_call()` 추가, DynamicToolExecutor에서 자동 기록. `GET /status/tool-logs` API. 프론트엔드 ToolsTab에 "도구 호출 로그" + "정책" 서브탭 추가 (5초 자동갱신) |
| INF-6 | 버전 하드코딩 수정 | 완료 | server.py root 엔드포인트 "1.3.0" → "1.5.0" |

### 2026-03-09 시스템 안정성 + UX 개선

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| H-1 | Observability 메트릭 | 완료 | core/metrics.py: 에이전트/도구/캐시 실행 메트릭 인메모리 수집. `/status/metrics` API 추가. DynamicToolExecutor + ResponseCache에 자동 기록 |
| H-2 | API 재시도 로직 | 완료 | 프론트엔드 apiCall()에 exponential backoff 추가 (502/503/504/408/429 + 네트워크 에러). 최대 2회 재시도 |
| H-3 | MCP 스타트업 보장 | 이미해결 | orchestrator.initialize()에서 이미 `await register_mcp_tools()` 호출 중. 스타트업 보장됨 |
| H-5 | 에러 토스트 통일 | 완료 | DashboardTab, GraphTab, SettingsTab(4곳), ToolsTab(7곳)의 catch 블록에 toast.error 추가 |
| M-1 | 비활성 탭 폴링 중지 | 완료 | DashboardTab, GraphTab의 setInterval에 `document.visibilityState === 'visible'` 체크 추가 |
| M-2 | 메모리 자동 정리 | 완료 | server.py lifespan에 6시간 주기 벡터 메모리 자동 프루닝 (importance < 0.3 + 30일 초과) |
| M-3 | 임베딩 모델 설정화 | 완료 | settings에 embedding_model/embedding_dimensions 추가, long_term.py에서 동적 참조. 하드코딩 제거 |
| M-5 | MCP 자동 재연결 | 완료 | MCPClient.call_tool()에서 세션 없으면 자동 재연결 1회 시도. 연결 끊김 감지 시 세션 제거 → 다음 호출에서 재연결 |
| M-6 | 상태색상 중복코드 제거 | 완료 | lib/utils.ts에 getAgentStatusColor/getAgentStatusText/getTaskStatusColor 추출. DashboardTab, TasksDropdown에서 참조 |
| M-7 | 접근성 개선 | 완료 | MemoryTab select/input, GraphTab select에 aria-label 추가 |
| H-1+ | 헬스체크 강화 | 완료 | /status/health에 Redis/Qdrant 연결 상태, uptime 포함 |

---

## 버전 v1.4.0

### 2026-03-09 GitHub 도구 수정 + 에이전트 협업 시스템

#### GitHub 도구 수정

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| GH-1 | MCP GitHub deprecated 대응 | 완료 | `@modelcontextprotocol/server-github`가 deprecated되어 "Unknown action: unsupported_request" 반환. Tool Policy에서 `mcp:github:*` 차단, `github_agent` (PyGithub REST API)로 대체 |
| GH-2 | github_agent JX_RESEARCHER 허용 | 완료 | `allowed_agents`에 JX_RESEARCHER 추가. Tool Policy whitelist에도 추가 |
| GH-3 | list_commits action 추가 | 완료 | `github_agent`에 커밋 목록 조회 기능 추가. `repo` 지정 시 해당 레포 커밋, `username`만 지정 시 전체 레포 최근 커밋 조회 |
| GH-4 | input_schema 추가 | 완료 | Claude tool_use가 올바른 파라미터를 생성하도록 `github_agent`에 JSON Schema 추가 (action enum, repo, username, query 등) |
| GH-5 | TOOL_SELECTION_GUIDE 업데이트 | 완료 | DynamicToolExecutor 가이드라인에 `github_agent` 사용법 명시, `mcp__github__*` 사용 금지 안내 |

### 2026-03-09 에이전트 협업 시스템

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| COLLAB-1 | 공유 워크스페이스 | 완료 | core/collaboration.py: SharedWorkspace — Redis 기반 에이전트 간 정보 공유 보드. 에이전트가 중간 결과를 게시하면 다른 에이전트가 참조 가능. 자동 만료 (1시간 TTL) |
| COLLAB-2 | 에이전트 간 직접 위임 | 완료 | AgentCollaborator.request_help() — 실행 중 다른 에이전트에게 직접 도움 요청. BaseAgent.request_help() 메서드 추가. 예: JX_RESEARCHER → JX_CODER |
| COLLAB-3 | 협업 실행 모드 | 완료 | execution_mode: "collaborative" 추가. 병렬 실행 + 먼저 끝난 에이전트 결과를 워크스페이스에 게시 → 느린 에이전트가 참조. JINXUS_CORE decompose에서 자동 판단 |
| COLLAB-4 | Communicator 연동 | 완료 | 기존 hr/communicator.py 인프라와 연결. register_agent 시 협업 시스템에도 자동 등록. 위임/결과 메시지 자동 전송 |

### 2026-03-09 8대 핵심 개선 (SSE 실시간 + WebSocket + 캐싱 + 정책엔진 + 요약 + 라우팅 + 자동학습 + 체이닝)

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| IMP-1 | SSE 실시간 도구 호출 이벤트 | 완료 | run_stream()에서 에이전트 실행 중 이벤트를 asyncio.Queue로 실시간 yield. 기존 list 버퍼 방식에서 Queue + create_task로 전환하여 도구 호출 진행 상황이 즉시 프론트엔드에 전달됨 |
| IMP-2 | WebSocket 채팅 엔드포인트 | 완료 | POST /chat/ws WebSocket 엔드포인트 추가. 양방향 실시간 통신 지원. 취소 요청도 WebSocket으로 처리. SSE 엔드포인트는 하위 호환으로 유지 |
| IMP-3 | 에이전트 응답 캐싱 | 완료 | core/response_cache.py 신규. Redis 쿼리 해시 → 응답 캐시 (TTL 5분). run_stream() 진입 시 캐시 확인, 성공 응답만 캐싱. 동일 질문 반복 시 LLM 호출 절약 |
| IMP-4 | Tool Policy Engine (B-6) | 완료 | core/tool_policy.py 신규. 에이전트별 도구 whitelist/blacklist 정책. DynamicToolExecutor에서 자동 필터링. 에이전트별 max_tool_rounds 설정. JX_RESEARCHER는 code_executor 차단, JX_OPS는 전체 허용 등 |
| IMP-5 | 대화 컨텍스트 LLM 요약 | 완료 | core/context_summarizer.py 신규. SessionFreshness COMPACT 시 단순 truncate 대신 LLM으로 오래된 메시지 요약. 최근 10개 원본 유지 + 이전 대화 요약 1개로 압축. 핵심 컨텍스트 보존 |
| IMP-6 | 에이전트 라우팅 정확도 강화 | 완료 | _classify_input() 패턴 매칭 대폭 확장. 명령형 동사(만들어/작성해 등), 질문형(어떻게/왜 등), 영어 동사(create/write 등) 추가. 15자 미만 비질문은 자동 chat. LLM 호출 빈도 감소 |
| IMP-7 | 실패 자동 학습 | 완료 | JinxLoop.analyze_and_learn_failures() 추가. 실패 3건 이상 시 LLM으로 패턴 분석 → 프롬프트 지침 자동 생성. improve_agent() 플로우에 통합. 패턴 분류 7개 카테고리 (도구 선택 오류, 할루시네이션 등) |
| IMP-8 | 멀티턴 도구 체이닝 | 완료 | DynamicToolExecutor에서 이전 도구 결과가 Claude messages에 자동 포함되어 다음 라운드 컨텍스트로 활용. 도구 체인 로깅 추가 (A→B→C 흐름 추적) |

### 2026-03-09 타임존 수정 + 실행 흐름 뷰어 + 성능 최적화 + 텔레그램 비동기

#### 타임존 KST 통일

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| T-1 | 백엔드 datetime.utcnow() → datetime.now() | 완료 | Docker TZ=Asia/Seoul이므로 now()가 KST. 13개 파일 일괄 변경 (base_agent, jinxus_core, state_tracker, task, daemon, background_worker, orchestrator, session_freshness, manager, long_term, meta_store, short_term, scheduler) |
| T-2 | 프론트엔드 timeZone: 'Asia/Seoul' | 완료 | MemoryTab, ChatTab 등 toLocaleString에 KST 명시 |

#### 실행 흐름 뷰어 (ThinkingPanel 확장)

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| EF-1 | meta_store tool_calls 컬럼 | 완료 | agent_task_logs 테이블에 tool_calls TEXT 컬럼 추가 (JSON). ALTER TABLE 마이그레이션 |
| EF-2 | DynamicToolExecutor tool_callback | 완료 | execute()에 tool_callback 파라미터 추가. 도구 호출 전후 콜백 (calling/done/error) |
| EF-3 | 에이전트 _progress_callback 주입 | 완료 | jinxus_core._run_agent()에서 agent._progress_callback 인스턴스 변수 설정. jx_researcher, jx_coder에서 tool_cb 연결 |
| EF-4 | logs API main_task_id 필터 | 완료 | GET /logs?main_task_id=xxx 파라미터 추가. 특정 채팅 메시지의 에이전트 실행 로그 조회 |
| EF-5 | ThinkingPanel 대화 이력 섹션 | 완료 | 로그 패널에 "대화 이력" 섹션 추가. 각 assistant 메시지 클릭 → API로 실행 흐름 조회 (에이전트, 도구, 점수, 소요시간). 데이터 캐시 |
| EF-6 | logsApi.getLogsByTaskId() | 완료 | 프론트엔드 API 메서드 추가. TaskLog에 main_task_id 필드 추가 |

#### 프론트엔드 성능 최적화

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| P-1 | cache-busting 제거 | 완료 | 모든 GET에 `_cb=timestamp` 붙이던 것 제거. next.config.js 헤더로 이미 no-cache 처리중이라 중복 |
| P-2 | 폴링 간격 5초 → 15초 | 완료 | POLLING_INTERVAL_MS 변경. 대부분 idle 상태에서 5초는 과도 |
| P-3 | DashboardTab logsApi.getSummary() 제거 | 완료 | 모든 에이전트 performance 순회 조회하는 무거운 API 제거. systemStatus에서 통계 대체 |
| P-4 | AgentGraph 자체 폴링 제거 | 완료 | 부모 컴포넌트(AgentsTab)가 이미 폴링 중. 마운트 시 1회만 fetch |
| P-5 | useCallback 의존성 버그 수정 | 완료 | DashboardTab, GraphTab, AgentsTab — useCallback(fn, [])이 렌더마다 interval 재등록하던 버그. useRef로 안정화 |
| P-6 | loadAgents 중복 호출 방지 | 완료 | useAppStore에서 agents 이미 로드됐으면 API 재요청 스킵 |

**새로고침 시 API 호출: ~8개 동시 → ~3개로 감소**

#### 텔레그램 비동기 처리

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| TG-1 | 메시지 처리 비동기화 | 완료 | _handle_message를 _handle_message(인증만) + _process_message(실행)으로 분리. asyncio.create_task()로 백그라운드 실행 → 이전 요청이 걸려도 새 메시지 수신 가능 |

#### 채팅 삭제 수정

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| CD-1 | handleClearChat 백엔드 연동 | 완료 | Zustand만 클리어하던 것 → chatApi.deleteSession() 호출 + sessions 목록 갱신. confirm() 제거 |

---

### 2026-03-09 시스템 프롬프트 심층 분석 + 프롬프트 전면 개선

> 참고: leaked-system-prompts (ChatGPT5, Claude 4.1/4.5, Cursor, Devin, Manus, Perplexity, Gemini CLI) 심층 분석 → `sysprompt_ex.md`

#### 프롬프트 개선 (전 에이전트)

| # | 항목 | 적용 대상 | 설명 |
|---|------|----------|------|
| P-1 | 정체성 기반 할루시네이션 방지 (Devin 패턴) | 전 에이전트 | 금지 목록("~하지마") → 정체성 서술("너는 ~하지 않는다"). LLM에 더 효과적 |
| P-2 | 정보 우선순위 계층 (Manus 패턴) | CORE, RESEARCHER | `<information_priority>` 섹션: 도구 결과 > 웹 검색 > 내부 지식. 스니펫 불신 |
| P-3 | 3회 실패 에스컬레이션 (Cursor/Devin 패턴) | 전 에이전트 | `<failure_handling>` 섹션: 동일 에러 3회 시 다른 접근 또는 보고 |
| P-4 | 능력 제한 + 에스컬레이션 경로 (Copilot/Devin 패턴) | 전 에이전트 | `<limitations>` 섹션: 할 수 없는 것 + 막혔을 때 행동 명시 |
| P-5 | 반아첨 오프닝 금지 확대 (Claude 4.1 패턴) | CORE | "네, 알겠습니다", "말씀하신 대로", 긍정 형용사 시작 금지 |
| P-6 | 즉시 확인 응답 (Manus 패턴) | CORE | 복합 작업 시 즉시 간단한 확인 → 최종 결과 보고 |
| P-7 | 산문 우선 (Claude 4.1 패턴) | WRITER | 보고서/문서는 불릿 나열보다 문단 위주 |
| P-8 | 도구 호출 상한 (Perplexity/Cursor 패턴) | CORE | 동일 작업 내 같은 도구 최대 3회 |

#### 프론트엔드 개선

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| F-13 | 에이전트 역할 하드코딩 제거 | 완료 | `AgentCard.tsx` 정적 역할 매핑 → HR API 동적 조회 (`useAppStore.getAgentRole`) |
| F-14 | GraphTab 서브에이전트 하드코딩 제거 | 완료 | `['JX_CODER', ...]` 정적 배열 → `agents.filter(a => a !== 'JINXUS_CORE')` 동적 |
| F-15 | 버전 하드코딩 수정 | 완료 | Sidebar + SettingsTab `v1.3.0` → `v1.4.0` |
| F-16 | GraphTab 폴백 하드코딩 제거 | 완료 | API 실패 시 빈 배열 반환 (하드코딩 에이전트 목록 제거) |
| F-17 | memoryApi 호출 버그 수정 | 완료 | POST → GET 변경 (백엔드와 HTTP 메서드 일치) |
| F-18 | ToolsTab 4탭 확장 | 완료 | MCP 서버 + 네이티브 도구 + ToolGraph 시각화/탐색 + 플러그인 관리 |
| F-19 | SettingsTab 자가 강화 섹션 | 완료 | JinxLoop 수동 트리거, A/B 테스트 이력, 프롬프트 버전 관리/롤백 |
| F-20 | api.ts API 연결 확장 | 완료 | improve, plugins, toolGraph, tools, performance, memory 엔드포인트 연결 |

#### 백엔드 개선

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| B-11 | HR Manager JS_PERSONA 누락 수정 | 완료 | `_register_existing_agents()`에 JS_PERSONA 추가 |
| B-12 | ToolGraph v2: BM25 + wRRF 퓨전 | 완료 | 아래 상세 |
| B-13 | MCP fetch 패키지 교체 | 완료 | `mcp-fetch-server` → `@kazuph/mcp-fetch` (하드코딩 경로 버그 해결) |

| B-14 | DynamicToolExecutor URL→filesystem 차단 | 완료 | filesystem 도구에 URL 전달 시 사전 차단 가드 추가 |
| B-15 | MCP 에이전트 권한 정비 | 완료 | JX_RESEARCHER→GitHub, JX_CODER→filesystem 접근 권한 추가 |

#### 코드 품질 일괄 개선 (Q-시리즈)

| # | 영역 | 내용 |
|---|------|------|
| Q-1 | 보안 | `claude_dangerously_skip_permissions` 기본값 `True`→`False`, 임시경로→영구경로 |
| Q-2 | 에러 | agents.py, task.py `except: pass` → 로깅 추가 |
| Q-3 | 설정 | .env.example 모델명 업데이트 + CLAUDE_FAST_MODEL, GPT_EMB_API_KEY 추가 |
| Q-4 | 하드코딩 | 에이전트 레지스트리 자동 스캔 (jx_\*.py, js_\*.py glob) |
| Q-5 | 하드코딩 | model_router.py 복잡도 키워드/품질 에이전트 → settings.py 이동 |
| Q-6 | 하드코딩 | context_guard.py 토큰 제한 상수 → settings.py 이동 |
| Q-7 | 하드코딩 | task.py 보관 시간/최대 작업 수 → settings.py 이동 |
| Q-8 | 중복 | task.py 텔레그램 알림 3곳 → `_send_telegram()` 헬퍼 추출 |
| Q-9 | 타입 | base_agent.py reflection JSON 파싱 구현 (improvement_hint 활용) |
| Q-10 | 프론트 | 시간 포맷 함수 4곳 중복 → `lib/utils.ts` 통일 |
| Q-11 | 프론트 | 폴링 간격 5곳 하드코딩 → `lib/constants.ts` POLLING_INTERVAL_MS |
| Q-12 | 프론트 | 사이드바 에이전트 수 하드코딩 → MAX_SIDEBAR_AGENTS 상수 |

#### B-12 ToolGraph v2 상세

> 참고: [graph-tool-call](https://github.com/SonAIengine/graph-tool-call), [Geny](https://github.com/CocoRoF/Geny)

| 항목 | 설명 |
|------|------|
| BM25Scorer | 자체 구현 BM25 (k1=1.2, b=0.75). 한국어 bigram + 영어 단어 + camelCase 분리 토크나이저 |
| wRRF 퓨전 | BM25(0.35) + 그래프 BFS(0.65) 두 소스 Weighted Reciprocal Rank Fusion (k=60) |
| History 디모션 | 최근 사용/실패 도구에 0.8x 감쇠 적용 → 같은 도구 반복 선택 방지 |
| 가중치 영속화 | `data/tool_graph_weights.json`에 학습된 노드/엣지 가중치 JSON 저장, 시작 시 자동 복원 |
| 토크나이저 중복 수정 | 2글자 한국어 단어의 bigram=전체 중복 제거 |

**성능 측정 (11개 도구 기준):**
- BM25 스코어링: 쿼리당 ~26μs (API 호출 0건)
- 메모리: ~24KB (BM25 인덱스)
- DynamicToolExecutor 대비 ~100,000배 빠르고 무료

**역할 분담:**
- ToolGraph: 오케스트레이션 레이어 (JINXUS_CORE decompose) - 워크플로우 사전 구성 + 실패 보완
- DynamicToolExecutor: 실행 레이어 (각 에이전트) - Claude tool_use로 실제 도구 선택

#### 프롬프트 버전 백업

| 에이전트 | 버전 |
|---------|------|
| JINXUS_CORE | v1.3 |
| JX_RESEARCHER | v1.5 |
| JX_CODER | v1.2 |
| JX_WRITER | v1.2 |
| JX_ANALYST | v1.2 |
| JX_OPS | v1.2 |
| JS_PERSONA | v1.2 |

---

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
| B-9 | 할루시네이션 방지 (입력 분류 + 검색 실패 처리) | 완료 | 아래 상세 |
| B-10 | 시스템 프롬프트 자기 인식 보강 | 완료 | JINXUS_CORE 프롬프트에 "너는 Claude.ai가 아니다, JINXUS다" 명시 + 할루시네이션 금지 규칙 추가 |

#### B-9 할루시네이션 방지 상세

| 수정 위치 | 문제 | 해결 |
|-----------|------|------|
| `jinxus_core.py` `_classify_input()` | "날씨 알려줘"가 chat으로 오분류 → 도구 호출 자체를 안 함 | `task_patterns` 키워드 목록 추가 (날씨/뉴스/주가/검색/코드 등) — 매칭되면 무조건 task |
| `jinxus_core.py` `_needs_external_info()` | Exception 시 `return False` → 검색 스킵 | `return True`로 변경 — 에러 시 안전하게 검색 시도 |
| `jinxus_core.py` `_quick_web_search()` | 검색 실패해도 빈 문자열 반환 → Claude가 지식으로 지어냄 | 실패 시 "[웹 검색 실패] 절대 지어내지 마세요" 메시지 반환 |
| `jx_researcher.py` `_execute()` | 검색 실패해도 `success=True`, `score=0.7` 반환 | `success=False`, `score=0.2`로 변경 — 실패는 실패로 보고 |

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

#### 인프라 / 스크립트 개선

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| I-1 | .sh 파일 포트 통일 | 완료 | `start.sh`, `stop.sh`, `setup.sh`, `frontend/rebuild.sh`, `frontend/dev.sh` — 포트 1818 → 5000 전면 교체 |
| I-2 | 원격 접속 정보 추가 | 완료 | `start.sh`, `setup.sh`, `rebuild.sh`, `dev.sh`에 로컬/Tailscale/같은 네트워크 접속 URL 안내 |
| I-3 | 프론트엔드 0.0.0.0 바인딩 | 완료 | `start.sh`, `dev.sh`, `rebuild.sh`에 `-H 0.0.0.0` 추가 — 원격 접속 허용 |
| I-4 | daemon.sh Linux(systemd) 지원 | 완료 | macOS(launchctl) + Linux(systemd) 크로스 플랫폼. `install` 시 systemd user service 자동 생성, `logs`에서 journalctl 조회 |
| I-5 | next.config.js standalone 출력 | 완료 | `output: 'standalone'` 추가 — Docker 프로덕션 빌드 지원 (Dockerfile 정상 작동) |
| I-6 | stop.sh next start 프로세스 종료 | 완료 | `npm run dev` 대신 `next dev` + `next start` 모두 종료하도록 수정 |

#### 검색 품질 + 도구 시스템 개선

| # | 항목 | 상태 | 설명 |
|---|------|------|------|
| S-1 | 네이버 검색 API 통합 | 완료 | `tools/naver_searcher.py` 신규. 웹/뉴스/블로그/지식iN/백과사전/지역 카테고리 지원. 일 25,000회 무료 |
| S-2 | OpenWeatherMap 날씨 도구 | 완료 | `tools/weather.py` 신규. 서울 25개 구 좌표 내장, 현재 날씨 + 5일 예보(3시간 간격). 일 1,000회 무료 |
| S-3 | 도구 레지스트리 통합 | 완료 | `tools/__init__.py`에 `naver_searcher`, `weather` 등록 → DynamicToolExecutor가 Claude tool_use로 자동 선택 |
| S-4 | JX_RESEARCHER 실행 흐름 단순화 | 완료 | 복잡한 분기(날씨체크→MCP체크→검색) 제거 → 항상 DynamicToolExecutor 우선, 실패 시 직접 검색 폴백 |
| S-5 | 텔레그램 타이핑 인디케이터 | 완료 | "처리 중입니다, 주인님..." 텍스트 → `send_chat_action("typing")` 4초 주기 갱신 |
| S-6 | 모델 하드코딩 제거 | 완료 | 모든 에이전트/코어의 `model="claude-sonnet-4-20250514"` → `settings.claude_model` / `settings.claude_fast_model` 참조로 변경 |
| S-7 | Docker 컨테이너 KST 시간대 | 완료 | Dockerfile에 `TZ=Asia/Seoul` 설정. UTC → KST 전환 |
| S-8 | Claude 모델 업그레이드 | 완료 | `claude-sonnet-4-20250514` → `claude-sonnet-4-6` (메인), `claude-haiku-4-5-20251001` (분류/평가용) |
| S-9 | context_guard 모델 목록 갱신 | 완료 | `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5` 추가 |

> **API 키 설정 (.env)**
> - `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` — 네이버 검색 (developers.naver.com)
> - `OPENWEATHERMAP_API_KEY` — 날씨 전용 (openweathermap.org)
> - `CLAUDE_MODEL` / `CLAUDE_FALLBACK_MODEL` / `CLAUDE_FAST_MODEL` — 모델 설정 (하드코딩 없음)

#### 향후 개선 예정

| # | 항목 | 설명 | 우선순위 |
|---|------|------|----------|
| B-6 | Tool Policy Engine | 에이전트 역할별 MCP 서버 접근 화이트리스트 필터링 | 중간 |
| B-9 | ToolGraph 추가 개선 | retrieve_with_history 활용 확대, 에이전트별 워크플로우 패턴 분석 | 낮음 |
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
