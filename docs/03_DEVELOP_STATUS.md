# JINXUS 개발 현황

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
