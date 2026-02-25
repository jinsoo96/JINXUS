# JINXUS 개발 현황

> 마지막 업데이트: 2026-02-26 (4차)

---

## 전체 진행률

| Phase | 상태 | 설명 |
|-------|------|------|
| **Phase 1** | ✅ 완료 | JINXUS_CORE + JX_CODER 기본 구현 |
| **Phase 2** | ✅ 완료 | 전체 에이전트 + 병렬 실행 |
| **Phase 3** | ✅ 완료 | 장기기억 구조 완성 + LangGraph 패턴 적용 |
| **Phase 4** | ✅ 완료 | JinxLoop A/B 테스트 + 롤백 기능 |
| **Phase 5** | ✅ 완료 | 멀티채널 (웹/텔레그램/CLI) + 플러그인 시스템 |

---

## 기술 스택

### 백엔드
- **Framework**: FastAPI (Python 3.11+)
- **LLM**: Anthropic Claude API
- **웹 검색**: Tavily API
- **벡터 DB**: Qdrant (장기기억)
- **캐시**: Redis (단기기억)
- **메타 저장**: SQLite
- **스케줄러**: APScheduler
- **GitHub 연동**: PyGithub

### 프론트엔드
- **Framework**: Next.js 14 (App Router)
- **UI**: React 18 + Tailwind CSS
- **상태 관리**: Zustand
- **아이콘**: Lucide React
- **언어**: TypeScript

### 인프라
- **컨테이너**: Docker (Redis, Qdrant)
- **포트**:
  - 프론트엔드: 1818
  - 백엔드 API: 9000
  - Redis: 6379
  - Qdrant: 6333

---

## 구현 완료 항목

### 백엔드 서버 (FastAPI)
- [x] `/chat` - SSE 스트리밍 채팅 (진짜 실시간 토큰 전송)
- [x] `/chat/sync` - 동기 채팅
- [x] `/task` - 비동기 작업 관리
- [x] `/feedback` - 피드백 처리 → JinxLoop 트리거
- [x] `/agents` - 에이전트 상태 조회
- [x] `/memory` - 메모리 검색/관리
- [x] `/status` - 시스템 상태
- [x] `/improve` - 수동 자가 강화

### JINXUS_CORE (총괄 지휘관)
- [x] 명령 분해 (decompose) + 강화된 JSON 파싱
- [x] 에이전트 자동 선택
- [x] 병렬/순차 실행 판단
- [x] 결과 취합 및 보고 + context_guard (토큰 제한)
- [x] ModelRouter (opus/sonnet 자동 선택)
- [x] **인격: "주인님" 호칭, 순종적 태도**

### 에이전트 (5개) - LangGraph 패턴 적용 완료

**그래프 구조:**
```
[receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                          ↑             │
                          └──[retry]────┘  (최대 3회, 지수 백오프)
```

| 에이전트 | 상태 | 기능 | 특수 기능 |
|----------|------|------|-----------|
| JX_CODER | ✅ 작동 | Claude Code CLI + python3 하이브리드 | 복잡한 작업은 CLI, 간단한 건 직접 실행 |
| JX_RESEARCHER | ✅ 작동 | Tavily 웹 검색 + Claude 분석 | 출처 관리, 검색 전략 |
| JX_WRITER | ✅ 작동 | 문서/자소서/보고서 작성 | 문서 유형 판단, 품질 검사 |
| JX_ANALYST | ✅ 작동 | 데이터 분석 코드 + 인사이트 | 분석 유형 판단, 결과 해석 |
| JX_OPS | ✅ 작동 | **실제 실행** (GitHub, 스케줄, 파일) | PyGithub, APScheduler, 파일 조작 |

### 메모리 시스템 (3계층)
| 계층 | 기술 | 상태 | 용도 |
|------|------|------|------|
| 단기기억 | Redis | ✅ 연결됨 | 세션 컨텍스트, 캐시 |
| 장기기억 | Qdrant | ✅ 연결됨 | 에이전트별 학습 기록 (벡터 검색) |
| 메타저장 | SQLite | ✅ 생성됨 | 통계, 프롬프트 버전, A/B 테스트 로그 |

### 자가 강화 (JinxLoop)
- [x] 피드백 수신 및 저장
- [x] 에이전트별 성능 분석
- [x] 프롬프트 개선안 생성
- [x] 버전 관리 및 롤백
- [x] **A/B 테스트** (새 프롬프트 적용 전 검증)

### 멀티채널
- [x] **텔레그램 봇** (`channels/telegram_bot.py`)
  - 명령어: /start, /status, /agents, /memory
  - 메시지 길이 자동 분할 (4000자)
  - 인가된 사용자만 허용
- [x] **CLI** (`channels/cli.py`)
  - `jinxus "명령"` 실행
  - `--stream` 스트리밍 출력
  - `--file` 파일 첨부
  - `--interactive` 대화형 모드
  - 파이프 입력 지원

### 플러그인 시스템
- [x] **자동 로더** (`core/plugin_loader.py`)
  - tools/ 폴더 스캔 후 자동 등록
  - 런타임 reload 지원
  - 에이전트별 도구 필터링

### 프론트엔드 (Next.js)
- [x] 채팅 UI (동기 API 연동)
- [x] 에이전트 상태 대시보드
- [x] 메모리 검색 UI
- [x] 설정 페이지 (시스템 상태, 인프라 연결)
- [x] 반응형 사이드바 네비게이션
- [x] Zustand 상태 관리
- [ ] SSE 스트리밍 실시간 연동 (백엔드 준비됨)
- [ ] 개선 이력 시각화
- [ ] 디자인 커스터마이징 (색상 테마 등)

---

## 미구현 항목

### 고급 기능
- [ ] Daemon 모드 (백그라운드 24시간 실행)
- [ ] 플러그인 ON/OFF API 엔드포인트

### 배포
- [ ] Docker Compose 통합
- [ ] K8s 배포 설정

---

## 환경 설정 상태

| 항목 | 상태 |
|------|------|
| ANTHROPIC_API_KEY | ✅ 설정됨 |
| OPENAI_API_KEY (임베딩) | ✅ 설정됨 |
| TAVILY_API_KEY | ✅ 설정됨 |
| GITHUB_TOKEN | ✅ 설정됨 |
| TELEGRAM_BOT_TOKEN | ✅ 설정됨 |
| TELEGRAM_AUTHORIZED_USER_ID | ⚠️ 설정 필요 |
| Redis | ✅ Docker 실행 중 |
| Qdrant | ✅ Docker 실행 중 |

---

## 프로젝트 구조

```
JINXUS/
├── agents/                    # 에이전트 모듈
│   ├── __init__.py           # 에이전트 레지스트리
│   ├── jinxus_core.py        # 총괄 지휘관 (SSE 스트리밍, context_guard)
│   ├── jx_coder.py           # 코드 전문가 (Claude Code CLI 연동)
│   ├── jx_researcher.py      # 리서치 전문가
│   ├── jx_writer.py          # 글쓰기 전문가
│   ├── jx_analyst.py         # 분석 전문가
│   └── jx_ops.py             # 운영 전문가 (GitHub, 스케줄, 파일 실제 실행)
├── channels/                  # 멀티채널 [NEW]
│   ├── __init__.py
│   ├── telegram_bot.py       # 텔레그램 봇
│   └── cli.py                # CLI 인터페이스
├── config/                    # 설정
│   └── settings.py           # (텔레그램 설정 추가됨)
├── core/                      # 핵심 모듈 [UPDATED]
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── jinx_loop.py          # 자가 강화 (A/B 테스트, 롤백)
│   ├── context_guard.py      # 토큰 폭탄 방지 [NEW]
│   ├── model_router.py       # opus/sonnet 자동 선택 [NEW]
│   └── plugin_loader.py      # 플러그인 자동 로더 [NEW]
├── memory/                    # 메모리 시스템
│   ├── __init__.py
│   ├── jinx_memory.py        # 통합 인터페이스 (A/B 테스트 메서드 추가)
│   ├── short_term.py
│   ├── long_term.py
│   └── meta_store.py         # (A/B 테스트 테이블 추가)
├── tools/                     # 도구 모듈
│   ├── base.py
│   ├── code_executor.py      # Claude Code CLI 연동
│   ├── web_searcher.py
│   ├── github_agent.py       # PyGithub 실제 연동
│   ├── scheduler.py          # APScheduler 실제 연동
│   └── file_manager.py       # 파일 조작 (copy 추가)
├── api/                       # FastAPI 라우터
├── frontend/                  # Next.js 프론트엔드
├── main.py                    # FastAPI 서버
├── pyproject.toml             # CLI 엔트리포인트 [NEW]
├── requirements.txt           # (python-telegram-bot 추가)
├── .env.example               # (텔레그램 설정 추가)
└── develop_status.md          # 이 파일
```

---

## 실행 방법

```bash
# 1. 인프라 (이미 실행 중이면 스킵)
docker run -d --name jinxus-redis -p 6379:6379 redis:7-alpine
docker run -d --name jinxus-qdrant -p 6333:6333 qdrant/qdrant

# 2. 백엔드 실행
cd /path/to/JINXUS
pip3 install -r requirements.txt
pip3 install -e .  # CLI 명령어 등록
python3 main.py

# 3. 프론트엔드 실행 (별도 터미널)
cd frontend
npm install
npm run dev

# 4. CLI 사용 (설치 후)
jinxus "안녕?"
jinxus --stream "코드 짜줘"
jinxus --interactive  # 대화형 모드

# 5. 접속
# 프론트엔드: http://localhost:1818
# API: http://localhost:9000
# Swagger: http://localhost:9000/docs
```

---

## 테스트 예시

```bash
# 간단한 대화
curl -X POST http://localhost:9000/chat/sync \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕?"}'

# 코드 실행 (간단한 작업 → python3 직접)
curl -X POST http://localhost:9000/chat/sync \
  -H "Content-Type: application/json" \
  -d '{"message": "파이썬으로 피보나치 수열 10개 출력해줘"}'

# 코드 실행 (복잡한 작업 → Claude Code CLI)
curl -X POST http://localhost:9000/chat/sync \
  -H "Content-Type: application/json" \
  -d '{"message": "FastAPI 서버 프로젝트 만들어줘"}'

# CLI 사용
jinxus "최신 LLM 트렌드 찾아줘"
jinxus --file ./code.py "이 코드 리뷰해줘"
cat error.log | jinxus "이 에러 분석해줘"
```

---

## 알려진 이슈 및 주의사항

### 1. Claude Code CLI 의존성
- `JX_CODER`의 복잡한 작업 실행에는 Claude Code CLI가 필요
- 설치 안 됐으면 복잡한 작업은 실패함
- 간단한 스크립트는 python3 직접 실행으로 동작

### 2. 텔레그램 봇
- `TELEGRAM_AUTHORIZED_USER_ID` 설정 필수 (본인 ID만 허용)
- 텔레그램에서 @userinfobot에게 메시지 보내서 ID 확인
- 봇 토큰은 @BotFather에서 발급

### 3. A/B 테스트
- 과거 성공 작업이 없으면 테스트 없이 바로 적용됨
- Claude API 호출로 점수 평가 → 비용 발생

### 4. 기존 DB 마이그레이션
- SQLite에 `ab_test_logs` 테이블이 새로 추가됨
- 기존 DB가 있으면 `init_db()` 재실행 필요

### 5. 플러그인 로더
- tools/ 폴더의 파일에 문법 오류 있으면 해당 도구만 스킵됨
- 로그에서 "failed to import" 메시지 확인

---

## 롤백 가이드

문제 발생 시 git으로 롤백:

```bash
# 변경 내역 확인
git log --oneline -10

# 특정 커밋으로 롤백 (예: 이전 안정 버전)
git checkout <commit-hash> -- <파일경로>

# 또는 전체 롤백
git reset --hard <commit-hash>
```

### 주요 변경 파일 (2026-02-26)
```
agents/jinxus_core.py    # SSE, context_guard, decompose
agents/jx_coder.py       # Claude Code CLI 연동
agents/jx_ops.py         # 실제 도구 실행
core/jinx_loop.py        # A/B 테스트
core/context_guard.py    # [신규]
core/model_router.py     # [신규]
core/plugin_loader.py    # [신규]
channels/telegram_bot.py # [신규]
channels/cli.py          # [신규]
memory/meta_store.py     # A/B 테스트 테이블
memory/jinx_memory.py    # A/B 테스트 메서드
tools/scheduler.py       # 이름 기반 조회
tools/file_manager.py    # copy 기능
```

---

## 변경 이력

### 2026-02-26 (5차) - UI 마스코트 적용
**프론트엔드 UI:**
- JINXUS 마스코트 캐릭터 적용 (하마 + 안경 + 백팩)
- 사이드바 로고에 마스코트 이미지
- 채팅 빈 화면에 마스코트 표시
- AI 응답 아바타를 마스코트로 변경
- 배경 투명화 처리 (다크 테마 호환)

### 2026-02-26 (4차) - 대규모 업데이트
**버그 수정:**
- SSE 스트리밍 실제 구현 (`messages.stream()` 사용)
- context_guard 추가 (토큰 폭탄 방지, 4000자 제한)
- decompose JSON 파싱 4단계 폴백
- ModelRouter 추가 (opus/sonnet 자동 라우팅)

**JX_OPS 실제 구현:**
- GitHub: PyGithub로 커밋, PR 생성 실제 동작
- Scheduler: APScheduler 작업 등록/관리 실제 동작
- FileManager: 파일 조작 + copy 기능

**JX_CODER 강화:**
- Claude Code CLI 연동 (복잡한 작업)
- 하이브리드 방식 (간단한 건 python3 직접)

**멀티채널:**
- 텔레그램 봇 구현 (명령어, 인가 체크)
- CLI 구현 (jinxus 명령, 스트리밍, 파일 첨부)

**자가 강화:**
- JinxLoop A/B 테스트 완성
- 프롬프트 롤백 기능

**플러그인 시스템:**
- tools/ 자동 스캔 로더
- 런타임 reload 지원

### 2026-02-25 (3차)
- develop_status.md 전면 업데이트
- 프로젝트 구조 문서화
- 기술 스택 정리

### 2026-02-25 (2차)
- 모든 에이전트 LangGraph 패턴 적용 완료
- Next.js 프론트엔드 구현 완료

### 2026-02-25 (1차)
- 초기 구현 완료 (Phase 1~4)
- JINXUS 인격 설정: "주인님" 호칭, 순종적 태도
