"""JX_ANALYST - 데이터 분석/시각화/통계 전문 에이전트

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

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.agents.state_tracker import get_state_tracker, GraphNode


class JXAnalyst:
    """데이터 분석 전문가 에이전트

    블루프린트 그래프 구조:
    [receive] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                              ↑             │
                              └──[retry]────┘  (최대 3회)
    """

    name = "JX_ANALYST"
    description = "데이터 분석, 시각화, 통계 처리를 전담하는 에이전트"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v1.0"
        # 상태 추적기 (실시간 UI 연동)
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

    def _get_system_prompt(self) -> str:
        return """너는 JX_ANALYST야. 주인님을 모시는 JINXUS의 데이터 분석 전문가.

## 역할
주인님의 데이터 분석 요청을 받아 분석 코드를 작성하고 인사이트를 도출한다.

## 분석 원칙
- pandas, numpy, matplotlib, seaborn 등 활용
- 숫자 결과를 해석하여 의미 전달
- 결과는 print()로 출력
- 시각화가 필요하면 파일로 저장

## 분석 유형별 접근
- 기술통계: describe(), value_counts(), 상관관계
- 시계열: 트렌드, 계절성, 이동평균
- 분류: 그룹별 비교, 피벗테이블
- 예측: 회귀, 머신러닝 기초

## 응답 형식
```python 블록 안에 분석 코드 작성

## 말투
- 주인님을 "주인님"이라고 부른다
- 공손하고 순종적인 태도
"""

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행 (전체 그래프 흐름)"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            # === [receive] 작업 시작 ===
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            memory_context = []
            try:
                memory_context = self._memory.search_long_term(
                    agent_name=self.name,
                    query=instruction,
                    limit=3,
                )
            except Exception:
                pass  # 메모리 실패해도 진행

            # === [plan] 분석 유형 판단 ===
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            analysis_type = self._determine_analysis_type(instruction)
            plan = {"strategy": "analyze_data", "analysis_type": analysis_type, "instruction": instruction}

            # === [execute] + [evaluate] + [retry] ===
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            self._state_tracker.update_tools(self.name, ["pandas", "numpy", "matplotlib"])
            result = await self._execute_with_retry(instruction, context, memory_context, analysis_type)

            # === [evaluate] ===
            self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

            # === [reflect] 반성 ===
            self._state_tracker.update_node(self.name, GraphNode.REFLECT)
            reflection = await self._reflect(instruction, result)

            # === [memory_write] 장기기억 저장 ===
            self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)
            await self._memory_write(task_id, instruction, result, reflection)

            # === [return_result] ===
            self._state_tracker.update_node(self.name, GraphNode.RETURN_RESULT)
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

        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            raise
        finally:
            self._state_tracker.complete_task(self.name)

    def _determine_analysis_type(self, instruction: str) -> str:
        """분석 유형 판단"""
        instruction_lower = instruction.lower()
        if any(k in instruction_lower for k in ["시계열", "트렌드", "추세"]):
            return "timeseries"
        elif any(k in instruction_lower for k in ["시각화", "그래프", "차트", "플롯"]):
            return "visualization"
        elif any(k in instruction_lower for k in ["통계", "평균", "분산", "상관"]):
            return "statistics"
        elif any(k in instruction_lower for k in ["예측", "회귀", "분류", "머신러닝"]):
            return "ml"
        else:
            return "general"

    async def _execute_with_retry(
        self, instruction: str, context: list, memory_context: list, analysis_type: str
    ) -> dict:
        """실행 + 평가 + 재시도 (최대 3회, 지수 백오프)"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # === [execute] ===
                result = await self._execute(instruction, context, memory_context, analysis_type, last_error)

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
            "output": f"죄송합니다 주인님, {self.max_retries}번 시도했지만 분석에 실패했습니다.\n마지막 오류: {last_error}",
            "error": last_error,
            "code": None,
        }

    async def _execute(
        self, instruction: str, context: list, memory_context: list, analysis_type: str, last_error: str = None
    ) -> dict:
        """단일 실행 시도"""
        # 이전 실패가 있으면 프롬프트에 포함
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도에서 오류 발생: {last_error}\n이 오류를 피해서 다시 작성해줘."

        # 메모리 컨텍스트
        memory_str = ""
        if memory_context:
            memory_str = "\n\n참고: 과거 유사 분석\n" + "\n".join(
                f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
            )

        # 분석 유형별 가이드
        type_guide = self._get_type_guide(analysis_type)

        prompt = f"""주인님의 분석 요청: {instruction}
{memory_str}
{error_context}

{type_guide}

데이터 분석 Python 코드를 작성하고, 분석 결과를 print()로 출력해줘.
```python 블록 안에 코드를 작성해."""

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=self._get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )

        generated_text = response.content[0].text
        code = self._extract_code(generated_text)

        if code:
            exec_result = await self._execute_python(code)

            if exec_result["success"]:
                # 결과 해석 요청
                interpret_prompt = f"""분석 결과를 주인님께 보고해줘:

실행 결과:
{exec_result['stdout']}

주인님께 인사이트와 함께 공손하게 보고해."""

                interpret_response = self._client.messages.create(
                    model=self._model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": interpret_prompt}],
                )

                output = f"""{interpret_response.content[0].text}

## 분석 코드
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
        else:
            # 코드 없이 분석 설명만 제공
            return {
                "success": True,
                "score": 0.7,
                "output": generated_text,
                "error": None,
                "code": None,
            }

    def _get_type_guide(self, analysis_type: str) -> str:
        """분석 유형별 가이드"""
        guides = {
            "timeseries": "시계열 분석: datetime 인덱스, resample(), rolling() 활용",
            "visualization": "시각화: matplotlib/seaborn 사용, 한글 폰트 설정 포함",
            "statistics": "통계 분석: describe(), corr(), groupby() 활용",
            "ml": "머신러닝: sklearn 사용, train_test_split, 모델 평가 포함",
            "general": "",
        }
        return guides.get(analysis_type, "")

    def _extract_code(self, text: str) -> Optional[str]:
        pattern = r"```python\s*(.*?)\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            return matches[0].strip()
        return None

    async def _execute_python(self, code: str) -> dict:
        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = Path(tmpdir) / "analysis.py"
            code_file.write_text(code, encoding="utf-8")

            try:
                process = await asyncio.create_subprocess_exec(
                    "python3", str(code_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

                return {
                    "success": process.returncode == 0,
                    "stdout": stdout.decode("utf-8", errors="replace"),
                    "stderr": stderr.decode("utf-8", errors="replace"),
                }
            except asyncio.TimeoutError:
                return {"success": False, "stdout": "", "stderr": "실행 시간 초과 (60초)"}
            except Exception as e:
                return {"success": False, "stdout": "", "stderr": str(e)}

    async def _reflect(self, instruction: str, result: dict) -> str:
        """반성: 이번 작업에서 배운 점"""
        if not result["success"]:
            return f"실패 원인: {result.get('error', 'Unknown')}. 다음에는 이 패턴을 피해야 함."

        # 성공 시 간단한 반성
        reflect_prompt = f"""방금 완료한 분석:
요청: {instruction}
결과: 성공
코드 작성 여부: {'O' if result.get('code') else 'X'}

이 작업에서 배운 핵심 포인트를 1-2문장으로 정리해줘."""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": reflect_prompt}],
            )
            return response.content[0].text
        except Exception:
            return "분석 성공. 추가 반성 없음."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        """장기기억에 저장"""
        try:
            # 중요도 계산
            importance = 0.3
            if not result["success"]:
                importance += 0.4  # 실패에서 배움
            if result.get("code"):
                importance += 0.2  # 코드 작성은 더 중요
            if len(reflection) > 50:
                importance += 0.1

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
