<div align="center">

# 🏆 JINXUS

### Multi-Agent AI Assistant System

**"주인님"을 모시는 충실한 AI 비서**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude-Opus-orange.svg)](https://anthropic.com)

</div>

---

## 📋 목차

- [개요](#-개요)
- [시스템 아키텍처](#-시스템-아키텍처)
- [핵심 기능](#-핵심-기능)
- [에이전트 상세](#-에이전트-상세)
- [기술 연동](#-기술-연동)
- [메모리 시스템](#-메모리-시스템)
- [자가 강화 시스템](#-자가-강화-시스템-jinxloop)
- [설치 및 실행](#-설치-및-실행)
- [API 문서](#-api-문서)
- [프로젝트 구조](#-프로젝트-구조)

---

## 🎯 개요

JINXUS는 **LangGraph 패턴**을 적용한 멀티 에이전트 AI 비서 시스템입니다.

자연어 명령 하나로 코드 작성, 웹 검색, 문서 작성, 데이터 분석, 시스템 운영까지 - 전문 에이전트들이 협력하여 작업을 수행합니다.

### 왜 JINXUS인가?

| 기존 AI 챗봇 | JINXUS |
|-------------|--------|
| 단일 모델 응답 | 5개 전문 에이전트 협업 |
| 일회성 대화 | 3계층 메모리로 학습 |
| 고정된 프롬프트 | 자가 강화로 지속 개선 |
| 텍스트만 출력 | 코드 실행, 웹 검색 실제 수행 |

---

## 🏗 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                        │
│                      http://localhost:1818                       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (:9000)                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐    │
│  │   /chat   │  │  /agents  │  │  /memory  │  │ /feedback │    │
│  └─────┬─────┘  └───────────┘  └───────────┘  └─────┬─────┘    │
└────────┼────────────────────────────────────────────┼──────────┘
         │                                            │
         ▼                                            ▼
┌─────────────────────┐                    ┌─────────────────────┐
│    JINXUS_CORE      │                    │     JinxLoop        │
│   (총괄 지휘관)      │                    │   (자가 강화)        │
│                     │                    │                     │
│ • 명령 분해         │                    │ • 피드백 분석        │
│ • 에이전트 선택     │                    │ • 프롬프트 개선      │
│ • 병렬/순차 실행    │                    │ • 버전 관리          │
└─────────┬───────────┘                    └─────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      전문 에이전트 (5개)                          │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐│
│  │JX_CODER  │ │JX_RESEARCH│ │JX_WRITER │ │JX_ANALYST│ │JX_OPS  ││
│  │코드 전문가│ │리서치 전문│ │글쓰기 전문│ │분석 전문가│ │운영 전문││
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘│
└───────┼────────────┼────────────┼────────────┼───────────┼─────┘
        │            │            │            │           │
        ▼            ▼            ▼            ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                        외부 서비스 연동                           │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Claude   │ │ Tavily   │ │ Python   │ │ GitHub   │           │
│  │   API    │ │   API    │ │ Runtime  │ │   API    │           │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└─────────────────────────────────────────────────────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      3계층 메모리 시스템                          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Redis     │  │   Qdrant     │  │   SQLite     │          │
│  │  (단기기억)   │  │  (장기기억)   │  │  (메타저장)   │          │
│  │  세션 컨텍스트 │  │  벡터 검색    │  │  통계/버전    │          │
│  │    :6379     │  │    :6333     │  │   로컬 파일   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ 핵심 기능

### 1. 자연어 명령 처리
```
"파이썬으로 피보나치 수열 출력해줘" → JX_CODER가 코드 생성 및 실행
"최신 AI 트렌드 찾아줘" → JX_RESEARCHER가 웹 검색 및 분석
"자기소개서 써줘" → JX_WRITER가 문서 작성
```

### 2. LangGraph 패턴
모든 에이전트가 동일한 그래프 구조를 따릅니다:

```
[receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write]
                          ↑            │
                          └───[retry]──┘ (최대 3회, 지수 백오프)
```

- **retry**: 실패 시 최대 3회 재시도 (1초 → 2초 → 4초 백오프)
- **reflect**: 작업 완료 후 반성 및 학습 포인트 도출
- **memory_write**: 중요한 경험을 장기기억에 저장

### 3. 실시간 코드 실행
JX_CODER는 생성한 Python 코드를 **실제로 실행**하고 결과를 반환합니다.
- 30초 타임아웃
- 에러 발생 시 자동 수정 후 재시도
- 실행 결과 즉시 확인

### 4. 웹 검색 통합
JX_RESEARCHER는 **Tavily API**를 통해 실시간 웹 검색을 수행합니다.
- 최신 정보 검색
- 검색 결과 AI 분석
- 출처 링크 제공

---

## 🤖 에이전트 상세

### JX_CODER (코드 전문가)
| 항목 | 내용 |
|------|------|
| 역할 | Python 코드 생성, 실행, 디버깅 |
| 연동 | Claude API, Python Runtime |
| 특수 기능 | 코드 추출, 자동 실행, 에러 자동 수정 |

**사용 예시:**
```
• "퀵소트 알고리즘 구현해줘"
• "이 CSV 파일 읽어서 그래프 그려줘"
• "API 호출하는 코드 만들어줘"
```

### JX_RESEARCHER (리서치 전문가)
| 항목 | 내용 |
|------|------|
| 역할 | 웹 검색, 정보 수집, 분석 요약 |
| 연동 | Tavily API, Claude API |
| 특수 기능 | 실시간 검색, 출처 관리, 다중 소스 종합 |

**사용 예시:**
```
• "2024년 AI 트렌드 조사해줘"
• "React vs Vue 비교해줘"
• "이 기술의 장단점 찾아줘"
```

### JX_WRITER (글쓰기 전문가)
| 항목 | 내용 |
|------|------|
| 역할 | 문서 작성, 자소서, 보고서, 이메일 |
| 연동 | Claude API |
| 특수 기능 | 문서 유형 자동 판단, 품질 검사 |

**사용 예시:**
```
• "데이터 사이언티스트 자소서 써줘"
• "프로젝트 보고서 작성해줘"
• "거절 이메일 정중하게 써줘"
```

### JX_ANALYST (분석 전문가)
| 항목 | 내용 |
|------|------|
| 역할 | 데이터 분석, 시각화, 통계, ML |
| 연동 | Claude API, Python (pandas, numpy, matplotlib) |
| 특수 기능 | 분석 유형 판단, 결과 해석, 인사이트 도출 |

**사용 예시:**
```
• "이 데이터 상관관계 분석해줘"
• "매출 트렌드 시각화해줘"
• "이상치 탐지해줘"
```

### JX_OPS (운영 전문가)
| 항목 | 내용 |
|------|------|
| 역할 | 파일 관리, Git, 스케줄링, 서버 운영 |
| 연동 | Claude API, (GitHub API 예정) |
| 특수 기능 | 파괴적 작업 감지, 안전 경고, 단계별 가이드 |

**사용 예시:**
```
• "이 폴더 GitHub에 올리는 방법 알려줘"
• "cron으로 매일 백업 설정하는 법"
• "Docker 컨테이너 관리 방법"
```

---

## 🔗 기술 연동

### API 연동

| 서비스 | 용도 | 연동 방식 |
|--------|------|-----------|
| **Anthropic Claude** | LLM 추론 | REST API |
| **Tavily** | 웹 검색 | REST API |
| **OpenAI** | 임베딩 (장기기억) | REST API |
| **GitHub** | 코드 저장소 연동 | REST API (예정) |

### 인프라 연동

| 서비스 | 용도 | 포트 |
|--------|------|------|
| **Redis** | 단기기억 (세션, 캐시) | 6379 |
| **Qdrant** | 장기기억 (벡터 검색) | 6333 |
| **SQLite** | 메타 저장 (통계, 버전) | 로컬 파일 |

### MCP (Model Context Protocol) 연동 준비

JINXUS는 MCP 확장을 위한 구조를 갖추고 있습니다:

```python
# tools/ 디렉토리의 도구들이 MCP 서버로 확장 가능
tools/
├── code_executor.py    # 코드 실행 도구
├── web_searcher.py     # 웹 검색 도구
├── file_manager.py     # 파일 관리 도구
├── github_agent.py     # GitHub 연동 도구
└── scheduler.py        # 스케줄러 도구
```

향후 MCP 서버로 각 도구를 노출하여 다른 AI 시스템과 연동할 수 있습니다.

---

## 🧠 메모리 시스템

JINXUS는 3계층 메모리 구조로 경험을 학습합니다.

### 단기기억 (Redis)
- **용도**: 현재 세션의 대화 컨텍스트
- **저장**: 최근 메시지, 임시 결과
- **만료**: 세션 종료 시 또는 TTL

### 장기기억 (Qdrant)
- **용도**: 에이전트별 학습 경험
- **저장**: 성공/실패 사례, 반성 내용
- **검색**: 벡터 유사도 기반

```python
# 유사 경험 검색 예시
memory.search_long_term(
    agent_name="JX_CODER",
    query="피보나치 수열",
    limit=3
)
```

### 메타저장 (SQLite)
- **용도**: 통계, 프롬프트 버전, 개선 로그
- **저장**: 성능 지표, A/B 테스트 결과

---

## 🔄 자가 강화 시스템 (JinxLoop)

JINXUS는 사용자 피드백을 기반으로 스스로 개선됩니다.

### 작동 원리

```
[피드백 수신] → [성능 분석] → [개선안 생성] → [프롬프트 업데이트] → [버전 관리]
```

### 피드백 제출
```bash
curl -X POST http://localhost:9000/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "abc-123",
    "score": 4,
    "comment": "코드는 좋은데 설명이 부족해요"
  }'
```

### 개선 프로세스
1. 낮은 점수(1-2점) 피드백 누적 시 자동 트리거
2. 실패 패턴 분석
3. Claude가 프롬프트 개선안 생성
4. 새 버전으로 저장 (롤백 가능)

---

## 🚀 설치 및 실행

### 요구사항

- Python 3.11+
- Node.js 18+
- Docker

### 1. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일 수정:
```env
# 필수
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
TAVILY_API_KEY=tvly-...

# 선택
GITHUB_TOKEN=ghp_...
```

### 2. 인프라 실행

```bash
# Redis
docker run -d --name jinxus-redis -p 6379:6379 redis:7-alpine

# Qdrant
docker run -d --name jinxus-qdrant -p 6333:6333 qdrant/qdrant
```

### 3. 백엔드 실행

```bash
pip install -r requirements.txt
python main.py
```

### 4. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

### 5. 접속

| 서비스 | URL |
|--------|-----|
| 🖥 프론트엔드 | http://localhost:1818 |
| 🔌 API 서버 | http://localhost:9000 |
| 📚 API 문서 | http://localhost:9000/docs |

---

## 📡 API 문서

### 채팅

```bash
# 동기 채팅
POST /chat/sync
{
  "message": "파이썬으로 hello world 출력해줘"
}

# SSE 스트리밍
GET /chat?message=안녕
```

### 에이전트 조회

```bash
GET /agents
# → 등록된 에이전트 목록 및 상태
```

### 메모리 검색

```bash
POST /memory/search
{
  "agent_name": "JX_CODER",
  "query": "피보나치"
}
```

### 피드백 제출

```bash
POST /feedback
{
  "task_id": "uuid",
  "score": 5,
  "comment": "완벽해요!"
}
```

### 시스템 상태

```bash
GET /status
# → Redis, Qdrant 연결 상태, 업타임, 처리 작업 수
```

---

## 📁 프로젝트 구조

```
JINXUS/
├── agents/                 # 에이전트 모듈
│   ├── jinxus_core.py     # 총괄 지휘관
│   ├── jx_coder.py        # 코드 전문가
│   ├── jx_researcher.py   # 리서치 전문가
│   ├── jx_writer.py       # 글쓰기 전문가
│   ├── jx_analyst.py      # 분석 전문가
│   └── jx_ops.py          # 운영 전문가
│
├── api/                    # FastAPI 라우터
│   └── routers/
│       ├── chat.py        # 채팅 API
│       ├── agents.py      # 에이전트 API
│       ├── memory.py      # 메모리 API
│       └── feedback.py    # 피드백 API
│
├── memory/                 # 3계층 메모리
│   ├── short_term.py      # Redis 연동
│   ├── long_term.py       # Qdrant 연동
│   └── meta_store.py      # SQLite 연동
│
├── core/                   # 핵심 로직
│   ├── orchestrator.py    # 오케스트레이터
│   └── jinx_loop.py       # 자가 강화
│
├── tools/                  # 도구 모듈
│   ├── code_executor.py   # 코드 실행
│   ├── web_searcher.py    # 웹 검색
│   └── file_manager.py    # 파일 관리
│
├── frontend/               # Next.js 프론트엔드
│   └── src/
│       ├── app/           # App Router
│       ├── components/    # UI 컴포넌트
│       └── store/         # Zustand 상태
│
├── prompts/                # 프롬프트 템플릿
├── main.py                 # 서버 엔트리포인트
└── requirements.txt        # Python 의존성
```

---

## 📄 라이선스

MIT License

---

<div align="center">

**Made with ❤️ by jinsoo96**

</div>
