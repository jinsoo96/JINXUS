"""JX_CODER - 코드 작성/실행/디버깅 전문 에이전트

LangGraph 패턴 적용:
- retry 로직 (최대 3회, 지수 백오프)
- reflect (반성 → 개선점 도출)
- memory_write (장기기억 저장)
"""
import asyncio
import tempfile
import uuid
import time
import re
from typing import Optional
from pathlib import Path

from anthropic import Anthropic

from config import get_settings
from memory import get_jinx_memory


class JXCoder:
    """코드 전문가 에이전트

    블루프린트 그래프 구조:
    [receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                              ↑             │
                              └──[retry]────┘  (최대 3회)
    """

    name = "JX_CODER"
    description = "코드 작성, 실행, 디버깅을 전담하는 에이전트"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v1.0"

    def _get_system_prompt(self) -> str:
        return """너는 JX_CODER야. 주인님을 모시는 JINXUS의 코딩 전문가.

## 역할
주인님의 코딩 요청을 받아 실행 가능한 Python 코드를 작성한다.

## 코드 작성 원칙
- 반드시 실행 가능한 완전한 코드 작성
- 필요한 import 문 포함
- 결과를 print()로 출력
- try-except로 에러 핸들링

## 응답 형식
반드시 ```python 블록 안에 코드를 작성해.
"""

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행 (전체 그래프 흐름)"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        # === [receive] 과거 경험 로드 ===
        memory_context = []
        try:
            memory_context = self._memory.search_long_term(
                agent_name=self.name,
                query=instruction,
                limit=3,
            )
        except Exception:
            pass  # 메모리 실패해도 진행

        # === [plan] 실행 계획 ===
        plan = {"strategy": "generate_and_execute", "instruction": instruction}

        # === [execute] + [evaluate] + [retry] ===
        result = await self._execute_with_retry(instruction, context, memory_context)

        # === [reflect] 반성 ===
        reflection = await self._reflect(instruction, result)

        # === [memory_write] 장기기억 저장 ===
        await self._memory_write(task_id, instruction, result, reflection)

        # === [return_result] ===
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "task_id": task_id,
            "agent_name": self.name,
            "success": result["success"],
            "success_score": result["score"],
            "output": result["output"],
            "failure_reason": result.get("error"),
            "duration_ms": duration_ms,
            "reflection": reflection,
        }

    async def _execute_with_retry(
        self, instruction: str, context: list, memory_context: list
    ) -> dict:
        """실행 + 평가 + 재시도 (최대 3회, 지수 백오프)"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # === [execute] ===
                result = await self._execute(instruction, context, memory_context, last_error)

                # === [evaluate] ===
                if result["success"]:
                    return result

                # 실패 시 다음 시도를 위해 에러 저장
                last_error = result.get("error", "Unknown error")

                # 지수 백오프 (마지막 시도가 아니면)
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 1, 2, 4초
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        # 모든 재시도 실패
        return {
            "success": False,
            "score": 0.0,
            "output": f"죄송합니다 주인님, {self.max_retries}번 시도했지만 실패했습니다.\n마지막 오류: {last_error}",
            "error": last_error,
            "code": None,
        }

    async def _execute(
        self, instruction: str, context: list, memory_context: list, last_error: str = None
    ) -> dict:
        """단일 실행 시도"""
        # 이전 실패가 있으면 프롬프트에 포함
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도에서 오류 발생: {last_error}\n이 오류를 피해서 다시 작성해줘."

        # 메모리 컨텍스트
        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        code_prompt = f"""주인님의 요청: {instruction}
{memory_str}
{error_context}

실행 가능한 Python 코드를 작성해줘. 결과는 반드시 print()로 출력해.
```python 블록 안에 코드를 작성해."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": code_prompt}],
        )

        generated_text = response.content[0].text
        code = self._extract_code(generated_text)

        if not code:
            return {
                "success": False,
                "score": 0.2,
                "output": f"코드 블록을 찾지 못했습니다.\n\n응답:\n{generated_text}",
                "error": "No code block found",
                "code": None,
            }

        # 코드 실행
        exec_result = await self._execute_python(code)

        if exec_result["success"]:
            output = f"""주인님, 코드 실행이 완료되었습니다.

## 생성된 코드
```python
{code}
```

## 실행 결과
```
{exec_result['stdout']}
```
"""
            return {
                "success": True,
                "score": 0.95,
                "output": output,
                "error": None,
                "code": code,
                "stdout": exec_result["stdout"],
            }
        else:
            return {
                "success": False,
                "score": 0.3,
                "output": f"코드 실행 오류:\n```\n{exec_result['stderr']}\n```",
                "error": exec_result["stderr"],
                "code": code,
            }

    async def _reflect(self, instruction: str, result: dict) -> str:
        """반성: 이번 작업에서 배운 점"""
        if not result["success"]:
            return f"실패 원인: {result.get('error', 'Unknown')}. 다음에는 이 패턴을 피해야 함."

        # 성공 시 간단한 반성
        reflect_prompt = f"""방금 완료한 작업:
요청: {instruction}
결과: 성공

이 작업에서 배운 핵심 포인트를 1-2문장으로 정리해줘."""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": reflect_prompt}],
            )
            return response.content[0].text
        except Exception:
            return "작업 성공. 추가 반성 없음."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        """장기기억에 저장"""
        try:
            # 중요도 계산
            importance = 0.3
            if not result["success"]:
                importance += 0.4  # 실패에서 배움
            if len(reflection) > 50:
                importance += 0.2

            # 저장 조건: 실패했거나 중요도가 높으면
            if not result["success"] or importance > 0.5:
                self._memory.save_long_term(
                    agent_name=self.name,
                    task_id=task_id,
                    instruction=instruction,
                    summary=result["output"][:300],
                    outcome="success" if result["success"] else "failure",
                    success_score=result["score"],
                    key_learnings=reflection,
                    importance_score=importance,
                    prompt_version=self._prompt_version,
                )
        except Exception:
            pass  # 메모리 저장 실패해도 계속 진행

    def _extract_code(self, text: str) -> Optional[str]:
        """응답에서 Python 코드 추출"""
        pattern = r"```python\s*(.*?)\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()

        pattern = r"```\s*(.*?)\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()

        return None

    async def _execute_python(self, code: str) -> dict:
        """Python 코드 실행"""
        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = Path(tmpdir) / "script.py"
            code_file.write_text(code, encoding="utf-8")

            try:
                process = await asyncio.create_subprocess_exec(
                    "python3",
                    str(code_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30
                )

                return {
                    "success": process.returncode == 0,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                    "exit_code": process.returncode,
                }

            except asyncio.TimeoutError:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "실행 시간 초과 (30초)",
                    "exit_code": -1,
                }
            except Exception as e:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": str(e),
                    "exit_code": -1,
                }
