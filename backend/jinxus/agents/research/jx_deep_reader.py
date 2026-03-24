"""JX_DEEP_READER - 문서/자료 심층 분석 전문가

JX_RESEARCHER 하위 전문가. PDF, 이미지, 웹페이지 등
문서의 깊은 내용 파악과 분석을 담당한다.
"""
import logging
import time
import uuid
from typing import Optional

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_dynamic_executor, DynamicToolExecutor
from jinxus.agents.state_tracker import get_state_tracker, GraphNode

logger = logging.getLogger(__name__)


class JXDeepReader:
    """문서/자료 심층 분석 전문가 에이전트"""

    name = "JX_DEEP_READER"
    description = "문서/PDF/이미지/웹페이지 심층 분석 전문가"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._memory = get_jinx_memory()
        self._executor: Optional[DynamicToolExecutor] = None
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)
        self._progress_callback = None

    def _get_executor(self) -> DynamicToolExecutor:
        if self._executor is None:
            self._executor = get_dynamic_executor(self.name)
        return self._executor

    def _get_system_prompt(self) -> str:
        from datetime import datetime
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""<identity>
너는 JX_DEEP_READER다. JINXUS 리서치팀의 문서 분석 전문가.
오늘은 {today}이다.

너는 문서를 읽지 않고 내용을 추측하지 않는다.
너는 이미지/PDF를 분석하지 않고 "분석했다"고 보고하지 않는다.
너는 문서의 맥락을 왜곡하지 않는다.
막히면 JX_RESEARCHER에게 보고한다.
</identity>

<expertise>
## 문서 분석
- **PDF**: 구조 파악, 핵심 내용 추출, 표/차트 해석
- **이미지**: OCR, 다이어그램 분석, 스크린샷 해석
- **웹페이지**: 본문 추출, 구조 분석, 메타데이터 파악
- **GitHub 소스코드**: 코드 구조 분석, 의존성 파악, README 해석

## 분석 기법
- **요약**: 핵심 포인트 3-5개로 압축
- **비교**: 여러 문서 간 공통점/차이점 분석
- **추출**: 특정 정보(수치, 날짜, 이름) 추출
- **해석**: 전문 용어/기술 문서를 평이한 언어로 변환
</expertise>

<tool_usage>
- PDF 분석: pdf_reader 도구 사용
- 이미지 분석: image_analyzer 도구 사용
- 웹페이지 내용 읽기: mcp:fetch 도구 사용
- GitHub 소스코드: github_agent 도구 사용
- 문서를 반드시 읽은 후 분석 보고
</tool_usage>

<output_rules>
- 분석 결과를 구조화하여 보고 (요약, 핵심 포인트, 상세 분석).
- 원문 인용 시 페이지/섹션 명시.
- 불확실한 해석은 명시적으로 표시.
- 도구 이름 노출 금지.
</output_rules>

<limitations>
- 웹 검색 → JX_WEB_SEARCHER에게 요청
- 정보 검증 → JX_FACT_CHECKER에게 요청
- 코드 실행 불가
</limitations>"""

    async def run(self, instruction: str, context: list = None, memory_context: list = None) -> dict:
        """에이전트 실행"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            if not memory_context:
                try:
                    memory_context = self._memory.search_long_term(
                        agent_name=self.name, query=instruction, limit=3
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] 메모리 검색 실패, 건너뜀: {e}")
                    memory_context = []

            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            result = await self._execute(instruction, context, memory_context)

            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": result["success"],
                "success_score": result.get("score", 0.0),
                "output": result["output"],
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
            }
        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            logger.error(f"[{self.name}] 실행 실패: {e}")
            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": False,
                "success_score": 0.0,
                "output": f"문서 분석 작업 실패: {e}",
                "failure_reason": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }
        finally:
            self._state_tracker.complete_task(self.name)

    async def _execute(self, instruction: str, context: list, memory_context: list) -> dict:
        """DynamicToolExecutor로 실행"""
        try:
            executor = self._get_executor()

            memory_str = ""
            if memory_context:
                memory_str = "\n\n참고: 과거 유사 분석\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n관련 컨텍스트:\n" + "\n".join(
                    f"- {c.get('output', '')[:200]}" for c in context if isinstance(c, dict)
                )

            tool_cb = self._make_tool_callback()

            full_context = f"{memory_str}\n{context_str}" if memory_str or context_str else None

            result = await executor.execute(
                instruction=instruction,
                system_prompt=self._get_system_prompt(),
                context=full_context,
                tool_callback=tool_cb,
            )

            if result.success:
                tools_used = [tc.tool_name for tc in result.tool_calls]
                return {
                    "success": True,
                    "score": 0.95 if tools_used else 0.85,
                    "output": result.output,
                    "error": None,
                    "tool_calls": tools_used,
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "output": result.error or "문서 분석 실패",
                    "error": result.error,
                }
        except Exception as e:
            logger.error(f"[{self.name}] 실행 오류: {e}")
            return {
                "success": False,
                "score": 0.0,
                "output": str(e),
                "error": str(e),
            }
