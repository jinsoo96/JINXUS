# 그래프 기반 자율 도구 탐색 엔진 설계

> 참고: [graph-tool-call](https://github.com/SonAIengine/graph-tool-call) by 손성준

## 목표

JINXUS의 도구/에이전트 실행을 선형 디스패치에서 **그래프 기반 자율 워크플로우**로 전환한다.
사용자가 "이 코드 분석하고 PR 올려줘"라고 하면, 관련 도구들이 자동으로 워크플로우를 구성하고 순차 실행한다.

## 현재 한계

```
사용자 → CORE decompose → 에이전트 1개 선택 → 도구 1개 실행 → 응답
```
- CORE가 모든 도구 관계를 프롬프트로 알아야 함
- 멀티스텝 워크플로우를 수동으로 분해해야 함
- 도구 간 의존성/순서를 매번 추론해야 함

## 개선 후

```
사용자 → CORE → ToolGraph.retrieve(query)
  → seed 도구 발견 → 그래프 BFS로 워크플로우 자동 구성
  → 노드 순차 실행 (각 노드 결과가 다음 노드 입력)
  → 자율적으로 분기/병합
```

## Phase 1: 도구 그래프 구축

### 1-1. ToolNode / ToolEdge 데이터 모델
- 기존 tools/ 폴더의 모든 도구를 노드로 모델링
- 엣지 타입: REQUIRES, PRECEDES, COMPLEMENTARY, SIMILAR_TO, CONFLICTS_WITH

### 1-2. ToolGraph 클래스
- 노드 등록/조회
- 엣지 기반 BFS/DFS 탐색
- 쿼리 → 관련 도구 워크플로우 반환

### 1-3. 기존 도구에서 자동 그래프 생성
- tool.name, tool.description, tool.input_schema에서 관계 추론
- 수동 엣지 정의 (핵심 관계)

## Phase 2: 자율 노드 탐색 엔진

### 2-1. WorkflowExecutor
- ToolGraph에서 반환된 워크플로우를 순차 실행
- 각 노드 실행 결과를 다음 노드에 전달
- 실패 시 대체 경로 탐색

### 2-2. JINXUS_CORE dispatch 노드 개조
- 기존: 에이전트 1개 선택
- 개선: ToolGraph로 워크플로우 생성 → WorkflowExecutor로 실행

## Phase 3: 런타임 그래프 학습

### 3-1. 워크플로우 패턴 저장
- 성공한 워크플로우 경로를 장기 메모리에 저장
- 엣지 가중치 업데이트 (성공 +, 실패 -)

### 3-2. 패턴 매칭 우선순위
- 유사 쿼리 → 기존 성공 워크플로우 우선 사용
- 새로운 쿼리 → 그래프 탐색으로 새 워크플로우 생성

---

## 구현 순서

1. `core/tool_graph.py` — ToolNode, ToolEdge, ToolGraph 클래스
2. `core/tool_graph.py` — 기존 도구 자동 등록 + 수동 엣지 정의
3. `core/workflow_executor.py` — 워크플로우 순차 실행 엔진
4. `agents/jinxus_core.py` — dispatch 노드에 ToolGraph 통합
5. 메모리 연동 — 워크플로우 패턴 학습
