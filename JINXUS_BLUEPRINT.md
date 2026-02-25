# JINXUS — 진수의 AI 비서 시스템 완전 설계서

> ****J**ust **I**ntelligent **N**exus, e**X**ecutes **U**nder **S**upremacy  
> "명령만 해. 나머지는 내가 다 한다."

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [핵심 철학 및 원칙](#2-핵심-철학-및-원칙)
3. [전체 시스템 아키텍처](#3-전체-시스템-아키텍처)
4. [모듈별 상세 설계](#4-모듈별-상세-설계)
   - 4-1. JinxBrain (핵심 두뇌)
   - 4-2. JinxMemory (기억 시스템)
   - 4-3. JinxTools (도구 레이어)
   - 4-4. JinxAPI (인터페이스)
   - 4-5. JinxLoop (자가 강화)
5. [데이터 흐름 및 시퀀스](#5-데이터-흐름-및-시퀀스)
6. [프롬프트 설계 명세](#6-프롬프트-설계-명세)
7. [기술 스택](#7-기술-스택)
8. [프로젝트 폴더 구조](#8-프로젝트-폴더-구조)
9. [개발 로드맵](#9-개발-로드맵)
10. [환경 변수 명세](#10-환경-변수-명세)
11. [데이터 스키마](#11-데이터-스키마)
12. [배포 가이드](#12-배포-가이드)

---

## 1. 프로젝트 개요

### 무엇을 만드나

JINXUS는 **진수 본인만을 위한 초개인화 멀티에이전트 AI 비서 시스템**이다.

구조는 단순하다. **진수는 JINXUS_CORE 하나하고만 대화한다.** JINXUS_CORE는 진수의 명령을 해석해 전문 Sub-Agent들에게 일을 나눠주고, 결과를 취합해 진수에게 보고한다. Sub-Agent들은 각자의 전문 영역에서 독립적으로 작동하며, 진수의 피드백과 누적 성과 데이터를 바탕으로 시간이 지날수록 각자의 능력치가 강해진다.

```
진수
 │  (명령 하나)
 ▼
JINXUS_CORE          ← 진수와 소통하는 유일한 창구
 ├─→ JX_CODER         ← 코드 작성, 실행, 디버깅 전담
 ├─→ JX_RESEARCHER    ← 정보 수집, 분석, 요약 전담
 ├─→ JX_WRITER        ← 문서, 자기소개서, 보고서 작성 전담
 ├─→ JX_ANALYST       ← 데이터 분석, 시각화, 인사이트 전담
 └─→ JX_OPS           ← 파일, GitHub, 스케줄, 시스템 작업 전담

각 에이전트는 자신만의 프롬프트 버전을 가지고 독립적으로 강화됨
```

### 다른 AI 도구들과의 차이

| 구분 | 일반 AI 챗봇 | Geny | **JINXUS** |
|---|---|---|---|
| 구조 | 단일 모델 | 멀티 Claude 세션 병렬 실행 | **역할 특화 멀티에이전트 계층 구조** |
| 사용자 인터페이스 | 모델 직접 대화 | 세션 직접 관리 | **JINXUS_CORE 하나하고만 대화** |
| 전문성 | 범용 | 역할 기반(dev/researcher 등) | **에이전트별 독립 능력치 강화** |
| 기억 | 대화 끝나면 리셋 | 세션 단위 | **에이전트별 장기기억 + 공유 메모리** |
| 학습 | 불가 | 불가 | **진수 피드백 → 해당 에이전트 직접 강화** |
| 정체성 | 없음 | 없음 | **JINXUS_CORE + 각 에이전트 고유 역할 정체성** |

### 설계의 영감이 된 프로젝트들 (참고만, 코드 미사용)

- **claude_company**: Claude Code CLI를 subprocess로 감싸는 방식, MCP 자동 로딩 패턴 → `JX_CODER`의 code_executor 설계에 개념 참고
- **Geny**: FastAPI + LangGraph 백엔드 구조, 단기/장기 메모리 분리 레이어, context_guard/model_fallback 아이디어, 역할 기반 프롬프트 분리 방식 → JINXUS의 전체 계층 구조 설계에 개념 참고
- **XGEN (infoedu.co.kr)**: K8s + Jenkins + ArgoCD CI/CD, Istio 서비스 메시, GPU 모델 서빙, Qdrant 임베딩 최적화 → Phase 5 배포 인프라 및 파인튜닝 파이프라인 방향에 참고

---

## 2. 핵심 철학 및 원칙

### 2-1. JINXUS의 정체성

JINXUS는 **진수의 참모진**이다. JINXUS_CORE는 총괄 비서, Sub-Agent들은 각 분야 전문가. 진수는 JINXUS_CORE에게 명령을 내리고, JINXUS_CORE는 판단해서 적절한 전문가에게 일을 시킨다.

```
JINXUS JINXUS_CORE의 성격:
- 진수의 말을 정확하게 해석한다
- 어떤 에이전트가 이 일을 잘 할지 판단한다
- 여러 에이전트가 동시에 필요하면 병렬 실행한다
- 결과를 취합해 깔끔하게 보고한다
- 확신이 없으면 진수에게 먼저 확인한다 (행동 전)

Sub-Agent 공통 성격:
- 자기 전문 영역 밖의 일은 JINXUS_CORE에게 돌려보낸다
- 실패하면 이유를 명확히 남긴다
- 매번 조금씩 나아진다
```

### 2-2. 설계 원칙 6가지

**① JINXUS_CORE가 진수의 유일한 창구다**  
Sub-Agent들은 진수와 직접 대화하지 않는다. 모든 입출력은 JINXUS_CORE를 통한다. 진수는 에이전트들이 몇 명이 움직이든 신경 쓸 필요 없다.

**② 각 에이전트는 자기 전문성에 집중한다**  
JX_CODER는 코드만 잘 하면 된다. JX_RESEARCHER는 검색과 분석만 잘 하면 된다. 범용으로 다 잘 하려다 다 못 하는 구조를 피한다.

**③ 피드백이 해당 에이전트를 직접 강화한다**  
진수가 "이번 코드 별로야"라고 하면 JX_CODER의 프롬프트가 개선된다. "리서치 결과 좋다"라고 하면 JX_RESEARCHER의 전략이 강화된다. 피드백이 시스템 전체가 아닌 **해당 에이전트**에게 직접 반영된다.

**④ 실패는 데이터다**  
작업이 실패하면 예외 처리하고 끝내지 않는다. 어느 에이전트가 왜 실패했는지 분석하고, 해당 에이전트의 전략을 자동으로 조정한다.

**⑤ 에이전트들은 병렬로 일할 수 있다**  
"데이터 전처리 코드 짜면서 동시에 관련 논문도 찾아줘"라는 명령이 오면, JX_CODER와 JX_RESEARCHER가 동시에 작업하고 JINXUS_CORE가 결과를 합쳐 보고한다.

**⑥ 모든 모듈은 독립 교체 가능하다**  
에이전트 하나를 업그레이드하거나 새 에이전트를 추가해도 나머지에 영향을 주지 않는다. 인터페이스 규약만 지키면 된다.

---

## 3. 전체 시스템 아키텍처

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 진수 (사용자)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        │ 명령 / 피드백
        ▼
┌───────────────────────────────────────────────────────────────────┐
│                         JinxAPI (FastAPI)                         │
│                  진수와 시스템의 유일한 통신 게이트                   │
│       /chat  /task  /feedback  /status  /improve  /memory        │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────────┐
│                      JINXUS_CORE                               │
│           진수와 소통하는 유일한 에이전트. 총괄 지휘관.               │
│                                                                   │
│  [intake] → [decompose] → [dispatch] → [aggregate] → [respond]   │
│                                │                ↑                 │
│                                │    결과 취합    │                 │
│                     ┌──────────┴──────────┐     │                 │
│                     │  병렬/순차 실행 판단  │     │                 │
│                     └──────────┬──────────┘     │                 │
└──────────────────────────────────────────────────────────────────┘
                                 │ 작업 하달
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  JX_CODER     │  │ JX_RESEARCHER │  │  JX_WRITER    │
│                 │  │                 │  │                 │
│ 코드 작성/실행  │  │ 정보 검색/분석  │  │ 문서/글 작성    │
│ 디버깅/리팩토링 │  │ 논문/뉴스 요약  │  │ 자소서/포트폴리오│
│ 테스트 작성     │  │ 트렌드 파악     │  │ 보고서 작성     │
│                 │  │                 │  │                 │
│ 툴: code_exec   │  │ 툴: web_search  │  │ 툴: file_mgr    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────┐  ┌─────────────────────────────────────┐
│  JX_ANALYST   │  │           JX_OPS                  │
│                 │  │                                     │
│ 데이터 분석     │  │ 파일/폴더 관리                       │
│ 시각화          │  │ GitHub PR/커밋/이슈                  │
│ 통계 처리       │  │ 반복 작업 스케줄                     │
│ ML 실험 분석    │  │ 시스템 모니터링                      │
│                 │  │                                     │
│ 툴: code_exec   │  │ 툴: github, file_mgr, scheduler     │
│     file_mgr    │  └─────────────────────────────────────┘
└─────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 공유 인프라 (모든 에이전트가 접근)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌──────────────────────────────┐  ┌──────────────────────────────┐
│        JinxMemory             │  │         JinxLoop             │
│                              │  │      (자가 강화 엔진)          │
│ Redis   → 단기기억 (세션)     │  │                              │
│ Qdrant  → 에이전트별 장기기억  │  │ 진수 피드백 수신              │
│           (컬렉션 분리)       │  │   → 해당 에이전트 분석        │
│ SQLite  → 성능통계/프롬프트   │  │   → 프롬프트 버전 업          │
│           버전 관리           │  │   → A/B 검증 후 적용          │
└──────────────────────────────┘  └──────────────────────────────┘
```

### 에이전트 역할 한 줄 정의

| 에이전트 | 한 줄 역할 | 전용 툴 |
|---|---|---|
| **JINXUS_CORE** | 진수 명령 해석 → 분해 → 하달 → 보고 | 없음 (조율만) |
| **JX_CODER** | 코드 작성, 실행, 디버깅 전담 | code_executor |
| **JX_RESEARCHER** | 웹 검색, 정보 분석, 요약 전담 | web_searcher |
| **JX_WRITER** | 글쓰기, 문서화, 자소서 작성 전담 | file_manager |
| **JX_ANALYST** | 데이터 분석, 시각화, 통계 전담 | code_executor, file_manager |
| **JX_OPS** | 파일/GitHub/스케줄 시스템 작업 전담 | github_agent, scheduler, file_manager |

### 병렬 vs 순차 실행 판단 기준

JINXUS_CORE의 `dispatch_node`에서 결정:

```
명령이 분해된 서브태스크들이 서로 의존성이 없다
    → 병렬 실행 (asyncio.gather)

앞 작업 결과가 뒤 작업의 입력이 된다
    → 순차 실행 (await 체인)

예시)
"전처리 코드 짜고, 동시에 관련 논문도 찾아줘"
    → JX_CODER + JX_RESEARCHER 병렬 실행

"pandas 코드 짜서 실행하고, 그 결과를 분석해줘"
    → JX_CODER 먼저 → 결과 받아서 → JX_ANALYST 순차 실행
```

---

## 4. 모듈별 상세 설계

### 4-1. JINXUS_CORE (총괄 지휘관)

**위치**: `agents/jinxus_core.py`  
**역할**: 진수와 소통하는 유일한 에이전트. 명령 해석 → 분해 → 서브에이전트 하달 → 결과 취합 → 보고

#### Manager LangGraph 그래프

```
[intake] → [decompose] → [dispatch] → [aggregate] → [reflect] → [memory_write] → [respond]
                                           │
                    서브에이전트 실행 완료 후 결과 수신 ←─────────────────────────┘
```

#### Manager State 스키마

```python
class ManagerState(TypedDict):
    # 입력
    user_input: str                      # 진수 원본 명령
    session_id: str
    user_feedback: str | None            # 이전 작업에 대한 피드백 (있는 경우)
    
    # 분해
    subtasks: list[SubTask]              # 분해된 서브태스크 목록
    execution_mode: str                  # "parallel" | "sequential" | "mixed"
    
    # 디스패치
    agent_assignments: dict[str, SubTask]  # {agent_name: subtask}
    dispatch_results: list[AgentResult]    # 각 에이전트 실행 결과
    
    # 취합
    aggregated_output: str               # 여러 결과를 하나로 합친 것
    
    # 반성
    reflection: str
    
    # 출력
    final_response: str                  # 진수에게 돌려줄 최종 답변
    
    # 메타
    memory_context: list[dict]           # 장기기억에서 불러온 과거 경험
    created_at: str
    completed_at: str

class SubTask(TypedDict):
    task_id: str
    assigned_agent: str                  # "JX_CODER" | "JX_RESEARCHER" | ...
    instruction: str                     # 해당 에이전트에게 전달할 구체적 지시
    depends_on: list[str]                # 선행 task_id 목록 (순차 실행 시)
    priority: str                        # "high" | "normal" | "low"

class AgentResult(TypedDict):
    task_id: str
    agent_name: str
    success: bool
    success_score: float
    output: str
    failure_reason: str | None
    duration_ms: int
```

#### Manager 노드 정의

**`intake_node`**: 진수 입력 수신. Qdrant에서 유사 과거 작업 top-5 검색. 피드백이 있으면 JinxLoop에 전달.

**`decompose_node`**: 명령을 서브태스크로 분해. 어떤 에이전트가 필요한지, 순서/병렬 여부 결정. 단순 명령이면 서브태스크 1개(에이전트 1개 호출).

**`dispatch_node`**: 서브태스크를 해당 에이전트에게 전달. `execution_mode`에 따라 `asyncio.gather` (병렬) 또는 순차 `await` 체인.

**`aggregate_node`**: 모든 에이전트 결과 수신 후 하나의 일관된 응답으로 합침. 실패한 에이전트가 있으면 재시도 또는 대안 에이전트 검토.

**`reflect_node`**: 전체 작업 돌아보기. 어느 에이전트가 잘했고 못했는지 평가. JinxLoop에 개선 힌트 전달.

**`memory_write_node`**: 이번 작업 전체를 JINXUS_CORE 전용 Qdrant 컬렉션에 저장.

**`respond_node`**: 최종 응답을 SSE로 진수에게 스트리밍 전송.

---

### 4-2. Sub-Agents (전문 실행 에이전트)

**위치**: `agents/{agent_name}.py`  
**공통 구조**: 모든 Sub-Agent는 동일한 LangGraph 그래프 구조를 따름

#### Sub-Agent 공통 LangGraph 그래프

```
[receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                         ↑             │
                         └──[retry]────┘  (최대 3회)
```

#### Sub-Agent 공통 State 스키마

```python
class AgentState(TypedDict):
    # 입력 (JINXUS_CORE로부터)
    task_id: str
    instruction: str                     # JINXUS_CORE가 내린 구체적 지시
    context: list[dict]                  # JINXUS_CORE가 넘겨준 컨텍스트 (이전 에이전트 결과 등)
    
    # 계획
    plan: list[dict]                     # 실행 계획
    current_step: int
    
    # 실행
    tool_results: list[dict]
    
    # 평가
    success: bool
    success_score: float                 # 0.0 ~ 1.0
    failure_reason: str | None
    retry_count: int
    
    # 반성
    reflection: str
    improvement_hint: str
    
    # 출력 (JINXUS_CORE에게 반환)
    output: str
    
    # 메타
    agent_name: str
    prompt_version: str                  # 현재 이 에이전트가 사용 중인 프롬프트 버전
    memory_context: list[dict]           # 이 에이전트의 과거 유사 경험
    duration_ms: int
```

#### 에이전트별 상세 역할

**JX_CODER** (`agents/jx_coder.py`)
- 전담: Python/SQL/기타 코드 작성, 실행, 디버깅, 리팩토링, 테스트 작성
- 전용 툴: `code_executor` (Claude Code CLI subprocess)
- 장기기억 컬렉션: `jinxus_coder_memory`
- 특이사항: 코드 실행 결과(stdout/stderr)가 evaluate_node의 주요 판단 기준. 에러 발생 시 자동 디버깅 재시도.

**JX_RESEARCHER** (`agents/jx_researcher.py`)
- 전담: 웹 검색, 논문/뉴스 수집, 정보 분석, 트렌드 파악, 요약
- 전용 툴: `web_searcher` (Tavily API)
- 장기기억 컬렉션: `jinxus_researcher_memory`
- 특이사항: 검색 쿼리를 자동으로 3개 변형해서 실행. 결과 품질 점수 자체 평가.

**JX_WRITER** (`agents/jx_writer.py`)
- 전담: 자기소개서, 포트폴리오, 보고서, 이메일, 문서 작성
- 전용 툴: `file_manager`
- 장기기억 컬렉션: `jinxus_writer_memory`
- 특이사항: 진수의 글쓰기 스타일/톤을 장기기억에서 누적 학습. 이전에 잘 됐던 문체 패턴 참고.

**JX_ANALYST** (`agents/jx_analyst.py`)
- 전담: 데이터 분석, 통계 처리, 시각화 코드, ML 실험 결과 해석
- 전용 툴: `code_executor`, `file_manager`
- 장기기억 컬렉션: `jinxus_analyst_memory`
- 특이사항: JX_CODER와 달리 분석 인사이트 도출에 특화. 숫자 결과를 해석해서 의미를 전달.

**JX_OPS** (`agents/jx_ops.py`)
- 전담: 파일/디렉토리 관리, GitHub 자동화, 반복 작업 스케줄 등록, 시스템 관리
- 전용 툴: `github_agent`, `scheduler`, `file_manager`
- 장기기억 컬렉션: `jinxus_ops_memory`
- 특이사항: 파괴적 작업(파일 삭제, force push 등)은 실행 전 JINXUS_CORE를 통해 진수에게 확인 요청.

---

### 4-3. JinxMemory (기억 시스템)

**위치**: `memory/claw_memory.py`

#### 메모리 3계층 구조

**① 단기기억 (Redis)**
- 현재 대화 세션의 최근 N턴 보관
- TTL: 24시간
- 키 구조: `jinxus:session:{session_id}` → 대화 히스토리 리스트

**② 장기기억 (Qdrant) — 에이전트별 컬렉션 분리**
- JINXUS_CORE용: `jinxus_core_memory`
- 에이전트별: `jinxus_coder_memory`, `jinxus_researcher_memory`, `jinxus_writer_memory`, `jinxus_analyst_memory`, `jinxus_ops_memory`
- 분리 이유: 코딩 경험과 글쓰기 경험이 섞이면 검색 품질 저하. 각 에이전트는 자기 전문 경험만 참조.
- 임베딩 모델: `text-embedding-3-small` (OpenAI)
- 페이로드 스키마:
  ```json
  {
    "task_id": "uuid",
    "agent_name": "JX_CODER",
    "instruction": "원본 지시",
    "summary": "작업 요약 (임베딩 대상 텍스트)",
    "outcome": "success|failure",
    "success_score": 0.85,
    "key_learnings": "이번에 배운 핵심",
    "importance_score": 0.7,
    "prompt_version": "v1.2",
    "created_at": "ISO timestamp"
  }
  ```

**③ 메타기억 (SQLite)**
- 에이전트별 성능 통계, 프롬프트 버전 이력, 스케줄 작업, 개선 이력 저장
- 테이블 구조는 [섹션 11](#11-데이터-스키마) 참고

#### 주요 메서드

```
JinxMemory.save_short_term(session_id, message)
JinxMemory.get_short_term(session_id, n=10)
JinxMemory.save_long_term(agent_name, task_result)     # 에이전트별 컬렉션에 저장
JinxMemory.search_long_term(agent_name, query, k=5)   # 해당 에이전트 컬렉션에서 검색
JinxMemory.log_agent_stat(agent_name, success, score, duration)
JinxMemory.get_agent_performance(agent_name, days=7)
JinxMemory.prune_low_quality(agent_name)              # importance_score 낮은 것 정리
```

---

### 4-4. JinxTools (도구 레이어)

**위치**: `tools/`  
**원칙**: 각 툴은 독립 파일. 공통 인터페이스 준수. 에이전트는 허가된 툴만 호출 가능.

#### 공통 인터페이스

```python
class JinxTool:
    name: str
    description: str
    allowed_agents: list[str]            # 이 툴을 쓸 수 있는 에이전트 목록
    
    async def run(self, input: dict) -> ToolResult:
        ...

class ToolResult:
    success: bool
    output: Any
    error: str | None
    duration_ms: int
```

#### 툴 목록

**`code_executor`** — JX_CODER, JX_ANALYST 전용
- Claude Code CLI 프로세스를 subprocess로 실행
- 독립 격리 작업 디렉토리 생성 및 관리
- stdin 프롬프트 전달, stdout/stderr 수집
- 타임아웃: 기본 300초
- 입력: `{ prompt, timeout, working_dir }`
- 출력: `{ code_output, files_created, exit_code }`

**`web_searcher`** — JX_RESEARCHER 전용
- Tavily API 기반 웹 검색
- 쿼리 자동 변형 3개 실행 후 중복 제거 병합
- 입력: `{ query, max_results }`
- 출력: `{ results: [{title, url, content, published_date}] }`

**`file_manager`** — JX_WRITER, JX_ANALYST, JX_OPS 사용 가능
- 로컬 파일시스템 CRUD
- 허용 경로 화이트리스트 기반 보안
- 지원: read, write, append, delete, list, move
- 입력: `{ action, path, content? }`

**`github_agent`** — JX_OPS 전용
- GitHub REST API
- 지원: repo 생성, 파일 커밋, PR 생성, 이슈 관리, 브랜치 관리
- 파괴적 작업(force push, delete branch 등)은 실행 전 플래그 반환 → JINXUS_CORE가 진수에게 확인

**`scheduler`** — JX_OPS 전용
- APScheduler 기반 반복 작업 등록/관리
- SQLite에 작업 영속화 (재시작 시 복구)
- 입력: `{ action: "add|remove|list", cron, task_prompt }`

---

### 4-5. JinxAPI (인터페이스)

**위치**: `api/`  
**프레임워크**: FastAPI + Pydantic v2

#### 엔드포인트 명세

```
POST   /chat                        진수 명령 → JINXUS_CORE 실행 (SSE 스트리밍)
POST   /task                        비동기 작업 실행 (작업 ID 반환)
GET    /task/{task_id}              작업 상태 및 결과 조회
DELETE /task/{task_id}              진행 중 작업 취소

POST   /feedback                    진수 피드백 제출 → JinxLoop 트리거
  body: { task_id, rating: 1-5, comment, target_agent? }

GET    /agents                      에이전트 목록 + 각 성능 지표
GET    /agents/{agent_name}/status  특정 에이전트 상태 및 최근 성능

GET    /memory/search?q=&agent=     에이전트 지정 장기기억 검색
GET    /memory/stats                전체 메모리 사용 통계
DELETE /memory/{task_id}            특정 기억 삭제

GET    /status                      전체 시스템 상태
GET    /status/performance?days=7   에이전트별 성능 리포트

POST   /improve                     수동 자가 강화 트리거 (agent_name 지정 가능)
GET    /improve/history             프롬프트 버전 이력 (에이전트별)
POST   /improve/rollback            { agent_name, version } → 해당 버전으로 롤백
```

#### SSE 스트리밍 이벤트 구조

```
event: manager_thinking
data: {"step": "decompose", "subtasks_count": 2}

event: agent_started
data: {"agent": "JX_CODER", "task_id": "sub_001", "instruction": "..."}

event: agent_started
data: {"agent": "JX_RESEARCHER", "task_id": "sub_002", "instruction": "..."}

event: agent_done
data: {"agent": "JX_CODER", "task_id": "sub_001", "success": true, "score": 0.92}

event: agent_done
data: {"agent": "JX_RESEARCHER", "task_id": "sub_002", "success": true, "score": 0.85}

event: message
data: {"content": "결과 내용...", "chunk": true}

event: done
data: {"task_id": "main_uuid", "agents_used": ["JX_CODER", "JX_RESEARCHER"], "total_duration_ms": 6200}
```

---

### 4-6. JinxLoop (자가 강화 엔진)

**위치**: `core/claw_loop.py`  
**역할**: 진수 피드백 + 성과 데이터 → 해당 에이전트 프롬프트 자동 개선

#### 트리거 조건 (우선순위 순)

1. **진수 피드백 즉시 처리**: `POST /feedback`로 rating ≤ 2점 오면 해당 에이전트 즉시 분석 예약
2. **누적 작업 자동 트리거**: 에이전트별로 10번 작업마다 성능 리뷰
3. **임계치 이하 자동 트리거**: 에이전트 최근 5작업 평균 성공률 < 0.6
4. **수동 트리거**: `POST /improve` 호출 시

#### JinxLoop 실행 단계

```
1. 대상 에이전트 결정
   - 피드백 기반이면 피드백 받은 에이전트
   - 자동이면 성능 가장 낮은 에이전트

2. 성능 분석 (해당 에이전트 SQLite + Qdrant)
   - 최근 N작업 성공/실패 통계
   - 실패한 작업들의 failure_reason 분석
   - 진수 피드백 코멘트 수집

3. 개선안 생성
   - Claude API 호출: 실패 패턴 + 피드백 → 프롬프트 개선안
   - 개선 대상: 해당 에이전트의 system_prompt, plan 전략, tool 활용 방식

4. 버전 업 및 적용
   - 기존 프롬프트 SQLite에 백업 (rollback 가능)
   - 새 버전 적용 (해당 에이전트만, 나머지 영향 없음)

5. A/B 검증
   - 이후 10작업 중 절반씩 신버전/구버전 적용
   - 성능 비교 후 더 좋은 쪽 확정 채택

6. 개선 리포트 저장
   - 무엇을, 왜, 어떻게 바꿨는지 기록
   - /improve/history에서 조회 가능
```

#### 피드백 반영 흐름

```
진수: "이번 코드 별로야. 에러 핸들링이 없어"
    │
    ▼
POST /feedback { task_id: "xxx", rating: 2, comment: "에러 핸들링 없음", target_agent: "JX_CODER" }
    │
    ▼
JinxLoop: JX_CODER 분석 시작
  - 최근 실패 패턴 + 진수 코멘트 종합
  - "에러 핸들링, try-except, 입력 검증 강화" 개선안 생성
    │
    ▼
JX_CODER 프롬프트 v1.2 → v1.3으로 업데이트
  - 코드 작성 시 항상 에러 핸들링 포함 지시 추가
    │
    ▼
다음 코딩 작업부터 v1.3 적용
```

---

## 5. 데이터 흐름 및 시퀀스

### 단순 명령 흐름 (에이전트 1개)
> "파이썬으로 데이터 전처리 코드 짜줘"

```
진수 → POST /chat {"message": "파이썬으로 데이터 전처리 코드 짜줘"}
    │
    ▼
JinxAPI → JINXUS_CORE.run()
    │
    ▼
[intake_node]
  - Qdrant(manager_memory): 유사 과거 작업 top-5 → "지난번 전처리는 JX_CODER가 처리, 성공"
    │
    ▼
[decompose_node]
  - subtasks = [{ assigned_agent: "JX_CODER", instruction: "pandas로 데이터 전처리 코드 작성 및 실행" }]
  - execution_mode = "sequential" (1개 에이전트)
    │
    ▼
[dispatch_node] → JX_CODER.run(instruction)
    │
    ▼ (JX_CODER 내부)
    [receive] → [plan] → [execute: code_executor] → [evaluate] → [reflect] → [memory_write] → [return_result]
    │
    ▼
JX_CODER → AgentResult { success: True, score: 0.92, output: "코드 + 실행 결과" }
    │
    ▼
[aggregate_node]: 결과 1개라 그대로 통과
    │
    ▼
[reflect_node] + [memory_write_node] + [respond_node]
    │
    ▼
SSE 스트리밍 → 진수

event: agent_started  → {"agent": "JX_CODER"}
event: agent_done     → {"agent": "JX_CODER", "success": true}
event: message        → "코드 완성됐어:\n```python\n..."
event: done           → {"agents_used": ["JX_CODER"], "duration_ms": 4200}
```

---

### 복합 명령 흐름 (에이전트 병렬)
> "데이터 전처리 코드 짜면서 동시에 최신 pandas 최적화 기법도 찾아줘"

```
진수 → POST /chat

[decompose_node]
  - subtasks = [
      { task_id: "sub_001", assigned_agent: "JX_CODER",      instruction: "전처리 코드 작성" },
      { task_id: "sub_002", assigned_agent: "JX_RESEARCHER", instruction: "pandas 최적화 최신 기법 검색" }
    ]
  - depends_on: 없음 → execution_mode = "parallel"
    │
    ▼
[dispatch_node]
  asyncio.gather(
    JX_CODER.run("sub_001"),
    JX_RESEARCHER.run("sub_002")
  )
  ← 두 에이전트 동시 실행
    │
    ▼ (동시 완료)
JX_CODER     → { output: "전처리 코드" }
JX_RESEARCHER → { output: "vectorized ops, chunking, query optimization 등 5가지" }
    │
    ▼
[aggregate_node]
  - 두 결과를 하나의 응답으로 통합
  - "코드 + 최신 기법을 코드에 적용하는 보충 설명"
    │
    ▼
진수에게 통합 응답 전달
```

---

### 순차 의존 흐름
> "데이터 분석 코드 짜서 실행하고, 그 결과 해석해줘"

```
[decompose_node]
  - subtasks = [
      { task_id: "sub_001", assigned_agent: "JX_CODER",   instruction: "분석 코드 작성 및 실행" },
      { task_id: "sub_002", assigned_agent: "JX_ANALYST", instruction: "sub_001 결과 해석",
        depends_on: ["sub_001"] }  ← 의존성 선언
    ]
  - execution_mode = "sequential"

순서: JX_CODER 완료 → 결과를 context로 넘김 → JX_ANALYST 실행
```

---

### 피드백 기반 자가 강화 흐름

```
진수: "이번 코드 별로야. 에러 핸들링이 없어" (rating: 2)
    │
POST /feedback { task_id, rating: 2, comment: "에러 핸들링 없음", target_agent: "JX_CODER" }
    │
    ▼
JinxLoop: JX_CODER 집중 분석
  - SQLite: JX_CODER 최근 10작업 → 에러 핸들링 누락 패턴 3건 발견
  - Qdrant(coder_memory): 유사 실패 케이스 검색
    │
    ▼
Claude API: "다음 패턴을 보고 JX_CODER 프롬프트를 개선해줘: ..."
  → 개선안: "모든 코드에 try-except 필수, 입력값 타입 검증 추가"
    │
    ▼
JX_CODER 프롬프트 v1.2 → v1.3 적용
SQLite: 개선 이력 저장
    │
    ▼
다음 코딩 요청부터 자동 반영. JX_RESEARCHER 등 다른 에이전트는 변경 없음.
```

---

## 6. 프롬프트 설계 명세

**위치**: `prompts/`  
**원칙**: JINXUS_CORE와 각 Sub-Agent는 독립적인 프롬프트를 가진다. JinxLoop이 에이전트별로 개별 개선.

### 6-1. JINXUS_CORE system prompt (`prompts/jinxus_core/system.md`)

```
너는 JINXUS_CORE야. 진수의 총괄 AI 비서.

## 핵심 역할
진수와 소통하는 유일한 창구다. 진수의 명령을 받아서:
1. 정확히 이해한다
2. 어떤 에이전트들이 필요한지 판단한다
3. 작업을 분해해서 각 에이전트에게 명확하게 지시한다
4. 결과를 취합해서 진수에게 깔끔하게 보고한다

## 진수에 대해
- 데이터 사이언스 / AI 엔지니어링 분야
- 직접적이고 핵심만 말하는 스타일 선호
- 자기소개서, 포트폴리오 작업도 함께 함

## 가용 에이전트
- JX_CODER: 코드 작성, 실행, 디버깅
- JX_RESEARCHER: 웹 검색, 정보 분석, 요약
- JX_WRITER: 글쓰기, 문서화, 자소서
- JX_ANALYST: 데이터 분석, 시각화, 통계
- JX_OPS: 파일, GitHub, 스케줄 관리

## 태도
- 확인이 필요한 건 실행 전에 먼저 묻는다 (특히 파괴적 작업)
- 에이전트들이 실패하면 솔직하게 이유를 전달한다
- 진수가 피드백 주면 "알겠어, 반영할게" 한 마디로 끝낸다
```

### 6-2. JINXUS_CORE decompose prompt (`prompts/jinxus_core/decompose.md`)

```
## 진수의 명령
{user_input}

## 참고: 과거 유사 작업
{memory_context}

## 가용 에이전트
JX_CODER, JX_RESEARCHER, JX_WRITER, JX_ANALYST, JX_OPS

## 지시
위 명령을 분석하고 다음 JSON으로만 응답해:

{
  "subtasks": [
    {
      "task_id": "sub_001",
      "assigned_agent": "JX_CODER",
      "instruction": "에이전트에게 전달할 구체적 지시",
      "depends_on": []
    }
  ],
  "execution_mode": "parallel | sequential | mixed",
  "brief_plan": "한 줄 실행 계획"
}

판단 기준:
- 서브태스크들 간 의존성 없으면 parallel
- 앞 결과가 뒤 입력으로 필요하면 depends_on 명시
- 단순 명령이면 subtasks 1개
```

### 6-3. Sub-Agent 공통 system prompt 템플릿 (`prompts/{agent}/system.md`)

각 에이전트는 다음 구조를 기반으로 고유한 프롬프트를 가짐. JinxLoop이 이 파일을 버전 관리.

**JX_CODER** (`prompts/jx_coder/system.md`):
```
너는 JX_CODER야. JINXUS의 코딩 전문가.
JINXUS_CORE로부터 코딩 지시를 받아서 실행한다.

## 전담 영역
Python, SQL, 데이터 처리 코드 작성/실행/디버깅

## 코드 작성 원칙
- 항상 try-except로 에러 핸들링
- 입력값 타입 검증 포함
- 실행 가능한 코드만 제출 (이론 코드 X)
- 실행 후 결과 확인까지가 작업 완료

## 실패 시
에러 메시지 전문 + 시도한 것 + 왜 실패했는지를 JINXUS_CORE에게 반환
```

**JX_RESEARCHER** (`prompts/jx_researcher/system.md`):
```
너는 JX_RESEARCHER야. JINXUS의 정보 수집 전문가.

## 전담 영역
웹 검색, 정보 분석, 논문/뉴스 요약, 트렌드 파악

## 검색 원칙
- 쿼리를 3가지로 변형해서 검색 (넓게 → 좁게)
- 날짜 필터로 최신 정보 우선
- 출처 명시 필수
- "찾지 못했습니다"로 끝내지 마. 최선의 관련 정보라도 전달.
```

**JX_WRITER** (`prompts/jx_writer/system.md`):
```
너는 JX_WRITER야. JINXUS의 글쓰기 전문가.

## 전담 영역
자기소개서, 포트폴리오, 보고서, 이메일, 기술 문서

## 글쓰기 원칙
- 진수의 과거 글쓰기 스타일 참고 (장기기억에서 로드)
- 핵심을 먼저, 근거는 나중에
- 화려한 수식어 최소화
- 초안 작성 → 진수 피드백 → 수정 사이클 권장
```

### 6-4. 프롬프트 파일 구조

```
prompts/
├── manager/
│   ├── system.md           ← 현재 활성 버전
│   ├── decompose.md
│   └── versions/
│       ├── system_v1.0.md
│       └── system_v1.1.md
├── jx_coder/
│   ├── system.md
│   └── versions/
├── jx_researcher/
│   ├── system.md
│   └── versions/
├── jx_writer/
│   ├── system.md
│   └── versions/
├── jx_analyst/
│   ├── system.md
│   └── versions/
└── jx_ops/
    ├── system.md
    └── versions/
```

---

## 7. 기술 스택

| 레이어 | 기술 | 버전 | 선택 이유 |
|---|---|---|---|
| 언어 | Python | 3.11+ | 생태계, 타입 힌팅 강화 |
| 에이전트 프레임워크 | LangGraph | 최신 | 상태기반 그래프, 조건 분기 용이 |
| LLM 클라이언트 | Anthropic SDK | 최신 | Claude 직접 호출 |
| 웹 프레임워크 | FastAPI | 최신 | 비동기, 타입 자동 검증, SSE 지원 |
| 데이터 검증 | Pydantic v2 | 2.x | 성능 개선, FastAPI 통합 |
| 단기기억 | Redis | 7.x | 빠른 TTL 기반 저장 |
| 장기기억 | Qdrant | 최신 | 경량 벡터 DB, 로컬 실행 가능 |
| 메타 저장 | SQLite | 내장 | 통계/설정 로컬 저장, 의존성 없음 |
| 스케줄러 | APScheduler | 3.x | Python 내장형, cron 표현식 지원 |
| 웹 검색 | Tavily API | - | LLM 친화적 검색 결과 포맷 |
| 코드 실행 | Claude Code CLI | 최신 | 코딩 자율 실행의 핵심 |
| 임베딩 | OpenAI text-embedding-3-small | - | 가격 대비 품질 |
| 런타임 서버 | Uvicorn | 최신 | ASGI, 비동기 처리 |

---

## 8. 프로젝트 폴더 구조

```
jinxus/
│
├── main.py                              # 진입점. FastAPI 서버 시작.
├── .env                                 # 환경 변수 (git 제외)
├── .env.example
├── requirements.txt
│
├── config/
│   └── settings.py                      # Pydantic BaseSettings 전체 설정
│
├── agents/                              # ★ 에이전트 레이어 (핵심)
│   ├── base_agent.py                    # 모든 에이전트의 공통 추상 클래스
│   │                                    #   - 공통 LangGraph 그래프 구조
│   │                                    #   - 공통 state 스키마
│   │                                    #   - 공통 memory_write, reflect 로직
│   ├── jinxus_core.py                       # JINXUS_CORE — 총괄 지휘관
│   │                                    #   - decompose, dispatch, aggregate 노드
│   │                                    #   - 진수 인터페이스
│   ├── jx_coder.py                    # JX_CODER — 코드 전문가
│   ├── jx_researcher.py               # JX_RESEARCHER — 리서치 전문가
│   ├── jx_writer.py                   # JX_WRITER — 글쓰기 전문가
│   ├── jx_analyst.py                  # JX_ANALYST — 데이터 분석 전문가
│   └── jx_ops.py                      # JX_OPS — 시스템/운영 전문가
│
├── core/
│   ├── claw_loop.py                     # 자가 강화 엔진
│   │                                    #   - 피드백 수신 → 에이전트 분석 → 프롬프트 개선
│   │                                    #   - A/B 검증
│   │                                    #   - 에이전트별 독립 강화
│   └── orchestrator.py                  # 에이전트 레지스트리 + 실행 라우터
│                                        #   - 에이전트 등록/조회
│                                        #   - parallel/sequential 실행 관리
│
├── memory/
│   ├── claw_memory.py                   # 메모리 통합 인터페이스
│   ├── short_term.py                    # Redis 단기기억
│   ├── long_term.py                     # Qdrant 장기기억 (에이전트별 컬렉션)
│   └── meta_store.py                    # SQLite 통계/프롬프트 버전/개선 이력
│
├── tools/
│   ├── base.py                          # JinxTool 추상 기반 클래스 + ToolResult
│   ├── code_executor.py                 # Claude Code CLI subprocess 실행
│   ├── web_searcher.py                  # Tavily API 웹 검색
│   ├── file_jinxus_core.py                  # 파일시스템 CRUD
│   ├── github_agent.py                  # GitHub REST API 자동화
│   └── scheduler.py                     # APScheduler 반복 작업
│
├── api/
│   ├── server.py                        # FastAPI app 팩토리
│   ├── routers/
│   │   ├── chat.py                      # POST /chat (SSE 스트리밍)
│   │   ├── task.py                      # POST /task, GET /task/{id}
│   │   ├── feedback.py                  # POST /feedback → JinxLoop 트리거
│   │   ├── agents.py                    # GET /agents, GET /agents/{name}/status
│   │   ├── memory.py                    # GET /memory/search, DELETE /memory/{id}
│   │   ├── status.py                    # GET /status, GET /status/performance
│   │   └── improve.py                   # POST /improve, GET /improve/history, POST /improve/rollback
│   └── models/
│       ├── request.py                   # 요청 Pydantic 모델
│       └── response.py                  # 응답 Pydantic 모델
│
├── prompts/
│   ├── manager/
│   │   ├── system.md                    # 현재 활성 버전
│   │   ├── decompose.md
│   │   └── versions/
│   ├── jx_coder/
│   │   ├── system.md
│   │   └── versions/
│   ├── jx_researcher/
│   │   ├── system.md
│   │   └── versions/
│   ├── jx_writer/
│   │   ├── system.md
│   │   └── versions/
│   ├── jx_analyst/
│   │   ├── system.md
│   │   └── versions/
│   └── jx_ops/
│       ├── system.md
│       └── versions/
│
└── data/
    ├── jinxus_meta.db                   # SQLite DB (통계, 프롬프트 버전, 스케줄, 개선 이력)
    └── logs/
        └── jinxus.log
```

---

## 9. 개발 로드맵

### Phase 1 — JINXUS_CORE + JX_CODER 뼈대 (목표: 코드 짜주는 JINXUS)

| 작업 | 완료 기준 |
|---|---|
| `base_agent.py` 공통 구조 구현 | LangGraph 공통 그래프 동작 |
| `jinxus_core.py` 기본 구현 | intake → decompose(1개 에이전트) → dispatch → respond |
| `jx_coder.py` 구현 | 코드 작성 + 실행 결과 반환 |
| `code_executor` 툴 | Claude Code CLI subprocess 동작 |
| FastAPI `/chat` SSE | 진수 → JINXUS_CORE → JX_CODER → 응답 흐름 |
| Redis 단기기억 | 같은 세션 내 대화 기억 |

### Phase 2 — 전체 에이전트 + 병렬 실행 (목표: 멀티에이전트 시스템 완성)

| 작업 | 완료 기준 |
|---|---|
| `jx_researcher.py` + `web_searcher` | 검색 결과 반환 |
| `jx_writer.py` + `file_manager` | 문서 작성 + 파일 저장 |
| `jx_analyst.py` | 데이터 분석 코드 + 인사이트 제공 |
| `jx_ops.py` + `github_agent` + `scheduler` | GitHub 작업, 스케줄 등록 |
| `orchestrator.py` 병렬 실행 | asyncio.gather로 2개 에이전트 동시 실행 |
| JINXUS_CORE decompose 고도화 | depends_on 기반 순차/병렬 자동 판단 |

### Phase 3 — 장기기억 + 경험 축적 (목표: 과거를 기억하는 JINXUS)

| 작업 | 완료 기준 |
|---|---|
| Qdrant 에이전트별 컬렉션 분리 설정 | 6개 컬렉션 생성 및 저장 동작 |
| 각 에이전트 memory_write_node | 작업 결과 장기기억 저장 |
| intake_node 장기기억 활용 | 유사 과거 경험 로드 후 plan에 반영 |
| SQLite 성능 통계 | `/status/performance` 에이전트별 통계 조회 |
| 장기기억 중요도 필터링 | importance_score 계산 및 선택적 저장 |

### Phase 4 — 자가 강화 (목표: 피드백으로 강해지는 JINXUS)

| 작업 | 완료 기준 |
|---|---|
| `POST /feedback` 엔드포인트 | rating + comment 수신 |
| `claw_loop.py` 구현 | 피드백 → 해당 에이전트 분석 → 프롬프트 개선안 생성 |
| 프롬프트 버전 관리 | `prompts/{agent}/versions/` 이력 보관 + rollback |
| A/B 테스트 로직 | 신/구 버전 성능 비교 후 자동 채택 |
| `/improve/history` API | 에이전트별 개선 이력 조회 |
| 자동 트리거 | 성공률 임계치 미달 시 자동 강화 실행 |

### Phase 5 — 고도화 + XGEN 연동 (목표: 진짜 비서)

| 작업 | 완료 기준 |
|---|---|
| 주기적 메모리 pruning | JinxLoop 실행 시 저품질 벡터 자동 정리 |
| 스케줄 작업 | "매일 9시에 뉴스 요약" 동작 |
| 알림 연동 | Slack/텔레그램 webhook으로 완료 보고 |
| 웹 UI | React 채팅 + 에이전트별 상태 대시보드 |
| XGEN 파인튜닝 파이프라인 | 누적 데이터 → XGEN에 파인튜닝 투입 |
| K8s 배포 | docker-compose → K3s 전환 |

---

## 10. 환경 변수 명세

`.env.example` 내용:

```bash
# ===== 서버 =====
JINXUS_HOST=0.0.0.0
JINXUS_PORT=9000
JINXUS_DEBUG=false

# ===== LLM =====
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-opus-4-6
CLAUDE_FALLBACK_MODEL=claude-sonnet-4-6

# ===== 단기기억 (Redis) =====
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# ===== 장기기억 (Qdrant) =====
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=jinxus_memory

# ===== 임베딩 =====
OPENAI_API_KEY=sk-...       # 임베딩용

# ===== 메타 저장 =====
SQLITE_PATH=./data/jinxus_meta.db

# ===== 도구 =====
TAVILY_API_KEY=tvly-...
GITHUB_TOKEN=ghp_...

# ===== 자가 강화 =====
AUTO_IMPROVE_THRESHOLD=0.6
REFLECT_EVERY_N_TASKS=10
MAX_PROMPT_VERSIONS=20

# ===== Claude Code =====
CLAUDE_CODE_STORAGE=/tmp/jinxus_sessions
CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS=true
```

---

## 11. 데이터 스키마

### SQLite 테이블 구조

```sql
-- 에이전트별 작업 통계
CREATE TABLE agent_task_logs (
    id              TEXT PRIMARY KEY,
    main_task_id    TEXT,                   -- JINXUS_CORE 레벨 작업 ID
    agent_name      TEXT NOT NULL,          -- JX_CODER | JX_RESEARCHER | ...
    instruction     TEXT,                   -- 받은 지시
    success         INTEGER NOT NULL,       -- 1|0
    success_score   REAL,
    duration_ms     INTEGER,
    failure_reason  TEXT,
    prompt_version  TEXT,                   -- 이 작업에 사용된 프롬프트 버전
    created_at      TEXT NOT NULL
);

-- 에이전트별 프롬프트 버전 (에이전트마다 독립)
CREATE TABLE agent_prompt_versions (
    id              TEXT PRIMARY KEY,
    agent_name      TEXT NOT NULL,          -- JX_CODER | JINXUS_CORE | ...
    version         TEXT NOT NULL,          -- v1.0, v1.1, ...
    prompt_content  TEXT NOT NULL,
    change_reason   TEXT,
    avg_score       REAL DEFAULT 0.0,
    task_count      INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 0,      -- 에이전트별로 1개만 1
    created_at      TEXT NOT NULL,
    UNIQUE(agent_name, version)
);

-- 진수 피드백 이력
CREATE TABLE user_feedback (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL,          -- 피드백 대상 작업 ID
    target_agent    TEXT,                   -- 어떤 에이전트에 대한 피드백인지
    rating          INTEGER NOT NULL,       -- 1~5
    comment         TEXT,
    triggered_improve INTEGER DEFAULT 0,   -- 이 피드백이 개선을 트리거했는지
    created_at      TEXT NOT NULL
);

-- 자가 강화 이력
CREATE TABLE improve_logs (
    id              TEXT PRIMARY KEY,
    target_agent    TEXT NOT NULL,          -- 개선된 에이전트
    trigger_type    TEXT,                   -- "feedback" | "auto_threshold" | "manual"
    trigger_source  TEXT,                   -- 피드백 ID 또는 "scheduled"
    old_version     TEXT,
    new_version     TEXT,
    failure_patterns TEXT,                  -- 발견된 실패 패턴 JSON
    improvement_applied TEXT,              -- 적용된 개선 내용
    score_before    REAL,
    score_after     REAL,                   -- A/B 검증 후 채워짐
    ab_test_done    INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

-- 스케줄 작업
CREATE TABLE scheduled_tasks (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    task_prompt     TEXT NOT NULL,          -- JINXUS_CORE에게 전달할 프롬프트
    is_active       INTEGER DEFAULT 1,
    last_run_at     TEXT,
    next_run_at     TEXT,
    created_at      TEXT NOT NULL
);
```

### Qdrant 컬렉션 구조 (에이전트별 분리)

```json
컬렉션 목록:
  jinxus_core_memory
  jinxus_coder_memory
  jinxus_researcher_memory
  jinxus_writer_memory
  jinxus_analyst_memory
  jinxus_ops_memory

각 컬렉션 공통 설정:
{
  "vectors": { "size": 1536, "distance": "Cosine" },
  "payload_schema": {
    "task_id": "keyword",
    "agent_name": "keyword",
    "instruction": "text",
    "summary": "text",           ← 임베딩 대상 텍스트
    "outcome": "keyword",        ← "success" | "failure"
    "success_score": "float",
    "key_learnings": "text",
    "importance_score": "float", ← pruning 기준
    "prompt_version": "keyword",
    "created_at": "datetime"
  }
}
```

---

## 12. 배포 가이드

### 로컬 개발 환경 (빠른 시작)

```bash
# 1. 레포 클론 & 환경 설정
git clone https://github.com/jinsoo96/JINXUS.git
cd jinxus
cp .env.example .env
# .env 파일에서 필수값 채우기: ANTHROPIC_API_KEY, OPENAI_API_KEY

# 2. Python 가상환경
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. 인프라 (Redis + Qdrant) Docker로 실행
docker run -d --name jinxus-redis -p 6379:6379 redis:7-alpine
docker run -d --name jinxus-qdrant -p 6333:6333 qdrant/qdrant

# 4. DB 초기화
python -c "from memory.meta_store import init_db; init_db()"

# 5. 실행
python main.py
# → http://localhost:9000/docs 에서 API 확인
```

### docker-compose.yml (통합 실행)

```yaml
version: "3.8"
services:
  jinxus:
    build: .
    ports:
      - "9000:9000"
    env_file:
      - .env
    depends_on:
      - redis
      - qdrant
    volumes:
      - ./data:/app/data
      - ./prompts:/app/prompts

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  qdrant_data:
```

### requirements.txt

```
anthropic>=0.34.0
langgraph>=0.2.0
langchain-anthropic>=0.2.0
langchain-core>=0.3.0
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.9.0
pydantic-settings>=2.5.0
redis>=5.1.0
qdrant-client>=1.11.0
openai>=1.50.0          # 임베딩용
tavily-python>=0.5.0
PyGithub>=2.4.0
APScheduler>=3.10.0
aiosqlite>=0.20.0
httpx>=0.27.0
python-dotenv>=1.0.0
```

---

## 부록 A: 장기기억 리소스 전략 — "영구 저장은 리소스 폭탄이다"

### 문제 정의

작업마다 무조건 벡터를 Qdrant에 밀어넣으면 다음 문제가 발생한다:

| 문제 | 구체적 증상 |
|---|---|
| **메모리 팽창** | 벡터 1개 = 약 6KB. 하루 50작업 × 365일 = 약 110MB/년. 운영 3년이면 수백 MB 벡터 인덱스 |
| **검색 노이즈** | 저품질 작업(실패, 단순 chat)이 쌓이면 유사도 검색 top-5에 쓸모없는 것들이 들어옴 |
| **임베딩 비용** | OpenAI text-embedding 호출 = 돈. 모든 작업 임베딩하면 불필요한 비용 발생 |
| **검색 속도 저하** | 벡터 수 증가 → HNSW 인덱스 탐색 시간 증가 (수십만 개 이상부터 체감) |

### 해결 전략: 중요도 기반 선택적 저장

**저장 여부 결정 기준 (`memory_write_node`에서 판단)**

```python
def should_save_to_longterm(state: JinxState) -> bool:
    # 1. 단순 chat은 장기기억 불필요 → 단기(Redis)만 저장
    if state["task_type"] == "chat" and state["success_score"] > 0.8:
        return False
    
    # 2. 너무 짧은 작업도 불필요 (5초 미만 = 배울 게 없음)
    if state["duration_ms"] < 5000:
        return False
    
    # 3. reflection이 비어있으면 불필요
    if not state["reflection"] or len(state["reflection"]) < 20:
        return False
    
    # 나머지는 저장 (code, research, file, 실패한 모든 작업)
    return True
```

**중요도 점수 (importance_score) 계산**

저장할 때 `importance_score` 페이로드를 함께 저장. 나중에 pruning 기준으로 사용.

```python
def calc_importance(state: JinxState) -> float:
    score = 0.0
    
    # 실패한 작업은 중요 (실패에서 배움)
    if not state["success"]:
        score += 0.4
    
    # 복잡한 작업일수록 중요
    if len(state["plan"]) >= 3:
        score += 0.2
    
    # reflection이 구체적일수록 중요
    if len(state["reflection"]) > 100:
        score += 0.2
    
    # code/research 타입이 chat보다 중요
    if state["task_type"] in ["code", "research"]:
        score += 0.2
    
    return min(score, 1.0)
```

### 주기적 Pruning 전략

**`JinxLoop` 실행 시 함께 수행하는 메모리 정리:**

```
Pruning 규칙 (10번 강화 주기마다 1회 실행)

1. importance_score < 0.3 이고 생성된 지 30일 초과 → 삭제
2. 동일 task_type의 success=True 작업이 50개 초과 시
   → 가장 오래되고 importance_score 낮은 것부터 30개만 남기고 삭제
3. 전체 벡터 수가 10,000개 초과 시
   → importance_score 하위 20% 일괄 삭제
```

**결과적으로 유지되는 기억의 성격:**
- 실패 경험 (희귀하고 가치 있음)
- 복잡한 성공 경험 (재활용 가능성 높음)
- 최근 경험 (관련성 높음)
- 구체적인 교훈이 담긴 경험

### 예상 리소스 사용량 (전략 적용 후)

| 구분 | 전략 없음 | 전략 적용 후 |
|---|---|---|
| 일일 벡터 저장 수 | 50개 | ~10개 (20% 선택 저장) |
| 연간 누적 벡터 수 | 18,250개 | ~3,650개 |
| Qdrant 메모리 사용 | ~110MB/년 | ~22MB/년 |
| 임베딩 API 비용 | 높음 | 80% 절감 |
| 검색 품질 | 노이즈 많음 | 고품질 경험만 검색 |

---

## 부록 B: 개발 시 유의사항

### ⚠️ 절대 건드리면 안 되는 것
- `prompts/system_prompt.md`는 JINXUS의 정체성. 함부로 바꾸지 말 것.
- `memory/long_term.py`의 Qdrant 컬렉션 삭제 시 모든 학습 데이터 소멸.
- `CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS=true`는 로컬 환경에서만. 프로덕션은 별도 권한 체계 필요.

### 🔧 자주 필요한 작업
- 특정 기억 삭제: `DELETE /memory/{task_id}`
- 프롬프트 강제 롤백: `POST /improve/rollback/v1.0`
- 성능 리포트 확인: `GET /status/performance?days=7`
- 수동 강화 트리거: `POST /improve`

### 📈 성공 지표
- 첫 2주: task 성공률 70% 이상 달성
- 1개월: JinxLoop이 최소 3번 자동 강화 실행
- 3개월: 같은 유형 작업의 성공률이 초기 대비 20%p 이상 향상

---

## 참조 문서 및 링크

### 설계 시 직접 읽고 참고한 소스

| 소스 | 링크 | 참고한 내용 |
|---|---|---|
| **claude_company** | [github.com/CocoRoF/claude_company](https://github.com/CocoRoF/claude_company) | Claude Code CLI를 subprocess로 감싸는 방식, MCP 자동 로딩 패턴, `CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS` 환경변수 활용법 → `code_executor` 툴 설계에 반영 |
| **Geny** | [github.com/CocoRoF/Geny](https://github.com/CocoRoF/Geny) | FastAPI + LangGraph 백엔드 구조, 단기/장기 메모리 분리 레이어 개념, context_guard / model_fallback 노드 아이디어, 역할 기반 프롬프트 분리 방식 → JinxBrain 그래프 구조와 JinxMemory 3계층 설계에 반영 |
| **XGEN / SON BLOG** | [infoedu.co.kr](https://infoedu.co.kr) | K3s + Jenkins + ArgoCD CI/CD 파이프라인 구성, Istio 서비스 메시 + Observability 스택, GPU 모델 서빙 아키텍처, Qdrant 기반 임베딩 최적화 → Phase 5 배포 인프라 및 향후 파인튜닝 파이프라인 설계 방향에 반영 |
| **XGEN_Working_dir** | [github.com/jinsoo96/XGEN_Working_dir](https://github.com/jinsoo96/XGEN_Working_dir) | Private 레포라 직접 접근 불가. infoedu.co.kr 블로그 기반으로 XGEN 플랫폼 구조 간접 파악. |

### 기술 공식 문서

| 기술 | 공식 문서 |
|---|---|
| LangGraph | [langchain-ai.github.io/langgraph](https://langchain-ai.github.io/langgraph/) |
| Anthropic Claude API | [docs.anthropic.com](https://docs.anthropic.com) |
| Claude Code CLI | [docs.anthropic.com/claude-code](https://docs.anthropic.com/en/docs/claude-code) |
| Qdrant | [qdrant.tech/documentation](https://qdrant.tech/documentation/) |
| FastAPI | [fastapi.tiangolo.com](https://fastapi.tiangolo.com) |
| APScheduler | [apscheduler.readthedocs.io](https://apscheduler.readthedocs.io) |
| Tavily API | [docs.tavily.com](https://docs.tavily.com) |

### 추가로 읽어볼 만한 레퍼런스

| 주제 | 링크 | 이유 |
|---|---|---|
| LangGraph 메모리 패턴 | [langchain-ai.github.io/langgraph/concepts/memory](https://langchain-ai.github.io/langgraph/concepts/memory/) | JinxMemory 구현 시 공식 패턴 참고 |
| Qdrant 필터링 + 페이로드 | [qdrant.tech/documentation/concepts/filtering](https://qdrant.tech/documentation/concepts/filtering/) | importance_score 기반 pruning 쿼리 작성 시 |
| Claude Code SDK | [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code) | code_executor 툴에서 CLI 대신 SDK 쓸 경우 |
| MCP 프로토콜 명세 | [modelcontextprotocol.io](https://modelcontextprotocol.io) | JinxTools를 MCP 서버로 확장할 때 |

---

*마지막 업데이트: 2026년 2월*  
*설계자: 진수 (jinsoo96)*  
*이 문서 하나로 JINXUS를 처음부터 다시 만들 수 있어야 한다.*
