# JINXUS 대규모 리팩토링 계획

> 작성일: 2026-03-03
> 상태: **✅ 완료**

---

## 1. 피드백 요약

### 사용자 요청사항
1. **폴더 구조 정리**: backend/ + frontend/ 분리
2. **작업 상태 UI**: 우상단 "작업중(N)" 클릭 시 목록 보기 + 중단 기능
3. **에이전트 대시보드**: 고용된 에이전트 목록, 도구 사용 상태, LangGraph 흐름 시각화
4. **HR 시스템**: 에이전트 고용/해고, 새끼 에이전트 스폰, tool화
5. **에이전트 협업**: 회사처럼 조직적 협업, 구조적 흐름

---

## 2. 현재 상태 분석

### 2.1 폴더 구조 (문제점)
```
현재:
JINXUS/
├── agents/, api/, core/, memory/, tools/, config/  (백엔드 - 루트에 혼재)
├── channels/                                        (멀티채널)
├── frontend/                                        (Next.js)
├── node_modules/                                    (루트에 불필요)
├── package.json                                     (MCP만)
├── main.py, requirements.txt                        (백엔드 진입점)
└── 기타 문서/스크립트
```

### 2.2 프론트엔드 현재 상태
- **컴포넌트**: Header, Sidebar, 5개 탭 (Chat, Agents, Memory, Logs, Settings)
- **상태관리**: Zustand (`useAppStore`)
- **에이전트 UI**: AgentsTab에 카드 전시만 (기능 없음)
- **작업 상태**: Header에 숫자만 표시 (상세 보기 없음)

### 2.3 백엔드 현재 상태
- **에이전트 구조**: `BaseAgent` → 5개 Sub-Agent (LangGraph 그래프)
- **협업**: `JINXUS_CORE`가 분해/디스패치/집계
- **작업 관리**: `background_worker.py` (비동기 큐)
- **도구**: 기존 5개 + MCP 93개 (`DynamicToolExecutor`)

---

## 3. 최종 설계

### 3.1 폴더 구조 재편 ✅ 완료

```
목표:
JINXUS/
├── backend/
│   ├── jinxus/                 # Python 패키지
│   │   ├── __init__.py
│   │   ├── agents/
│   │   ├── api/
│   │   ├── core/
│   │   ├── memory/
│   │   ├── tools/
│   │   ├── config/
│   │   ├── channels/
│   │   └── hr/                 # 신규: HR 시스템
│   ├── prompts/
│   ├── main.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── TasksDropdown.tsx    # 신규
│   │   │   ├── AgentCard.tsx        # 신규
│   │   │   ├── AgentGraph.tsx       # 신규
│   │   │   ├── OrgChart.tsx         # 신규
│   │   │   └── HireAgentModal.tsx   # 신규
│   │   └── ...
│   ├── package.json
│   └── Dockerfile
│
├── docker-compose.yml
├── README.md
└── docs/
```

### 3.2 HR 시스템 설계

#### 핵심 클래스
```python
# backend/jinxus/hr/manager.py
class HRManager:
    """에이전트 고용/해고/스폰 관리"""
    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator
        self.agent_pool: Dict[str, AgentRecord] = {}

    async def hire(self, spec: HireSpec) -> AgentRecord
    async def fire(self, agent_id: str) -> bool
    async def spawn_child(self, parent_id: str, spec: SpawnSpec) -> AgentRecord
    def get_org_chart(self) -> OrgChart
```

#### 에이전트 계층 구조
```
JINXUS_CORE (CEO)
├── JX_CODER (SENIOR)
│   └── spawned_coder_001 (JUNIOR)
├── JX_RESEARCHER (SENIOR)
├── JX_WRITER (SENIOR)
├── JX_ANALYST (SENIOR)
└── JX_OPS (SENIOR)
```

#### HR Tool (JINXUS_CORE 전용)
```python
# backend/jinxus/tools/hr_tool.py
class HRTool(BaseTool):
    name = "hr_tool"
    description = "에이전트 고용/해고/스폰 관리"

    async def execute(self, action: str, **kwargs) -> Dict:
        # action: hire, fire, spawn, list, org_chart
```

### 3.3 프론트엔드 UI 설계

#### A. TasksDropdown (작업 상태)
```typescript
// 위치: frontend/src/components/TasksDropdown.tsx
interface TaskItem {
  id: string;
  agent: string;
  status: 'pending' | 'running' | 'done' | 'error';
  startTime: string;
  description: string;
}

// Header 우상단 "작업중(N)" 클릭 시 드롭다운
// - 작업 목록 표시
// - 각 작업 취소 버튼
// - 5초 간격 폴링 업데이트
```

#### B. AgentCard (에이전트 카드)
```typescript
// 위치: frontend/src/components/AgentCard.tsx
interface AgentCardProps {
  name: string;
  status: 'idle' | 'working' | 'error';
  currentTask?: string;
  currentTools: string[];
  graphState: GraphState;  // LangGraph 현재 노드
}

// - 실시간 상태 표시
// - 현재 사용 중인 도구 표시
// - 해고 버튼
```

#### C. AgentGraph (LangGraph 시각화)
```typescript
// 위치: frontend/src/components/AgentGraph.tsx
// 노드: receive → plan → execute → evaluate → reflect → memory_write
// 현재 노드 강조 표시
// React Flow 또는 D3.js 사용
```

#### D. OrgChart (조직도)
```typescript
// 위치: frontend/src/components/OrgChart.tsx
// 트리 구조로 에이전트 계층 표시
// JINXUS_CORE 중심
```

### 3.4 API 엔드포인트

#### 작업 관리
```
GET  /tasks/active          - 활성 작업 목록
DELETE /tasks/{task_id}     - 작업 취소
WS   /ws/tasks              - 실시간 상태 (선택)
```

#### 에이전트 상태
```
GET  /agents/{name}/status  - 실시간 상태
GET  /agents/{name}/graph   - LangGraph 현재 노드
GET  /agents/{name}/tools   - 사용 중인 도구
```

#### HR 시스템
```
POST /hr/hire               - 에이전트 고용
POST /hr/fire               - 에이전트 해고
POST /hr/spawn              - 새끼 에이전트 스폰
GET  /hr/org-chart          - 조직도
GET  /hr/available-specs    - 고용 가능한 에이전트 스펙
```

---

## 4. 상세 구현 계획

### Phase 1: 폴더 구조 재편 ✅ 완료

#### 1.1 백엔드 이동
```bash
# 폴더 생성
mkdir -p backend/jinxus

# Python 모듈 이동
mv agents api core memory tools config channels backend/jinxus/
mv prompts backend/
mv main.py requirements.txt pyproject.toml backend/

# __init__.py 생성
touch backend/jinxus/__init__.py
```

#### 1.2 Import 경로 수정 ✅ 완료
모든 `from agents.xxx` → `from jinxus.agents.xxx`
모든 `from core.xxx` → `from jinxus.core.xxx`
등등...

#### 1.3 프론트엔드 정리 ✅ 완료
```bash
# 루트 node_modules 제거
rm -rf node_modules package-lock.json
```

### Phase 2: 작업 상태 UI ✅ 완료

#### 2.1 백엔드
- `api/routers/task.py` 확장
  - GET /task/active/list: `BackgroundWorker.get_active_tasks()`
  - DELETE /task/active/{id}: `BackgroundWorker.cancel_task(id)`

#### 2.2 프론트엔드
- `TasksDropdown.tsx` 컴포넌트 생성 ✅
- `Header.tsx` 수정: 드롭다운 통합 ✅
- `api.ts` 확장: taskApi 추가 ✅

### Phase 3: 에이전트 대시보드 ✅ 완료

#### 3.1 백엔드
- `agents/state_tracker.py` 생성: 실시간 상태 추적 ✅
- `agents/base_agent.py` 수정: 상태 훅 추가 ✅
- `api/routers/agents.py` 확장: 상태/그래프/도구 API ✅

#### 3.2 프론트엔드
- `AgentCard.tsx` 생성 ✅
- `AgentGraph.tsx` 생성 (SVG 기반) ✅
- `AgentsTab.tsx` 전면 개편 ✅

### Phase 4: HR 시스템 ✅ 완료

#### 4.1 백엔드
- `hr/` 디렉토리 생성 ✅
  - `manager.py`: HRManager 클래스 ✅
  - `agent_factory.py`: 동적 에이전트 생성 ✅
  - `models.py`: HireSpec, SpawnSpec, AgentRecord ✅
- `tools/hr_tool.py` 생성 ✅
- `api/routers/hr.py` 생성 ✅

#### 4.2 프론트엔드
- `HireAgentModal.tsx` 생성 ✅
- `OrgChart.tsx` 생성 ✅
- `AgentsTab.tsx` HR 기능 추가 ✅

### Phase 5: 협업 구조 강화 ✅ 완료

#### 5.1 에이전트 간 통신
```python
# hr/communicator.py ✅
class AgentCommunicator:
    async def send(self, from_agent: str, to_agent: str, content: Any, message_type: MessageType)
    async def delegate(self, from_agent: str, to_agent: str, instruction: str, callback: Optional)
    async def share_result(self, from_agent: str, to_agents: List[str], result: Any)
    async def complete_task(self, task_id: str, result: Any, error: Optional[str])
```

#### 5.2 작업 위임 메커니즘
- JINXUS_CORE에 communicator 통합 ✅
- delegate_to_agent() 메서드 추가 ✅
- broadcast_result() 메서드 추가 ✅
- 결과 버블업 (TASK_RESULT 메시지 타입) ✅

---

## 5. 핵심 파일 수정 목록

### 백엔드 수정
| 파일 | 변경 내용 |
|------|----------|
| `agents/base_agent.py` | AgentState, 상태 훅 추가 |
| `agents/jinxus_core.py` | HR Tool 통합 |
| `core/orchestrator.py` | HRManager 통합 |
| `core/background_worker.py` | 상태 조회/취소 API |
| `api/routers/` | tasks.py, hr.py 추가 |

### 백엔드 신규
| 파일 | 설명 |
|------|------|
| `hr/__init__.py` | HR 모듈 |
| `hr/manager.py` | HRManager 클래스 |
| `hr/agent_factory.py` | AgentFactory |
| `hr/communicator.py` | 에이전트 간 통신 |
| `hr/models.py` | 데이터 모델 |
| `tools/hr_tool.py` | HR Tool |

### 프론트엔드 수정
| 파일 | 변경 내용 |
|------|----------|
| `components/Header.tsx` | TasksDropdown 통합 |
| `components/tabs/AgentsTab.tsx` | 전면 개편 |
| `store/useAppStore.ts` | 상태 확장 |
| `lib/api.ts` | 새 API 추가 |

### 프론트엔드 신규
| 파일 | 설명 |
|------|------|
| `components/TasksDropdown.tsx` | 작업 목록 |
| `components/AgentCard.tsx` | 에이전트 카드 |
| `components/AgentGraph.tsx` | LangGraph 시각화 |
| `components/OrgChart.tsx` | 조직도 |
| `components/HireAgentModal.tsx` | 고용 모달 |

---

## 6. 재사용 가능한 기존 코드

| 위치 | 용도 |
|------|------|
| `core/background_worker.py` | 비동기 작업 큐 기반 |
| `agents/base_agent.py` | LangGraph 그래프 구조 |
| `tools/base.py` | BaseTool 상속 |
| `core/orchestrator.py` | 에이전트 등록 패턴 |
| `frontend/src/lib/api.ts` | API 호출 패턴 |
| `frontend/src/store/useAppStore.ts` | Zustand 패턴 |

---

## 7. 검증 방법

### Phase 1 검증
```bash
cd backend && python main.py  # 서버 정상 실행
cd frontend && npm run dev    # 프론트 정상 실행
```

### Phase 2 검증
- UI에서 "작업중(N)" 클릭 → 드롭다운 표시
- 작업 취소 버튼 클릭 → 작업 중단

### Phase 3 검증
- AgentsTab에서 에이전트 상태 실시간 확인
- LangGraph 노드 변화 시각화

### Phase 4 검증
- "새 에이전트 고용" → 목록에 추가
- "해고" → 목록에서 제거
- 조직도 트리 표시

### Phase 5 검증
- 복잡한 작업 시 에이전트 간 위임 확인
- 결과 공유 로그 확인

---

## 8. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| Import 경로 수정 누락 | grep으로 전체 검색 후 sed 일괄 변경 |
| 프론트엔드 빌드 실패 | TypeScript 타입 에러 우선 수정 |
| WebSocket 복잡성 | 먼저 폴링으로 구현, 추후 WS 전환 |
| HR 동적 생성 불안정 | Factory 패턴으로 표준화 |

---

## 9. 진행 상황

| Phase | 기간 | 상태 |
|-------|------|------|
| Phase 1 | 2일 | ✅ 완료 |
| Phase 2 | 2일 | ✅ 완료 |
| Phase 3 | 3일 | ✅ 완료 |
| Phase 4 | 3일 | ✅ 완료 |
| Phase 5 | 4일 | ✅ 완료 |

---

## 10. 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-03-03 | Phase 1 완료: 폴더 구조 재편 (backend/jinxus 패키지화) |
| 2026-03-03 | Phase 2 완료: TasksDropdown, 작업 취소 API |
| 2026-03-03 | Phase 3 완료: AgentCard, AgentGraph, state_tracker |
| 2026-03-03 | Phase 4 완료: HR 시스템 (HRManager, HRTool, HireAgentModal, OrgChart) |
| 2026-03-03 | Phase 5 완료: AgentCommunicator, 위임 메커니즘, 결과 버블업 |

---

## 11. 생성된 파일 목록

### 백엔드 신규 파일
- `backend/jinxus/__init__.py` - 패키지 초기화
- `backend/jinxus/hr/__init__.py` - HR 모듈
- `backend/jinxus/hr/models.py` - 데이터 모델 (AgentRole, AgentRecord, HireSpec, SpawnSpec, OrgChart)
- `backend/jinxus/hr/manager.py` - HRManager 클래스
- `backend/jinxus/hr/agent_factory.py` - AgentFactory
- `backend/jinxus/hr/communicator.py` - 에이전트 간 통신
- `backend/jinxus/agents/state_tracker.py` - 실시간 상태 추적
- `backend/jinxus/tools/hr_tool.py` - HR Tool
- `backend/jinxus/api/routers/hr.py` - HR API

### 프론트엔드 신규 파일
- `frontend/src/components/TasksDropdown.tsx` - 작업 목록 드롭다운
- `frontend/src/components/AgentCard.tsx` - 에이전트 상태 카드
- `frontend/src/components/AgentGraph.tsx` - LangGraph 시각화
- `frontend/src/components/OrgChart.tsx` - 조직도
- `frontend/src/components/HireAgentModal.tsx` - 에이전트 고용 모달
