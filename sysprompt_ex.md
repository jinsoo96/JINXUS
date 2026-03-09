# 시스템 프롬프트 분석 레퍼런스

> 출처: https://github.com/jujumilk3/leaked-system-prompts

---

## 기업별 시스템 프롬프트 분석

### 1. OpenAI ChatGPT (GPT-4o / GPT-5)

**구조:** 아이덴티티 → 메타데이터(cutoff, 날짜) → 행동 지침 → 도구 정의 → 도구별 가이드라인

**핵심 기법:**
- **Guardian Tool 패턴**: 민감 주제 감지 → 정책 조회 도구 자동 호출. "DO NOT explain yourself"로 강제
- **도구 사용 트리거 4분류**: Local/Freshness/Niche/Accuracy로 "언제 써야 하는지" 명시
- **Deprecated 도구 차단**: "IMPORTANT: Do not attempt to use the old `browser` tool" — 과거 도구 명시적 금지
- **반아첨**: `Be direct; avoid ungrounded or sycophantic flattery`

### 2. Anthropic Claude (Opus 4, Sonnet 4.5)

**구조:** 아이덴티티 → 제품 정보 → 행동 원칙(서술형) → 안전 가드레일 → 톤/포맷 → `<election_info>` 같은 특수 태그

**핵심 기법:**
- **서술형 원칙 기반**: 번호 리스트 아닌 자연어 서술 ("Claude cares about...")
- **포맷 제어 극도로 상세**: bullet 최소 1-2문장, emoji 금지(요청 시만), 볼드 기준까지
- **Skills 시스템 (4.5)**: `/mnt/skills/` 디렉토리에서 작업별 베스트 프랙티스 참조. SKILL.md 먼저 읽기 강제
- **파일 핸들링 3계층**: uploads(입력) → /home/claude(작업) → outputs(산출물)

### 3. Cursor IDE (Agent Mode)

**구조:** 아이덴티티 → XML 태그 섹션 분리 (`<tool_calling>`, `<making_code_changes>`) → 함수 정의 → 사용자 환경

**핵심 기법:**
- **도구 이름 은닉**: "NEVER refer to tool names when speaking to the USER"
- **코드 변경 규칙 7가지**: 린터 에러 3회 초과 반복 금지 등 구체적 함정 방지
- **Explanation before action**: 도구 호출 전 이유 설명 강제

### 4. Perplexity AI

**구조:** 아이덴티티 → Instructions(정보 수집 루프) → Tool Guidelines → Answer Formatting → Citation → Output Rules → Stop Conditions

**핵심 기법:**
- **강제 도구 호출**: "you must call at least one tool to gather information before answering" — 할루시네이션 방지
- **인용 시스템**: `[web:1][web:2]` 형식, 모든 문장에 출처 필수
- **메타 코멘터리 금지**: "Based on my search results..." 같은 표현 구체적으로 나열하여 금지
- **포맷 규칙**: 볼드 3단어 이상 금지, 문단당 볼드 1회, 리스트 중첩 금지
- **Stop Conditions**: 최대 3회 도구 호출

### 5. Google Gemini CLI

**구조:** Core Mandates → Primary Workflows(SE Tasks/New Apps) → Operational Guidelines → Examples → Final Reminder

**핵심 기법:**
- **5단계 워크플로우**: Understand → Plan → Implement → Verify(Tests) → Verify(Standards)
- **프로젝트 컨벤션 우선**: "NEVER assume a library is available"
- **No Chitchat**: "Avoid conversational filler, preambles, or postambles"
- **Example-driven**: 실제 대화 예시 6개 제공

### 6. Manus (에이전트 시스템)

**구조:** `<intro>` → `<system_capability>` → `<event_stream>` → `<agent_loop>` → `<planner_module>` → `<knowledge_module>` → 각종 `_rules` 태그

**핵심 기법:**
- **Agent Loop 6단계**: Analyze → Select Tools → Wait → Iterate → Submit → Standby
- **Planner Module**: 외부 플래너가 실행 계획 제공, 에이전트는 따름
- **Todo.md 패턴**: 체크리스트 파일로 진행 상황 추적
- **Event Stream 아키텍처**: Message/Action/Observation/Plan/Knowledge/Datasource 이벤트 유형 분류

### 7. Microsoft Copilot

**핵심 기법:**
- **능력 제한 투명성**: "I can't edit images", "I can't set a reminder" — 불가능한 것 명확히 나열
- **저작권 보호**: "NEVER provide full copyrighted content verbatim", 요약만 허용

---

## 공통 패턴 정리

### 구조적 패턴

| 패턴 | 사용 기업 | 설명 |
|------|----------|------|
| XML 태그 섹션 분리 | Claude, Cursor, Manus, Bolt, Windsurf | `<tool_calling>`, `<making_code_changes>` 등 관심사 분리 |
| 아이덴티티 → 도구 → 규칙 순서 | 거의 전부 | 정체성 선언이 항상 맨 앞 |
| 메타데이터 동적 주입 | 전부 | `{{currentDateTime}}`, knowledge cutoff 등 |

### 도구 사용 패턴

| 패턴 | 사용 기업 | 설명 |
|------|----------|------|
| 강제 도구 호출 | Perplexity | 답변 전 최소 1회 도구 호출 강제 |
| 도구별 사용 조건 | ChatGPT, Perplexity, Gemini | 각 도구를 "언제" 써야 하는지 시나리오 명시 |
| 도구 호출 상한 | Perplexity, Cursor | 최대 3회, 린터 3회 등 반복 제한 |
| 도구 이름 은닉 | Cursor, Windsurf | 사용자에게 내부 도구 이름 노출 금지 |

### 출력 제어 패턴

| 패턴 | 사용 기업 | 설명 |
|------|----------|------|
| 메타 코멘터리 금지 | Perplexity, Gemini CLI | "Based on my research..." 등 과정 노출 금지 |
| 반아첨 | ChatGPT, Claude | "좋은 질문입니다" 같은 아첨으로 시작 금지 |
| 간결성 우선 | Gemini CLI, Grok | "fewer than 3 lines", "shortest answer" |
| Explanation before action | Cursor, Windsurf | 도구 호출 전 이유 설명 |

### 에이전트 워크플로우 패턴

| 패턴 | 사용 기업 | 설명 |
|------|----------|------|
| 단계적 워크플로우 | Gemini(5단계), Manus(6단계) | Understand → Plan → Implement → Verify |
| Example-driven | Gemini CLI | 실제 대화 예시로 기대 동작 시연 |
| Skills/Knowledge 참조 | Claude 4.5, Manus | 작업 전 베스트 프랙티스 문서 참조 |

---

## JINXUS 적용 제안

### A. JINXUS_CORE 프롬프트 XML 구조화

현재 산문형 → XML 태그로 관심사 분리:

```xml
<identity>
현재 날짜, 정체성, 역할
</identity>

<output_rules>
출력 형식 제어, 메타 코멘터리 금지, 포맷 규칙
</output_rules>

<agent_dispatch>
가용 에이전트, 선택 기준, 위임 규칙
</agent_dispatch>

<tool_usage>
도구 사용 조건, 상한선, deprecated 도구 차단
</tool_usage>
```

### B. 서브에이전트 워크플로우 명시 (Gemini 패턴)

```
## 작업 워크플로우
1. 이해: 주인님의 요청과 기존 컨텍스트 분석
2. 계획: 실행 전략 수립, 필요한 도구 확인
3. 구현: 도구 사용하여 실행
4. 검증: 결과 확인, 에러 처리
5. 보고: 결과만 깔끔하게 (과정 노출 금지)
```

### C. 메타 코멘터리 금지 목록 (Perplexity 패턴)

```
## 금지 표현
- "검색 결과에 따르면..."
- "도구를 호출하여..."
- "분석해보겠습니다..."
- "잠시만요, 확인중입니다..."
결과만 바로 보고해라.
```

### D. Example-driven 프롬프트 (Gemini 패턴)

각 에이전트에 2-3개 입출력 예시 추가 → few-shot 효과

### E. 도구 사용 조건 체계화 (ChatGPT 패턴)

```
## 도구 사용 기준
- 실시간 정보: 현재 날짜 이후 정보 필요 → web_search
- 정확도 중시: 틀리면 안 되는 정보(버전, 날짜 등) → 반드시 검색
- 니치 정보: 널리 알려지지 않은 세부 정보 → 검색
- 코드 실행: 계산/분석 → code_executor
```

### F. 강제 도구 호출 (Perplexity 패턴)

JX_RESEARCHER에 "답변 전 최소 1회 검색 도구 호출 필수" 강제 → 할루시네이션 근본 차단

### G. 능력 제한 명시 (Copilot 패턴)

각 에이전트에 "할 수 없는 것" 목록 추가

### 우선순위

| 순위 | 개선안 | 난이도 | 효과 |
|------|--------|--------|------|
| 1 | B. 워크플로우 명시 | 낮음 | 높음 |
| 2 | C. 메타 코멘터리 금지 | 낮음 | 중간 |
| 3 | D. Example-driven | 낮음 | 높음 |
| 4 | F. 강제 도구 호출 | 낮음 | 높음 |
| 5 | A. XML 구조화 | 중간 | 높음 |
| 6 | E. 도구 사용 조건 | 중간 | 중간 |
| 7 | G. 능력 제한 명시 | 낮음 | 낮음 |

---

## 2차 심층 분석 (2026-03-09)

> 출처: leaked-system-prompts 실제 프롬프트 + Geny/graph-tool-call 심층 분석

### 8. Devin AI (코딩 에이전트)

**핵심 기법:**
- **3-모드 상태머신**: planning(정보 수집만) → standard(반응적 실행) → edit(일괄 수정). 모드별 허용 행동이 다름
- **강제 `<think>` 체크포인트**: git 전/plan 전환 전/완료 보고 전/스크린샷 확인 후 — 의무. 나머지에서 쓰면 페널티
- **정체성 기반 할루시네이션 방지**: 금지("~하지마")가 아닌 "너는 ~하지 않는 존재다" 서술이 더 효과적
  - "You don't create fake sample data or tests when you can't get real data"
  - "You don't mock / override / give fake data when you can't pass tests"
  - "You don't pretend that broken code is working when you test it"
- **DONE/BLOCK/NONE 세션 상태머신**: 완전 종료 vs 유저 필요 vs 진행 중 명확 구분
- **테스트 수정 금지**: 테스트 통과 안 되면 테스트 말고 코드를 고쳐라
- **환경 이슈 분리**: 환경 문제는 보고만 하고 CI로 우회

### 9. Manus AI (에이전트 시스템 심층)

**핵심 기법 (기존 대비 추가):**
- **단일 액션 per 이터레이션**: "Choose only one tool call per iteration" — 연쇄 에러 방지
- **즉시 확인 응답**: "Reply immediately to new user messages. First reply must be brief, only confirming receipt"
- **정보 우선순위 계층**: `authoritative data from datasource API > web search > model's internal knowledge`
- **검색 스니펫 불신**: "Snippets in search results are not valid sources; must access original pages via browser"
- **todo.md 물리 파일**: 컨텍스트 초과해도 진행상황 유지
- **notify vs ask 분리**: 비차단 진행 보고(notify) vs 차단 질문(ask)
- **이벤트 스트림 truncation 인정**: "may be truncated or partially omitted"

### 10. Claude Opus 4.1 / Sonnet 4.5 (심층)

**핵심 기법 (기존 대비 추가):**
- **반아첨 오프닝 금지**: "Claude never starts its response by saying a question or idea was good, great, fascinating, profound, excellent"
- **산문 우선**: "For reports, documents...write in prose and paragraphs without any lists"
- **Long Conversation Reminder**: `<long_conversation_reminder>` 태그로 긴 대화 중 핵심 지시 재주입
- **저작권 하드 리밋**: "15+ words from any single source is a SEVERE VIOLATION"

### 11. 크로스 시스템 비교 (에이전트 루프)

| 패턴 | Manus | Devin | Cursor |
|---|---|---|---|
| 루프 | 단일 액션 + 이벤트 스트림 | 3-모드 상태머신 | 대화형 + 편집 1회/턴 |
| 계획 | Planner module + todo.md | planning 모드 + suggest_plan | 없음 (인라인 추론) |
| 에러 | 수정 → 대안 → 유저 보고 | 테스트 수정 금지; 환경 → CI | 3회 실패 하드 리밋 |

---

## 추가 JINXUS 적용 제안

### H. 정체성 기반 할루시네이션 방지 (Devin 패턴)

금지("~하지마") 대신 정체성 서술:
```
너는 가짜 데이터를 만들지 않는다.
너는 검색 실패 시 지식으로 지어내지 않는다.
너는 작동하지 않는 코드를 작동한다고 보고하지 않는다.
막히면 주인님께 보고한다.
```

### I. 정보 우선순위 계층 (Manus 패턴)

```
정보 신뢰도 순서:
1. 도구 실행 결과 (API, DB, 파일 읽기)
2. 웹 검색 결과 (원본 페이지 확인 필수)
3. 내부 지식 (knowledge cutoff 이전만, 불확실하면 검색)
```

### J. 즉시 확인 + 비차단 진행 보고 (Manus 패턴)

복합 작업 시: 즉시 확인 → 비차단 진행 보고 → 최종 결과

### K. 3회 실패 에스컬레이션 (Cursor/Devin 패턴)

같은 에러로 3회 반복 실패 시 다른 접근 시도 또는 보고

### L. 능력 제한 + 에스컬레이션 경로 (Copilot + Devin 패턴)

각 에이전트에 "할 수 없는 것" + "막혔을 때 행동" 명시

### 업데이트 우선순위

| 순위 | 개선안 | 적용 대상 | 난이도 | 효과 |
|------|--------|----------|--------|------|
| 1 | H. 정체성 기반 할루시네이션 방지 | 전 에이전트 | 낮음 | 높음 |
| 2 | I. 정보 우선순위 계층 | CORE, RESEARCHER | 낮음 | 높음 |
| 3 | J. 즉시 확인 + 진행 보고 | CORE | 낮음 | 중간 |
| 4 | K. 3회 실패 에스컬레이션 | CODER, RESEARCHER | 낮음 | 중간 |
| 5 | L. 능력 제한 + 에스컬레이션 | 전 에이전트 | 낮음 | 낮음 |
