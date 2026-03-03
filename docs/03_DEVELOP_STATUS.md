# JINXUS 개발 현황

## 버전 v1.2.0 (진행 중)

### 2026-03-03 업데이트

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

#### 3. MCP 도구 선택 문제 (TODO)

**문제:**
- GitHub 레포지토리 분석 요청 시 github MCP 대신 filesystem MCP 선택
- "Path not allowed: /" 오류 발생

**해결 방안 (예정):**
- DynamicToolExecutor 시스템 프롬프트에 도구 선택 가이드라인 추가
- 컨텍스트에서 작업 유형 파악하여 적절한 MCP 도구 선택 유도

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
│   └── jx_ops.py          # 운영 에이전트
├── core/
│   ├── orchestrator.py    # 오케스트레이터 (progress_callback 전달)
│   └── background_worker.py  # 백그라운드 워커 (progress_callback 생성)
├── api/
│   └── routers/
│       └── status.py      # MCP 상태 API
└── config/
    └── mcp_servers.py     # MCP 서버 설정

frontend/src/
├── components/
│   └── tabs/
│       └── ToolsTab.tsx   # MCP 상태 UI
├── lib/
│   └── api.ts             # API 타입 정의
└── store/
    └── useAppStore.ts     # 상태 관리
```
