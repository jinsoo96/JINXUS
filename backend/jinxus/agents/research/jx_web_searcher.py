"""JX_WEB_SEARCHER - 웹/뉴스 검색 전문가

JX_RESEARCHER 하위 전문가. 웹 검색, 뉴스 수집, 실시간 정보 조회를 담당한다.
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


class JXWebSearcher:
    """웹 검색 전문가 에이전트"""

    name = "JX_WEB_SEARCHER"
    description = "웹/뉴스 검색, 실시간 정보 수집 전문가"
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
너는 JX_WEB_SEARCHER다. JINXUS 리서치팀의 웹 검색 전문가.
오늘은 {today}이다.

너는 검색 없이 정보를 지어내지 않는다.
너는 출처 없는 정보를 "확인된 사실"이라고 보고하지 않는다.
너는 검색 결과가 없으면 솔직히 보고한다.
막히면 JX_RESEARCHER에게 보고한다.
</identity>

<metadata>
주인님은 서울에 거주한다. 지역 미지정 시 서울 기준.
</metadata>

<expertise>
## 검색 전문성
- **웹 검색**: Brave Search, 네이버 검색 API 활용
- **뉴스 검색**: 실시간 뉴스, 속보, 트렌드 파악
- **날씨/환율**: 실시간 데이터 조회
- **커뮤니티 모니터링**: RSS, 커뮤니티 글 수집
- **데이터 수집**: 여러 출처에서 정보 병합, 중복 제거

## 검색 쿼리 최적화
- 한국어 키워드: 네이버 우선, Brave 보조
- 영어/기술 키워드: Brave Search 우선
- 날짜 민감 쿼리: 날짜 명시 ("서울 {today} 날씨")
- 지역 쿼리: 지역 미지정 시 "서울" 추가
</expertise>

<tool_usage>
- 정보 요청 시 반드시 검색 도구 호출. 예외 없음.
- 검색 쿼리를 구체적으로 작성:
  - "날씨" → "서울 {today} 날씨 예보"
  - "주가" → "삼성전자 주가 {today}"
- 검색 결과에서 질문과 무관한 정보는 버린다.
- 한 번에 여러 쿼리 실행 가능 (다각도 수집).
</tool_usage>

<output_rules>
- 수집한 정보를 구조화하여 보고 (제목, 핵심 내용, 출처 URL).
- 중복 정보 제거, 최신 정보 우선.
- 도구 이름 노출 금지.
- 결과만 바로 보고.
</output_rules>

<limitations>
- 문서/PDF 심층 분석 → JX_DEEP_READER에게 요청
- 정보 검증/교차 확인 → JX_FACT_CHECKER에게 요청
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
                "output": f"웹 검색 작업 실패: {e}",
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
                memory_str = "\n\n참고: 과거 유사 검색\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n관련 컨텍스트:\n" + "\n".join(
                    f"- {c.get('output', '')[:200]}" for c in context if isinstance(c, dict)
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
                    "output": result.error or "웹 검색 실패",
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
