<div align="center">

<img src="JINXUS_IMG.png" alt="JINXUS Mascot" width="200"/>

# JINXUS

### Multi-Agent AI Assistant System

**"주인님"을 모시는 충실한 AI 비서**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet-orange.svg)](https://anthropic.com)
[![Version](https://img.shields.io/badge/Version-1.1.0-purple.svg)]()

**웹 UI** | **텔레그램** | **CLI** - 어디서든 JINXUS와 대화하세요

</div>

---

## 📋 목차

- [개요](#-개요)
- [빠른 시작](#-빠른-시작)
- [멀티채널](#-멀티채널)
- [시스템 아키텍처](#-시스템-아키텍처)
- [핵심 기능](#-핵심-기능)
- [에이전트 상세](#-에이전트-상세)
- [메모리 시스템](#-메모리-시스템)
- [자가 강화 시스템](#-자가-강화-시스템-jinxloop)
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
| 고정된 프롬프트 | 자가 강화로 지속 개선 (A/B 테스트) |
| 텍스트만 출력 | 코드 실행, 웹 검색, GitHub 실제 수행 |
| 웹에서만 사용 | 웹 + 텔레그램 + CLI 멀티채널 |

---

## 🚀 빠른 시작

### 요구사항

- Python 3.11+
- Node.js 18+
- Docker

### 1. 클론 & 환경 설정

```bash
git clone https://github.com/jinsoo96/JINXUS.git
cd JINXUS

# 환경 변수 설정
cp .env.example .env
```

`.env` 파일 수정:
```env
# 필수
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # 임베딩용
TAVILY_API_KEY=tvly-...        # 웹 검색용

# 선택 (텔레그램 사용 시)
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_AUTHORIZED_USER_ID=your-user-id

# 선택 (GitHub 연동 시)
GITHUB_TOKEN=ghp_...
```

### 2. 인프라 실행 (Docker)

```bash
# Redis (단기기억)
docker run -d --name jinxus-redis -p 6379:6379 redis:7-alpine

# Qdrant (장기기억)
docker run -d --name jinxus-qdrant -p 6333:6333 qdrant/qdrant
```

### 3. 백엔드 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# CLI 명령어 등록 (선택)
pip install -e .

# 서버 실행
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
| 웹 UI | http://localhost:1818 |
| API 서버 | http://localhost:9000 |
| API 문서 | http://localhost:9000/docs |

---

## 📱 멀티채널

JINXUS는 3가지 방법으로 사용할 수 있습니다.

### 웹 UI (localhost:1818)

브라우저에서 채팅 인터페이스로 사용

### 텔레그램 봇 (@JINXUS_bot)

```
서버 실행 → 텔레그램에서 @JINXUS_bot 검색 → 대화 시작

명령어:
/start   - 시작
/status  - 시스템 상태
/agents  - 에이전트 목록
/memory  - 장기기억 검색
```

**원격 사용**: 집에서 서버 켜두면 → 밖에서 텔레그램으로 JINXUS 제어 가능!

### CLI (터미널)

```bash
# 기본 사용
jinxus "파이썬으로 피보나치 출력해줘"

# 스트리밍 출력
jinxus --stream "FastAPI 서버 설계해줘"

# 파일 첨부
jinxus --file ./code.py "이 코드 리뷰해줘"

# 파이프 입력
cat error.log | jinxus "이 에러 분석해줘"

# 대화형 모드
jinxus --interactive
```

---

## 🏗 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                         입력 채널                                │
│   📱 텔레그램    💻 CLI (jinxus)    🖥 웹 UI (Next.js)           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (:9000)                        │
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │ JINXUS_CORE │───▶│ 전문 에이전트 │───▶│  JinxLoop   │         │
│  │  (총괄 지휘) │    │   (5개)     │    │ (자가 강화)  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                  │                  │                 │
│         ▼                  ▼                  ▼                 │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              플러그인 시스템 (tools/)                 │       │
│  │  code_executor | web_searcher | github | scheduler  │       │
│  └─────────────────────────────────────────────────────┘       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    3계층 메모리 시스템                            │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │    Redis     │  │   Qdrant     │  │   SQLite     │          │
│  │  (단기기억)   │  │  (장기기억)   │  │  (메타저장)   │          │
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
"이 코드 GitHub에 올려줘" → JX_OPS가 실제로 커밋/푸시
```

### 2. LangGraph 패턴
모든 에이전트가 동일한 그래프 구조를 따릅니다:

```
[receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write]
                          ↑            │
                          └───[retry]──┘ (최대 3회, 지수 백오프)
```

### 3. 실시간 코드 실행 (하이브리드)

| 작업 유형 | 실행 방식 |
|----------|----------|
| 간단한 스크립트 | Python 직접 실행 (빠름) |
| 복잡한 프로젝트 | Claude Code CLI (패키지 설치, 멀티파일) |

### 4. 실제 도구 실행
JX_OPS는 안내만 하는 게 아니라 **실제로 실행**합니다:
- **GitHub**: PyGithub로 커밋, PR 생성
- **스케줄러**: APScheduler로 작업 예약
- **파일 관리**: 생성, 복사, 이동, 삭제

---

## 🤖 에이전트 상세

| 에이전트 | 역할 | 연동 기술 |
|----------|------|-----------|
| **JX_CODER** | 코드 생성/실행/디버깅 | Claude API, Python, Claude Code CLI |
| **JX_RESEARCHER** | 웹 검색, 정보 분석 | Tavily API |
| **JX_WRITER** | 문서/자소서/보고서 작성 | Claude API |
| **JX_ANALYST** | 데이터 분석, 시각화 | pandas, matplotlib |
| **JX_OPS** | GitHub, 스케줄, 파일 관리 | PyGithub, APScheduler |

---

## 🧠 메모리 시스템

| 계층 | 기술 | 용도 |
|------|------|------|
| **단기기억** | Redis | 세션 대화, 임시 결과 |
| **장기기억** | Qdrant | 에이전트별 학습 경험 (벡터 검색) |
| **메타저장** | SQLite | 통계, 프롬프트 버전, A/B 테스트 |

---

## 🔄 자가 강화 시스템 (JinxLoop)

### 피드백 → 자동 개선

```
[피드백 수신] → [성능 분석] → [개선안 생성] → [A/B 테스트] → [적용/롤백]
```

### A/B 테스트
- 새 프롬프트 적용 전 기존 버전과 비교
- 10% 이상 개선되어야 적용
- 성능 저하 시 자동 롤백

---

## 📡 API 문서

### 채팅
```bash
# 동기 채팅
curl -X POST http://localhost:9000/chat/sync \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕?"}'

# SSE 스트리밍
curl http://localhost:9000/chat?message=안녕
```

### 시스템 상태
```bash
curl http://localhost:9000/status
```

### 전체 API 문서
http://localhost:9000/docs (Swagger UI)

---

## 📁 프로젝트 구조

```
JINXUS/
├── agents/                 # 에이전트 모듈
│   ├── jinxus_core.py     # 총괄 지휘관 (SSE 스트리밍)
│   ├── jx_coder.py        # 코드 전문가 (Claude Code CLI)
│   ├── jx_researcher.py   # 리서치 전문가
│   ├── jx_writer.py       # 글쓰기 전문가
│   ├── jx_analyst.py      # 분석 전문가
│   └── jx_ops.py          # 운영 전문가 (실제 실행)
│
├── channels/               # 멀티채널
│   ├── telegram_bot.py    # 텔레그램 봇
│   └── cli.py             # CLI 인터페이스
│
├── core/                   # 핵심 로직
│   ├── orchestrator.py    # 오케스트레이터
│   ├── jinx_loop.py       # 자가 강화 (A/B 테스트)
│   ├── context_guard.py   # 토큰 관리
│   ├── model_router.py    # 모델 자동 선택
│   └── plugin_loader.py   # 플러그인 로더
│
├── memory/                 # 3계층 메모리
│   ├── short_term.py      # Redis
│   ├── long_term.py       # Qdrant
│   └── meta_store.py      # SQLite
│
├── tools/                  # 플러그인 도구
│   ├── code_executor.py   # 코드 실행
│   ├── web_searcher.py    # 웹 검색
│   ├── github_agent.py    # GitHub 연동
│   ├── scheduler.py       # 스케줄러
│   └── file_manager.py    # 파일 관리
│
├── frontend/               # Next.js 프론트엔드
├── main.py                 # 서버 엔트리포인트
├── pyproject.toml          # CLI 설정
└── requirements.txt        # Python 의존성
```

---

## 📄 라이선스

MIT License

---

<div align="center">

**Made with ❤️ by jinsoo96**

*"명령만 해. 나머지는 내가 다 한다."*

</div>
