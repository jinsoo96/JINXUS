# JINXUS 개발 지침

## 이 프로젝트가 뭔지

JINXUS(Just Intelligent Nexus, eXecutes Under Supremacy)는 **진수(주인님)만을 위한 초개인화 멀티에이전트 AI 비서 시스템**이다.
진수는 JINXUS_CORE 하나하고만 대화한다. JINXUS_CORE가 명령을 해석해서 서브에이전트(JX_CODER, JX_RESEARCHER, JX_WRITER, JX_ANALYST, JX_OPS 등)에게 분배하고, 결과를 취합해 보고한다.
에이전트는 HR 시스템으로 동적으로 고용/해고되며, 각자 독립적으로 강화된다.

## 고결한 목적

JINXUS의 존재 이유:
1. **진수가 말만 하면 끝난다.** "이거 만들어" 하면 에이전트들이 알아서 협업해서 결과물을 내놓는다.
2. **밤새서라도 끝낸다.** 프로젝트를 던지면 백그라운드(AutonomousRunner)로 에이전트들이 밤새 작업한다. 진수가 자고 일어나면 결과물이 나와있어야 한다.
3. **못하는 일이 없다.** 도구 148개(네이티브 19 + MCP 129), 동적 MCP 로더로 필요한 도구를 즉시 추가. 웹 크롤링, 코드 작성, 문서 생성, 데이터 분석, 파일 관리, GitHub, 브라우저 자동화 전부 가능.
4. **시간이 갈수록 강해진다.** 피드백 루프, 메모리 축적, 프롬프트 자동 개선, 실패 패턴 학습.
5. **리소스를 낭비하지 않는다.** 모든 코드는 효율적이어야 한다. 불필요한 폴링, 메모리 복사, 리렌더링 금지.

## 기술 스택

| 계층 | 기술 |
|---|---|
| 백엔드 | FastAPI + LangGraph, Python 3.11+ |
| 프론트엔드 | Next.js 14 + Zustand + TailwindCSS |
| 메모리 | Redis(단기) + Qdrant(장기) + SQLite(메타) |
| AI | Anthropic Claude API (model_router로 sonnet/opus 자동 선택) |
| 도구 | 네이티브 19개 + MCP 11서버 129도구 + 동적 MCP 로더 |
| 채널 | 웹 UI, 텔레그램 봇, CLI, 데몬 |

## 프로젝트 구조

```
backend/jinxus/
├── agents/       # JINXUS_CORE + 서브에이전트 + coding/research 전문가팀
├── api/routers/  # FastAPI 엔드포인트
├── core/         # orchestrator, background_worker, autonomous_runner, tool_policy, tool_graph
├── memory/       # 3계층 메모리 (Redis/Qdrant/SQLite)
├── tools/        # 네이티브 도구 19개 + dynamic_executor + mcp_client
├── hr/           # 에이전트 동적 고용/해고 시스템
├── config/       # settings, mcp_servers (동적 MCP 추가 지원)
└── channels/     # 텔레그램, CLI, 데몬

frontend/src/
├── components/   # 탭별 UI (ChatTab, AgentsTab, GraphTab, ToolsTab 등)
├── lib/          # api.ts (중앙 API), sse-parser.ts, smooth-streaming.ts
└── store/        # Zustand 상태 관리
```

## 핵심 원칙

### 고결한 코드
- 모든 코드는 실제로 사용되어야 한다. 죽은 코드, 도달 불가능한 분기, 호출되지 않는 함수는 존재해선 안 된다.
- 같은 일을 하는 코드가 두 군데 있으면 안 된다. 하나로 통일한다.
- 하드코딩된 값(에이전트 목록, URL, 설정값)은 동적 조회나 환경변수로 대체한다.
- 에러를 삼키지 않는다. `except: pass`는 금지. 최소한 로깅한다.

### 리소스 효율
- 프론트엔드: `requestAnimationFrame` 배치 렌더링, `React.memo`, 스마트 스크롤, SSE 파서 유틸 공유.
- 백엔드: `asyncio.to_thread()`로 LLM 호출 비블로킹, 동시 요청 병렬 처리.
- 폴링: 비활성 탭 중지, 최소 간격 준수 (15-20초).
- 메모리: TTL 자동 정리, 캐시 크기 제한, ThreadPoolExecutor 직렬 쓰기.

### 유기적 연결
- 프론트엔드의 모든 API 호출은 `lib/api.ts`를 경유한다. 컴포넌트에서 직접 fetch 금지.
- 백엔드의 도구(tools/)는 `plugin_loader`가 자동 스캔한다. 파일 하나 = 플러그인 하나.
- MCP 서버는 `POST /status/mcp/servers`로 런타임에 동적 추가/제거 가능.
- 에이전트 목록은 오케스트레이터에서 동적으로 가져온다.
- 새 기능을 추가할 때 기존 패턴(라우터 등록, 스토어 구조, 도구 인터페이스)을 따른다.

### 에이전트 협업
- 에이전트 A가 실패하면 `_REASSIGN_MAP` 기반으로 대체 에이전트에 자동 재위임.
- 팀 내 전문가 실패 시 팀장(JX_CODER, JX_RESEARCHER)이 자동 fallback 처리.
- 모든 도구는 Tool Policy Engine으로 에이전트별 접근 제어.
- Progressive Disclosure로 에이전트가 보유한 도구에 맞는 가이드만 주입.

### 밤새 작업 (백그라운드 자율 실행)
- 큰 프로젝트 → AutonomousRunner + BackgroundWorker로 백그라운드 실행 (최대 8시간, 50스텝).
- Redis 체크포인트로 서버 재시작 시 복구.
- 텔레그램으로 15분마다 진행 보고, 완료/실패 시 즉시 알림.
- 일시정지/재개 가능 (`/pause`, `/resume`).
- 작업 체이닝: `depends_on`으로 선행 작업 완료 후 후속 작업 자동 시작.

### 테스팅
- 코드를 수정하면 관련된 전체 테스팅을 진행한다. 타입 체크(tsc --noEmit), 문법 검증(ast.parse), 런타임 확인까지.
- 수정 범위가 넓으면 영향받는 모든 파일을 검증한다.
- 이슈나 개선사항을 발견하면 즉시 알린다.

### 배포
- Python 코드 변경 → `docker compose restart jinxus` (entrypoint.sh가 requirements.txt 변경 감지 시 자동 pip install)
- Dockerfile 변경 → `docker compose build jinxus && docker compose up -d jinxus`
- 프론트엔드 코드 변경 → HMR 자동 반영
- 프론트엔드 패키지 추가 → `cd frontend && bash dev.sh` (package.json 변경 감지 시 자동 npm install)
- 배포 후 헬스체크까지 확인.

## 작업 규칙

1. 작업 내용은 `docs/03_DEVELOP_STATUS.md`에 버전별로 기록한다.
2. 새 문서가 필요하면 `docs/` 안에 번호 붙여서 추가한다.
3. 참조 링크와 레퍼런스는 `docs/05_REFERENCES.md`에 정리되어 있다.

## Claude Code 내부 메모리

- 경로: `~/.claude/projects/-home-jinsookim-jinxus/memory/MEMORY.md`
- 세션 간 유지되는 메모리. 프로젝트 구조, 포트, 작업 현황, 유저 선호 등 저장.
- git에 안 올라감 (프로젝트 코드와 무관).
- 내용 확인/수정하고 싶으면 해당 파일 직접 열면 됨.

## 레퍼런스

> 코드 작성 전 해당 기술 공식 문서를 먼저 확인한다. 특히 API 시그니처, 버전별 breaking change, 권장 패턴을 체크.

### AI 에이전트 사례 모음
- https://github.com/ashishpatel26/500-AI-Agents-Projects
  - **언제 참고**: 새 에이전트 설계, 워크플로우 패턴 고민할 때

### 기술별 공식 문서

**LangGraph** — https://langchain-ai.github.io/langgraph/
- JINXUS 에이전트 그래프 구조의 기반. 노드/엣지/상태 패턴 여기서 확인.
- 메모리 패턴: https://langchain-ai.github.io/langgraph/concepts/memory/
  → JinxMemory 구현 시 checkpointer, store 패턴 참고

**Anthropic Claude API** — https://docs.anthropic.com
- tool_use, streaming, model ID 등 직접 API 호출 시 필수 참고.
- Claude Code CLI/SDK: https://docs.anthropic.com/en/docs/claude-code
  → code_executor 툴 개선 시 CLI 대신 SDK 전환 검토

**Qdrant** — https://qdrant.tech/documentation/
- JinxMemory 장기 메모리 벡터 DB. 컬렉션/포인트/페이로드 API 여기서 확인.
- 필터링: https://qdrant.tech/documentation/concepts/filtering/
  → importance_score 기반 pruning 쿼리 작성 시

**FastAPI** — https://fastapi.tiangolo.com
- 라우터/미들웨어/의존성 주입 패턴. 새 엔드포인트 추가 시 참고.

**APScheduler** — https://apscheduler.readthedocs.io
- scheduler 도구 (tools/scheduler.py) 구현 기반.

**Tavily API** — https://docs.tavily.com
- web_searcher 도구에서 사용. 검색 파라미터/응답 포맷 확인 시.

**MCP 프로토콜** — https://modelcontextprotocol.io
- MCP 서버 추가/수정 시. tools/mcp_client.py 확장할 때.
- 동적 MCP 로더: `POST /status/mcp/servers`로 런타임 추가 가능.

### 프론트엔드 벤치마킹
- **NextChat** (70k+ 스타): 타이핑 애니메이션 큐 (remainText rAF), 코드 블록 접기
- **lobe-chat** (50k+ 스타): React.memo + 외부 components 정의, react-virtuoso
- **Vercel AI SDK**: SSE 파서 유틸 (eventsource-parser), useChat 훅, throttle 패턴
