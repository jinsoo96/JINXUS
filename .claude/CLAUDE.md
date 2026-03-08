# JINXUS 개발 지침

## 이 프로젝트가 뭔지

JINXUS(Just Intelligent Nexus, eXecutes Under Supremacy)는 **진수(주인님)만을 위한 초개인화 멀티에이전트 AI 비서 시스템**이다.
진수는 JINXUS_CORE 하나하고만 대화한다. JINXUS_CORE가 명령을 해석해서 서브에이전트(JX_CODER, JX_RESEARCHER, JX_WRITER, JX_ANALYST, JX_OPS 등)에게 분배하고, 결과를 취합해 보고한다.
에이전트는 HR 시스템으로 동적으로 고용/해고되며, 각자 독립적으로 강화된다.

## 기술 스택

| 계층 | 기술 |
|---|---|
| 백엔드 | FastAPI + LangGraph, Python 3.11+ |
| 프론트엔드 | Next.js 14 + Zustand + TailwindCSS |
| 메모리 | Redis(단기) + Qdrant(장기) + SQLite(메타) |
| AI | Anthropic Claude API (model_router로 sonnet/opus 자동 선택) |
| 채널 | 웹 UI, 텔레그램 봇, CLI, 데몬 |

## 프로젝트 구조

```
backend/jinxus/
├── agents/       # JINXUS_CORE + 서브에이전트 정의
├── api/routers/  # FastAPI 엔드포인트
├── core/         # orchestrator, plugin_loader, context_guard, model_router, tool_graph, workflow_executor
├── memory/       # 3계층 메모리 (Redis/Qdrant/SQLite)
├── tools/        # 플러그인 도구 (code_executor, web_searcher, github, scheduler 등)
├── hr/           # 에이전트 동적 고용/해고 시스템
└── channels/     # 텔레그램, CLI, 데몬

frontend/src/
├── components/   # 탭별 UI (ChatTab, AgentsTab, GraphTab, LogsTab 등)
├── lib/api.ts    # 중앙 집중 API 클라이언트 (모든 백엔드 호출은 여기 경유)
└── store/        # Zustand 상태 관리
```

## 핵심 원칙

### 고결한 코드
- 모든 코드는 실제로 사용되어야 한다. 죽은 코드, 도달 불가능한 분기, 호출되지 않는 함수는 존재해선 안 된다.
- 같은 일을 하는 코드가 두 군데 있으면 안 된다. 하나로 통일한다.
- 하드코딩된 값(에이전트 목록, URL, 설정값)은 동적 조회나 환경변수로 대체한다.
- 에러를 삼키지 않는다. `except: pass`는 금지. 최소한 로깅한다.

### 유기적 연결
- 프론트엔드의 모든 API 호출은 `lib/api.ts`를 경유한다. 컴포넌트에서 직접 fetch 금지.
- 백엔드의 도구(tools/)는 `plugin_loader`가 자동 스캔한다. 파일 하나 = 플러그인 하나.
- 에이전트 목록은 오케스트레이터에서 동적으로 가져온다. 배열 리터럴로 박아넣지 않는다.
- 새 기능을 추가할 때 기존 패턴(라우터 등록, 스토어 구조, 도구 인터페이스)을 따른다.

### 테스팅
- 코드를 수정하면 관련된 전체 테스팅을 진행한다. 타입 체크(tsc --noEmit), 문법 검증(ast.parse), 런타임 확인까지.
- 수정 범위가 넓으면 영향받는 모든 파일을 검증한다.
- 이슈나 개선사항을 발견하면 즉시 알린다.

### 주인님의 의도
- JINXUS는 진수의 생산성을 극대화하는 도구다. 복잡성을 숨기고, 진수는 JINXUS_CORE에게 말만 하면 된다.
- 시스템은 시간이 지날수록 강해져야 한다. 피드백 루프, 메모리 축적, 프롬프트 자동 개선이 핵심이다.
- 과잉 설계하지 않되, 확장 가능한 구조를 유지한다.

## 작업 규칙

1. 작업 내용은 `docs/03_DEVELOP_STATUS.md`에 버전별로 기록한다.
2. 새 문서가 필요하면 `docs/` 안에 번호 붙여서 추가한다.
3. 참조 링크와 레퍼런스는 `docs/05_REFERENCES.md`에 정리되어 있다.
