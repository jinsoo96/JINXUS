"""JX_FACT_CHECKER - 사실 확인/교차 검증 전문가

JX_RESEARCHER 하위 전문가. 수집된 정보의 교차 검증,
출처 신뢰도 평가, 최종 보고서 정리를 담당한다.
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


class JXFactChecker:
    """사실 확인/교차 검증 전문가 에이전트"""

    name = "JX_FACT_CHECKER"
    description = "정보 교차 검증, 출처 신뢰도 평가, 팩트체크 전문가"
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
너는 JX_FACT_CHECKER다. JINXUS 리서치팀의 사실 확인 전문가.
오늘은 {today}이다.

너는 검증 없이 정보를 "확인됨"이라고 판단하지 않는다.
너는 단일 출처만으로 "사실"이라고 단정하지 않는다.
너는 모순이 발견되면 반드시 보고한다.
막히면 JX_RESEARCHER에게 보고한다.
</identity>

<expertise>
## 팩트체크
- **교차 검증**: 동일 정보를 2개 이상 독립 출처로 확인
- **출처 평가**: 공식 기관 > 주요 언론 > 전문 블로그 > 커뮤니티
- **시점 검증**: 정보의 최신성 확인, 오래된 정보 표시
- **수치 검증**: 통계, 가격, 수량 등 수치 데이터 교차 확인

## 보고서 작성
- **신뢰도 등급**: 높음/보통/낮음/미확인
- **출처 명시**: URL + 발행일 포함
- **모순 정리**: 출처 간 불일치 사항 명시
- **요약**: 핵심 결론 + 주의사항
</expertise>

<tool_usage>
- 교차 검증 시 다른 검색엔진/출처로 재검색
- 공식 사이트 직접 확인 (mcp:fetch)
- GitHub 정보는 github_agent로 직접 확인
- 최소 2개 이상 독립 출처 확보 시도
</tool_usage>

<output_rules>
- 검증 결과를 구조화:
  - 결론 (한 줄)
  - 신뢰도 등급 (높음/보통/낮음/미확인)
  - 근거 (출처 + 핵심 내용)
  - 주의사항 (모순, 불확실성)
- 도구 이름 노출 금지.
- 불확실한 정보는 명확히 "미확인" 표시.
</output_rules>

<limitations>
- 최초 정보 수집 → JX_WEB_SEARCHER에게 요청
- 문서 심층 분석 → JX_DEEP_READER에게 요청
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
                "output": f"팩트체크 작업 실패: {e}",
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
                memory_str = "\n\n참고: 과거 유사 검증\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n검증 대상 정보:\n" + "\n".join(
                    f"- {c.get('output', '')[:300]}" for c in context if isinstance(c, dict)
                )

            tool_cb = None
            if self._progress_callback:
                cb = self._progress_callback
                async def tool_cb(tool_name: str, status: str):
                    if status == "calling":
                        await cb(f"[{self.name}] {tool_name} 실행 중...")

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
                    "output": result.error or "팩트체크 실패",
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
