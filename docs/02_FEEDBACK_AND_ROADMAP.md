# JINXUS → JSCLAW 완전 분석 보고서
> 실제 소스 코드 기반 피드백 + 수정 지시 + 멀티채널 설계 + 플러그인 구조 + 향후 로드맵 + 최종 목표
> 작성일: 2026년 2월 25일 | 분석 기준: 실제 레포 소스 (jinxus_core.py, jx_coder.py, orchestrator.py, develop_status.md)

---

## 목차
1. [현재 상태 요약](#1-현재-상태-요약)
2. [실제 소스 기반 버그/문제 피드백](#2-실제-소스-기반-버그문제-피드백)
3. [즉시 수정해야 할 코드 지시](#3-즉시-수정해야-할-코드-지시)
4. [향후 개발 로드맵](#4-향후-개발-로드맵)
5. [멀티채널 + 플러그인 설계](#5-멀티채널--플러그인-설계)
6. [궁극적으로 뭘 만들게 되는 건지](#6-궁극적으로-뭘-만들게-되는-건지)

---

## 1. 현재 상태 요약

### 진행률 실제 평가

| 항목 | develop_status 선언 | 실제 동작 상태 | 진짜 완성도 |
|------|---------------------|----------------|-------------|
| Phase 1 (뼈대) | ✅ 완료 | 동작함 | **85%** |
| Phase 2 (전체 에이전트) | ✅ 완료 | 구조는 있음 | **70%** |
| Phase 3 (장기기억) | ✅ 완료 | 연결은 됨 | **80%** |
| Phase 4 (JinxLoop) | ⚠️ 부분 | 피드백 저장만 됨 | **40%** |
| Phase 5 (프론트엔드) | ⚠️ 부분 | UI는 있음 | **60%** |

### 잘 된 것 (진짜로)

지금 코드에서 **실제로 잘 만들어진 부분**이 있어. 이건 유지해야 함.

**LangGraph 그래프 구조** — `jinxus_core.py`의 intake→decompose→dispatch→aggregate→reflect→memory_write→respond 흐름이 블루프린트대로 정확하게 구현됨. 노드 연결, 상태(State) 스키마 설계 모두 깔끔함.

**retry 지수 백오프** — `jx_coder.py`의 `_execute_with_retry()`에서 1초→2초→4초 백오프 로직 제대로 구현됨. 이건 그대로 쓰면 됨.

**orchestrator 싱글톤** — `get_instance()` 패턴으로 전역 상태 안전하게 관리. 초기화 흐름(`initialize()`)도 깔끔함.

**병렬/순차 실행 분리** — `_execute_parallel()`과 `_execute_sequential()`에서 `asyncio.gather` + `depends_on` 기반 판단 로직이 제대로 작동함.

**importance_score 선택적 저장** — `jx_coder.py`의 `_memory_write()`에서 실패 여부/반성 길이 기반으로 저장 여부 판단하는 로직이 블루프린트 의도대로 구현됨.

---

## 2. 실제 소스 기반 버그/문제 피드백

### 🔴 치명적 문제 3가지 (지금 당장 고쳐야 함)

---

#### 문제 1: SSE 스트리밍이 가짜다

**파일:** `agents/jinxus_core.py` → `run_stream()` 메서드

**현재 코드:**
```python
async def run_stream(self, user_input: str, session_id: str = None):
    # ...
    result = await self.run(user_input, session_id)   # ← 여기서 전부 끝남
    
    response = result["response"]
    chunk_size = 100
    for i in range(0, len(response), chunk_size):
        yield {                                         # ← 다 끝내고 100자씩 자름
            "event": "message",
            "data": {"content": response[i:i+chunk_size], "chunk": True},
        }
```

**실제 동작 흐름:**
```
진수 요청 → [4~10초 완전한 침묵] → 갑자기 응답 쭉 표시됨
```

**문제:** `self.run()`이 완료될 때까지 기다렸다가, 끝난 다음에 결과를 100자씩 잘라서 보내는 방식. 이건 스트리밍이 아니라 "버퍼 분할 전송"임. 사용자 경험상 실시간 응답처럼 보이지 않음.

**왜 중요한가:** LLM을 쓰는 이유 중 하나가 "타이핑하는 것처럼 실시간으로 응답이 나오는 경험"인데, 지금 방식으로는 그게 없음. 특히 복잡한 명령에서 10초 넘게 아무것도 안 보이면 진수 입장에서 "고장났나?" 싶음.

---

#### 문제 2: JX_CODER가 Claude Code CLI를 안 쓴다

**파일:** `agents/jx_coder.py` → `_execute_python()` 메서드

**현재 코드:**
```python
async def _execute_python(self, code: str) -> dict:
    """Python 코드 실행"""
    with tempfile.TemporaryDirectory() as tmpdir:
        code_file = Path(tmpdir) / "script.py"
        code_file.write_text(code, encoding="utf-8")

        process = await asyncio.create_subprocess_exec(
            "python3",          # ← 그냥 python3 직접 실행
            str(code_file),
            ...
        )
```

**블루프린트 의도:**
```python
# 원래 이렇게 돼야 함
process = await asyncio.create_subprocess_exec(
    "claude",                    # ← Claude Code CLI
    "--dangerously-skip-permissions",
    "--print",
    prompt,
    ...
)
```

**현재 방식의 한계:**
- 단순 코드 스니펫만 실행 가능 (print()가 있는 짧은 코드)
- pandas, numpy 등 미설치 패키지 쓰면 바로 실패
- 멀티 파일 작업 불가능
- 파일 읽기/쓰기 요청 처리 불가능
- "FastAPI 서버 만들어줘" 같은 복잡한 요청 처리 불가능

**Claude Code CLI를 쓰면:**
- 스스로 패키지 설치 가능
- 파일 생성/수정 가능
- 멀티 파일 프로젝트 빌드 가능
- 에러 나면 스스로 수정 가능
- 실질적인 코딩 자동화 가능

이게 빠지면 JX_CODER는 "코드 생성기"에 불과하고, 진짜 "코딩 에이전트"가 아님.

---

#### 문제 3: JX_OPS가 실제로 아무것도 안 한다

**develop_status.md 기재 내용:**
```
JX_OPS | ✅ 작동 | 시스템/운영 작업 안내 | 파괴적 작업 감지, 안전 경고
```

**실제 동작:**
- "이 코드 GitHub에 올려줘" → 방법 설명만 함
- "파일 폴더 정리해줘" → 어떻게 하면 되는지 안내만 함
- "매일 9시에 뉴스 요약 실행해줘" → 스케줄 등록 방법 설명만 함

**문제:** 에이전트가 "실행"이 아니라 "안내"를 하고 있음. 진수 입장에서는 "알아서 해줘"가 필요한데 "이렇게 하면 됩니다"만 돌아옴.

미구현 목록:
- `github_agent.py` — PyGithub 연동 실제 미구현
- `scheduler.py` — APScheduler 등록 실제 미구현
- `file_manager.py` — 실제 파일 조작 미구현

---

### 🟡 중요한 구조적 문제 2가지

---

#### 문제 4: context_guard 없음 → 토큰 폭탄 위험

**문제 발생 시나리오:**
```
진수: "데이터 분석 코드 짜서 실행하고 그 결과 해석해줘"

→ JX_CODER 실행: 코드 생성 + 실행결과 전체 state에 저장 (수천 토큰)
→ JX_ANALYST 실행: 앞 결과 context로 받음
→ _aggregate_results() 호출: 두 결과 합쳐서 Claude에게 전달
→ 💥 컨텍스트 한도 초과 또는 과도한 과금
```

**현재 `_aggregate_results()`:**
```python
async def _aggregate_results(self, user_input: str, results: list[AgentResult]) -> str:
    results_text = ""
    for r in results:
        results_text += f"\n### {r['agent_name']}\n{r['output']}\n"  # ← output 전체 다 들어감
```

`r['output']`에 아무런 길이 제한이 없음. JX_CODER가 긴 코드 + 실행결과를 output으로 반환하면 그게 그대로 다음 Claude 호출에 들어감.

---

#### 문제 5: JinxLoop A/B 테스트가 미완성

**develop_status.md:**
```
- [ ] A/B 테스트 실제 실행
```

지금 JinxLoop은:
1. 피드백 받음 ✅
2. 실패 패턴 분석 ✅
3. 프롬프트 개선안 생성 ✅
4. 새 버전 저장 ✅
5. **A/B 비교 실행** ❌ — 새 프롬프트를 만들어놓고 기존이랑 실제로 비교를 안 함

이게 없으면 JinxLoop이 "개선을 했는지 안 했는지 검증이 안 되는" 상태. 오히려 이상한 방향으로 프롬프트가 바뀔 수도 있음.

---

### 🟢 작은 개선 포인트들

**decompose 결과 파싱 취약:**
```python
def _parse_decomposition(self, response_text: str) -> dict:
    try:
        json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        return json.loads(response_text)
    except json.JSONDecodeError:
        return {"subtasks": [], "execution_mode": "sequential"}  # ← 파싱 실패 시 빈 배열
```

Claude가 JSON 형식을 조금만 다르게 뱉어도 subtasks가 빈 배열로 떨어져서 에이전트 아무것도 안 쓰고 직접 응답으로 처리됨. 더 강건한 파싱 필요.

**model이 하드코딩:**
모든 에이전트가 `settings.claude_model` 하나를 씀. 단순 chat은 sonnet, 복잡한 분석은 opus 이런 라우팅이 없어서 비용 최적화 안 됨.

---

## 3. 즉시 수정해야 할 코드 지시

### Fix 1: 진짜 SSE 스트리밍

**`agents/jinxus_core.py` `run_stream()` 전체 교체**

```python
async def run_stream(self, user_input: str, session_id: str = None):
    """진짜 SSE 스트리밍 — 토큰 단위 실시간 전송"""
    if not session_id:
        session_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())

    yield {"event": "start", "data": {"task_id": task_id, "session_id": session_id}}
    yield {"event": "manager_thinking", "data": {"step": "decompose"}}

    # 1. decompose (이건 먼저 끝내야 함)
    subtasks, execution_mode = await self._decompose(user_input, session_id, task_id)

    # 2. 에이전트가 있으면 에이전트 실행 (기존 방식 유지)
    if subtasks and subtasks[0]["assigned_agent"] != "DIRECT":
        for task in subtasks:
            yield {"event": "agent_started", "data": {"agent": task["assigned_agent"]}}

        results = await self._dispatch(subtasks, execution_mode)

        for r in results:
            yield {
                "event": "agent_done",
                "data": {"agent": r["agent_name"], "success": r["success"]}
            }

        # 취합 결과를 스트리밍
        aggregate_text = await self._aggregate_results(user_input, results)
        chunk_size = 50
        for i in range(0, len(aggregate_text), chunk_size):
            yield {"event": "message", "data": {"content": aggregate_text[i:i+chunk_size], "chunk": True}}
            await asyncio.sleep(0.01)  # 프론트가 받을 수 있게 약간의 딜레이

    else:
        # 직접 응답: 여기서 진짜 스트리밍
        yield {"event": "agent_started", "data": {"agent": "JINXUS_CORE"}}

        with self._client.messages.stream(
            model=self._model,
            max_tokens=2048,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": user_input}],
        ) as stream:
            for text_chunk in stream.text_stream:
                yield {"event": "message", "data": {"content": text_chunk, "chunk": True}}

    yield {"event": "done", "data": {"task_id": task_id, "success": True}}
```

---

### Fix 2: JX_CODER Claude Code CLI 연동

**`tools/code_executor.py` 새로 만들기**

```python
"""Claude Code CLI 기반 코드 실행기"""
import asyncio
import uuid
import os
from pathlib import Path
from config import get_settings


class CodeExecutor:
    """Claude Code CLI를 subprocess로 실행하는 도구
    
    claude_company의 process_manager.py 패턴 참고.
    """

    DEFAULT_TIMEOUT = 300  # 5분
    STORAGE_ROOT = "/tmp/jinxus_sessions"

    async def run(self, prompt: str, timeout: int = None) -> dict:
        """Claude Code CLI 실행"""
        session_id = str(uuid.uuid4())
        working_dir = Path(self.STORAGE_ROOT) / session_id
        working_dir.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env["CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS"] = "true"

        try:
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--dangerously-skip-permissions",
                "--print",          # 비대화형 모드
                prompt,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(working_dir),
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout or self.DEFAULT_TIMEOUT,
            )

            return {
                "success": process.returncode == 0,
                "output": stdout.decode("utf-8", errors="replace"),
                "error": stderr.decode("utf-8", errors="replace"),
                "working_dir": str(working_dir),
                "exit_code": process.returncode,
            }

        except asyncio.TimeoutError:
            return {
                "success": False,
                "output": "",
                "error": f"타임아웃 ({timeout or self.DEFAULT_TIMEOUT}초 초과)",
                "working_dir": str(working_dir),
                "exit_code": -1,
            }
```

**`agents/jx_coder.py` `_execute()` 수정:**

```python
# 기존 python3 직접 실행 → CodeExecutor 사용으로 교체
from tools.code_executor import CodeExecutor

async def _execute(self, instruction: str, context: list, memory_context: list, last_error: str = None) -> dict:
    executor = CodeExecutor()
    
    prompt = f"""다음 요청을 완수해줘:
{instruction}

{f"이전 시도 오류: {last_error}" if last_error else ""}
"""
    
    result = await executor.run(prompt)
    
    if result["success"]:
        return {
            "success": True,
            "score": 0.95,
            "output": f"주인님, 완료했습니다.\n\n{result['output']}",
            "error": None,
        }
    else:
        return {
            "success": False,
            "score": 0.3,
            "output": result["error"],
            "error": result["error"],
        }
```

---

### Fix 3: context_guard 추가

**`core/context_guard.py` 신규 파일:**

```python
"""컨텍스트 윈도우 관리 — 토큰 폭탄 방지"""

MAX_OUTPUT_CHARS = 4000   # 에이전트 output 최대 길이
MAX_CONTEXT_CHARS = 8000  # aggregate로 넘기는 최대 전체 길이


def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """에이전트 output 길이 제한"""
    if len(output) <= max_chars:
        return output
    
    half = max_chars // 2
    return (
        output[:half]
        + f"\n\n... [중간 {len(output) - max_chars}자 생략] ...\n\n"
        + output[-half:]
    )


def guard_results(results: list[dict]) -> list[dict]:
    """aggregate 전에 각 에이전트 output 자르기"""
    guarded = []
    for r in results:
        guarded.append({
            **r,
            "output": truncate_output(r["output"]),
        })
    return guarded
```

**`agents/jinxus_core.py` `_aggregate_node()` 수정:**

```python
from core.context_guard import guard_results

async def _aggregate_node(self, state: ManagerState) -> ManagerState:
    results = guard_results(state["dispatch_results"])  # ← 이 줄 추가
    user_input = state["user_input"]

    if len(results) == 1:
        aggregated = results[0]["output"]
    else:
        aggregated = await self._aggregate_results(user_input, results)

    return {**state, "aggregated_output": aggregated}
```

---

### Fix 4: JX_OPS 실제 GitHub 연동

**`tools/github_agent.py` 실제 구현:**

```python
from github import Github
from config import get_settings

class GitHubAgent:
    def __init__(self):
        settings = get_settings()
        self._gh = Github(settings.github_token)

    async def create_commit(self, repo_name: str, file_path: str, content: str, message: str) -> dict:
        """파일 커밋"""
        try:
            repo = self._gh.get_repo(repo_name)
            try:
                existing = repo.get_contents(file_path)
                repo.update_file(file_path, message, content, existing.sha)
                action = "updated"
            except Exception:
                repo.create_file(file_path, message, content)
                action = "created"
            
            return {"success": True, "action": action, "file": file_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_pr(self, repo_name: str, title: str, body: str, head: str, base: str = "main") -> dict:
        """PR 생성"""
        try:
            repo = self._gh.get_repo(repo_name)
            pr = repo.create_pull(title=title, body=body, head=head, base=base)
            return {"success": True, "pr_url": pr.html_url, "pr_number": pr.number}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

### Fix 5: decompose 파싱 강화

**`agents/jinxus_core.py` `_parse_decomposition()` 교체:**

```python
def _parse_decomposition(self, response_text: str) -> dict:
    """더 강건한 JSON 파싱"""
    import re, json

    # 1차: ```json 블록
    m = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 2차: ``` 블록 (언어 표시 없음)
    m = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3차: { } 찾기
    m = re.search(r"\{.*\}", response_text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # 4차: 파싱 완전 실패 → 직접 응답으로 폴백 (에이전트 없이 처리)
    return {"subtasks": [], "execution_mode": "sequential", "brief_plan": "direct_response"}
```

---

### Fix 6: ModelRouter 추가 (비용 최적화)

**`core/model_router.py` 신규 파일:**

```python
"""작업 복잡도에 따른 모델 자동 선택"""
from config import get_settings


def select_model(agent_name: str, instruction: str) -> str:
    """에이전트 + 명령 복잡도 기반 모델 선택"""
    settings = get_settings()

    # 품질이 중요한 작업 → opus
    quality_critical_agents = {"JX_WRITER", "JX_ANALYST"}
    if agent_name in quality_critical_agents:
        return settings.claude_model  # claude-opus-4-6

    # 짧고 단순한 명령 → sonnet (비용 절감)
    if len(instruction) < 100 and not any(
        kw in instruction for kw in ["분석", "작성", "설계", "최적화", "자소서"]
    ):
        return settings.claude_fallback_model  # claude-sonnet-4-6

    return settings.claude_model
```

---

## 4. 향후 개발 로드맵

### 다음 2주 (핵심 수정)

**Week 1 — 3가지 치명적 버그 수정**

| 일자 | 작업 | 파일 |
|------|------|------|
| Day 1 | 진짜 SSE 스트리밍 구현 | `agents/jinxus_core.py` |
| Day 2 | Claude Code CLI 연동 (`code_executor.py`) | `tools/code_executor.py` |
| Day 3 | JX_CODER를 CodeExecutor 사용으로 교체 | `agents/jx_coder.py` |
| Day 4 | context_guard 추가 | `core/context_guard.py` |
| Day 5 | decompose 파싱 강화 + ModelRouter 추가 | `agents/jinxus_core.py`, `core/model_router.py` |

**Week 2 — JX_OPS 실제 구현**

| 일자 | 작업 | 파일 |
|------|------|------|
| Day 1~2 | `github_agent.py` 실제 PyGithub 연동 | `tools/github_agent.py` |
| Day 3 | `scheduler.py` APScheduler 실제 등록 | `tools/scheduler.py` |
| Day 4 | `file_manager.py` 실제 파일 조작 | `tools/file_manager.py` |
| Day 5 | JX_OPS에 실제 툴 연결 | `agents/jx_ops.py` |

---

### 다음 1개월 (기능 확장)

**JS_PERSONA 에이전트 추가**

진수가 자소서/포트폴리오를 자주 쓰는 걸 감안해서, 일반 JX_WRITER와 분리된 "진수 전용 글쓰기 에이전트"를 만들어야 함.

```
JS_PERSONA 역할:
- 진수의 과거 자소서/포트폴리오를 Qdrant에 벡터로 저장
- 새 자소서 요청이 오면 과거 버전들 참고 후 진수 어투로 작성
- 회사별 맞춤 전략 장기기억에 축적
  (예: 스타트업 → 자율성/임팩트 강조 / 대기업 → 안정성/성과 강조)
- JX_WRITER와의 차이: "진수로서 쓰는 것"에 특화
```

**JinxLoop A/B 테스트 완성**

```python
# jinxloop/jinx_loop.py에 추가해야 할 핵심 로직
async def _run_ab_test(self, agent_name: str, old_version: str, new_version: str):
    """이후 10작업을 반반씩 신/구 버전으로 실행하여 비교"""
    test_results = {"old": [], "new": []}
    
    # 다음 10작업에 버전 할당 플래그 설정
    await self._memory.set_ab_test(
        agent_name=agent_name,
        old_version=old_version,
        new_version=new_version,
        remaining_tasks=10,
    )
    # → 에이전트가 실행될 때마다 플래그 체크 후 버전 교대로 선택
    # → 10작업 완료 시 success_score 평균 비교 후 승자 확정
```

**SSE 프론트엔드 실시간 연동**

```
현재: 채팅 UI가 동기 API (/chat/sync) 사용
목표: /chat SSE 엔드포인트로 교체, 에이전트 실행 상태 실시간 표시

UI에 보여줄 것:
- "JX_CODER 작업 중..." (에이전트 실행 중 표시)
- 토큰 단위 실시간 타이핑 효과
- 어떤 에이전트가 동원됐는지 태그로 표시
```

---

### 다음 3개월 (고도화)

**Telegram 알림 연동**

```
진수 시나리오:
"매일 오전 9시에 AI 트렌드 뉴스 요약해서 텔레그램으로 보내줘"

→ JX_OPS가 APScheduler에 등록
→ 매일 9시 JX_RESEARCHER가 검색 실행
→ JX_WRITER가 요약 작성
→ Telegram Bot API로 진수에게 전송

.env에 TELEGRAM_BOT_TOKEN이 이미 있음 → 연동만 하면 됨
```

**데이터 사이언스 특화 기능**

진수 분야가 DS/AI이니까 이 방향으로 강화:

```
JX_ANALYST 강화:
- Jupyter Notebook 자동 생성
- 데이터 시각화 (matplotlib/seaborn 코드 생성 + 실행)
- ML 실험 결과 추적 (mlflow 연동)
- Kaggle 데이터셋 검색 + 다운로드 자동화
```

**로컬 모델 폴백 (비용 최적화)**

```
단순 반복 작업 → Ollama 로컬 모델 사용
복잡한 추론 작업 → Claude API 사용

월 API 비용 대폭 절감 가능
```

**포트폴리오 자동 업데이트**

```
진수가 프로젝트 완성 → JS_OPS가 GitHub 업데이트
                      → JS_PERSONA가 포트폴리오 문서 자동 업데이트
                      → JS_WRITER가 기술 블로그 초안 작성
```

---

## 5. 멀티채널 + 플러그인 설계

### 핵심 구조 — 채널은 여러 개, 두뇌는 하나

```
┌─────────────────────────────────────────────────────┐
│                  입력 채널 (Interface Layer)          │
│                                                     │
│  📱 텔레그램 봇    💻 CLI     🖥 웹 UI    ⏰ 스케줄러 │
│        │              │          │            │     │
└────────┼──────────────┼──────────┼────────────┼─────┘
         │              │          │            │
         └──────────────┴──────────┴────────────┘
                                │
                                ▼
                    ┌─────────────────────┐
                    │    JINXUS_CORE       │
                    │   (두뇌, 하나뿐)     │
                    └──────────┬──────────┘
                               │
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
   ┌──────────┐         ┌──────────┐         ┌──────────┐
   │ JX_CODER │         │JX_RESEARCH│        │ JX_OPS   │
   └──────────┘         └──────────┘         └──────────┘

플러그인 풀 (tools/)
   code_executor  web_searcher  github_agent  telegram  scheduler  ...
   [ON]           [ON]          [ON]          [ON]      [ON]       [추가 가능]
```

진수가 텔레그램으로 보내든, 터미널에서 치든, 스케줄러가 자동 실행하든 **JINXUS_CORE 하나가 전부 받아서 처리함.**

---

### 5-1. 텔레그램 채널

**동작 흐름:**
```
진수 (폰, 길가면서)
  ↓ "fastapi 서버 에러 고쳐줘. 어제 짠 코드야"
텔레그램 봇
  ↓
JINXUS_CORE
  ↓
JX_CODER → 데스크탑에서 실제 코드 수정 + 실행
  ↓
"수정 완료, PR 올렸습니다 주인님" 텔레그램으로 전송
```

**`channels/telegram_bot.py`** 신규 파일:

```python
"""텔레그램 봇 — JINXUS_CORE와 연결"""
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from core.orchestrator import get_orchestrator

AUTHORIZED_USER_ID = 진수_텔레그램_ID  # 본인만 허용


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != AUTHORIZED_USER_ID:
        return
    
    user_input = update.message.text
    chat_id = update.effective_chat.id
    
    thinking_msg = await context.bot.send_message(chat_id, "⚙️ 처리 중...")
    
    orchestrator = get_orchestrator()
    result = await orchestrator.run_task(
        user_input=user_input,
        session_id=f"telegram_{chat_id}",
    )
    
    response = result["response"]
    await thinking_msg.delete()
    
    # 텔레그램 4096자 제한 처리
    for chunk in [response[i:i+4000] for i in range(0, len(response), 4000)]:
        await context.bot.send_message(chat_id, chunk, parse_mode="Markdown")


def start_telegram_bot(token: str):
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
```

**`main.py`에 추가:**

```python
if settings.telegram_bot_token:
    asyncio.create_task(
        asyncio.to_thread(start_telegram_bot, settings.telegram_bot_token)
    )
```

> `.env`에 `TELEGRAM_BOT_TOKEN`이 이미 있음 → **파일 하나 만들면 내일부터 폰으로 JINXUS 사용 가능.**

**텔레그램 특수 명령:**
```
/status          → 에이전트 상태 + 실행 중인 작업 확인
/agents          → 현재 활성화된 에이전트 목록
/memory 검색어   → 장기기억 검색
/improve         → 수동 자가 강화 트리거
/cancel          → 현재 실행 중인 작업 취소
/schedule list   → 등록된 스케줄 목록
```

---

### 5-2. CLI 채널

**사용 예시:**
```bash
# 직접 명령
$ jinxus "pandas DataFrame 결측치 처리 함수 짜줘"

# 파이프로
$ cat error.log | jinxus "이 에러 분석하고 수정 방법 알려줘"

# 파일 첨부
$ jinxus "이 코드 리뷰해줘" --file ./src/model.py

# 에이전트 지정
$ jinxus --agent JX_RESEARCHER "RAG 최신 논문 찾아줘"

# 스트리밍 출력
$ jinxus --stream "FastAPI 서버 전체 구조 설계해줘"
```

**`channels/cli.py`** 신규 파일:

```python
"""CLI 채널 — 터미널에서 JINXUS 직접 사용"""
import asyncio, argparse, sys
from core.orchestrator import get_orchestrator


async def run_cli(args):
    orchestrator = get_orchestrator()
    await orchestrator.initialize()
    
    user_input = args.message
    if args.file:
        with open(args.file) as f:
            user_input = f"{user_input}\n\n```\n{f.read()}\n```"
    
    if not sys.stdin.isatty():
        user_input = f"{user_input}\n\n{sys.stdin.read()}"
    
    if args.stream:
        async for event in orchestrator.run_task_stream(user_input):
            if event["event"] == "message":
                print(event["data"]["content"], end="", flush=True)
            elif event["event"] == "agent_started":
                print(f"\n[{event['data']['agent']} 작동 중...]", flush=True)
        print()
    else:
        result = await orchestrator.run_task(user_input)
        print(result["response"])


def main():
    parser = argparse.ArgumentParser(description="JINXUS CLI")
    parser.add_argument("message", help="JINXUS에게 전달할 명령")
    parser.add_argument("--file", "-f", help="첨부할 파일 경로")
    parser.add_argument("--agent", "-a", help="특정 에이전트 지정")
    parser.add_argument("--stream", "-s", action="store_true", help="스트리밍 출력")
    asyncio.run(run_cli(parser.parse_args()))
```

**`pyproject.toml`에 엔트리포인트 추가:**
```toml
[project.scripts]
jinxus = "channels.cli:main"
```
```bash
pip install -e .
jinxus "안녕?"   # 어디서든 jinxus 명령 사용 가능
```

---

### 5-3. 데스크탑 자율 작동 (Daemon 모드)

**진수가 자는 동안 JINXUS가 혼자 일하는 구조:**

```
"오늘 밤 자는 동안 내 GitHub 레포 전체 코드 리뷰하고
 개선사항 PR로 올려줘. 아침에 확인할게."

→ JX_CODER가 밤새 코드 분석
→ JX_OPS가 브랜치 생성 + 수정 + PR 생성
→ 아침에 텔레그램: "PR 3개 올렸습니다 주인님"
```

**`channels/daemon.py`** 신규 파일:

```python
"""JINXUS Daemon — 데스크탑에서 24시간 백그라운드 실행"""
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from core.orchestrator import get_orchestrator
from channels.telegram_bot import send_notification


class JinxusDaemon:
    def __init__(self):
        self.orchestrator = get_orchestrator()
        self.scheduler = AsyncIOScheduler()
        self.running_tasks = {}

    async def start(self):
        await self.orchestrator.initialize()
        self.scheduler.start()
        await self._restore_schedules()
        print("JINXUS Daemon 시작됨. 대기 중...")
        while True:
            await asyncio.sleep(60)
            await self._health_check()

    async def add_schedule(self, cron: str, task_prompt: str, name: str) -> str:
        job = self.scheduler.add_job(
            self._run_scheduled_task, "cron",
            **self._parse_cron(cron),
            args=[task_prompt, name], id=name, replace_existing=True,
        )
        await self.orchestrator._memory.save_schedule(name, cron, task_prompt)
        return job.id

    async def run_background_task(self, task_prompt: str, task_id: str = None) -> str:
        """장기 작업 백그라운드 실행 — 즉시 task_id 반환, 완료 시 텔레그램 알림"""
        import uuid
        if not task_id:
            task_id = str(uuid.uuid4())[:8]

        async def _run():
            result = await self.orchestrator.run_task(task_prompt)
            await send_notification(
                f"✅ 백그라운드 작업 완료 (ID: {task_id})\n\n{result['response'][:3000]}"
            )

        self.running_tasks[task_id] = asyncio.create_task(_run())
        return task_id

    async def _health_check(self):
        health = await self.orchestrator.get_system_status()
        if not health["redis_connected"] or not health["qdrant_connected"]:
            await send_notification("⚠️ 인프라 연결 문제 감지됨")

    async def _restore_schedules(self):
        schedules = await self.orchestrator._memory.get_all_schedules()
        for s in schedules:
            if s["is_active"]:
                await self.add_schedule(s["cron"], s["task_prompt"], s["name"])
        print(f"{len(schedules)}개 스케줄 복구됨")
```

**실행:**
```bash
# 백그라운드 데몬
nohup python -m channels.daemon &

# systemd 서비스 등록 (부팅 시 자동 시작)
# → macOS는 launchd 사용
```

---

### 5-4. 플러그인 시스템 (파일 넣다 뺐다)

**설계 원칙: 파일 하나 = 플러그인 하나.**

```
tools/                          ← 파일 넣으면 자동 활성화
├── code_executor.py            [ON]  기본
├── web_searcher.py             [ON]  기본
├── github_agent.py             [ON]  기본
├── telegram_notify.py          [ON]  기본
├── scheduler.py                [ON]  기본
│
├── notion_agent.py             [OFF → 파일 넣으면 ON]
├── arxiv_searcher.py           [OFF → 파일 넣으면 ON]
├── kaggle_downloader.py        [OFF → 파일 넣으면 ON]
└── custom_anything.py          [직접 만들어서 넣으면 됨]
```

**`core/plugin_loader.py`** 신규 파일:

```python
"""플러그인 자동 로더 — tools/ 폴더 스캔해서 자동 등록"""
import importlib, inspect
from pathlib import Path


class PluginLoader:
    def __init__(self, tools_dir: str = "tools"):
        self.tools_dir = Path(tools_dir)
        self.loaded_tools = {}

    def scan_and_load(self) -> dict:
        self.loaded_tools = {}
        for py_file in self.tools_dir.glob("*.py"):
            if py_file.stem.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"tools.{py_file.stem}")
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if hasattr(obj, "name") and hasattr(obj, "run"):
                        instance = obj()
                        self.loaded_tools[instance.name] = instance
                        print(f"  ✓ 툴 로드됨: {instance.name}")
                        break
            except Exception as e:
                print(f"  ✗ 툴 로드 실패: {py_file.name} — {e}")
        return self.loaded_tools

    def get_tools_for_agent(self, agent_name: str) -> dict:
        return {
            name: tool for name, tool in self.loaded_tools.items()
            if not hasattr(tool, "allowed_agents") or agent_name in tool.allowed_agents
        }

    def reload(self) -> dict:
        """재시작 없이 런타임 중 재스캔"""
        return self.scan_and_load()
```

**플러그인 작성 규칙 (이 형식만 지키면 끝):**

```python
# tools/arxiv_searcher.py  ← 이 파일 tools/에 넣으면 자동 활성화
import httpx

class ArxivSearcher:
    name = "arxiv_searcher"
    description = "arxiv에서 AI 논문 검색"
    allowed_agents = ["JX_RESEARCHER"]
    
    async def run(self, query: str, max_results: int = 5) -> dict:
        url = f"http://export.arxiv.org/api/query?search_query={query}&max_results={max_results}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
        return {"success": True, "results": self._parse(response.text)}
```

**런타임 플러그인 관리 API:**
```bash
GET  /plugins                  # 현재 로드된 툴/에이전트 목록
POST /plugins/reload           # 재시작 없이 즉시 재스캔
POST /plugins/toggle           # 특정 툴 ON/OFF
```

---

### 5-5. 전체 실행 구조 (데스크탑에서 돌아가는 것들)

```
프로세스 1: python main.py
  → FastAPI 서버 (웹 UI + REST API)
  → 텔레그램 봇 (asyncio task)
  → APScheduler (스케줄 작업)
  → JINXUS_CORE + 에이전트들
  → 플러그인 로더

프로세스 2: docker
  → Redis (단기기억)
  → Qdrant (장기기억)
```

**단 2개의 프로세스로 전부 돌아감.**

---

### 5-6. 멀티채널 구현 우선순위

| 순서 | 기능 | 난이도 | 임팩트 | 예상 시간 |
|------|------|--------|--------|-----------|
| 1 | 텔레그램 봇 연동 | 쉬움 | 매우 높음 | 1일 |
| 2 | CLI 채널 (`jinxus` 명령) | 쉬움 | 높음 | 반나절 |
| 3 | 플러그인 로더 | 중간 | 높음 | 1일 |
| 4 | 백그라운드 장기 작업 | 중간 | 높음 | 1일 |
| 5 | Daemon + systemd 등록 | 중간 | 중간 | 1일 |
| 6 | 런타임 플러그인 ON/OFF API | 쉬움 | 중간 | 반나절 |

**총 약 1주일. 텔레그램부터 시작하는 게 맞음 — `.env`에 토큰 이미 있음.**

---

## 6. 궁극적으로 뭘 만들게 되는 건지

### 한 줄 정의

> **"진수의 두 번째 뇌"** — 명령 하나로 코딩, 리서치, 글쓰기, 분석, 운영이 전부 자동으로 되는 개인화 AI 참모 시스템

---

### 3개월 후 진수가 실제로 쓸 수 있는 것들

**시나리오 1 — 취업 준비**
```
진수: "카카오 데이터 엔지니어 공고 보고 자소서 써줘"

JINXUS:
1. JX_RESEARCHER → 카카오 데이터 엔지니어 공고 + 기술 스택 검색
2. JS_PERSONA → 진수의 과거 자소서 장기기억에서 로드, 어투/강조점 파악
3. JX_WRITER + JS_PERSONA → 카카오 문화에 맞는 자소서 초안 작성
4. 결과물 파일로 저장까지 자동

진수는 명령 하나만 했는데 맞춤 자소서가 완성됨
```

**시나리오 2 — 데이터 사이언스 프로젝트**
```
진수: "타이타닉 데이터로 생존율 예측 모델 만들어줘. 코드 짜고 실행하고 결과 해석까지"

JINXUS:
1. JX_CODER → Claude Code CLI로 데이터 로드, EDA, 모델 학습 코드 작성 및 실행
2. JX_ANALYST → 모델 성능 해석, 인사이트 도출
3. JX_RESEARCHER → 관련 최신 기법 검색 후 개선 제안
4. 결과 보고서 자동 생성

한 번의 명령으로 프로젝트 완성
```

**시나리오 3 — 자동화 설정**
```
진수: "매일 오전 8시에 최신 AI 논문 3개 요약해서 텔레그램으로 보내줘"

JINXUS:
1. JX_OPS → APScheduler에 매일 8시 작업 등록
2. (매일 8시) JX_RESEARCHER → arxiv에서 최신 논문 검색
3. JX_WRITER → 논문 3개 요약 작성
4. Telegram으로 진수에게 전송

설정 한 번으로 매일 자동 실행
```

**시나리오 4 — 코드 리뷰 + GitHub 자동화**
```
진수: "이 파이썬 코드 리뷰하고 개선사항 적용해서 GitHub에 PR 올려줘"

JINXUS:
1. JX_CODER → Claude Code CLI로 코드 분석 및 개선사항 적용
2. JX_OPS → feature 브랜치 생성, 커밋, PR 생성까지 자동
3. JX_RESEARCHER → 관련 best practice 검색 후 PR description에 포함

진수는 리뷰 승인만 하면 됨
```

---

### 1년 후 JSCLAW가 진수에게 해주는 것

```
아침 8시   텔레그램 자동 알림 → 오늘 AI 뉴스 + 논문 요약 (스케줄 자동)

출근길     텔레그램: "어제 짠 코드 버그 찾아줘"
           → 데스크탑에서 JX_CODER가 분석
           → 5분 후 텔레그램으로 결과

점심       텔레그램: "지금 핫한 MLOps 툴 조사해줘"
           → JX_RESEARCHER가 검색 + 요약

퇴근       CLI: $ jinxus "오늘 작업 커밋하고 정리해줘"
           → JX_OPS가 GitHub 자동화

취침 전    텔레그램: "내일 면접 준비용 자소서 초안 써줘"
           → JS_PERSONA가 과거 자소서 참고해서 맞춤 작성
           → 텔레그램으로 전송

새벽       데스크탑 혼자 작동 (Daemon):
           → JINXUS_CORE가 레포 전체 코드 리뷰
           → PR 생성
           → 아침에 결과 텔레그램으로
```

---

### 다른 AI 도구들과의 차이

| | ChatGPT/Claude.ai | Cursor/GitHub Copilot | **JSCLAW** |
|--|--|--|--|
| 기억 | 세션 끝나면 리셋 | 파일 단위 | **진수의 모든 과거 작업 기억** |
| 학습 | 불가 | 불가 | **진수 피드백 → 에이전트 직접 강화** |
| 실행 | 텍스트만 | 코드만 | **코드, 검색, 파일, GitHub, 스케줄 전부** |
| 접근 채널 | 웹만 | IDE만 | **텔레그램, CLI, 웹 UI, 스케줄 자동** |
| 전문성 | 범용 | 코딩만 | **5개 전문 에이전트 협업** |
| 맞춤화 | 없음 | 없음 | **진수 어투/스타일/선호도 학습** |
| 확장성 | 불가 | 제한적 | **플러그인 파일 하나로 기능 추가/제거** |

---

### 최종 목표 한 마디

지금은 "명령을 처리하는 AI"를 만들고 있지만, 로드맵을 따라가면 결국 **"진수가 생각하기 전에 먼저 준비하는 AI"**가 된다. 진수가 뭘 필요로 할지 패턴을 기억하고, 선제적으로 준비하고, 반복 작업은 자동으로 처리하는 그 수준이 최종 목표다.

이게 단순한 챗봇이나 코딩 도구가 아닌 이유는, **시간이 지날수록 진수에게 더 맞춰지고 더 강해지는 구조**이기 때문이다. 피드백 한 번 줄 때마다 에이전트가 개선되고, 작업 하나 완료할 때마다 다음 작업을 더 잘 수행할 수 있는 경험이 쌓인다.

---

*마지막 업데이트: 2026년 2월 26일*
*기반 소스: jinsoo96/JINXUS (jinxus_core.py, jx_coder.py, orchestrator.py, develop_status.md)*
*섹션 5 추가: 멀티채널(텔레그램/CLI/Daemon) + 플러그인 시스템 설계*
